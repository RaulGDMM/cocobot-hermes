# NVFP4 Status & Analysis

## Kernel Implementation Details (PR #22196, merged Apr 28 2026)

**Blackwell native NVFP4 MMA kernels** by @michaelw9999.

- Uses `mma.sync.aligned.kind::mxf4nvf4.block_scale.scale_vec::4X.m16n8k64` PTX instructions
- 76-byte `MMQ_MMA_TILE_X_K_FP4` tiles
- Direct gmem → smem → regs path for prefill (no transpose, no load_generic, no load_ldmatrix)
- **Decode shapes (M=1)**: Small shapes hit kernel launch overhead + F32 scale multiplication step
- **Prefill shapes**: Large M values saturate Tensor Cores, bandwidth-bound, +43-68% speedup

### Why GPU utilization is ~75% vs 90%+ Q6_K

1. **Derived tensor overhead**: NVFP4 requires `FP32_activations = F4 * F8 * F32` — the F32 per-tensor scale is applied AFTER each `ggml_mul_mat`, breaking kernel fusion pipelines that Q6_K exploits
2. **Higher register pressure**: Two-level scaling (F8 per-block + F32 per-tensor) consumes more registers per warp
3. **Lower occupancy**: Fewer active warps per SM → SMs not fully utilized
4. **Decode shapes are suboptimal**: Kernel optimized for large prefill matrices, not M=1 decode
5. **AoSoA layout pending**: ORippler (GGML collaborator, discussion #22042) notes that pre-arranging bytes into tiles (Array of Structs of Arrays) would eliminate transposes and reduce smem usage significantly

### Timeline for fused kernels

- **Current state**: Separate kernel for matmul + separate step for F32 scale application
- **Target**: Fused kernel that integrates F32 scale into the matmul operation
- **ETA**: 2-4 months (kernel tuning for small-M shapes is ongoing)
- **Expected impact**: GPU utilization 85-90%, decode speed ~identical (still bandwidth-bound)

## Quality Analysis: NVFP4-Q8_0 vs Q6_K

### Layer-by-layer comparison

| Layer | Q6_K | NVFP4-Q8_0 | Winner |
|-------|------|------------|--------|
| Attention | Q6_K (~6 bits) | Q8_0 (~8 bits) | NVFP4-Q8_0 ✅ |
| SSM | Q6_K (~6 bits) | Q8_0 (~8 bits) | NVFP4-Q8_0 ✅ |
| FFN | Q6_K (~6 bits) | NVFP4 (~4 bits) | Q6_K ✅ |
| Norms/Biases | F16/F32 | F32 | NVFP4-Q8_0 ✅ |

### Why attention matters more than FFN

- **Attention layers** control contextual coherence, instruction following, logical consistency
- Most quantization-sensitive — precision loss here degrades model behavior disproportionately
- FFN is the "dictionary" — more robust to quantization, stores factual knowledge
- FFN is 70% of parameters but less sensitive per-parameter to precision loss
- **Conclusion**: NVFP4-Q8_0 has structural advantage for long-context tasks where attention precision is critical

### Practical quality difference

- Perplexity gap: ~0.1-0.5 (minimal)
- Unsloth benchmarks (safetensors, vLLM): GSM8K 0.20 vs 0.20 BF16, MMLU-Pro 0.63 vs 0.64 BF16
- NVFP4 two-level scaling introduces cumulative numerical errors (ORippler #22042)
- Current kernels do not derive NVFP4 perfectly — minor quality loss vs theoretical maximum
- **Verdict**: NVFP4-Q8_0 ≥ Q6_K theoretically, ~identical practically

## Publisher Landscape

### LibertAIDAI
- **Qwen3.6-27B-NVFP4-MTP-GGUF**: Best current option
- 3 MTP head variants: BF16 (5.95GB), Q4_K_M (15.8GB), Q8_0 (20GB)
- Trunk: NVFP4-Q8_0 (19GB) with attention/SSM in Q8_0
- mmproj-F16 (931MB) included
- Benchmarked: ~115 t/s real workloads, ~90.8 t/s synthetic

### Unsloth
- **Qwen3.6-27B-NVFP4**: Safetensors-only (compressed-tensors)
- Calibration: UltraChat, 16K ctx, ~2M tokens
- Benchmarks: GSM8K 0.20, MMLU-Pro 0.63 (vs BF16 0.20/0.64)
- **NO GGUF, NO MTP** — designed for vLLM/SGLang/KTransformers
- Not directly comparable to LibertAIDAI GGUF

### Bartowski / Mradermacher
- **NO NVFP4 yet** (June 2026)
- Bartowski focuses on standard GGUF formats (Q4-Q8, IQ variants)
- If/when they release NVFP4 GGUF, likely superior imatrix calibration
- Monitor for updates

## Decode Speed Analysis

### Why decode is ~identical to Q6_K

- **Memory-bandwidth bound**: Decode (batch=1) limited by VRAM bandwidth, not FLOPS
- NVFP4 weights are ~25% smaller, but kernel overhead (F32 scale step) compensates
- Community consensus: "You can do FP4→BF16 conversion 'for free' while waiting for memory fetch"
- Net result: ~73.6 t/s decode base (identical to Q6_K)
- With MTP: ~103 t/s effective (same mechanism as Q6_K+MTP)

### Prefill is the real advantage

- Large M shapes → Tensor Cores saturate → bandwidth-bound
- NVFP4 smaller weights = fewer bytes/token = faster prefill
- +43-68% prefill speedup (context 32K: +43%, short: +68%)
- Critical for agents with long prompts, RAG, code-heavy contexts

## NVFP4 as Derived Tensor (Discussion #22042)

From ORippler (GGML collaborator):

> NVFP4 is a two-step quantization: per-tensor F32 scale + blocks of F4+F8 values.
> To dequantize: `FP32_activations = F4 * F8 * F32`.
> The `struct block_nvfp4` does NOT fully represent the tensor — F32 scale is external.
> Responsibility for dequantization is shared between GGML and callee (llama.cpp).
> Compute graph for NVFP4 MulMat requires `GGML_OP_MUL` for F32 scale AFTER matmul.

**Implications**:
- Swapping `GGML_OP_MUL` and non-linearity may produce incorrect results
- Behavior undocumented in GGML — error-prone for downstream consumers
- Fused kernel would eliminate this separation concern

## References

- PR #22196: https://github.com/ggml-org/llama.cpp/pull/22196 (Blackwell native NVFP4, merged)
- PR #21095: https://github.com/ggml-org/llama.cpp/pull/21095 (compressed-tensors converter, merged)
- Discussion #22042: https://github.com/ggml-org/llama.cpp/discussions/22042 (derived tensor analysis)
- croll83/llama.cpp-dgx: https://github.com/croll83/llama.cpp-dgx (DGX Spark optimized fork)
- ICLR 2026: "Bridging the Gap Between Promise and Performance for Microscaling FP4 Quantization"
- Quartet II (Jan 2026): Full NVFP4 pre-training, zero-shot benchmarks show insignificant differences vs BF16
