# Benchmark Tracking — llama.cpp + Qwen3.6-27B AutoRound Q6_K

**Hardware**: RTX 5090 32GB | **Modelo**: Qwen3.6-27B AutoRound Q6_K | **Ctx**: 160K | **KV Cache**: K Q8_0 / V Q5_1
**Servidor**: 172.23.176.1:30000 | **MTP + ngram**: activo

---

## Historial de benchmarks (run 1 frío)

> **Importante**: Los benchmarks anteriores usaban mediana de 3 runs, pero los runs 2-3 tenían cache caliente
> y daban resultados inflados. Desde 03/07 se usa **run 1 frío** como métrica principal.

| Fecha | Versión | Texto Corto | Texto Medio | Texto Largo | Tool Calls | MTP Corto | KV Cache | Ctx | Notas |
|-------|---------|:-:|:-:|:-:|:-:|:-:|---------|-----|-------|
| 02/06 | b9474 | 134.9 t/s | 121.4 t/s | 118.7 t/s | 136.5 t/s | 68-80% | K Q4_0 / V Q5_1 | 170K | Base b9474, mmproj GPU |
| 25/06 | b9796 | 147.0 t/s | 129.9 t/s | 116.8 t/s | 142.6 t/s | 86.0% | K Q4_0 / V Q5_1 | 170K | +322 commits desde b9474 |
| **03/07** | **latest** | **121.1 t/s** | **106.5 t/s** | **105.8 t/s** | **123.2 t/s** | **85.2%** | **K Q8_0 / V Q5_1** | **160K** | **Actualización llama.cpp** |

---

## Comparación: 03/07 (latest) vs 25/06 (b9796) — run 1 frío

### Velocidad de generación

| Métrica | b9796 (25/06) | **latest (03/07)** | Cambio |
|---------|:-:|:-:|:-:|
| Texto corto | 147.0 t/s | **121.1 t/s** | 🔴 -17.6% |
| Texto medio | 129.9 t/s | **106.5 t/s** | 🔴 -18.0% |
| Texto largo | 116.8 t/s | **105.8 t/s** | 🔴 -9.4% |
| Tool calls | 142.6 t/s | **123.2 t/s** | 🔴 -13.6% |

### MTP Acceptance

| Prompt | b9796 | **latest** | Cambio |
|--------|:-:|:-:|:-:|
| Corto | 86.0% | **85.2%** | ⚪ -0.8pp |
| Medio | 61.7% | **51.3%** | 🔴 -10.4pp |
| Largo | 44.6% | **51.8%** | 🟢 +7.2pp |
| Tool calls | 82.5% | **86.7%** | 🟢 +4.2pp |

### Prompt Processing

| Métrica | b9796 | **latest** | Cambio |
|---------|:-:|:-:|:-:|
| Corto (~40 tok) | 351.4 t/s | **319.6 t/s** | ⚪ -9% |
| Medio (~790 tok) | 2424.8 t/s | **1922.1 t/s** | 🔴 -21% |
| Largo (~3163 tok) | 2858.2 t/s | **2381.1 t/s** | 🔴 -17% |

---

## Análisis

### ⚠️ Regresión de rendimiento confirmada

**Run 1 frío**: -9 a -18% en todas las métricas vs b9796. Regresión consistente, no ruido.

**Variables que cambiaron**:
1. **llama.cpp**: b9796 → latest (nueva compilación)
2. **KV cache K**: Q4_0 → Q8_0 (más preciso, más VRAM)
3. **Contexto**: 170K → 160K (debería ser neutro o ligeramente mejor)

### KV cache K Q4_0 → Q8_0

El cambio de K a Q8_0 debería **mejorar** MTP acceptance (más precisión en los keys → drafts más precisos).
De hecho, tool calls mejoran (+4.2pp). Pero no compensa la regresión general.

### Lo que SÍ mejora

- **MTP acceptance en tool calls**: +4.2pp (86.7% vs 82.5%) — más drafts aceptados
- **MTP acceptance en largo**: +7.2pp — mejor calibración en contextos largos
- **MTP acceptance en medio**: -10pp — esto es preocupante, puede indicar problema con prompts de ~800 tokens

### Posibles causas de la regresión

1. **Kernels CUDA recompilados**: Flags de compilación diferentes entre b9796 y latest
2. **Cambio en speculative decoding**: Los commits entre versiones pueden haber tocado MTP/ngram
3. **`kv_unified = true`**: Nuevo en latest, consolida KV cache en un solo buffer
4. **Batch size / ubatch**: Si cambió el tamaño de batch, afecta decoding directamente

### Conclusión parcial

La regresión es real pero no catastrófica. El servidor sigue funcionando bien:
- ~120 t/s en texto corto (suficiente para uso real)
- ~105 t/s en texto medio/largo (aceptable)
- MTP acceptance saludable (>85% en corto y tool calls)

Merece la pena investigar si es compilación o código, pero no es urgente revertir.

---

## Cómo ejecutar el benchmark

```bash
# Desde el workspace de performance:
cd /mnt/e/Workspace/Hermes/Performance

# Benchmark completo (3 runs, 512 tokens, texto + tool calls):
python3 ~/.hermes/skills/mlops/llm-inference-benchmark/scripts/dflash-benchmark.py \
  --host 172.23.176.1 --port 30000 --runs 3 --max-tokens 512

# Solo texto (sin tool calls):
python3 ~/.hermes/skills/mlops/llm-inference-benchmark/scripts/dflash-benchmark.py \
  --host 172.23.176.1 --port 30000 --runs 3 --max-tokens 512 --skip-tool-calls

# Resultados se guardan en:
# /root/workspace/benchmark-results/benchmark-YYYYMMDD-HHMMSS.json
```

## Checklist para próxima comparación

- [ ] Verificar versión exacta de llama.cpp (`llama-server.exe --version` o commits desde b9796)
- [ ] Confirmar que el servidor usa los mismos flags (MTP + ngram, spec-draft-n-max 3)
- [ ] Verificar VRAM con `nvidia-smi` antes del benchmark
- [ ] Ejecutar benchmark con `--runs 3 --max-tokens 512`
- [ ] Usar **run 1 frío** como métrica principal (evitar cache)
- [ ] Actualizar tabla arriba con resultados
- [ ] Si hay regresión >10%, investigar commits entre versiones

---

## Referencias

- Skill: `llm-inference-benchmark` (completa, con pitfalls y diagnóstico)
- JSON raw: `benchmark-20260703-232237.json` (este benchmark)
- JSON raw: `benchmark-20260625-181318.json` (b9796, 25/06)
- Skill references: historial completo de benchmarks desde mayo
