# LTX 2.3 Video Production Workflow

Complete workflow for producing narrated videos with LTX 2.3, including mandatory quality verification.

## Prerequisites

- `faster-whisper` installed: `pip install --break-system-packages faster-whisper`
- ComfyUI broker running and accessible at `$OPENCLAW_COMFYUI_LOCAL_BROKER_URL`
- LTX 2.3 models installed (see SKILL.md for file list)

## Step-by-step workflow

### 1. Generate first-frame image with FLUX

```bash
uv run scripts/generate_image.py \
  --prompt "YOUR DETAILED PROMPT" \
  --filename "first-frame.png" \
  --aspect 16:9 \
  --model flux2-klein-9b \
  --steps 24 \
  --guidance 3.5
```

**Tips**:
- Use consistent style keywords across all frames in a series
- FLUX often misspells text — add critical text in post-production
- For multi-clip series, keep character descriptions identical across prompts

### 2. Generate video with LTX 2.3

```bash
uv run scripts/generate_video.py \
  --image "first-frame.png" \
  --prompt "Motion description + Speaking in Spanish with clear Spanish accent, saying: 'EXACT DIALOGUE HERE'" \
  --filename "output.mp4" \
  --duration 20 \
  --resolution 720p \
  --aspect 16:9
```

**Rules**:
- `--duration` max is **20** (hard LTX limit)
- ~50 words per 20s clip is safe (up to 70 fits but tight)
- Always put spoken text in **quotes** and specify **language + accent**
- If scene has multiple characters, LTX assigns voice to the MOST PROMINENT one

### 3. Mandatory verification (NEVER skip)

**3a. Audio verification with Whisper**

```python
from faster_whisper import WhisperModel
model = WhisperModel("medium", device="cpu", compute_type="int8")
segments, info = model.transcribe("output.mp4", language="es", beam_size=3)
transcript = " ".join([seg.text for seg in segments])
print(transcript)
# Compare against expected text — ≥90% word coverage = OK
```

**3b. Movement verification with frame extraction**

```bash
ffmpeg -i output.mp4 -vf "fps=0.3" /tmp/verify_%02d.jpg -y
# Visually compare first vs last frame
# If identical except for scale = static video (zoom only) → REGENERATE
```

### 4. Regeneration rules

| Problem | Fix |
|---------|-----|
| Audio cut off (<90% coverage) | Shorten dialogue text or try different seed |
| Static image (no movement) | Add "ANIMATED SCENE", "visible mouth movement", "blinking", explicit motion verbs |
| Wrong character speaking | Make desired speaker visually prominent, add "X is the narrator, Y is silent" |
| Text misspelled | Accept and add correct text in post, or regenerate with explicit character-by-character hints |

## Common prompt patterns

### Narrated scene with specific speaker
```
"The [desired speaker] turns head toward camera and speaks with visible mouth movement,
[other characters] are silent.
Speaking in Spanish with clear Spanish accent as a [character type] narrator voice,
saying: 'exact dialogue here'"
```

### Animated scene with motion
```
"ANIMATED SCENE: [character] moves [specific motion], [other elements] [motion verbs],
camera slowly [pans/zooms]. Speaking in Spanish..."
```

## Music overlay

For video series where intro has its own music:
- Generate background music **N seconds shorter** (where N = intro duration)
- Place music starting at intro's end, not at 0:00
- Mix at -15dB to -20dB:
  ```bash
  ffmpeg -i video.mp4 -i music.mp3 \
    -filter_complex "[1:a]volume=-18dB[bg];[0:a][bg]amix=inputs=2:duration=first" \
    -c:v copy output_with_music.mp4
  ```
