#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "qwen-tts>=0.1.0",
#     "soundfile",
# ]
# ///
"""Generate speech locally using Qwen3-TTS (voice cloning / custom voice).

Auto-detects GPU: uses CUDA (FP16) when enough VRAM is free, otherwise
falls back to CPU (FP32). Model weights and uv venv are cached in
/workspace/.cache/ so they survive Docker container rebuilds.

Modes:
  1. Voice clone (default for Cocobot):
       --ref-audio ./assets/cocobot-voice-ref.wav --ref-text "transcript"
  2. Custom voice (preset speakers):
       --speaker Mochi --instruct "Speak playfully"
  3. Voice design (create a new character voice):
       --design "A playful cat-robot with a high-pitched cheerful tone"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Persistent cache dirs — survive container rebuilds
# ---------------------------------------------------------------------------
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", "/workspace"))
CACHE_BASE = WORKSPACE / ".cache"

os.environ.setdefault("UV_CACHE_DIR", str(CACHE_BASE / "uv"))
os.environ.setdefault("HF_HOME", str(CACHE_BASE / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(CACHE_BASE / "huggingface" / "hub"))
# Avoid OMP thread oversubscription on high-core-count machines
os.environ.setdefault("OMP_NUM_THREADS", "4")

# Default models (1.7B — higher quality, slower on CPU)
MODEL_BASE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
MODEL_CUSTOM = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
MODEL_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"

# Fast models (0.6B — lower quality, ~3x faster on CPU)
MODEL_BASE_FAST = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
MODEL_CUSTOM_FAST = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

# Default reference audio for Cocobot (created once, reused forever)
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REF_AUDIO = SCRIPT_DIR / "assets" / "cocobot-voice-ref.wav"
DEFAULT_REF_TEXT_FILE = SCRIPT_DIR / "assets" / "cocobot-voice-ref.txt"


# Approximate VRAM requirements (BF16) including speech tokenizer (~1.3 GB)
# Conservative: add ~1.5 GB headroom for CUDA context + generation buffers
VRAM_NEEDED_06B = 3.5   # GB — 0.6B model (BF16)
VRAM_NEEDED_17B = 6.0   # GB — 1.7B model (BF16)


def estimate_vram(model_name: str) -> float:
    """Return approximate VRAM needed in GB for a model."""
    if "0.6B" in model_name:
        return VRAM_NEEDED_06B
    return VRAM_NEEDED_17B


def pick_device(requested: str, model_name: str) -> tuple:
    """Pick (device, dtype). 'auto' tries CUDA if enough VRAM is free."""
    import torch

    if requested != "auto":
        # GPU: use BF16 (model's native format). CPU: use FP32 (BF16 slow on CPU).
        if "cuda" in requested:
            dtype = torch.bfloat16
        else:
            dtype = torch.float32
        return requested, dtype

    # Auto-detect
    if not torch.cuda.is_available():
        print("CUDA not available, using CPU (FP32)", file=sys.stderr)
        return "cpu", torch.float32

    free_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)
    needed = estimate_vram(model_name)
    print(f"CUDA available — {free_gb:.1f} GB free, need ~{needed:.1f} GB", file=sys.stderr)

    if free_gb < needed:
        print("Not enough free VRAM, falling back to CPU (FP32)", file=sys.stderr)
        return "cpu", torch.float32

    print("Using CUDA (BF16)", file=sys.stderr)
    return "cuda:0", torch.bfloat16


def load_model(model_name: str, device: str = "auto", compile_model: bool = False):
    """Load a Qwen3-TTS model with auto device/dtype selection."""
    import torch
    from qwen_tts import Qwen3TTSModel

    device, dtype = pick_device(device, model_name)
    print(f"Loading model {model_name} on {device} ({dtype})...", file=sys.stderr)

    # Pick best attention implementation:
    #  - flash_attention_2 if flash-attn is installed (fastest)
    #  - sdpa (PyTorch native, no extra install) otherwise
    try:
        from transformers.utils import is_flash_attn_2_available
        if is_flash_attn_2_available():
            attn_impl = "flash_attention_2"
        else:
            attn_impl = "sdpa"
    except ImportError:
        attn_impl = "sdpa"
    print(f"Attention: {attn_impl}", file=sys.stderr)

    t0 = time.time()
    model = Qwen3TTSModel.from_pretrained(
        model_name,
        device_map=device,
        dtype=dtype,
        attn_implementation=attn_impl,
    )
    print(f"Model loaded in {time.time() - t0:.1f}s", file=sys.stderr)
    if compile_model and "cuda" in str(device):
        import torch
        print("Compiling talker with torch.compile...", file=sys.stderr)
        t1 = time.time()
        model.model.talker = torch.compile(model.model.talker)
        print(f"torch.compile applied in {time.time() - t1:.1f}s (actual compilation happens on first forward pass)", file=sys.stderr)
    return model


# 12Hz tokenizer: 12 codec tokens ≈ 1 second of audio
TOKENS_PER_SECOND = 12


def generate_clone(
    model,
    text: str,
    language: str,
    ref_audio: str,
    ref_text: str,
    output_path: Path,
    max_new_tokens: int = 2048,
):
    """Generate speech by cloning a reference voice."""
    import soundfile as sf

    print(f"Generating voice-clone speech ({len(text)} chars, lang={language}, max_tokens={max_new_tokens})...", file=sys.stderr)
    t0 = time.time()
    wavs, sr = model.generate_voice_clone(
        text=text,
        language=language,
        ref_audio=ref_audio,
        ref_text=ref_text,
        max_new_tokens=max_new_tokens,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), wavs[0], sr)
    dur = len(wavs[0]) / sr
    print(
        f"Done in {time.time() - t0:.1f}s → {output_path} ({dur:.1f}s audio)",
        file=sys.stderr,
    )


def generate_custom(
    model,
    text: str,
    language: str,
    speaker: str,
    instruct: str,
    output_path: Path,
    max_new_tokens: int = 2048,
):
    """Generate speech using a preset speaker + instruct."""
    import soundfile as sf

    print(f"Generating custom-voice speech (speaker={speaker}, max_tokens={max_new_tokens})...", file=sys.stderr)
    t0 = time.time()
    kwargs = dict(text=text, language=language, speaker=speaker, max_new_tokens=max_new_tokens)
    if instruct:
        kwargs["instruct"] = instruct
    wavs, sr = model.generate_custom_voice(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), wavs[0], sr)
    dur = len(wavs[0]) / sr
    print(
        f"Done in {time.time() - t0:.1f}s → {output_path} ({dur:.1f}s audio)",
        file=sys.stderr,
    )


def generate_design(
    model,
    text: str,
    language: str,
    instruct: str,
    output_path: Path,
    max_new_tokens: int = 2048,
):
    """Generate speech with a designed voice from a natural-language description."""
    import soundfile as sf

    print(f"Generating voice-design speech (max_tokens={max_new_tokens})...", file=sys.stderr)
    t0 = time.time()
    wavs, sr = model.generate_voice_design(
        text=text,
        language=language,
        instruct=instruct,
        max_new_tokens=max_new_tokens,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), wavs[0], sr)
    dur = len(wavs[0]) / sr
    print(
        f"Done in {time.time() - t0:.1f}s → {output_path} ({dur:.1f}s audio)",
        file=sys.stderr,
    )


def detect_language(text: str) -> str:
    """Simple heuristic: if >30% of chars are CJK/accented-latin, guess accordingly."""
    latin_accented = sum(1 for c in text if "\u00c0" <= c <= "\u024f")
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    kana = sum(1 for c in text if "\u3040" <= c <= "\u30ff")
    total = max(len(text), 1)
    if cjk / total > 0.15:
        return "Chinese"
    if hangul / total > 0.15:
        return "Korean"
    if kana / total > 0.15:
        return "Japanese"
    # Rough Spanish detection
    spanish_markers = {"ñ", "¿", "¡", "á", "é", "í", "ó", "ú", "ü"}
    if any(c in spanish_markers for c in text.lower()):
        return "Spanish"
    return "Auto"


def main():
    parser = argparse.ArgumentParser(
        description="Generate speech with Qwen3-TTS (CPU, local)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Cocobot voice (uses default reference audio):
  uv run generate_speech.py --text "¡Hola! Soy Cocobot" --filename speech.wav

  # Voice clone from custom reference:
  uv run generate_speech.py --text "Hello!" --ref-audio ref.wav --ref-text "transcript" --filename out.wav

  # Preset speaker with instruct:
  uv run generate_speech.py --text "Hello!" --speaker Mochi --instruct "Playful tone" --filename out.wav

  # Design a new voice:
  uv run generate_speech.py --text "Hello!" --design "Young cheerful cat-robot voice" --filename out.wav

  # Fast mode (0.6B model, ~3x faster, lower quality):
  uv run generate_speech.py --text "¡Hola!" --fast --filename quick.wav

  # Long audio (up to 10 minutes):
  uv run generate_speech.py --text "(very long text...)" --max-duration 600 --filename long.wav
""",
    )
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--filename", required=True, help="Output audio file path (.wav)")
    parser.add_argument("--language", default=None, help="Language (Auto/Spanish/English/Chinese/...)")
    parser.add_argument("--fast", action="store_true", help="Use 0.6B model (~3x faster, lower quality)")
    parser.add_argument("--max-duration", type=int, default=300,
                        help="Max audio duration in seconds (default: 300 = 5 min). "
                             "Prevents infinite generation. Use 600 for ~10 min.")

    # Voice clone mode (default)
    parser.add_argument("--ref-audio", default=None, help="Reference audio for voice cloning")
    parser.add_argument("--ref-text", default=None, help="Transcript of the reference audio")

    # Custom voice mode
    parser.add_argument("--speaker", default=None, help="Preset speaker name (Vivian/Mochi/Ryan/...)")
    parser.add_argument("--instruct", default=None, help="Voice style instruction")

    # Voice design mode
    parser.add_argument("--design", default=None, help="Natural-language voice description")

    # Advanced
    parser.add_argument("--device", default="auto", help="Device: auto (try GPU, fallback CPU), cpu, cuda:0")
    parser.add_argument("--model", default=None, help="Override model name/path")
    parser.add_argument("--compile", action="store_true", help="Use torch.compile on GPU (slower first run, faster generation)")

    args = parser.parse_args()

    language = args.language or detect_language(args.text)
    output_path = Path(args.filename)

    fast = args.fast
    max_tokens = args.max_duration * TOKENS_PER_SECOND

    def run_generation(device_override=None):
        """Run the selected generation mode. Returns True on success."""
        dev = device_override or args.device

        if args.design:
            model_name = args.model or MODEL_DESIGN
            model = load_model(model_name, dev, compile_model=args.compile)
            generate_design(model, args.text, language, args.design, output_path, max_new_tokens=max_tokens)
        elif args.speaker:
            model_name = args.model or (MODEL_CUSTOM_FAST if fast else MODEL_CUSTOM)
            model = load_model(model_name, dev, compile_model=args.compile)
            generate_custom(model, args.text, language, args.speaker, args.instruct or "", output_path, max_new_tokens=max_tokens)
        else:
            model_name = args.model or (MODEL_BASE_FAST if fast else MODEL_BASE)
            model = load_model(model_name, dev, compile_model=args.compile)
            generate_clone(model, args.text, language, ref_audio, ref_text, output_path, max_new_tokens=max_tokens)

    # Validate mode-specific restrictions
    if args.design and fast:
        parser.error("--fast is not available for --design (no 0.6B VoiceDesign model exists)")

    # Resolve ref_audio / ref_text for clone mode
    ref_audio = args.ref_audio
    ref_text = args.ref_text
    if not args.design and not args.speaker:
        if ref_audio is None:
            if DEFAULT_REF_AUDIO.exists():
                ref_audio = str(DEFAULT_REF_AUDIO)
                if ref_text is None and DEFAULT_REF_TEXT_FILE.exists():
                    ref_text = DEFAULT_REF_TEXT_FILE.read_text().strip()
                print(f"Using Cocobot default voice: {ref_audio}", file=sys.stderr)
            else:
                parser.error(
                    "No --ref-audio provided and no default Cocobot reference found at "
                    f"{DEFAULT_REF_AUDIO}. "
                    "Use --speaker for preset voices or --design to create a reference."
                )
        if ref_text is None:
            parser.error("--ref-text is required for voice cloning (transcript of the reference audio)")

    # Run with CUDA fallback to CPU on error
    try:
        run_generation()
    except Exception as exc:
        if args.device == "auto" and "CUDA" in str(type(exc).__name__) + str(exc):
            print(f"\nCUDA error: {exc}\nRetrying on CPU (new process)...", file=sys.stderr)
            # After a CUDA device-side assert the context is corrupted.
            # Safest recovery: re-exec ourselves with --device cpu.
            import subprocess
            argv = [sys.executable] + sys.argv + ["--device", "cpu"]
            sys.exit(subprocess.call(argv))
        else:
            raise

    print(str(output_path))


if __name__ == "__main__":
    main()
