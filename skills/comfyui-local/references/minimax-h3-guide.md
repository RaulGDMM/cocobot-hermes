# MiniMax H3 — guía de uso, prompting y referencias

Actualizado: 2026-08-05. Esta referencia resume la documentación oficial y las lecciones verificadas en el entorno local RTX 5090. Si una fuente cambia, prevalecen la documentación de MiniMax y la de ComfyUI.

## Fuentes autoritativas

1. [Modelo y arquitectura oficial de MiniMax H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)
2. [Guía oficial de prompting T2VA/I2VA/FL2VA/L2VA](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md)
3. [Guía oficial de prompting Full-Reference / Ref2VA](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)
4. [API y límites oficiales de generación](https://platform.minimax.io/docs/guides/video-generation)
5. [Tutorial oficial de MiniMax H3 en ComfyUI](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
6. [Workflow oficial Ref2VA de ComfyUI](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json)
7. [Guía práctica de prompting de fal](https://fal.ai/learn/devs/minimax-h3-prompting-guide) — secundaria; útil para ejemplos, pero la documentación oficial manda.

## Capacidades y formatos

- Salida local base: 768p nativo, 24 fps, audio estéreo de 32 kHz generado conjuntamente.
- `720p` en el script corresponde a 1344×768, múltiplos de 32.
- Rango oficial de producción: 4–15 s. ComfyUI ajusta la longitud a la cuadrícula temporal `17k+5`; una petición nominal puede durar unas centésimas más.
- **Sampler por defecto desde 2026-08-31: PDD 8-step** (LoRA oficial Alibaba PAI `MiniMax-H3-{FL2VA,Ref2VA}-Acc-8Step.safetensors` + node pack `ComfyUI-MiniMax-H3-PDD-Acc`). Receta fail-closed: 4/6/8 pasos, euler, CFG 1.0, strength 1.0, sigma shift 12/3 — el nodo rechaza otros conteos. `--no-pdd` = modo clásico 20 pasos `res_multistep`, **solo si Raúl lo pide explícitamente**.
- Español figura entre los 11 idiomas con soporte estable.
- H3-Context-IR oficial no forma parte de los pesos abiertos. Localmente hay que compensarlo con prompts estructurados y explícitos.
- El regenerador oficial 2K (H3-Regenerate-2K) tampoco está abierto (comprobado 2026-09-12: respuesta del org MiniMax en discussion #39 — open-source “cuando esta tecnología se estabilice”, sin fecha; re-comprobado 2026-10-06: discussion #92, el org respondió “Still working on it” ~24/09, sin fecha de release). No es un upscaler: regenera el clip a 2K in-context con el propio H3 + contexto original; hoy solo vía API de platform.minimax.io (flujo híbrido: iterar local 768p → API para el master 2K). Endpoint `/v2/video_regeneration` (task_type=regeneration): el base_video debe ser salida H3 768p válida (24 fps, lados divisibles por 32, área ≤768×1344, 107–362 frames en pasos de 17, pista de audio obligatoria), cuerpo ≤64 MB, y el `text` debe ser el prompt FINAL enviado al modelo (post-Context-IR), no el original. Precio orientativo ~$0.13/s de vídeo 2K (blog comunidad HF, no verificado en la página oficial). Existen latent upscalers comunitarios (LBH-123-AI/Minimax_h3_latent_Upscaler ~700MB + fork xmarre-Plus; Mamad8/H3-Latent-Upscaler-2x; Tr1dae clean-latent 2×) pero Raúl los descarta (2026-09-12): no le interesan mejoras de velocidad/resolución con riesgo de calidad. No proponerlos de nuevo sin cambio de criterio explícito. La salida local base es 768p salvo un proceso posterior independiente.

## Elegir el modo correcto

H3 usa dos checkpoints realmente distintos:

### FL2VA (`minimax_h3_fl2va_*`)

Sirve para:

- Texto a vídeo, sin imágenes.
- Primer fotograma exacto con `--image`.
- Último fotograma exacto con `--end-image`.
- Primer y último fotograma juntos.

Los keyframes se incorporan como anclas temporales reales. Elegir FL2VA cuando la prioridad sea que el fotograma 0 o el fotograma final coincidan con una imagen concreta.

### Ref2VA (`minimax_h3_ref2va_*`)

Sirve para combinar referencias multimodales:

- Hasta 9 imágenes.
- Hasta 3 vídeos, cada uno de 2–15 s y con duración total de vídeo ≤15 s.
- Hasta 3 audios, cada uno de 2–15 s y con duración total de audio ≤15 s. El audio no puede ser la única modalidad de referencia.
- Máximo 12 archivos combinados.

Usar Ref2VA para identidad, estilo, movimiento, cámara, voz, edición o continuación. Las referencias son condicionamiento semántico/temporal, no restricciones píxel a píxel.

No combinar los flags FL2VA (`--image`, `--end-image`) con referencias en el nodo nativo. Una imagen enviada mediante `--reference-image` sigue siendo una referencia Ref2VA aunque el prompt le asigne la función de primer fotograma.

## Etiquetas y asignación de funciones

El orden de los flags determina las etiquetas:

- Imágenes: `<Picture 1>`, `<Picture 2>`, etc.
- Vídeos: `<Video 1>`, `<Video 2>`, etc.
- Audios: `<Audio 1>`, `<Audio 2>`, etc.

Las numeraciones son independientes. Un vídeo con soundtrack puede introducir una etiqueta de audio antes de los audios independientes; leer siempre la asignación que imprime el CLI.

La práctica de mayor impacto es asignar un trabajo explícito a cada entrada:

```text
Use <Picture 1> for the two characters' exact appearance and opening composition.
Use <Video 1> as the continuation source and for identity, movement, camera, environment, and temporal context.
```

No limitarse a describir de nuevo lo que aparece en la referencia. Explicar **para qué se usa** y qué debe conservarse o cambiarse.

## Estructura recomendada de prompts

### T2VA / FL2VA

La guía oficial recomienda:

1. Estilo y composición inicial.
2. Acciones en orden cronológico.
3. Planos y movimientos de cámara.
4. Diálogo y sonidos sincronizados.
5. `overall_soundscape`.
6. `non_diegetic_music`.

Para diálogos, usar un hablante estable `(S1)`, idioma explícito y texto exacto dentro de `<d>`:

```text
The man with a warm baritone voice (S1) looks at him and says, <d>[Spanish] Te quiero.</d>
```

En prompts simples, las comillas funcionan, pero la notación oficial mejora la atribución y la conservación literal del diálogo.

### Ref2VA

Para trabajos complejos o sensibles a continuidad, seguir la estructura oficial:

1. `subject_definitions`: define sujetos y procedencia.
2. `summary`: tipo de tarea y relación entre entradas.
3. `retention_analysis`: `fully_preserved`, `partially_preserved`, `attribute_transfer` o `weak_reference`.
4. `detailed_description`: cronología completa por planos.
5. `overall_soundscape`.
6. `non_diegetic_music`.

Los tipos de tarea relevantes incluyen `reference generation`, `video editing`, `video continuation`, `keyframe completion`, `audio reuse` y `audio reference`. Pueden combinarse.

## Receta recomendada para extender un vídeo

### Opción A: Ref2VA con vídeo solamente

- Usar la cola relevante del clip, no necesariamente los 15 s completos.
- El vídeo aporta identidad, acción, cámara, entorno y estructura temporal.
- Riesgo: el primer fotograma nuevo puede reinterpretarse y producir un salto de pose o encuadre.

### Opción B: Ref2VA con último fotograma + cola del vídeo (recomendada)

- Extraer el último fotograma del clip anterior y pasarlo como `--reference-image` (`<Picture 1>`).
- Pasar los últimos segundos como `--reference-video` (`<Video 1>`).
- Declarar que `<Picture 1>` es el primer fotograma/ancla de composición y que `<Video 1>` es la fuente de continuación.

Ejemplo de intención:

```text
subject_definitions:
<Picture 1> is the exact opening composition and first-frame anchor of [Shot 1].
<Video 1> is the source video from whose final moment the target video continues.
<Subject 1> and <Subject 2> are the two men whose appearance, clothing, relationship, and motion come from <Picture 1> and <Video 1>.

summary:
[video continuation + keyframe completion] The target video begins from <Picture 1> and continues directly from the final moment of <Video 1>.

retention_analysis:
<Picture 1> ([Shot 1] first frame): fully_preserved - preserve pose, framing, lighting, background, clothing, faces, and spatial placement.
<Video 1> (continuation source): fully_preserved - continue the same action, camera, subjects, and environment.
```

Esto está respaldado por la guía oficial Full-Reference, que permite que `<Picture N>` sea un primer fotograma o ancla de composición y que `<Video N>` sea una fuente de continuación. Sin embargo, en Ref2VA la imagen no es un keyframe duro: mejora la continuidad potencial, pero no garantiza igualdad píxel a píxel ni que el primer fotograma conserve la pose o el punto de vista. En una prueba local con el último fotograma como `<Picture 1>` y los últimos 10 s como `<Video 1>`, H3 preservó bien personajes, escenario y acción, pero volvió a empezar desde un encuadre frontal distinto en lugar de reproducir la composición trasera solicitada. Para una unión exacta, usar FL2VA con `--image`; Ref2VA debe considerarse una aproximación semántica incluso con `fully_preserved`.

### Opción C: FL2VA con último fotograma

Usar solo `--image` para bloquear el comienzo. Da la unión visual más exacta, pero pierde el vídeo como contexto temporal y usa el checkpoint FL2VA.

## Rendimiento y memoria

- **PDD Acc 8-step (default desde 2026-08-31):** `MiniMaxH3SigmaShift` (12/3) → `MiniMaxH3PDDAccApply` (nfe 8, lora 1.0, on_off_grid=error) → BasicGuider sobre el modelo parcheado (slot 0) y sigmas entrenados del Apply (slot 1); sampler `euler`. Sin PDD: `BasicScheduler simple` + `res_multistep` 20 pasos. A/B controlado en la 5090 (mismo prompt/seed/refs/Sage ambos lados): 5s FL2VA 480p 1.63× (58.7→35.9 s); **15s Ref2VA 1344×768 3 refs 2.23× (914→410 s)**, sin degradación visible y con diálogo presente. El modo PDD ahorra ~8 min por render de 15 s.
- SageAttention específico de H3 está validado en este entorno y aproximadamente duplicó la velocidad sin degradación visual clara.
- No confundir `ComfyUI-INT8-Fast` de BobJohnson24 con otro checkpoint o modo H3: es un loader W8A8 alternativo para los mismos pesos INT8 ConvRot. Su rama principal de 2026-06-26 es anterior a H3, no ofrece `model_type=minimax` y el soporte de H3 sigue sin validación oficial ([issue #95](https://github.com/BobJohnson24/ComfyUI-INT8-Fast/issues/95)); el truco comunitario de elegir `ltx2` solo es incidental cuando se carga un checkpoint ya cuantizado. Los grandes aumentos publicados frente al loader nativo se asocian principalmente con instalaciones antiguas de CUDA/ComfyUI/comfy-kitchen. En el entorno RTX 5090 validado (CUDA 13, ComfyUI INT8 nativo y comfy-kitchen actual), otros usuarios han observado ganancia nula o incluso regresión. No asumir un 2×: si se evalúa, mantener `UNETLoader` nativo como predeterminado y hacer un A/B mismo prompt/seed con un selector experimental de loader. Como ambos caminos usan el mismo checkpoint `pruned_int8_convrot`, no hay una reducción de precisión adicional intencionada, pero tampoco existe aún un A/B perceptual controlado de H3 que demuestre pérdida cero.
- `ref_image_size=match`: escala las referencias al área de salida y es la opción predeterminada/rápida.
- `ref_image_size=max`: conserva hasta 2048 px de lado corto; puede reforzar detalles de identidad, pero aumenta mucho tokens, RAM y tiempo. Usarlo solo si `match` no conserva identidad suficiente.
- Los tokens de referencia atraviesan todos los pasos. Vídeos largos y varias referencias incrementan mucho el coste.
- Mediciones locales a 1344×768, 362 frames, 20 pasos y SageAttention: I2V sin vídeo de referencia, 13m45s; Ref2VA con 10 s de vídeo, 34m41s; Ref2VA con una imagen + 10 s de vídeo, 35m12s. El coste dominante es codificar/mantener los tokens del vídeo de referencia; añadir una imagen a tamaño `match` apenas sumó 31 s.
- Caso observado por el usuario: con 15 s de vídeo de referencia la VRAM se llenó y ComfyUI empezó a usar memoria compartida/system RAM. Esa ejecución superó el timeout de 1800 s. No interpretar el timeout como fallo del workflow: ComfyUI había aceptado y estaba ejecutando el prompt, pero el spill/swap puede penalizar drásticamente el rendimiento.
- Para Ref2VA pesado, usar `background=true`, `notify_on_complete=true` y `--timeout-seconds 7200` cuando proceda. Evitar 15 s de referencia en una RTX 5090 de 32 GB si una cola de 10 s contiene contexto suficiente.
- El workflow oficial señala que `beta` o `normal` puede rendir mejor que `simple` en prompts muy cargados de referencias. El script actual usa `simple`; no cambiar sin una prueba A/B reproducible.

## Buenas prácticas visuales

- Describir toda la escena, pero mantener una cronología clara y realizable en 15 s.
- Preferir un solo plano cuando la continuidad espacial importe. Añadir cortes solo si aportan información nueva.
- Especificar tipo de movimiento de cámara, amplitud y velocidad cuando sean relevantes: `push in`, `pan`, `tracking shot`, `static shot`, etc.
- Para identidad, enumerar rostro, pelo, ropa, proporciones y rasgos que deben conservarse.
- Para continuidad, enumerar pose, encuadre, iluminación, fondo y relaciones espaciales.
- No asignar funciones contradictorias a dos referencias. Si una controla identidad y otra movimiento, decirlo expresamente.
- Usar la misma semilla al comparar cambios de prompt o parámetros.

## Buenas prácticas de audio y diálogo

- Especificar hablante físico, idioma, acento, timbre, emoción y momento aproximado.
- Mantener el diálogo breve para que termine antes del último fotograma.
- Para español: `[Spanish]` y texto literal dentro de `<d>` siguiendo la guía oficial.
- Distinguir audio diegético, ambiente y música no diegética.
- El audio semántico es el modo habitual: H3 regenera voz/contenido conjuntamente.
- Usar `--preserve-reference-audio` solo si se exige conservar la señal original exacta.
- La sincronía audiovisual es buena, pero no garantiza fonemas perfectos: verificar siempre con Whisper y revisión temporal.

## Mezcla posterior de música y SFX con FFmpeg

- Mantener la música como una pista independiente y completa. No usar `atrim` salvo que el montaje pida explícitamente cortarla.
- Para superponer música y SFX sin que `amix` atenúe todas las entradas, usar `amix=inputs=N:duration=longest:normalize=0`.
- Aplicar `adelay` a cada SFX, seguido de `apad=whole_dur=<duración total>`; rellenar también la música hasta la duración final cuando sea necesario.
- Terminar la mezcla con `atrim=0:<duración total>` para evitar colas sobrantes.
- Ajustar la ganancia por pista antes de `adelay`. No compensar un mal balance elevando toda la mezcla final, porque también altera la música.
- Verificar continuidad y balance con `volumedetect` en ventanas con SFX y en al menos dos ventanas posteriores sin SFX. Comparar estas últimas con la música fuente para confirmar que sigue presente y conserva su nivel.
- Pitfall: `amix=duration=first` puede cortar toda la salida al terminar la primera entrada; `normalize=1` puede bajar inesperadamente la música según el número de pistas.

## VAE int8 de H3 — DEFAULT desde 2026-10-06 (A/B aprobado por Raúl)

ComfyUI 22/09/2026: VAE de vídeo de H3 ~2.2× más rápido codificando y 1.4–2.7× decodificando (round-trip 1344×768/129f: 24.3s → 12.7s en 5090). Fuente: blog.comfy.org/p/making-the-minimax-h3-video-vae-2x

Setup completado 2026-10-06:
- `minimax_h3_video_vae_int8_convrot.safetensors` (2.8GB) en `F:\ComfyUIModels\vae\`.
- `"--fast", "fp16_accumulation"` añadido a los args de ComfyUI en `comfyui-broker.py` (activo desde el reinicio del broker de las 16:28).
- `generate_video.py`: `--h3-vae {fp16,int8}` con **default int8** (también en los defaults de `build_h3_workflow`/`generate_video`). El log muestra `+vae-int8` en los renders normales; es esperable.

**A/B (zorro 8s 720p PDD-8, seed 1234, mismo batch, `~/workspace/ab-h3-vae/`):** PSNR 43 dB / SSIM 0.983 entre clips. Revisión visual a pares (criterio Qwen: nunca solo métricas): fp16 gana de forma sutil pero medible — microdetalle de pelaje, bigotes, nitidez de gotas, y leve banding del int8 en gradientes (reflejos de agua/contraluz). Sin artefactos graves en int8. **Raúl lo revisó directamente en el reproductor y aprobó int8 como default por la velocidad extra** (138.5s→111.0s en el test, algo inflado por orden de carga; ganancia real ~10-15s por clip de 8s). `--h3-vae fp16` queda para masters si algún día se pide máxima calidad.


## H3 Motion Context (encadenado largo sin uniones visibles) — INSTALADO 2026-10-19, VALIDADO

Pack `ComfyUI-H3-Motion-Context` v0.7.1 (NikoDemon80) en `custom_nodes` del install del broker. Requiere ComfyUI ≥0.34 (tenemos 0.41.0). Encadena clips anclando ~1 s del latente (vídeo+audio) del clip anterior: el siguiente continúa movimiento y sonido REAL, no reinterpretación semántica. Resuelve el límite de 15 s y los saltos de unión de la Opción B.

**Receta API validada (spike en `~/workspace/h3-motion-context/spike.py`, referencia del wiring):** sobre el workflow de `build_h3_workflow` insertar: nodo Load 0 para clip 1 (pass-through, NO mutearlo) / clip N lee `h3_context/<tag>/clip_0000{N-1}.safetensors`; `MiniMaxH3MotionContext{conditioning:[5,0], vae:[3,0], latent:[5,1], context_length:"22", audio_context_length:18, context_latent}` → BasicGuider; `MiniMaxH3MotionContextTrim{images:[11,0], audio:[12,0], trim_frames:[51,1], fps:24, match_tail:true}` → CreateVideo; `MiniMaxH3MotionContextSaveLatent{latent:[10,0], filename_prefix:<misma carpeta que Load>/clip, clip_index}`. El prefijo de Save y la ruta de Load DEBEN coincidir (bug tonto que se coló en el primer draft). Los latentes quedan en `C:\ComfyUI\output\h3_context\...` (output real = C:, no E:) → un trabajo de broker por segmento, cero re-subidas. La salida SaveLatent no aparece en `outputs[]` del broker (es `ui.latents`): filtrar `.mp4`.

**Resultados A/B (19/10/2026, 2×124f, 736×416, seed 4242, PDD 8-step + Sage + VAE int8, log `spike.log`):** PDD Acc 8-step es COMPATIBLE con Motion Context (142 s y 132 s/segmento). Unión 9/10 visual (zorro trotando, sin salto de pose/encuadre/grade; el clip 2 obedeció la continuación narrativa). Audio: −0.95 dB paso, sin click, sin colapso de agudos. Duraciones exactas: clip N entrega frames−22 (los anclados se recortan con Trim).

**CADENA EXACT-AUDIO VALIDADA (19/10/2026, prueba PVSG `~/workspace/h3-motion-context/pvsg-test/`):** 2×175f @1344×768, 4 imágenes ref + 1 ventana de canción por segmento, grito sostenido cruzando la unión ("a-vi-ra-le"): boca YA abierta en el frame 0 entregado del seg2, unión sin salto (frame-diff 5.9 vs vecinos 8.8, línea base 2.8), cierre natural de mandíbula al morir la nota, sin cuello jirafa, micro estable. **RECETA DE VENTANA (crítico):** la `--reference-audio` de cada segmento debe cubrir la VENTANA MUESTREADA completa, incluido el pinned head: ventana del seg N = canción[T_N−0.917 .. T_{N+1}] (el offset 0.917 = 22 frames que aporta el clip anterior). Si solo se pasa la ventana entregada, la boca iría ~0.92 s tarde. Coste medido: 264-290 s por segmento de 7.3 s @768p con refs (frente a ~410 s de un 15 s normal): el contexto encadenado no penaliza apenas. El audio final va SIEMPRE remuxado desde la maestra (el co-generado solo importa para el timing de boca).

**PERCEPCIÓN DE UNIONES (Raúl en `cli_smoke`, cadena t2v sin anclas, 19/10/2026 — corrige mi "invisible"):** se nota el corte visual y que "la música se reinicia", aunque las rejillas numéricas salieran limpias. Medido: paso de grado en la unión (luma +2.0/255, U +0.42, V +0.20) y reinicio sonoro (centroid 1613→1491 Hz, RMS +2.5 dB). Causas y mitigaciones: (1) el paso de grado es el síntoma que atacan los nodos experimentales **Join Match** (mejor en plano fijo) y **Refine Blend** del pack 0.7.1; con refs/keyframe anclados (caso PVSG) no apareció. (2) El audio H3 NO atraviesa la unión como pista: el modelo re-toca el ambiente condicionado por ~0.75 s de cola, así que viento/música “renace” ahí — lo primero que caza el oído. Si una cadena va sin pista maestra y el plano es sensible: sustituir el audio (música/narración), crossfade de 12-24 frames en la unión, o aceptar solo para ambiente suave. Política derivada (Raúl): ≤15 s monolito; cadena solo para >15 s, one-takes explícitos o notas que no caben. Driver de referencia: `pvsg_chain.py` (sube refs+ventanas, encadena por output folder, concat + tajada maestra).

**Reglas del pack (README, probadas por el autor):** `context_length 22` + `audio_context_length 18` SIEMPRE (todo lo demás es fijo o peor); duraciones 124/175/226/277/328 frames (alinean rejilla 40 Hz de audio); **regla del airlock**: abrir el clip N+1 con el encuadre exacto del cierre del N, SIN diálogo, ~2 s, con algo que hacer (respirar, peso, mirada — si no, freeze literal), y luego ya el cambio; los prompts describen CONTRADICCIONES como UNIÓN (si el prompt del clip 2 describe otra disposición de gente, salen TODOS); sin `first_frame` con motion context (lo descarta; `last_frame` sí convive); sin upscale entre segmentos (pixel-shift = costuras visibles) — el post-proceso (DLSS/FG) va sobre el master montado, que es lo nuestro; H3 escupe audio 32 kHz (ojo al remuxar); cadenas largas ensordecen el audio (~2-3 clips), irrelevante si la pista final es la maestra; no mezclar Spectrum; resolución fija en toda la cadena. Referencias Ref2VA conviven con el nodo (los bloques ref no se tocan). **MODO OFICIAL DESDE 19/10/2026: `generate_video.py --h3-chain N`** — ver sección de cadenas en SKILL.md (slots, re-ruedo, ventana exact-audio automática; `--dry-run` imprime el plan). El addon Auto-Chain (lip-sync largo con audio troceado por UI) sigue sin instalar: el modo CLI cubre el caso de vídeo musical.

## Verificación obligatoria para entregables

1. `ffprobe`: duración, resolución, fps, códecs, frecuencia y canales.
2. Movimiento/coherencia: extraer fotogramas al inicio, centro y final; revisar identidad, anatomía y escenario.
3. Continuaciones: comparar último fotograma anterior contra primero nuevo y revisar una secuencia alrededor de la unión.
4. Diálogo: extraer audio y transcribir con Whisper; comprobar texto y timestamps.
5. Fusionar solo tras aprobar la extensión. Si hay salto, preferir regenerar con mejor ancla antes que esconderlo con un fundido.
6. Si se usa fundido, revisar doble exposición en varios fotogramas, no solo una captura.
