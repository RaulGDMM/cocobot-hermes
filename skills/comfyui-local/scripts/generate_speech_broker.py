#!/usr/bin/env python3
"""Broker wrapper for Qwen3-TTS speech generation.

Runs inside the sandbox container — sends the TTS job to the comfyui-broker's
/v1/gpu-exec endpoint, which handles GPU swap (stop llama → run TTS → restart).

No external dependencies — uses only Python stdlib (urllib, json, argparse).

IMPORTANT: Output files are written to /workspace/ which is shared between the
container and WSL. Paths are auto-translated:
  Container:  /workspace/temp/out.wav
  WSL host:   /root/.openclaw/workspace/temp/out.wav

Usage (Cocobot voice):
  python3 {thisfile} --text "¡Miau! Hola Raúl" --filename /workspace/temp/cocobot.wav

Usage (voice clone):
  python3 {thisfile} --text "Hello" --ref-audio /workspace/skills/comfyui-local/scripts/assets/ref.wav \
      --ref-text "transcript" --filename /workspace/temp/clone.wav

Usage (custom speaker):
  python3 {thisfile} --text "Hello" --speaker vivian \
      --instruct "Speak warmly" --filename /workspace/temp/custom.wav

Usage (voice design):
  python3 {thisfile} --text "Hello" --design "Young cheerful male" \
      --filename /workspace/temp/designed.wav
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

# Path to generate_speech.py on the WSL host
GENERATE_SCRIPT = WSL_PREFIX + "skills/comfyui-local/scripts/generate_speech.py"


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


# Dummy suffix to prevent Qwen3-TTS from cutting the last syllable.
# Confirmed fix: https://github.com/QwenLM/Qwen3-TTS/discussions/161
# The model doesn't read these symbols, but the extra tokens give it
# enough time to complete the final phoneme properly.
TTS_TRAILING_DUMMY = " ... ^.◦"


def build_command(args):
    """Build the uv run command for generate_speech.py (WSL paths, full uv path)."""
    # Append dummy symbols to prevent last-syllable truncation
    text = args.text.rstrip() + TTS_TRAILING_DUMMY
    cmd = [UV_PATH, "run", GENERATE_SCRIPT]
    cmd += ["--text", text]
    cmd += ["--filename", container_to_wsl(args.filename)]

    if args.ref_audio:
        cmd += ["--ref-audio", container_to_wsl(args.ref_audio)]
    if args.ref_text:
        cmd += ["--ref-text", args.ref_text]
    if args.speaker:
        cmd += ["--speaker", args.speaker]
    if args.instruct:
        cmd += ["--instruct", args.instruct]
    if args.design:
        cmd += ["--design", args.design]
    if args.language:
        cmd += ["--language", args.language]
    if args.fast:
        cmd += ["--fast"]
    if args.max_duration:
        cmd += ["--max-duration", str(args.max_duration)]
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
        description="Generate speech via broker (Qwen3-TTS)"
    )
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--filename", required=True,
                        help="Output .wav path (use /workspace/temp/...)")
    parser.add_argument("--language", default=None)
    parser.add_argument("--fast", action="store_true", help="Use 0.6B model")
    parser.add_argument("--max-duration", type=int, default=300)

    # Voice clone
    parser.add_argument("--ref-audio", default=None)
    parser.add_argument("--ref-text", default=None)

    # Custom voice
    parser.add_argument("--speaker", default=None)
    parser.add_argument("--instruct", default=None)

    # Voice design
    parser.add_argument("--design", default=None)

    # Broker
    parser.add_argument("--broker-url", default=DEFAULT_BROKER_URL)
    parser.add_argument("--timeout", type=int, default=900,
                        help="GPU-exec timeout in seconds")

    args = parser.parse_args()

    command = build_command(args)
    print(f"Sending TTS job to broker: {args.broker_url}", file=sys.stderr)
    print(f"Command: {' '.join(command)}", file=sys.stderr)

    result = call_broker(args.broker_url, command, args.timeout)

    exit_code = result.get("exit_code", -1)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    if stderr:
        print(stderr, file=sys.stderr)

    if exit_code != 0:
        print(f"TTS failed (exit code {exit_code})", file=sys.stderr)
        if stdout:
            print(stdout, file=sys.stderr)
        sys.exit(1)

    # Print the container-side path (translate WSL path back if needed)
    if stdout:
        wsl_path = stdout.strip().split("\n")[-1]
        print(wsl_to_container(wsl_path))
    else:
        print(args.filename)


if __name__ == "__main__":
    main()
