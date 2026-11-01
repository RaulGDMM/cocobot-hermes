# DFlash + TurboQuant Compatibility Analysis

## vLLM Incompatibility (Issue #41559)

### Root Cause
DFlash speculative decoding requires **non-causal cross-attention** (`causal=False`) for the draft model. Every attention backend in vLLM v0.20.0 either:
1. Rejects non-causal attention entirely (FLASHINFER, TRITON)
2. Rejects KV-quant dtypes when non-causal is set (FLASH_ATTN, FLEX_ATTENTION)
3. Has `causal=True` hardcoded (TURBOQUANT backend at lines 308, 319, 612)

### Verified Compatibility Matrix (vLLM v0.20.0)

| Backend | Non-causal support | fp8_e5m2 KV + non-causal | turboquant_4bit_nc KV + non-causal |
|---|---|---|---|
| FLASH_ATTN | Yes | Rejected (supported_kv_cache_dtypes excludes fp8 for non-causal) | Rejected |
| FLASHINFER | No (rejects non-causal entirely) | N/A | N/A |
| TRITON | No (rejects non-causal entirely) | N/A | N/A |
| FLEX_ATTENTION | Yes | Rejected (no fp8 in non-causal supported_kv_cache_dtypes) | Rejected |
| TURBOQUANT | N/A | N/A | Hardcoded causal=True |

### Impact
On consumer GPUs (24GB RTX 3090) with a 27B-class target model:
- DFlash is locked to bfloat16 KV cache
- Available KV pool halves (~28K -> ~14K tokens)
- Spec decode throughput gains don't justify halving KV pool for long-context workloads

### Suggested Fix Paths
1. Add `causal=False` support to TurboQuant backend kernels
2. Make non-causal attention work with quantized KV dtypes in FLASH_ATTN/FLEX_ATTENTION

### Source
- Issue: https://github.com/vllm-project/vllm/issues/41559
- DFlash source: `vllm/v1/spec_decode/dflash.py:192,289` (causal=False)
- TurboQuant source: `vllm/v1/attention/backends/turboquant.py:308,319,612` (causal=True)

## BeeLlama.cpp Compatibility

### Why It Works
BeeLlama.cpp separates the drafter's non-causal attention from the target's KV cache:
- Drafter reads hidden states from target via **server eval callbacks** and cross-data APIs
- CPU ring buffer: 4096 tokens per captured layer
- Cross-attention window: controlled by `--spec-dflash-cross-ctx` (default 512)
- GPU ring allocated for requested window
- The drafter's attention is a separate computation path that doesn't touch the target's quantized KV cache

### Performance
- Qwen 3.6 27B Q5 with 200K context on RTX 3090
- 2-3x faster than baseline
- Peak 135 tok/s
- KV cache: turbo4 (K) + turbo3_tcq (V) -> ~4-5x compression vs FP16

### Source
- Repo: https://github.com/Anbeeld/beellama.cpp
- Reddit post: https://www.reddit.com/r/LocalLLaMA/comments/1t88zvv/
- Features doc: `docs/beellama-features.md`
