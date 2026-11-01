# AutoRound Q6_K + DFlash — Benchmark 2026-07-01

**Modelo**: `Qwen3.6-27B-AutoRound-Q6_K.gguf` (sphaela)
**Draft model**: `dflash-draft-3.6-q4_k_m.gguf` (DFlash, 5 blocks)
**Servidor**: `http://172.23.176.1:30000`
**GPU**: RTX 5090 32GB + Ryzen 7 7800X3D
**Contexto**: 160,000 tokens
**KV Cache**: K=q8, V=q5_1
**Speculative decoding**: DFlash (confirmed via server logs — `dflash-draft` architecture)
**mmproj**: BF16 (multimodal)
**llama.cpp build**: b9341-633cd34fb (actualizado desde 17/06)

## Velocidad (timings del servidor)

| Test | Prompt tok | Gen tok | Prompt TPS | **Gen TPS** |
|------|-----------|---------|------------|-------------|
| Corto (256) | 13 | 80 | 48 | **198.3** |
| Corto (512) | 13 | 80 | 128 | **253.4** |
| Medio (256) | 724 | 256 | 2,228 | **109.8** |
| Medio (512) | 724 | 512 | 2,213 | **141.4** |
| Largo (256) | 2,165 | 256 | 2,617 | **121.2** |
| Largo (512) | 2,165 | 512 | 2,500 | **155.2** |

## Comparación con benchmarks anteriores

| Test | 12/06 (MTP) | 17/06 (MTP) | **01/07 (DFlash)** | Δ vs 17/06 |
|------|-------------|-------------|-------------------|------------|
| Corto | ~123 tok/s | 107.7 tok/s | **198-253 tok/s** | **+84-134%** |
| Medio (512) | ~105 tok/s | 116.4 tok/s | **141.4 tok/s** | **+21%** |
| Largo (512) | ~95 tok/s | 136.8 tok/s | **155.2 tok/s** | **+13%** |
| Prefill | 2,200-2,800 | 2,670-2,690 | **2,200-2,617** | ≈ Igual |

## Hallazgos clave

1. **DFlash > MTP para este modelo**: DFlash supera consistentemente a MTP en todas las categorías. El salto es más dramático en generaciones cortas (+84-134%) y significativo en largas (+13-21%).

2. **DFlash brilla en contextos pequeños**: Con 13 tokens de prompt, el draft model puede predecir bloques enteros sin overhead → 198-253 tok/s vs ~100 base.

3. **Prefill estable**: Sin regresión tras la actualización de llama.cpp (2,200-2,617 tok/s constante).

4. **`/props` sigue mintiendo sobre speculative decoding**: `speculative.types` reporta `"none"` aunque DFlash está activo. Confirmar siempre con logs del servidor (`grep "dflash-draft"` en stdout).

5. **El benchmark API no reporta stats speculativas**: `timings_per_token[].speculative` viene vacío con DFlash (igual que con MTP). Los logs del servidor (`slot print_timing`) son la fuente de verdad.

## Configuración del servidor

```
Modelo principal: E:\Workspace\Openclaw\models\qwen36-27b\Qwen3.6-27B-AutoRound-Q6_K.gguf
Draft model: E:\Workspace\Openclaw\beellama\models\dflash-draft-3.6-q4_k_m.gguf
mmproj: E:\Workspace\Openclaw\models\qwen36-27b\mmproj-BF16.gguf
n_ctx: 160000
KV cache: q8 (K) + q5_1 (V)
```

## Veredicto

La actualización de llama.cpp + DFlash ha mejorado el rendimiento un **13-134%** respecto a la configuración anterior con MTP. DFlash es el speculative decoding method preferido para este modelo — supera a MTP en todas las métricas y no requiere tensores MTP adicionales en el modelo principal.
