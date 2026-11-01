# Control vectors / uncensor en llama.cpp — landscape

Referencia de la sección 8 de SKILL.md. Verificado en esta caja (mainline b11374 + ik_llama) y HF, oct/2026.

## Flags y verificación
- `--control-vector FNAME` · `--control-vector-scaled FNAME:SCALE,...` · `--control-vector-layer-range START END` (soporte mainline desde PR ggml-org#5970, 2024; #20653 añadió las funciones de cvec a arquitecturas que las omitían, incl. qwen3.5/qwen-next).
- Verificar en el build local: `llama-server.exe --help | grep -i control-vector` desde WSL interop. **No usar `strings` del stub .exe** (el código vive en `llama.dll`; strings del exe = falso negativo conocido). El mensaje `control vector n_embd does not match model` confirma la validación de dimensionalidad.
- Arquitectura nueva sin soporte → el vector no se aplica; comprobar con un arranque de prueba o grep `control vector` en `llama.dll`.

## Model-espacificidad
El vector se deriva sobre las activaciones de UN modelo concreto y se valida por n_embd: no reutilizar entre modelos/tamaños distintos, ni dentro de la misma familia (el cvec de Flash-Next no vale para el 27B denso). El de Strata (`--cvec-mode project --cvec-dir per-layer`) vive dentro del bundle del pack (`data/uncensor/*.gguf`) y tampoco transfiere.

## Formatos
- llama.cpp aplica el vector **aditivo** (activation-addition estilo vgel, por salida de capa). El fork de Strata añade `project` + dirección por capa (más quirúrgico: KL 0,026 / top-1 94,4 % vs stock en gptq). Misma filosofía, menos control fino en mainline.
- Los repos de vectores publican a menudo dos variantes: `vector.gguf` (proyecto) y `vector-add.gguf` (aditivo) — usar la `-add` para llama.cpp.

## Publicados (estado oct/2026, HF API)
- **Sin vector de dirección-refusal publicado para Qwen3.8-27B.**
- `MonumentalSystems/Qwen3.8-Flash-Next-control-vectors`: solo *verbosity* y *comment-density* (NO uncensor).
- Abliterated/uncensored de fábrica para 27B: `huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF`, `orcarouter/Qwen3.8-27B-Uncensored-GGUF` (ladder IQ2→Q8 + mmproj; el abliteration de OrcaRouter nos tiró el agente en sesiones largas en la era orca de Flash-Next), `0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF`, `HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF` (conserva la cabeza NextN/MTP → mantiene velocidad de draft).
- Si no existe vector publicado y se quiere el modo toggle: derivarlo uno mismo (dirección refusal estilo repeng + set de probes) — proyecto, no un comando.

## Recetas HF (sin auth)
- Buscar repos: `curl -s "https://huggingface.co/api/models?search=<terms>&limit=10"`
- Por autor: `api/models?author=<name>` · Ficheros de un repo: `api/models/<repo>` → `siblings[].rfilename` (decisivo para saber si trae vector o solo packs).

## Expectativas (regla, no landscape)
Un control vector mueve la dirección de rechazo, no la capacidad: no esperar cambio medible en benchmarks de razonamiento cortos (GSM8K/HumanEval); el efecto real aparece en estabilidad de thinking en sesiones largas y en tasa de refusals. Al contrario que la abliteration completa, no degrada el agente de sesiones largas — elegir vector > pack abliterated si el vector existe.
