---
name: llama-cpp-video-input
description: Understand video via local llama.cpp server (input_video).
version: 1.0.0
author: cocobot
license: MIT
metadata:
  hermes:
    tags: [llama.cpp, video, vision, local-llm, mtmd]
    related_skills: [llama-cpp, h3-cinematic-video]
---

# Llama.cpp video nativo (input_video)

## When to Use

- El usuario pide que **mire/analice un video** con el modelo local (no con visión externa).
- Necesitas que el LLM entienda **movimiento/temporal** (lo que no da una imagen).
- **QA de clips generados con H3/LTX** (ver skill `h3-cinematic-video`): los clips
  cortos (5-10 s) caben en una sola petición (~3-5K tokens de video, ~15 s de
  respuesta). Flujo: generar → analizar → ajustar prompt/refs → regenerar.
  Útil para detectar deriva de rostro, incoherencia de movimiento o timing de
  actuación (cruzar con transcripción Whisper del audio).
- Diagnóstico: ¿el video llega al server? (verificar prompt_tokens).

## Contexto

El server local llama.cpp (Windows, modelo Qwen VL con mtmd) puede decodificar y
comprender video de verdad. Verificado 2026-08-20: clip 4.5 s → 10.8K prompt tokens,
12 s de respuesta.

## Prerrequisitos
- Server activo en **172.23.176.1:30000** (IP del host Windows visto desde WSL;
  `localhost` NO llega desde WSL).
- Modelo con soporte VL + build con MTMD_VIDEO (build b10538 o superior de BtbN).
- **Wrapper de video desplegado** en `E:\Workspace\Openclaw\llama-cpp\`:
  `ffmpeg.exe`/`ffprobe.exe` = wrapper C (anti-deadlock bug #24429),
  `ffmpeg_real.exe`/`ffprobe_real.exe` = binarios BtbN.
  - Si tras una actualización del server el video vuelve a dar 0 frames:
    restaurar los 4 exe del backup `E:\Workspace\Openclaw\llama-cpp-backup-<fecha>\`
    (el script `actualizar-llama-cpp.bat` ya lo hace automáticamente desde 2026-08-20).
  - Fuente del wrapper: `E:\Workspace\Openclaw\temp\video_test\wrapper.c`,
    build: `x86_64-w64-mingw32-gcc -O2 -static -Wall -o mtmd_wrapper.exe wrapper.c` (WSL).

## Cómo llamarlo (desde WSL)

```python
import base64, json, urllib.request

data = base64.b64encode(open("clip.mp4","rb").read()).decode()
payload = {
    "model": "local",
    "messages": [{"role":"user","content":[
        {"type":"text","text":"Describe este video con detalle."},
        {"type":"input_video","input_video":{"data": data}}
    ]}],
    "max_tokens": 4096,
}
req = urllib.request.Request(
    "http://172.23.176.1:30000/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type":"application/json"})
r = json.load(urllib.request.urlopen(req, timeout=300))
```

Claves del formato:
- `input_video.data` = **base64 raw del binario** (NO data-URI, sin prefijo `data:video/mp4;base64,`).
- Sin `image_url`/`video_url`: esos formatos NO los entiende el provider local.
- El server aplica **`fps_target = 4`** fijo (mtmd-helper.cpp, sin flag público):
  N_frames ≈ duración_s × 4. Resolución irrelevante (ViT resizea a ~1120 px):
  4K y 1080p dan los mismos ~617 tokens/frame.

## Coste y límites (medidos 2026-08-20 con sonda_europa.mp4 4K/60fps)

- ~**617 tokens/frame** → 30 s de video ≈ 61.700 prompt tokens ≈ **45 s** de
  respuesta total (prefill 35,9 s a 1.720 tok/s, RTX 5090, b10538).
- **Ctx del server = 140.000 tokens** → tope práctico: **~35-40 s de video por
  petición**. Un video de 4:30 (1.080 frames ≈ 270K tokens) NO cabe de una.
- **Límite de payload**: base64 de 133 MB rompe la conexión (broken pipe).
  Mantener el archivo por debajo de ~100 MB; para 4K largo, re-encodear antes:
  `ffmpeg -ss <inicio> -t 30 -i video.mp4 -vf scale=1920:1080 -r 24 -c:v libx264 -crf 23 -an out.mp4`
- **Videos largos: trocear en chunks de 30 s** (~45 s/chunk) y resumir por acto,
  o pedirle a Raúl qué momentos buscar y localizarlos primero.

## Verificación (SIEMPRE)

1. **`usage.prompt_tokens`**: es la prueba de que se decodificaron frames.
   - Roto (0 frames) ≈ 273 tokens solo texto.
   - Bien ≈ N_frames × ~1024 + tokens de texto (18 frames → ~10-18K).
2. **Tiempo**: un clip de 4 s tarda ~12 s. Si tarda 2 min exactos y devuelve 0 frames
   → deadlock #24429 de vuelta (falta el wrapper) → ver prerrequisitos.
3. Log del server `E:\Workspace\Openclaw\llama-server.log`: debe tener líneas de
   ffprobe/ffmpeg (width/height/nb_frames). 0 líneas + gap de 2 min = bug activo.

## Pitfalls

- **Reasoning se come max_tokens**: con `reasoning_effort` alto, la respuesta puede
  llegar vacía (todo el presupuesto en thinking). Subir `max_tokens` (4096+).
- **BtbN rechaza rutas 8.3 cortas** (`C:\Users\RAL~1\...`): por eso el wrapper pone
  su temp-file junto a sí mismo, no en `%TEMP%`. No "mejorar" esto si lo recompilas.
- **CreateProcessW**: la `lpCommandLine` del wrapper DEBE empezar por el nombre del
  exe real entre comillas, o los argv del hijo se desplazan (ffprobe estricto lo
  detecta; ffmpeg sobrevivía por suerte).
- **Hermes `video_analyze` NO usa esta ruta**: envía `video_url`/frames al auxiliary
  vision, no `input_video`. Para video nativo local, llamar al server con
  execute_code/terminal directamente (este skill).
- Imágenes funcionan igual de bien vía `image_url` en el mismo endpoint (1136 tokens,
  2.8 s verificado) — para "¿qué pasa en esta imagen del video?" no hace falta video.
