#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate videos locally through the OpenClaw ComfyUI broker (LTX 2.3)."""

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


def duration_to_frames(seconds: float, fps: int = DEFAULT_FPS) -> int:
    """Convert seconds to LTX frame count (must be 8k+1)."""
    raw = seconds * fps
    return round(raw / 8) * 8 + 1


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
    original_audio_path: Path | None = None,
    negative_prompt: str = NEGATIVE_PROMPT,
) -> str | None:
    """Generate one video. Returns an error message string, or None on success."""
    prefix = f"openclaw-local-output_{output_path.stem}-{seed}"

    audio_tag = "+audio" if input_audio else ""
    if lipsync and input_image and input_audio:
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
        description="Generate videos locally through the ComfyUI broker (LTX 2.3)"
    )
    parser.add_argument("--prompt", "-p", required=True, help="Video description (t2v) or action description (i2v)")
    parser.add_argument("--filename", "-f", required=True, help="Output filename (e.g. output.mp4)")
    parser.add_argument("--image", "-i", default=None, help="First-frame image for image-to-video mode")
    parser.add_argument("--end-image", default=None, help="Last-frame image for start+end frame conditioning (requires --image)")
    parser.add_argument("--audio", default=None, help="Audio file to condition the video on (wav/mp3/ogg/flac/m4a)")
    parser.add_argument("--lipsync", action="store_true", help="Lip-sync mode: isolate vocals with MelBand RoFormer for better lip synchronisation (requires --image and --audio)")
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
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help=f"Frames per second (default {DEFAULT_FPS})")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help=f"Sampling steps (default {DEFAULT_STEPS})")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducibility")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of videos to generate (each with different seed)")
    parser.add_argument("--negative-prompt", default=None, help="Negative prompt (what to avoid). Appended to built-in negatives unless prefixed with !")
    parser.add_argument("--timeout-seconds", type=int, default=None, help="Broker timeout override")
    parser.add_argument("--broker-url", default=None, help="Broker base URL override")
    args = parser.parse_args()

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
    if preset_key not in VIDEO_PRESETS:
        print(f"Invalid preset combination: {preset_key}", file=sys.stderr)
        return 1
    width, height = VIDEO_PRESETS[preset_key]

    # Duration -> frames
    duration = max(1.0, min(args.duration, 20.0))
    frames = duration_to_frames(duration, args.fps)

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
        if not args.image:
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

    mode = "lip-sync" if lipsync else ("image-to-video" if uploaded_image else "text-to-video")
    if not lipsync and uploaded_end_image:
        mode += " (start+end)"
    if uploaded_audio:
        mode += " + audio"
    print(f"Mode: {mode} | {width}x{height} @ {args.fps}fps | {duration:.1f}s ({frames} frames)")
    # Resolve negative prompt
    if args.negative_prompt and args.negative_prompt.startswith("!"):
        neg_prompt = args.negative_prompt[1:]  # full override
    elif args.negative_prompt:
        neg_prompt = f"{NEGATIVE_PROMPT}, {args.negative_prompt}"
    else:
        neg_prompt = NEGATIVE_PROMPT

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
