# Long-context degradation — baseline 19/08/2026

Prueba de degradación de calidad en contexto largo. Baseline de referencia para comparar
cambios de cuantización / KV-cache / builds.

## Setup del baseline
- Servidor: `172.23.176.1:30000`, modelo `qwen3.8-27b` (NVFP4-Q8attn MTP, perfil `qwen38_27b_nvfp4_q8attn_mtp`), `n_ctx` 230144 (nativo 262k), KV K Q8_0 / V q5_1, MTP + ngram.
- Scripts: `scripts/long_context_test.py` + `scripts/long_context_hard_test.py` (copias de trabajo en `/mnt/e/Workspace/performance/`).
- Filler: notas de reuniones sintéticas en español, seed fija (contextos reproducibles). **chars/token calibrado en vivo** con `usage.prompt_tokens`: ~4.63 para Qwen con este filler.
- `temperature=0`, `max_tokens=1024`, respuestas exactas parseadas por inclusión de string.
- `finish_reason` fue `stop` en todos los probes (sin truncamientos).

## Resultados (25/25 correctos)

### Suite easy (`long_context_test.py`, 18 probes)
- Aguja (CÓDIGO SECRETO: AZUL-DELFIN-42) a 32k/64k/96k/140k/180k × profundidad 20/50/80% → 15/15 ✅ (ctx real ~31k/62k/93k/135k/174k; prefill 9s→126s).
- Baseline 4k ✅ (2s).
- Suma de 5 PUNTO dispersos: 64k → 2904 ✅ (22.7s); 140k → 3714 ✅ (72.2s).

### Suite hard (`long_context_hard_test.py`, 7 probes)
- Aguja a ~193k × 20/50/80% → 3/3 ✅ (~131-132s cada uno).
- Multi-hop 3-sum a 135k → 1469 ✅ = 220+821+428 (72.5s).
- Multi-hop 4-sum a ~193k → 2137 ✅ = 401+123+676+937 (152.9s).
- Distractores (18 PUNTO-DECIM + 1 FINALE) a 140k → FINALE-1607 ✅ (75.6s).
- Distractores a 200k → FINALE-1330 ✅ (133.7s).

## Conclusiones
- **Sin degradación medible hasta ~200k tokens**, incluso en lectura integral (sumas multi-hop) y discriminación entre registros del mismo formato.
- El coste es **latencia, no calidad**: prefill 200k ≈ 130-155s.
- Si en conversaciones largas reales el modelo "olvida" hechos antiguos: sospechar **primero** de la compresión de conversación de Hermes (resumen del historial a nivel agente) antes que del modelo o de la KV.

## Notas de metodología
- **La aguja simple es la prueba fácil**: un modelo con atención degradada puede pasarla. Lo que realmente expone la degradación es el multi-hop (sumar N hechos dispersos y hacer aritmética) y los distractores (N-1 registros con formato casi idéntico al objetivo).
- Los probes se ejecutan secuenciales (servidor single-slot; en paralelo se encuean y contaminan).
- Para extender: contextos >200k requieren más `cache-ram` / KV más comprimida; multi-hop con aritmética cruzada entre hechos (dato en A modifica dato en B) es el siguiente nivel de dificultad.
- **Siempre verificar que `finish_reason` sea `stop`**: un `length` invalida el probe (max_tokens cortó la respuesta).
- JSONs raw: `/mnt/e/Workspace/performance/results/long-context-20260819-164559.json` (easy) y `long-context-hard-20260819-170302.json` (hard).
