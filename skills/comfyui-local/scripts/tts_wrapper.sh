#!/bin/bash
# Wrapper script for TTS generation via broker
# This runs on the WSL host where uv should be available

# Try to find uv in common locations
if command -v uv &> /dev/null; then
    UV_PATH=$(command -v uv)
elif [ -f "/usr/local/bin/uv" ]; then
    UV_PATH="/usr/local/bin/uv"
elif [ -f "$HOME/.local/bin/uv" ]; then
    UV_PATH="$HOME/.local/bin/uv"
elif [ -f "/usr/bin/uv" ]; then
    UV_PATH="/usr/bin/uv"
else
    echo "Error: uv not found in PATH or common locations" >&2
    echo "Searched: PATH, /usr/local/bin, $HOME/.local/bin, /usr/bin" >&2
    exit 1
fi

echo "Using uv from: $UV_PATH" >&2

# Run the TTS script
exec "$UV_PATH" run /root/.openclaw/workspace/skills/comfyui-local/scripts/generate_speech.py "$@"
