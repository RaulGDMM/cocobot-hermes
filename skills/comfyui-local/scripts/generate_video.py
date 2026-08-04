#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate videos locally through the ComfyUI broker (LTX 2.3 or MiniMax H3)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


DEFAULT_BROKER_URL = "http://host.docker.internal:8791"
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_FPS = 24
DEFAULT_STEPS = 20

NEGATIVE_PROMPT = (
    "blurry, low quality, still frame, frames, watermark, "
    "overlay, titles, has blurbox, has subtitles"
)

MODEL_CHECKPOINT = "ltx-2.3-22b-dev.safetensors"
MODEL_TEXT_ENCODER = "gemma_3_12B_it_fp4_mixed.safetensors"
MODEL_UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
MODEL_LORA = "ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
MODEL_AUDIO_VAE = "ltx-2.3-22b-dev_audio_vae.safetensors"
MODEL_MELBAND = "MelBandRoformer_fp32.safetensors"
MODEL_IDLORA = "ltx-2.3-id-lora-talkvid-3k.safetensors"

H3_MODEL_FL2VA = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
H3_MODEL_REF2VA = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
H3_TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
H3_VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
H3_AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"

# ID-LoRA pipeline (matches the official "video_ltx2_3_id_lora" template):
# uses the FP8 checkpoint + the v1.0 distilled LoRA at 0.5 strength stacked
# with the ID-LoRA at 1.0 strength, two-stage low/high-res with latent
# upsampling, CFGGuider (cfg=1.0), euler_ancestral_cfg_pp / euler_cfg_pp.
MODEL_IDLORA_CHECKPOINT = "ltx-2.3-22b-dev.safetensors"
MODEL_IDLORA_DISTILLED = "ltx-2.3-22b-distilled-lora-384.safetensors"
IDLORA_NEGATIVE_PROMPT = (
    "pc game, console game, video game, cartoon, childish, ugly"
)
IDLORA_DEFAULT_FPS = 25

# Video presets: "resolution-aspect" -> (width, height)
# LTX 2.3 silently snaps to the closest valid dimensions.
VIDEO_PRESETS = {
    "480p-16:9": (848, 480),
    "480p-4:3": (640, 480),
    "480p-1:1": (480, 480),
    "480p-9:16": (480, 848),
    "480p-3:4": (480, 640),
    "720p-16:9": (1280, 720),
    "720p-4:3": (960, 720),
    "720p-1:1": (720, 720),
    "720p-9:16": (720, 1280),
    "720p-3:4": (720, 960),
    "1080p-16:9": (1920, 1088),
    "1080p-4:3": (1440, 1088),
    "1080p-1:1": (1088, 1088),
    "1080p-9:16": (1088, 1920),
    "1080p-3:4": (1088, 1440),
}

# MiniMax H3 requires both dimensions to be multiples of 32. The 720p preset
# maps to H3's native 768px-short-edge canvas; 1080p is the optional ~2MP mode.
H3_VIDEO_PRESETS = {
    "480p-16:9": (864, 480),
    "480p-4:3": (640, 480),
    "480p-1:1": (480, 480),
    "480p-9:16": (480, 864),
    "480p-3:4": (480, 640),
    "720p-16:9": (1344, 768),
    "720p-4:3": (1024, 768),
    "720p-1:1": (768, 768),
    "720p-9:16": (768, 1344),
    "720p-3:4": (768, 1024),
    "1080p-16:9": (1920, 1088),
    "1080p-4:3": (1632, 1216),
    "1080p-1:1": (1408, 1408),
    "1080p-9:16": (1088, 1920),
    "1080p-3:4": (1216, 1632),
}


def duration_to_frames(seconds: float, fps: int = DEFAULT_FPS) -> int:
    """Convert seconds to LTX frame count (must be 8k+1)."""
    raw = seconds * fps
    return round(raw / 8) * 8 + 1


def h3_duration_to_frames(seconds: float) -> int:
    """Convert seconds to MiniMax H3's 17k+5 frame grid at fixed 24 fps."""
    raw = max(5, round(seconds * 24))
    return raw + (5 - raw % 17) % 17


# ---------------------------------------------------------------------------
# Text-to-Video workflow
# ---------------------------------------------------------------------------

def build_t2v_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    width: int,
    height: int,
    frames: int,
    steps: int,
    fps: int,
    seed: int,
    input_audio: str | None = None,
    negative_prompt: str = NEGATIVE_PROMPT,
) -> dict[str, object]:
    """Build an LTX 2.3 text-to-video workflow (API format)."""
    return {
        # --- model loaders ---
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": MODEL_CHECKPOINT},
        },
        "2": {
            "class_type": "LTXAVTextEncoderLoader",
            "inputs": {
                "text_encoder": MODEL_TEXT_ENCODER,
                "ckpt_name": MODEL_CHECKPOINT,
                "device": "default",
            },
        },
        # --- prompt enhancement ---
        "3": {
            "class_type": "TextGenerateLTX2Prompt",
            "inputs": {
                "clip": ["2", 0],
                "prompt": prompt,
                "max_length": 256,
                "sampling_mode": "on",
                "sampling_mode.temperature": 0.7,
                "sampling_mode.top_k": 64,
                "sampling_mode.top_p": 0.95,
                "sampling_mode.min_p": 0.05,
                "sampling_mode.repetition_penalty": 1.05,
                "sampling_mode.seed": 0,
            },
        },
        # --- conditioning ---
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": ["3", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative_prompt},
        },
        "6": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "frame_rate": fps,
            },
        },
        # --- empty image -> half-res for first pass ---
        "7": {
            "class_type": "EmptyImage",
            "inputs": {"width": width, "height": height, "batch_size": 1, "color": 0},
        },
        "8": {
            "class_type": "ImageScaleBy",
            "inputs": {"image": ["7", 0], "upscale_method": "lanczos", "scale_by": 0.5},
        },
        "9": {
            "class_type": "GetImageSize",
            "inputs": {"image": ["8", 0]},
        },
        # --- video latent ---
        "10": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": ["9", 0],
                "height": ["9", 1],
                "length": frames,
                "batch_size": 1,
            },
        },
        # --- audio latent ---
        "11": {
            "class_type": "LTXVAudioVAELoader",
            "inputs": {"ckpt_name": MODEL_CHECKPOINT},
        },
        **({
            "35": {
                "class_type": "LoadAudio",
                "inputs": {"audio": input_audio},
            },
            "12": {
                "class_type": "LTXVAudioVAEEncode",
                "inputs": {
                    "audio": ["35", 0],
                    "audio_vae": ["11", 0],
                },
            },
        } if input_audio else {
            "12": {
                "class_type": "LTXVEmptyLatentAudio",
                "inputs": {
                    "audio_vae": ["11", 0],
                    "frames_number": frames,
                    "frame_rate": fps,
                    "batch_size": 1,
                },
            },
        }),
        # --- combine AV latent ---
        "13": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["10", 0],
                "audio_latent": ["12", 0],
            },
        },
        # --- LoRA (for second pass) ---
        "14": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": MODEL_LORA,
                "strength_model": 1.0,
            },
        },
        # --- FIRST PASS scheduler + sampler ---
        "15": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": steps,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": ["13", 0],
            },
        },
        # --- guider: MultimodalGuider when external audio, CFGGuider otherwise ---
        **({  # external audio → cross-modal sync
            "50": {
                "class_type": "GuiderParameters",
                "inputs": {
                    "modality": "AUDIO",
                    "cfg": 7.0,
                    "stg": 1.0,
                    "perturb_attn": True,
                    "rescale": 0.7,
                    "modality_scale": 3.0,
                    "skip_step": 0,
                    "cross_attn": True,
                },
            },
            "51": {
                "class_type": "GuiderParameters",
                "inputs": {
                    "parameters": ["50", 0],
                    "modality": "VIDEO",
                    "cfg": 3.0,
                    "stg": 1.0,
                    "perturb_attn": True,
                    "rescale": 0.9,
                    "modality_scale": 3.0,
                    "skip_step": 0,
                    "cross_attn": True,
                },
            },
            "16": {
                "class_type": "MultimodalGuider",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["6", 0],
                    "negative": ["6", 1],
                    "parameters": ["51", 0],
                    "skip_blocks": "",
                },
            },
        } if input_audio else {
            "16": {
                "class_type": "CFGGuider",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["6", 0],
                    "negative": ["6", 1],
                    "cfg": 4.0,
                },
            },
        }),
        "17": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
        },
        "18": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_ancestral"},
        },
        "19": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["17", 0],
                "guider": ["16", 0],
                "sampler": ["18", 0],
                "sigmas": ["15", 0],
                "latent_image": ["13", 0],
            },
        },
        # --- separate AV after first pass ---
        "20": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["19", 0]},
        },
        # --- crop guides + upscale ---
        "21": {
            "class_type": "LTXVCropGuides",
            "inputs": {
                "positive": ["6", 0],
                "negative": ["6", 1],
                "latent": ["20", 0],
            },
        },
        "22": {
            "class_type": "LatentUpscaleModelLoader",
            "inputs": {"model_name": MODEL_UPSCALER},
        },
        "23": {
            "class_type": "LTXVLatentUpsampler",
            "inputs": {
                "samples": ["21", 2],
                "upscale_model": ["22", 0],
                "vae": ["1", 2],
            },
        },
        # --- recombine for second pass ---
        "24": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["23", 0],
                "audio_latent": ["20", 1],
            },
        },
        # --- SECOND PASS sigmas + sampler ---
        "25": {
            "class_type": "ManualSigmas",
            "inputs": {"sigmas": "0.909375, 0.725, 0.421875, 0.0"},
        },
        "26": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["14", 0],
                "positive": ["21", 0],
                "negative": ["21", 1],
                "cfg": 1.0,
            },
        },
        "27": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
        },
        "28": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_ancestral"},
        },
        "29": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["27", 0],
                "guider": ["26", 0],
                "sampler": ["28", 0],
                "sigmas": ["25", 0],
                "latent_image": ["24", 0],
            },
        },
        # --- final decode ---
        "30": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["29", 0]},
        },
        "31": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["30", 0],
                "vae": ["1", 2],
                "tile_size": 512,
                "overlap": 64,
                "temporal_size": 4096,
                "temporal_overlap": 8,
            },
        },
        "32": {
            "class_type": "LTXVAudioVAEDecode",
            "inputs": {
                "samples": ["30", 1],
                "audio_vae": ["11", 0],
            },
        },
        # --- create + save video ---
        "33": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["31", 0],
                "audio": ["32", 0],
                "fps": float(fps),
            },
        },
        "34": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["33", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }


# ---------------------------------------------------------------------------
# Image-to-Video workflow
# ---------------------------------------------------------------------------

def build_i2v_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    input_image: str,
    input_end_image: str | None = None,
    width: int,
    height: int,
    frames: int,
    steps: int,
    fps: int,
    seed: int,
    input_audio: str | None = None,
    negative_prompt: str = NEGATIVE_PROMPT,
) -> dict[str, object]:
    """Build an LTX 2.3 image-to-video workflow (API format)."""
    return {
        # --- model loaders ---
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": MODEL_CHECKPOINT},
        },
        "2": {
            "class_type": "LTXAVTextEncoderLoader",
            "inputs": {
                "text_encoder": MODEL_TEXT_ENCODER,
                "ckpt_name": MODEL_CHECKPOINT,
                "device": "default",
            },
        },
        # --- load + resize input image ---
        "3": {
            "class_type": "LoadImage",
            "inputs": {"image": input_image},
        },
        "4": {
            "class_type": "ResizeImageMaskNode",
            "inputs": {
                "input": ["3", 0],
                "scale_method": "lanczos",
                "resize_type": "scale dimensions",
                "resize_type.width": width,
                "resize_type.height": height,
                "resize_type.crop": "center",
            },
        },
        "5": {
            "class_type": "GetImageSize",
            "inputs": {"image": ["4", 0]},
        },
        # --- resize for preprocessing + preprocess ---
        "6": {
            "class_type": "ResizeImagesByLongerEdge",
            "inputs": {"images": ["4", 0], "longer_edge": 1536},
        },
        "7": {
            "class_type": "LTXVPreprocess",
            "inputs": {"image": ["6", 0], "img_compression": 33},
        },
        # --- end image load + preprocess (when provided) ---
        **(
            {
                "60": {
                    "class_type": "LoadImage",
                    "inputs": {"image": input_end_image},
                },
                "61": {
                    "class_type": "ResizeImageMaskNode",
                    "inputs": {
                        "input": ["60", 0],
                        "scale_method": "lanczos",
                        "resize_type": "scale dimensions",
                        "resize_type.width": width,
                        "resize_type.height": height,
                        "resize_type.crop": "center",
                    },
                },
                "62": {
                    "class_type": "ResizeImagesByLongerEdge",
                    "inputs": {"images": ["61", 0], "longer_edge": 1536},
                },
                "63": {
                    "class_type": "LTXVPreprocess",
                    "inputs": {"image": ["62", 0], "img_compression": 33},
                },
            } if input_end_image else {}
        ),
        # --- prompt enhancement (with image) ---
        "8": {
            "class_type": "TextGenerateLTX2Prompt",
            "inputs": {
                "clip": ["2", 0],
                "prompt": prompt,
                "image": ["4", 0],
                "max_length": 256,
                "sampling_mode": "on",
                "sampling_mode.temperature": 0.7,
                "sampling_mode.top_k": 64,
                "sampling_mode.top_p": 0.95,
                "sampling_mode.min_p": 0.05,
                "sampling_mode.repetition_penalty": 1.05,
                "sampling_mode.seed": 0,
            },
        },
        # --- conditioning ---
        "9": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": ["8", 0]},
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative_prompt},
        },
        "11": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["9", 0],
                "negative": ["10", 0],
                "frame_rate": fps,
            },
        },
        # --- half-res latent from target dimensions ---
        "12": {
            "class_type": "EmptyImage",
            "inputs": {
                "width": ["5", 0],
                "height": ["5", 1],
                "batch_size": 1,
                "color": 0,
            },
        },
        "13": {
            "class_type": "ImageScaleBy",
            "inputs": {"image": ["12", 0], "upscale_method": "lanczos", "scale_by": 0.5},
        },
        "14": {
            "class_type": "GetImageSize",
            "inputs": {"image": ["13", 0]},
        },
        "15": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": ["14", 0],
                "height": ["14", 1],
                "length": frames,
                "batch_size": 1,
            },
        },
        # --- first pass image conditioning ---
        **(
            {   # start+end frame guides via LTXVAddGuide chain
                "64": {
                    "class_type": "LTXVAddGuide",
                    "inputs": {
                        "positive": ["11", 0],
                        "negative": ["11", 1],
                        "vae": ["1", 2],
                        "latent": ["15", 0],
                        "image": ["7", 0],
                        "frame_idx": 0,
                        "strength": 1.0,
                    },
                },
                "65": {
                    "class_type": "LTXVAddGuide",
                    "inputs": {
                        "positive": ["64", 0],
                        "negative": ["64", 1],
                        "vae": ["1", 2],
                        "latent": ["64", 2],
                        "image": ["63", 0],
                        "frame_idx": -1,
                        "strength": 1.0,
                    },
                },
            } if input_end_image else {
                "16": {
                    "class_type": "LTXVImgToVideoInplace",
                    "inputs": {
                        "vae": ["1", 2],
                        "image": ["7", 0],
                        "latent": ["15", 0],
                        "strength": 1,
                        "bypass": False,
                    },
                },
            }
        ),
        # --- audio latent ---
        "17": {
            "class_type": "LTXVAudioVAELoader",
            "inputs": {"ckpt_name": MODEL_CHECKPOINT},
        },
        **({
            "42": {
                "class_type": "LoadAudio",
                "inputs": {"audio": input_audio},
            },
            "18": {
                "class_type": "LTXVAudioVAEEncode",
                "inputs": {
                    "audio": ["42", 0],
                    "audio_vae": ["17", 0],
                },
            },
        } if input_audio else {
            "18": {
                "class_type": "LTXVEmptyLatentAudio",
                "inputs": {
                    "audio_vae": ["17", 0],
                    "frames_number": frames,
                    "frame_rate": fps,
                    "batch_size": 1,
                },
            },
        }),
        # --- combine AV latent ---
        "19": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["65", 2] if input_end_image else ["16", 0],
                "audio_latent": ["18", 0],
            },
        },
        # --- FIRST PASS ---
        "20": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": steps,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": ["19", 0],
            },
        },
        # --- guider: MultimodalGuider when external audio, CFGGuider otherwise ---
        **({  # external audio → cross-modal sync
            "50": {
                "class_type": "GuiderParameters",
                "inputs": {
                    "modality": "AUDIO",
                    "cfg": 7.0,
                    "stg": 1.0,
                    "perturb_attn": True,
                    "rescale": 0.7,
                    "modality_scale": 3.0,
                    "skip_step": 0,
                    "cross_attn": True,
                },
            },
            "51": {
                "class_type": "GuiderParameters",
                "inputs": {
                    "parameters": ["50", 0],
                    "modality": "VIDEO",
                    "cfg": 3.0,
                    "stg": 1.0,
                    "perturb_attn": True,
                    "rescale": 0.9,
                    "modality_scale": 3.0,
                    "skip_step": 0,
                    "cross_attn": True,
                },
            },
            "21": {
                "class_type": "MultimodalGuider",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["65", 0] if input_end_image else ["11", 0],
                    "negative": ["65", 1] if input_end_image else ["11", 1],
                    "parameters": ["51", 0],
                    "skip_blocks": "",
                },
            },
        } if input_audio else {
            "21": {
                "class_type": "CFGGuider",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["65", 0] if input_end_image else ["11", 0],
                    "negative": ["65", 1] if input_end_image else ["11", 1],
                    "cfg": 4.0,
                },
            },
        }),
        "22": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
        },
        "23": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        "24": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["22", 0],
                "guider": ["21", 0],
                "sampler": ["23", 0],
                "sigmas": ["20", 0],
                "latent_image": ["19", 0],
            },
        },
        # --- separate AV after first pass ---
        "25": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["24", 0]},
        },
        # --- crop guides + upscale ---
        "26": {
            "class_type": "LTXVCropGuides",
            "inputs": {
                "positive": ["65", 0] if input_end_image else ["11", 0],
                "negative": ["65", 1] if input_end_image else ["11", 1],
                "latent": ["25", 0],
            },
        },
        "27": {
            "class_type": "LatentUpscaleModelLoader",
            "inputs": {"model_name": MODEL_UPSCALER},
        },
        "28": {
            "class_type": "LTXVLatentUpsampler",
            "inputs": {
                "samples": ["26", 2],
                "upscale_model": ["27", 0],
                "vae": ["1", 2],
            },
        },
        # --- re-inject frame guides after upscale ---
        **(
            {   # re-add start+end guides to upscaled latent
                "66": {
                    "class_type": "LTXVAddGuide",
                    "inputs": {
                        "positive": ["26", 0],
                        "negative": ["26", 1],
                        "vae": ["1", 2],
                        "latent": ["28", 0],
                        "image": ["7", 0],
                        "frame_idx": 0,
                        "strength": 1.0,
                    },
                },
                "67": {
                    "class_type": "LTXVAddGuide",
                    "inputs": {
                        "positive": ["66", 0],
                        "negative": ["66", 1],
                        "vae": ["1", 2],
                        "latent": ["66", 2],
                        "image": ["63", 0],
                        "frame_idx": -1,
                        "strength": 1.0,
                    },
                },
            } if input_end_image else {
                "29": {
                    "class_type": "LTXVImgToVideoInplace",
                    "inputs": {
                        "vae": ["1", 2],
                        "image": ["7", 0],
                        "latent": ["28", 0],
                        "strength": 1,
                        "bypass": False,
                    },
                },
            }
        ),
        # --- recombine for second pass ---
        "30": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["67", 2] if input_end_image else ["29", 0],
                "audio_latent": ["25", 1],
            },
        },
        # --- SECOND PASS ---
        "31": {
            "class_type": "ManualSigmas",
            "inputs": {"sigmas": "0.909375, 0.725, 0.421875, 0.0"},
        },
        "32": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": MODEL_LORA,
                "strength_model": 1.0,
            },
        },
        "33": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["32", 0],
                "positive": ["67", 0] if input_end_image else ["26", 0],
                "negative": ["67", 1] if input_end_image else ["26", 1],
                "cfg": 1.0,
            },
        },
        "34": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
        },
        "35": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "gradient_estimation"},
        },
        "36": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["34", 0],
                "guider": ["33", 0],
                "sampler": ["35", 0],
                "sigmas": ["31", 0],
                "latent_image": ["30", 0],
            },
        },
        # --- final decode ---
        "37": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["36", 0]},
        },
        "38": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["37", 0],
                "vae": ["1", 2],
            },
        },
        "39": {
            "class_type": "LTXVAudioVAEDecode",
            "inputs": {
                "samples": ["37", 1],
                "audio_vae": ["17", 0],
            },
        },
        # --- create + save video ---
        "40": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["38", 0],
                "audio": ["39", 0],
                "fps": float(fps),
            },
        },
        "41": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["40", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }



# ---------------------------------------------------------------------------
# Lip-sync workflow (image + audio with MelBand vocal separation)
# ---------------------------------------------------------------------------

def build_lipsync_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    input_image: str,
    input_audio: str,
    width: int,
    height: int,
    frames: int,
    steps: int,
    fps: int,
    seed: int,
    negative_prompt: str = NEGATIVE_PROMPT,
) -> dict[str, object]:
    """Build an LTX 2.3 lip-sync workflow.

    Uses MelBand RoFormer to isolate vocals from the audio, then conditions
    the video generation on the clean vocal track via a dedicated Audio VAE.
    This produces much better lip synchronisation than the regular i2v+audio
    pipeline.
    """
    return {
        # --- model loaders ---
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": MODEL_CHECKPOINT},
        },
        "2": {
            "class_type": "LTXAVTextEncoderLoader",
            "inputs": {
                "text_encoder": MODEL_TEXT_ENCODER,
                "ckpt_name": MODEL_CHECKPOINT,
                "device": "default",
            },
        },
        # --- load + resize input image ---
        "3": {
            "class_type": "LoadImage",
            "inputs": {"image": input_image},
        },
        "4": {
            "class_type": "ResizeImageMaskNode",
            "inputs": {
                "input": ["3", 0],
                "scale_method": "lanczos",
                "resize_type": "scale dimensions",
                "resize_type.width": width,
                "resize_type.height": height,
                "resize_type.crop": "center",
            },
        },
        "5": {
            "class_type": "GetImageSize",
            "inputs": {"image": ["4", 0]},
        },
        # --- preprocessed image for prompt enhancement ---
        "6": {
            "class_type": "ResizeImagesByLongerEdge",
            "inputs": {"images": ["4", 0], "longer_edge": 1536},
        },
        "7": {
            "class_type": "LTXVPreprocess",
            "inputs": {"image": ["6", 0], "img_compression": 33},
        },
        # --- prompt enhancement (with image) ---
        "8": {
            "class_type": "TextGenerateLTX2Prompt",
            "inputs": {
                "clip": ["2", 0],
                "prompt": prompt,
                "image": ["4", 0],
                "max_length": 256,
                "sampling_mode": "on",
                "sampling_mode.temperature": 0.7,
                "sampling_mode.top_k": 64,
                "sampling_mode.top_p": 0.95,
                "sampling_mode.min_p": 0.05,
                "sampling_mode.repetition_penalty": 1.05,
                "sampling_mode.seed": 0,
            },
        },
        # --- conditioning ---
        "9": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": ["8", 0]},
        },
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative_prompt},
        },
        "11": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["9", 0],
                "negative": ["10", 0],
                "frame_rate": fps,
            },
        },
        # --- half-res latent ---
        "12": {
            "class_type": "EmptyImage",
            "inputs": {
                "width": ["5", 0],
                "height": ["5", 1],
                "batch_size": 1,
                "color": 0,
            },
        },
        "13": {
            "class_type": "ImageScaleBy",
            "inputs": {"image": ["12", 0], "upscale_method": "lanczos", "scale_by": 0.5},
        },
        "14": {
            "class_type": "GetImageSize",
            "inputs": {"image": ["13", 0]},
        },
        "15": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": ["14", 0],
                "height": ["14", 1],
                "length": frames,
                "batch_size": 1,
            },
        },
        # --- first-frame conditioning ---
        "16": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["1", 2],
                "image": ["7", 0],
                "latent": ["15", 0],
                "strength": 1,
                "bypass": False,
            },
        },
        # --- audio: load + vocal separation + encode ---
        "40": {
            "class_type": "LoadAudio",
            "inputs": {"audio": input_audio},
        },
        "41": {
            "class_type": "MelBandRoFormerModelLoader",
            "inputs": {"model_name": MODEL_MELBAND},
        },
        "42": {
            "class_type": "MelBandRoFormerSampler",
            "inputs": {
                "model": ["41", 0],
                "audio": ["40", 0],
            },
        },
        "43": {
            "class_type": "LTXVAudioVAELoader",
            "inputs": {"ckpt_name": MODEL_AUDIO_VAE},
        },
        "44": {
            "class_type": "LTXVAudioVAEEncode",
            "inputs": {
                "audio": ["42", 0],  # vocals output
                "audio_vae": ["43", 0],
            },
        },
        # --- combine AV latent ---
        "19": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["16", 0],
                "audio_latent": ["44", 0],
            },
        },
        # --- FIRST PASS ---
        "20": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": steps,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": ["19", 0],
            },
        },
        # --- MultimodalGuider (always, for cross-modal lip sync) ---
        "50": {
            "class_type": "GuiderParameters",
            "inputs": {
                "modality": "AUDIO",
                "cfg": 7.0,
                "stg": 1.0,
                "perturb_attn": True,
                "rescale": 0.7,
                "modality_scale": 3.0,
                "skip_step": 0,
                "cross_attn": True,
            },
        },
        "51": {
            "class_type": "GuiderParameters",
            "inputs": {
                "parameters": ["50", 0],
                "modality": "VIDEO",
                "cfg": 3.0,
                "stg": 1.0,
                "perturb_attn": True,
                "rescale": 0.9,
                "modality_scale": 3.0,
                "skip_step": 0,
                "cross_attn": True,
            },
        },
        "21": {
            "class_type": "MultimodalGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["11", 0],
                "negative": ["11", 1],
                "parameters": ["51", 0],
                "skip_blocks": "",
            },
        },
        "22": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
        },
        "23": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        "24": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["22", 0],
                "guider": ["21", 0],
                "sampler": ["23", 0],
                "sigmas": ["20", 0],
                "latent_image": ["19", 0],
            },
        },
        # --- separate AV after first pass ---
        "25": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["24", 0]},
        },
        # --- crop guides + upscale ---
        "26": {
            "class_type": "LTXVCropGuides",
            "inputs": {
                "positive": ["11", 0],
                "negative": ["11", 1],
                "latent": ["25", 0],
            },
        },
        "27": {
            "class_type": "LatentUpscaleModelLoader",
            "inputs": {"model_name": MODEL_UPSCALER},
        },
        "28": {
            "class_type": "LTXVLatentUpsampler",
            "inputs": {
                "samples": ["26", 2],
                "upscale_model": ["27", 0],
                "vae": ["1", 2],
            },
        },
        # --- re-inject first frame after upscale ---
        "29": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["1", 2],
                "image": ["7", 0],
                "latent": ["28", 0],
                "strength": 1,
                "bypass": False,
            },
        },
        # --- recombine for second pass ---
        "30": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["29", 0],
                "audio_latent": ["25", 1],
            },
        },
        # --- SECOND PASS ---
        "31": {
            "class_type": "ManualSigmas",
            "inputs": {"sigmas": "0.909375, 0.725, 0.421875, 0.0"},
        },
        "32": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": MODEL_LORA,
                "strength_model": 1.0,
            },
        },
        "33": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["32", 0],
                "positive": ["26", 0],
                "negative": ["26", 1],
                "cfg": 1.0,
            },
        },
        "34": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
        },
        "35": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "gradient_estimation"},
        },
        "36": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["34", 0],
                "guider": ["33", 0],
                "sampler": ["35", 0],
                "sigmas": ["31", 0],
                "latent_image": ["30", 0],
            },
        },
        # --- final decode ---
        "37": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["36", 0]},
        },
        "38": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["37", 0],
                "vae": ["1", 2],
            },
        },
        "39": {
            "class_type": "LTXVAudioVAEDecode",
            "inputs": {
                "samples": ["37", 1],
                "audio_vae": ["43", 0],
            },
        },
        # --- create + save video ---
        "45": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["38", 0],
                "audio": ["39", 0],
                "fps": float(fps),
            },
        },
        "46": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["45", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }


# ---------------------------------------------------------------------------
# ID-LoRA workflow (voice identity from ~5s reference audio)
# ---------------------------------------------------------------------------

def build_idlora_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    input_image: str,
    reference_audio: str,
    width: int,
    height: int,
    frames: int,
    steps: int,  # accepted for CLI compatibility, but the pipeline uses fixed sigma schedules
    fps: int,
    seed: int,
    identity_guidance_scale: float = 3.0,
    negative_prompt: str = IDLORA_NEGATIVE_PROMPT,
) -> dict[str, object]:
    """Build an LTX 2.3 ID-LoRA workflow that mirrors the official
    "video_ltx2_3_id_lora" ComfyUI template.

    Pipeline (two stages with latent upsampling):
      1. Low-res:  euler_ancestral_cfg_pp + 8-step ManualSigmas, cfg=1.0
                   (distilled LoRA + ID-LoRA stacked on the FP8 model)
      2. Upsample: LTXVLatentUpsampler (×2 spatial)
      3. High-res: euler_cfg_pp + 3-step ManualSigmas, cfg=1.0,
                   image re-conditioned via LTXVImgToVideoInplace

    `steps` is accepted for CLI compatibility but ignored — the distilled
    pipeline is calibrated for the fixed sigma schedules below.
    """
    del steps  # parameter kept for API compatibility

    # Low-res latent dimensions (template uses width/2, height/2).
    low_w = max(64, (width // 2) // 32 * 32)
    low_h = max(64, (height // 2) // 32 * 32)

    # Sigma schedules taken verbatim from the template.
    SIGMAS_LOW = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
    SIGMAS_HIGH = "0.85, 0.7250, 0.4219, 0.0"
    HIGH_RES_NOISE_SEED = 42  # template hardcodes a fixed seed for the refiner

    return {
        # ============================================================
        # Loaders
        # ============================================================
        "ckpt": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": MODEL_IDLORA_CHECKPOINT},
        },
        "text_enc": {
            "class_type": "LTXAVTextEncoderLoader",
            "inputs": {
                "text_encoder": MODEL_TEXT_ENCODER,
                "ckpt_name": MODEL_IDLORA_CHECKPOINT,
                "device": "default",
            },
        },
        "audio_vae": {
            "class_type": "LTXVAudioVAELoader",
            "inputs": {"ckpt_name": MODEL_IDLORA_CHECKPOINT},
        },
        "upscaler": {
            "class_type": "LatentUpscaleModelLoader",
            "inputs": {"model_name": MODEL_UPSCALER},
        },
        # Distilled LoRA at 0.5 stacked with ID-LoRA at 1.0 (template defaults).
        "lora_distilled": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["ckpt", 0],
                "lora_name": MODEL_IDLORA_DISTILLED,
                "strength_model": 0.5,
            },
        },
        "lora_id": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["lora_distilled", 0],
                "lora_name": MODEL_IDLORA,
                "strength_model": 1.0,
            },
        },

        # ============================================================
        # Inputs (image + reference audio)
        # ============================================================
        "load_image": {
            "class_type": "LoadImage",
            "inputs": {"image": input_image},
        },
        "load_audio": {
            "class_type": "LoadAudio",
            "inputs": {"audio": reference_audio},
        },
        # Resize to the target frame size, then to the longer-edge canvas (1536),
        # then run the LTXV preprocess (light-compression artifact prior).
        "resize_to_frame": {
            "class_type": "ResizeImageMaskNode",
            "inputs": {
                "input": ["load_image", 0],
                "scale_method": "lanczos",
                "resize_type": "scale dimensions",
                "resize_type.width": width,
                "resize_type.height": height,
                "resize_type.crop": "center",
            },
        },
        "resize_longer": {
            "class_type": "ResizeImagesByLongerEdge",
            "inputs": {
                "images": ["resize_to_frame", 0],
                "longer_edge": 1536,
            },
        },
        "preprocess": {
            "class_type": "LTXVPreprocess",
            "inputs": {
                "image": ["resize_longer", 0],
                "img_compression": 18,
            },
        },

        # ============================================================
        # Conditioning (positive/negative + reference-audio identity)
        # ============================================================
        "pos_clip": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["text_enc", 0], "text": prompt},
        },
        "neg_clip": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["text_enc", 0], "text": negative_prompt},
        },
        # LTXVReferenceAudio patches the model with identity guidance and
        # injects the reference-audio embedding into both conditionings.
        "ref_audio": {
            "class_type": "LTXVReferenceAudio",
            "inputs": {
                "model": ["lora_id", 0],
                "positive": ["pos_clip", 0],
                "negative": ["neg_clip", 0],
                "reference_audio": ["load_audio", 0],
                "audio_vae": ["audio_vae", 0],
                "identity_guidance_scale": identity_guidance_scale,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        },
        "ltxv_cond": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["ref_audio", 1],
                "negative": ["ref_audio", 2],
                "frame_rate": fps,
            },
        },

        # ============================================================
        # Stage 1: Low-resolution generation
        # ============================================================
        "empty_video_low": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": low_w,
                "height": low_h,
                "length": frames,
                "batch_size": 1,
            },
        },
        "img_low": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["ckpt", 2],
                "image": ["preprocess", 0],
                "latent": ["empty_video_low", 0],
                "strength": 0.7,
                "bypass": False,
            },
        },
        "empty_audio": {
            "class_type": "LTXVEmptyLatentAudio",
            "inputs": {
                "audio_vae": ["audio_vae", 0],
                "frames_number": frames,
                "frame_rate": fps,
                "batch_size": 1,
            },
        },
        "concat_av_low": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["img_low", 0],
                "audio_latent": ["empty_audio", 0],
            },
        },
        "sigmas_low": {
            "class_type": "ManualSigmas",
            "inputs": {"sigmas": SIGMAS_LOW},
        },
        "sampler_low": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_ancestral_cfg_pp"},
        },
        "guider_low": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["lora_id", 0],
                "positive": ["ltxv_cond", 0],
                "negative": ["ltxv_cond", 1],
                "cfg": 1.0,
            },
        },
        "noise_low": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed, "control_after_generate": "randomize"},
        },
        "ksampler_low": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["noise_low", 0],
                "guider": ["guider_low", 0],
                "sampler": ["sampler_low", 0],
                "sigmas": ["sigmas_low", 0],
                "latent_image": ["concat_av_low", 0],
            },
        },
        "split_av_low": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["ksampler_low", 0]},
        },

        # ============================================================
        # Stage 2: Latent upsample + high-res refinement
        # ============================================================
        # CropGuides primarily forwards conditionings; with no keyframes set
        # by LTXVImgToVideoInplace it acts as a passthrough.
        "crop_guides": {
            "class_type": "LTXVCropGuides",
            "inputs": {
                "positive": ["ltxv_cond", 0],
                "negative": ["ltxv_cond", 1],
                "latent": ["split_av_low", 0],
            },
        },
        "upsample": {
            "class_type": "LTXVLatentUpsampler",
            "inputs": {
                "samples": ["split_av_low", 0],
                "upscale_model": ["upscaler", 0],
                "vae": ["ckpt", 2],
            },
        },
        "img_high": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["ckpt", 2],
                "image": ["preprocess", 0],
                "latent": ["upsample", 0],
                "strength": 1.0,
                "bypass": False,
            },
        },
        "concat_av_high": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["img_high", 0],
                "audio_latent": ["split_av_low", 1],
            },
        },
        "sigmas_high": {
            "class_type": "ManualSigmas",
            "inputs": {"sigmas": SIGMAS_HIGH},
        },
        "sampler_high": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler_cfg_pp"},
        },
        "guider_high": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["lora_id", 0],
                "positive": ["crop_guides", 0],
                "negative": ["crop_guides", 1],
                "cfg": 1.0,
            },
        },
        "noise_high": {
            "class_type": "RandomNoise",
            "inputs": {
                "noise_seed": HIGH_RES_NOISE_SEED,
                "control_after_generate": "fixed",
            },
        },
        "ksampler_high": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["noise_high", 0],
                "guider": ["guider_high", 0],
                "sampler": ["sampler_high", 0],
                "sigmas": ["sigmas_high", 0],
                "latent_image": ["concat_av_high", 0],
            },
        },
        "split_av_high": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {"av_latent": ["ksampler_high", 0]},
        },

        # ============================================================
        # Decode + save
        # ============================================================
        "decode_video": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["split_av_high", 0],
                "vae": ["ckpt", 2],
                "tile_size": 768,
                "overlap": 64,
                "temporal_size": 4096,
                "temporal_overlap": 4,
            },
        },
        "decode_audio": {
            "class_type": "LTXVAudioVAEDecode",
            "inputs": {
                "samples": ["split_av_high", 1],
                "audio_vae": ["audio_vae", 0],
            },
        },
        "create_video": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["decode_video", 0],
                "audio": ["decode_audio", 0],
                "fps": float(fps),
            },
        },
        "save_video": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["create_video", 0],
                "filename_prefix": filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }


# ---------------------------------------------------------------------------
# MiniMax H3 workflow (T2V / first-last-frame I2V / reference-image R2V)
# ---------------------------------------------------------------------------

def build_h3_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    width: int,
    height: int,
    frames: int,
    steps: int,
    seed: int,
    input_image: str | None = None,
    input_end_image: str | None = None,
    reference_images: list[str] | None = None,
    ref_image_size: str = "match",
) -> dict[str, object]:
    """Build a native MiniMax H3 ComfyUI workflow in API format."""
    references = reference_images or []
    if len(references) > 9:
        raise ValueError("MiniMax H3 supports at most 9 reference images")
    if references and (input_image or input_end_image):
        raise ValueError("H3 reference mode cannot be combined with first/last keyframes")

    model_name = H3_MODEL_REF2VA if references else H3_MODEL_FL2VA
    conditioning_inputs: dict[str, object] = {
        "clip": ["2", 0],
        "vae": ["3", 0],
        "prompt": prompt,
        "width": width,
        "height": height,
        "length": frames,
    }
    workflow: dict[str, object] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": model_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": H3_TEXT_ENCODER,
                "type": "minimax",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": H3_VIDEO_VAE},
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": H3_AUDIO_VAE},
        },
    }

    if references:
        conditioning_inputs.update(
            {
                "audio_vae": ["4", 0],
                "ref_image_size": ref_image_size,
            }
        )
        for index, image_name in enumerate(references):
            node_id = str(20 + index)
            workflow[node_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": image_name},
            }
            conditioning_inputs[f"ref_images.ref_image_{index}"] = [node_id, 0]
        conditioning_type = "MiniMaxH3ReferenceToVideo"
    else:
        if input_image:
            workflow["20"] = {
                "class_type": "LoadImage",
                "inputs": {"image": input_image},
            }
            conditioning_inputs["first_frame"] = ["20", 0]
        if input_end_image:
            workflow["21"] = {
                "class_type": "LoadImage",
                "inputs": {"image": input_end_image},
            }
            conditioning_inputs["last_frame"] = ["21", 0]
        conditioning_type = "MiniMaxH3ImageToVideo"

    workflow.update(
        {
            "5": {
                "class_type": conditioning_type,
                "inputs": conditioning_inputs,
            },
            "6": {
                "class_type": "BasicGuider",
                "inputs": {"model": ["1", 0], "conditioning": ["5", 0]},
            },
            "7": {
                "class_type": "BasicScheduler",
                "inputs": {
                    "model": ["1", 0],
                    "scheduler": "simple",
                    "steps": steps,
                    "denoise": 1.0,
                },
            },
            "8": {
                "class_type": "RandomNoise",
                "inputs": {"noise_seed": seed, "control_after_generate": "fixed"},
            },
            "9": {
                "class_type": "KSamplerSelect",
                "inputs": {"sampler_name": "res_multistep"},
            },
            "10": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["8", 0],
                    "guider": ["6", 0],
                    "sampler": ["9", 0],
                    "sigmas": ["7", 0],
                    "latent_image": ["5", 1],
                },
            },
            "11": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["10", 0], "vae": ["3", 0]},
            },
            "12": {
                "class_type": "VAEDecodeAudio",
                "inputs": {"samples": ["10", 0], "vae": ["4", 0]},
            },
            "13": {
                "class_type": "CreateVideo",
                "inputs": {"images": ["11", 0], "audio": ["12", 0], "fps": 24.0},
            },
            "14": {
                "class_type": "SaveVideo",
                "inputs": {
                    "video": ["13", 0],
                    "filename_prefix": filename_prefix,
                    "format": "auto",
                    "codec": "auto",
                },
            },
        }
    )
    return workflow


# ---------------------------------------------------------------------------
# Network helpers (same pattern as generate_image.py)
# ---------------------------------------------------------------------------

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}
AUDIO_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}


def upload_file(broker_url: str, file_path: Path, timeout: int = 60) -> str:
    """Upload a local file (image or audio) to the broker and return the filename in ComfyUI input dir."""
    data = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    ct = AUDIO_CONTENT_TYPES.get(suffix)
    if ct is None:
        ct = "image/png"
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


def request_json(
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    timeout: int = 30,
) -> dict[str, object]:
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
                print(
                    f"Broker connection failed (attempt {attempt}/{retries}): {reason}; retrying...",
                    file=sys.stderr,
                )
                time.sleep(retry_delay * attempt)
                continue
            raise
        except ConnectionError as exc:
            last_error = exc
            if attempt == retries:
                raise
            print(
                f"Broker connection failed (attempt {attempt}/{retries}): {exc}; retrying...",
                file=sys.stderr,
            )
            time.sleep(retry_delay * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("request_json_with_retries: unreachable")


def download_file(
    url: str,
    target_path: Path,
    timeout: int,
    retries: int = 15,
    retry_delay: float = 1.0,
) -> None:
    request = urlrequest.Request(url, headers={"Accept": "*/*"}, method="GET")
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


# ---------------------------------------------------------------------------
# Core generation logic
# ---------------------------------------------------------------------------

def generate_video(
    *,
    broker_url: str,
    timeout_seconds: int,
    engine: str,
    prompt: str,
    output_path: Path,
    width: int,
    height: int,
    frames: int,
    steps: int,
    fps: int,
    seed: int,
    input_image: str | None = None,
    input_end_image: str | None = None,
    input_audio: str | None = None,
    lipsync: bool = False,
    id_lora: bool = False,
    reference_audio: str | None = None,
    reference_images: list[str] | None = None,
    ref_image_size: str = "match",
    identity_guidance_scale: float = 3.0,
    original_audio_path: Path | None = None,
    negative_prompt: str = NEGATIVE_PROMPT,
) -> str | None:
    """Generate one video. Returns an error message string, or None on success."""
    prefix = f"openclaw-local-output_{output_path.stem}-{seed}"

    audio_tag = "+audio" if input_audio else ""
    if engine == "minimax-h3":
        workflow = build_h3_workflow(
            prompt=prompt,
            filename_prefix=prefix,
            width=width,
            height=height,
            frames=frames,
            steps=steps,
            seed=seed,
            input_image=input_image,
            input_end_image=input_end_image,
            reference_images=reference_images,
            ref_image_size=ref_image_size,
        )
        if reference_images:
            label = f"h3-r2v ({len(reference_images)} refs), seed={seed}, {width}x{height}, {frames}f"
        elif input_image or input_end_image:
            keyframes = "+".join(
                name for name, present in (("first", input_image), ("last", input_end_image)) if present
            )
            label = f"h3-i2v ({keyframes}), seed={seed}, {width}x{height}, {frames}f"
        else:
            label = f"h3-t2v, seed={seed}, {width}x{height}, {frames}f"
    elif id_lora and input_image and reference_audio:
        workflow = build_idlora_workflow(
            prompt=prompt,
            filename_prefix=prefix,
            input_image=input_image,
            reference_audio=reference_audio,
            width=width,
            height=height,
            frames=frames,
            steps=steps,
            fps=fps,
            seed=seed,
            identity_guidance_scale=identity_guidance_scale,
            negative_prompt=negative_prompt,
        )
        label = f"id-lora, seed={seed}, {width}x{height}, {frames}f"
    elif lipsync and input_image and input_audio:
        workflow = build_lipsync_workflow(
            prompt=prompt,
            filename_prefix=prefix,
            input_image=input_image,
            input_audio=input_audio,
            width=width,
            height=height,
            frames=frames,
            steps=steps,
            fps=fps,
            seed=seed,
            negative_prompt=negative_prompt,
        )
        label = f"lipsync, seed={seed}, {width}x{height}, {frames}f"
    elif input_image:
        workflow = build_i2v_workflow(
            prompt=prompt,
            filename_prefix=prefix,
            input_image=input_image,
            input_end_image=input_end_image,
            width=width,
            height=height,
            frames=frames,
            steps=steps,
            fps=fps,
            seed=seed,
            input_audio=input_audio,
            negative_prompt=negative_prompt,
        )
        end_tag = "+end" if input_end_image else ""
        label = f"i2v{end_tag}{audio_tag}, seed={seed}, {width}x{height}, {frames}f"
    else:
        workflow = build_t2v_workflow(
            prompt=prompt,
            filename_prefix=prefix,
            width=width,
            height=height,
            frames=frames,
            steps=steps,
            fps=fps,
            seed=seed,
            input_audio=input_audio,
            negative_prompt=negative_prompt,
        )
        label = f"t2v{audio_tag}, seed={seed}, {width}x{height}, {frames}f"

    payload = {
        "workflow": workflow,
        "timeout_seconds": timeout_seconds,
    }

    print(f"Sending to broker ({label})")

    try:
        response = request_json_with_retries(
            "POST",
            f"{broker_url}/v1/generate",
            payload=payload,
            timeout=timeout_seconds + 90,
        )
    except Exception as exc:
        return f"Error talking to broker: {exc}"

    if response.get("status") != "ok":
        return f"Broker error: {json.dumps(response, ensure_ascii=False)}"

    results = response.get("results") or []
    if not results:
        return "Broker returned no results."

    first_result = results[0]
    outputs = first_result.get("outputs") or []
    if not outputs:
        return "Broker result did not include output files."

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
        download_file(download_url, output_path, timeout=max(120, timeout_seconds))
    except Exception as exc:
        return f"Error downloading broker output: {exc}"

    # For lipsync mode, replace the model-generated audio with the original
    if lipsync and original_audio_path and original_audio_path.exists():
        tmp_path = output_path.with_suffix(".tmp.mp4")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(output_path),
            "-i", str(original_audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(tmp_path),
        ]
        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=120)
            tmp_path.replace(output_path)
            print(f"Audio replaced with original: {original_audio_path.name}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            # Non-fatal: keep the model-generated audio
            print(f"Warning: could not replace audio ({exc}). Keeping model audio.", file=sys.stderr)
            if tmp_path.exists():
                tmp_path.unlink()

    print(f"Video saved: {output_path.resolve()}")
    print(f"SOURCE_FILENAME: {primary.get('filename')}")
    print(f"BROKER_PROMPT_ID: {first_result.get('prompt_id')}")
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate videos locally through the ComfyUI broker (LTX 2.3 or MiniMax H3)"
    )
    parser.add_argument(
        "--engine",
        choices=["ltx23", "minimax-h3"],
        default="ltx23",
        help="Generation engine (default: ltx23)",
    )
    parser.add_argument("--prompt", "-p", required=True, help="Video description (t2v) or action description (i2v)")
    parser.add_argument("--filename", "-f", required=True, help="Output filename (e.g. output.mp4)")
    parser.add_argument("--image", "-i", default=None, help="First-frame image for image-to-video mode")
    parser.add_argument("--end-image", default=None, help="Last-frame image (H3 also supports this without --image)")
    parser.add_argument(
        "--reference-image",
        action="append",
        default=[],
        help="H3 reference image; repeat up to 9 times in <Picture N> order",
    )
    parser.add_argument(
        "--ref-image-size",
        choices=["match", "max"],
        default="match",
        help="H3 reference sizing: match is faster; max preserves more identity detail",
    )
    parser.add_argument("--audio", default=None, help="Audio file to condition the video on (wav/mp3/ogg/flac/m4a)")
    parser.add_argument("--lipsync", action="store_true", help="Lip-sync mode: isolate vocals with MelBand RoFormer for better lip synchronisation (requires --image and --audio)")
    parser.add_argument("--id-lora", action="store_true", help="ID-LoRA mode: transfer voice identity from a ~5s reference audio to generate speech with consistent voice (requires --image and --reference-audio)")
    parser.add_argument("--reference-audio", default=None, help="Reference audio (~5s) for ID-LoRA voice identity transfer (wav/mp3/ogg/flac/m4a)")
    parser.add_argument("--identity-guidance-scale", type=float, default=3.0, help="Identity guidance scale for ID-LoRA (default 3.0, higher = stronger voice identity)")
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=5.0,
        help="Duration in seconds (1-20, default 5)",
    )
    parser.add_argument(
        "--resolution",
        "-r",
        choices=["480p", "720p", "1080p"],
        default="720p",
        help="Resolution preset (default 720p)",
    )
    parser.add_argument(
        "--aspect",
        "-a",
        choices=["16:9", "4:3", "1:1", "9:16", "3:4"],
        default="16:9",
        help="Aspect ratio (default 16:9)",
    )
    parser.add_argument("--fps", type=int, default=None, help=f"Frames per second (default {DEFAULT_FPS}, or {IDLORA_DEFAULT_FPS} when --id-lora)")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help=f"Sampling steps (default {DEFAULT_STEPS})")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducibility")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of videos to generate (each with different seed)")
    parser.add_argument("--negative-prompt", default=None, help="Negative prompt (what to avoid). Appended to built-in negatives unless prefixed with !")
    parser.add_argument("--timeout-seconds", type=int, default=None, help="Broker timeout override")
    parser.add_argument("--broker-url", default=None, help="Broker base URL override")
    args = parser.parse_args()

    is_h3 = args.engine == "minimax-h3"
    if is_h3:
        incompatible = []
        if args.lipsync:
            incompatible.append("--lipsync")
        if args.id_lora:
            incompatible.append("--id-lora")
        if args.audio:
            incompatible.append("--audio")
        if args.reference_audio:
            incompatible.append("--reference-audio")
        if incompatible:
            print(f"MiniMax H3 does not support these LTX options: {', '.join(incompatible)}", file=sys.stderr)
            return 1
        if args.reference_image and (args.image or args.end_image):
            print("H3 --reference-image cannot be combined with --image/--end-image", file=sys.stderr)
            return 1
        if len(args.reference_image) > 9:
            print("MiniMax H3 supports at most 9 --reference-image values", file=sys.stderr)
            return 1
        if args.fps is not None and args.fps != 24:
            print("MiniMax H3 runs at a fixed 24 fps", file=sys.stderr)
            return 1
    elif args.reference_image:
        print("--reference-image requires --engine minimax-h3", file=sys.stderr)
        return 1

    broker_url = (
        args.broker_url
        or os.environ.get("OPENCLAW_COMFYUI_LOCAL_BROKER_URL")
        or os.environ.get("OPENCLAW_BROKER_URL")
        or DEFAULT_BROKER_URL
    ).rstrip("/")

    timeout_seconds = args.timeout_seconds or int(
        os.environ.get("OPENCLAW_COMFYUI_LOCAL_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    )

    # Resolve resolution + aspect -> width x height
    preset_key = f"{args.resolution}-{args.aspect}"
    presets = H3_VIDEO_PRESETS if is_h3 else VIDEO_PRESETS
    if preset_key not in presets:
        print(f"Invalid preset combination: {preset_key}", file=sys.stderr)
        return 1
    width, height = presets[preset_key]

    # Default fps depends on the mode (ID-LoRA template runs at 25 fps).
    if is_h3:
        args.fps = 24
    elif args.fps is None:
        args.fps = IDLORA_DEFAULT_FPS if getattr(args, "id_lora", False) else DEFAULT_FPS

    # Duration -> frames
    duration = max(1.0, min(args.duration, 15.0 if is_h3 else 20.0))
    frames = h3_duration_to_frames(duration) if is_h3 else duration_to_frames(duration, args.fps)

    seed = args.seed if args.seed is not None else int(time.time() * 1000) % 2147483647
    count = max(1, min(args.count, 10))
    output_path = Path(args.filename)

    # Upload image if i2v
    uploaded_image: str | None = None
    if args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"Input image not found: {image_path}", file=sys.stderr)
            return 1
        print(f"Uploading first-frame image: {image_path}")
        try:
            uploaded_image = upload_file(broker_url, image_path)
            print(f"Uploaded as: {uploaded_image}")
        except Exception as exc:
            print(f"Error uploading image: {exc}", file=sys.stderr)
            return 1

    # Upload end image if provided
    uploaded_end_image: str | None = None
    if args.end_image:
        if not args.image and not is_h3:
            print("--end-image requires --image (start frame)", file=sys.stderr)
            return 1
        end_image_path = Path(args.end_image)
        if not end_image_path.exists():
            print(f"End image not found: {end_image_path}", file=sys.stderr)
            return 1
        print(f"Uploading end-frame image: {end_image_path}")
        try:
            uploaded_end_image = upload_file(broker_url, end_image_path)
            print(f"Uploaded as: {uploaded_end_image}")
        except Exception as exc:
            print(f"Error uploading end image: {exc}", file=sys.stderr)
            return 1

    # Upload H3 reference images in the same order used by <Picture N> tags.
    uploaded_reference_images: list[str] = []
    for index, reference in enumerate(args.reference_image, start=1):
        reference_path = Path(reference)
        if not reference_path.exists():
            print(f"Reference image {index} not found: {reference_path}", file=sys.stderr)
            return 1
        print(f"Uploading reference image {index}: {reference_path}")
        try:
            uploaded = upload_file(broker_url, reference_path)
            uploaded_reference_images.append(uploaded)
            print(f"Uploaded as <Picture {index}>: {uploaded}")
        except Exception as exc:
            print(f"Error uploading reference image {index}: {exc}", file=sys.stderr)
            return 1

    # Upload audio if provided
    uploaded_audio: str | None = None
    if args.audio:
        audio_path = Path(args.audio)
        if not audio_path.exists():
            print(f"Input audio not found: {audio_path}", file=sys.stderr)
            return 1
        if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            print(f"Unsupported audio format: {audio_path.suffix}", file=sys.stderr)
            return 1
        print(f"Uploading audio: {audio_path}")
        try:
            uploaded_audio = upload_file(broker_url, audio_path)
            print(f"Uploaded as: {uploaded_audio}")
        except Exception as exc:
            print(f"Error uploading audio: {exc}", file=sys.stderr)
            return 1

    # Validate --lipsync requirements
    lipsync = getattr(args, 'lipsync', False)
    if lipsync:
        if not uploaded_image:
            print("--lipsync requires --image (face/portrait)", file=sys.stderr)
            return 1
        if not uploaded_audio:
            print("--lipsync requires --audio (speech audio)", file=sys.stderr)
            return 1

    # Upload reference audio for ID-LoRA mode
    uploaded_reference_audio: str | None = None
    id_lora = getattr(args, 'id_lora', False)
    if id_lora:
        if not uploaded_image:
            print("--id-lora requires --image (first-frame face/portrait)", file=sys.stderr)
            return 1
        if not args.reference_audio:
            print("--id-lora requires --reference-audio (5s voice sample)", file=sys.stderr)
            return 1
        ref_audio_path = Path(args.reference_audio)
        if not ref_audio_path.exists():
            print(f"Reference audio not found: {ref_audio_path}", file=sys.stderr)
            return 1
        if ref_audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            print(f"Unsupported reference audio format: {ref_audio_path.suffix}", file=sys.stderr)
            return 1
        print(f"Uploading reference audio: {ref_audio_path}")
        try:
            uploaded_reference_audio = upload_file(broker_url, ref_audio_path)
            print(f"Uploaded as: {uploaded_reference_audio}")
        except Exception as exc:
            print(f"Error uploading reference audio: {exc}", file=sys.stderr)
            return 1

    if is_h3:
        if uploaded_reference_images:
            mode = f"MiniMax H3 reference-to-video ({len(uploaded_reference_images)} images)"
        elif uploaded_image or uploaded_end_image:
            anchors = "+".join(
                name for name, present in (("first", uploaded_image), ("last", uploaded_end_image)) if present
            )
            mode = f"MiniMax H3 image-to-video ({anchors})"
        else:
            mode = "MiniMax H3 text-to-video"
    else:
        mode = "id-lora" if id_lora else ("lip-sync" if lipsync else ("image-to-video" if uploaded_image else "text-to-video"))
        if not id_lora and not lipsync and uploaded_end_image:
            mode += " (start+end)"
        if uploaded_audio:
            mode += " + audio"
    print(f"Mode: {mode} | {width}x{height} @ {args.fps}fps | {duration:.1f}s ({frames} frames)")
    # Resolve negative prompt (ID-LoRA template uses a different baseline).
    base_negative = IDLORA_NEGATIVE_PROMPT if id_lora else NEGATIVE_PROMPT
    if args.negative_prompt and args.negative_prompt.startswith("!"):
        neg_prompt = args.negative_prompt[1:]  # full override
    elif args.negative_prompt:
        neg_prompt = f"{base_negative}, {args.negative_prompt}"
    else:
        neg_prompt = base_negative

    print(f"Steps: {args.steps} | Seed: {seed}" + (f" | Count: {count}" if count > 1 else ""))

    errors = []
    for idx in range(count):
        current_seed = seed + idx
        if count > 1:
            stem = output_path.stem
            suffix = output_path.suffix
            current_output = output_path.with_name(f"{stem}_{idx + 1}{suffix}")
            print(f"\n--- Video {idx + 1}/{count} (seed {current_seed}) ---")
        else:
            current_output = output_path

        err = generate_video(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            engine=args.engine,
            prompt=args.prompt,
            output_path=current_output,
            width=width,
            height=height,
            frames=frames,
            steps=args.steps,
            fps=args.fps,
            seed=current_seed,
            input_image=uploaded_image,
            input_end_image=uploaded_end_image,
            input_audio=uploaded_audio,
            lipsync=lipsync,
            id_lora=id_lora,
            reference_audio=uploaded_reference_audio,
            reference_images=uploaded_reference_images,
            ref_image_size=args.ref_image_size,
            identity_guidance_scale=args.identity_guidance_scale,
            original_audio_path=audio_path if lipsync else None,
            negative_prompt=neg_prompt,
        )
        if err:
            print(err, file=sys.stderr)
            errors.append(err)

    if errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
