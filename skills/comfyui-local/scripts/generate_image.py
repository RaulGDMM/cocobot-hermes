#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate images locally through the OpenClaw ComfyUI broker."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


DEFAULT_BROKER_URL = "http://host.docker.internal:8791"
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_GUIDANCE_GENERATE = 3.5
DEFAULT_GUIDANCE_EDIT = 2.5
ASPECT_PRESETS = {
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "21:9": (1536, 640),
    "3:2": (1216, 832),
    "4:3": (1152, 896),
    "5:4": (1120, 896),
    "2:3": (832, 1216),
    "4:5": (896, 1120),
    "9:16": (768, 1344),
}


# Ideogram 4 sampling presets (from the official ComfyUI blueprint
# "Text to Image (Ideogram v4).json"): preset -> (num_steps, mu, std).
# The dual-DiT asymmetric guidance (DualModelGuider cfg=7.0) is constant
# in the blueprint; CFGOverride pins the conditional model to cfg=3.0
# over the [0.7, 1.0] sigma range.
IDEOGRAM4_PRESETS = {
    "quality": (48, 0.0, 1.5),
    "default": (20, 0.0, 1.75),
    "turbo": (12, 0.5, 1.75),
}
IDEOGRAM4_DUAL_CFG = 7.0
IDEOGRAM4_CFG_OVERRIDE = 3.0
DEFAULT_LLAMA_URL = "http://172.23.176.1:30000"

# Ideogram 4's official open-source "magic prompt" system prompt (v1, from
# ideogram-oss/ideogram4 magic_prompt_system_prompts/v1.txt). It converts a
# natural-language idea into the structured JSON caption the model was
# trained on. Plain-text prompts trigger the built-in safety filter at a
# high false-positive rate; JSON captions are in-distribution.
MAGIC_PROMPT_FILE = Path(__file__).resolve().parent / "ideogram4_magic_prompt_v1.txt"
MAGIC_PROMPT_USER_TEMPLATE = (
    "TARGET IMAGE ASPECT RATIO: {aspect_ratio} (width:height).\n"
    "User idea: {original_prompt}"
)


def _ideogram4_aspect(width: int, height: int) -> str:
    import math

    g = math.gcd(width, height)
    return f"{width // g}:{height // g}"


def magic_prompt_expansion(
    prompt: str,
    width: int,
    height: int,
    llama_url: str | None = None,
) -> str | None:
    """Expand a natural-language prompt into an Ideogram 4 JSON caption via
    the local LLM. Returns the minified JSON string, or None on any failure
    (caller then falls back to the raw prompt)."""
    try:
        system = MAGIC_PROMPT_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[magic-prompt] No system prompt file: {exc}")
        return None
    base = (llama_url or os.environ.get("OPENCLAW_LLAMA_URL") or DEFAULT_LLAMA_URL).rstrip("/")
    body = json.dumps(
        {
            "model": "local",
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": MAGIC_PROMPT_USER_TEMPLATE.format(
                        aspect_ratio=_ideogram4_aspect(width, height),
                        original_prompt=prompt,
                    ),
                },
            ],
            "temperature": 0.1,
            "max_tokens": 8000,
            "stream": False,
        }
    ).encode("utf-8")
    try:
        req = urlrequest.Request(
            f"{base}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data["choices"][0]["message"].get("content") or "").strip()
    except Exception as exc:
        print(f"[magic-prompt] LLM call failed ({exc}); using raw prompt (higher block risk)")
        return None
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        print("[magic-prompt] No JSON in LLM output; using raw prompt")
        return None
    candidate = text[start : end + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        print("[magic-prompt] LLM output was not valid JSON; using raw prompt")
        return None
    if not isinstance(obj, dict) or "compositional_deconstruction" not in obj:
        print("[magic-prompt] LLM JSON missing compositional_deconstruction; using raw prompt")
        return None
    return candidate


# Qwen-Image 2.1 prompt enhancer (v1): local-LLM rewrite of a short brief
# into a full 5-slot layout brief (artifact type, scene, quoted+placed text
# strings, typography, camera/light). Inspired by Qwen's official PE-T2I
# models, without needing the 9.4GB weights. See
# references/qwen-image-2-1-prompt-guide.md. Plain-text output (the model
# takes natural language, unlike Ideogram 4's JSON captions).
QWEN21_ENHANCE_FILE = Path(__file__).resolve().parent / "qwen_image_2.1_enhance_v1.txt"
QWEN21_ENHANCE_USER_TEMPLATE = (
    "TARGET IMAGE ASPECT RATIO: {aspect_ratio} (width:height).\n"
    "MODE: {mode}\n"
    "USER BRIEF:\n{original_prompt}"
)


def _qwen21_prompt_complete(text: str) -> bool:
    """A prompt that ends mid-word/mid-phrase is a truncated LLM output
    (the model stopped before finishing, well under max_tokens). Treat any
    output that does not end with terminal punctuation as incomplete and
    retry / fall back to the raw brief — a truncated 5-slot prompt silently
    drops the subject's defining features (bioluminescence, eyes, tail)."""
    stripped = text.rstrip()
    if not stripped:
        return False
    return bool(re.search(r"[.!?…:;»\"')\]]\s*$", stripped))


def qwen21_prompt_expansion(
    prompt: str,
    width: int,
    height: int,
    mode: str,
    llama_url: str | None = None,
) -> str | None:
    """Expand a short Qwen-Image 2.1 brief into a detailed 5-slot English
    prompt via the local LLM. mode is "t2i" or "edit". Returns the cleaned
    prompt text, or None on any failure (caller keeps the raw prompt)."""
    try:
        system = QWEN21_ENHANCE_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[qwen21-enhance] No system prompt file: {exc}")
        return None
    base = (llama_url or os.environ.get("OPENCLAW_LLAMA_URL") or DEFAULT_LLAMA_URL).rstrip("/")
    if mode == "edit":
        aspect = "same as the reference image(s) (edit mode)"
    else:
        aspect = _ideogram4_aspect(width, height)
    body = json.dumps(
        {
            "model": "local",
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": QWEN21_ENHANCE_USER_TEMPLATE.format(
                        aspect_ratio=aspect,
                        mode=mode,
                        original_prompt=prompt,
                    ),
                },
            ],
            "temperature": 0.3,
            "max_tokens": 1200,
            "stream": False,
        }
    ).encode("utf-8")
    try:
        text = ""
        for attempt in (1, 2):
            req = urlrequest.Request(
                f"{base}/v1/chat/completions",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urlrequest.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            if text.startswith("```"):
                text = text.strip("`").lstrip("text").strip()
            # Drop any leading label like "Final prompt:" or "Prompt:"
            if ":" in text.split("\n", 1)[0] and len(text.split("\n", 1)[0]) < 40:
                text = text.split("\n", 1)[1].strip()
            text = text.strip()
            if len(text) >= 20 and _qwen21_prompt_complete(text):
                break
            if attempt == 1:
                print(f"[qwen21-enhance] Incomplete LLM output ({len(text)} chars, no final punctuation), retrying once")
    except Exception as exc:
        print(f"[qwen21-enhance] LLM call failed ({exc}); using raw prompt")
        return None
    if len(text) < 20 or not _qwen21_prompt_complete(text):
        print(f"[qwen21-enhance] LLM output truncated/incomplete ({len(text)} chars); using raw prompt")
        return None
    return text


def build_ideogram4_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    width: int,
    height: int,
    steps: int,
    guidance: float,
    seed: int,
    preset: str = "default",
) -> dict[str, object]:
    # Ideogram 4: dual DiT (conditional + unconditional fp8), Qwen3-VL-8B
    # text encoder (clip type "ideogram4"), flux2-vae. Flow-matching via
    # Ideogram4Scheduler (mu/std from preset). Asymmetric guidance:
    # DualModelGuider cfg=7 with an unconditional DiT on the negative
    # pass, plus CFGOverride cfg=3 from 70% into the schedule. No text
    # negative prompt exists for this model.
    preset_steps, mu, std = IDEOGRAM4_PRESETS[preset]
    if steps is None:
        steps = preset_steps
    # Latent sizes must be multiples of 16, min 256 (blueprint math)
    width = max(((width + 15) // 16) * 16, 256)
    height = max(((height + 15) // 16) * 16, 256)
    # Frontend-compatible seed range
    seed = seed % 4294967295
    return {
        "177": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "flux2-vae.safetensors"},
        },
        "185": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "ideogram4_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        },
        "200": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "ideogram4_unconditional_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        },
        "187": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_8b_fp8_scaled.safetensors",
                "type": "ideogram4",
                "device": "default",
            },
        },
        "186": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["187", 0]},
        },
        # Unconditional pass conditioning (null/zero)
        "178": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["186", 0]},
        },
        "179": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "184": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        "182": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        "183": {
            "class_type": "Ideogram4Scheduler",
            "inputs": {
                "steps": steps,
                "width": width,
                "height": height,
                "mu": mu,
                "std": std,
            },
        },
        # Asymmetric dual-model guidance (positive DiT vs unconditional DiT)
        "201": {
            "class_type": "DualModelGuider",
            "inputs": {
                "model": ["203", 0],
                "model_negative": ["200", 0],
                "positive": ["186", 0],
                "cfg": IDEOGRAM4_DUAL_CFG,
                "negative": ["178", 0],
            },
        },
        # Pin the conditional model to cfg=3.0 over the last 30% of sigmas
        "203": {
            "class_type": "CFGOverride",
            "inputs": {
                "model": ["185", 0],
                "cfg": IDEOGRAM4_CFG_OVERRIDE,
                "start_percent": 0.7,
                "end_percent": 1.0,
            },
        },
        "180": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["184", 0],
                "guider": ["201", 0],
                "sampler": ["182", 0],
                "sigmas": ["183", 0],
                "latent_image": ["179", 0],
            },
        },
        "181": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["180", 0], "vae": ["177", 0]},
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["181", 0]},
        },
    }


QWEN21_CLIP = "qwen3vl_8b_int8_convrot.safetensors"
QWEN21_VAE = "qwen_image_2.1_vae_bf16.safetensors"

MOSS_SFT_DIT = "moss_image_sft_bf16.safetensors"
MOSS_CLIP = "qwen3.5_9b_int8_convrot.safetensors"
MOSS_VAE = "flux2-vae.safetensors"

FLUX3_KLEIN_DIT = "flux3-image-klein-bf16.safetensors"
FLUX3_KLEIN_BASE_DIT = "flux3-image-klein-base-bf16.safetensors"
FLUX3_CLIP = "qwen3vl_4b_bf16.safetensors"
FLUX3_UPSAMPLE_CLIP = "qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors"
FLUX3_UPSAMPLE_FILE = Path(__file__).resolve().parent / "flux3_upsampler_system.txt"


def build_workflow(
    upsample_system: str = "",
    *,
    prompt: str,
    filename_prefix: str,
    width: int,
    height: int,
    steps: int,
    guidance: float,
    seed: int,
    model: str = "flux1-dev",
    preset: str = "default",
    dit_override: str | None = None,
    negative: str = "",
) -> dict[str, object]:
    if model == "ideogram4":
        return build_ideogram4_workflow(
            prompt=prompt,
            filename_prefix=filename_prefix,
            width=width,
            height=height,
            steps=steps,
            guidance=guidance,
            seed=seed,
            preset=preset,
        )
    if model == "qwen-image-2.1":
        # Qwen-Image 2.1 (7B unified t2i + edit, 2K native, RGBA).
        # Mirrors the official Comfy-Org template image_qwen_image_2_1_t2i.json
        # subgraph: UNETLoader + CLIPLoader(type qwen_image, Qwen3VL-8B) +
        # VAELoader + TextEncodeQwenImage21 (no refs in t2i mode) + KSampler
        # (euler/simple, cfg 1) + VAEDecode. Native resolution is 2048;
        # official template defaults to 1024 and 25 steps.
        width = max(((width + 31) // 32) * 32, 32)
        height = max(((height + 31) // 32) * 32, 32)
        # Only the bf16 DiT is installed (int8 weights deleted 2026-09-21).
        dit_name = dit_override or "qwen_image_2.1_bf16.safetensors"
        return {
            "451": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": dit_name, "weight_dtype": "default"},
            },
            "453": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": QWEN21_CLIP, "type": "qwen_image", "device": "default"},
            },
            "454": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": QWEN21_VAE},
            },
            "452": {
                "class_type": "TextEncodeQwenImage21",
                "inputs": {
                    "clip": ["453", 0],
                    "prompt": prompt,
                    "negative_prompt": "",
                    "vae": ["454", 0],
                    # Required by the API validator even though the UI
                    # defaults it. In t2i (no image_N refs) it only sizes the
                    # unused square latent the node also returns; the KSampler
                    # uses EmptyLatentImage instead.
                    "resolution": 1024,
                },
            },
            "456": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "458": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["451", 0],
                    "positive": ["452", 0],
                    "negative": ["452", 1],
                    "latent_image": ["456", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "457": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["458", 0], "vae": ["454", 0]},
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": filename_prefix, "images": ["457", 0]},
            },
        }
    if model == "moss-image":
        # MOSS-Image SFT (OpenMOSS, Apache-2.0). Native support in ComfyUI >= 0.42:
        # UNETLoader + CLIPLoader(type moss_image, Qwen3.5-9B) + FLUX.2 VAE +
        # EmptyFlux2LatentImage (Flux2 latent format). Official/community recipe:
        # er_sde, scheduler simple, 30 steps, CFG 2.5, negative "plastic skin, waxy skin".
        width = max(((width + 31) // 32) * 32, 32)
        height = max(((height + 31) // 32) * 32, 32)
        dit_name = dit_override or MOSS_SFT_DIT
        return {
            "700": {"class_type": "UNETLoader", "inputs": {"unet_name": dit_name, "weight_dtype": "default"}},
            "701": {"class_type": "CLIPLoader", "inputs": {"clip_name": MOSS_CLIP, "type": "moss_image", "device": "default"}},
            "702": {"class_type": "VAELoader", "inputs": {"vae_name": MOSS_VAE}},
            "703": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["701", 0], "text": prompt}},
            "704": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["701", 0], "text": negative}},
            "705": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "706": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["700", 0],
                    "positive": ["703", 0],
                    "negative": ["704", 0],
                    "latent_image": ["705", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": guidance,
                    "sampler_name": "er_sde",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "707": {"class_type": "VAEDecode", "inputs": {"samples": ["706", 0], "vae": ["702", 0]}},
            "708": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["707", 0]}},
        }
    if model in ("flux3-klein", "flux3-klein-base"):
        # FLUX 3 Image Klein (BFL, 5.6B, open weights, FLUX Kommunity License).
        # Mirrors the official ComfyUI workflows flux3_klein_bf16_t2i.json /
        # flux3_klein_base_bf16_t2i.json: UNETLoader + CLIPLoader(type flux3,
        # Qwen3VL-4B) + ModelSamplingFlux (max_shift=base_shift=ln(16)) +
        # KSampler euler/simple (distilled: 16 steps cfg 1; base: 50 steps
        # cfg 4). VAE = FLUX.2 VAE, Flux2 latent format. Prompt upsampler is
        # part of the UI template but OFF here (raw prompts, A/B fairness).
        width = max(((width + 31) // 32) * 32, 32)
        height = max(((height + 31) // 32) * 32, 32)
        dit_name = dit_override or (
            FLUX3_KLEIN_BASE_DIT if model == "flux3-klein-base" else FLUX3_KLEIN_DIT
        )
        # Official t2i template ships a prompt upsampler subgraph (BFL: "do not
        # skip it"): Qwen3.5-9B upsampler clip -> TextGenerate rewrites the raw
        # request into one detailed caption BEFORE qwen3vl CLIPTextEncode.
        # Sampling widgets mirror the template (temp 1, top_k 1 = greedy-ish,
        # presence 1.5, max 3584). DynamicCombo sub-inputs use DOTTED keys
        # ("sampling_mode.top_k") like every other v3 dynamic input.
        text_src: object = prompt
        wf: dict[str, object] = {
            "800": {"class_type": "UNETLoader", "inputs": {"unet_name": dit_name, "weight_dtype": "default"}},
            "801": {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX3_CLIP, "type": "flux3", "device": "default"}},
            "802": {"class_type": "VAELoader", "inputs": {"vae_name": MOSS_VAE}},
            "803": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["801", 0], "text": text_src}},
            "804": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["801", 0], "text": negative}},
            "805": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "806": {"class_type": "ModelSamplingFlux", "inputs": {
                "model": ["800", 0], "max_shift": 2.77259, "base_shift": 2.77259,
                "width": width, "height": height}},
            "807": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["806", 0], "positive": ["803", 0], "negative": ["804", 0],
                    "latent_image": ["805", 0], "seed": seed, "steps": steps,
                    "cfg": guidance, "sampler_name": "euler", "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "808": {"class_type": "VAEDecode", "inputs": {"samples": ["807", 0], "vae": ["802", 0]}},
            "809": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["808", 0]}},
        }
        if upsample_system:
            wf["810"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX3_UPSAMPLE_CLIP, "type": "flux3", "device": "default"}}
            wf["811"] = {"class_type": "TextGenerate", "inputs": {
                "clip": ["810", 0],
                "prompt": "ORIGINAL PROMPT:\n" + prompt,
                "max_length": 3584,
                "sampling_mode": "on",
                "sampling_mode.temperature": 1.0,
                "sampling_mode.top_k": 1,
                "sampling_mode.top_p": 0.95,
                "sampling_mode.min_p": 0.0,
                "sampling_mode.repetition_penalty": 1.0,
                "sampling_mode.seed": seed,
                "sampling_mode.presence_penalty": 1.5,
                "thinking": False,
                "use_default_template": True,
                "mtp": "off",
                "system_prompt": upsample_system,
            }}
            wf["803"]["inputs"]["text"] = ["811", 0]  # type: ignore[index]
        return wf
    if model == "z-image-turbo":
        # Z-Image-Turbo: single Qwen3-4B text encoder (lumina2), AuraFlow sampling, distilled (CFG=1)
        effective_steps = max(steps, 8)
        return {
            "4": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"},
            },
            "8": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "ae.safetensors"},
            },
            "11": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "mode": "default"},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["11", 0]},
            },
            "33": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "", "clip": ["11", 0]},
            },
            "5": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "40": {
                "class_type": "ModelSamplingAuraFlow",
                "inputs": {"model": ["4", 0], "shift": 3},
            },
            "13": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["40", 0], "positive": ["6", 0], "negative": ["33", 0],
                    "latent_image": ["5", 0], "seed": seed, "steps": effective_steps,
                    "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                },
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["13", 0], "vae": ["8", 0]},
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": filename_prefix, "images": ["9", 0]},
            },
        }
    if model == "flux2-klein-9b":
        # FLUX.2 Klein 9B: single Qwen3 text encoder, flux2-vae
        return {
            "4": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "flux-2-klein-9b-fp8.safetensors",
                    "weight_dtype": "default",
                },
            },
            "8": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "flux2-vae.safetensors",
                },
            },
            "11": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen_3_8b_fp8mixed.safetensors",
                    "type": "flux2",
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["11", 0],
                },
            },
            "33": {
                "class_type": "ConditioningZeroOut",
                "inputs": {
                    "conditioning": ["6", 0],
                },
            },
            "35": {
                "class_type": "FluxGuidance",
                "inputs": {
                    "conditioning": ["6", 0],
                    "guidance": guidance,
                },
            },
            "5": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
            },
            "13": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["4", 0],
                    "positive": ["35", 0],
                    "negative": ["33", 0],
                    "latent_image": ["5", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["13", 0],
                    "vae": ["8", 0],
                },
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["9", 0],
                },
            },
        }
    else:
        # FLUX.1 Dev: dual CLIP (clip_l + t5xxl), ModelSamplingFlux
        return {
            "4": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "flux1-dev.safetensors",
                    "weight_dtype": "default",
                },
            },
            "8": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "ae.safetensors",
                },
            },
            "11": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "t5xxl_fp16.safetensors",
                    "type": "flux",
                },
            },
            "6": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {
                    "clip": ["11", 0],
                    "clip_l": prompt,
                    "t5xxl": prompt,
                    "guidance": guidance,
                },
            },
            "33": {
                "class_type": "ConditioningZeroOut",
                "inputs": {
                    "conditioning": ["6", 0],
                },
            },
            "5": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
            },
            "12": {
                "class_type": "ModelSamplingFlux",
                "inputs": {
                    "model": ["4", 0],
                    "max_shift": 1.15,
                    "base_shift": 0.5,
                    "width": width,
                    "height": height,
                },
            },
            "13": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["12", 0],
                    "positive": ["6", 0],
                    "negative": ["33", 0],
                    "latent_image": ["5", 0],
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["13", 0],
                    "vae": ["8", 0],
                },
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": filename_prefix,
                    "images": ["9", 0],
                },
            },
        }


def build_qwen21_edit_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    ref_images: list[str],
    steps: int,
    seed: int,
    ref_resolution: int = 1024,
    dit_override: str | None = None,
    qwen_cfg: float = 1.0,
    qwen_negative: str = "",
) -> dict[str, object]:
    """Qwen-Image 2.1 multi-reference editing workflow.

    Mirrors the official Comfy-Org template image_qwen_image_2_1_image_edit.json
    (subgraph 'Image Edit (Qwen Image 2.1)'), flattened for the API:
    UNETLoader → QwenImage21Cache → KSampler(euler/simple/cfg1), with the
    reference images plugged into TextEncodeQwenImage21 as autogrow inputs
    image_1..image_N. The node outputs a latent at the first reference's
    (resized) size — that, not EmptyLatentImage, drives the KSampler so the
    edit stays at the reference's dimensions.

    ComfySwitchNode from the template is frontend-only; in API mode we wire
    the encoder latent straight to the KSampler (edit mode is the only path
    this builder serves).
    """
    # Only the bf16 DiT is installed (int8 weights deleted 2026-09-21).
    dit_name = dit_override or "qwen_image_2.1_bf16.safetensors"
    if not 1 <= len(ref_images) <= 16:
        raise SystemExit("qwen-image-2.1 editing needs 1..16 reference images")

    wf: dict[str, object] = {
        "451": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": dit_name, "weight_dtype": "default"},
        },
        "453": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": QWEN21_CLIP, "type": "qwen_image", "device": "default"},
        },
        "454": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": QWEN21_VAE},
        },
        "469": {
            # KV prefix cache: makes multi-ref editing viable (refs are
            # encoded once and reused every step). 'auto' = spare VRAM.
            "class_type": "QwenImage21Cache",
            "inputs": {"model": ["451", 0], "device": "auto", "dtype": "default"},
        },
        "474": {
            "class_type": "TextEncodeQwenImage21",
            "inputs": {
                "clip": ["453", 0],
                "prompt": prompt,
                "negative_prompt": qwen_negative,
                "vae": ["454", 0],
                # Each reference is resized to ~ref_resolution px (aspect
                # kept, multiple of 32) before VAE-encoding.
                "resolution": ref_resolution,
                # Reference images are wired in the loop below as dotted
                # top-level keys ("images.image_N"); the runtime re-groups
                # them into the `images` dict parameter via dynamic_paths.
            },
        },
        "458": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["469", 0],
                "positive": ["474", 0],
                "negative": ["474", 1],
                "latent_image": ["474", 2],
                "seed": seed,
                "steps": steps,
                "cfg": qwen_cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "457": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["458", 0], "vae": ["454", 0]},
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["457", 0]},
        },
    }
    for i, name in enumerate(ref_images, start=1):
        wf[str(400 + i)] = {"class_type": "LoadImage", "inputs": {"image": name}}
        wf["474"]["inputs"][f"images.image_{i}"] = [str(400 + i), 0]
    return wf


def build_flux3_edit_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    ref_images: list[str],
    seed: int,
    steps: int,
    guidance: float,
    model: str = "flux3-klein",
) -> dict[str, object]:
    """FLUX 3 Klein editing, mirroring the official BFL workflow
    flux3_klein_bf16_i2i.json / _mi2i.json: LoadImage -> ImageScaleToTotalPixels
    (1 MP, multiple of 16) -> ReferenceMultiLatent (attaches ref latents to BOTH
    positive and negative conditioning and feeds them via dotted keys
    images.imageN — same autogrow API format as Qwen's images.image_N).
    Output latent size comes from the (scaled) first reference via GetImageSize.
    KSampler: distilled 16 steps cfg 1; base 50 steps cfg 1 (template uses
    guidance 1 for editing on both checkpoints)."""
    shift = round(math.log(max(steps, 2)), 5)
    wf: dict[str, object] = {
        "900": {"class_type": "LoadImage", "inputs": {"image": ref_images[0], "upload": "image"}},
        "901": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["900", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 16}},
        "902": {"class_type": "GetImageSize", "inputs": {"image": ["901", 0]}},
        "903": {"class_type": "UNETLoader", "inputs": {"unet_name": FLUX3_KLEIN_BASE_DIT if model == "flux3-klein-base" else FLUX3_KLEIN_DIT, "weight_dtype": "default"}},
        "904": {"class_type": "CLIPLoader", "inputs": {"clip_name": FLUX3_CLIP, "type": "flux3", "device": "default"}},
        "905": {"class_type": "VAELoader", "inputs": {"vae_name": MOSS_VAE}},
        "906": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["904", 0], "text": prompt}},
        "907": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["904", 0], "text": ""}},
        "908": {
            "class_type": "ReferenceMultiLatent",
            "inputs": {
                "positive": ["906", 0],
                "negative": ["907", 0],
                "vae": ["905", 0],
                "resolution": "resize",
                "resolution.megapixels": 1.0,
                "images.image0": ["901", 0],
            },
        },
        "909": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["902", 0], "height": ["902", 1], "batch_size": 1}},
        "910": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["903", 0], "max_shift": shift, "base_shift": shift, "width": ["902", 0], "height": ["902", 1]}},
        "911": {
            "class_type": "KSampler",
            "inputs": {"model": ["910", 0], "positive": ["908", 0], "negative": ["908", 1], "latent_image": ["909", 0], "seed": seed, "steps": steps, "cfg": guidance, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
        },
        "912": {"class_type": "VAEDecode", "inputs": {"samples": ["911", 0], "vae": ["905", 0]}},
        "913": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["912", 0]}},
    }
    for i, extra in enumerate(ref_images[1:], start=1):
        wf[f"92{i}"] = {"class_type": "LoadImage", "inputs": {"image": extra, "upload": "image"}}
        wf[f"93{i}"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": [f"92{i}", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 16}}
        wf["908"]["inputs"][f"images.image{i}"] = [f"93{i}", 0]  # type: ignore[index]
    return wf


def build_kontext_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    input_image: str,
    input_image2: str | None,
    steps: int,
    guidance: float,
    seed: int,
    model: str = "flux1-dev",
) -> dict[str, object]:
    """Build an image-edit workflow. FLUX.1 uses Kontext, FLUX.2 Klein uses native editing."""
    if model == "flux2-klein-9b":
        # FLUX.2 Klein 9B multi-reference editing via ReferenceLatent chain
        # Each image: LoadImage → VAEEncode → ReferenceLatent
        # ReferenceLatent nodes chain sequentially to inject visual conditioning
        wf: dict[str, object] = {
            "37": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "flux-2-klein-9b-fp8.safetensors",
                    "weight_dtype": "default",
                },
            },
            "39": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "flux2-vae.safetensors"},
            },
            "38": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen_3_8b_fp8mixed.safetensors",
                    "type": "flux2",
                },
            },
        }
        # Positive prompt encoding
        wf["6"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["38", 0]},
        }
        # Negative: ConditioningZeroOut of the same prompt
        wf["33"] = {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["6", 0]},
        }
        # Build ReferenceLatent chain for each image
        images = [input_image]
        if input_image2:
            images.append(input_image2)

        img_idx = 100
        encode_idx = 120
        ref_idx = 170
        first_latent = None

        for i, img in enumerate(images):
            # LoadImage → VAEEncode
            wf[str(img_idx)] = {
                "class_type": "LoadImage",
                "inputs": {"image": img},
            }
            # VAEEncode
            wf[str(encode_idx)] = {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": [str(img_idx), 0],
                    "vae": ["39", 0],
                },
            }
            # ReferenceLatent: inject image features into conditioning
            # First image uses prompt conditioning as base
            # Subsequent images chain from previous ReferenceLatent
            if i == 0:
                cond_input = ["6", 0]
            else:
                cond_input = [str(ref_idx - 1), 0]
            wf[str(ref_idx)] = {
                "class_type": "ReferenceLatent",
                "inputs": {
                    "conditioning": cond_input,
                    "latent": [str(encode_idx), 0],
                },
            }
            first_latent = encode_idx
            img_idx += 1
            encode_idx += 1
            ref_idx += 1

        # Last ReferenceLatent output → FluxGuidance → KSampler
        last_ref = ref_idx - 1
        wf["35"] = {
            "class_type": "FluxGuidance",
            "inputs": {
                "conditioning": [str(last_ref), 0],
                "guidance": guidance,
            },
        }
        wf["31"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": ["37", 0],
                "positive": ["35", 0],
                "negative": ["33", 0],
                "latent_image": [str(first_latent), 0],
                "seed": seed,
                "steps": steps,
                "cfg": 4.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 0.75,
            },
        }
        wf["8"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["31", 0], "vae": ["39", 0]},
        }
        wf["10"] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": ["8", 0],
            },
        }
        return wf

    # --- FLUX.1 Kontext (original) ---
    wf = {
        "37": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux1-dev-kontext_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        },
        "39": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "ae.safetensors"},
        },
        "38": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "flux",
                "device": "default",
            },
        },
    }

    wf["100"] = {"class_type": "LoadImage", "inputs": {"image": input_image}}

    if input_image2:
        wf["101"] = {"class_type": "LoadImage", "inputs": {"image": input_image2}}
        wf["146"] = {
            "class_type": "ImageStitch",
            "inputs": {
                "image1": ["100", 0],
                "image2": ["101", 0],
                "direction": "right",
                "match_image_size": True,
                "max_columns": 0,
                "color": "white",
                "spacing_width": 0,
                "spacing_color": "white",
            },
        }
        scale_input = ["146", 0]
    else:
        scale_input = ["100", 0]

    wf["42"] = {"class_type": "FluxKontextImageScale", "inputs": {"image": scale_input}}
    wf["124"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["42", 0], "vae": ["39", 0]}}
    wf["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["38", 0]}}
    wf["177"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["6", 0], "latent": ["124", 0]}}
    wf["35"] = {"class_type": "FluxGuidance", "inputs": {"conditioning": ["177", 0], "guidance": guidance}}
    wf["135"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}}
    wf["31"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["37", 0],
            "positive": ["35", 0],
            "negative": ["135", 0],
            "latent_image": ["124", 0],
            "seed": seed,
            "steps": steps,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    }
    wf["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["31", 0], "vae": ["39", 0]}}
    wf["10"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}}

    return wf


def upload_file(broker_url: str, file_path: Path, timeout: int = 60) -> str:
    """Upload a local image to the broker and return the filename in ComfyUI input dir."""
    data = file_path.read_bytes()
    ct = "image/png"
    suffix = file_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        ct = "image/jpeg"
    elif suffix == ".webp":
        ct = "image/webp"

    req = urlrequest.Request(
        f"{broker_url}/v1/upload",
        data=data,
        headers={"Content-Type": ct, "Content-Length": str(len(data))},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["filename"]


def request_json(method: str, url: str, payload: dict[str, object] | None = None, timeout: int = 30) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urlrequest.Request(url, data=data, headers=headers, method=method)
    with urlrequest.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def request_json_with_retries(
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    *,
    timeout: int = 30,
    retries: int = 6,
    retry_delay: float = 0.4,
) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return request_json(method, url, payload=payload, timeout=timeout)
        except urlerror.URLError as exc:
            last_error = exc
            reason = getattr(exc, "reason", None)
            if attempt == retries:
                raise
            if isinstance(reason, OSError):
                print(f"Broker connection failed (attempt {attempt}/{retries}): {reason}; retrying...", file=sys.stderr)
                time.sleep(retry_delay * attempt)
                continue
            raise
        except ConnectionError as exc:
            last_error = exc
            if attempt == retries:
                raise
            print(f"Broker connection failed (attempt {attempt}/{retries}): {exc}; retrying...", file=sys.stderr)
            time.sleep(retry_delay * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("request_json_with_retries reached an unexpected state")


def download_file(url: str, target_path: Path, timeout: int, retries: int = 15, retry_delay: float = 1.0) -> None:
    request = urlrequest.Request(url, headers={"Accept": "image/png,image/*,*/*"}, method="GET")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                body = response.read()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(body)
            return
        except urlerror.HTTPError as exc:
            last_error = exc
            if exc.code != 404 or attempt == retries:
                raise
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                raise
        time.sleep(retry_delay)

    if last_error is not None:
        raise last_error


def parse_prompts(single_prompt: str | None, prompts_json: str | None) -> list[str]:
    prompts: list[str] = []
    if single_prompt:
        prompts.append(single_prompt)
    if prompts_json:
        loaded = json.loads(prompts_json)
        if not isinstance(loaded, list) or not loaded or not all(isinstance(item, str) and item.strip() for item in loaded):
            raise ValueError("--prompts-json must be a non-empty JSON array of strings")
        prompts.extend(item.strip() for item in loaded)
    if not prompts:
        raise ValueError("Provide --prompt or --prompts-json")
    return prompts


def resolve_size(width: int | None, height: int | None, aspect: str) -> tuple[int, int]:
    if width is not None and height is not None:
        return width, height
    return ASPECT_PRESETS[aspect]


def generate_one(
    *,
    broker_url: str,
    timeout_seconds: int,
    prompt: str,
    output_path: Path,
    width: int,
    height: int,
    steps: int,
    guidance: float,
    seed: int,
    index: int,
    input_image: str | None = None,
    input_image2: str | None = None,
    model: str = "flux1-dev",
    preset: str = "default",
    llama_url: str | None = None,
    dit_override: str | None = None,
    qwen_cfg: float = 1.0,
    qwen_negative: str = "",
    negative: str = "",
    upsample_system: str = "",
) -> str | None:
    # Ideogram 4 is trained on structured JSON captions. Natural-language
    # prompts hit its built-in safety filter at a high false-positive rate,
    # so expand them through the local LLM ("magic prompt") first — unless
    # the user already supplied a structured JSON caption.
    if model == "ideogram4" and not input_image:
        is_structured = False
        try:
            candidate = json.loads(prompt.strip())
            is_structured = (
                isinstance(candidate, dict)
                and "compositional_deconstruction" in candidate
            )
        except (json.JSONDecodeError, ValueError):
            is_structured = False
        if not is_structured:
            expanded = magic_prompt_expansion(prompt, width, height, llama_url)
            if expanded is not None:
                print(f"[{index}] [magic-prompt] Expanded prompt to structured JSON caption")
                prompt = expanded
    if input_image:
        if model in ("flux3-klein", "flux3-klein-base"):
            refs = [input_image]
            if input_image2:
                refs.append(input_image2)
            workflow = build_flux3_edit_workflow(
                prompt=prompt,
                filename_prefix=f"openclaw-local-{output_path.stem}-{seed}",
                ref_images=refs,
                seed=seed,
                steps=steps,
                guidance=guidance,
                model=model,
            )
        elif model == "qwen-image-2.1":
            refs = [input_image]
            if input_image2:
                refs.append(input_image2)
            workflow = build_qwen21_edit_workflow(
                prompt=prompt,
                filename_prefix=f"openclaw-local-{output_path.stem}-{seed}",
                ref_images=refs,
                steps=steps,
                seed=seed,
                dit_override=dit_override,
                qwen_cfg=qwen_cfg,
                qwen_negative=qwen_negative,
            )
        else:
            workflow = build_kontext_workflow(
                prompt=prompt,
                filename_prefix=f"openclaw-local-{output_path.stem}-{seed}",
                input_image=input_image,
                input_image2=input_image2,
                steps=steps,
                guidance=guidance,
                seed=seed,
                model=model,
            )
        label = f"edit, seed={seed}, model={model}"
    else:
        workflow = build_workflow(
            prompt=prompt,
            filename_prefix=f"openclaw-local-{output_path.stem}-{seed}",
            width=width,
            height=height,
            steps=steps,
            guidance=guidance,
            seed=seed,
            model=model,
            preset=preset,
            dit_override=dit_override,
            negative=negative,
            upsample_system=upsample_system,
        )
        label = f"seed={seed}, size={width}x{height}, model={model}"

    if upsample_system and not any(
        n.get("class_type") == "TextGenerate" for n in workflow.values() if isinstance(n, dict)
    ):
        return f"[{index}] --upsample requested but the workflow has no TextGenerate node (wiring bug)"
    if upsample_system:
        print(f"[{index}] FLUX 3 prompt upsampler ON (TextGenerate in graph)")

    payload = {
        "workflow": workflow,
        "timeout_seconds": timeout_seconds,
    }

    print(f"[{index}] Sending to broker ({label})")

    try:
        response = request_json_with_retries(
            "POST",
            f"{broker_url}/v1/generate",
            payload=payload,
            timeout=timeout_seconds + 90,
        )
    except Exception as exc:
        return f"[{index}] Error talking to broker: {exc}"

    if response.get("status") != "ok":
        return f"[{index}] Broker error: {json.dumps(response, ensure_ascii=False)}"

    results = response.get("results") or []
    if not results:
        return f"[{index}] Broker returned no results."

    first_result = results[0]
    outputs = first_result.get("outputs") or []
    if not outputs:
        return f"[{index}] Broker result did not include output images."

    primary = outputs[0]
    query = urlparse.urlencode(
        {
            "type": primary.get("type", "output"),
            "subfolder": primary.get("subfolder", ""),
            "filename": primary.get("filename", ""),
        }
    )
    download_url = f"{broker_url}/v1/file?{query}"

    try:
        download_file(download_url, output_path, timeout=max(60, timeout_seconds))
    except Exception as exc:
        return f"[{index}] Error downloading broker output: {exc}"

    print(f"[{index}] Image saved: {output_path.resolve()}")
    print(f"[{index}] SOURCE_FILENAME: {primary.get('filename')}")
    print(f"[{index}] BROKER_PROMPT_ID: {first_result.get('prompt_id')}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or edit images locally through the ComfyUI broker")
    parser.add_argument("--prompt", "-p", help="Image description (generate) or edit instruction (edit)")
    parser.add_argument("--prompts-json", help="JSON array of prompts, one per output image")
    parser.add_argument("--filename", "-f", required=True, help="Output filename inside the workspace")
    parser.add_argument("--image", "-i", default=None, help="Input image to edit (enables Kontext edit mode)")
    parser.add_argument("--image2", default=None, help="Optional second reference image for edit mode")
    parser.add_argument("--width", type=int, default=None, help="Output width in pixels (generate mode only)")
    parser.add_argument("--height", type=int, default=None, help="Output height in pixels (generate mode only)")
    parser.add_argument("--aspect", choices=sorted(ASPECT_PRESETS), default="1:1", help="Aspect preset, default 1:1 (generate mode only)")
    parser.add_argument("--steps", type=int, default=None, help="Sampling steps (default: 20; ideogram4 uses its preset steps unless overridden)")
    parser.add_argument("--guidance", type=float, default=None, help="Guidance value (default: 3.5 generate, 2.5 edit; ignored for ideogram4/z-image-turbo which use their own guidance)")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducible output")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of images to generate in one batch")
    parser.add_argument("--timeout-seconds", type=int, default=None, help="Broker timeout override")
    parser.add_argument("--broker-url", default=None, help="Broker base URL override")
    parser.add_argument("--llama-url", default=None, help="Local LLM base URL for the ideogram4 magic prompt (default: env OPENCLAW_LLAMA_URL or http://172.23.176.1:30000)")
    parser.add_argument("--upsample", action="store_true", help="flux3-klein[-base] t2i only: run the official BFL prompt upsampler (Qwen3.5-9B, TextGenerate) before encoding the prompt")
    parser.add_argument("--prompt-enhance", action="store_true", help="qwen-image-2.1 only: expand the prompt into a detailed 5-slot layout brief via the local LLM before generation (opt-in; skip it when your prompt already has full structure)")
    parser.add_argument("--model", choices=["flux1-dev", "flux2-klein-9b", "z-image-turbo", "ideogram4", "qwen-image-2.1", "moss-image", "flux3-klein", "flux3-klein-base"], default="qwen-image-2.1", help="Model to use (default: qwen-image-2.1 — best overall t2i + multi-ref editing + RGBA; use 'ideogram4' when exact text matters and it isn't safety-blocked, 'flux2-klein-9b' for musical-instrument/anatomy detail, 'z-image-turbo' for speed)")
    parser.add_argument("--preset", choices=sorted(IDEOGRAM4_PRESETS), default="default", help="Ideogram 4 sampling preset: quality (48 steps), default (20), turbo (12)")
    parser.add_argument("--dit", default=None, help="qwen-image-2.1 only: override the diffusion-model filename in ComfyUI models/diffusion_models (e.g. NoctQ_V4_int8_convrot.safetensors for the uncensored merge)")
    parser.add_argument("--qwen-cfg", type=float, default=1.0, help="qwen-image-2.1 edit mode: KSampler cfg (default 1.0 = official template; NoctQ uncensored recommends 3.0 with a negative prompt)")
    parser.add_argument("--qwen-negative", default="", help="qwen-image-2.1 edit mode: negative prompt (only active when --qwen-cfg > 1)")
    parser.add_argument("--moss-negative", default="", help="moss-image t2i only: negative prompt (active at cfg>1; community recipe: 'plastic skin, waxy skin')")
    args = parser.parse_args()

    edit_mode = args.image is not None
    broker_url = (
        args.broker_url
        or os.environ.get("OPENCLAW_COMFYUI_LOCAL_BROKER_URL")
        or os.environ.get("OPENCLAW_BROKER_URL")
        or DEFAULT_BROKER_URL
    ).rstrip("/")
    timeout_seconds = args.timeout_seconds or int(
        os.environ.get("OPENCLAW_COMFYUI_LOCAL_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    )
    guidance = args.guidance if args.guidance is not None else (DEFAULT_GUIDANCE_EDIT if edit_mode else DEFAULT_GUIDANCE_GENERATE)
    if args.guidance is None and args.model == "moss-image" and not edit_mode:
        guidance = 2.5
    if args.guidance is None and args.model == "flux3-klein" and not edit_mode:
        guidance = 1.0
    if args.guidance is None and args.model == "flux3-klein-base" and not edit_mode:
        guidance = 4.0
    if args.guidance is None and args.model == "flux3-klein-base" and edit_mode:
        guidance = 1.0
    if args.guidance is None and args.model == "flux3-klein" and edit_mode:
        guidance = 1.0

    try:
        prompts = parse_prompts(args.prompt, args.prompts_json)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    count = max(1, min(args.count, 20))
    if len(prompts) > 1:
        count = len(prompts)
    if len(prompts) == 1:
        prompts = prompts * count
    elif len(prompts) != count:
        print("When using --prompts-json, the number of prompts must match --count or omit --count.", file=sys.stderr)
        return 1

    width, height = resolve_size(args.width, args.height, args.aspect)

    # FLUX 3 prompt upsampler (BFL says don't skip it in their template). The
    # expansion runs INSIDE the graph (TextGenerate node, deterministic: top_k
    # 1), so unlike --prompt-enhance there is no llama-server round trip and
    # the upsampler model load happens once per broker batch.
    args._upsample_system = ""
    if args.upsample:
        if args.model not in ("flux3-klein", "flux3-klein-base") or edit_mode:
            print("--upsample is only supported for flux3-klein / flux3-klein-base t2i.", file=sys.stderr)
            return 1
        args._upsample_system = FLUX3_UPSAMPLE_FILE.read_text(encoding="utf-8")

    # Qwen-Image 2.1 optional prompt enhancement: expand each short brief into
    # a detailed 5-slot layout brief via the local LLM. Runs in main() — NOT
    # inside the worker threads — so all expansions finish before the first
    # broker POST; batched jobs then land inside the broker's batching window
    # (one GPU swap, not one per job). Fails open to the raw prompt if the
    # LLM is down or the output is unusable.
    if args.prompt_enhance and args.model == "qwen-image-2.1":
        mode = "edit" if edit_mode else "t2i"
        for pos, brief in enumerate(prompts):
            expanded = qwen21_prompt_expansion(brief, width, height, mode, args.llama_url)
            if expanded is not None and expanded != brief:
                print(f"[qwen21-enhance] Expanded prompt {pos + 1}/{len(prompts)} ({len(brief)} -> {len(expanded)} chars)")
                print(f"[qwen21-enhance] New prompt: {expanded[:400]}")
                prompts[pos] = expanded

    # --- Upload input image(s) if in edit mode ---
    uploaded_image: str | None = None
    uploaded_image2: str | None = None
    if edit_mode:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"Input image not found: {image_path}", file=sys.stderr)
            return 1
        print(f"Uploading input image: {image_path}")
        try:
            uploaded_image = upload_file(broker_url, image_path)
            print(f"Uploaded as: {uploaded_image}")
        except Exception as exc:
            print(f"Error uploading input image: {exc}", file=sys.stderr)
            return 1

        if args.image2:
            image2_path = Path(args.image2)
            if not image2_path.exists():
                print(f"Second input image not found: {image2_path}", file=sys.stderr)
                return 1
            print(f"Uploading second image: {image2_path}")
            try:
                uploaded_image2 = upload_file(broker_url, image2_path)
                print(f"Uploaded as: {uploaded_image2}")
            except Exception as exc:
                print(f"Error uploading second image: {exc}", file=sys.stderr)
                return 1

    base_seed = args.seed if args.seed is not None else int(time.time() * 1000) % 2147483647
    output_path = Path(args.filename)

    steps = args.steps
    if steps is None:
        if args.model == "ideogram4":
            steps = IDEOGRAM4_PRESETS[args.preset][0]
        elif args.model == "moss-image":
            steps = 30
        elif args.model == "flux3-klein":
            steps = 16
        elif args.model == "flux3-klein-base":
            steps = 50
        else:
            steps = 20

    if edit_mode and args.model == "ideogram4":
        print("ideogram4 only supports text-to-image generation (no --image editing)", file=sys.stderr)
        return 1

    if edit_mode and args.model == "moss-image":
        print("moss-image only supports text-to-image generation (no --image editing)", file=sys.stderr)
        return 1
    preset_note = f" | Preset: {args.preset}" if args.model == "ideogram4" else ""
    if edit_mode:
        extra = f" + image2={args.image2}" if args.image2 else ""
        engine = "Qwen-Image 2.1 multi-ref" if args.model == "qwen-image-2.1" else "Kontext/ReferenceLatent"
        print(f"Editing {count} image(s) via {engine}: {args.image}{extra}")
    else:
        print(f"Generating {count} image(s) locally via broker: {broker_url}")
    print(f"Steps: {steps} | Guidance: {guidance}{preset_note} | Base seed: {base_seed}")

    if count == 1:
        err = generate_one(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            prompt=prompts[0],
            output_path=output_path,
            width=width,
            height=height,
            steps=steps,
            guidance=guidance,
            seed=base_seed,
            index=1,
            input_image=uploaded_image,
            input_image2=uploaded_image2,
            model=args.model,
            preset=args.preset,
            llama_url=args.llama_url,
            dit_override=args.dit,
            qwen_cfg=args.qwen_cfg,
            qwen_negative=args.qwen_negative,
            negative=args.moss_negative,
            upsample_system=args._upsample_system,
        )
        if err:
            print(err, file=sys.stderr)
            return 1
        return 0

    stem = output_path.stem
    suffix = output_path.suffix or ".png"
    parent = output_path.parent
    errors: list[str] = []
    errors_lock = threading.Lock()

    def worker(index: int) -> None:
        err = generate_one(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            prompt=prompts[index],
            output_path=parent / f"{stem}-{index + 1}{suffix}",
            width=width,
            height=height,
            steps=steps,
            guidance=guidance,
            seed=base_seed + index,
            index=index + 1,
            input_image=uploaded_image,
            input_image2=uploaded_image2,
            model=args.model,
            preset=args.preset,
            llama_url=args.llama_url,
            dit_override=args.dit,
            qwen_cfg=args.qwen_cfg,
            qwen_negative=args.qwen_negative,
            negative=args.moss_negative,
            upsample_system=args._upsample_system,
        )
        if err:
            with errors_lock:
                errors.append(err)

    threads: list[threading.Thread] = []
    for index in range(count):
        thread = threading.Thread(target=worker, args=(index,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print(f"All {count} images generated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())