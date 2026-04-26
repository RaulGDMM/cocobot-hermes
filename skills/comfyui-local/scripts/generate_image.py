#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate images locally through the OpenClaw ComfyUI broker."""

from __future__ import annotations

import argparse
import json
import os
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


def build_workflow(
    *,
    prompt: str,
    filename_prefix: str,
    width: int,
    height: int,
    steps: int,
    guidance: float,
    seed: int,
    model: str = "flux1-dev",
) -> dict[str, object]:
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
) -> str | None:
    if input_image:
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
        )
        label = f"seed={seed}, size={width}x{height}, model={model}"

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
    parser.add_argument("--steps", type=int, default=20, help="Sampling steps")
    parser.add_argument("--guidance", type=float, default=None, help="Guidance value (default: 3.5 generate, 2.5 edit)")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducible output")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of images to generate in one batch")
    parser.add_argument("--timeout-seconds", type=int, default=None, help="Broker timeout override")
    parser.add_argument("--broker-url", default=None, help="Broker base URL override")
    parser.add_argument("--model", choices=["flux1-dev", "flux2-klein-9b"], default="flux2-klein-9b", help="Model to use (default: flux2-klein-9b)")
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

    width, height = resolve_size(args.width, args.height, args.aspect)
    base_seed = args.seed if args.seed is not None else int(time.time() * 1000) % 2147483647
    output_path = Path(args.filename)

    if edit_mode:
        extra = f" + image2={args.image2}" if args.image2 else ""
        print(f"Editing {count} image(s) via Kontext: {args.image}{extra}")
    else:
        print(f"Generating {count} image(s) locally via broker: {broker_url}")
    print(f"Steps: {args.steps} | Guidance: {guidance} | Base seed: {base_seed}")

    if count == 1:
        err = generate_one(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            prompt=prompts[0],
            output_path=output_path,
            width=width,
            height=height,
            steps=args.steps,
            guidance=guidance,
            seed=base_seed,
            index=1,
            input_image=uploaded_image,
            input_image2=uploaded_image2,
            model=args.model,
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
            steps=args.steps,
            guidance=guidance,
            seed=base_seed + index,
            index=index + 1,
            input_image=uploaded_image,
            input_image2=uploaded_image2,
            model=args.model,
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