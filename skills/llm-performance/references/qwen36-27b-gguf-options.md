# Qwen3.6-27B GGUF Quantization Options

## Available GGUF Files (unsloth/Qwen3.6-27B-GGUF)

### Standard Quantizations
| File | Size | Quality | Notes |
|---|---|---|---|
| `Qwen3.6-27B-Q8_0.gguf` | ~54GB | Highest | Too large for 32GB GPU |
| `Qwen3.6-27B-Q6_K.gguf` | ~27GB | Very high | Just fits, no room for KV |
| `Qwen3.6-27B-Q5_K_M.gguf` | ~18GB | High | **Best balance** |
| `Qwen3.6-27B-Q5_K_S.gguf` | ~17GB | High | Slightly smaller |
| `Qwen3.6-27B-Q4_K_M.gguf` | ~15GB | Good | **Most popular** |
| `Qwen3.6-27B-Q4_K_S.gguf` | ~14GB | Good | Smaller variant |
| `Qwen3.6-27B-Q4_1.gguf` | ~15GB | Good | Legacy format |
| `Qwen3.6-27B-Q4_0.gguf` | ~14GB | Good | Legacy format |
| `Qwen3.6-27B-Q3_K_M.gguf` | ~11GB | Moderate | Aggressive compression |
| `Qwen3.6-27B-Q3_K_S.gguf` | ~10GB | Moderate | More aggressive |
| `Qwen3.6-27B-IQ4_XS.gguf` | ~14GB | Good | I-quant, compact |
| `Qwen3.6-27B-IQ4_NL.gguf` | ~14GB | Good | I-quant no-linear |

### Unsloth Dynamic (UD) Quantizations
| File | Size | Quality | Notes |
|---|---|---|---|
| `Qwen3.6-27B-UD-Q8_K_XL.gguf` | ~54GB | Highest | Dynamic quant, largest |
| `Qwen3.6-27B-UD-Q6_K_XL.gguf` | ~27GB | Very high | Dynamic quant |
| `Qwen3.6-27B-UD-Q5_K_XL.gguf` | ~17GB | High | **Recommended UD** |
| `Qwen3.6-27B-UD-Q4_K_XL.gguf` | ~15GB | Good | **Popular UD** |
| `Qwen3.6-27B-UD-Q3_K_XL.gguf` | ~11GB | Moderate | Dynamic quant |
| `Qwen3.6-27B-UD-Q2_K_XL.gguf` | ~8GB | Lower | Very aggressive |
| `Qwen3.6-27B-UD-IQ3_XXS.gguf` | ~10GB | Moderate | I-quant dynamic |
| `Qwen3.6-27B-UD-IQ2_M.gguf` | ~8GB | Lower | Very aggressive |
| `Qwen3.6-27B-UD-IQ2_XXS.gguf` | ~7GB | Lowest | Maximum compression |

### Alternative Sources
| Source | File | Size | Notes |
|---|---|---|---|
| cHunter789 | `Qwen3.6-27B-i1-IQ4_XS-GGUF` | ~14.7GB | Optimized IQ4_XS, attn_qkv fully IQ4_XS |

## DFlash Draft Models (z-lab/Qwen3.6-27B-DFlash)

The draft model is a lightweight 5-layer model that shares token embedding/LM head with the target at runtime.

| Quantization | Size | Notes |
|---|---|---|
| Q4_K_M | ~7GB | Recommended |
| Q5_K_M | ~8GB | Higher quality drafter |
| IQ4_XS | ~5GB | Compact |

**Note**: Q8 drafters typically reduce tok/s due to larger size and diminishing quantization benefits for short-range token guessing.

## VRAM Tradeoffs (RTX 5090, 32GB)

### Configuration A — Best Quality
- Target: Q5_K_M (~18GB)
- Draft: Q4_K_M (~7GB)
- KV: turbo4 + turbo3_tcq
- **Total**: ~26-28GB -> ~100K-120K context

### Configuration B — Max Context
- Target: IQ4_XS (~14.7GB)
- Draft: IQ4_XS (~5GB)
- KV: turbo3_tcq + turbo3_tcq
- **Total**: ~20-22GB -> ~200K context

### Configuration C — Unsloth Dynamic
- Target: UD-Q5_K_XL (~17GB)
- Draft: Q4_K_M (~7GB)
- KV: turbo4 + turbo3_tcq
- **Total**: ~25-27GB -> ~120K-150K context

## Download Commands

```bash
# Target model (Unslowth)
huggingface-cli download unsloth/Qwen3.6-27B-GGUF Qwen3.6-27B-Q5_K_M.gguf --local-dir ./models

# DFlash draft model
huggingface-cli download z-lab/Qwen3.6-27B-DFlash --local-dir ./models/draft

# Multimodal projector (optional)
huggingface-cli download unsloth/Qwen3.6-27B-GGUF mmproj-BF16.gguf --local-dir ./models
```
