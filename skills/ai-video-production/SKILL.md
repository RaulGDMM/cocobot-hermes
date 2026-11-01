---
name: ai-video-production
description: Use when producing multi-clip AI video series with LTX 2.3 + FLUX + TTS/music + post-production. Covers the complete autonomous pipeline from scene planning through delivery.
version: 1.0.0
author: Cocobot
license: MIT
metadata:
  hermes:
    tags: [video, ltx-2.3, flux, autonomous, production, verification, post-production]
    related_skills: [comfyui-local, songwriting-and-ai-music]
---

# AI Video Production Pipeline

Complete workflow for producing narrated AI video series using LTX 2.3, FLUX.2 Klein 9B, TTS, music, and post-production. Designed for **autonomous operation** — the agent generates, verifies, repairs, and delivers without user intervention.

## Overview

This skill codifies every lesson learned from producing multi-episode AI video series. It covers the full pipeline: scene planning → image generation → video generation → mandatory verification → repair → concatenation → music → upscaling → delivery.

**Key principle:** NEVER deliver unverified video. Every clip passes Whisper transcription + movement check before acceptance.

## When to Use

- Producing multi-clip AI narrated video series
- Creating videos with LTX 2.3 that require voice/dialogue
- Autonomous video generation pipelines
- Post-production: concatenation, music mixing, upscaling
- Multi-episode video series from source content (web pages, documents, scripts)

**Don't use for:** Simple single-image generation (use `comfyui-local` directly)

---

> **Consolidated from `ai-video-series-production` and `ltx-video-test-workflow`.**
> The sections below cover multi-episode series production and LTX test workflows.

## Multi-Episode Series Production

For producing multi-episode series from source content (web pages, documents, scripts):

### Project Structure

```
project-name-video/
├── intro/                    # Intro video (if pre-existing)
├── capN/                     # One dir per chapter
│   ├── frames/               # FLUX first-frames (PNG)
│   ├── videos/               # LTX 2.3 generated videos (MP4)
│   ├── audio/                # SFX, extracted audio
│   └── guion.txt             # Script/storyboard
├── music/                    # ACE-generated music
└── output/                   # Final assembled episodes
```

### Whisper TTS Verification (MANDATORY before image generation)

When you have pre-existing TTS audio clips, ALWAYS verify the text matches actual audio before generating images:

```python
from faster_whisper import WhisperModel
model = WhisperModel('medium', device='cpu', compute_type='int8')
segs, info = model.transcribe('clip.wav', language='es', beam_size=1)
text = ' '.join([s.text for s in segs]).strip()
print(f"Lang: {info.language} ({info.language_probability:.2f})")
print(text)
```

**Then update the plan with REAL Whisper text** — every image prompt must be based on actual spoken content.

### Model Selection for First-Frames

| Model | When to use | Strengths |
|-------|-------------|-----------|
| `flux1-dev` | Character scenes, consistency-critical | Better character consistency |
| `flux2-klein-9b` | Landscapes, backgrounds, fast iterations | Faster (~3-5s), better text rendering |
| Gemini 3.1 Flash (Nano Banana) | Creative/literal scenes, complex compositions | Best at multi-element scenes |

### Character Consistency Rules

1. **Maintain a character description bank** in PLAN_MASTER.md
2. **Include FULL character description in EVERY prompt** — FLUX has no memory between calls
3. **Use FLUX1 Dev for character-heavy scenes** — more consistent rendering
4. **Visual elements must match narration LITERALLY** — every image should contain ALL key objects from the audio narration
5. **For political figures in Gemini**: NEVER use real names (blocked). Use visual descriptions.

### ffmpeg Assembly — filter_complex concat (MANDATORY)

**⚠️ NEVER use `-f concat -safe 0` (concat demuxer) for clips with audio** — accumulates AAC padding drift. Use `filter_complex concat`:

```bash
ffmpeg -y -i clip1.mp4 -i clip2.mp4 -i clip3.mp4 \
  -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[outv][outa]" \
  -map "[outv]" -map "[outa]" \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart output.mp4
```

### Audio Normalization (MANDATORY before assembly)

```bash
ffmpeg -y -i "clip.mp4" -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
  -af "loudnorm=I=-16:LRA=11:TP=-1.5,acompressor=threshold=-20dB:ratio=2:attack=30:release=100" \
  -shortest "normalized_clip.mp4"
```

Verify: `ffmpeg -i "normalized_clip.mp4" -af volumedetect -f null -` (target: mean_volume -22 to -24 dB)

### Music Overlay with Fade

```bash
ffmpeg -y -i "video.mp4" -i "music.mp3" \
  -filter_complex "[1:a]volume=-18dB,afade=t=out:st=TOTAL-5:d=5[music];[0:a][music]amix=inputs=2:duration=first[outa]" \
  -map 0:v -map "[outa]" -c:v copy -c:a aac -b:a 192k -movflags +faststart final.mp4
```

### LTX 2.3 IC-LoRA for Character Consistency

- **Weight sweet spot: 0.5-0.7** — at 1.0 weight produces near-static video
- Train with video frames (not just still photos) to preserve motion
- Use reference image as visual anchor

### Assembly Verification (MANDATORY)

```bash
ffprobe -v error -show_entries stream=codec_type,duration -of json output.mp4
# Video/audio stream durations must differ by <0.1s
```

## LTX Video Test Workflow

Reusable test case for evaluating video generation quality.

### Test Scenario: "El Gato del Ranking"

A 20-second video of a black cat delivering a political corruption joke in Spanish with physical action (jumping and landing).

**Working prompt format** (single paragraph, present tense, dialogue in quotes):
```
A medium shot of [SUBJECT] in [SETTING]. The subject turns to face the camera and speaks in [LANGUAGE] with [LANGUAGE] accent, "[DIALOGUE]". The subject then [PHYSICAL ACTION]. The camera slowly zooms. The audio features crisp [LANGUAGE] dialogue with [AMBIENT SOUND].
```

### Quality Checklist
- [ ] First frame image matches scene described in prompt
- [ ] Dialogue timing matches visual action
- [ ] Motion is smooth without artifacts
- [ ] Audio is clear and intelligible
- [ ] Subject maintains consistent appearance

### Re-test When
- New video model version released
- LTX 2.3 updates improve motion/dialogue
- Different aspect ratios or longer durations needed

---

## Complete Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ 0. EXTRACT  → Download full HTML, extract ALL text verbatim    │
├─────────────────────────────────────────────────────────────────┤
│ 1. PLAN     → Scene breakdown, EXACT text per clip, word counts│
├─────────────────────────────────────────────────────────────────┤
│ 2. TTS      → Generate ALL audio first (Qwen3-TTS via broker)  │
│               → Download + pad (ffmpeg 0.3s) + Whisper verify  │
│               → Full text audit: web line-by-line vs audio     │
├─────────────────────────────────────────────────────────────────┤
│ 3. IMAGES   → FLUX.2 Klein first-frame per scene               │
├─────────────────────────────────────────────────────────────────┤
│ 4. VIDEO    → LTX 2.3 img2video per clip (max 20s)             │
├─────────────────────────────────────────────────────────────────┤
│ 5. VERIFY   → Whisper ≥90% coverage + frame movement check     │
├─────────────────────────────────────────────────────────────────┤
│ 6. REPAIR   → Regenerate failed clips (max 3 attempts)         │
├─────────────────────────────────────────────────────────────────┤
│ 7. CONCAT   → Assemble clips, fix audio drift, normalize levels│
├─────────────────────────────────────────────────────────────────┤
│ 8. MUSIC    → Overlay background music at -15dB to -20dB       │
├─────────────────────────────────────────────────────────────────┤
│ 9. SCALE    → ncnn-vulkan 4K upscaling via broker              │
├─────────────────────────────────────────────────────────────────┤
│ 10. DELIVER → Final quality check + output                     │
└─────────────────────────────────────────────────────────────────┘
```

**TTS-FIRST RULE: Generate and verify ALL audio BEFORE generating any images or video.**
Reason: TTS determines the actual clip count and duration. Images/videos are expensive to regenerate if the audio changes. If you discover missing text after generating videos, you'd have to redo everything. TTS is cheap and fast; video is slow and costly. Audit the full text coverage (web line-by-line vs audio transcript) BEFORE moving to images.

## Phase 0: Source Text Extraction (MANDATORY — DO FIRST)

**CRITICAL: NEVER summarize or invent source text.** This is the #1 failure mode.

1. Download the full HTML of the source website/page
2. Extract ALL text verbatim (no summarizing, no paraphrasing)
3. Save to a `contenido_web.txt` file for reference
4. Create a `PLAN_COMPLETO.txt` with EXACT text per clip per section
5. **DO NOT skip to generation** — complete Phase 0 before anything else

**User preference: NEVER skip text or summarize.** If a section has 3 paragraphs, all 3 paragraphs must be narrated. Split into more clips if needed — but never omit content.

**Before any generation, verify:** You have the COMPLETE text extracted and organized in a plan file. If you don't, stop and do Phase 0 first.

## Phase 0.5: Full Text Audit (MANDATORY — AFTER TTS, BEFORE IMAGES)

After generating ALL TTS clips and verifying them individually with Whisper, perform a **line-by-line audit** comparing the source web text against ALL audio transcripts combined:

1. List every narrative paragraph/line from the source
2. Check which paragraphs are covered by which audio clips
3. Identify COMPLETELY MISSING content (paragraphs with no audio at all)
4. Identify PARTIALLY COVERED content (paragraphs where key details were dropped)
5. **Generate additional clips for ANY missing content** — do not proceed to images until 100% coverage

**Common gaps found in audits:**
- Transitional sentences between paragraphs ("Las mascarillas llegaban, pero el dinero público se iba...")
- Attribution/citation phrases ("— Apocalipsis Felina 1:4")
- Closing remarks/footnotes ("Ningún gato fue dañado durante la creación...")
- Character titles ("Ábalos, que fue ministro y secretario de organización del PSOE")
- Extended analogies that were shortened ("el recorrido de un gato a las 4 de la mañana cuando decide que NECESITA correr de un extremo de la casa al otro derrapando en el parqué")

**This audit caught 1,700+ chars of missing content in a 56-clip project that initially appeared "complete." Always do it.**

## Phase 1: Scene Planning

Before generating anything, create a scene plan:

| Field | Required | Notes |
|-------|:---:|------|
| `clip_N_image_prompt` | ✅ | FLUX prompt for first-frame image |
| `clip_N_video_prompt` | ✅ | Motion + dialogue for LTX |
| `clip_N_dialogue` | ✅ | **EXACT** source text (never summarize) |
| `clip_N_expected_duration` | ✅ | Max 20s LTX hard limit |
| `clip_N_word_count` | ✅ | Safe: ≤50 words per 20s clip |

**Style consistency rules:**
- Use IDENTICAL style keywords across ALL image prompts for character consistency
- **BUT vary overall style per scene** — user preference: "animación no significa infantil", mix medieval/cinematic/digital styles for variety
- Use images from the source website as reference/inspiration when available
- Character descriptions must be identical across all scenes
- Example: "cinematic digital painting, warm amber and deep blue tones, flat 2D illustration style"

**Dialogue rules per clip:**
- Maximum 50 words of spoken dialogue per 20s clip
- Put exact spoken text in quotes: `'exact dialogue here'`
- Specify language: "Speaking in Spanish with clear Spanish accent"
- If multiple characters: make desired speaker visually most prominent
- **Images must reflect the SPECIFIC content being narrated** — don't use generic "cat prophet" images if the text describes a specific scene (e.g., "Epstein island" → show island, not just cat)

### Phase 2: TTS Generation (BEFORE images/video)

Generate ALL narration audio first. Use `comfyui-local` TTS section.

**Per clip:**
1. Generate via `generate_speech_broker.py` (max 20s per clip)
2. Download via broker base64 endpoint (NOT SSH)
3. Pad with ffmpeg `apad=pad_dur=0.3` (fixes last-syllable cutoff)
4. Verify with faster-whisper (≥80% keyword coverage)

**Rules:**
- If text >20s: split into 2+ clips, NEVER summarize
- Numbers: write "MIL" not "1.000" (prevents "mil mil" misreading)
- Common words: use "pesquería" not "pesquetería" (better pronunciation)
- After ALL TTS done: perform Phase 0.5 full text audit

See `comfyui-local` skill → TTS section and `references/tts-workflow.md` for details.

### Phase 3: First-Frame Image Generation

Use FLUX.2 Klein 9B for best quality:

```bash
uv run {baseDir}/scripts/generate_image.py \
  --prompt "EXACT CHARACTER + SCENE DESCRIPTION" \
  --filename "clip_N_firstframe.png" \
  --aspect 16:9 \
  --model flux2-klein-9b \
  --steps 24 \
  --guidance 3.5
```

**CRITICAL:** Keep character descriptions identical across ALL clips.
- Example: "sleek black cat with glowing golden eyes, wearing tiny spectacles, cinematic digital painting"

### Phase 4: Video Generation (LTX 2.3)

**STEP 0 — MANDATORY: Analyze source image with vision BEFORE crafting prompt.**
```
vision_analyze(image_url="<selected_image>", 
  question="Describe composition, layout, panels, character positions, decorative elements, style. Detail every zone so I can create a video prompt that respects this exact composition.")
```
**Why:** Without understanding the image composition, video prompts produce camera movements that destroy panel layouts (tríptics, vignettes, split compositions). The prompt must describe the ACTUAL image, not a generic scene.

**For EACH clip (use --lipsync for narrated scenes):**

```bash
uv run scripts/generate_video.py \
  --lipsync \
  --image "clip_N_firstframe.png" \
  --audio "clip_N_narration.wav" \
  --prompt "STATIC CAMERA. [Exact composition from vision analysis]. The [speaker] speaks with visible mouth movement. [Subtle element motion]. No camera movement. Speaking in Spanish with clear Spanish accent as [voice type] voice, saying: 'EXACT DIALOGUE TEXT'" \
  --filename "clip_N_raw.mp4" \
  --duration <audio_duration> \
  --resolution 720p \
  --aspect 16:9
```

**Prompt template for narrated scenes (Lipsync version):**
```
"STATIC CAMERA. [Describe exact composition from vision analysis - panels, character positions, key elements].
The [desired speaker] speaks with visible mouth movement and [subtle head/paw gestures].
[Other characters] remain still or have [minimal natural motion - breathing, ear twitch, tail swish].
[Environment motion - steam rises, flames flicker, runes rotate, lightning flashes].
No camera movement.
Speaking in Spanish with clear Spanish accent as a [character description] voice,
saying: 'exact dialogue text here'"
```

**CRITICAL — Lipsync requires exact text in quotes:**
- Without the `saying: '...'` block, lip sync quality is very poor
- The text inside quotes MUST match the TTS audio content exactly
- Format: `Speaking in Spanish with clear Spanish accent as a [voice type] voice, saying: 'exact text here'`

**Camera movement rules:**
- **STATIC CAMERA is the default.** Never assume movement is acceptable.
- Zoom and pan DESTROY structured compositions (tríptics, panels, ornate frames)
- Only use camera movement if explicitly requested by the user (e.g., "cámara girando alrededor")
- When camera movement IS wanted: use "SLOW circular camera orbit" not aggressive zoom/pan

**Timing specific actions within a clip:**
- For actions that should happen at a specific point: "About two-thirds into the scene, [character] suddenly [action]"
- This helps LTX place timed events correctly within the video duration

### Phase 5: Mandatory Verification (NEVER SKIP)

### 4A: Whisper Audio Verification

```python
from faster_whisper import WhisperModel
model = WhisperModel("medium", device="cpu", compute_type="int8")
segments, _ = model.transcribe("clip_N_raw.mp4", language="es", beam_size=3)
transcript = " ".join([seg.text for seg in segments])
print(f"Transcript: {transcript}")

# Word coverage check
expected_words = expected_dialogue.lower().split()
actual_words = transcript.lower().split()
coverage = sum(1 for w in expected_words if any(w in actual for actual in actual_words))
coverage_pct = coverage / len(expected_words) * 100
print(f"Coverage: {coverage_pct:.0f}% (need ≥90%)")
```

**Thresholds:**
- ≥90% coverage → ✅ ACCEPT
- 70-89% → ⚠️ Try 1 more regeneration with different seed
- <70% → ❌ REJECT and reduce word count

### 4B: Movement Verification

```bash
# Extract keyframes
ffmpeg -i clip_N_raw.mp4 -vf "fps=0.3,select='gt(scene\,0.1)'" /tmp/verify_clipN_%02d.jpg -y

# Count unique frames (more than 3 = real movement)
ls /tmp/verify_clipN_*.jpg | wc -l
```

**Check visually:** First frame vs last frame should differ significantly (not just a zoom).

**Automatic check:**
```bash
# Compare first and last extracted frame
ffmpeg -i clip_N_raw.mp4 -vf "fps=1,select='eq(n\,0)+eq(n\,-1)',scale=64:64" -vsync vfw /tmp/vf_%02d.jpg -y
# If both frames identical → static video → REGENERATE
```

### Phase 6: Repair / Regeneration Rules

| Problem | Fix | Max Attempts |
|---------|-----|:---:|
| Audio cut off (<90% coverage) | Shorten dialogue, try different seed | 3 |
| Static image (no movement) | Add explicit motion verbs + "ANIMATED SCENE" | 3 |
| Wrong character speaking | Make speaker visually prominent in image prompt | 3 |
| Voice quality poor | Regenerate, don't change prompt | 3 |
| Text misspelled in image | Accept — add correct text in post with ffmpeg subtitles | — |

**Autonomous regeneration rules:**
- Max **3 regeneration attempts** per clip before moving on
- If 3rd attempt fails: accept best clip and add note for manual review
- Reduce word count by 20% on each retry
- Always use `--seed` different value on retries

### Phase 7: Concatenation

When joining multiple clips, audio/video drift is the #1 failure mode.

### Correct concatenation (fixes drift):

```bash
# Method: concat demuxer with explicit input mapping
cat > /tmp/concat.txt << EOF
file 'clip_1.mp4'
file 'clip_2.mp4'
file 'clip_3.mp4'
EOF

ffmpeg -f concat -safe 0 -i /tmp/concat.txt \
  -c:v libx264 -crf 18 -preset medium \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  output_concatenated.mp4
```

### Volume normalization per segment:

If clips have different voice volumes:

```bash
ffmpeg -i clip_1.mp4 -af "loudnorm=I=-16:LRA=11:TP=-1.5" -c:v copy clip_1_norm.mp4
```

### Handling audio gaps:

When combining clips where some have voice and others are silent:
- Extract audio from each clip separately
- Normalize each independently
- Concatenate with gapless audio:

```bash
# Better approach: extract, normalize, concat audio separately
for i in 1 2 3 4; do
  ffmpeg -i clip_${i}.mp4 -vn -af "loudnorm=I=-16:LRA=11:TP=-1.5" audio_${i}.aac
done

# Concat audio
cat > /tmp/audio_concat.txt << EOF
file 'audio_1.aac'
file 'audio_2.aac'
file 'audio_3.aac'
file 'audio_4.aac'
EOF

ffmpeg -f concat -safe 0 -i /tmp/audio_concat.txt -c:a aac -b:a 192k output_audio.aac
ffmpeg -f concat -safe 0 -i /tmp/concat.txt -c:v libx264 -crf 18 -an output_video_noadio.mp4
ffmpeg -i output_video_noadio.mp4 -i output_audio.aac -c:v copy -c:a aac -shortest output_final.mp4
```

### Phase 8: Music Overlay

Generate background music (use `generate_song.py` or similar):

```bash
# Mix music at -18dB so voice remains primary
ffmpeg -i video.mp4 -i music.mp3 \
  -filter_complex "[1:a]volume=-18dB[bg];[0:a][bg]amix=inputs=2:duration=first" \
  -c:v copy \
  output_with_music.mp4
```

**Music rules:**
- If intro clip has its own music: generate background music **N seconds shorter** (N = intro duration)
- Music starts at intro's end, not at 0:00
- Volume: -15dB to -20dB (voice must dominate)
- Use `-shortest` to avoid music extending past video

### Avoiding volume jumps at music boundaries:

```bash
# Add fade-out to music track to prevent sudden level drops
ffmpeg -i video.mp4 -i music.mp3 \
  -filter_complex \
    "[1:a]volume=-18dB,afade=t=out:st=TOTAL_DURATION-5:d=5[music];[0:a][music]amix=inputs=2:duration=first" \
  -c:v copy output.mp4
```

Where `TOTAL_DURATION` is the video length minus 5 seconds for the fade.

### Phase 9: Upscaling to 4K

**ALWAYS use ncnn-vulkan via broker** — never run upscaling directly while llama-server is active.

```bash
python3 {baseDir}/scripts/upscale_video_ncnn_broker.py \
  --input /path/to/final_video.mp4 \
  --output /path/to/final_video_4k.mp4 \
  --scale 4 \
  --model realesr-animevideov3 \
  --threads 2:4:4 \
  --broker-url $OPENCLAW_COMFYUI_LOCAL_BROKER_URL \
  --timeout 7200
```

**Why ncnn-vulkan over Python Real-ESRGAN:**
- 10-20x faster (native Vulkan GPU compute)
- No Python dependency hell
- Model `realesr-animevideov3` optimized for animated content

### Phase 10: Delivery

Final checks before delivering:
1. [ ] All clips verified (Whisper ≥90%, movement confirmed)
2. [ ] Audio/video sync verified on final output
3. [ ] Volume levels consistent throughout
4. [ ] Music doesn't overpower voice
5. [ ] Resolution is target (4K if upscaled)

```bash
# Final quality check
ffprobe -v error -show_entries stream=width,height,duration,codec_name \
  -show_entries format=size,duration,bit_rate \
  -of json output_final.mp4
```

## Autonomous Mode Rules

When operating autonomously (user said "do it yourself"):

1. **Extract ALL source text FIRST** — Save complete text to a plan file. Never work from summaries or web extracts that truncate.
2. **Confirm the plan once** — Show scene breakdown with EXACT text and get ONE confirmation
3. **Then execute** — Generate all images, then all videos, verify each
4. **Max 3 retries per clip** — If 3rd fails, accept best and note it
5. **Report progress** — Brief status after each phase
6. **Deliver automatically** — Don't ask "should I continue?" — keep going
7. **Track progress in a PROGRESO.txt file** — Update after each completed section. Format: `[✅] [ ] [~]` status markers per section.
8. **Clean up failed clips immediately** — Remove incorrect generations (wrong language, wrong image, wrong text) to avoid confusion. User will get confused by leftover files.
9. **Stop and ask only when:**
   - All clips failed verification
   - User's creative direction is unclear
   - Output quality is below acceptable threshold despite retries
   - Source text extraction was incomplete

### Progress Tracking Format

Maintain a `PROGRESO.txt` file with this structure:
```
[✅] Section N — X clips — COMPLETED
[~] Section N — X/Y clips — IN PROGRESS (clip1 ✅, clip2 ❌ needs regenerate)
[ ] Section N — X clips — NOT STARTED
```

Update this file after each section completion. This lets the user see status at a glance.

### Token budget awareness

- LTX video generation: slow (several minutes per clip)
- Image generation: fast (~3-5s per image)
- Always batch: generate all images in one broker batch (`--count`), not sequentially

## Critical: Broker Interruption Awareness

**⚠️ The broker kills llama.cpp while running GPU jobs.** This means:

- When you submit a video/image generation job to the broker, **llama-server stops immediately**
- While the job runs, **you cannot issue new tool calls that require the model** (no `write_file`, no `execute_code`, no thinking)
- **You MUST wait** for the background process to complete (use `process action=wait`) before continuing
- If you try to act during the gap, the stream stalls and the action never executes

**Correct workflow:**
1. Submit generation job as background process
2. Set `notify_on_complete=true`
3. Wait with `process action=wait` until it finishes
4. Only THEN proceed with next steps (verification, concatenation, etc.)

**Wrong workflow (causes stalls):**
1. Submit generation job
2. Try to write scripts, generate files, or plan next steps while it runs
3. Stream stalls — action never executes — you're stuck

## Common Pitfalls

1. **Broker interruption stalls** — See "Critical: Broker Interruption Awareness" above. This is the #1 cause of stuck sessions.

2. **Summarizing source text** — NEVER do this. User explicitly complained about this multiple times. Every paragraph of source text must be narrated. Split into more clips if needed, but never omit content. This is the #1 creative failure mode.

3. **Audio/video drift in concatenation** — Use concat demuxer, NOT filter_complex concat. Always re-encode both streams.

4. **Volume jumps between clips** — Normalize each clip independently before concatenation with `loudnorm`.

5. **Music fade-out creates silence gap** — Extend music track 5-10s past expected end + add `afade` instead of hard cut.

6. **LTX assigns voice to wrong character** — The most visually prominent character gets the voice. Make desired speaker larger/more centered in the image prompt.

7. **Static video from LTX** — Always include explicit motion verbs AND "ANIMATED SCENE" prefix. If still static, regenerate with higher `--steps`.

8. **Running upscaling alongside llama-server** — **CRITICAL:** Always use broker for upscaling. Direct execution saturates system despite low VRAM.

9. **torch sm_120 incompatibility** — RTX 5090 requires `torch>=2.6`. The broker's `uv --with` may resolve to torch 2.4. Use ncnn-vulkan (no torch) or pre-built venv.

10. **FLUX misspells text** — Don't regenerate for this. Add correct text in post-production with ffmpeg overlay.

11. **Word count too high** — >50 words per 20s clip → audio gets cut off. Trim dialogue aggressively.

12. **uv cache resolves wrong torch** — When `basicsr` is in deps, uv may downgrade torch. Use pre-built venv or ncnn-vulkan to avoid.

13. **Generic images don't match narrated content** — User preference: images should reflect the SPECIFIC scene being described. If text says "Epstein island", show the island, not just a generic cat prophet. Use source website images as reference/inspiration.

14. **Leftover failed clips cause confusion** — Always clean up incorrect generations (wrong language, wrong text, wrong image) immediately after detecting failure.

15. **No progress tracking** — User needs to see status at a glance. Maintain a PROGRESO.txt file with `[✅] [ ] [~]` markers per section, updated after each completion.

16. **Intro clips need music** — When generating intro clips (~10s) for each section, include music generation in the prompt: "angelical biblical music background" or similar to set tone.

17. **Images too childish** — User preference: "animación no significa infantil". Use mature styles (medieval manuscripts, cinematic painting, aged parchment). Avoid cartoonish or overly simplified styles.

18. **TTS before images/video** — Generate ALL audio FIRST, verify with Whisper, do full text audit, THEN generate images/video. Reason: TTS is cheap and determines clip count. If you generate video first and then find missing text, you have to redo everything. A 56-clip project caught 1,700+ chars of missing content only after the full text audit — doing TTS first saves hours of wasted video generation.

19. **Full text audit catches invisible gaps** — Even when individual clips look "complete," comparing source text line-by-line against audio transcripts reveals missing transitional sentences, footnotes, character titles, and extended analogies. Always do Phase 0.5 audit.

20. **Broker file download via base64 only** — Do NOT use SSH to download generated files from the broker (it times out). Use the `/v1/gpu-exec` endpoint with `["base64", "path/to/file"]` command. For batch downloads, write a Python script.

21. **Lip sync fails without quoted dialogue** — Without the `saying: 'exact text'` block in the prompt, LTX produces very poor mouth movement that doesn't match the audio. ALWAYS include the full dialogue text in quotes after `saying:`.

22. **Camera movement destroys compositions** — Default prompt includes camera movement, but many images have structured layouts (tríptics, panels, ornate frames). Camera zoom/pan distorts these. Use STATIC CAMERA by default unless user explicitly requests movement.

23. **Vision analysis skipped** — Without analyzing the source image first, prompts describe generic scenes instead of the actual image. This causes mismatches: the video tries to create a scene that differs from the first-frame image, producing artifacts and composition errors.

24. **Erratic limb movement** — Characters' hands/paws may make strange motions. Fix: add "His arms and paws stay relaxed at his sides without erratic movement" to the prompt.

25. **Grain/noise inherent to LTX 2.3** — Output videos have visible grain/pixel noise. This is NATURAL model behavior, NOT a workflow bug. Cannot be fixed via prompt (no negative prompt support) or workflow changes. Accept it or use post-production denoising.

26. **Bombs/explosions stay static** — LTX may render falling objects (bombs, rain, debris) as floating still images rather than animated. Emphasize verbs: "bombs RAINING DOWN, CRASHING into buildings with bright EXPLOSIONS, lightning STRIKES flashing".

## Verification Checklist

- [ ] Phase 0: Complete source text extracted to `contenido_web.txt`
- [ ] Phase 0.5: Full text audit done — every source paragraph matched to audio clip
- [ ] ALL TTS generated, padded (+0.3s ffmpeg), Whisper-verified (≥80%)
- [ ] Scene plan created with word counts ≤50 per clip
- [ ] Character descriptions identical across all image prompts
- [ ] Style keywords consistent across all scenes
- [ ] Whisper transcription ≥90% for every video clip
- [ ] Movement verified (first ≠ last frame)
- [ ] Concatenation uses concat demuxer (not filter_complex)
- [ ] Volume normalized per clip before concatenation
- [ ] Music at -15dB to -20dB with fade-out
- [ ] Upscaling done via ncnn-vulkan broker
- [ ] Final ffprobe quality check passed
