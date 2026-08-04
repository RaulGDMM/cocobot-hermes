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

- **Native support**: ComfyUI merged PR #13111 — `LTXVReferenceAudio` node is now built-in (no custom nodes needed).
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
- Insert dots `"...."` to force short pauses
- Use multi `[speech]` inputs with contextual pause markers
- Provide slower-paced reference audio

## Future Roadmap

- Long-video workflow with overlapping frames for voice consistency across cuts
- V2V variant (add consistent speech to existing silent videos)
- Specialized "Dub it" and "Just talk" workflows
