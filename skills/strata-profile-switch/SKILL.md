---
name: strata-profile-switch
description: Use when restarting Strata uncensored or normal mode.
metadata:
  tags: [strata, uncensored, censura, control-vector, perfil, reinicio]
---

# Strata: cambiar perfil normal ↔ uncensored

Triggers: "reinicia strata sin censura", "pon strata en modo normal", "¿en qué modo está strata?".

## Cómo está montado (2026-10-25)
- Install: `/mnt/e/Workspace/Openclaw/strata-nvfp4/strata-nvfp4/`.
- Perfiles: `config/cocobot-normal.json` (SIN `--control-vector-*`/`--cvec-*`, `"uncensored": false`) y `config/cocobot-uncensored.json` (control vector uncensor :1.0, capas 8-33, project). Resto de args idénticos.
- Perfil activo: `config/strata-profile.txt` (la default `normal` solo aplica si el fichero NO existe; escrito, persiste entre arranques).
- `start-cocobot.cmd` copia `cocobot-<perfil>.json` → `cocobot.json` en CADA lanzamiento. Tanto `start-hermes.ps1` como el broker lanzan ese .cmd → siempre mismos parámetros. **Nunca editar `cocobot.json` a mano**: se sobrescribe; editar el perfil (y si es un arg común, en AMBOS perfiles).
- `start-hermes.ps1 -StrataProfile normal|uncensored` fija y persiste el perfil (no reinicia un Strata ya cargado). SIN el flag el ps1 NO toca `strata-profile.txt`, lo lee → cualquier arranque completo (incl. Desktop `Start Hermes.lnk` → `start-hermes.bat` → ps1 sin args, que reenvía `%*`) mantiene el último perfil elegido; solo un flag explícito lo cambia. Para responder «¿en qué modo arrancará?», leer el fichero con `status`, no suponer la default.
- Por qué existe `normal`: con >90K tokens el thinking degeneraba en bucles tipo "47×89 = 4183" con el control vector puesto (sospecha, A/B pendiente).

## Procedimiento
1. `bash ~/.hermes/skills/mlops/strata-profile-switch/scripts/strata-profile.sh status`
2. Avisar a Raúl ANTES: el reinicio corta el LLM 1-3 min; si esta sesión corre sobre Strata, la respuesta se interrumpe.
3. `bash .../strata-profile.sh normal` o `... uncensored` → escribe el perfil y pide al broker un gpu-exec trivial (async), que para Strata y lo relanza vía start-cocobot.cmd (con trim de working sets y reintentos).
4. Verificar: `status` muestra `cvec en cocobot.json` acorde y `/health` con loaded=true.

## Pitfalls
- El cambio de perfil INVALIDA los diálogos aparcados en conv-disk: el arranque nuevo los refusa (`2 refused (another model, engine version or settings)`) porque el KV depende de los pesos efectivamente activos (con/sin cvec). El primer turno tras conmutar paga re-read completo (medido 17,8 s para 70K, 3925 t/s). Es comportamiento correcto, no un bug; avisar a Raúl de ese coste al conmutar sesiones largas.
- Scripts auxiliares escritos con `write_file` que cargan la api-key inline (`$(cat ~/.hermes/secrets/...)`) quedan REDACTADOS en disco (`*** (`) por el hook de secrets → bash muere en parse (exit 2) SIN ejecutar nada. `/health` no necesita auth: los watcher scripts NO deben leer claves. Verificar siempre `bash -n` antes de lanzar en background.
- Timing real del relevo (medido 25/10): gpu-exec queued → engine started ~28 s → health loaded=true ~64 s; pinned 42,00 GiB en el relevo (banda 0 fallos). Watcher con poll cada 10 s + ancla `engine started` por offset del log es suficiente.
- El reinicio va SIEMPRE por el broker (regla VRAM); no lanzar el .cmd desde WSL.
- Si el broker está ocupado (ComfyUI), el gpu-exec se encola; esperar.
- El server acepta `"uncensored": bool` por petición, pero solo tiene efecto si el vector está cargado (perfil uncensored).
