#!/usr/bin/env python3
"""Broker wrapper for Real-ESRGAN video upscaling.

Sends the upscale job to the comfyui-broker's /v1/gpu-exec endpoint,
which handles GPU swap (stop llama -> run upscaling -> restart).

No external dependencies — uses only Python stdlib (urllib, json, argparse).

Usage:
  python3 upscale_video_broker.py --input /workspace/video.mp4 \
                                  --output /workspace/video_4k.mp4 --scale 4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Broker URL
# ---------------------------------------------------------------------------
DEFAULT_BROKER_URL = os.environ.get(
    "OPENCLAW_COMFYUI_LOCAL_BROKER_URL",
    "http://host.docker.internal:8791",
)

# Path mapping: container /workspace/ <-> WSL /root/.hermes/workspace/
CONTAINER_PREFIX = "/workspace/"
WSL_PREFIX = "/root/.hermes/workspace/"

# Use a pre-built venv to guarantee torch>=2.6 (RTX 5090 sm_120 support).
# uv --with resolves basicsr deps to torch 2.4.1+cu121 which is incompatible.
VENV_DIR = "/root/workspace/biblia-gato-video/upscale_env"
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")

# Path to upscale_video.py on the WSL host
UPSCALE_SCRIPT = "/root/.hermes/skills/media/comfyui-local/scripts/upscale_video.py"


def ensure_venv():
    """Create venv with correct deps if it doesn't exist."""
    if os.path.exists(VENV_PYTHON):
        print(f"[INFO] Using existing venv: {VENV_PYTHON}", file=sys.stderr)
        return
    print(f"[INFO] Creating venv with torch>=2.6 at {VENV_DIR}...", file=sys.stderr)
    r = subprocess.run(
        ["/root/.local/bin/uv", "venv", VENV_DIR],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[ERROR] uv venv failed: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    r = subprocess.run(
        [VENV_PYTHON, "-m", "pip", "install", "-U",
         "torch>=2.6", "realesrgan", "basicsr", "opencv-python",
         "numpy", "facexlib", "torchvision"],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        print(f"[ERROR] pip install failed: {r.stderr[-500:]}", file=sys.stderr)
        sys.exit(1)
    print("[INFO] venv ready", file=sys.stderr)


def container_to_wsl(path):
    if path.startswith(CONTAINER_PREFIX):
        return WSL_PREFIX + path[len(CONTAINER_PREFIX):]
    return path


def wsl_to_container(path):
    if path.startswith(WSL_PREFIX):
        return CONTAINER_PREFIX + path[len(WSL_PREFIX):]
    return path


def build_command(args):
    cmd = [VENV_PYTHON, UPSCALE_SCRIPT]
    cmd += ["--input", container_to_wsl(args.input)]
    cmd += ["--output", container_to_wsl(args.output)]
    cmd += ["--scale", str(args.scale)]
    if args.tile:
        cmd += ["--tile", str(args.tile)]
    if args.tmp_dir:
        cmd += ["--tmp-dir", container_to_wsl(args.tmp_dir)]
    return cmd


def call_broker(broker_url, command, timeout_seconds):
    url = f"{broker_url}/v1/gpu-exec"
    payload = json.dumps({
        "command": command,
        "timeout_seconds": timeout_seconds,
        "wsl": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds + 60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Broker HTTP error {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Cannot reach broker at {url}: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AI Video Upscaler via broker (Real-ESRGAN)")
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--output", required=True, help="Output video path")
    parser.add_argument("--scale", type=int, default=4, choices=[2, 4], help="Upscale factor")
    parser.add_argument("--tile", type=int, default=512, help="Tile size (lower = less VRAM)")
    parser.add_argument("--tmp-dir", default=None, help="Temp directory for frames")
    parser.add_argument("--broker-url", default=DEFAULT_BROKER_URL)
    parser.add_argument("--timeout", type=int, default=3600, help="GPU-exec timeout (default 1h)")

    args = parser.parse_args()

    ensure_venv()

    command = build_command(args)
    print(f"Sending upscale job to broker: {args.broker_url}", file=sys.stderr)
    print(f"Command: {' '.join(command)}", file=sys.stderr)
    print(f"Timeout: {args.timeout}s", file=sys.stderr)

    result = call_broker(args.broker_url, command, args.timeout)

    exit_code = result.get("exit_code", -1)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    if stderr:
        print(stderr, file=sys.stderr)

    if exit_code != 0:
        print(f"Upscaling failed (exit code {exit_code})", file=sys.stderr)
        if stdout:
            print(stdout, file=sys.stderr)
        sys.exit(1)

    if stdout:
        wsl_path = stdout.strip().split("\n")[-1]
        print(wsl_to_container(wsl_path))
    else:
        print(args.output)


if __name__ == "__main__":
    main()
