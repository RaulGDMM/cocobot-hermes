# Bartowski Q6_K_L — Speed Benchmark 02/08/2026 (post-update)

**Modelo:** `Qwen3.6-27B-Q6_K_L.gguf` (Bartowski)
**llama.cpp:** updated (post-b10170)
**Server:** 172.23.176.1:30000 | **GPU:** RTX 5090
**Config:** MTP + ngram, KV cache K Q8_0 / V Q5_1, ctx 115K
**llama-benchy:** 0.4.0

## Speed Results (llama-benchy API)

### Run 1 (11:26:40)

| Metric | Value |
|--------|-------|
| PP 2048 | 2508.49 ± 23.26 tok/s |
| TG 32 | 97.65 ± 11.22 tok/s (peak: 100.80) |
| TTFR | 817.79 ± 7.62 ms |
| Latency (api) | 0.89 ms |

### Run 2 (11:27:01)

| Metric | Value |
|--------|-------|
| PP 2048 | 2458.58 ± 34.52 tok/s |
| TG 32 | 105.93 ± 8.17 tok/s (peak: 109.34) |
| TTFR | 834.52 ± 11.62 ms |
| Latency (api) | 0.81 ms |

### Run 3 (11:27:58)

| Metric | Value |
|--------|-------|
| PP 4096 | 2704.39 ± 23.68 tok/s |
| TG 1024 | 95.87 ± 6.13 tok/s (peak: 96.33) |
| TTFR | 1515.82 ± 13.42 ms |
| Latency (api) | 0.89 ms |

### Promedio

| Metric | Average |
|--------|---------|
| PP 2048 | **~2484 tok/s** |
| PP 4096 | **~2704 tok/s** |
| TG 32 | **~102 tok/s** |
| TG 1024 | **~96 tok/s** |
| TTFR (2048) | **~826 ms** |
| TTFR (4096) | **~1516 ms** |

## Comparison with 30/07/2026 (llama.cpp b10170)

| Test | 30/07 (b10170) | 02/08 (updated) | Δ |
|------|---------------|-----------------|---|
| PP 2048 | — | ~2484 tok/s | — |
| PP 4096 | 2770 tok/s | ~2704 tok/s | **-66 (-2.4%)** |
| PP 8192 | 2777 tok/s | — | — |
| TG 32 | — | ~102 tok/s | — |
| TG 1024 | 100.6 tok/s | ~96 tok/s | **-4.6 (-4.6%)** |
| TG 4096 | 105.3 tok/s | — | — |
| TG 8192 | 108.0 tok/s | — | — |

## Notes

- Benchmarks taken immediately after updating llama.cpp and Hermes
- PP 4096: -2.4% (2770→2704) — dentro de margen normal de variación
- TG 1024: -4.6% (100.6→96) — ligera regresión, podría ser ruido o cambio en MTP/draft
- Diferencias pequeñas; se necesitan más runs para confirmar si es real o variación normal
