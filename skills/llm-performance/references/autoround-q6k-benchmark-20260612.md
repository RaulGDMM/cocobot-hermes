# AutoRound Q6_K (sphaela) — Benchmark 2026-06-12

**Modelo**: `sphaela/Qwen3.6-27B-AutoRound-GGUF` → `Qwen3.6-27B-AutoRound-Q6_K.gguf`
**Servidor**: `http://172.23.176.1:30000/v1`
**GPU**: RTX 5090 32GB + Ryzen 7 7800X3D
**Contexto**: 170,240 tokens (de 262,144 nativos)
**mmproj**: BF16 (multimodal, ~1.1 GB)
**MTP**: Activo (15 tensores, blk.64.*)
**Speculative decoding**: ngram-mod + draft-mtp
**Prompt cache**: 16 GB, activo
**Chat format**: `peg-native` (con thinking/reasoning)
**Carga del modelo**: ~3 min 15 seg

## Resultados

| Benchmark | Score | Muestras |
|---|---|---|
| GSM8K | **80.4%** | 42/51 |
| ARC Easy | **100.0%** | 30/30 |
| HellaSwag | **66.7%** | 20/30 |
| PIQA | **100.0%** | 20/20 |
| HumanEval | **84.8%** | 139/164 |
| **Promedio** | **86.8%** | — |
| PPL WikiText-2 | **1.4440** | 313 chunks |

**Tiempo total**: 3,056s (~51 min)

## Velocidad (de logs llama.cpp)

| Métrica | Valor |
|---|---|
| Gen speed (sin MTP) | ~42-47 tok/s |
| Gen speed (con MTP) | **80-140 tok/s** |
| Prompt eval (cold) | **2,200-2,800 tok/s** |
| Prompt eval (cached) | 1,100-2,200 tok/s |
| Draft acceptance (MTP) | 50-90% |
| VRAM usada | ~30.6/32.6 GB |

## Comparación vs NVFP4 1f

| Benchmark | AutoRound Q6_K | NVFP4 1f | Δ |
|---|---|---|---|
| GSM8K | 80.4% | 88.2% | **-7.8 pp** ⚠️ |
| HumanEval | 84.8% | 86.0% | -1.2 pp |
| Promedio | 86.8% | 90.4% | **-3.6 pp** |
| PPL | 1.4440 | 1.1255 | +0.32 |
| VRAM | ~30.6 GB | ~29.3 GB | +1.3 GB |
| Contexto | 170K | 260K | -90K |
| MTP speed | 80-140 tok/s | 108-143 tok/s | comparable |

## Observaciones

- **GSM8K cae notablemente**: -7.8 pp vs NVFP4 1f. AutoRound parece penalizar razonamiento matemático — probablemente el dataset de calibración no representaba bien este tipo de tareas.
- **HumanEval intacto**: 84.8% es comparable a NVFP4 1f (86.0%). La generación de código NO se ve afectada.
- **ARC/PIQA perfectos**: 100% como siempre.
- **PPL peor**: 1.44 vs 1.12 del NVFP4 1f.
- **Más VRAM, menos contexto**: 30.6 GB vs 29.3 GB, y solo 170K de contexto vs 260K.
- **MTP funciona bien**: 80-140 tok/s con draft acceptance de 50-90%.
- **SWA cache invalidation frecuente**: Los logs muestran `forcing full prompt re-processing` — known issue con modelos que usan Sliding Window Attention.

## Datos crudos

`llm-eval-qwen3.6-27b-20260612-205341.json`

## Veredicto

AutoRound Q6_K es el peor de los 4 métodos evaluados en promedio. La velocidad con MTP es comparable, pero pierde inteligencia en razonamiento matemático y usa más VRAM con menos contexto. **NVFP4 1f (michaelw9999) sigue siendo la mejor opción.**
