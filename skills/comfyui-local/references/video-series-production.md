# Video Series Production Pipeline

Multi-episode video series workflow for Cocobot content (e.g., "La Biblia del Gato Apocalíptico").

## Structure

```
project/
├── capitulo1/{tts,imagenes,videos}   ← Intro chapter
├── sello_N/{tts,imagenes,videos}      ← Each chapter/seal
├── epilogo/{tts,imagenes,videos}     ← Ending
├── PLAN_MASTER.md                    ← Full text + prompts per clip
└── PROGRESO.txt                      ← Progress tracker
```

## Pipeline

### Phase 1: TTS Generation
1. Generate via `generate_speech_broker.py` (see `references/tts-workflow.md`)
2. Download via broker base64 endpoint
3. Pad +0.3s with ffmpeg `apad`
4. Verify with Whisper ≥80% keywords
5. **NEVER summarize text** — split into 2+ clips if >20s
6. **ALWAYS include complete source text** — audit against source before moving to images

### Phase 2: Image Generation
1. Generate first-frame images via `generate_image.py`
2. Use FLUX.2 Klein 9B for speed/quality balance
3. Style consistency: define visual style in PLAN_MASTER.md
4. Include reference images from source (e.g., web illustrations)

### Phase 3: Video Generation
1. Image-to-video via `generate_video.py` with `--image --audio --lipsync`
2. Each clip uses the corresponding TTS audio
3. Verify Whisper coverage on final video audio

### Phase 4: Assembly
1. Concatenate clips per chapter
2. Add background music
3. Upscale to 4K with `upscale_video_ncnn_broker.py`

## Quality Gates

- [ ] All TTS clips ≤20s (before padding)
- [ ] All TTS clips verified with Whisper ≥80% keywords
- [ ] All source text included (no summaries)
- [ ] Images consistent in style across series
- [ ] Videos synced to audio (lipsync mode)
