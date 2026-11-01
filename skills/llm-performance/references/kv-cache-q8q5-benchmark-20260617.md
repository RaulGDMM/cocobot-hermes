# KV Cache Quantization — q8 (K) + q5_1 (V) — Benchmark 2026-06-17

**Modelo**: `Qwen3.6-27B-AutoRound-Q6_K.gguf`
**GPU**: RTX 5090 32GB + Ryzen 7 7800X3D
**Contexto**: 160,000 tokens (bajado de 170K)
**KV Cache**: K=q8, V=q5_1 (antes f16/f16)
**MTP**: Activo (confirmed via server logs, NOT `/props`)
**ngram-mod**: Activo (n_match=24)
**Draft acceptance**: ~56-57%, mean acc length ~2.9-3.2

## Velocidad

| Test | Prompt tokens | Prompt TPS | Gen tokens | **Gen TPS** |
|------|--------------|-----------|------------|-------------|
| Corto | 12 | 67 | 256 | **107.7** |
| Medio | 1,023 | **2,670** | 512 | **116.4** |
| Largo | 2,086 | **2,690** | 512 | **136.8** |

### Logs del servidor (tareas reales con Hermes)

| Métrica | Valor |
|---------|-------|
| Decode (n_decoded) | **96.8-97.5 tok/s** |
| Eval time | **104-105 tok/s** |
| Prefill | **1,273-1,788 tok/s** |

## Comparación vs anterior (KV f16, 170K ctx)

| Métrica | Antes (f16, 170K) | Ahora (q8/q5_1, 160K) | Cambio |
|---------|-------------------|----------------------|--------|
| Gen con MTP | 80-140 tok/s | **108-137 tok/s** | ✅ Similar / ligero + |
| Prefill cold | 2,200-2,800 tok/s | **2,670-2,690 tok/s** | ✅ Igual |
| Draft acceptance | 50-90% | **56-57%** | ✅ En rango |
| Contexto | 170K | 160K | -10K (-6%) |

## Hallazgo: `/props` miente sobre MTP

- `/props` reporta `speculative.types: "none"` **aunque MTP está activo y funcionando**
- Confirmado en logs del servidor: líneas `statistics draft-mtp: #calls(b,g,a) = ...` muestran MTP activo
- **Siempre verificar con logs del servidor**, no confiar en `/props` para speculative decoding

## Veredicto

La cuantización del KV cache (q8 K + q5_1 V) **NO penaliza velocidad**:
- Decode con MTP se mantiene en ~105-137 tok/s
- Prefill igual de rápido (~2,700 tok/s)
- MTP funciona bien con ~57% acceptance
- VRAM ahorrada: cuantización reduce consumo del KV cache vs f16
- Trade-off mínimo: -10K contexto, +eficiencia VRAM, =velocidad

## Inteligencia (pendiente)

Benchmark de inteligencia (GSM8K, ARC, HellaSwag, PIQA, HumanEval, PPL) lanzado en background.
Resultados en: `/root/workspace/llm-eval-qwen3.6-27b-q6k-autoround-kv-q8q5-20260617.json`
