#!/bin/bash
# Batch LTX 2.3 i2v clip generation for a music video.
# Edit the generate_clip calls with your images + motion prompts, then: bash generate-all-clips.sh
# Run via Hermes terminal with background=true + notify=true (~2-3 min per clip).

BASE="<EDIT: path to your project folder>"
IMAGES="$BASE/imagenes"
VIDEOS="$BASE/videos"
SCRIPT="$HOME/.hermes/skills/media/comfyui-local/scripts/generate_video.py"

mkdir -p "$VIDEOS"

generate_clip() {
  local num=$1
  local img=$2
  local prompt=$3
  echo "=== Clip $num: $(basename "$img") ==="
  uv run "$SCRIPT" \
    --image "$img" \
    --prompt "$prompt" \
    --filename "$VIDEOS/clip-$num.mp4" \
    --duration 12 \
    --resolution 720p \
    --aspect 16:9
  echo "=== Clip $num done ==="
}

# IMPORTANT: do NOT prompt "singing" — LTX co-generates audio that clashes with the song.
# Use camera movement, atmosphere, gestures, landscapes, light effects.

generate_clip "01" "$IMAGES/01-scene.png" "Describe the camera movement and what changes"
generate_clip "02" "$IMAGES/02-scene.png" "Describe the camera movement and what changes"
# ... add more ...

echo "=== ALL CLIPS GENERATED ==="
