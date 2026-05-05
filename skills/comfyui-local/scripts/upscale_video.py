#!/usr/bin/env python3
"""Video upscaler using Real-ESRGAN anime model (frame-by-frame Python API).

Uses RealESRGAN_x4plus_anime_6B model via the realesrgan Python package.
Requires torch>=2.6 for RTX 5090 (sm_120) support.

Usage (via uv):
  uv run --with "torch>=2.6,realesrgan,basicsr,opencv-python,numpy,facexlib,torchvision" \
    python3 upscale_video.py --input video.mp4 --output video_4k.mp4 --scale 4
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import urllib.request

# ---------------------------------------------------------------------------
# Monkey-patch: basicsr references torchvision.transforms.functional_tensor
# which was removed in modern torchvision. Must run BEFORE importing basicsr.
# ---------------------------------------------------------------------------
def _patch_torchvision_functional_tensor():
    """Create a shim module so basicsr's import doesn't fail."""
    if "torchvision.transforms.functional_tensor" in sys.modules:
        return
    try:
        import torchvision.transforms.functional as F
        fake = types.ModuleType("torchvision.transforms.functional_tensor")
        fake.__dict__.update({k: v for k, v in F.__dict__.items()})
        sys.modules["torchvision.transforms.functional_tensor"] = fake
    except ImportError:
        pass

_patch_torchvision_functional_tensor()
# ---------------------------------------------------------------------------


def run_cmd(cmd, timeout=600):
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    print(f"[CMD] {cmd_str}", file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def install_deps():
    """Verify deps are importable (assumes uv provides them)."""
    try:
        from basicsr.archs.rrdbnet_arch import RRDBNet  # noqa: F401
        from realesrgan import RealESRGANer  # noqa: F401
        import cv2  # noqa: F401
        import torch  # noqa: F401
        print(f"[INFO] All deps OK (torch={torch.__version__}, cuda={torch.version.cuda})", file=sys.stderr)
        return True
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}", file=sys.stderr)
        print("[HINT] Run via: uv run --with 'torch>=2.6,realesrgan,basicsr,opencv-python,numpy,facexlib,torchvision' python3 upscale_video.py ...", file=sys.stderr)
        return False


def download_model(model_dir):
    """Download RealESRGAN_x4plus_anime_6B.pth if not present."""
    model_name = "RealESRGAN_x4plus_anime_6B.pth"
    model_path = os.path.join(model_dir, model_name)

    if os.path.exists(model_path):
        print(f"[INFO] Model found: {model_path}", file=sys.stderr)
        return model_path

    urls = [
        f"https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/{model_name}",
        f"https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/{model_name}",
    ]

    for url in urls:
        try:
            print(f"[INFO] Downloading model from {url}...", file=sys.stderr)
            os.makedirs(model_dir, exist_ok=True)
            urllib.request.urlretrieve(url, model_path)
            if os.path.exists(model_path) and os.path.getsize(model_path) > 10_000_000:
                print(f"[INFO] Model downloaded: {os.path.getsize(model_path)/1024/1024:.1f} MB", file=sys.stderr)
                return model_path
            os.remove(model_path)
        except Exception as e:
            print(f"[WARN] Download failed from {url}: {e}", file=sys.stderr)

    raise RuntimeError("Failed to download model from any URL")


def upscale_frames(model_path, frame_dir, output_dir, scale=4, tile=512):
    """Upscale all frames using Real-ESRGAN Python API."""
    import cv2
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    # RealESRGAN_x4plus_anime_6B architecture: 6 blocks, 64 features
    model = RRDBNet(
        num_in_ch=3, num_out_ch=3, num_feat=64,
        num_block=6, num_grow_ch=32, scale=4,
    )

    half = torch.cuda.is_available()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    upsampler = RealESRGANer(
        scale=4,
        model_path=model_path,
        model=model,
        tile=tile,
        tile_pad=10,
        pre_pad=0,
        half=half,
        device=device,
    )

    frames = sorted(glob.glob(os.path.join(frame_dir, "frame_*.png")))
    total = len(frames)
    os.makedirs(output_dir, exist_ok=True)

    print(f"[INFO] Upscaling {total} frames (tile={tile}, half={half}, device={device})...", file=sys.stderr)

    for i, fpath in enumerate(frames):
        # Skip already-processed frames (resume support)
        basename = os.path.basename(fpath)
        out_path = os.path.join(output_dir, basename)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            if (i + 1) % 100 == 0:
                print(f"[INFO] Skipping frame {i+1}/{total} (already done)", file=sys.stderr)
            continue

        img = cv2.imread(fpath, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"[WARN] Could not read frame: {fpath}", file=sys.stderr)
            continue

        try:
            output, _ = upsampler.enhance(img, outscale=scale)
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                # Retry with smaller tile
                new_tile = max(upsampler.tile // 2, 128) if upsampler.tile > 0 else 256
                print(f"[WARN] OOM on frame {i+1}, retrying with tile={new_tile}...", file=sys.stderr)
                torch.cuda.empty_cache()
                upsampler.tile = new_tile
                output, _ = upsampler.enhance(img, outscale=scale)
            else:
                raise

        basename = os.path.basename(fpath)
        out_path = os.path.join(output_dir, basename)
        cv2.imwrite(out_path, output)

        if (i + 1) % 50 == 0 or i == total - 1:
            print(f"[PROGRESS] Frame {i+1}/{total}", file=sys.stderr)

    upscaled = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
    print(f"[INFO] Upscaled {len(upscaled)}/{total} frames", file=sys.stderr)


def extract_frames(video_path, frame_dir):
    os.makedirs(frame_dir, exist_ok=True)
    rc, _, err = run_cmd(
        ["ffmpeg", "-y", "-i", video_path, f"{frame_dir}/frame_%06d.png"],
        timeout=300,
    )
    if rc != 0:
        print(f"[ERROR] Frame extraction failed: {err[-300:]}", file=sys.stderr)
        sys.exit(1)
    frames = sorted(glob.glob(os.path.join(frame_dir, "frame_*.png")))
    print(f"[INFO] Extracted {len(frames)} frames", file=sys.stderr)
    return len(frames)


def get_video_info(video_path):
    r = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height",
        "-show_entries", "format=duration",
        "-of", "json", video_path
    ], capture_output=True, text=True)
    info = json.loads(r.stdout)
    stream = info.get("streams", [{}])[0]
    fps_str = stream.get("r_frame_rate", "24/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den) if float(den) else float(num)
    return fps, int(stream.get("width", 0)), int(stream.get("height", 0))


def reassemble(frame_dir, output_path, audio_path, fps):
    has_audio = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(round(fps, 3)),
        "-i", os.path.join(frame_dir, "frame_%06d.png"),
    ]
    if has_audio:
        cmd += ["-i", audio_path]

    cmd += [
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-map", "0:v", "-map", "1:a"]

    cmd += ["-movflags", "+faststart", output_path]

    rc, _, err = run_cmd(cmd, timeout=600)
    if rc != 0:
        print(f"[ERROR] Video reassembly failed: {err[-300:]}", file=sys.stderr)
        sys.exit(1)

    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration,size",
        "-of", "json", output_path
    ], capture_output=True, text=True)
    info = json.loads(r.stdout)
    w = info.get("streams", [{}])[0].get("width", "?")
    h = info.get("streams", [{}])[0].get("height", "?")
    dur = float(info["format"]["duration"])
    sz = int(float(info["format"]["size"])) / 1024 / 1024
    print(f"[INFO] Output: {w}x{h}, {dur:.1f}s, {sz:.0f} MB", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Real-ESRGAN Anime Video Upscaler")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scale", type=int, default=4, choices=[2, 4])
    parser.add_argument("--tile", type=int, default=512,
                        help="Tile size for processing (lower = less VRAM, 0 = no tiling)")
    parser.add_argument("--tmp-dir", default=None)
    args = parser.parse_args()

    inp = os.path.abspath(args.input)
    out = os.path.abspath(args.output)

    if not os.path.exists(inp):
        print(f"[ERROR] Not found: {inp}", file=sys.stderr)
        sys.exit(1)

    tmp_base = args.tmp_dir or tempfile.mkdtemp(prefix="upscale_")
    frame_dir = os.path.join(tmp_base, "frames")
    upscaled_dir = os.path.join(tmp_base, "upscaled")
    audio_file = os.path.join(tmp_base, "audio.aac")
    model_dir = os.path.join(tmp_base, "model")

    # Persistent model dir — avoids re-downloading every run
    PERSISTENT_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "RealESRGAN_x4plus_anime_6B.pth")
    PERSISTENT_MODEL = os.path.normpath(PERSISTENT_MODEL)
    if not os.path.exists(PERSISTENT_MODEL):
        # Fallback: project-level models dir
        PERSISTENT_MODEL = os.path.join(os.getcwd(), "models", "RealESRGAN_x4plus_anime_6B.pth")

    fps, w, h = get_video_info(inp)
    print(f"{'=' * 60}", file=sys.stderr)
    print(f"Real-ESRGAN Anime Upscaler (Python API)", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(f"In:  {inp} ({w}x{h})", file=sys.stderr)
    print(f"Out: {out} ({w*args.scale}x{h*args.scale})", file=sys.stderr)
    print(f"FPS: {fps:.1f}, Scale: {args.scale}x, Tile: {args.tile}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    print("\n[STEP 1] Extracting frames...", file=sys.stderr)
    extract_frames(inp, frame_dir)

    print("\n[STEP 2] Extracting audio...", file=sys.stderr)
    run_cmd(["ffmpeg", "-y", "-i", inp, "-vn", "-c:a", "aac", "-b:a", "192k", audio_file])

    print("\n[STEP 3] Checking deps...", file=sys.stderr)
    if not install_deps():
        sys.exit(1)

    print("\n[STEP 4] Loading model...", file=sys.stderr)
    if os.path.exists(PERSISTENT_MODEL):
        model_path = PERSISTENT_MODEL
        print(f"[INFO] Using persistent model: {model_path}", file=sys.stderr)
    else:
        model_path = download_model(model_dir)

    print("\n[STEP 5] Upscaling...", file=sys.stderr)
    upscale_frames(model_path, frame_dir, upscaled_dir, scale=args.scale, tile=args.tile)

    print("\n[STEP 6] Reassembling...", file=sys.stderr)
    reassemble(upscaled_dir, out, audio_file, fps)

    shutil.rmtree(tmp_base, ignore_errors=True)
    print(f"\n[DONE] {out}", file=sys.stderr)
    print(out)


if __name__ == "__main__":
    main()
