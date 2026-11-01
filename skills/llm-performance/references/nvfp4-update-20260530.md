# NVFP4 Update Benchmark — 30/05/2026

**Modelo**: `michaelw9999/Qwen3.6-27B-NVFP4-MTP-GGUF`
**Versión anterior**: 14.87 GB (29/05/2026 15:03)
**Versión actual**: 15.24 GB (30/05/2026 08:55)
**Diferencia**: +370 MB

## Inteligencia

| Benchmark | Anterior (29/05) | Actual (30/05) | Cambio |
|-----------|:-:|:-:|:-:|
| GSM8K (51 muestras) | 88.2% | 88.2% | = |
| ARC Easy (30 muestras) | 100% | 100% | = |
| HellaSwag (30 muestras) | 73.3% | 73.3% | = |
| PIQA (20 muestras) | 100% | 100% | = |
| HumanEval (164 muestras) | 86.0% | pendiente | — |
| Promedio | 90.4% | 90.4% | = |
| PPL WikiText-2 | 1.13 | 1.105 | 🟢 -2.2% |

## Velocidad (texto plano, 220K ctx, K Q8_0/V Q5_1)

| Métrica | Anterior | Actual | Cambio |
|---------|:-:|:-:|:-:|
| Texto corto | 151.7 t/s | 144.7 t/s | 🔴 -4.6% |
| Texto medio | 124.0 t/s | 120.1 t/s | 🔴 -3.1% |
| Texto largo | 115.0 t/s | 111.6 t/s | 🔴 -3.0% |

## MTP Acceptance

| | Anterior | Actual | Cambio |
|---|:-:|:-:|:-:|
| Corto | 65.7% | 68.5% | +2.8pp |
| Medio | 61.9% | 52.4% | -9.5pp |
| Largo | 57.0% | 44.1% | -12.9pp |

## Observaciones
- Inteligencia idéntica en todos los benchmarks
- PPL mejoró ligeramente (1.13 → 1.105)
- Velocidad -3 a -5% (modelo más grande)
- MTP acceptance baja en prompts largos (44%) — posible indicador de degradación del drafter con el nuevo imatrix
- HumanEval pendiente (timeout foreground 600s)
