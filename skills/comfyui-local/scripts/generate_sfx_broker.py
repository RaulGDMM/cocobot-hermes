#!/usr/bin/env python3
"""Broker wrapper for AudioGen sound effects generation.

Runs inside the sandbox container — sends the SFX job to the comfyui-broker's
/v1/gpu-exec endpoint, which handles GPU swap (stop llama → run AudioGen → restart).

No external dependencies — uses only Python stdlib (urllib, json, argparse).

Output files are written to /workspace/ which is shared between the container and WSL.
Paths are auto-translated:
  Container:  /workspace/temp/sfx.wav
  WSL host:   /root/.openclaw/workspace/temp/sfx.wav

Usage:
  python3 {thisfile} --prompt "cat hissing" --filename /workspace/temp/sfx.wav
  python3 {thisfile} --prompt "thunder" --duration 10 --filename /workspace/temp/thunder.wav
  python3 {thisfile} --prompt "footsteps on gravel" "door creaking" \\
      --filename /workspace/temp/steps.wav /workspace/temp/door.wav
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Broker URL — set by openclaw start script as env var, fallback to default
# ---------------------------------------------------------------------------
DEFAULT_BROKER_URL = os.environ.get(
    "OPENCLAW_COMFYUI_LOCAL_BROKER_URL",
    "http://host.docker.internal:8791",
)

# Path mapping: container /workspace/ <-> WSL /root/.openclaw/workspace/
CONTAINER_PREFIX = "/workspace/"
WSL_PREFIX = "/root/.openclaw/workspace/"

# FULL PATH to uv in WSL — required because broker runs wsl non-interactively
# (no .bashrc → /root/.local/bin is NOT in PATH)
UV_PATH = "/root/.local/bin/uv"

# Path to generate_sfx.py on the WSL host
GENERATE_SCRIPT = WSL_PREFIX + "skills/comfyui-local/scripts/generate_sfx.py"


def container_to_wsl(path):
    """Translate a /workspace/... path to the WSL equivalent."""
    if path.startswith(CONTAINER_PREFIX):
        return WSL_PREFIX + path[len(CONTAINER_PREFIX):]
    return path


def wsl_to_container(path):
    """Translate a WSL /root/.openclaw/workspace/... path to container equivalent."""
    if path.startswith(WSL_PREFIX):
        return CONTAINER_PREFIX + path[len(WSL_PREFIX):]
    return path


def build_command(args):
    """Build the uv run command for generate_sfx.py (WSL paths, full uv path)."""
    cmd = [UV_PATH, "run", GENERATE_SCRIPT]

    for prompt in args.prompt:
        cmd += ["--prompt", prompt]

    for filename in args.filename:
        cmd += ["--filename", container_to_wsl(filename)]

    if args.duration:
        cmd += ["--duration", str(args.duration)]
    if args.steps and args.steps != 100:
        cmd += ["--steps", str(args.steps)]
    if args.guidance and args.guidance != 7.0:
        cmd += ["--guidance", str(args.guidance)]
    if args.count and args.count > 1:
        cmd += ["--count", str(args.count)]
    if args.negative_prompt and args.negative_prompt != "Low quality, distorted, noise.":
        cmd += ["--negative-prompt", args.negative_prompt]

    return cmd


def call_broker(broker_url, command, timeout_seconds):
    """POST to /v1/gpu-exec and return the response dict."""
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
        print("Is the broker running? (start-openclaw.ps1)", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate sound effects via broker (Stable Audio Open)"
    )
    parser.add_argument("--prompt", nargs="+", required=True,
                        help="Text description(s) of the sound effect(s)")
    parser.add_argument("--filename", nargs="+", required=True,
                        help="Output .wav path(s) — use /workspace/temp/...")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Duration in seconds (default: 10, max ~47)")
    parser.add_argument("--steps", type=int, default=100,
                        help="Diffusion steps (default: 100)")
    parser.add_argument("--guidance", type=float, default=7.0,
                        help="Guidance scale (default: 7.0)")
    parser.add_argument("--count", type=int, default=1,
                        help="Variations per prompt (files get _001 suffix)")
    parser.add_argument("--negative-prompt", default="Low quality, distorted, noise.",
                        help="Negative prompt to improve quality")

    # Broker
    parser.add_argument("--broker-url", default=DEFAULT_BROKER_URL)
    parser.add_argument("--timeout", type=int, default=300,
                        help="GPU-exec timeout in seconds")

    args = parser.parse_args()

    if len(args.prompt) != len(args.filename):
        print("Error: must provide same number of --prompt and --filename args",
              file=sys.stderr)
        sys.exit(1)

    command = build_command(args)
    print(f"Sending SFX job to broker: {args.broker_url}", file=sys.stderr)
    print(f"Command: {' '.join(command)}", file=sys.stderr)

    result = call_broker(args.broker_url, command, args.timeout)

    exit_code = result.get("exit_code", -1)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    if stderr:
        print(stderr, file=sys.stderr)

    if exit_code != 0:
        print(f"SFX generation failed (exit code {exit_code})", file=sys.stderr)
        if stdout:
            print(stdout, file=sys.stderr)
        sys.exit(1)

    # Print the container-side paths (translate WSL paths back)
    if stdout:
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if line:
                print(wsl_to_container(line))
    else:
        for f in args.filename:
            print(f)


if __name__ == "__main__":
    main()
