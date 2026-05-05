#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate songs locally through the OpenClaw ComfyUI broker (ACE Step 1.5)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


DEFAULT_BROKER_URL = "http://host.docker.internal:8791"
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_STEPS = 8
DEFAULT_CFG = 1.0
DEFAULT_BPM = 120
DEFAULT_DURATION = 120.0

# Turbo model supports 1-20 inference steps (official docs recommend 8).
# Short songs get fewer LM tokens, so more DiT steps compensate.
# Auto-scaling: 120s→8, 60s→16, 30s→20 (capped).
TURBO_MAX_STEPS = 20
TURBO_BASELINE_DURATION = 120.0  # seconds — step count calibrated for this
DEFAULT_LANGUAGE = "es"
DEFAULT_KEY = "C major"
DEFAULT_TIMESIG = "4"



# Split 4B models (high quality — larger text encoder, 2B base)
MODEL_UNET = "acestep_v1.5_turbo.safetensors"
MODEL_CLIP1 = "qwen_0.6b_ace15.safetensors"
MODEL_CLIP2 = "qwen_4b_ace15.safetensors"
MODEL_VAE = "ace_1.5_vae.safetensors"

# XL models (4B decoder — higher quality audio)
MODEL_XL_TURBO = "acestep_v1.5_xl_turbo_bf16.safetensors"
MODEL_XL_MERGE = "acestep_v1.5_xl_merge_sft_turbo_ta_0.5.safetensors"

# AIO checkpoint (standard quality — bundled small encoder)
MODEL_AIO = "ace_step_1.5_turbo_aio.safetensors"

# Map quality presets to their model file
QUALITY_MODELS: dict[str, str] = {
    "high": MODEL_UNET,
    "xl-turbo": MODEL_XL_TURBO,
    "xl-merge": MODEL_XL_MERGE,
}

KEYSCALE_OPTIONS = [
    f"{root} {quality}"
    for quality in ["major", "minor"]
    for root in [
        "C", "C#", "Db", "D", "D#", "Eb", "E", "F",
        "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B",
    ]
]

LANGUAGE_OPTIONS = [
    "en", "ja", "zh", "es", "de", "fr", "pt", "ru", "it", "nl",
    "pl", "tr", "vi", "cs", "fa", "id", "ko", "uk", "hu", "ar",
    "sv", "ro", "el",
]

TIMESIG_OPTIONS = ["2", "3", "4", "6"]

def auto_steps(duration: float, base_steps: int = DEFAULT_STEPS) -> int:
    """Scale DiT inference steps inversely to duration so short songs get
    more compute per second.  Capped at TURBO_MAX_STEPS (20).
    120s → 8 steps,  60s → 16,  30s → 20 (capped)."""
    if duration >= TURBO_BASELINE_DURATION:
        return base_steps
    scaled = round(base_steps * TURBO_BASELINE_DURATION / duration)
    return max(base_steps, min(TURBO_MAX_STEPS, scaled))


AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}
AUDIO_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}


# ---------------------------------------------------------------------------
# Workflow builder
# ---------------------------------------------------------------------------

def build_song_workflow(
    *,
    tags: str,
    lyrics: str,
    filename_prefix: str,
    duration: float,
    bpm: int,
    language: str,
    key: str,
    timesig: str,
    seed: int,
    steps: int,
    cfg: float,
    quality: str,
    reference_audio: str | None = None,
    output_format: str = "mp3",
) -> dict[str, object]:
    """Build an ACE Step 1.5 song generation workflow (API format).

    Uses the AceStepSFTGenerate all-in-one node for generation.
    """

    use_reference = reference_audio is not None

    # Select diffusion model based on quality tier
    unet_name = QUALITY_MODELS.get(quality, MODEL_UNET)

    guidance_mode = "standard_cfg"
    shift = 3.0

    has_lyrics = bool(lyrics and lyrics.strip() and lyrics.strip().lower() != "[instrumental]")

    # --- AceStepSFTGenerate all-in-one node ---
    workflow: dict[str, object] = {
        "1": {
            "class_type": "AceStepSFTGenerate",
            "inputs": {
                # Model files
                "diffusion_model": unet_name,
                "text_encoder_1": MODEL_CLIP1,
                "text_encoder_2": MODEL_CLIP2,
                "vae_name": MODEL_VAE,
                # Text inputs
                "caption": tags,
                "lyrics": lyrics if has_lyrics else "[Instrumental]",
                "instrumental": not has_lyrics,
                # Sampling
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "infer_method": "ode",
                "guidance_mode": guidance_mode,
                # Duration & metadata
                "duration": duration,
                "bpm": bpm,
                "timesignature": timesig,
                "language": language,
                "keyscale": key,
                # LLM audio code generation
                "generate_audio_codes": True,
                "lm_cfg_scale": 2.0,
                "lm_temperature": 0.85,
                "lm_top_p": 0.9,
                "lm_top_k": 0,
                "lm_min_p": 0.0,
                # Schedule shift
                "shift": shift,
                # APG parameters (active only when guidance_mode="apg")
                "apg_momentum": -0.75,
                "apg_norm_threshold": 2.5,
                "apg_eta": 0.0,
                # Guidance interval: apply guidance in centered 50% of timesteps
                "guidance_interval": 0.5,
            },
        },
    }

    # --- Reference audio for timbre/style transfer (img2img approach) ---
    if use_reference:
        workflow["10"] = {
            "class_type": "LoadAudio",
            "inputs": {"audio": reference_audio},
        }
        # Connect reference as source audio; denoise=0.7 preserves timbre
        # while regenerating content with the new tags/lyrics.
        workflow["1"]["inputs"]["latent_or_audio"] = ["10", 0]
        workflow["1"]["inputs"]["denoise"] = 0.7

    # --- Save output ---
    if output_format == "flac":
        workflow["2"] = {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["1", 0],
                "filename_prefix": filename_prefix,
            },
        }
    else:
        workflow["2"] = {
            "class_type": "SaveAudioMP3",
            "inputs": {
                "audio": ["1", 0],
                "filename_prefix": filename_prefix,
                "quality": "320k",
            },
        }

    return workflow


def build_edit_workflow(
    *,
    original_audio: str,
    tags: str,
    lyrics: str,
    filename_prefix: str,
    duration: float,
    bpm: int,
    language: str,
    key: str,
    timesig: str,
    seed: int,
    steps: int,
    cfg: float,
    quality: str,
    denoise: float,
    output_format: str = "mp3",
) -> dict[str, object]:
    """Build an ACE Step 1.5 song EDIT workflow (partial denoise on encoded original).

    Uses the AceStepSFTGenerate all-in-one node with
    latent_or_audio input for img2img-style editing.
    """

    unet_name = QUALITY_MODELS.get(quality, MODEL_UNET)
    guidance_mode = "standard_cfg"
    shift = 3.0

    has_lyrics = bool(lyrics and lyrics.strip() and lyrics.strip().lower() != "[instrumental]")

    workflow: dict[str, object] = {
        # Load original audio
        "10": {
            "class_type": "LoadAudio",
            "inputs": {"audio": original_audio},
        },
        # AceStepSFTGenerate with partial denoise on original
        "1": {
            "class_type": "AceStepSFTGenerate",
            "inputs": {
                # Model files
                "diffusion_model": unet_name,
                "text_encoder_1": MODEL_CLIP1,
                "text_encoder_2": MODEL_CLIP2,
                "vae_name": MODEL_VAE,
                # Text inputs
                "caption": tags,
                "lyrics": lyrics if has_lyrics else "[Instrumental]",
                "instrumental": not has_lyrics,
                # Sampling
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": denoise,
                "infer_method": "ode",
                "guidance_mode": guidance_mode,
                # Source audio for img2img editing
                "latent_or_audio": ["10", 0],
                # Duration & metadata (use 0 = derive from source audio)
                "duration": 0.0,
                "bpm": bpm,
                "timesignature": timesig,
                "language": language,
                "keyscale": key,
                # LLM audio code generation
                "generate_audio_codes": True,
                "lm_cfg_scale": 2.0,
                "lm_temperature": 0.85,
                "lm_top_p": 0.9,
                "lm_top_k": 0,
                "lm_min_p": 0.0,
                # Schedule shift
                "shift": shift,
                # APG parameters
                "apg_momentum": -0.75,
                "apg_norm_threshold": 2.5,
                "apg_eta": 0.0,
                "guidance_interval": 0.5,
            },
        },
    }

    # --- Save output ---
    if output_format == "flac":
        workflow["2"] = {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["1", 0],
                "filename_prefix": filename_prefix,
            },
        }
    else:
        workflow["2"] = {
            "class_type": "SaveAudioMP3",
            "inputs": {
                "audio": ["1", 0],
                "filename_prefix": filename_prefix,
                "quality": "320k",
            },
        }

    return workflow


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def _ensure_ffmpeg() -> str:
    for candidate in ("ffmpeg",):
        if shutil.which(candidate):
            return candidate
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    raise FileNotFoundError("ffmpeg not found")


def _ensure_ffprobe() -> str:
    for candidate in ("ffprobe",):
        if shutil.which(candidate):
            return candidate
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass
    if shutil.which("ffprobe"):
        return "ffprobe"
    raise FileNotFoundError("ffprobe not found")


def get_audio_duration(path: Path) -> float:
    """Get duration of an audio file in seconds."""
    ffprobe = _ensure_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def splice_edit_region(
    original_path: Path,
    regenerated_path: Path,
    output_path: Path,
    start: float,
    end: float,
    crossfade: float = 0.5,
) -> None:
    """Splice the edit region from regenerated into original with crossfade."""
    ffmpeg = _ensure_ffmpeg()
    total = get_audio_duration(original_path)
    cf = min(crossfade, start, total - end, (end - start) / 2)
    cf = max(cf, 0.05)

    filter_complex = (
        f"[0]atrim=0:{start + cf / 2},asetpts=PTS-STARTPTS[a];"
        f"[1]atrim={start - cf / 2}:{end + cf / 2},asetpts=PTS-STARTPTS[b];"
        f"[0]atrim={end - cf / 2},asetpts=PTS-STARTPTS[c];"
        f"[a][b]acrossfade=d={cf}:c1=tri:c2=tri[ab];"
        f"[ab][c]acrossfade=d={cf}:c1=tri:c2=tri[out]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y",
         "-i", str(original_path),
         "-i", str(regenerated_path),
         "-filter_complex", filter_complex,
         "-map", "[out]",
         "-b:a", "320k",
         str(output_path)],
        check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def upload_file(broker_url: str, file_path: Path, timeout: int = 60) -> str:
    """Upload a local audio file to the broker and return the filename in ComfyUI input dir."""
    data = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    ct = AUDIO_CONTENT_TYPES.get(suffix, "application/octet-stream")

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

def generate_song(
    *,
    broker_url: str,
    timeout_seconds: int,
    tags: str,
    lyrics: str,
    output_path: Path,
    duration: float,
    bpm: int,
    language: str,
    key: str,
    timesig: str,
    seed: int,
    steps: int,
    cfg: float,
    quality: str,
    reference_audio: str | None = None,
    output_format: str = "mp3",
) -> str | None:
    """Generate one song. Returns an error message string, or None on success."""
    prefix = f"audio/openclaw-song-{output_path.stem}-{seed}"

    workflow = build_song_workflow(
        tags=tags,
        lyrics=lyrics,
        filename_prefix=prefix,
        duration=duration,
        bpm=bpm,
        language=language,
        key=key,
        timesig=timesig,
        seed=seed,
        steps=steps,
        cfg=cfg,
        quality=quality,
        reference_audio=reference_audio,
        output_format=output_format,
    )

    ref_tag = "+ref" if reference_audio else ""
    label = f"{quality}{ref_tag}, seed={seed}, {duration:.0f}s, {bpm}bpm, {key}, {language}"

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

    print(f"Song saved: {output_path.resolve()}")
    print(f"SOURCE_FILENAME: {primary.get('filename')}")
    print(f"BROKER_PROMPT_ID: {first_result.get('prompt_id')}")
    return None


def edit_song(
    *,
    broker_url: str,
    timeout_seconds: int,
    original_path: Path,
    tags: str,
    lyrics: str,
    output_path: Path,
    duration: float,
    bpm: int,
    language: str,
    key: str,
    timesig: str,
    seed: int,
    steps: int,
    cfg: float,
    quality: str,
    denoise: float,
    start_time: float,
    end_time: float,
    crossfade: float,
    output_format: str = "mp3",
) -> str | None:
    """Edit a section of a song. Returns an error message string, or None on success."""

    # 1. Upload original to broker
    try:
        uploaded = upload_file(broker_url, original_path)
    except Exception as exc:
        return f"Error uploading original: {exc}"

    prefix = f"audio/openclaw-edit-{output_path.stem}-{seed}"

    workflow = build_edit_workflow(
        original_audio=uploaded,
        tags=tags,
        lyrics=lyrics,
        filename_prefix=prefix,
        duration=duration,
        bpm=bpm,
        language=language,
        key=key,
        timesig=timesig,
        seed=seed,
        steps=steps,
        cfg=cfg,
        quality=quality,
        denoise=denoise,
        output_format=output_format,
    )

    label = f"{quality}, denoise={denoise}, edit {start_time:.1f}-{end_time:.1f}s"
    print(f"Sending to broker ({label})")

    payload = {"workflow": workflow, "timeout_seconds": timeout_seconds}

    try:
        response = request_json_with_retries(
            "POST", f"{broker_url}/v1/generate",
            payload=payload, timeout=timeout_seconds + 90,
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
    query = urlparse.urlencode({
        "type": primary.get("type", "output"),
        "subfolder": primary.get("subfolder", ""),
        "filename": primary.get("filename", ""),
    })
    download_url = f"{broker_url}/v1/file?{query}"

    # 2. Download the fully-regenerated song to a temp file
    regen_ext = ".flac" if output_format == "flac" else ".mp3"
    temp_regen = output_path.parent / f".regen-{output_path.stem}-{seed}{regen_ext}"
    try:
        download_file(download_url, temp_regen, timeout=max(120, timeout_seconds))
    except Exception as exc:
        return f"Error downloading regenerated audio: {exc}"

    # 3. Splice: take edit region from regenerated, keep rest from original
    try:
        splice_edit_region(
            original_path, temp_regen, output_path,
            start=start_time, end=end_time, crossfade=crossfade,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        return f"ffmpeg splice failed: {stderr}"
    finally:
        temp_regen.unlink(missing_ok=True)

    print(f"Edited song saved: {output_path.resolve()}")
    print(f"Edit region: {start_time:.1f}s – {end_time:.1f}s (denoise={denoise}, crossfade={crossfade}s)")
    print(f"SOURCE_FILENAME: {primary.get('filename')}")
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate songs locally through the ComfyUI broker (ACE Step 1.5)"
    )
    parser.add_argument("--tags", "-t", required=True, help="Genre/style tags (e.g. 'rock, epic, female vocals')")
    parser.add_argument("--filename", "-f", required=True, help="Output filename (e.g. output.mp3)")
    parser.add_argument("--lyrics", "-l", default="", help="Song lyrics (optional)")
    parser.add_argument("--duration", "-d", type=float, default=DEFAULT_DURATION, help=f"Duration in seconds (1-1000, default {DEFAULT_DURATION})")
    parser.add_argument("--bpm", type=int, default=DEFAULT_BPM, help=f"Beats per minute (10-300, default {DEFAULT_BPM})")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, choices=LANGUAGE_OPTIONS, help=f"Language code (default {DEFAULT_LANGUAGE})")
    parser.add_argument("--key", default=DEFAULT_KEY, help=f"Key and scale (e.g. 'E minor', 'C major', default '{DEFAULT_KEY}')")
    parser.add_argument("--timesig", default=DEFAULT_TIMESIG, choices=TIMESIG_OPTIONS, help=f"Time signature (default {DEFAULT_TIMESIG})")
    parser.add_argument("--reference-audio", default=None, help="Reference audio file for style/timbre transfer (wav/mp3/ogg/flac/m4a)")
    parser.add_argument("--quality", choices=["xl-turbo", "xl-merge", "high", "standard"], default="xl-turbo",
                        help="Quality preset: xl-turbo=XL 4B decoder turbo (default, 8 steps), xl-merge=XL SFT+Turbo merge (8 steps, experimental), high=2B split, standard=AIO")
    parser.add_argument("--format", choices=["mp3", "flac"], default="mp3", help="Output audio format: mp3=320kbps lossy (default), flac=lossless")
    parser.add_argument("--count", "-n", type=int, default=1, help="Number of songs to generate in one batch (default 1)")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducibility (random by default)")
    # Edit mode
    parser.add_argument("--edit", default=None, help="Original song to edit (enables edit mode)")
    parser.add_argument("--start", type=float, default=None, help="Edit region start time in seconds")
    parser.add_argument("--end", type=float, default=None, help="Edit region end time in seconds")
    parser.add_argument("--denoise", type=float, default=0.25, help="Edit denoise strength (0=unchanged, 1=full regeneration, default 0.25)")
    parser.add_argument("--crossfade", type=float, default=0.5, help="Crossfade duration at edit boundaries in seconds (default 0.5)")
    parser.add_argument("--steps", type=int, default=None,
                        help="DiT inference steps (turbo: 1-20 default 8, sft: 1-100 default 50)")
    parser.add_argument("--cfg", type=float, default=DEFAULT_CFG, help=argparse.SUPPRESS)
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

    # Validate key
    if args.key not in KEYSCALE_OPTIONS:
        print(f"Invalid key: {args.key}", file=sys.stderr)
        print(f"Valid options: {', '.join(KEYSCALE_OPTIONS[:10])}...", file=sys.stderr)
        return 1

    # Clamp duration and bpm
    duration = max(1.0, min(args.duration, 1000.0))
    bpm = max(10, min(args.bpm, 300))

    # Resolve steps
    if args.steps is not None:
        steps = max(1, min(args.steps, TURBO_MAX_STEPS))
    else:
        steps = DEFAULT_STEPS

    count = max(1, min(args.count, 10))
    seed = args.seed if args.seed is not None else int(time.time() * 1000) % 2147483647
    output_path = Path(args.filename)

    # ---- Edit mode ----
    if args.edit:
        edit_path = Path(args.edit)
        if not edit_path.exists():
            print(f"Original song not found: {edit_path}", file=sys.stderr)
            return 1
        if args.start is None or args.end is None:
            print("--start and --end are required in edit mode", file=sys.stderr)
            return 1
        if args.start >= args.end:
            print("--start must be less than --end", file=sys.stderr)
            return 1
        edit_duration = get_audio_duration(edit_path)
        if args.end > edit_duration:
            print(f"--end ({args.end}) exceeds song duration ({edit_duration:.1f}s)", file=sys.stderr)
            return 1
        denoise = max(0.05, min(args.denoise, 1.0))
        crossfade = max(0.05, min(args.crossfade, 5.0))
        print(f"Mode: Edit | {args.start:.1f}s–{args.end:.1f}s | denoise={denoise} | crossfade={crossfade}s")
        print(f"Original: {edit_path} ({edit_duration:.1f}s)")
        print(f"Steps: {steps} | Seed: {seed}")
        err = edit_song(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            original_path=edit_path,
            tags=args.tags,
            lyrics=args.lyrics,
            output_path=output_path,
            duration=edit_duration,
            bpm=bpm,
            language=args.language,
            key=args.key,
            timesig=args.timesig,
            seed=seed,
            steps=steps,
            cfg=args.cfg,
            quality=args.quality,
            output_format=args.format,
            denoise=denoise,
            start_time=args.start,
            end_time=args.end,
            crossfade=crossfade,
        )
        if err:
            print(err, file=sys.stderr)
            return 1
        return 0

    # Upload reference audio if provided
    uploaded_reference: str | None = None
    if args.reference_audio:
        ref_path = Path(args.reference_audio)
        if not ref_path.exists():
            print(f"Reference audio not found: {ref_path}", file=sys.stderr)
            return 1
        if ref_path.suffix.lower() not in AUDIO_EXTENSIONS:
            print(f"Unsupported audio format: {ref_path.suffix}", file=sys.stderr)
            return 1
        print(f"Uploading reference audio: {ref_path}")
        try:
            uploaded_reference = upload_file(broker_url, ref_path)
            print(f"Uploaded as: {uploaded_reference}")
        except Exception as exc:
            print(f"Error uploading reference audio: {exc}", file=sys.stderr)
            return 1

    mode = f"ACE Step 1.5 ({args.quality})"
    if uploaded_reference:
        mode += " + reference"
    has_lyrics = "with lyrics" if args.lyrics.strip() else "instrumental"
    count_label = f" x{count}" if count > 1 else ""
    print(f"Mode: {mode} | {duration:.0f}s @ {bpm}bpm | {args.key} | {args.language} | {has_lyrics}{count_label}")
    print(f"Steps: {steps} | Seed: {seed}")

    if count == 1:
        err = generate_song(
            broker_url=broker_url,
            timeout_seconds=timeout_seconds,
            tags=args.tags,
            lyrics=args.lyrics,
            output_path=output_path,
            duration=duration,
            bpm=bpm,
            language=args.language,
            key=args.key,
            timesig=args.timesig,
            seed=seed,
            steps=steps,
            cfg=args.cfg,
            quality=args.quality,
            reference_audio=uploaded_reference,
            output_format=args.format,
        )
        if err:
            print(err, file=sys.stderr)
            return 1
        return 0

    # --- Batch mode: generate count songs in parallel threads ---
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
            tags=args.tags,
            lyrics=args.lyrics,
            output_path=song_path,
            duration=duration,
            bpm=bpm,
            language=args.language,
            key=args.key,
            timesig=args.timesig,
            seed=song_seed,
            steps=steps,
            cfg=args.cfg,
            quality=args.quality,
            reference_audio=uploaded_reference,
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
