---
name: llm-intelligence-suite
description: Benchmark LLM intelligence (GSM8K/HumanEval) via llama.cpp.
version: 1.0.0
author: cocobot
license: MIT
metadata:
  hermes:
    tags: [llm, benchmark, llama.cpp, qwen, intelligence, reasoning, humaneval, rtx5090]
    related_skills: [llm-performance, llm-inference-benchmark]
---

# LLM Intelligence Suite — Qwen + llama.cpp (RTX 5090)

## When to Use
- Cuando hay que **medir la inteligencia/razonamiento** de un modelo chat local (Qwen u otro) servido por llama.cpp en la RTX 5090.
- Cuando hay que **comparar un modelo nuevo vs una versión anterior** (3.6 → 3.8 → 3.9...) con la misma suite.
- NO para velocidad/throughput (eso es `llm-inference-benchmark`).

Benchmarks de **inteligencia/razonamiento** (no velocidad — la velocidad vive en `llm-inference-benchmark` / `benchmark-tracking.md`). Suite v1 (canario de regresión): **GSM8K → ARC Easy → HellaSwag → PIQA → Perplexity → HumanEval** — ARC/PIQA/HumanEval ya SATURADOS (100/100/97), útil solo para detectar roturas. **En comparativas de versión omitir los clavados al 100%** (ARC-Easy/PIQA en v1; ARC-C en v2 si el baseline marca ≥99): no discriminan y gastan horas; correr solo los discriminables — Raúl: v1 = GSM8K+HellaSwag+HumanEval, v2 = GPQA+HE++MATH.

**Suite v2 (`/root/workspace/scripts/benchmarks/suite2/`, post-saturación, creada 09/10)**: ARC-Challenge-100 + GPQA-Main-50 + HumanEval+-164 + MATH-level4+-60, datasets JSONL fijados con semilla, sampling idéntico T0.6/0.95/20 en ambos perfiles (`run-suite2.py --profile fn|27b`), checkpoint + `--resume`, `--calibrate N` para presupuesto. Para comparativas de inteligencia entre modelos usar v2; NO mezclar columnas v1↔v2 (datasets distintos y v1-27B es greedy).

## ⚠️ Techo de tokens en Strata: el thinking comparte bote con la respuesta (verificado 10/10)
En Strata el contador del log `[strata] thinking: N of max M tokens` revela que **`max_tokens` cubre razonamiento + respuesta juntos**: un xhigh de ~10K tokens de thinking deja sin espacio la respuesta y sale vacía/recortada (`finish_reason: "length"`). El techo seguro NO es el de v1 (8192): para xhigh en benchmarks duros hay que dar **32768 de techo y reintento a 65536** (verificado: una física GPQA-like usó 27.286 tokens de salida y cerró con `finish_reason: stop` en 5m49s). Reglas:
- **Nunca juzgues un score de Strata sin comprobar truncamientos**: mira `finish_reason` en la respuesta (el `chat()` de `suite2_engine.py` ya lo propaga como tupla `(texto, finish)` y reintenta a 65536 si viene `length`, marcando `"truncated": true` en details). Tras cada run: `grep -c truncated` / contar `finish_reason==length` residual.
- Techos fijados en suite2 tras el fix: ARC 16384, GPQA 32768, HumanEval+ 32768, MATH 32768 (antes ARC 8192 / GPQA 16384 → subestimaban).
- El reintento por truncamiento **no es determinista** (sampling) pero es la alternativa justa a penalizar por un límite de petición; documenta si algún ítem sigue truncado a 65536.
- Coste real: GPQA ~4 min/ítem con xhigh → ~3 h para 50 ítems. Presupuesta en consecuencia.

## Servidor / runners por backend
- **llama.cpp (27B)**: `172.23.176.1:30000`, sin auth.
- **Strata (Flash-Next)**: `172.23.176.1:8097`, exige `Authorization: Bearer $(cat ~/.hermes/secrets/strata-api-key)`; verificar modelo/n_ctx/sampling vivo con `GET /props` → `default_generation_settings.params` (`/server_info` y `/version` NO existen en Strata ≥0.1.44: devuelven 404; la versión del motor va en `release-manifest.json` del dir de instalación). El motor NO manda auth → wrapper monkey-patch de `requests.post` en el runner (ver `run-flashnext-intelligence.py`) SIN tocar el motor compartido. Strata **no devuelve logprobs** → PPL siempre vacío (limitación conocida, issue #675). Lanzar SIEMPRE con `/usr/bin/python3` (el python3 de Hermes no tiene `requests`).

**Servidor**: `172.23.176.1:30000` (llama-server, MTP + ngram). Hardware: RTX 5090 32GB.
**Reasoning**: se corre en **xhigh** (el usuario lo quiere así — máximo rendimiento de inteligencia, aunque genere muchos tokens).

## Archivos clave
| Archivo | Qué es |
|---|---|
| `/root/workspace/llm-intelligence-benchmark.py` | **Motor** de la suite. Funciones: `evaluate_gsm8k(BASE,MODEL)`, `evaluate_arc_easy`, `evaluate_hellaswag`, `evaluate_piqa`, `evaluate_perplexity`, `evaluate_humaneval`. Todas devuelven `(score, details)` — o `(geo,arith,total_tokens)` en PPL. Datasets embebidos. |
| `/root/workspace/scripts/benchmarks/run-<model>-intelligence.py` | **Runner por modelo**: importa el motor y orquesta los 6 benchmarks en orden, guardando JSON incremental. Plantilla parametrizada en `scripts/runner-template.py`. |
| `/root/workspace/scripts/benchmarks/<model>-intelligence-<YYYYMMDD>.json` | Salida: `scores`, `details` (con cada pregunta + `correct`), `perplexity`, `elapsed_seconds`. |
| `/root/workspace/scripts/benchmarks/intelligence-benchmark-tracking.md` | **Tracking de inteligencia** con historial por versión. Actualizar al terminar cada run. |
| `/root/workspace/HumanEval.jsonl` | Dataset de código (164 casos). Si falta, hay una copia válida en `~/.hermes/skills/mlops/llm-performance/`. |

## Flujo (paso a paso)

### 1. Verificar el servidor (SOLO LECTURA)
Nunca modificar la config del llama-server — Raúl lo carga él y quiere que se use tal cual. Solo comprobaciones GET:
```bash
# Modelo + n_ctx + MTP activos
curl -s http://172.23.176.1:30000/v1/models
curl -s http://172.23.176.1:30000/server_info | python3 -m json.tool | grep -iE 'n_ctx|spec|mtp|kv'
```
Confirma que el `model` devuelto coincide con el que vas a medir. Si no coincide, **dile a Raúl** (no lo cambies tú).

### 2. Verificar max_tokens (CRÍTICO con xhigh)
Con reasoning **xhigh** un GSM8K duro genera ~900–1100 tokens de razonamiento + respuesta. El motor por defecto usaba `max_tokens=2000`, lo cual **cortaba** razonamientos largos y daba respuestas vacías.
- Comprobar: `grep -n "max_tokens" /root/workspace/llm-intelligence-benchmark.py`
- Si es < 8192, subir a **8192** (tope de seguridad — el modelo normalmente termina en EOS; 8192 solo protege contra corte anómalo). **8192 es un tope, no un objetivo.**
- Verificado: con 8192 y xhigh, **0 truncamientos** en un run completo.
- **PERO 8192 NO basta para Qwen3.8-Flash-Next (Strata)**: su thinking bajo xhigh puede llegar a los 8K y el benchmark mide con la respuesta cortada. **El límite está en la petición, NO en la config de Strata** (verificado 04/10): Strata no aplica tope de pensamiento por defecto — `reasoning_budget_tokens` sin definir en cocobot.json, `/settings` defaults `{}`, y si una petición no trae `max_tokens` usa todo el contexto restante (server.py:2624; una petición real de Hermes con prompt de 55.6K salió con max_tokens 206516 de 262144). **NO poner max_tokens/reasoning_budget_tokens en la config de Strata: limitaría también a Hermes, que ahora piensa sin tope.**
- **Rerun Flash-Next: cambiar el `max_tokens` que envía el benchmark a 32768** (término medio 16384 si el tiempo aprieta — ~40-60 t/s → 8K≈2-3min, 16K≈4.5-7min, 32K≈9-14min por pregunta dura; la mayoría termina mucho antes). Como el motor es compartido con el baseline 27B (validado con 0 truncamientos a 8192), **no editar el motor**: sobreescribir `max_tokens` en el payload desde el monkey-patch de `requests.post` del runner (misma técnica que la inyección de auth/reasoning_effort). Anotar la asimetría de techo en la comparativa. Verificar truncamiento real: `got` vacío en details.
- **Strata y el esfuerzo**: la chat_template del modelo solo admite low/medium/xhigh y traduce `high`→`xhigh` (default xhigh) — mandar `high` o `xhigh` es lo mismo. Hermes manda xhigh (agent.reasoning_effort).
- **SAMPLING en Strata**: si el `cocobot.json` no tiene bloque `sampling`, Strata corre **GREEDY** (server.py: "an absent temperature keeps the engine's default, which is greedy"). El config VIVO es **T1.0/0.95/20** desde 16/10 (decisión de Raúl: la calidad de thinking oficial vale más que la ventaja de T0.6 en HumanEval; `start-hermes.ps1` reescribe 1.0 en cada arranque). Los runners deben inyectar sampling EXPLÍCITO en el payload (monkey-patch) para que el JSON documente la config medida, y ese muestreo debe **coincidir con la columna baseline comparada** (T1.0 ↔ card10; T0.6 ↔ cfg06 y suite2) o el delta queda confundido por el sampling.
- **Verificar qué sampling está activo** sin tocar config: en Strata, `GET /props` (ver 'Servidor / runners') devuelve el sampling vivo directo; en otros backends manda 4 peticiones idénticas sin `temperature` — si varían, hay sampling del config; si son idénticas, greedy.

### 3. Auditar los datasets (evitar penalización injusta)
Antes de comparar, auditar que los `expected` sean correctos — un typo en el dataset penaliza a TODAS las versiones igual y rompe la comparativa.
- Caso real encontrado: GSM8K "1200 unique items a day... open 26 days... 150 not sold" → `expected` decía `30450` pero la correcta es `31050` (1200×26−150). Qwen3.6 respondió 31.050 y lo marcaban como fallo. Corregir el `expected` en el motor.
- Al auditar, recalcula el impacto sobre los runs previos para saber si la comparativa cambia.

### 4. Calibrar xhigh (opcional pero recomendado)
Antes del run largo, medir cuánto razonamiento genera un problema duro para confirmar que max_tokens da de sobra:
```python
# /tmp/calibrate.py — un GSM8K duro + uno fácil, medir tokens de reasoning_content
```
Bueno para confirmar velocidad bajo carga (~61-65 t/s) vs en vacío (~98 t/s con MTP).

### 5. Crear el runner por modelo
Copia `scripts/runner-template.py` → `/root/workspace/scripts/benchmarks/run-<model>-intelligence.py` y edita `BASE`, `MODEL`, `OUT` (OUT con fecha). Mantiene el orden GSM8K→ARC→HellaSwag→PIQA→PPL→HumanEval y guarda JSON incremental tras cada benchmark (si cae a mitad, no pierdes lo hecho).
- **Pitfall de logging**: la plantilla define `def log(m, *a, **k): print(m, *a, **k)` — si llamas `log(..., flush=True)` la firma SIEMPRE debe aceptar `**k`. Si usas `print` directo, pon `flush=True` o el log no se escribe en tiempo real.

### 6. Lanzar en background
```bash
cd /root/workspace/scripts/benchmarks
# background=true + notify_on_complete=true (el foreground con timeout 600s NO basta — el run dura ~45-50 min)
python3 -u run-<model>-intelligence.py > <model>-intelligence-<YYYYMMDD>.log 2>&1
```
**NO usar `nohup`** (falla en este entorno, exit -1). Usar el mecanismo background de Hermes con `notify=true` (booleano literal — un string 'True' es rechazado).
- **Runs desatendidos (toda la noche)**: lanzar con `persist_on_release=true` DESDE el primer lanzamiento — /stop, /new o la compresión de sesión matan un background normal a mitad de run, y matar+relanzar para añadir persistencia tira el progreso hecho. El checkpoint JSON solo salva si relanzas con `--resume` y el mismo `--profile`/`--tag`.

### 7. Monitorizar cada ~10 min
- `process_manage(action="wait", session_id=..., timeout=600)` para bloquear hasta 10 min, o `poll` — es una herramienta diferida: no está en la lista de tools, cargar su schema con `tool_describe('process_manage')` e invocar con `tool_call` (el nombre `process` a secas no existe).
- El log hace checkpoint de HumanEval **cada 20 casos** — no verás cambio hasta el siguiente múltiplo de 20. `stat -c %y` sobre el log para confirmar que sigue escribiendo.
- Avisar al usuario con el progreso + ETA, pero **el presupuesto es engine-dependent: remedir tras cada cambio de motor/pack** en vez de extrapolar (HE medido: ~55 s/caso con orca/0.1.40.3 @T1.0 → 150 min; ~22 s/caso con gptq/0.1.44.1 @T1.0 → ~60 min; GSM8K+HellaSwag ≈ 5-6 min en ambos).
- **Pitfall**: el aviso de `notify_on_complete` puede llegar de una sesión antigua si lanzaste dos veces (primera con nohup que falló, segunda correcta). Verifica con `ps aux | grep run-` y el mtime del log que el proceso vivo es el correcto antes de alarmarte.

### 8. Al terminar: extraer y comparar
```python
import json
d = json.load(open("/root/workspace/scripts/benchmarks/<model>-intelligence-<YYYYMMDD>.json"))
print(d["scores"])  # gsm8k, arc_easy, hellaswag, piqa, humaneval, average
```
- **Pitfall del campo `average`**: NO es comparable entre JSONs de distintas versiones tal cual. En el runner de 3.8 `average` = **media de 4** (razonamiento); en el JSON de 3.6 era **media de 5** (incluye código). **Siempre reconstruye la media a mano** a partir de los 4 benchmarks de razonamiento y/o los 5 con código.
- **Pitfall PPL**: el script mide logprobs con **1 token/chunk** → valores tipo 1.0040 vs 1.4585 son **artefacto de la medición, NO señal de calidad**. No uses PPL para comparar modelos a menos que remeasures con ventana de tokens completa.
- **Potencia estadística real de la suite**: SE(GSM8K n=51)=4.5pp, SE(HellaSwag n=30)=7.3pp, SE(HumanEval n=164)=1.7pp — solo HumanEval resuelve deltas de 2-4pp. Para comparar configs usa **McNemar exacto sobre ítems discordantes** (cruza `details` por `task_id`/`q`) y el **pooled de 295 items** como métrica única; ARC/PIQA están saturados (siempre 100) y no informan.
- **Cambios de motor Strata se controlan con rerun greedy**: el motor y `--prefill` cambian entre versiones; un perfil greedy de control en el motor nuevo (reproduce ítem a ítem el greedy anterior) aísla el confound antes de atribuir deltas al sampling.

### 9. Análisis de fallos (lo que de verdad importa, no solo %)
No te quedes con el porcentaje — cruza los `details` para saber qué se movió de verdad:
```python
# ¿Qué problemas curó X que Y fallaba? ¿Qué fallos nuevos introdujo X?
fX = [x for x in dX["details"]["humaneval"]["details"] if not x["correct"]]
fY = [x for x in dY["details"]["humaneval"]["details"] if not x["correct"]]
idsX = {x["task_id"] for x in fX}; idsY = {x["task_id"] for x in fY}
curados  = idsY - idsX   # X acierta, Y fallaba
nuevos   = idsX - idsY   # X falla, Y acertaba
solapados= idsX & idsY
```
- Si `curados` y `nuevos` son parecidos y neto ~0 → es **ruido** (GSM8K típico).
- Si neto es claramente positivo/negativo → mejora/regresión **real** (HumanEval de 3.8 curó 14, rompió 8 → +6 neto → mejora real).
- **Verificar truncamiento** (solo si hay sospecha de corte por max_tokens): comprobar que `got` no quede vacío en GSM8K/ARC/HellaSwag/PIQA, y que los fallos de HumanEval sean tracebacks/errores de test reales y no código incompleto.

### 10. Registrar en tracking
Actualizar `/root/workspace/scripts/benchmarks/intelligence-benchmark-tracking.md`:
- Añadir fila al historial (fecha, modelo/cuantización, KV, ctx, los 4 razonamientos, media 4, HumanEval, PPL*, tiempo).
- Añadir una sección de comparativa vs la versión anterior comparable (misma cuantización/KV).
- Incluir el análisis de fallos (curados/nuevos/solapados).
- Marcar `*` en PPL si no es comparable.

## Resultado de referencia (18/10 — baseline oficial config viva)
**Flash-Next pack gptq + motor 0.1.44.1, T1.0/0.95/20, xhigh, 32K, subset sin ARC/PIQA, media 2 pasadas**: GSM8K 86.3 / HellaSwag 78.3 (n=30: las 2 pasadas difieren 10pp — no concluyente) / **HumanEval 96.9 (98.2 en una pasada = récord de la suite)** / pooled 245 = 92.45%. Futuros A/B parten de aquí (tracking 18/10; runner `run-flashnext-gptq-compare.py`). El motor 0.1.44.1 corre HumanEval a ~23 s/ítem (orca@0.1.40.3: ~55 s) — presupuesta ~65 min/pasada del subset.

**Suite v2 baseline vivo (19/10, el de Qwen4)**: gptq@T1.0, xhigh → ARC-C 98 / GPQA 82 / HE+ 92.1 / MATH 90 / **pooled 91.98%**. Runner: `run-suite2.py --profile fn --sampling '{"temperature":1.0,"top_p":0.95,"top_k":20}' --tag gptq-t10`. OJO tiempo real: **~4.2 h** (GPQA a T1.0 tarda 137m — ítems de 30-48K de pensamiento), no las ~2 h del presupuesto T0.6. El baseline viejo 10/10 (93.85%) era un draw alto con confound triple (pack/motor/T).

## Resultado de referencia (14/08)
**Qwen3.8-27B unsloth Q6_K, ctx140k, KV K=Q8/V=q5_1, xhigh** → GSM8K 88.2%, ARC 100%, HellaSwag 73.3%, PIQA 100%, **media 4: 90.4%**, **HumanEval 92.7% (152/164)**, 44.5 min.
vs Qwen3.6-27B AutoRound Q6_K (17/06): media 4 88.7% → HumanEval 89.0%. **3.8 gana en todo, sin regresión, ~12% más rápido.**

## Pitfalls resumidos
1. **NO tocar la config del llama-server** — solo lecturas. Si el modelo no coincide, avisa.
2. **max_tokens** debe ser ≥ 8192 con xhigh, o se corta el razonamiento y salen respuestas vacías.
3. **`average` del JSON no es comparable** entre versiones (media 4 vs media 5) — reconstruir a mano.
4. **PPL no comparable** (1 token/chunk) — artefacto, no calidad.
5. **nohup falla** (exit -1) — usar background de Hermes con `notify_on_complete=true`.
6. **HumanEval hace checkpoint cada 20** — el log no se mueve hasta el siguiente múltiplo de 20; usa mtime para confirmar que vive.
7. **Auditar los datasets** antes de comparar (tipos en `expected` penalizan a todos).
8. **Aviso de sesión antigua**: si lanzaste dos veces, el `notify_on_complete` puede llegar del proceso muerto — verifica con `ps` + mtime antes de alarmarte.
