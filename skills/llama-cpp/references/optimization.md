# Performance Optimization Guide

Maximize llama.cpp inference speed and efficiency.

## CPU Optimization

### Thread tuning
```bash
# Set threads (default: physical cores)
./llama-cli -m model.gguf -t 8

# For AMD Ryzen 9 7950X (16 cores, 32 threads)
-t 16  # Best: physical cores

# Avoid hyperthreading (slower for matrix ops)
```

### BLAS acceleration
```bash
# OpenBLAS (faster matrix ops)
make LLAMA_OPENBLAS=1

# BLAS gives 2-3× speedup
```

## GPU Offloading

### Layer offloading
```bash
# Offload 35 layers to GPU (hybrid mode)
./llama-cli -m model.gguf -ngl 35

# Offload all layers
./llama-cli -m model.gguf -ngl 999

# Find optimal value:
# Start with -ngl 999
# If OOM, reduce by 5 until fits
```

### Memory usage
```bash
# Check VRAM usage
nvidia-smi dmon

# Reduce context if needed
./llama-cli -m model.gguf -c 2048  # 2K context instead of 4K
```

## Batch Processing

### Prompt processing batch size
```bash
# --ubatch-size controls how many tokens are processed in parallel during prompt eval
# Default: typically 2048 or 4096

# For RTX 5090 (32GB VRAM):
--ubatch-size 4096   # Good baseline, fits comfortably in VRAM
--ubatch-size 8192   # Diminishing returns — may help slightly if VRAM allows
```

**Diminishing returns data** (Qwen3.4-27B Q4_K_XL, RTX 5090):
| `--ubatch-size` | Prompt tok/s (105K context) | Notes |
|---|---|---|
| 4096 | ~1,850 | Good baseline |
| 8192 | ~2,088 | +13% improvement, but only if ~5GB+ VRAM free |

**Key insight:** The jump from 2048→4096 is large. From 4096→8192 it's modest (~10-15%). With limited free VRAM, a smaller batch may be more efficient because it avoids swapping. If your model uses ~25GB of VRAM, you only have ~7GB free — large ubatch sizes may not fit entirely in fast HBM.

### Generation batch size
```bash
# -b controls the physical batch for token generation
./llama-cli -m model.gguf -b 512  # Default: 512

# For long context + high VRAM:
./llama-cli -m model.gguf -b 2048
```

## Context Management

```bash
# Default context (512 tokens)
-c 512

# Longer context (slower, more memory)
-c 4096

# Very long context (if model supports)
-c 32768
```

**Long context impact on performance** (Qwen3.4-27B Q4_K_XL, RTX 5090):
| Context | Prompt tok/s | Gen tok/s | Notes |
|---|---|---|---|
| Short (<10K) | ~3,100 | ~65-70 | KV cache small, mostly bandwidth-bound |
| Medium (~50K) | ~2,500 | ~58 | KV cache growing, attention O(n²) |
| Long (~105K) | ~2,088 | ~51 | KV cache large, potential VRAM pressure |
| Very long (~153K) | ~1,850 | ~47 | KV cache dominates VRAM |

The token generation speed drops significantly with long context because the KV cache consumes more VRAM bandwidth per token. This is inherent to the attention mechanism — not a configuration issue.

## Benchmarks

### RTX 5090 (32GB VRAM) — Qwen3.x 27B models, llama.cpp

| Model | Quant | Context | Prompt tok/s | Gen tok/s | Source |
|---|---|---|---|---|---|
| Qwen3.4-27B | Q4_K_XL | 105K | 2,088 | 51.3 | Verified (RTX 5090 + WSL) |
| Qwen3.6-27B | Q4_K_M | short | — | 45.9 | llm-speed.com |
| Qwen3.6-27B | Q4_K_M | — | — | ~70 | Reddit (lmstudio) |
| Qwen3.6-27B | NVFP4 + MTP | — | — | up to 129 | Reddit (vLLM) |

**Community context:** With llama.cpp and long context (100K+ tokens), 50-60 tok/s generation is solid. Speeds of 80-100+ tok/s typically use vLLM + MTP + short context or NVFP4 (still beta).

### RTX 5090 vs R9700 (Qwen3.5-35B-A3B MoE Q4_K_XL)

| Context | RTX 5090 PP (t/s) | R9700 PP (t/s) | 5090 Advantage |
|---|---|---|---|
| 512 | 7,026 | 2,713 | 2.59× |
| 4,096 | 6,958 | 2,546 | 2.73× |
| 32,768 | 6,461 | 1,877 | 3.44× |

Token generation: RTX 5090 **194 tok/s** vs R9700 **127.4 tok/s** (1.52× advantage).

### CPU Performance (Llama 2-7B Q4_K_M)

| Setup | Speed | Notes |
|-------|-------|-------|
| Apple M3 Max | 50 tok/s | Metal acceleration |
| AMD 7950X (16c) | 35 tok/s | OpenBLAS |
| Intel i9-13900K | 30 tok/s | AVX2 |

### GPU Offloading (RTX 4090)

| Layers GPU | Speed | VRAM |
|------------|-------|------|
| 0 (CPU only) | 30 tok/s | 0 GB |
| 20 (hybrid) | 80 tok/s | 8 GB |
| 35 (all) | 120 tok/s | 12 GB |

## Tuning Checklist

When diagnosing slow inference:

1. **Check VRAM usage**: `nvidia-smi` — if free VRAM < 2GB, you're likely swapping
2. **Start with `--ubatch-size 4096`**: Good baseline for 32GB+ cards
3. **Test `--ubatch-size 8192`**: Only if you have 5GB+ free VRAM; diminishing returns after this
4. **Long context is the real bottleneck**: KV cache O(n²) attention dominates over batch size
5. **Q4_K_XL vs Q4_K_M**: Q4_K_XL uses more VRAM for weights, leaving less for KV cache — with long context this can hurt generation speed
6. **MTP (beta)**: When stabilized, 1.5x-2.5x throughput boost for compatible models (Qwen3.5/3.6, DeepSeek V3)
7. **NVFP4 (future)**: ~16x weight compression for Blackwell GPUs (SM120), still unstable in early 2026
