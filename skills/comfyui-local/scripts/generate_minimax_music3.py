#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate songs locally through the OpenClaw ComfyUI broker (MiniMax Music 3).

MiniMax Music 3 (open weights) — hierarchical autoregressive music model:
8B global LLM + 0.6B local LLM + Flow Matching + Flow-VAE.
Creates complete songs up to 6 minutes (360s) with vocals or instrumental.

Uses the native ComfyUI nodes (MiniMaxMusic3TextEncode,
EmptyMiniMaxMusic3LatentAudio, KSampler, VAEDecodeAudio[Tiled]).

NOTE: the broker swaps the GPU (stops llama-server, starts ComfyUI, runs the
job, restores llama-server) — the Hermes LLM goes offline for the duration.
"""

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
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_STEPS = 30
DEFAULT_CFG = 1.7
DEFAULT_MAX_DURATION = 120.0

# MAX_AUDIO_FRAMES (9000) / AUDIO_FRAMES_PER_SECOND (25) = 360s hard ceiling.
HARD_MAX_DURATION = 360.0

# Model files (Comfy-Org/MiniMax-Music-3 repackaged)
DIT_FP16 = "minimax_music3_dit_fp16.safetensors"
TEXT_ENCODER = "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"
VAE = "minimax_music3_dav.safetensors"

# Quality presets -> diffusion model
QUALITY_MODELS: dict[str, str] = {
    "high": DIT_FP16,   # 4.6GB — best quality, needs ~24GB+ VRAM
}


# ---------------------------------------------------------------------------
# Workflow builder (API format, mirrors official template audio_minimax_music_3)
# ---------------------------------------------------------------------------

def build_music3_workflow(
    *,
    caption: str,
    lyrics: str,
    filename_prefix: str,
    max_duration: float,
    seed: int,
    steps: int,
    cfg: float,
    quality: str,
    tiled_decode: bool = False,
    output_format: str = "mp3",
) -> dict[str, object]:
    """Build the MiniMax Music 3 text-to-music workflow (ComfyUI API format)."""
    unet_name = QUALITY_MODELS.get(quality, DIT_FP16)

    workflow: dict[str, object] = {
        # Loaders
        "6": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": TEXT_ENCODER, "type": "minimax"},
        },
        "7": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VAE},
        },
        # Conditioning: text encode from caption + lyrics;
        # also emits the seconds the model actually wants.
        "13": {
            "class_type": "MiniMaxMusic3TextEncode",
            "inputs": {
                "clip": ["3", 0],
                "caption": caption,
                "lyrics": lyrics,
                "seed": seed,
                "max_duration": max_duration,
                "cfg_scale": cfg,
                "top_k": 50,
            },
        },
        "10": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["13", 0]},
        },
        # Empty latent sized to the model's chosen duration
        "15": {
            "class_type": "EmptyMiniMaxMusic3LatentAudio",
            "inputs": {"seconds": ["13", 1], "batch_size": 1},
        },
        # Sampling (official template: 30 steps, cfg 1.7, euler/simple)
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["6", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["13", 0],
                "negative": ["10", 0],
                "latent_image": ["15", 0],
                "denoise": 1.0,
            },
        },
        # Decodes (normal + tiled), switched by --tiled-decode
        "12": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["9", 0], "vae": ["7", 0]},
        },
        "42": {
            "class_type": "VAEDecodeAudioTiled",
            "inputs": {"samples": ["9", 0], "vae": ["7", 0],
                       "tile_size": 1536, "overlap": 64},
        },
        "43": {
            "class_type": "ComfySwitchNode",
            "inputs": {"switch": tiled_decode,
                       "on_false": ["12", 0], "on_true": ["42", 0]},
        },
        # Save. `format` is a DynamicCombo input: in API format the frontend
        # sends flattened dotted keys, e.g. "format": "mp3" +
        # "format.quality": "V0" (build_nested_inputs restructures them).
        "35": {
            "class_type": "SaveAudioAdvanced",
            "inputs": {
                "audio": ["43", 0],
                "filename_prefix": filename_prefix,
                "format": output_format,
                **({"format.quality": "V0"} if output_format == "mp3" else {}),
            },
        },
    }
    return workflow


# ---------------------------------------------------------------------------
# Network helpers (same pattern as generate_song.py)
# ---------------------------------------------------------------------------

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
            time.sleep(retry_delay)
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

def generate_song(
    *,
    broker_url: str,
    timeout_seconds: int,
    caption: str,
    lyrics: str,
    output_path: Path,
    max_duration: float,
    seed: int,
    steps: int,
    cfg: float,
    quality: str,
    tiled_decode: bool,
    output_format: str,
) -> str | None:
    """Generate one song. Returns an error message string, or None on success."""
    prefix = f"audio/openclaw-mm3-{output_path.stem}-{seed}"

    workflow = build_music3_workflow(
        caption=caption,
        lyrics=lyrics,
        filename_prefix=prefix,
        max_duration=max_duration,
        seed=seed,
        steps=steps,
        cfg=cfg,
        quality=quality,
        tiled_decode=tiled_decode,
        output_format=output_format,
    )

    label = (f"{quality}, seed={seed}, max={max_duration:.0f}s, "
             f"{steps} steps, cfg={cfg}"
             + (", tiled" if tiled_decode else ""))

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
    if first_result.get("error"):
        return f"Job error: {first_result['error']}"
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

    print(f"Song saved: {output_path.resolve()}")
    print(f"SOURCE_FILENAME: {primary.get('filename')}")
    print(f"BROKER_PROMPT_ID: {first_result.get('prompt_id')}")
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate songs locally through the ComfyUI broker (MiniMax Music 3)"
    )
    parser.add_argument(
        "--caption", "-c", required=True,
        help="Structured music description (Global Metadata / Vocal Details / Arrangement)",
    )
    parser.add_argument("--filename", "-f", required=True,
                        help="Output filename (e.g. output.mp3)")
    parser.add_argument("--lyrics", "-l", default="",
                        help="Song lyrics with section tags ([Intro] [Verse] [Chorus] [Bridge] [Outro]). "
                             "Empty = instrumental.")
    parser.add_argument("--instrumental", action="store_true",
                        help="Force instrumental (sets lyrics to [Instrumental])")
    parser.add_argument("--duration", "-d", type=float, default=DEFAULT_MAX_DURATION,
                        help=f"Max duration in seconds (1-{HARD_MAX_DURATION:.0f}, default {DEFAULT_MAX_DURATION:.0f}). "
                             "The model may end the song earlier.")
    parser.add_argument("--quality", choices=["high"], default="high",
                        help="high=FP16 DiT (the only installed DiT; int8 was never downloaded and removed from the menu 2026-09-21)")
    parser.add_argument("--tiled-decode", action="store_true",
                        help="Decode VAE in tiles (cuts VRAM for long songs; slight seam risk)")
    parser.add_argument("--format", choices=["mp3", "flac"], default="mp3",
                        help="Output audio format (default mp3 V0)")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"KSampler steps (default {DEFAULT_STEPS}; official template value)")
    parser.add_argument("--cfg", type=float, default=DEFAULT_CFG,
                        help=f"CFG scale for both text-encode and KSampler (default {DEFAULT_CFG})")
    parser.add_argument("--count", "-n", type=int, default=1,
                        help="Number of songs in one batch (default 1)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed for reproducibility (random by default)")
    parser.add_argument("--timeout-seconds", type=int, default=None,
                        help="Broker timeout override")
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

    duration = max(1.0, min(args.duration, HARD_MAX_DURATION))
    lyrics = args.lyrics.strip()
    if args.instrumental:
        lyrics = ""
    has_lyrics = bool(lyrics)
    lyrics_for_model = lyrics if has_lyrics else "[Instrumental]"

    count = max(1, min(args.count, 10))
    seed = args.seed if args.seed is not None else int(time.time() * 1000) % 2147483647
    output_path = Path(args.filename)

    mode = f"MiniMax Music 3 ({args.quality})"
    if args.tiled_decode:
        mode += " + tiled"
    kind = "with lyrics" if has_lyrics else "instrumental"
    count_label = f" x{count}" if count > 1 else ""
    print(f"Mode: {mode} | max {duration:.0f}s | {kind}{count_label}")
    print(f"Steps: {args.steps} | CFG: {args.cfg} | Seed: {seed}")
    print(f"Broker: {broker_url}")

    if count == 1:
        err = generate_song(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            caption=args.caption,
            lyrics=lyrics_for_model,
            output_path=output_path,
            max_duration=duration,
            seed=seed,
            steps=args.steps,
            cfg=args.cfg,
            quality=args.quality,
            tiled_decode=args.tiled_decode,
            output_format=args.format,
        )
        if err:
            print(err, file=sys.stderr)
            return 1
        return 0

    # --- Batch mode: one job per song (broker batches them), unique seeds ---
    stem = output_path.stem
    suffix = output_path.suffix or ".mp3"
    parent = output_path.parent
    errors: list[str] = []
    errors_lock = threading.Lock()

    def worker(index: int) -> None:
        song_seed = seed + index
        song_path = parent / f"{stem}-{index + 1}{suffix}"
        err = generate_song(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            caption=args.caption,
            lyrics=lyrics_for_model,
            output_path=song_path,
            max_duration=duration,
            seed=song_seed,
            steps=args.steps,
            cfg=args.cfg,
            quality=args.quality,
            tiled_decode=args.tiled_decode,
            output_format=args.format,
        )
        if err:
            with errors_lock:
                errors.append(err)

    threads: list[threading.Thread] = []
    for i in range(count):
        thread = threading.Thread(target=worker, args=(i,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print(f"All {count} songs generated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
