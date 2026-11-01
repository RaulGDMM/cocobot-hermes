# PLAN — Local AI Studio (web + espejo de skills)

Documento vivo por hitos. Inicio: 2026-11-01. Dueño: Raúl. Ejecutora: Cocobot.

## Objetivo
Web pública que sirva **a humanos y a agentes** para montar en casa un stack local completo de IA de media
(ordenador potente, ideal 24-32 GB VRAM; guías por tier): música, texto→imagen, imagen→imagen/edición,
escalado de imagen y vídeo (DLSS + upscale BFL con la lección σ identidad>textura), texto→vídeo,
imagen→vídeo, referencias→vídeo, clonación de voz/TTS, transcripción, animaciones por código→MP4
(code-video) y LLMs locales. Todo lo que nosotros ya tenemos probado, con **números medidos** (VRAM,
tiempos, calidad A/B) — ese es el diferenciador frente a blogs genéricos.

## Decisiones (Raúl, 2026-11-01)
- **Hosting:** sección en `cocobot-pages` (`pages/local-ai-studio/`).
- **Idiomas:** ES + EN desde el día 1.
- **Alcance:** stack completo media **+ LLM local**.
- **Broker:** se publica como **patrón genérico** (pasarela GPU con cola única que serializa peticiones)
  + nuestro `scripts/comfyui-broker.py` como referencia implementable.
- **Escaparate:** vídeos incrustados de Gatos Rebeldas — `youtube.com/watch?v=-xjZmepNbU4`
  (Perros vs Gatos, concierto 100% IA local 4K60) y `youtube.com/watch?v=xaDnAqtJVM8`
  (Sonda Europa, cortometraje sci-fi IA local). Embeber, no subir MPs pesados a Pages.
- **Doble faz humano/agente:** la web HTML se genera de un `catalog.json`; la misma web expone
  `/catalog.json` y `llms.txt` para que un agente (p.ej. Hermes con modelo local) lea las capacidades,
  ofrezca montarlas al usuario e instale ComfyUI él mismo (git clone/portable + Manager + nodos +
  descargas `hf` + health-check `/system_stats`).

## Fases
### P0 — Espejo de skills a cocobot-hermes ✅ (2026-11-01, pendiente de OK de commit)
28 skills de media/LLM espejadas con scrub automático: IPs tailnet/LAN → placeholders, `Z:\` →
`<MEDIA_DRIVE>`, registros NSFW personales eliminados de los .md (el código que soporta variantes
uncensored se mantiene: es una función legítima), `.gitignore` raíz ampliado con `*.mp3/*.wav`
(excepto assets de voz), exclusiones de `output/`, `capitulo1/`, `__pycache__`, `.bak`.
Verificado: sin marcadores personales y todos los .py espejados compilan.
Pendientes de decisión de Raúl: `cocobot-voice-ref.wav` (ya público en el repo) y autoría/licencia de
`hyperframes*`/`media-use` (copiadas de `~/.claude/skills`, sin LICENSE visible).

### P1 — Catálogo como dato único ✅ (2026-11-01)
38 entradas × 3 secciones (`catalog-parts/{image,video,audio-llm}[-en].json`), extraídas de las skills por fan-out y traducidas EN. Campos nulos = «sin medición» (nunca inventado).

### P2 — Web ✅ DESPLEGADA (2026-11-01)
`cocobot-pages/pages/local-ai-studio/` → https://raulgdmm.github.io/cocobot-pages/pages/local-ai-studio/ (ES) y `index-en.html` (EN). `build_site.py` regenera ES/EN desde catalog-parts (fuente única). QA: verificación estructural + móvil 390 sin desborde + escaparate YouTube embebido. Tarjeta añadida al índice.

### ~~P1 borrador original~~ (contenido arriba)
Esquema por capacidad: `{id, name_es/en, models:[{nombre, rol(recomendado/alternativa), vram_gb,
disco_gb, tiempo_medido, licencias, cuando_no_usarlo, workflow_ref, verified_date}]}`.
Semilla desde skills `comfyui-local`, `ai-video-studio`, `dlss-comfyui-video`, `video-4k-upscale`,
`video-fps-interpolation`, `code-video`, `minimax-music3`, `llama-cpp`, `local-llm-ops`.
Vive en el repo cocobot-pages; la web lo consume y `/catalog.json` se sirve tal cual.

### P2 — Web en `cocobot-pages/pages/local-ai-studio/` (ES+EN)
- Home: escaparate (los 2 vídeos + galería) + qué puedes hacer + tiers de hardware 12/16/24/32 GB.
- Guía de instalación: Windows (portable) y Linux (git+venv), ComfyUI-Manager, nodos necesarios,
  descarga de modelos (fuentes oficiales, tamaños), requisitos NVMe/RAM/drivers.
- Catálogo por capacidad + recetas paso a paso: t2i, i2i/edición multi-ref + RGBA, upscale/refine
  (lección σ: identidad > textura; QA recortando todas las caras), t2v, i2v, referencias→vídeo
  (patrón personaje-consistente), música, TTS/clon de voz, transcripción, DLSS/upscale/interpolación
  de vídeo, code→vídeo, LLM local (llama.cpp/Strata, perfiles, servidores).
- Errores comunes (pitfalls verificados: parche SageAttention >5 s, encoder equivocado Qwen, etc.).
- Sección "Para agentes": contrato de health-checks, comandos exactos, `/llms.txt`, `/catalog.json`.

### P3 — Superficie agente
`llms.txt` + `catalog.json` servidos + skill Hermes instalable `local-media-studio` (la web es la
cara; la skill son las manos).

### P4 — Mantenimiento y difusión
Sello "verificado <fecha>" por entrada + cron mensual de revalidación del catálogo. Difusión
(r/LocalLLaMA, foros) cuando el P2 esté completo.

## Legal y seguridad (aplica a todo lo publicado)
- Clonación de voz: solo voz propia o con consentimiento explícito; etiquetar contenido generado por
  IA (trasparencia, AI Act UE).
- Licencias por modelo en cada entrada: Qwen-Image 2.1/Ideogram 4 = research no comercial; MOSS =
  Apache-2.0 comercial-OK; FLUX: según variante. Descargas solo a fuentes oficiales (mirrors como
  nota, nunca como enlace primario).
- Auditoría scrub obligatoria antes de publicar o commitear (IPs, hostnames, rutas, tokens,
  identidades personales). `cocobot-hermes` es PÚBLICO: sin registros personales NSFW ni datos
  internos de Inditex/Jira (bajo ningún concepto).
- Números de rendimiento siempre medidos, nunca teóricos; si no hay medición, se dice.

## Capas del stack a documentar (mínimo del catálogo)
1. **t2i**: Qwen-Image 2.1 (default A/B), MOSS-Image (piel/fotorrealismo, Apache), FLUX 3 Klein
   (velocidad 6-8 s/1MP + edición), Z-Image-Turbo (velocidad/texto).
2. **i2i/edición**: Qwen 2.1 multi-ref (16 refs, RGBA nativo), FLUX Klein (anatomía fina).
3. **Upscale/refine imagen**: upscale BFL (--upsample); lección σ identidad>textura.
4. **t2v/i2v**: LTX 2.3/2.5, MiniMax H3 (PDD 8-step 2.23× default; refine 9.4 s 2K ~15 min; sin
   parche SageAttention), MOSS.
5. **Referencias→vídeo**: flujo multi-ref → vídeo con personaje consistente.
6. **Música**: MiniMax Music 3 vía broker (narración + canciones).
7. **Voz**: clon TTS + whisper (bridges del repo) + ética.
8. **Post-vídeo**: DLSS pipeline HDR10 (repo `dlss-pipeline/`), upscale 4K Lanczos, interpolación
   60fps AMT-L.
9. **Code→vídeo**: skill `code-video` v1 (canvas/JS → MP4 verificado).
10. **LLM local**: llama.cpp + Strata (NVFP4 ~95 t/s en 5090; Qwen 27B Q6 en Pi 5 100k ctx),
    servidor + perfiles + multimodal sin mmproj.
11. **Patrón broker/pasarela**: cola única GPU, pausa de agente, health-checks.

## Riesgos
- Obsolescencia (panorama cambia cada mes): fechas de verificación + cron P4.
- Límites GitHub Pages (1 GB, banda): embeber YouTube + previews comprimidos, nunca vídeos fuente.
- `hyperframes*`/`media-use` sin LICENSE en origen → confirmar/redirigir a repo oficial si procede.
