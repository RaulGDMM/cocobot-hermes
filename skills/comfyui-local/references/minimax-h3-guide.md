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
- El regenerador oficial 2K tampoco está abierto; la salida local base es 768p salvo un proceso posterior independiente.

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

## Verificación obligatoria para entregables

1. `ffprobe`: duración, resolución, fps, códecs, frecuencia y canales.
2. Movimiento/coherencia: extraer fotogramas al inicio, centro y final; revisar identidad, anatomía y escenario.
3. Continuaciones: comparar último fotograma anterior contra primero nuevo y revisar una secuencia alrededor de la unión.
4. Diálogo: extraer audio y transcribir con Whisper; comprobar texto y timestamps.
5. Fusionar solo tras aprobar la extensión. Si hay salto, preferir regenerar con mejor ancla antes que esconderlo con un fundido.
6. Si se usa fundido, revisar doble exposición en varios fotogramas, no solo una captura.
