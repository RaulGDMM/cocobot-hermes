#!/usr/bin/env python3
"""Fast video upscaler using realesrgan-ncnn-vulkan via broker.

Uses the native Windows ncnn-vulkan binary (Vulkan GPU compute) which is
10-20x faster than the Python Real-ESRGAN approach.

Flow:
  1. Extract frames from video (ffmpeg, local)
  2. Send ncnn-vulkan upscale command to broker (stops llama, runs GPU job)
  3. Reassemble upscaled frames into video (ffmpeg, local)

No external Python dependencies — uses only stdlib.

Usage:
  python3 upscale_video_ncnn_broker.py --input /path/video.mp4 \
                                       --output /path/video_4k.mp4 --scale 4
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_BROKER_URL = os.environ.get(
    "OPENCLAW_COMFYUI_LOCAL_BROKER_URL",
    "http://host.docker.internal:8791",
)

# ncnn-vulkan binary location (Windows path)
NCNN_DIR_WIN = r"E:\Workspace\Openclaw\realesrgan-ncnn-vulkan"
NCNN_EXE_WIN = os.path.join(NCNN_DIR_WIN, "realesrgan-ncnn-vulkan.exe")
NCNN_MODELS_WIN = os.path.join(NCNN_DIR_WIN, "models")

# Working directory on Windows filesystem for fast I/O
WIN_WORK_BASE = r"E:\tmp_upscale"
WSL_WORK_BASE = "/mnt/e/tmp_upscale"

# Path mapping for container paths
CONTAINER_PREFIX = "/workspace/"
WSL_PREFIX = "/root/.hermes/workspace/"


def container_to_wsl(path: str) -> str:
    if path.startswith(CONTAINER_PREFIX):
        return WSL_PREFIX + path[len(CONTAINER_PREFIX):]
    return path


def wsl_to_container(path: str) -> str:
    if path.startswith(WSL_PREFIX):
        return CONTAINER_PREFIX + path[len(WSL_PREFIX):]
    return path


def wsl_to_win(path: str) -> str:
    """Convert WSL path under /mnt/X/ to Windows path."""
    if path.startswith("/mnt/") and len(path) > 6 and path[5].isalpha() and path[6] == "/":
        drive = path[5].upper()
        return f"{drive}:\\" + path[7:].replace("/", "\\")
    return "\\\\wsl.localhost\\Ubuntu" + path.replace("/", "\\")


def run_cmd(cmd, desc="", timeout=600):
    """Run a local command with output."""
    if desc:
        print(f"[INFO] {desc}", file=sys.stderr)
    print(f"  $ {' '.join(cmd[:6])}{'...' if len(cmd) > 6 else ''}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"[ERROR] Command failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr[-1000:], file=sys.stderr)
        sys.exit(1)
    return result


def extract_frames(input_video, frames_dir):
    """Extract all frames from video. Returns (frame_count, fps)."""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", input_video],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    fps = 24.0
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            r_fps = stream.get("r_frame_rate", "24/1")
            num, den = r_fps.split("/")
            fps = float(num) / float(den)
            break

    os.makedirs(frames_dir, exist_ok=True)

    existing = [f for f in os.listdir(frames_dir) if f.endswith(".png")]
    if existing:
        print(f"[INFO] Found {len(existing)} existing frames in {frames_dir}", file=sys.stderr)
        return len(existing), fps

    run_cmd(
        ["ffmpeg", "-i", input_video, "-vsync", "0",
         os.path.join(frames_dir, "frame_%08d.png")],
        desc=f"Extracting frames from {os.path.basename(input_video)}",
        timeout=300,
    )

    frame_count = len([f for f in os.listdir(frames_dir) if f.endswith(".png")])
    print(f"[INFO] Extracted {frame_count} frames @ {fps:.2f} fps", file=sys.stderr)
    return frame_count, fps


def extract_audio(input_video, audio_file):
    """Extract audio track. Returns True if audio exists."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a",
         "-show_entries", "stream=codec_type", input_video],
        capture_output=True, text=True,
    )
    if "audio" not in result.stdout:
        return False

    if os.path.exists(audio_file):
        print(f"[INFO] Audio already extracted: {audio_file}", file=sys.stderr)
        return True

    run_cmd(
        ["ffmpeg", "-i", input_video, "-vn", "-acodec", "copy", audio_file],
        desc="Extracting audio",
    )
    return True


def call_broker(broker_url, command, timeout_seconds, wsl=False):
    """Send command to broker's /v1/gpu-exec endpoint."""
    url = f"{broker_url}/v1/gpu-exec"
    payload = json.dumps({
        "command": command,
        "timeout_seconds": timeout_seconds,
        "wsl": wsl,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds + 120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[ERROR] Broker HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"[ERROR] Cannot reach broker at {url}: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def upscale_via_broker(
    frames_dir_wsl,
    upscaled_dir_wsl,
    scale,
    model,
    threads,
    broker_url,
    timeout,
    output_format="png",
):
    """Call broker to run ncnn-vulkan on frames directory."""
    frames_win = wsl_to_win(frames_dir_wsl)
    upscaled_win = wsl_to_win(upscaled_dir_wsl)

    os.makedirs(upscaled_dir_wsl, exist_ok=True)

    existing = [f for f in os.listdir(upscaled_dir_wsl) if f.endswith(f".{output_format}")]
    total_input = len([f for f in os.listdir(frames_dir_wsl) if f.endswith(".png")])
    if existing and len(existing) >= total_input:
        print(f"[INFO] All {len(existing)} frames already upscaled, skipping GPU job", file=sys.stderr)
        return

    command = [
        NCNN_EXE_WIN,
        "-i", frames_win,
        "-o", upscaled_win,
        "-s", str(scale),
        "-n", model,
        "-m", NCNN_MODELS_WIN,
        "-j", threads,
        "-f", output_format,
    ]

    print(f"[INFO] Sending ncnn upscale job to broker ({total_input} frames, scale={scale}x)", file=sys.stderr)
    print(f"  Input:  {frames_win}", file=sys.stderr)
    print(f"  Output: {upscaled_win}", file=sys.stderr)
    print(f"  Model:  {model}", file=sys.stderr)

    t0 = time.time()
    result = call_broker(broker_url, command, timeout, wsl=False)
    elapsed = time.time() - t0

    exit_code = result.get("exit_code", -1)
    stderr = result.get("stderr", "")

    if stderr:
        lines = stderr.strip().split("\n")
        for line in lines[-10:]:
            print(f"  [ncnn] {line}", file=sys.stderr)

    if exit_code != 0:
        print(f"[ERROR] ncnn-vulkan failed (exit {exit_code})", file=sys.stderr)
        stdout = result.get("stdout", "")
        if stdout:
            print(stdout[-500:], file=sys.stderr)
        sys.exit(1)

    upscaled_count = len([f for f in os.listdir(upscaled_dir_wsl) if f.endswith(f".{output_format}")])
    fps = upscaled_count / elapsed if elapsed > 0 else 0
    print(f"[INFO] Upscaled {upscaled_count} frames in {elapsed:.1f}s ({fps:.1f} fps)", file=sys.stderr)


def reassemble_video(
    upscaled_dir,
    output_video,
    fps,
    audio_file=None,
    output_format="png",
):
    """Reassemble upscaled frames into video with audio."""
    input_pattern = os.path.join(upscaled_dir, f"frame_%08d.{output_format}")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", input_pattern,
    ]
    if audio_file and os.path.exists(audio_file):
        cmd += ["-i", audio_file, "-c:a", "aac", "-b:a", "192k"]

    cmd += [
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if audio_file and os.path.exists(audio_file):
        cmd += ["-shortest"]

    cmd.append(output_video)

    run_cmd(cmd, desc=f"Encoding output video: {os.path.basename(output_video)}", timeout=600)

    size_mb = os.path.getsize(output_video) / (1024 * 1024)
    print(f"[INFO] Output: {output_video} ({size_mb:.1f} MB)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Fast video upscaler (ncnn-vulkan via broker)")
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--output", required=True, help="Output video path")
    parser.add_argument("--scale", type=int, default=4, choices=[2, 3, 4],
                        help="Upscale factor (default: 4)")
    parser.add_argument("--model", default="realesr-animevideov3",
                        help="Model name (default: realesr-animevideov3)")
    parser.add_argument("--threads", default="2:4:4",
                        help="load:proc:save threads (default: 2:4:4)")
    parser.add_argument("--format", default="png", choices=["png", "jpg", "webp"],
                        help="Intermediate frame format (default: png)")
    parser.add_argument("--work-dir", default=None,
                        help="Working directory (default: auto on E: drive)")
    parser.add_argument("--keep-frames", action="store_true",
                        help="Don't delete frame directories after completion")
    parser.add_argument("--broker-url", default=DEFAULT_BROKER_URL)
    parser.add_argument("--timeout", type=int, default=7200,
                        help="GPU-exec timeout in seconds (default: 2h)")
    args = parser.parse_args()

    input_video = container_to_wsl(args.input)
    output_video = container_to_wsl(args.output)

    if not os.path.isfile(input_video):
        print(f"[ERROR] Input not found: {input_video}", file=sys.stderr)
        sys.exit(1)

    if args.work_dir:
        work_dir = container_to_wsl(args.work_dir)
    else:
        os.makedirs(WSL_WORK_BASE, exist_ok=True)
        work_dir = tempfile.mkdtemp(dir=WSL_WORK_BASE)

    frames_dir = os.path.join(work_dir, "frames")
    upscaled_dir = os.path.join(work_dir, "upscaled")
    audio_file = os.path.join(work_dir, "audio.aac")

    print(f"[INFO] Input:  {input_video}", file=sys.stderr)
    print(f"[INFO] Output: {output_video}", file=sys.stderr)
    print(f"[INFO] Work:   {work_dir}", file=sys.stderr)
    print(f"[INFO] Scale:  {args.scale}x  Model: {args.model}", file=sys.stderr)

    t_start = time.time()

    frame_count, fps = extract_frames(input_video, frames_dir)
    has_audio = extract_audio(input_video, audio_file)

    upscale_via_broker(
        frames_dir_wsl=frames_dir,
        upscaled_dir_wsl=upscaled_dir,
        scale=args.scale,
        model=args.model,
        threads=args.threads,
        broker_url=args.broker_url,
        timeout=args.timeout,
        output_format=args.format,
    )

    os.makedirs(os.path.dirname(output_video), exist_ok=True)
    reassemble_video(
        upscaled_dir=upscaled_dir,
        output_video=output_video,
        fps=fps,
        audio_file=audio_file if has_audio else None,
        output_format=args.format,
    )

    total_time = time.time() - t_start
    print(f"[INFO] Total time: {total_time:.0f}s ({total_time/60:.1f} min)", file=sys.stderr)
    print(f"[INFO] Average: {frame_count/total_time:.1f} fps overall", file=sys.stderr)

    if not args.keep_frames:
        print(f"[INFO] Cleaning up work directory: {work_dir}", file=sys.stderr)
        shutil.rmtree(work_dir, ignore_errors=True)

    # Print output path (for piping)
    print(wsl_to_container(output_video))


if __name__ == "__main__":
    main()
