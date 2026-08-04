#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "diffusers[torch]>=0.32",
#     "transformers>=4.39",
#     "accelerate",
#     "soundfile",
#     "sentencepiece",
#     "protobuf",
#     "torchsde",
# ]
# ///
"""Generate sound effects from text descriptions using Stable Audio Open 1.0.

Model: stabilityai/stable-audio-open-1.0 (1.2B params).
Output: 44.1 kHz stereo WAV (high quality).
Max duration: ~47 seconds.
VRAM: ~4 GB (FP16).
Auto-downloads on first run (~5 GB from HuggingFace).

Usage:
  uv run generate_sfx.py --prompt "cat hissing aggressively" --filename /workspace/temp/sfx.wav
  uv run generate_sfx.py --prompt "thunder rolling" --duration 10 --filename /workspace/temp/thunder.wav
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Persistent cache dirs — survive container rebuilds
# ---------------------------------------------------------------------------
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", "/workspace"))
CACHE_BASE = WORKSPACE / ".cache"

os.environ.setdefault("UV_CACHE_DIR", str(CACHE_BASE / "uv"))
os.environ.setdefault("HF_HOME", str(CACHE_BASE / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(CACHE_BASE / "huggingface" / "hub"))
os.environ.setdefault("OMP_NUM_THREADS", "4")

# Ensure HF token is available (uv run isolates env, so read from standard location)
_token_path = Path.home() / ".cache" / "huggingface" / "token"
if not os.environ.get("HF_TOKEN") and _token_path.is_file():
    os.environ["HF_TOKEN"] = _token_path.read_text().strip()

MODEL_ID = "stabilityai/stable-audio-open-1.0"


def detect_device() -> str:
    """Pick CUDA if available with enough VRAM, else CPU."""
    try:
        import torch
        if torch.cuda.is_available():
            free_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)
            if free_gb >= 3.0:
                return "cuda"
            print(f"Only {free_gb:.1f} GB VRAM free, falling back to CPU", file=sys.stderr)
    except Exception:
        pass
    return "cpu"


def generate(prompts, duration, device, output_paths,
             steps=100, guidance=7.0, count=1,
             negative_prompt="Low quality, distorted, noise."):
    """Generate audio for each prompt and save to corresponding output path."""
    import torch
    import soundfile as sf
    from diffusers import StableAudioPipeline

    dtype = torch.float16 if device == "cuda" else torch.float32

    print(f"Loading Stable Audio Open ({MODEL_ID}) on {device} ({dtype})...", file=sys.stderr)
    t0 = time.time()
    pipe = StableAudioPipeline.from_pretrained(MODEL_ID, torch_dtype=dtype)
    pipe = pipe.to(device)
    sample_rate = pipe.vae.sampling_rate  # 44100
    print(f"Model loaded in {time.time() - t0:.1f}s (sample rate: {sample_rate} Hz)", file=sys.stderr)

    for i, (prompt, out_path) in enumerate(zip(prompts, output_paths)):
        n = count if count > 1 else 1
        label = f" x{n}" if n > 1 else ""
        print(f"[{i+1}/{len(prompts)}] Generating: \"{prompt}\" ({duration}s{label})...", file=sys.stderr)

        generator = torch.Generator(device=device).manual_seed(int(time.time()) + i)
        t0 = time.time()
        result = pipe(
            prompt,
            negative_prompt=negative_prompt,
            audio_end_in_s=duration,
            num_inference_steps=steps,
            guidance_scale=guidance,
            num_waveforms_per_prompt=n,
            generator=generator,
        )
        elapsed = time.time() - t0
        print(f"  Generated {n} variation(s) in {elapsed:.1f}s", file=sys.stderr)

        for j, audio_tensor in enumerate(result.audios):
            if n > 1:
                stem = out_path.stem
                dest = out_path.with_name(f"{stem}_{j+1:03d}{out_path.suffix}")
            else:
                dest = out_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            # audio_tensor shape: (channels, samples) — transpose to (samples, channels)
            audio_np = audio_tensor.T.float().cpu().numpy()
            sf.write(str(dest), audio_np, sample_rate)
            duration_s = audio_np.shape[0] / sample_rate
            print(f"  Saved: {dest} ({duration_s:.1f}s, {sample_rate}Hz stereo)", file=sys.stderr)
            print(str(dest))


def main():
    parser = argparse.ArgumentParser(description="Generate sound effects with Stable Audio Open")
    parser.add_argument("--prompt", nargs="+", required=True,
                        help="Text description(s) of the sound effect(s)")
    parser.add_argument("--filename", nargs="+", required=True,
                        help="Output .wav path(s) — one per prompt")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Duration in seconds (default: 10, max ~47)")
    parser.add_argument("--device", default=None,
                        help="Force device (cuda/cpu). Auto-detects by default.")
    parser.add_argument("--steps", type=int, default=100,
                        help="Diffusion steps (default: 100, lower=faster)")
    parser.add_argument("--guidance", type=float, default=7.0,
                        help="Classifier-free guidance scale (default: 7.0)")
    parser.add_argument("--count", type=int, default=1,
                        help="Variations per prompt (default: 1). Files get _001 suffix.")
    parser.add_argument("--negative-prompt", default="Low quality, distorted, noise.",
                        help="Negative prompt to improve quality")
    args = parser.parse_args()

    if len(args.prompt) != len(args.filename):
        print("Error: must provide same number of --prompt and --filename args", file=sys.stderr)
        sys.exit(1)

    if args.duration > 47:
        print("Warning: Stable Audio Open max is ~47s, clamping", file=sys.stderr)
        args.duration = 47.0

    device = args.device or detect_device()
    output_paths = [Path(f) for f in args.filename]

    generate(args.prompt, args.duration, device, output_paths,
             steps=args.steps, guidance=args.guidance, count=args.count,
             negative_prompt=args.negative_prompt)


if __name__ == "__main__":
    main()
