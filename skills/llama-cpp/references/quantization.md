# GGUF Quantization Guide

Complete guide to GGUF quantization formats and model conversion.

## Hub-first quant selection

Before using generic tables, open the model repo with:

```text
https://huggingface.co/<repo>?local-app=llama.cpp
```

Prefer the exact quant labels and sizes shown in the `Hardware compatibility` section of the fetched `?local-app=llama.cpp` page text or HTML. Then confirm the matching filenames in:

```text
https://huggingface.co/api/models/<repo>/tree/main?recursive=true
```

Use the Hub page first, and only fall back to the generic heuristics below when the repo page does not expose a clear recommendation.

## Quantization Overview

**GGUF** (GPT-Generated Unified Format) - Standard format for llama.cpp models.

### Format Comparison

| Format | Perplexity | Size (7B) | Tokens/sec | Notes |
|--------|------------|-----------|------------|-------|
| FP16 | 5.9565 (baseline) | 13.0 GB | 15 tok/s | Original quality |
| Q8_0 | 5.9584 (+0.03%) | 7.0 GB | 25 tok/s | Nearly lossless |
| **Q6_K** | 5.9642 (+0.13%) | 5.5 GB | 30 tok/s | Best quality/size |
| **Q5_K_M** | 5.9796 (+0.39%) | 4.8 GB | 35 tok/s | Balanced |
| **Q4_K_M** | 6.0565 (+1.68%) | 4.1 GB | 40 tok/s | **Recommended** |
| Q4_K_S | 6.1125 (+2.62%) | 3.9 GB | 42 tok/s | Faster, lower quality |
| Q3_K_M | 6.3184 (+6.07%) | 3.3 GB | 45 tok/s | Small models only |
| Q2_K | 6.8673 (+15.3%) | 2.7 GB | 50 tok/s | Not recommended |

**Recommendation**: Use **Q4_K_M** for best balance of quality and speed.

## Converting Models

### Hugging Face to GGUF

```bash
# 1. Download Hugging Face model
hf download meta-llama/Llama-2-7b-chat-hf \
    --local-dir models/llama-2-7b-chat/

# 2. Convert to FP16 GGUF
python convert_hf_to_gguf.py \
    models/llama-2-7b-chat/ \
    --outtype f16 \
    --outfile models/llama-2-7b-chat-f16.gguf

# 3. Quantize to Q4_K_M
./llama-quantize \
    models/llama-2-7b-chat-f16.gguf \
    models/llama-2-7b-chat-Q4_K_M.gguf \
    Q4_K_M
```

### Batch quantization

```bash
# Quantize to multiple formats
for quant in Q4_K_M Q5_K_M Q6_K Q8_0; do
    ./llama-quantize \
        model-f16.gguf \
        model-${quant}.gguf \
        $quant
done
```

## K-Quantization Methods

**K-quants** use mixed precision for better quality:
- Attention weights: Higher precision
- Feed-forward weights: Lower precision

**Variants**:
- `_S` (Small): Faster, lower quality
- `_M` (Medium): Balanced (recommended)
- `_L` (Large): Better quality, larger size

**Example**: `Q4_K_M`
- `Q4`: 4-bit quantization
- `K`: Mixed precision method
- `M`: Medium quality

## Quality Testing

```bash
# Calculate perplexity (quality metric)
./llama-perplexity \
    -m model.gguf \
    -f wikitext-2-raw/wiki.test.raw \
    -c 512

# Lower perplexity = better quality
# Baseline (FP16): ~5.96
# Q4_K_M: ~6.06 (+1.7%)
# Q2_K: ~6.87 (+15.3% - too much degradation)
```

## Use Case Guide

### General purpose (chatbots, assistants)
```
Q4_K_M - Best balance
Q5_K_M - If you have extra RAM
```

### Code generation
```
Q5_K_M or Q6_K - Higher precision helps with code
```

### Creative writing
```
Q4_K_M - Sufficient quality
Q3_K_M - Acceptable for draft generation
```

### Technical/medical
```
Q6_K or Q8_0 - Maximum accuracy
```

### Edge devices (Raspberry Pi)
```
Q2_K or Q3_K_S - Fit in limited RAM
```

## Model Size Scaling

### 7B parameter models

| Format | Size | RAM needed |
|--------|------|------------|
| Q2_K | 2.7 GB | 5 GB |
| Q3_K_M | 3.3 GB | 6 GB |
| Q4_K_M | 4.1 GB | 7 GB |
| Q5_K_M | 4.8 GB | 8 GB |
| Q6_K | 5.5 GB | 9 GB |
| Q8_0 | 7.0 GB | 11 GB |

### 13B parameter models

| Format | Size | RAM needed |
|--------|------|------------|
| Q2_K | 5.1 GB | 8 GB |
| Q3_K_M | 6.2 GB | 10 GB |
| Q4_K_M | 7.9 GB | 12 GB |
| Q5_K_M | 9.2 GB | 14 GB |
| Q6_K | 10.7 GB | 16 GB |

### 70B parameter models

| Format | Size | RAM needed |
|--------|------|------------|
| Q2_K | 26 GB | 32 GB |
| Q3_K_M | 32 GB | 40 GB |
| Q4_K_M | 41 GB | 48 GB |
| Q4_K_S | 39 GB | 46 GB |
| Q5_K_M | 48 GB | 56 GB |

**Recommendation for 70B**: Use Q3_K_M or Q4_K_S to fit in consumer hardware.

## Finding Pre-Quantized Models

Use the Hub search with the llama.cpp app filter:

```text
https://huggingface.co/models?apps=llama.cpp&sort=trending
https://huggingface.co/models?search=<term>&apps=llama.cpp&sort=trending
https://huggingface.co/models?search=<term>&apps=llama.cpp&num_parameters=min:0,max:24B&sort=trending
```

For a specific repo, open:

```text
https://huggingface.co/<repo>?local-app=llama.cpp
https://huggingface.co/api/models/<repo>/tree/main?recursive=true
```

Then launch directly from the Hub without extra Hub tooling:

```bash
llama-cli -hf <repo>:Q4_K_M
llama-server -hf <repo>:Q4_K_M
```

If you need the exact file name from the tree API:

```bash
llama-server --hf-repo <repo> --hf-file <filename.gguf>
```

## Importance Matrices (imatrix)

**What**: Calibration data to improve quantization quality.

**Benefits**:
- 10-20% perplexity improvement with Q4
- Essential for Q3 and below

**Usage**:
```bash
# 1. Generate importance matrix
./llama-imatrix \
    -m model-f16.gguf \
    -f calibration-data.txt \
    -o model.imatrix

# 2. Quantize with imatrix
./llama-quantize \
    --imatrix model.imatrix \
    model-f16.gguf \
    model-Q4_K_M.gguf \
    Q4_K_M
```

**Calibration data**:
- Use domain-specific text (e.g., code for code models)
- ~100MB of representative text
- Higher quality data = better quantization

## AWQ Format — NOT Supported in llama.cpp

**AWQ-INT4 quantized models from HuggingFace (e.g., `cyankiwi/Qwen3.6-27B-AWQ-INT4`) are designed for vLLM/SGLang/AutoAWQ — they will NOT work in llama.cpp.**

- llama.cpp uses K-quants (Q4_K, Q6_K, etc.) — no native AWQ inference backend exists
- AWQ can be used as **pre-processing**: adjust FP16 weights with AutoAWQ → convert to GGUF → quantize with `llama-quantize` (improves Q4/Q6 quality)
- But a true AWQ-INT4 model cannot be directly loaded in llama.cpp without dequantizing to FP16 first (~54GB for 27B), which defeats the purpose
- **For llama.cpp, Q6_K remains superior to any AWQ-INT4 conversion** — especially with MTP support

### llama.cpp AWQ history

- PR #4593 (merged Dec 2023) added "AWQ support" — but this was a **workaround**, not true AWQ inference. It applied AWQ scales to FP16 weights before converting to GGUF, then re-quantized with standard K-quants. The perplexity improvement was marginal (~0.02-0.1 points).
- **No active work** to add native AWQ support. ggerganov's strategy has been improving K-quants (mixed-precision by channel, similar philosophy to AWQ) which now match AWQ perplexity.
- For Qwen3.6-27B specifically, AWQ models exist on HuggingFace (`QuantTrio/`, `cyankiwi/`, `mattbucci/`) — all vLLM/SGLang only, ~19-21 GB. Not usable in llama.cpp.

### QAT (Quantization-Aware Training) — fundamentally different from PTQ

QAT is NOT post-training quantization. It **simulates quantization during the training loop** so the model learns to compensate for precision loss while still adjusting weights. This is why QAT models at Q4 can approach BF16 quality — the model was literally trained to be quantized.

**QAT is only possible for the model's training team:**
- Requires original training data (or representative corpus)
- Requires GPU cluster for fine-tuning with quantization simulation (~5000+ steps)
- Requires the pre-QAT checkpoint

Google has released QAT checkpoints for Gemma 3 and Gemma 4 (Q4_0 + mobile schema). Results: 54% reduction in perplexity drop vs standard PTQ at Q4_0.

**QAT for Qwen models is unlikely** — Alibaba has not shown interest in QAT. Community QAT is theoretically possible (Unsloth could fine-tune with quantization simulation) but requires serious compute. Do not recommend QAT as an option for non-Gemma models.

### Benchmark scores vs subjective quality

When comparing quantizations, benchmark scores (GSM8K, HellaSwag, HumanEval) can be nearly identical while subjective experience differs noticeably:

- **Benchmarks measure closed-answer accuracy**, not text fluency, reasoning quality, or conversational coherence
- Small sample sizes (20-30 items) have high variance — 1-2 answers move scores by 3-7pp
- Q6_K vs NVFP4-Q8_0 on Qwen3.6-27B: -0.3pp average difference (statistical noise), but Q6_K produces more "natural" text in open-ended generation
- **Reason**: uniform quantization (Q6_K ~6 bits/param everywhere) preserves the weight distribution more smoothly than hybrid formats (NVFP4: Q8 attention + FP4 FFN). Both reach the same correct answer, but the path (reasoning quality, fluency) differs.
- **Practical rule**: If benchmarks are within 2pp, trust subjective experience for daily use. Benchmarks are for ruling out bad quantizations, not declaring winners among good ones.

## NVFP4 / FP4 Quantization (NVIDIA Blackwell GPUs)

**Format ecosystems — critical distinction:**
- **llama.cpp / BeeLlama**: Requires **GGUF format** with `GGML_TYPE_NVFP4 = 40`. Models must be exported as `.gguf` files with NVFP4 quantization.
- **vLLM**: Uses **modelopt** or **compressed-tensors** format (NOT GGUF). These are NVIDIA's native formats for SM120. Repos like `sakamakismile/Qwen3.6-27B-Text-NVFP4-MTP` are vLLM-only — they will NOT work in llama.cpp.
- **Same name, different formats**: A repo named "Qwen3.6-27B-NVFP4" on HuggingFace could be either format. Check the files: `.gguf` = llama.cpp, `model.safetensors` + `config.json` with modelopt = vLLM.

**NVFP4** (FP4 E2M1 weights + UE4M3 per-block scale) is NVIDIA's format for Blackwell GPUs (SM120: RTX 5090, RTX PRO 6000). On Blackwell with llama.cpp b8967+, NVFP4 GGUF uses native tensor-core MMA kernels for FFN matmul.

### NVFP4 GGUF variants (Qwen3.6-27B example)

NVFP4 quantizes FFN tensors to FP4; other tensors (attention, embeddings, output) use conventional GGUF quantization:

| File | Size | FFN | Other Tensors | Notes |
|------|------|-----|---------------|-------|
| `NVFP4-Q4_K_M.gguf` | ~15 GB | NVFP4 | Q4_K_M | Smallest VRAM, fastest throughput |
| `NVFP4-Q8_0.gguf` | ~19 GB | NVFP4 | Q8_0 | Higher precision attention/embeddings |
| `NVFP4-BF16.gguf` | ~28 GB | NVFP4 | BF16 | Max quality, slower (bandwidth-bound) |

Source: [LibertAIDAI/Qwen3.6-27B-NVFP4-GGUF](https://huggingface.co/LibertAIDAI/Qwen3.6-27B-NVFP4-GGUF)

### Performance (RTX 5090, llama.cpp c84e6d6db)

| Variant | Size | Prompt Processing | Token Generation |
|---------|------|-------------------|------------------|
| `NVFP4-Q4_K_M` | 14.72 GiB | 2865 tok/s | **64 tok/s** |
| `NVFP4-Q8_0` | 18.65 GiB | 3346 tok/s | **64 tok/s** |
| `NVFP4-BF16` | 27.19 GiB | 1403 tok/s | **49 tok/s** |

**Note**: These are **pre-MTP** numbers (no speculative decoding). With MTP active, NVFP4-Q8_0 reaches ~103 t/s (text generation) and ~92 t/s (tool calls). Decode speed without MTP is ~identical to Q6_K (~73-74 t/s baseline) — decode is memory-bandwidth bound, not compute bound. The two-level NVFP4 scaling overhead (F8 per-block + F32 per-tensor) compensates for the smaller weight size. GPU utilization runs ~75% vs ~90%+ Q6_K due to kernel immaturity (derived tensor breaks kernel fusion); expected to improve with fused kernels in 2-4 months.

### Quality: NVFP4-Q4 vs NVFP4-Q8

No direct benchmarks exist comparing NVFP4-Q4 vs NVFP4-Q8 specifically. Standard GGUF Q4_K_M vs Q8_0 benchmarks for Qwen3.6-27B provide a close proxy (the difference between NVFP4 variants is the same: attention+embeddings at Q4 vs Q8):

| Benchmark | BF16 | Q8_0 | Q4_K_M | Q8→Q4 Drop |
|-----------|------|------|--------|------------|
| **HumanEval** (code) | 56.1% | 52.4% | 50.6% | **-1.8 pts** |
| **HellaSwag** (reasoning) | 86% | 85% | 84% | **-1 pt** |
| **BFCL** (function calling) | 63.25% | 63% | 63% | **0 pts** |
| **Average** | 68.45% | 66.81% | 65.87% | **-0.94 pts** |

Sources: [heyneo.com benchmark](https://heyneo.com/blog/evaluating-qwen-3-6-27b-benchmarking-case-study), [reddit r/LocalLLaMA quality comparison](https://www.reddit.com/r/LocalLLaMA/comments/1t53dhp/)

### NVFP4-Q4 vs Q8 trade-off for agent workloads

When choosing between NVFP4-Q4 and NVFP4-Q8 for Hermes Agent or similar frameworks:

| Factor | NVFP4-Q8 | NVFP4-Q4 | Winner |
|--------|----------|----------|--------|
| Model precision | 97% of BF16 | 96% of BF16 | Q8 (marginal) |
| Summary quality | Better (Q8 summarizes) | Slightly worse (Q4 summarizes) | Q8 |
| VRAM available for KV cache | Less (~4 GB less) | More (~4 GB extra) | Q4 |
| Context before compression | Smaller | Larger (can increase ctx-size) | Q4 |
| Compression frequency | More frequent | Less frequent | Q4 |
| Accumulated degradation | Less (better summaries) | More (worse summaries × more recompressions) | Q8 |

**Recommendation for agent workloads**: Prefer **NVFP4-Q8** when compression is already working well (parallel 2 avoids blocking). The summary quality matters more than extra context — a Q8 model compressing 50K tokens preserves more useful information than a Q4 model compressing 60K. The ~1 point precision difference is imperceptible in daily use, but summary quality compounds across multiple compressions in long sessions.

**When Q4 makes sense**: If you're experiencing frequent compression blocking, need larger tail protection, or want to increase ctx-size beyond current VRAM limits.

### MXFP4 vs NVFP4 (June 2026 — both fully supported)

- **MXFP4** (Microscaling FP4): Generic format, native Blackwell kernels merged via PR #17906. ~27% prefill speedup on SM120.
- **NVFP4**: NVIDIA-specific format (UE4M3 per-block scale). **FULLY supported as of June 2026** — all three required PRs merged:
  - PR #21074 (Apr 1): Generic NVFP4 MMQ kernel — up to 2.91x prefill speedup (Qwen3.5-27B: 1026→2988 t/s on RTX 5090)
  - PR #22196 (Apr 28): Blackwell native NVFP4 MMA kernels (SM120 tensor-core acceleration) — ~20% additional prefill speedup over generic kernel
  - PR #21095 (Jun 25): compressed-tensors NVFP4 → GGUF conversion (previously only ModelOpt format supported)
- **Compile from master** with `-DCMAKE_CUDA_ARCHITECTURES="120f"` to get Blackwell-optimized kernels.
- For MoE models on Blackwell, **both MXFP4_MOE and NVFP4 are usable now**.

### NVFP4 + DFlash / Turbo Quant compatibility

- **DFlash speculative decoding**: Compatible. DFlash loads a *separate* drafter model, so the target model's quantization format is irrelevant. No known incompatibility between NVFP4 targets and DFlash drafters.
- **Turbo Quant (KV cache)**: Compatible. Turbo4/Turbo3_tcq operate on the KV cache independently of model weights. You can use `--cache-type-k turbo4 --cache-type-v turbo3_tcq` with any model quantization including NVFP4.

### NVFP4 pitfall: linear attention layers (Qwen3.6-27B)

**Qwen3.6-27B uses DeltaNet (linear attention) in 48/64 layers.** These layers are highly sensitive to aggressive quantization. As of June 2026:

- **No NVFP4 GGUF exists that preserves linear_attn layers at high precision.** All available GGUF variants (LibertAIDAI) quantize linear_attn tensors to NVFP4.
- The `kaitchup/Qwen3.6-27B-autoround-nvfp4-linearattn-BF16` variant preserves linear_attn in BF16 but is **compressed-tensors format only (vLLM)**, not GGUF. With PR #21095 merged, conversion of this format to GGUF is now possible — but nobody has produced such a GGUF yet.
- The llama.cpp NVFP4 conversion pipeline does not yet support selective mixed-precision (FFN=NVFP4 + linear_attn=Q8_0/BF16).

**Practical recommendation**: For Qwen3.6-27B with llama.cpp, **Q6_K with MTP remains superior to NVFP4-Q4_K_M** for pure quality — Q6_K preserves linear_attn quality via imatrix-aware quantization AND retains MTP. However, **NVFP4-Q8_0 with MTP** (LibertAIDAI, Jun 2026) is competitive: attention/SSM layers in Q8_0 (superior to Q6_K), only FFN in NVFP4. NVFP4-Q8_0 wins on VRAM (19 vs 22.5 GB) and prefill throughput (+43-68% with Blackwell kernels). The trade-off: decode speed is ~identical to Q6_K, GPU utilization is lower (~75% vs ~90%+), but this is a kernel maturity issue expected to resolve in 2-4 months.

### NVFP4 + MTP + Vision status (Updated July 2026)

`LibertAIDAI/Qwen3.6-27B-NVFP4-MTP-GGUF` (Jun 26, 2026) has NVFP4 + MTP. Vision mmproj is a separate file (`mmproj-Qwen3.6-27B-F16.gguf`, 889 MB) that is reusable with any GGUF variant.

| Component | NVFP4 | MTP | Vision | Repo |
|-----------|-------|-----|--------|------|
| Trunk (NVFP4-Q8_0) | ✅ | ✅ (separate draft head) | ✅ (mmproj-F16) | LibertAIDAI/Qwen3.6-27B-NVFP4-MTP-GGUF |
| Trunk (NVFP4-Q4_K_M) | ✅ | ✅ (separate draft head) | ✅ (mmproj-F16) | LibertAIDAI/Qwen3.6-27B-NVFP4-MTP-GGUF |

**Usage**: Load trunk + `--model-draft mtp-*.gguf --spec-type draft-mtp` + `--mmproj mmproj-*.gguf`.

**Runtime performance notes** (RTX 5090):
- **Decode speed**: ~identical to Q6_K (~103 t/s with MTP vs ~106 t/s). Decode is memory-bandwidth bound; NVFP4's two-level scaling overhead (F8 per-block + F32 per-tensor) compensates for smaller weight size.
- **GPU utilization**: ~75% vs ~90%+ Q6_K. Kernel maturity issue — NVFP4 is a "derived tensor" requiring F32 scale after each matmul, breaking kernel fusion. Expected to reach 85-90% with fused kernels (2-4 months).
- **Prefill**: +43-68% faster than standard quantization. This is the primary benefit for agent/RAG workloads.

### NVFP4 vs Q6_K quality comparison (Qwen3.6-27B)

From PR #21095 benchmarks (RTX 5090):

| Format | Mean KLD (↓better) | Quality tier |
|--------|-------------------|--------------|
| Q6_K | ~0.010-0.020 | Excellent (~99% BF16) |
| Q4_0 | 0.048630 | Good |
| **NVFP4 (FFN only)** | **0.089473** | Between Q3_K and Q4_0 |
| Q3_K | 0.082418 | Acceptable |

**Key insight**: NVFP4-Q4_K_M hybrid has NVFP4 quality (~Q3/Q4) for FFN tensors + Q4_K_M for attention/embeddings. Q6_K has Q6 quality EVERYWHERE. Q6_K wins on pure quality, but NVFP4 wins on VRAM (15 vs 22.5 GB) and prefill throughput (with Blackwell kernels). The trade-off is meaningful only if you sacrifice MTP (which NVFP4 GGUFs currently do).

## Qwen3.6-27B Quantization Benchmarks

Real benchmark data from multiple independent sources (heyneo, reddit r/LocalLLaMA, localbench).

### Task-level accuracy vs BF16

| Quant | HumanEval (code) | HellaSwag (reasoning) | BFCL (function calling) | Average |
|-------|-------------------|------------------------|--------------------------|---------|
| **BF16** | 56.10% | 86.00% | 63.25% | **68.45%** |
| **Q8_0** | 52.44% | 85.00% | 63.00% | **66.81%** |
| **Q6_K** | ~53-54% | ~85% | ~63% | ~**67%** |
| **Q5_K_M** | ~52-53% | ~85% | ~63% | ~**66.5-67%** |
| **Q4_K_M** | 50.61% | 84.00% | 63.00% | **65.87%** |
| **IQ4_XS** | ~49% | ~83% | ~62% | ~**64.5%** |

Sources: [heyneo.com](https://heyneo.com/blog/evaluating-qwen-3-6-27b-benchmarking-case-study), [reddit r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1t53dhp/)

### KLD and perplexity (Q5_K_M focus)

| Quant | PPL delta vs BF16 | Mean KLD | Size | Notes |
|-------|-------------------|----------|------|-------|
| **Q8_0** | +0.01% | ~0.005 | ~29 GB | Practically identical |
| **Q6_K** | +0.05% | ~0.010 | ~21 GB | Excellent sweet spot |
| **Q5_K_M** | ~+0.15% | ~**0.020** | ~**17 GB** | **~97% of BF16 quality** |
| **Q4_K_M** | ~+0.3% | ~0.040 | ~17 GB | ~96% of BF16 quality |
| **IQ4_XS** | ~+0.5% | ~0.060 | ~15 GB | imatrix-aware, efficient |

### Key findings for Qwen3.6-27B

- **Function calling is quantization-invariant**: BFCL scores are identical (63%) across all quants. Tool calling works equally well at any precision.
- **Code generation is the most sensitive**: ~5.5 point drop from BF16 to Q4_K_M on HumanEval. Expect more subtle syntax/logic bugs at lower precision.
- **General reasoning is robust**: Only ~2 point drop from BF16 to Q4_K_M on HellaSwag.
- **Q5_K_M is the practical sweet spot**: ~97% of BF16 quality, same disk size as Q4_K_M (~17 GB), with measurably better code generation. The "K" mixed-precision format allocates extra bits to attention layers.
- **Q5_K_M + DFlash + Turbo Quant** is an optimal combo: Q5_K_M for weight quality, DFlash drafter for ~2x generation speed, turbo4/turbo3_tcq for full-context KV cache without quality loss (PPL indistinguishable from F16, KLD < 0.03).

## Troubleshooting

**Model outputs gibberish**:
- Quantization too aggressive (Q2_K)
- Try Q4_K_M or Q5_K_M
- Verify model converted correctly

**Out of memory**:
- Use lower quantization (Q4_K_S instead of Q5_K_M)
- Offload fewer layers to GPU (`-ngl`)
- Use smaller context (`-c 2048`)

**Slow inference**:
- Higher quantization uses more compute
- Q8_0 much slower than Q4_K_M
- Consider speed vs quality trade-off
