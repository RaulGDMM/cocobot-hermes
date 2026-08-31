---
name: comfyui-local
description: Generate images and videos locally through the Windows ComfyUI broker using FLUX, LTX 2.3, LTX 2.5, and MiniMax H3.
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
| FLUX.1 Dev | `--model flux1-dev` | High | ~8-12s | ~16GB | Good | Character consistency and detailed recurring subjects |
| FLUX.2 Klein 9B | `--model flux2-klein-9b` | Higher | ~3-5s | ~12GB | Excellent | Speed, text rendering, landscapes and iteration |
| Z-Image-Turbo | `--model z-image-turbo` | High | ~1-2s | ~10GB | Excellent, including Spanish | Ultra-fast generation, portraits, HDR-like lighting and text |

FLUX.2 Klein 9B is a distillation of FLUX.2 Dev (32B) into a compact 9B model. It inherits FLUX.2's architecture: better prompt adherence, superior text rendering, improved anatomy, and higher native resolution (4MP vs 1MP). Despite being smaller than FLUX.1 Dev (12B), it outperforms it due to the FLUX.2 architecture.

Z-Image-Turbo is Alibaba Tongyi Lab's distilled 6B S3-DiT model. It uses a Qwen3-4B text encoder, AuraFlow sampling, and 8-step generation. It is the fastest installed option and performed better than FLUX.2 Klein in our Spanish text-rendering comparison.

For video series with recurring characters, prefer FLUX.1 Dev for character reference frames and FLUX.2 Klein for backgrounds, landscapes, text-heavy shots, and rapid iteration.

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

Before image-to-image edits, check the input image dimensions. If the image is larger than about 2MP or its longest side is above 1536px, downscale a temporary copy first and pass that resized file to `--image`. Phone photos such as 3072x4096 will make FLUX.2 Klein sample the full latent and can turn a 3-5s job into many minutes. Prefer a longest side of 1536px for fast edits, 2048px when the user explicitly prioritizes detail, and only keep original size when the user explicitly asks for full-resolution editing.

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

**Input size rule:** In i2i mode, the script does not resize with `--width`/`--height`; the encoded latent comes directly from the input image size. Always inspect and downscale oversized input images before running FLUX.2 Klein i2i. Target ~1-2MP / longest side 1536px by default. This preserves the expected fast path and avoids dynamic VRAM/offload behavior that can make each sampler step take tens of seconds.

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

# ComfyUI Local — Video Generation (MiniMax H3 by default; LTX 2.5 and LTX 2.3 optional)

Use the bundled script to generate videos locally through the broker on the Windows host.

Before calling the script, always send a short confirmation message to the user with the `message` tool. Example: `Ok, voy a generar un video de 5 segundos en 720p de un gato jugando. Tardará unos minutos.`

## MiniMax H3

> **Detailed reference:** Before planning non-trivial H3 work—Ref2VA, continuation, editing, multiple references, dialogue, or performance tuning—read [`references/minimax-h3-guide.md`](references/minimax-h3-guide.md). It contains the official MiniMax/ComfyUI sources, mode-selection rules, prompt structures, continuation recipes, performance findings, and verification checklist.

MiniMax H3 is the default engine because it provides substantially higher visual and audiovisual quality. `--engine minimax-h3` remains accepted when an explicit command is clearer. H3 generates native stereo audio jointly with the video and runs at a fixed 24 fps.

**PDD 8-step is the default sampler (since 2026-08-31).** The script builds the workflow with the official Alibaba PAI PDD Acc LoRAs (`MiniMax-H3-{FL2VA,Ref2VA}-Acc-8Step.safetensors` in `models/pdd_acc/`, node pack `ComfyUI-MiniMax-H3-PDD-Acc`): `MiniMaxH3SigmaShift` (video 12 / audio 3) → `MiniMaxH3PDDAccApply` (nfe 8, lora 1.0, on_off_grid=error) → guider on the patched model, sampler `euler`, sigmas from the Apply node. A/B-validated on this machine: 5s FL2VA 480p 1.63×, 15s Ref2VA 1344×768 3 refs **2.23×** (914s → 410s), no visible degradation, dialogue present. **Only use the classic 20-step `res_multistep` mode when Raúl explicitly asks for it** (`--no-pdd`; keep `--steps 20`). The PDD recipe is fail-closed — the script rejects any `--steps` other than 4/6/8 while PDD is on.

H3 uses the KJNodes `MiniMaxH3MemoryEfficientSageAttentionPatch` by default. This patches only MiniMax H3 transformer blocks; it does not enable SageAttention globally or change LTX workflows. Use `--no-sage-attention` only for troubleshooting or reproducible A/B comparisons against PyTorch attention.

Validated RTX 5090 stack (2026-08-04):

- ComfyUI Python 3.12, PyTorch `2.10.0+cu130`, CUDA 13.0
- `sageattention==2.2.0+cu130torch2.10.0andhigher.post6` (`cp310-abi3-win_amd64`)
- `triton-windows==3.6.0.post26` (Torch 2.10 maps to Triton 3.6; keep it below 3.7)
- KJNodes commit `195d312a251efdc484c3d9c4570914ab2da9da54`
- SageAttention wheel SHA-256: `8a8df597c0c0a874c70b0ce915dedf6ab4a1254d577375939f79b8d2dcb0b195`

A same-prompt, same-seed H3 benchmark at 1344x768, 362 frames, and 20 steps completed in 14m44s with SageAttention versus 30m21s with PyTorch attention (2.06x end-to-end, 51.45% less wall time), with no clear visual degradation. Do not use ComfyUI's global `--use-sage-attention` flag for this setup.

Text-to-video:

```bash
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --prompt 'A cinematic storm over a futuristic city. Stereo audio: rain and distant thunder.' \
  --filename h3-t2v.mp4
```

Image-to-video supports an initial frame, a final frame, or both:

```bash
# Initial frame
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --image first.png --prompt 'The subject turns toward the camera' --filename h3-first.mp4

# Final frame only
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --end-image last.png --prompt 'The scene evolves naturally into the supplied final frame' --filename h3-last.mp4

# Initial and final frames
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --image first.png --end-image last.png --prompt 'A smooth transition between both frames' --filename h3-both.mp4
```

Reference-to-video accepts up to nine images, three videos, and three standalone audio clips, with at most twelve mixed files. Image order defines `<Picture 1>`, `<Picture 2>`, etc.; video order independently defines `<Video 1>`, `<Video 2>`, etc. Audio numbering includes video soundtracks first, followed by standalone `--reference-audio` values. Reference inputs cannot be combined with first/last-frame conditioning.

```bash
uv run {baseDir}/scripts/generate_video.py --engine minimax-h3 \
  --reference-image character.png \
  --reference-video camera-motion.mp4 \
  --prompt 'Use <Picture 1> for character identity and <Video 1> for camera movement and timing. Generate the character walking through a rainy street.' \
  --filename h3-reference.mp4
```

- `--ref-image-size match` is the default and fastest. Use `max` only when stronger identity fidelity justifies much higher compute cost.
- Repeat `--reference-video` up to three times. Each clip must be 2–15 seconds at 23.976–60 fps, and their combined duration cannot exceed 15 seconds.
- Reference videos are normalized locally to 24 fps H.264/AAC before upload so their timing matches H3's local Ref2VA node. Supported inputs: MP4, MOV, WebM, MKV, and AVI.

### H3 Reference Audio & Dialogue

H3 generates native stereo audio including dialogue, SFX, music, and ambience. **Spanish is fully supported** as one of 11 stable dialogue languages (Arabic, Chinese, English, French, German, Italian, Japanese, Korean, Portuguese, Russian, Spanish).

**Dialogue in prompts:** Use speaker labels `(S1)`, `(S2)`, language tags, and `<d>` tags for exact text:
```text
The man (S1) looks at her and says, <d>[Spanish] ¿Estás bien?</d>
She smiles and replies, <d>[Spanish] ¡Ahora sí!</d>
```
For simpler prompts, quotes work too: `speaking in Spanish, saying: "¿Estás bien?"`

**Voice cloning with audio reference:** H3 accepts up to 3 standalone audio clips (2-15s each, 15s total combined) for voice identity transfer. The model clones the voice timbre and cadence from the reference and generates new speech with that voice.

Semantic mode (default): H3 uses the audio for voice identity, words, cadence, timing, music, or sound design, then jointly generates a new AAC stereo soundtrack.
```bash
uv run {baseDir}/scripts/generate_video.py \
  --reference-image portrait.png \
  --reference-audio speech.wav \
  --prompt 'Use <Picture 1> as the speaker and <Audio 1> for voice, words, timing, and lip movement.' \
  --filename h3-semantic-audio.mp4
```

Exact mode adds `--preserve-reference-audio`: H3 still conditions mouth and motion on `<Audio 1>`, then the script replaces the generated soundtrack with the complete original recording encoded as 16-bit ALAC lossless. The output duration follows the reference audio automatically; any explicit `--duration` is ignored. Exact mode accepts exactly one standalone audio reference.

```bash
uv run {baseDir}/scripts/generate_video.py \
  --reference-image portrait.png \
  --reference-audio speech.wav \
  --preserve-reference-audio \
  --prompt 'Use <Picture 1> as the speaker. Match mouth and jaw movement to every syllable and timestamp in <Audio 1>.' \
  --filename h3-exact-audio.mp4
```

- Exact mode preserves the decoded PCM16 samples and original sample rate/channel count; it does not merely re-encode to AAC.
- H3 produces visible speaking motion and joint audiovisual timing, but phoneme-perfect lip sync is not guaranteed. Inspect the result temporally for production use.
- When reference videos contain audio, their soundtracks consume the first `<Audio N>` tags. The CLI prints the actual tag assigned to each standalone audio.
- H3 supports 1–15 seconds; frame counts are automatically aligned to the model's 17k+5 temporal grid.
- H3 presets are multiples of 32. Its `720p` preset maps to the native 1344×768 canvas.
- Do not combine H3 with LTX-only flags such as `--audio`, `--lipsync`, or `--id-lora`.
- The broker prepares prompts and uploads while Qwen is active, unloads llama.cpp for the GPU job, and restores the exact Qwen profile afterward.
- **Pitfall — repo/venv drift breaks ComfyUI startup (seen 2026-08-21):** ComfyUI Desktop auto-updated the repo which now imports `ColorPrimaries`/`ColorTrc` from `av.video.reformatter` (needs PyAV ≥ 17, PR #2175) while `C:\ComfyUI\.venv` still had `av 16.1.0` → broker logs `RuntimeError: ComfyUI exited during startup` and every job fails with HTTP 500. **Diagnose via the last traceback in `E:\Workspace\Hermes\comfyui-process.log`.** RESOLVED 2026-08-21:
  1. `uv pip install --python 'C:\ComfyUI\.venv\Scripts\python.exe' --upgrade 'av>=17'` → installed av 18.1.0. (cmd.exe mangles `"` quotes for uv — use PowerShell single-quotes, e.g. `powershell -NoProfile -Command "& uv pip install --python 'C:\ComfyUI\.venv\Scripts\python.exe' --upgrade 'av>=17'"`.)
  2. Bump the repo pin `E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\requirements.txt`: `av>=16.0.0` → `av>=17.0.0` (the old pin let the stale venv pass checks on future upgrades).
  3. Verify: `C:\ComfyUI\.venv\Scripts\python.exe -c "from av.video.reformatter import ColorPrimaries, ColorRange, ColorTrc"` → IMPORT_OK.
  Note: a 404 on broker `GET /v1/health` is NORMAL for this broker build — no health route; the broker is fine when the ComfyUI subprocess crashes.

## LTX 2.5

LTX 2.5 (Lightricks, 2026) is the newest LTX generation: a 22B distilled transformer that jointly generates **video + stereo audio** with fixed sigma schedules. It must be selected explicitly with `--engine ltx25`.

Quality sits between H3 and LTX 2.3; it is faster than H3 and has better prompt adherence and audio than 2.3. Use it when you want native audio generation with LTX-style speed, or as an A/B alternative to H3.

Text-to-video:

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx25 \
  --prompt "A red fox leaping across a snowy forest at golden hour, cinematic" \
  --filename output-t2v.mp4
```

Image-to-video (first frame):

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx25 \
  --image first.png --prompt "The scene comes alive, camera slowly pushes in" \
  --filename output-i2v.mp4
```

First+last-to-video (interpolate between two frames):

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx25 \
  --image first.png --end-image last.png --prompt "A smooth transition between both frames" \
  --filename output-flf.mp4
```

- Pipeline (mirrors the official Comfy-Org `video_ltx2_5_t2v/i2v/flf2v` templates): t2v/i2v run **two stages** — stage 1 at half resolution (8-sigma distilled schedule) → `LTXVLatentUpsampler` x2 → stage 2 refinement (4-sigma schedule). flf2v runs a **single full-resolution pass** (12-sigma schedule) with `LTXVAddGuide` on frame 0 and frame -1 (strength 0.7) plus `LTXVCropGuides`.
- Sampling: `SamplerCustomAdvanced` + `euler_ancestral`, `LTXVDualCFGGuider` cfg 1/1, `ManualSigmas` — the distilled model ignores `--steps`; it prints 20 but the schedule is fixed. `--fps` is fixed at 24.
- Audio is generated natively (no `--audio` conditioning in 2.5). Frame grid: 8k+1 (73 frames for 3s).
- Models (in `F:\ComfyUIModels`): `diffusion_models/ltx-2.5-22b-distilled-int8-convrot.safetensors`, `clip/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` (`CLIPLoader type="ltxv"`), `vae/ltx-2.5-vae.safetensors`, `vae/ltx-2.5-vae-encoder.safetensors`, `loras/ltx-2.5-32x-upscale.safetensors` (latent upscaler via `LatentUpscaleModelLoader`).
- Not available in 2.5 (script rejects): `--audio`, `--lipsync`, `--id-lora`, `--reference-audio`, `--preserve-reference-audio`, `--reference-image/-video`.
- 720p 3s measured on RTX 5090 (2026-08-27): t2v 45 s, i2v 44 s, flf2v 61 s. 1080p works but is ~2x slower; prefer 720p for iteration.

## LTX 2.3

LTX 2.3 is the faster fallback and must be selected explicitly with `--engine ltx23`. Use it when speed, supplied-audio conditioning, lip-sync, or ID-LoRA matters more than H3's higher generation quality.

Text-to-Video (basic)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --prompt "A cat chasing a laser pointer across a living room" --filename "output.mp4"
```

Image-to-Video (animate a first frame)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --image "./first-frame.png" --prompt "The camera slowly zooms in while flowers sway in the wind" --filename "output.mp4"
```

Audio-conditioned video (the video follows the audio)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --audio "./music.mp3" --prompt "A DJ mixing tracks in a neon club" --filename "output.mp4"
```

Image + Audio (first frame + audio conditioning)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --image "./scene.png" --audio "./narration.wav" --prompt "The narrator describes the scene" --filename "output.mp4"
```

Lip-sync mode (best for talking heads / singing)

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --lipsync --image "./portrait.png" --audio "./speech.wav" --prompt "A woman speaking directly to camera" --filename "lipsync_output.mp4"
```

- Requires both `--image` (face/portrait) and `--audio` (speech/singing audio).
- Internally uses MelBand RoFormer to isolate vocals from the audio, then conditions video generation on the clean vocal track via a dedicated Audio VAE.
- Produces significantly better lip synchronisation than regular `--image --audio` (which treats audio as ambient conditioning).
- **The output video keeps the original audio track** — the script automatically replaces the model-generated audio with the input audio via ffmpeg after generation.
- Best results with: clear frontal face, clean speech audio, 3-8 second clips.

**Lip-sync prompt rules:**
- Include the exact spoken text in quotes and identify the language/accent so the mouth motion has matching phonetic guidance.
- Analyze the source image before writing the prompt, especially for panels, ornamental frames, or multi-subject compositions.
- Default to a static camera for structured source images; zooms and pans can deform their layout.

Custom duration, resolution, and aspect ratio

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --prompt "A drone shot over a mountain range at sunset" --filename "output.mp4" --duration 10 --resolution 1080p --aspect 16:9
```

**🚫 Avoid editing `generate_video.py` unless you are explicitly asked to update the workflow itself. It already encodes the official LTX 2.3 ID-LoRA template (two-stage distilled pipeline). Just call it with `--engine ltx23 --id-lora`.**

ID-LoRA mode (consistent voice identity from a 5-second reference)

ID-LoRA transfers the voice identity from a ~5-second audio reference to generate new speech with the same voice. The model generates both video and audio jointly — no separate TTS step needed. Lip-sync is built-in.

**⚠️ IMPORTANT: Always use the script below. Do NOT construct the ComfyUI workflow JSON manually — the ID-LoRA pipeline mirrors the official `video_ltx2_3_id_lora` ComfyUI template (BF16 checkpoint `ltx-2.3-22b-dev.safetensors` + distilled LoRA + ID-LoRA stacked, two-stage low/high-res with `LTXVLatentUpsampler`, `CFGGuider` cfg=1.0, `euler_ancestral_cfg_pp` / `euler_cfg_pp`, `ManualSigmas`). All the node wiring is handled internally by `generate_video.py --engine ltx23 --id-lora`.**

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --id-lora \
  --image "./portrait.png" \
  --reference-audio "./voice_sample.wav" \
  --identity-guidance-scale 1.5 \
  --prompt "[VISUAL]: A person speaks to camera in a cozy room. The character opens its mouth wide to speak clearly, its jaw moving with each word [SPEECH]: Hello, this is what I want to say [SOUNDS]: warm indoor ambience, soft echo" \
  --filename "output.mp4"
```

- Requires `--image` (first frame, ideally a face/portrait) and `--reference-audio` (5-second voice sample for identity).
- The reference audio defines WHO speaks (voice timbre, pitch, cadence). The `[SPEECH]` tag in the prompt defines WHAT they say.
- The model generates the actual spoken words with the reference voice identity — unlike regular `--audio` mode which only generates ambient sounds.
- **Prompt format for ID-LoRA** — use structured tags:
  - `[VISUAL]:` — Scene description (what the camera sees)
  - `[SPEECH]:` — Exact words the character says (the model will synthesize these)
  - `[SOUNDS]:` — Vocal quality descriptors + ambient sounds (e.g. "deep male voice, room reverb, rain outside")
- `--identity-guidance-scale N` (default 3.0) — Controls how strongly the voice identity is preserved. Higher = more faithful to reference but less natural. Range 0-10, sweet spot is 2.0-5.0. **For lip-sync: use 1.5** — lower guidance allows more facial movement while preserving voice identity. Tested and confirmed working on RTX 5090 with full BF16 model.
- **Language note**: ID-LoRA was trained primarily on English (CelebV-HQ + TalkVid datasets). Spanish works but quality may vary — the voice identity transfers well, but pronunciation/prosody may be less natural than English. Try it and iterate.
- Best results with: clear 5s voice sample (no background noise), frontal face image, short clips (3-8s).
- Can be combined with `--duration`, `--resolution`, `--aspect`, `--steps`, `--seed`.
- **Do NOT combine** with `--lipsync` or `--audio` — ID-LoRA handles voice generation internally.
- **Do NOT build the workflow JSON manually** — always call `generate_video.py --engine ltx23 --id-lora` which handles all the complex node wiring internally.

**💡 ID-LoRA — Lip-sync & quality tips (tested on RTX 5090):**
1. **Use `--identity-guidance-scale 1.5`** (not the default 3.0) — lower guidance = more facial movement while keeping voice identity
2. **Add mouth movement to `[VISUAL]`**: "The character opens its mouth wide to speak clearly, its jaw moving with each word"
3. **Use BF16 checkpoint** (`ltx-2.3-22b-dev.safetensors`) — the full model works fine with memory swap and produces better visuals/lip-sync than FP8. Script's `MODEL_IDLORA_CHECKPOINT` is set to BF16.
4. **Audio glitches at the start**: If you hear artifacts before the main speech, regenerate with a different seed — it's random and usually clears on the second try
5. **Model location**: User models are in `F:\ComfyUIModels` (not the default ComfyUI path)
6. **Text length**: Keep `[SPEECH]` to ~10s of spoken text. Longer text (>15s) causes truncation and garbled output. Split into multiple clips if needed.

**⚠️ ID-LoRA rigidity problem (KNOWN):**
At `strength_model: 1.0` the video is **extremely static/rigid** — barely any motion. Fixes: lower `--identity-guidance-scale` to **1.5** or switch to **CelebVHQ checkpoint** (better motion than TalkVid).

ID-LoRA examples:

Same character, different lines (voice stays consistent across videos):

```bash
# First video
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --id-lora \
  --image "./gato.png" --reference-audio "./gato_voice.wav" \
  --identity-guidance-scale 1.5 \
  --prompt "[VISUAL]: A black cat speaks to camera. The character opens its mouth wide to speak clearly, its jaw moving with each word [SPEECH]: Yo soy el guardian de los secretos [SOUNDS]: deep mysterious male voice, echo" \
  --filename "scene1.mp4"

# Second video — same voice reference, different text
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --id-lora \
  --image "./gato.png" --reference-audio "./gato_voice.wav" \
  --identity-guidance-scale 1.5 \
  --prompt "[VISUAL]: The same black cat turns to look at something off-screen. Opens its mouth wide to speak clearly [SPEECH]: Los humanos no comprenden nuestro poder [SOUNDS]: deep mysterious male voice, wind" \
  --filename "scene2.mp4"
```

### Visual character consistency across clips

- Generate the initial reference set with FLUX.1 Dev when identity consistency matters most.
- For stronger persistence, train an LTX 2.3 Character LoRA from 10–20 varied frames; use IC-LoRA when pose or structural control is the priority.
- Character LoRA and ID-LoRA can be combined to keep visual and voice identity consistent. See `references/ltx-2-3-lora-training.md` and `references/id-lora-voice.md`.

Optional quality controls

```bash
uv run {baseDir}/scripts/generate_video.py --engine ltx23 --prompt "description" --filename "output.mp4" --steps 24 --seed 42
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
- **Speech/Lip-sync**: LTX 2.3 can generate real spoken dialogue natively. Specify the language/accent and put the exact line in quotes, for example: `speaking in Spanish with a Spanish accent, saying: "Hola"`.
- The negative prompt is built-in: blurry, watermark, subtitles, etc. Use `--negative-prompt "extra terms"` to **append** to the defaults, or prefix with `--negative-prompt "!only these terms"` to replace entirely.

Notes (video)
Notes (video)
- Uses LTX 2.3 with a two-pass pipeline: first pass at half-resolution for structure, then latent upscale + refinement for detail.
- Audio is generated automatically alongside the video (ambient sounds, effects). No separate audio step needed.
- **Voice generation**: LTX 2.3 generates real voices and spoken words jointly with video. State the language explicitly and quote the exact dialogue. ID-LoRA adds consistent voice identity from a reference sample; `--lipsync` is for matching a supplied audio recording.
- **`--audio`**: optionally provide a local audio file (wav/mp3/ogg/flac/m4a) as a conditioning reference. The model uses it to synchronize video motion to the rhythm, speech, or effects in the audio. The output audio is **regenerated by the model** (not the original file). If the user wants the exact original audio track on the video, replace it afterward with ffmpeg. Can be combined with `--image`.
- Output format is MP4 (auto codec). Compatible with Telegram and most players.
- For image-to-video, `--image` accepts a local path. The script uploads it to the broker automatically.
- `--aspect` and `--resolution` are ignored in i2v mode if the image already defines dimensions (the image is resized to the closest preset).
- Video generation is significantly slower than image generation. A 5s 720p video may take several minutes.
- **CRITICAL**: Always use `exec timeout=1800` for video generation. The default exec timeout (300s) is NOT enough. LTX example: `exec timeout=1800 uv run {baseDir}/scripts/generate_video.py --engine ltx23 ...`
- After generation, send the video with the `message` tool: `{ "action": "send", "message": "Aquí va el video", "media": "./output.mp4" }`.
- One video per invocation. Do not batch video requests.

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
- For production clips, add 0.3s trailing silence and verify the spoken content with Whisper before using it in video. The complete generate/download/pad/verify procedure is in `references/tts-workflow.md`.
