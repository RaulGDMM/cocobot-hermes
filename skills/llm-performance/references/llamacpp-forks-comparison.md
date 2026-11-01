# llama.cpp Forks Comparison (May 2026)

## Overview

When llama.cpp main branch lags on features (TurboQuant PR #21089 open since early 2026, no D-Flash), community forks fill the gap. Key tradeoff: **speed of innovation vs stability**.

## Fork Matrix

| Fork | Stars | Backend | MTP | D-Flash | TurboQuant | TCQ | Vision | Spec Decode |
|---|---|---|---|---|---|---|---|---|
| **llama.cpp main** | 122k | All | ✅ Beta | ❌ | ❌ | ❌ | ✅ libmtmd | ✅ Draft model |
| **BeeLlama** (Anbeeld) | 258 | CUDA/Metal | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ D-Flash + Copyspec + DDTree |
| **TheTom TurboQuant+** | 1.5k | Metal/CUDA/HIP/Vulkan | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| **AtomicBot** | ~100 | Metal/CUDA/Vulkan/HIP | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ MTP + NextN |
| **animehacker** | ~50 | CUDA | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **spiritbuun** | ~200 | CUDA | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |

## Fork Detail

### BeeLlama (Anbeeld/beellama.cpp)
- Fork of spiritbuun, which forked TheTom
- **Best for**: D-Flash + TurboQuant + Vision all together
- D-Flash with reasoning-loop protection, adaptive draft control (profit/fringe), DDTree branch verification
- Copyspec (model-free rolling-hash suffix matching) as fallback
- Request-level overrides for draft parameters
- **Limitation**: CUDA/Metal only, no Vulkan/HIP

### TheTom TurboQuant+ (TheTom/llama-cpp-turboquant)
- **Best for**: TurboQuant across all backends (Metal TurboFlash, CUDA, HIP/ROCm, Vulkan)
- Weight compression: TQ3_1S, TQ4_1S (not just KV cache)
- Base of upstream PR #21089 — most likely to merge into main
- **Limitation**: No speculative decoding, no D-Flash, no MTP

### AtomicBot (AtomicBot-ai/atomic-llama-cpp-turboquant)
- **Best for**: MTP + TurboQuant combined (unique among forks)
- Qwen 3.6 NextN spec decode (+24-36% throughput), Gemma 4 MTP (+30-50%)
- Async depth-2 pipeline overlaps draft compute with verification
- Vision compatible with spec decode (text-only turns accelerated)
- **Limitation**: No D-Flash (NextN is less aggressive), benchmarks only on Metal

### spiritbuun (spiritbuun/buun-llama-cpp)
- Original D-Flash + TCQ implementation
- Base of BeeLlama — BeeLlama improves on it in nearly every way
- **Verdict**: Use BeeLlama instead

### animehacker (animehacker/llama-turboquant)
- CUDA MMVQ kernel, 72K+ context for 70B models
- **Verdict**: Too narrow, BeeLlama supersedes it

## TCQ Explained (Trellis-Coded Quantization)

TurboQuant standard = scalar quantization (each value independent).
TCQ = treats sequences as paths in a trellis graph, finds optimal global path.
Same idea as ADSL/VDSL modems for noisy channels.

**Practical impact** (critical at 2-3 bits):
- `turbo2` scalar: significant quality loss
- `turbo2_tcq`: quality close to 3-bit scalar, 10-44% KL reduction
- `turbo3_tcq`: best high-compression quality-aware option

**Recommended combo**: `--cache-type-k turbo4 --cache-type-v turbo3_tcq`
(Keys need quality for attention scoring; values can be more aggressive with TCQ.)

## llama.cpp Main Branch Timeline

| Feature | Status | ETA |
|---|---|---|
| MTP (beta) | Merged PR #22673 | ✅ Now |
| TurboQuant | PR #21089 open, under review | 2-4 months |
| TurboQuant + MTP tested together | Not started | +1-2 months after merge |
| D-Flash upstream | No PR filed | 6-12 months (if ever) |
| Vision + MTP combined | Not tested | 3-6 months |
| All features + stable | — | Q4 2026 / Q1 2027 |

**Why slow?** ggml-org is the industry standard — every KV cache change needs regressions across CUDA/Metal/Vulkan/CPU, GGUF compatibility, and perplexity benchmarks. PRs that touch core infrastructure move slowly.

## Non-llama.cpp Alternatives

### Genesis vLLM Patches (Sandermage/genesis-vllm-patches)
- **Speed**: 160-192 tok/s on RTX 5090 (vs ~100 for BeeLlama)
- **Tech**: vLLM 0.19 + 126 patches: TurboQuant k8v4, MTP/D-Flash spec-decode, full cudagraph, GDN streaming
- **Context**: Up to 256K on 5090
- **Limitation**: **No vision support**, Linux only, Qwen3.6-specific, complex setup
- **Verdict**: Faster for text-only, but loses multimodal capability

### qwen3.6-windows-server (devnen/qwen3.6-windows-server)
- **Speed**: ~158 tok/s on RTX 5090 (NVFP4)
- **Tech**: Embedded Python 3.12 + patched vLLM wheel, one-click ZIP, native Windows
- **Limitation**: **No vision**, Windows only, no D-Flash (uses MTP)
- **Verdict**: Easiest setup on Windows, but no vision and less flexible

### vLLM stock (no patches)
- TurboQuant merged to main in April 2026
- Presets: turboquant_k8v4, turboquant_4bit_nc, turboquant_3bit_nc
- **Limitation**: DFlash requires `causal=False` which conflicts with quantized KV (Issue #41559)
- **Verdict**: Good for KV compression alone, but DFlash + TurboQuant incompatible

## When to Switch From BeeLlama

Switch to llama.cpp main when:
1. TurboQuant merged (PR #21089)
2. D-Flash contributed upstream
3. Vision + MTP proven stable together

Estimated: **Q4 2026 at earliest**. Until then, BeeLlama is the most feature-complete option for RTX 5090 + Qwen3.6-27B with vision.
