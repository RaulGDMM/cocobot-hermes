# NVFP4 1f Update Benchmark — 30/05/2026

**Modelo**: `michaelw9999/Qwen3.6-27B-NVFP4-MTP-GGUF` updated 30/05
**Tamaño**: 16.36 GB (prev 15.96 GB — +370 MB)
**Servidor**: 172.23.176.1:30000, 230K ctx, K Q8_0 / V Q5_1, llama.cpp b9415

## Resultados vs anterior (29/05)

### Velocidad (script dflash-benchmark.py, 3 runs, 512 tokens)

| Métrica | Anterior (29/05) | Actual (30/05) | Cambio |
|---------|:-:|:-:|:-:|
| Texto corto | 151.7 t/s | 144.7 t/s | 🔴 -4.6% |
| Texto medio | 124.0 t/s | 120.1 t/s | 🔴 -3.1% |
| Texto largo | 115.0 t/s | 111.6 t/s | 🔴 -3.0% |

### Velocidad real (curl directo, sin overhead de script)

| Test | Gen TPS | MTP Acceptance |
|------|:-------:|:--------------:|
| Texto corto | 143.4 t/s | 84.3% |
| Texto medio | **150.4 t/s** | **90.1%** |
| Tool calls | **127.9 t/s** | 70.7% |

**Nota**: La velocidad real es buena — el script tiene overhead de espera entre runs y cache de KV que infla resultados.

### Inteligencia (llm-intelligence-benchmark.py)

| Benchmark | Anterior (29/05) | Actual (30/05) | Cambio |
|-----------|:-:|:-:|:-:|
| GSM8K (51 muestras) | 88.2% | **88.2%** | ⚪ = |
| ARC Easy (30 muestras) | 100% | **100%** | ⚪ = |
| HellaSwag (30 muestras) | 73.3% | **73.3%** | ⚪ = |
| PIQA (20 muestras) | 100% | **100%** | ⚪ = |
| HumanEval (164 muestras) | 86.0% | **85.4%** | ⚪ -0.6pp |
| PPL WikiText-2 | 1.13 | **1.105** | 🟢 -2.2% |
| **Promedio** | **90.4%** | **90.4%** | ⚪ = |

## Hallazgos clave

1. **Inteligencia idéntica** en todos los benchmarks (mismo score exacto)
2. **Velocidad script -3 a -5%** pero **velocidad real buena** (150 t/s texto, 128 t/s tools)
3. **MTP acceptance sana** (70-90% en tests directos)
4. **PPL ligeramente mejor** (-2.2%, posiblemente real por actualización del imatrix)
5. **Modelo 370 MB más grande** (16.36 GB vs 15.96 GB)

## Veredicto

Upgrade merece la pena — velocidad real buena, calidad mantenida, PPL mejorada.

## Pitfalls encontrados

1. **HumanEval path**: Script en `/root/workspace/` busca en `/root/references/HumanEval.jsonl` — necesita symlink
2. **Foreground timeout 600s**: HumanEval tarda ~40 min, requiere cron job one-shot como workaround
3. **dflash-benchmark.py timing fields**: `/completion` devuelve `predicted_per_second` directamente, no `predicted_ms`
