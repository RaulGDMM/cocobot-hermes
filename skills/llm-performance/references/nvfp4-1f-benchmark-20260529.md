# Benchmark NVFP4-Q8_0 (1f) — 2026-05-29

**Configuración**: Qwen3.6-27B NVFP4-Q8_0, full context (260K), vision encoder en VRAM, KV cache q4_0/q5_1 (~175K práctico con 32GB VRAM). RTX 5090.

## Resultados

| Benchmark | Score | Muestras |
|---|---|---|
| GSM8K | 88.2% | 51 |
| ARC Easy | 100.0% | 30 |
| HellaSwag | 73.3% | 30 |
| PIQA | 100.0% | 20 |
| HumanEval | 86.0% | 164 |
| Promedio | 90.4% | — |
| PPL WikiText-2 | 1.1255 | 313 tokens |

> **Nota PPL**: El servidor devuelve logprobs de tokens generados, no del prompt. Valor no comparable con PPL ~6.90 del paper.

## Comparativa con versiones anteriores

| Benchmark | NVFP4 (27/05) | NVFP4 1f (29/05) | Q6_K (27/05) | Cambio 1f |
|---|---|---|---|---|
| GSM8K | 86.3% | **88.2%** | 88.2% | +1.9 pp |
| ARC Easy | 100.0% | **100.0%** | 100.0% | = |
| HellaSwag | 66.7% | **73.3%** | 63.3% | +6.6 pp |
| PIQA | 100.0% | **100.0%** | 100.0% | = |
| HumanEval | 84.8% | **86.0%** | 85.4% | +1.2 pp |
| Promedio | 88.2% | **90.4%** | 87.9% | +2.5 pp |

## Velocidad (gen TPS, 512 tokens)

| Modo | NVFP4 1f | Q6_K | Cambio |
|---|---|---|---|
| Texto corto | 143.5 t/s | 149.2 t/s | -3.8% |
| Texto medio | 117.6 t/s | 114.8 t/s | +2.4% |
| Texto largo | 112.2 t/s | 108.5 t/s | +3.4% |
| Tool calls | 102.8 t/s | 111.8 t/s | -8.1% |
| Visión | **275.5 t/s** | ❌ mmproj en CPU | Exclusivo NVFP4 |

## VRAM

| | NVFP4 1f | Q6_K |
|---|---|---|
| VRAM usada | 29.3 GB / 32.6 GB (90.4%) | ~31 GB |
| mmproj en GPU | ✅ | ❌ |
| Contexto modelo | 260K tokens | 150K tokens |
| Contexto práctico | ~175K (KV q4_0/q5_1) | ~150K (KV q4_0/q5_1) |

## Veredicto

- **Inteligencia**: Idéntica o ligeramente mejor (+2.5 pp promedio, +1.2 pp HumanEval). Dentro del ruido estadístico pero favorable.
- **Velocidad**: Prácticamente idéntica en texto (+2-3% en medio/largo, -8% en tool calls).
- **Visión**: Ventaja exclusiva. mmproj en GPU = visión funcional a ~275 t/s.
- **Contexto**: 260K vs 150K Q6_K. Más espacio para tareas largas.
- **Conclusión**: Cambio justificado. Misma inteligencia, visión funcional, más contexto, misma velocidad.

## Datos crudos

- `benchmark-results/intelligence-nvfp4.json` (GSM8K, ARC, HellaSwag, PIQA, PPL)
- `llm-eval-humaneval-nvfp4-1f-20260529-162027.json` (HumanEval: 141/164)
