# ID-LoRA Voice Consistency for LTX 2.3

## Overview
ID-LoRA (Identity-Driven In-Context LoRA) enables consistent voice identity across LTX 2.3 video generations. A single ~5-second reference audio clip "locks" a voice identity that persists across all generated clips.

**GitHub**: https://github.com/ID-LoRA/ID-LoRA
**Paper**: https://id-lora.github.io/

## Pre-trained Checkpoints (ready to use — no training needed)

| Checkpoint | Dataset | Speakers | Rank | Size | Link |
|---|---|---|---|---|---|
| LTX-2.3-ID-LoRA-CelebVHQ-3K | CelebV-HQ | 872 | 128 | ~1.1 GB | [AviadDahan/LTX-2.3-ID-LoRA-CelebVHQ-3K](https://huggingface.co/AviadDahan/LTX-2.3-ID-LoRA-CelebVHQ-3K) |
| LTX-2.3-ID-LoRA-TalkVid-3K | TalkVid | 1,973 | 128 | ~1.1 GB | [AviadDahan/LTX-2.3-ID-LoRA-TalkVid-3K](https://huggingface.co/AviadDahan/LTX-2.3-ID-LoRA-TalkVid-3K) |

**Model selection**: CelebVHQ = better scene variety + generalization. TalkVid = more speaker styles/voices. A combined checkpoint is planned.

## How It Works

1. **Reference audio**: ~5 seconds of the target voice (WAV, PCM 16-bit, 24kHz mono). This is the OPTIMAL length — the model was trained on 5-second clips. Shorter or longer clips may degrade quality.
2. **First frame image**: Reference image for visual conditioning.
3. **Structured prompt**: Text prompt with three tagged sections:
   ```
   [VISUAL]: <scene and appearance description>
   [SPEECH]: <exact words the person should say>
   [SOUNDS]: <speaker vocal style + ambient/environmental sounds>
   ```
4. **Generation**: LTX 2.3 + ID-LoRA generates video + synchronized audio with the reference voice.

**Key insight**: The 5-second audio is a *fingerprint*, not a playback clip. The model extracts voice identity and generates any duration of speech with that voice.

## ComfyUI Integration

- **Nodes required**: The ID-LoRA workflow uses `LTXVReferenceAudio`, `LTXVAddGuide`, `LTXVCropGuides`, `IDGuider`, and `MultimodalGuider`. These nodes were merged into core ComfyUI in PR #13111+, but **your ComfyUI version may not include them yet**.
- **⚠️ If you get HTTP 500 from the broker with `--id-lora`**: This almost always means ComfyUI doesn't recognize one of the ID-LoRA nodes. Check the ComfyUI process log (`comfyui-process.log` on the Windows host) for the specific missing node name. Fix: update ComfyUI to latest, or install the `ID-LoRA-LTX2.3-ComfyUI` custom node extension.
- **Workflow**: Kijai has a production-ready workflow: [Kijai/LTX2.3_comfy discussions/40](https://huggingface.co/Kijai/LTX2.3_comfy/discussions/40)
- **Voice cleanup**: Workflow includes MelBand RoFormer node to isolate clean vocals from reference audio.

## CLI Usage

```bash
python infer.py \
  --lora-path /path/to/LTX-2.3-ID-LoRA-CelebVHQ-3K.safetensors \
  --reference-audio ./voice_ref.wav \
  --first-frame ./scene.png \
  --prompt "[VISUAL]: A robot cat speaking...
[SPEECH]: 'Exact dialogue text here'
[SOUNDS]: Robotic mechanical voice, conversational tone" \
  --width 1024 --height 576 --num-frames 121
```

**Key parameters**:
- `--quantize` — Enables int8 quantization (reduces VRAM ~30-40%, essential for <48GB setups)
- `--identity-guidance-scale` (default 3.0) — Increase for stronger voice consistency
- `--video-guidance-scale` (default 3.0)
- `--audio-guidance-scale` (default 7.0)

## Inference Modes

| Mode | Resolution | Steps | Best For |
|---|---|---|---|
| Two-Stage | 512→1024 (2x upscale) | 30 | Higher quality |
| Two-Stage HQ | 512→1024 (Res2s sampler) | 15 | Maximum fidelity (LTX-2.3 only) |
| One-Stage | 512x512 | 30 | Fast inference / Low VRAM |

## VRAM Requirements

- LTX 2.3 base: ~47 GB
- ID-LoRA checkpoint: ~1.1 GB
- Total unquantized: ~48 GB
- With `--quantize` (int8): ~30-35 GB (fits on RTX 5090 32GB)

## Voice Reference Audio Preparation

```bash
# Extract 5-second reference from existing TTS clip
ffmpeg -y -i input.wav -t 5 -acodec pcm_s16le -ar 24000 -ac 1 voice_ref.wav
```

**Format**: WAV, PCM 16-bit, 24kHz, mono. Choose a clean 5-second segment where the voice is clear and representative.

## Pipeline Comparison

### Current pipeline (TTS + img2video):
```
Imagen + TTS externo (Qwen3-TTS) → LTX 2.3 img2video con lipsync → ffmpeg replace audio
```

### With ID-LoRA:
```
Imagen + audio referencia 5s + prompt estructurado → LTX 2.3 + ID-LoRA → video con voz consistente
```

**Trade-offs**:
- ID-LoRA = consistent voice across ALL clips, no TTS dependency, native audio
- ID-LoRA = less precise text rendering (model interprets prompt, doesn't read exact text)
- TTS pipeline = exact text control but inconsistent lip sync and variable voice quality

## Voice Speed Control (Workarounds)

No native parameter yet. Community-tested approaches:
- Insert dots `""....""` to force short pauses
- Use multi `[speech]` inputs with contextual pause markers
- Provide slower-paced reference audio

## ⚠️ Known Problem: ID-LoRA Rigidity / Suppressed Motion

**Symptom**: Generated video is extremely static — barely any camera movement, subject motion, or natural motion. The character stays "frozen" despite prompts for movement.

**Root cause**: `strength_model: 1.0` on the ID-LoRA node (`build_idlora_workflow` in `generate_video.py`) anchors the identity so strongly it suppresses temporal coherence and motion. This is a **known upstream issue** — [LTX-2.3 Discussion #36](https://huggingface.co/Lightricks/LTX-2.3/discussions/36) confirms LoRA at full weight kills motion.

**Fixes to try (in order of preference)**:
1. **Lower `strength_model` from 1.0 to 0.5–0.7** — edit `generate_video.py` in the `build_idlora_workflow` function. This preserves identity while restoring natural movement.
2. **Switch to CelebVHQ checkpoint** — see comparison table below. CelebVHQ was trained on more action/scene variety and naturally produces better motion than TalkVid.

### Checkpoint Comparison (TalkVid vs CelebVHQ)

Both are ~1.1GB LoRA adapters (rank 128, 3k training steps) that stack on the LTX 2.3 base checkpoint. The base precision (BF16/FP8) applies to the diffusion model, not the adapter.

| Aspect | TalkVid-3K | CelebVHQ-3K |
|--------|-----------|-------------|
| **Dataset** | TalkVid (1,973 speakers) | CelebV-HQ (872 speakers) |
| **Strength** | More voice styles, better for talking-head scenarios | Better scene variety, more natural motion |
| **Motion** | More rigid (trained on static-face talking videos) | Better (trained on clips with more action/movement) |
| **Best for** | Voice consistency, dialogue scenes | Dynamic scenes, camera movement, action |

## Text Length Limitation

**Keep `[SPEECH]` to ~10s of spoken text.** Longer prompts (>15s) cause:
- Audio truncation (speech cuts off mid-sentence)
- Garbled speech at the start ("Coco Bott", "Guayanda" artifacts)
- Voice identity degradation toward the end

**Fix**: Split long text into ~10s segments and generate multiple clips, then concatenate with ffmpeg.

## Model Precision: BF16 (recommended) vs FP8

**BF16 is the recommended default** for ID-LoRA on RTX 5090 (32GB). The script uses the full BF16 model `ltx-2.3-22b-dev.safetensors` which fits in VRAM with memory swap and produces noticeably better visuals and lip-sync than FP8.

| Setting | VRAM | Quality | Speed | When to use |
|---------|------|---------|-------|-------------|
| **BF16 (full)** | ~48GB | ✅ Best | Slow | RTX 5090 (32GB) — DEFAULT |
| **FP8 (quantized)** | ~30-35GB | Good | Faster | Quick iterations, fallback |

**The script (`generate_video.py`) uses BF16 by default** (`MODEL_IDLORA_CHECKPOINT = "ltx-2.3-22b-dev.safetensors"`). On RTX 5090 (32GB), it fits with memory swap.

## Lip-sync Optimization (tested, working)

These parameters were confirmed during session testing (2026-05-08):

1. **`--identity-guidance-scale 1.5`** (not the default 3.0) — lower guidance = more facial movement while keeping voice identity
2. **Add mouth movement to `[VISUAL]`**: `"The character opens its mouth wide to speak clearly, its jaw moving with each word"`
3. **Use BF16 checkpoint** — produces better visuals/lip-sync than FP8
4. **Audio glitches at the start**: If you hear artifacts before the main speech, regenerate with a different seed — it's random and usually clears on the second try

## Session Test Results

- **Project**: Biblia Apocalíptica — gato negro con voz profunda
- **Voice ref**: `biblia-gato-video/fuente/sello2/clip1_barcanas.mp4` (seg 1-6)
- **Image**: `biblica-apocaliptica-gato-negro/test_gato_negro.png`
- **Prompt**: `[VISUAL]:... [SPEECH]: "El poder corrompe, y los gatos aún más" [SOUNDS]:...`
- **Output**: 10s, 1280x704, 25fps, ~6.7MB (BF16)
- **Whisper transcription**: ✅ Correct ("El poder corrompe y los gatos aún más")
- **Lip-sync**: ✅ Improved with guidance 1.5 + mouth movement prompt
- **Model location**: `F:\ComfyUIModels` (Windows host)
- **Rigidity**: ⚠️ Confirmed — video was very static/rigid despite prompts for camera movement. `strength_model: 1.0` is the cause. Pending fix (lower to 0.5-0.7 or switch to CelebVHQ checkpoint). User paused further tests pending decision.
- **Text length**: ⚠️ Clips >10s show truncation and artifacts. ~10s segments are the sweet spot.
- **Glitch artifacts**: ⚠️ Initial clips had audio glitches ("Coco Bott", "Guayanda") — resolved by regenerating with different seed.

## Future Roadmap

- Long-video workflow with overlapping frames for voice consistency across cuts
- V2V variant (add consistent speech to existing silent videos)
- Specialized "Dub it" and "Just talk" workflows
