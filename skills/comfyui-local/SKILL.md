---
name: comfyui-local
description: Generate images locally through the Windows ComfyUI broker using FLUX.1 Dev or FLUX.2 Klein 9B workflows.
metadata:
  {
    "openclaw":
      {
        "emoji": "🖼️",
        "requires": { "bins": ["uv"], "env": ["OPENCLAW_COMFYUI_LOCAL_BROKER_URL"] },
        "primaryEnv": "OPENCLAW_COMFYUI_LOCAL_BROKER_URL",
        "install":
          [
            {
              "id": "uv-brew",
              "kind": "brew",
              "formula": "uv",
              "bins": ["uv"],
              "label": "Install uv (brew)",
            },
          ],
      },
  }
---

# ComfyUI Local

Use the bundled script to generate images locally through the broker on the Windows host.

## Model Selection

Use `--model` to choose the image generation model. Default is `flux2-klein-9b`.

| Model | Flag | Quality | Speed (RTX 5090) | VRAM | Text | Best for |
|-------|------|---------|-------------------|------|------|----------|
| FLUX.1 Dev | `--model flux1-dev` | High | ~8-12s | ~16GB | Good | **Character consistency**, faithful to detailed character descriptions |
| FLUX.2 Klein 9B | `--model flux2-klein-9b` | Higher | ~3-5s | ~12GB | Excellent | Speed + quality, text rendering, landscapes, fast iterations |

**For video series with recurring characters**: Use FLUX.1 Dev for scenes featuring the main character. It produces more consistent character rendering across multiple generations. FLUX.2 Klein is better for backgrounds, landscapes, and quick iterations.

## Before calling the script

Always send a short confirmation message to the user. Example: `Ok, voy a generar 3 imagenes en formato 16:9 de Cocobot persiguiendo un raton. Tardara un poco.`

## Generate one image

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png"
```

With FLUX.2 Klein 9B:

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --model flux2-klein-9b
```

## Generate multiple images in one broker batch

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --count 3 --aspect 16:9
```

This creates `output-1.png`, `output-2.png`, `output-3.png` and keeps all requests inside the same broker batch. Do not call the script multiple times for a multi-image request.

## Generate multiple images with different prompts

```bash
uv run {baseDir}/scripts/generate_image.py \
  --prompts-json '["prompt one", "prompt two", "prompt three"]' \
  --filename "output.png" \
  --aspect 16:9
```

## Optional quality controls

```bash
uv run {baseDir}/scripts/generate_image.py \
  --prompt "your image description" \
  --filename "output.png" \
  --steps 24 \
  --guidance 3.5 \
  --aspect 16:9
```

Aspect ratio guide

- `--aspect 1:1` => `1024x1024`
- `--aspect 16:9` => `1280x720` (standard wide format, preferred over extra-wide cinematic sizes like `1920x512`)
- `--aspect 21:9` => `1536x640` (ultrawide / cinematic)
- `--aspect 3:2` => `1216x832`
- `--aspect 4:3` => `1152x896`
- `--aspect 5:4` => `1120x896`
- `--aspect 2:3` => `832x1216`
- `--aspect 4:5` => `896x1120`
- `--aspect 9:16` => `768x1344`

If the user asks for panoramic in the normal sense, use `--aspect 16:9`.
Use `--aspect 21:9` only when the user clearly asks for ultrawide or cinematic.
If the user asks for some other format or exact dimensions, use explicit `--width` and `--height`.

Examples:

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "scene" --filename "output.png" --aspect 4:3
```

```bash
uv run {baseDir}/scripts/generate_image.py --prompt "scene" --filename "output.png" --width 1408 --height 1024
```

Broker configuration

- `OPENCLAW_COMFYUI_LOCAL_BROKER_URL` env var
- Optional timeout via `OPENCLAW_COMFYUI_LOCAL_TIMEOUT_SECONDS`
- Or set `skills."comfyui-local".env.*` in `~/.openclaw/openclaw.json`

Edit an existing image (Flux Kontext)

```bash
uv run {baseDir}/scripts/generate_image.py --image "./input.png" --prompt "Change the background to a sunset beach" --filename "./edited.png"
```

Edit with a second reference image

```bash
uv run {baseDir}/scripts/generate_image.py --image "./photo.png" --image2 "./style-ref.png" --prompt "Apply the style from the second image to the first" --filename "./styled.png"
```

In edit mode, `--aspect`/`--width`/`--height` are ignored (dimensions come from the input image). Default guidance is 2.5 (vs 3.5 for generation). You can override with `--guidance`.

Prompt tips for editing:
- Be specific: "Change the car color to red" instead of "make it red"
- Preserve explicitly: "Change the background to a beach while keeping the person in the same position"
- For style transfer: "Transform to oil painting with visible brushstrokes while maintaining the original composition"

Notes (images)

- This skill is local-only and uses the Windows broker plus ComfyUI.
- **Model selection**: `--model flux1-dev` (default) or `--model flux2-klein-9b`. FLUX.2 Klein 9B is faster (~3-5s vs ~8-12s on RTX 5090) and produces higher quality with better text rendering.
- **Image editing**: Both models support image editing via `--image`. FLUX.1 uses Kontext architecture, FLUX.2 Klein uses a completely different native i2i workflow. Edit with FLUX.2 Klein: `--image "input.png" --model flux2-klein-9b --prompt "your edit"`.

### FLUX.2 Klein i2i — CRITICAL SETTINGS

FLUX.2 Klein's i2i workflow uses **ReferenceLatent chaining** per the official ComfyUI documentation. Each reference image is independently VAE-encoded and its visual features are injected into conditioning tensors through `ReferenceLatent` nodes that chain sequentially.

**Single-image edit workflow:**
- `LoadImage` → `VAEEncode` → `ReferenceLatent(conditioning, latent)` → `FluxGuidance` → `KSampler`
- `ConditioningZeroOut` of the same prompt as negative conditioning
- CFG: **4.0** | Denoise: **0.75** | CLIP: `type: "flux2"` with `qwen_3_8b_fp8mixed.safetensors`

**Dual reference images (`--image` + `--image2`):** Uses `ReferenceLatent` chaining — NOT `ImageStitch`.
- Each image: `LoadImage` → `VAEEncode` → independent `ReferenceLatent` node
- First `ReferenceLatent` takes prompt conditioning as base
- Second `ReferenceLatent` chains from the first `ReferenceLatent` output
- Final `ReferenceLatent` → `FluxGuidance` → `KSampler`
- The first encoded latent is used as the base latent in `KSampler`
- Prompt should describe what to combine from each reference

**Denoise guide for Klein i2i:**
- 0.75 (default) — Balanced: preserves composition, allows meaningful style/subject changes
- 0.60 — Subtle changes: color tweaks, minor detail edits, keeps original composition
- 0.90 — Heavy changes: significant reimagining, less structure preserved

**⚠️ ComfyUI Node Compatibility:** The following nodes may NOT be available in all ComfyUI versions:
- ❌ `SamplerCustomAdvanced`, `Flux2Scheduler`, `CFGGuider`, `RandomNoise`, `KSamplerSelect`, `ImageScaleToTotalPixels`, `GetImageSize`
- The script uses only **verified available nodes**: `UNETLoader`, `VAELoader`, `CLIPLoader`, `CLIPTextEncode`, `ConditioningZeroOut`, `FluxGuidance`, `LoadImage`, `VAEEncode`, `ReferenceLatent`, `KSampler`, `VAEDecode`, `SaveImage`
- If you get HTTP 500 from the broker, check which node caused the error and replace it with a compatible alternative

- **Denoise in edit mode**: FLUX.2 Klein i2i uses `denoise=0.75` by default. For subtle edits, use lower denoise (~0.6). For heavy structural changes, use higher (~0.9).
- Historical broker download failures in prior chat turns may be stale. For a new text-to-image request, try this skill once in the current turn before concluding it is unavailable.
- The script saves the final PNG into the current workspace path you pass in `--filename`.
- For multi-image requests, prefer `--count` and optionally `--prompts-json` rather than multiple separate exec calls.
- After generation, send each image with the `message` tool using both `message` and `media`. Example: `{ "action": "send", "message": "Imagen 1 de 3", "media": "./output-1.png" }`.
- The `message` text field is required. Never call `message` without it.
- Do not read the image back; report the saved path only.

### Required model files

| Model | Diffusion model | VAE | Text encoder |
|-------|----------------|-----|--------------|
| FLUX.1 Dev | `diffusion_models/flux1-dev.safetensors` (23G) | `vae/ae.safetensors` (320M) | `clip/clip_l.safetensors` + `clip/t5xxl_fp16.safetensors` |
| FLUX.2 Klein 9B | `diffusion_models/flux-2-klein-9b-fp8.safetensors` (8.8G) | `vae/flux2-vae.safetensors` (321M) | `clip/qwen_3_8b_fp8mixed.safetensors` (8.1G) |

---

# ComfyUI Local — Video Generation (LTX 2.3)

Use the bundled script to generate videos locally through the broker on the Windows host.

Before calling the script, always send a short confirmation message to the user with the `message` tool. Example: `Ok, voy a generar un video de 5 segundos en 720p de un gato jugando. Tardará unos minutos.`

Text-to-Video (basic)

```bash
uv run {baseDir}/scripts/generate_video.py --prompt "A cat chasing a laser pointer across a living room" --filename "output.mp4"
```

Image-to-Video (animate a first frame)

```bash
uv run {baseDir}/scripts/generate_video.py --image "./first-frame.png" --prompt "The camera slowly zooms in while flowers sway in the wind" --filename "output.mp4"
```

Audio-conditioned video (the video follows the audio)

```bash
uv run {baseDir}/scripts/generate_video.py --audio "./music.mp3" --prompt "A DJ mixing tracks in a neon club" --filename "output.mp4"
```

Image + Audio (first frame + audio conditioning)

```bash
uv run {baseDir}/scripts/generate_video.py --image "./scene.png" --audio "./narration.wav" --prompt "The narrator describes the scene" --filename "output.mp4"
```

Lip-sync mode (best for talking heads / singing)

```bash
uv run {baseDir}/scripts/generate_video.py --lipsync --image "./portrait.png" --audio "./speech.wav" --prompt "A woman speaking directly to camera" --filename "lipsync_output.mp4"
```

- Requires both `--image` (face/portrait) and `--audio` (speech/singing audio).
- Internally uses MelBand RoFormer to isolate vocals from the audio, then conditions video generation on the clean vocal track via a dedicated Audio VAE.
- Produces significantly better lip synchronisation than regular `--image --audio` (which treats audio as ambient conditioning).
- **The output video keeps the original audio track** — the script automatically replaces the model-generated audio with the input audio via ffmpeg after generation.
- Best results with: clear frontal face, clean speech audio, 3-8 second clips.

**CRITICAL for lipsync quality:**
- Your prompt MUST include the exact spoken text in quotes for proper mouth movement:
  `Speaking in Spanish with clear Spanish accent as [voice type] voice, saying: 'exact dialogue text here'`
- Without this, lip sync is very poor — mouth moves but doesn't match the audio rhythm.
- **ALWAYS analyze your source image with vision BEFORE crafting the prompt** to understand its composition (panels, character positions, decorative frames). Without this, camera movements can destroy structured compositions (tríptics, vignettes, ornate borders).
- Use `STATIC CAMERA` in your prompt by default — zoom/pan distorts structured image layouts.

Custom duration, resolution, and aspect ratio

```bash
uv run {baseDir}/scripts/generate_video.py --prompt "A drone shot over a mountain range at sunset" --filename "output.mp4" --duration 10 --resolution 1080p --aspect 16:9
```

Optional quality controls

```bash
uv run {baseDir}/scripts/generate_video.py --prompt "description" --filename "output.mp4" --steps 24 --seed 42
```

Resolution presets

- `--resolution 480p` — Fast previews; good for testing prompts
- `--resolution 720p` — Default; good balance of quality and speed
- `--resolution 1080p` — Full HD; slower but best quality

Aspect ratio guide

- `--aspect 16:9` — Standard widescreen (default)
- `--aspect 4:3` — Classic TV / photo
- `--aspect 1:1` — Square (social media)
- `--aspect 9:16` — Vertical / mobile / stories
- `--aspect 3:4` — Vertical photo

Duration

- `--duration N` where N is 1–20 seconds (default 5)
- Internally converted to a valid LTX frame count (8k+1 formula)
- Longer videos use proportionally more VRAM and time

Prompt tips for video
Prompt tips for video
- Describe **motion** explicitly: "A bird takes flight from a branch", "The camera pans left slowly"
- Include environment details: "in a sunlit forest", "during heavy rain at night"
- For image-to-video, describe what should **change** from the static image: "The water begins to flow", "Clouds drift across the sky"
- Prompts are auto-enhanced by Gemma 3 12B for better results — keep your prompt natural and descriptive
- **Speech/Lip-sync**: For characters speaking, specify language and accent: "speaking in Spanish with Spanish accent, saying: 'dialogue here'". Note: LTX generates mouth movements but audio will be ambient, not actual speech. For proper voice, generate TTS separately and combine with ffmpeg.
- The negative prompt is built-in: blurry, watermark, subtitles, etc. Use `--negative-prompt "extra terms"` to **append** to the defaults, or prefix with `bash: line 1: to: command not found--negative-prompt "!only these terms"`.

### LTX 2.3 — Consistent Voice via ID-LoRA (for video series)

For multi-clip video series where the same character speaks in every clip, use **ID-LoRA** to achieve consistent voice identity across all videos without relying on external TTS + post-processing.

**What it does**: Uses a 5-second reference audio clip as "voice identity" → LTX 2.3 generates video with audio where the voice matches the reference for every clip, including proper lip-sync.

**Models** (by AviadDahan, trained on LTX 2.3):
- [CelebVHQ-3K](https://huggingface.co/AviadDahan/LTX-2.3-ID-LoRA-CelebVHQ-3K) — better generalization, scene variety, background sounds
- [TalkVid-3K](https://huggingface.co/AviadDahan/LTX-2.3-ID-LoRA-TalkVid-3K) — more speaking styles/voices

**How to use** (ComfyUI workflow by Kijai):
- Download ID-LoRA model to ComfyUI models directory
- Load the [I2V/T2V ID-LoRA workflow](https://huggingface.co/Kijai/LTX2.3_comfy/discussions/40)
- Provide: reference image + 5s reference audio + text prompt with dialogue
- The ID-LoRA node strength controls voice consistency — higher = more consistent
- Uses MelBand RoFormer to extract clean vocal from reference audio automatically

**Advantages over TTS + post-processing**:
- Voice is natively generated by LTX (not pasted on afterward)
- Lip-sync is native (not a separate step)
- Ambient sound + dialogue are generated together coherently
- No ffmpeg audio replacement needed
- Voice stays consistent across clips even when scenes change

**Limitations**:
- ComfyUI must be up-to-date (ID-LoRA support added recently)
- No native voice speed control yet (workaround: insert `....` for pauses)
- Text-to-speech accuracy is improving but not perfect yet

**For custom character voice**: Train your own ID-LoRA using [`ltx-trainer`](https://github.com/Lightricks/ltx-trainer) with clips of the target voice as reference dataset. See `references/ltx-2-3-lora-training.md` for details.

### LTX 2.3 — Visual Character Consistency via Character LoRA

For consistent character appearance across video clips, train a **Character LoRA** or **IC-LoRA** on LTX 2.3:

- **Character LoRA**: Train on still frames of the character → consistent identity in generated videos
- **IC-LoRA**: Structural control — keeps character pose/structure consistent across shots
- **Training**: Use [`ltx-trainer`](https://github.com/Lightricks/ltx-trainer) or AI Toolkit (Ostris) ComfyUI workflow
- **Dataset**: 10-20 still frames from different angles/poses (can be generated with FLUX.1 Dev which excels at character consistency)
- See `references/ltx-2-3-lora-training.md` for full training guide

**Recommended approach for character video series**:
1. Generate reference images with FLUX.1 Dev (best character consistency)
2. Train Character LoRA on those images for LTX 2.3 visual consistency
3. Train ID-LoRA on character voice reference clips for audio consistency
4. Use both LoRAs together in ComfyUI for fully consistent character video clips

Notes (video)
Notes (video)
- Uses LTX 2.3 with a two-pass pipeline: first pass at half-resolution for structure, then latent upscale + refinement for detail.
- Audio is generated automatically alongside the video (ambient sounds, effects). No separate audio step needed.
- **Voice options**: LTX 2.3 has THREE approaches for character voice:
  1. **Built-in voice** (default) — LTX generates ambient audio with mouth movements. Use `--lipsync` + quoted text for lip sync. Voice varies per clip.
  2. **ID-LoRA voice** (consistent) — Uses a 5s reference audio clip to maintain consistent voice identity across clips. See section above. Best for video series.
  3. **External TTS + ffmpeg** — Generate TTS with Qwen3-TTS separately, paste audio onto LTX video. Most control over exact dialogue text, but lip-sync requires the `--lipsync` flag and quoted text in prompt.
- For **video series with recurring characters**: ID-LoRA is preferred for voice consistency; Character LoRA for visual consistency.
- **`--audio`**: optionally provide a local audio file (wav/mp3/ogg/flac/m4a) as a conditioning reference. The model uses it to synchronize video motion to the rhythm, speech, or effects in the audio. The output audio is **regenerated by the model** (not the original file). If the user wants the exact original audio track on the video, replace it afterward with ffmpeg. Can be combined with `--image`.
- Output format is MP4 (auto codec). Compatible with Telegram and most players.
- For image-to-video, `--image` accepts a local path. The script uploads it to the broker automatically.
- `--aspect` and `--resolution` are ignored in i2v mode if the image already defines dimensions (the image is resized to the closest preset).
- Video generation is significantly slower than image generation. A 5s 720p video may take several minutes.
- **CRITICAL**: Always use `exec timeout=1800` for video generation. The default exec timeout (300s) is NOT enough. Example: `exec timeout=1800 uv run {baseDir}/scripts/generate_video.py ...`
- After generation, send the video with the `message` tool: `{ "action": "send", "message": "Aquí va el video", "media": "./output.mp4" }.`.
- One video per invocation. Do not batch video requests.
- **Consistent voice across clips**: See `references/id-lora-voice.md` — ID-LoRA enables voice identity locking with a ~5s reference audio clip. Pre-trained checkpoints available (~1.1 GB each). Requires `--quantize` for <48GB VRAM setups.

---

# ComfyUI Local — Song Generation (ACE Step 1.5)

Use the bundled script to generate songs locally through the broker on the Windows host.

Before calling the script, always send a short confirmation message to the user with the `message` tool. Example: `Ok, voy a generar una canción de 2 minutos de rock épico. Tardará un poco.`

Generate a song (basic)

```bash
uv run {baseDir}/scripts/generate_song.py --tags "rock, epic, female vocals" --filename "output.mp3"
```

Generate a song with lyrics

```bash
uv run {baseDir}/scripts/generate_song.py --tags "pop, ballad, male vocals" --lyrics "Verse 1\nHere are my lyrics...\n\nChorus\nThis is the chorus..." --filename "output.mp3"
```

Generate with custom BPM, key, and duration

```bash
uv run {baseDir}/scripts/generate_song.py --tags "electronic, ambient" --filename "output.mp3" --duration 240 --bpm 90 --key "A minor" --language en
```

Use a reference audio for style/timbre transfer

```bash
uv run {baseDir}/scripts/generate_song.py --tags "rock, guitar" --reference-audio "./media/inbound/reference.mp3" --filename "output.mp3"
```

Tag guide

- Tags describe the genre, style, instruments, and mood: `rock, epic, guitar solo, cinematic, female vocals`
- Multiple tags separated by commas
- Be specific: `hard rock, electric guitar, power ballad` produces better results than just `rock`
- Include vocal type if relevant: `male vocals`, `female vocals`, `duet`, `choir`

Key options

- Format: `<root> <quality>` — e.g. `C major`, `E minor`, `F# minor`, `Bb major`
- All standard roots supported: C, C#, Db, D, D#, Eb, E, F, F#, Gb, G, G#, Ab, A, A#, Bb, B
- Default: `C major`

Language codes

- `es` (Spanish, default), `en` (English), `ja` (Japanese), `zh` (Chinese), `de` (German), `fr` (French), `pt` (Portuguese), `ru` (Russian), `it` (Italian), `ko` (Korean), and more.

Notes (songs)

- Uses ACE Step 1.5 XL Turbo with the 4B decoder and 4B text encoder by default (`--quality xl-turbo`, 8 steps, CFG 1.0). Fast generation with great quality.
- `--quality xl-merge` uses the SFT+Turbo merged model (task arithmetic α=0.5). Same 8 steps as turbo but with blended SFT weights — less artifacts, fewer wrong notes, better structure. Experimental — community feedback is on the 2B version, XL merge is very new.
- `--quality high` uses the original 2B base turbo model with 4B encoder split (8 steps).
- `--quality standard` uses the AIO checkpoint with the smaller encoder (faster, lower quality). Only use as fallback.
- Output format is MP3 at 320kbps. Compatible with Telegram and all players.
- **Lyrics**: Write lyrics in the language matching `--language`. Cocobot should compose the lyrics creatively and pass them via `--lyrics`.
- **Reference audio**: `--reference-audio` sets the timbre/style from another song. The script uploads it to the broker automatically.
- `--quality standard` uses the AIO checkpoint with the smaller encoder (faster, lower quality). Only use as fallback.
- `--format flac` outputs lossless FLAC instead of the default MP3 (320kbps). Use FLAC when audio fidelity matters (master copies, further processing). Default is `mp3` for compatibility.
- Song generation is fast: a 2-minute song typically takes 30-60 seconds.
- After generation, send the song with the `message` tool: `{ "action": "send", "message": "Aquí va la canción", "media": "./output.mp3" }`.
- Use `--count N` (or `-n N`) to generate multiple variations in a single batch. Files are named `output-1.mp3`, `output-2.mp3`, etc. Each gets a different seed automatically.
- **Always use `--count N`** instead of calling the script multiple times — this keeps all requests in the same broker batch and avoids repeated model loading/unloading.

### Edit mode (inpainting a section of a song)

Re-render a specific time range of an existing song (fix vocal quality, change instrumentation, etc.). The rest of the song remains untouched.

Edit a section (fix vocal clarity):

```bash
uv run {baseDir}/scripts/generate_song.py --edit "./original.mp3" --start 45 --end 50 --tags "rock, epic, female vocals" --lyrics "Same lyrics as original..." --filename "./edited.mp3"
```

Edit with stronger denoise (change melody/feel):

```bash
uv run {baseDir}/scripts/generate_song.py --edit "./original.mp3" --start 30 --end 50 --tags "pop, ballad" --lyrics "Same lyrics as original..." --filename "./edited.mp3" --denoise 0.5
```

Edit-specific flags:

| Flag          | Default | Description |
|---------------|---------|-------------|
| `--edit`      | —       | Path to original MP3 (activates edit mode) |
| `--start`     | —       | Start of edit region in seconds (required) |
| `--end`       | —       | End of edit region in seconds (required) |
| `--denoise`   | 0.25    | Regeneration strength (0.05 = subtle, 1.0 = full) |
| `--crossfade` | 0.5     | Crossfade at edit boundaries in seconds |

How it works: the script VAE-encodes the original, runs KSampler with partial denoise on the full latent (preserving structure), then uses ffmpeg to splice only the edit region back into the original with smooth crossfade.

Denoise guide:

| Range       | Use case |
|-------------|----------|
| 0.15 – 0.30 | Fix vocal clarity, clean small artifacts. Preserves temporal structure and lyrics placement. |
| 0.30 – 0.50 | Moderate change: adjust timbre, slight melodic variation. |
| 0.50 – 0.80 | Heavy change: new melody/instrumentation. Lyrics may shift position. |

Notes (edit mode):

- **MUST pass the same `--tags`, `--lyrics`, `--bpm`, `--key`** as the original song — without matching conditioning the edit will sound incoherent.
- **Always include `--lyrics`** even for small edits — without lyrics conditioning the model may generate instrumental-only content in the edit region.
- Duration is auto-detected from the original file (no `--duration` needed).
- `--count` is not supported in edit mode (one edit per invocation).
---

## Sound Effects (SFX) Generation

Model: **Stable Audio Open 1.0** (stabilityai/stable-audio-open-1.0) — 1.2B params, 44.1 kHz stereo output.
VRAM: ~4 GB (FP16). Max duration: ~47 seconds.
Auto-downloads on first run (~5 GB from HuggingFace).

### Direct (WSL, with GPU)

```bash
uv run {baseDir}/scripts/generate_sfx.py --prompt "cat hissing aggressively" --filename ./sfx.wav
uv run {baseDir}/scripts/generate_sfx.py --prompt "thunder rolling in the distance" --duration 10 --filename ./thunder.wav
uv run {baseDir}/scripts/generate_sfx.py --prompt "glass shattering" --count 3 --filename ./glass.wav
```

### Via Broker (from sandbox container)

```bash
python3 {baseDir}/scripts/generate_sfx_broker.py --prompt "rain on a tin roof" --filename /workspace/temp/rain.wav
```

### Options

| Flag                | Default                          | Description |
|---------------------|----------------------------------|-------------|
| `--prompt`          | (required)                       | Text description of the sound effect |
| `--filename`        | (required)                       | Output WAV path |
| `--duration`        | 10.0                             | Duration in seconds (max ~47) |
| `--steps`           | 100                              | Diffusion steps |
| `--guidance`        | 7.0                              | CFG scale |
| `--count`           | 1                                | Number of variations (different seeds) |
| `--negative-prompt` | "Low quality, distorted, noise." | What to avoid |

### Notes

- Output is always 44.1 kHz stereo 16-bit WAV (high quality).
- HuggingFace token required (gated model). Auto-read from `~/.cache/huggingface/token`.
- Multiple prompts + filenames supported: `--prompt "A" "B" --filename a.wav b.wav`
- Broker wrapper uses gpu-exec endpoint (stops llama → runs SFX → restarts llama).

---

## Text-to-Speech (TTS)

Model: **Qwen3-TTS** (1.7B default, 0.6B with `--fast`). Multilingual (Spanish, English, Chinese, etc.).
VRAM: ~6 GB (FP16). Falls back to CPU when insufficient VRAM.

### Via Broker (from sandbox container — preferred)

```bash
python3 {baseDir}/scripts/generate_speech_broker.py --text "¡Miau! Hola Raúl" --filename /workspace/temp/cocobot.wav
python3 {baseDir}/scripts/generate_speech_broker.py --text "Hello world" --ref-audio /workspace/skills/comfyui-local/scripts/assets/ref.wav --ref-text "transcript" --filename /workspace/temp/clone.wav
```

### Direct (WSL, with GPU)

```bash
uv run {baseDir}/scripts/generate_speech.py --text "Hello" --filename ./speech.wav
uv run {baseDir}/scripts/generate_speech.py --text "Hola" --ref-audio ./ref.wav --ref-text "Reference transcript" --filename ./clone.wav
uv run {baseDir}/scripts/generate_speech.py --text "Hi there" --speaker Mochi --instruct "Speak playfully" --filename ./mochi.wav
```

### Modes

1. **Voice clone** (default for Cocobot): `--ref-audio` + `--ref-text` — clones the voice from a reference sample.
2. **Preset speaker**: `--speaker Mochi` + `--instruct "Speak playfully"` — uses built-in voices.
3. **Voice design**: `--design "A warm female voice with a slight accent"` — creates a new character voice from a natural-language description.

### Options

| Flag            | Default | Description |
|-----------------|---------|-------------|
| `--text`        | (required) | Text to synthesize |
| `--filename`    | (required) | Output WAV path |
| `--language`    | auto    | Language override (Spanish/English/Chinese/...) |
| `--fast`        | off     | Use 0.6B model (~3x faster, lower quality) |
| `--ref-audio`   | —       | Reference audio for voice cloning |
| `--ref-text`    | —       | Transcript of the reference audio |
| `--speaker`     | —       | Preset speaker name (Vivian/Mochi/Ryan/...) |
| `--instruct`    | —       | Voice style instruction |
| `--design`      | —       | Natural-language voice description |
| `--max-duration` | 300    | Max output duration in seconds |

### Notes (TTS)

- **CRITICAL: ALWAYS use `generate_speech_broker.py` for TTS.** This is the ONLY correct way to generate speech from the sandbox. It handles the broker gpu-exec swap automatically (stops llama-server → runs TTS on GPU → restarts llama-server). NEVER try to call llama-server's API directly for TTS — llama-server runs the Qwen3.5-27B chat model, NOT a TTS model.
- **NEVER write your own TTS script or try alternative approaches.** The infrastructure is already built and tested. Just call `generate_speech_broker.py` with the right arguments.
- For long texts, split into fragments and call `generate_speech_broker.py` once per fragment. Each call goes through the broker (stop llama → TTS → restart llama), so minimize the number of fragments.
- The `--timeout` flag controls how long the broker waits for the TTS to finish. Default is 900s (15 min). For very long texts, increase it.
- First run may be slow: the TTS model (~3.4 GB) downloads from HuggingFace on first use. Subsequent runs use the cached model.
- Output is always WAV (24 kHz mono). Convert to other formats with ffmpeg if needed.
- English, Spanish, Chinese, and other languages are all supported. Use `--language English` to force English if auto-detection fails.
- If no `--ref-audio` and no `--speaker` and no `--design` are given, the script uses the default Cocobot voice (from `assets/cocobot-voice-ref.wav`).
- Use `exec timeout=900` when calling from sandbox to match the broker timeout.

### TTS — Post-Processing (REQUIRED)

Qwen3-TTS tends to cut off the last syllable of generated speech. This is a known model behavior (see [Qwen3-TTS discussion #161](https://github.com/QwenLM/Qwen3-TTS/discussions/161)).

**Fix: Add trailing silence with ffmpeg AFTER generation:**
```bash
ffmpeg -y -i "input.wav" -filter_complex "[0:a]apad=pad_dur=0.3[s]" -map "[s]" "output.wav"
```
This adds 0.3s of silence at the end, preventing abrupt cuts and giving the final phoneme room to complete. **Always apply this to every TTS clip before video generation.**

### TTS + Video Pipeline (img2video with external audio)

For video series where you need narration in a specific voice (e.g., Cocobot's voice via Qwen3-TTS), use a **two-step pipeline** instead of LTX's built-in voice:

1. **Generate TTS** → `generate_speech_broker.py` (Qwen3-TTS with voice cloning)
2. **Generate image** → `generate_image.py` (FLUX.2 Klein)
3. **Generate video img2video** → `generate_video.py --image frame.png --audio narration.wav --prompt "scene description"`

This gives you full control over the narration voice (cloned from reference) while LTX handles the visual animation synced to the audio rhythm. The output video will have LTX-generated ambient audio, so **replace it with your TTS audio via ffmpeg** after generation:

```bash
ffmpeg -i "video.mp4" -i "narration.wav" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest "final.mp4"
```

### TTS — Pronunciation Fixes

Qwen3-TTS sometimes garbles specific words (especially multi-syllable Spanish words like "transparentes" → "traspafartes"). If Whisper verification shows a word mispronounced:

1. **First attempt**: Regenerate with the word split by hyphens to force syllable-by-syllable pronunciation:
   - `"transparentes"` → `"trans-pa-ren-tes"`
   - `"inteligencia"` → `"in-te-li-gen-cia"`
   - This works because the TTS model treats each hyphenated segment as a separate phoneme group.

2. **If still wrong**: Try phonetic spelling or simplify the word in context.

3. **If neither works**: Accept the minor error — Whisper transcription doesn't always match what humans hear. The audio may sound fine even if Whisper transcribes it wrong. **Always verify by ear when possible.**

**Apply this BEFORE regenerating the entire clip** — only fix the problematic word in the text.

### TTS — Verifying Output (REQUIRED)

After generating TTS clips, verify content with Whisper to ensure correct speech:

```bash
# Use faster-whisper (installed locally) to transcribe and check keyword coverage
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('medium', device='cpu', compute_type='int8')
segs, info = model.transcribe('clip.wav', language='es', beam_size=1)
text = ' '.join([s.text for s in segs]).strip()
print(f'Language: {info.language} ({info.language_probability:.2f})')
print(text)
# Check keywords: sum(1 for kw in ['keyword1','keyword2'] if kw.lower() in text.lower())
# Target: ≥80% keyword coverage
"
```

- Use `faster-whisper` model `medium` with `int8` quantization (fast on CPU).
- Check that detected language matches expected language (probability ≥0.9).
- Verify ≥80% of key content words appear in transcription.
- **If coverage <80%**: regenerate the clip. Common issues: wrong number pronunciation ("1.000" read as "mil mil" instead of "mil"), cut final syllables, or garbled proper nouns.
- **Never summarize or truncate source text to fit 20s limit.** Instead, split the text into 2+ clips. User prefers complete content over clipped summaries.

### TTS — Downloading from Broker

Generated files live on the Windows host (WSL), NOT the sandbox. Download via broker base64 endpoint:

```bash
curl -s -X POST "$BROKER_URL/v1/gpu-exec" \
  -H "Content-Type: application/json" \
  -d '{"command":["base64","path/to/output.wav"],"timeout_seconds":30,"wsl":true}'
```

The response `stdout` contains the base64-encoded WAV. Decode and save locally.

**Do NOT use SSH** to the broker — it times out and is unreliable for file transfer.

**Script `scripts/broker_audio_download.py`** handles batch download + ffmpeg padding in one step. See `references/tts-workflow.md` for the full production pipeline.
