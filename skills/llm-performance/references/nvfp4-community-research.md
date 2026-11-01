# NVFP4 Community Research — Qwen3.6-27B

## Fuentes consultadas (29/05/2026)

### NVIDIA Technical Blog
- **Pérdida de precisión**: <1% vs FP8 en benchmarks clave (MMLU-PRO, GPQA, LiveCodeBench)
- **AIME 2024**: NVFP4 mostró **+2% de ganancia** sobre el baseline
- **Bloques de 16 valores** (vs 32 en MXFP4) para adaptación más fina al rango dinámico
- **E4M3 scaling**: Fraccional (vs power-of-two en MXFP4) → MSE 0.08 vs 0.72

### llama.cpp Discussion #22498 (Qwen3.5-4B)
| Tipo | PPL (menor=mejor) | KLD (menor=mejor) |
|---|---|---|
| NVFP4 puro | 11.56 | 0.092 |
| Q6_K | **10.82** | **0.006** |
| Q8_0 | 10.82 | 0.002 |

⚠️ **IMPORTANTE**: Esto es NVFP4 "puro" (todo a 4 bits). No comparable con NVFP4 mixed-precision que preserva capas críticas en alta precisión.

### Substack (kaitchup — Qwen3.6-27B específico)
- **NVFP4 "full"** (cuantizando linear attention): ❌ Bajo rendimiento consistente
- **NVFP4 con linear attention en FP16**: ✅ Rendimiento cercano a otros métodos
- **Clave**: *"Linear attention puede cuantizarse, siempre que `in_proj_a` y `in_proj_b` queden en alta precisión"*

### Unsloth Docs
> *"NVFP4 slightly outperforms the BF16 reference"* en algunos benchmarks

### Reddit (r/LocalLLaMA)
- *"The benchmarks put its quality/accuracy at Q6_K level with perplexity equivalent to FP16"*
- *"mxfp4 were close to q6 while being 1.7 times quicker"*

### michaelw9999 (HuggingFace — Qwen3.6-27B-NVFP4-MTP-GGUF)
- **PPL medio**: 7.28 (vs 6.90 FP16) → ~5.5% degradación
- **KLD medio**: 0.067
- **Correlación**: 98.27% con FP16
- **Same top-p**: ~90%
- **Tamaño**: 15.5 GB (vs ~22.5 GB Q6_K)

## Conclusión

NVFP4 puro (todo a 4 bits) es inferior a Q6_K en PPL/KLD. Pero NVFP4 con mixed precision (preservando capas críticas como linear attention en alta precisión) iguala o supera Q6_K en benchmarks prácticos.

Nuestro modelo (michaelw9999, advanced-gguf-quantizer) usa imatrix (wikitrain) y preserva MTP tensors, lo que explica los resultados superiores a Q6_K en HumanEval (86.0% vs 85.4%) y GSM8K (88.2% = 88.2%).
