# TTS Production Workflow

Full pipeline for generating, downloading, padding, and verifying TTS clips via the ComfyUI broker.

## Pipeline Steps

1. **Generate** via `generate_speech_broker.py` (sends job to broker GPU)
2. **Download** via broker base64 endpoint (NOT SSH)
3. **Pad** with ffmpeg `apad=pad_dur=0.3` (+0.3s silence at end)
4. **Verify** with faster-whisper (≥80% keyword coverage, correct language)

## Step 1: Generate

```bash
python3 scripts/generate_speech_broker.py \
  --text "exact text here" \
  --filename "output/clip_name.wav" \
  --broker-url http://172.23.176.1:8791
```

- Files are generated on the Windows host at the relative path from CWD.
- **Max duration**: Keep clips <20s. If text is too long, split into 2+ clips.
- **Never summarize or truncate text** to fit time limits — always split.

## Step 2: Download (base64 via broker)

```bash
curl -s -X POST "$BROKER_URL/v1/gpu-exec" \
  -H "Content-Type: application/json" \
  -d '{"command":["base64","path/to/clip_name.wav"],"timeout_seconds":30,"wsl":true}'
```

Response contains `stdout` with base64 WAV data. Decode with Python:
```python
import base64, json, sys
d = json.load(sys.stdin)
data = base64.b64decode(d["stdout"].strip())
open("clip_name.wav", "wb").write(data)
```

**⚠️ Do NOT use SSH** — it times out. The broker gpu-exec endpoint is the only reliable method.

For batch downloads, use `scripts/broker_audio_download.py` which handles download + padding in one pass.

## Step 3: Pad with ffmpeg

```bash
ffmpeg -y -i "clip.wav" -filter_complex "[0:a]apad=pad_dur=0.3[s]" -map "[s]" "clip_padded.wav"
```

- **Why**: Qwen3-TTS cuts the last syllable (known issue, [GitHub #161](https://github.com/QwenLM/Qwen3-TTS/discussions/161)).
- **How much**: 0.3s silence is sufficient. Tested across 45+ clips.
- This gives the final phoneme room to complete and prevents abrupt cuts in video concatenation.
- **Alternative**: The dummy suffix `... ^.◦` appended to input text was tried but proved unreliable — ffmpeg padding is the proven solution.

## Step 4: Verify with Whisper

```bash
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('medium', device='cpu', compute_type='int8')
segs, info = model.transcribe('clip.wav', language='es', beam_size=1)
text = ' '.join([s.text for s in segs]).strip()
kws = ['keyword1', 'keyword2', 'keyword3']
found = sum(1 for kw in kws if kw.lower() in text.lower())
pct = found/len(kws)*100
print(f'{pct:.0f}% — {\"✅\" if pct>=80 else \"❌\"} ({info.language} {info.language_probability:.2f})')
"
```

- **Model**: `faster-whisper` medium with `int8` quantization (fast on CPU, ~10s per clip)
- **Language check**: Detected language must match expected (probability ≥0.9)
- **Keyword coverage**: ≥80% of key content words present
- **If <80%**: Regenerate. Common issues:
  - Number pronunciation: "1.000" → "mil mil" instead of "mil" (fix: write "MIL" in caps)
  - Cut final syllables (fix: verify padding was applied)
  - Garbled proper nouns (fix: try phonetic spelling)

## Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| Last syllable cut | Qwen3-TTS model behavior | Add 0.3s padding with ffmpeg |
| "mil mil" instead of "mil" | Number "1.000" misread | Write "MIL" or "UN MIL" in caps |
| "pesquetería" mispronounced | Uncommon word | Try "pesquería" (more common) |
| Audio >20s | Text too long for TTS speed | Split into 2+ clips, never summarize |
| Missing content | Summarized text to fit | Include ALL source text, split clips |
