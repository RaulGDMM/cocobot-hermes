---
name: minimax-music3
description: "Generate songs with MiniMax Music 3 via ComfyUI broker."
tags: [music, minimax, open-source, comfyui, broker, vocals]
related_skills: [ace-step-music, comfyui-local]
---

# MiniMax Music 3 — Generación de Música Local

Genera canciones completas (con o sin voces) hasta 6 min localmente vía el
broker de ComfyUI (`http://172.23.176.1:8791`, env `OPENCLAW_COMFYUI_LOCAL_BROKER_URL`).
Mismo flujo que ACE Step 1.5 XL y H3: el broker hace swap de GPU (mata
`llama-server`, arranca ComfyUI, ejecuta, restaura llama-server con KV slots).

## Cuándo usar qué modelo

| Modelo | Cuándo |
|---|---|
| **MiniMax Music 3** (este skill) | Vocales realistas, mezcla más limpia, estructura de canción completa, calidad tipo Suno v3.5. Producción final. |
| **ACE Step 1.5 XL** (ace-step-music) | Cinemática/orquestal, LoRA personalización, edición con denoise parcial, rapidez, licenciar 100% libre. |

## Modelos instalados (F:/ComfyUIModels, visible en C:\ComfyUI\models)

```
diffusion_models/minimax_music3_dit_fp16.safetensors          (4.6 GB, calidad alta)
diffusion_models/minimax_music3_dit_int8_convrot.safetensors  (2.3 GB, low VRAM)
text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors (8.6 GB)
vae/minimax_music3_dav.safetensors                            (0.2 GB)
```

Fuente: `Comfy-Org/MiniMax-Music-3` en Hugging Face (repackaged de
`MiniMaxAI/MiniMax-Music3`). Nodos nativos de ComfyUI >= 0.33:
`MiniMaxMusic3TextEncode`, `EmptyMiniMaxMusic3LatentAudio`, `VAEDecodeAudioTiled`.
Licencia: MiniMax-Music3 Community License (excluye despliegue local en UE/EEUU/UK/KR —
misma situación que H3; se acepta igual).

## Comandos

**Canción única (producción):**
```bash
uv run /root/.hermes/skills/media/comfyui-local/scripts/generate_minimax_music3.py \
  --caption "Global Metadata: ... Vocal Details: ... Arrangement: ..." \
  --lyrics "[Verse]
...
[Chorus]
..." \
  --duration 180 \
  --quality high \
  --filename /path/to/output.mp3
```

**Instrumental:** `--instrumental` (o `--lyrics ""`).

**Batch 3 variaciones:** `--count 3` (seeds únicos automáticos; archivos `output-1.mp3`, `output-2.mp3`, ...).

**Low VRAM:** `--quality fast` (DiT INT8) y/o `--tiled-decode` (decode VAE por
tiles, corta VRAM en canciones largas; riesgo leve de seams en bordes).

**Opciones:** `--steps` (default 30, valor del template oficial), `--cfg`
(default 1.7), `--seed` (reproducir), `--format flac`, `--timeout-seconds`
(default 1800).

## ⚠️ Reglas de ejecución (CRÍTICO)

1. **SIEMPRE `background=true` + `notify_on_complete=true`.** El broker mata
   `llama-server` (el LLM de Hermes) durante el swap; el turno actual puede
   morir y reanudar cuando el broker restaura llama-server. El proceso de
   generación sigue vivo en background y entrega el resultado al terminar.
2. **Avisar al usuario** antes de lanzar: "va a cortar la conexión unos minutos
   (swap de GPU)".
3. **`--filename` único por batch** — con `--count N` el segundo batch con el
   mismo nombre pisa al primero.
4. Verificar el output en WSL: `/mnt/c/ComfyUI/output/audio/` (el log del
   script imprime `SOURCE_FILENAME:` con el nombre exacto).
5. Duración máxima 360s (límite duro del modelo). El modelo puede terminar la
   canción ANTES de `--duration` (el node de text-encode decide los segundos).

## Guía de Prompting

### Caption (estructura de 3 secciones)

El caption NO son tags sueltos: es una descripción estructurada en prosa.
Tres secciones, en este orden:

**1. Global Metadata** — género, BPM, tonalidad, escala, progresión emocional,
escenario de escucha, perfil de producción:
```
Global Metadata: Upbeat Latin pop, 108 BPM, A major, major scale.
Energetic and joyful, starts bright and confident, builds to a big singalong
chorus. Late-night dance party, summer rooftop listening scenario. Polished
modern production: crisp drums, punchy low end, bright sparkling top end.
```

**2. Vocal Details** — género vocal, timbre, delivery, técnicas, armonías,
efectos. (Para instrumental: "No vocals" o sección ausente + `--instrumental`.)
```
Vocal Details: Male lead vocal, warm mid-range timbre, confident and playful
delivery, slight rhythmic bounce behind the beat. Light double-tracked harmony
in the chorus, occasional oh-oh backing vocals.
```

**3. Arrangement** — instrumentos primarios/secundarios, groove, bajo,
percusión, texturas, efectos espaciales. Describir el DESARROLLO por secciones
(intro → verse → chorus → bridge → outro):
```
Arrangement: Punchy four-on-the-floor kick with claps on 2 and 4, tight sub
bass locked to the kick, bright synth stabs, plucky guitar figure. Intro:
guitar riff and handclaps, drums enter at first verse. Chorus: full
arrangement with layered harmonies and synth lead. Instrumental break: guitar
and synth solo over the beat. Outro: strips down to drums and claps.
```

**Reglas del caption:**
- Cuanto más específico, más cerca el resultado. El modelo sigue la evolución
  musical en el tiempo, no solo el estilo global.
- 10-30 líneas de prosa bien escrita > una lista de tags.
- Los tags de estructura NO van aquí: van en las lyrics.
- 26 ejemplos oficiales con captions completos: https://minimax-ai.github.io/music3-demo/
- MiniMax publica un skill `music-caption-rewriter` que convierte una
  descripción breve en caption estructurado:
  `npx skills add MiniMax-AI/MiniMax-Music3 --skill music-caption-rewriter`

### Lyrics (tags de sección)

Los tags son las ÚNICAS instrucciones estructurales ejecutables; el texto de la
letra solo transmite mood. Tags disponibles:
`[Intro] [Verse] [Pre-Chorus] [Chorus] [Post-Chorus] [Bridge] [Instrumental] [Solo] [Outro]`

```
[Verse]
Sube la música, no pares ya
La noche es nuestra, brilla la luna

[Chorus]
Dale, dale, no te detengas
Que esta noche el ritmo manda

[Instrumental]

[Outro]
Oh-oh, oh-oh...
```

- Vocales: el idioma se infiere de la letra (no hay flag `--language`).
- Vocalizaciones no léxicas (`Ah-ah-ah`, `Ooh`) funcionan bien.
- `--instrumental` o lyrics vacíos → `[Instrumental]`.

### BPM / tonalidad

MiniMax Music 3 no tiene flags `--bpm`/`--key` como ACE Step: se declaran en
el caption ("108 BPM, A major"). Si son críticas, escribirlo explícitamente en
Global Metadata.

## Comparativa rápida con ACE Step 1.5 XL

| | MiniMax Music 3 | ACE Step 1.5 XL |
|---|---|---|
| Vocales | Muy realistas (timbre, falsete, efectos) | Buenas, menos control |
| Mezcla | Más abierta y limpia | Bien, algo más densa |
| Control | Caption prosaico (BPM/key en texto) | Tags + flags --bpm/--key/--language |
| Duración máx | 360s | ~300s |
| Edición (denoise parcial) | No | Sí (--edit) |
| Reference audio (img2img) | No | Sí (--reference-audio) |
| LoRA | No | Sí |
| Velocidad | Lento (~1-2 min/canción en 5090) | Rápido (~6s con turbo) |
| Licencia | Community (excluye UE) | Apache 2.0 |

## Verificación post-generación

1. El script imprime `Song saved: <path>` y `SOURCE_FILENAME: ...`
2. Comprobar duración con `ffprobe` (puede ser menor a `--duration`)
3. Para proyectos con plan maestro (p.ej. Sonda Europa): verificar el contenido
   vocal real con Whisper si la letra importa (patrón biblia-cocobot).

## Pitfalls

- **`SaveAudioAdvanced` usa un input `format` tipo DynamicCombo**: en formato API NO funciona enviarlo como dict `{"format": "mp3", "quality": "V0"}` (el parser lo descarta en silencio → error 500 al ejecutar el nodo, aunque todo el pipeline de generación sí haya completado). La forma correcta son **claves aplanadas con punto**, como las manda el frontend: `"format": "mp3"` + `"format.quality": "V0"`. Para `flac` solo `"format": "flac"` (no tiene sub-opción). `build_nested_inputs` (comfy_api) es el que re-ensambla el dict para `execute`.

- **Criterio de elección vs ACE Step 1.5 XL (consenso comunidad, ago 2026):** para calidad de
  audio general (y sobre todo rock/electrónica/géneros pesados), ACE 1.5 XL gana — "still the best
  music generator out there, free and extremely fast, runs locally". MM3 destaca en (a) coherencia
  estructural de larga duración (hasta 5 min) y (b) fidelidad exacta de letra/vocal. Limitaciones
  MM3: audio nativo 32 kHz (vs 48 kHz ACE), cierre de duración a criterio del modelo (pide 270s y
  entrega 232s), y caption mejor procesado con su prompt-enhancer oficial. A/B real (Tierra Rota,
  14 ago 2026): el usuario prefirió claramente la ACE. Usar MM3 solo si se necesitan sus puntos (a)/(b).
- **`--tiled-decode` es OBLIGATORIO para canciones > ~120s** (evidencia real, 14 ago 2026): a 90s el decode normal cabe en la 5090 (32GB), pero a 270s el VAE decode (fp32, `dav.py`) **explota la VRAM dedicada (31.5/31.5 GB) y Windows vierte ~19 GB a memoria compartida (RAM del sistema) → el equipo hace swap/thrashing y ComfyUI muere (exit 3) durante el decode**. Síntoma visible: "Memoria de GPU compartida" llena en el Administrador de tareas y RAM del sistema disparada. Usar `--tiled-decode` (tile 1536/overlap 64) para cualquier `--duration` por encima de ~120s.
- **Si el broker devuelve "ComfyUI exited during startup"**: revisar
  `E:/Workspace/Hermes/comfyui-process.log` (log de stdout de ComfyUI).
- **Modelo no encontrado**: el broker busca en `C:\ComfyUI\models` (symlink a
  `F:\ComfyUIModels`); comprobar que el filename exacto coincide con
  `QUALITY_MODELS` del script.
- **No existe modo edición ni reference audio** en Music 3: para editar
  secciones de una canción, usar ACE Step o regenerar completa.
