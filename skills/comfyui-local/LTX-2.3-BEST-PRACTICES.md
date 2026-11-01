# LTX 2.3 Video Generation - Best Practices

## 📋 **Estructura de Prompts Recomendada**

### Formato ideal (en orden):
1. **Acción principal** en una sola oración
2. **Detalles específicos** sobre movimientos y gestos
3. **Descripción precisa** de apariciones de personajes/objetos
4. **Detalles del fondo** y ambiente
5. **Ángulos y movimientos de cámara**
6. **Iluminación y colores**
7. **Cambios o eventos repentinos**

### Longitud óptima:
- **~200 palabras** (recomendado)
- Puede ser más corto para validar ideas de movimiento
- No todo lo que escribas ocurrirá en el video

---

## 🎬 **Para Image-to-Video (I2V)**

### Enfoque recomendado:
1. **Usar LLM multimodal** para describir la imagen de entrada
2. **Trabajar con esa descripción**, adaptándola para video
3. **Especificar qué debe cambiar** desde el frame inicial

### Ejemplo de estructura:
```
[Descripción de la escena estática desde la imagen]
+
[Qué movimiento debe ocurrir]
+
[Cómo debe verse el resultado final]
```

### DO (correcto):
> "A detailed and vivid tranquil village scene under the soft glow of a full moon. In the heart of the village, there is a charming cobblestone path leading to a quaint cottage. Standing in front of the cottage is a woman with vibrant red hair, her face illuminated by the moonlight, revealing a warm and genuine smile."

### DON'T (incorrecto):
> "a village, woman, ((smiling)), red hair, (moon:2)"

---

## 🔊 **DIÁLOGO Y VOZ - FORMATO CONFIRMADO**

### ✅ **Formato que SÍ funciona (verificado en video 2):**

**Estructura correcta:**
```
he is yelling 'texto del diálogo' con características
```

**Ejemplo que funcionó (Video 2 - padre-video2.mp4):**
```
he is yelling 'desgraciado me ha empujado' with terror on his face
```

### ⚠️ **Formatos que NO usar:**
- ❌ Comillas dobles: `"TEXTO"`
- ❌ Formato narrativo complejo: `"TEXTO" he screams at the top of his lungs`
- ❌ Sobrecargar con adjetivos

### ✅ **Reglas para diálogo:**
1. Usar **comillas simples**: `'texto'`
2. Verbo simple: `he is yelling`, `he says`, `she screams`
3. Mantener simple: `'desgraciado me ha empujado' with terror on his face`
4. **NO complicar** con formatos narrativos complejos

### Características vocales a incluir (simples):
- `with terror on his face`
- `yelling desperately`
- `shouting loudly`
- `screaming`

**NO usar:**
- ❌ `at the top of his lungs`
- ❌ `mouth wide open yelling desperately`
- ❌ Formatos tipo guion de película

---

## ⚙️ **Parámetros Recomendados**

### Resolución:
- **Recomendada**: 720x1280 o inferior (divisible por 32)
- **Inicio**: 512x768
- **Lower resolutions** = más movimiento dinámico
- **Higher resolutions** = menos movimiento (más estático)

### Duración:
- **Máximo sugerido**: 257 frames
- **Recomendado**: 4-7 segundos (96-168 frames)
- Videos más largos = más riesgo de artefactos

### Steps:
- **Image-to-Video**: 15-20 steps suficiente
- **Text-to-Video**: Puede necesitar más

---

## ❌ **Mitos Comunes (y la verdad)**

### Mitos a evitar:
1. **"Puedo promptear como en 2022"** → Necesitas prompts detallados
2. **"Movimientos de cámara confiables"** → No reconoce bien zoom, pan, tilt
3. **"Resolución más alta = mejor"** → Más resolución = menos movimiento
4. **"Puedo hacer videos largos"** → Máximo 257 frames, mejor 96-168

### ✅ **Verdades confirmadas:**
1. **"LTX 2.3 genera diálogo inteligible"** → SÍ, con formato simple: `he is yelling 'texto'`
2. **"Formato simple funciona mejor"** → NO complicar con narrativas complejas
3. **"Comillas simples, no dobles"** → `'texto'` no `"texto"`

### Limitaciones conocidas:
- **Personas realistas**: Solo bien en primeros planos
- **Movimiento complejo**: "Un infierno se desata" si hay mucho movimiento
- **Movimientos de cámara**: No fiables

---

## 🔧 **Troubleshooting Común**

### "Motionless Movie" (video sin movimiento):
- **Causa**: Resolución muy alta, steps insuficientes
- **Solución**: Bajar resolución, aumentar steps, simplificar prompt

### "Slithering Spectre" (deformaciones):
- **Causa**: Prompts con elementos conflictivos (viento, rayos, fuego)
- **Solución**: Eliminar elementos problemáticos del prompt

### "Switching Slideshow" (cortes bruscos):
- **Causa**: Prompt demasiado complejo o contradictorio
- **Solución**: Un solo "motion beat" por prompt

### "Diálogo no inteligible":
- **Causa**: Usar comillas dobles o formato narrativo complejo
- **Solución**: Usar `he is yelling 'texto'` con comillas simples
- **Ejemplo que funcionó**: `he is yelling 'desgraciado me ha empujado' with terror on his face`

### "Pretentious Prompt" (prompt demasiado elaborado):
- **Causa**: Demasiados detalles no relacionados con la escena
- **Solución**: Mantener relevante a la imagen de entrada

---

## 🎯 **Tips Específicos para LTX 2.3**

### Para mejor movimiento:
1. **Especificar velocidad**: "rapidly", "slowly", "in slow motion"
2. **Dirección clara**: "falling down", "moving left", "rising up"
3. **Intensidad**: "dramatic", "subtle", "intense"
4. **Efectos ambientales**: "wind blowing", "clouds passing", "leaves rustling"

### Para preservar elementos:
1. **Mencionar explícitamente**: "maintaining original [feature]"
2. **Especificar qué NO cambiar**: "keeping the same hairstyle"
3. **Usar "preserve"**: "preserving original facial features"

### Para audio (generación automática):
- El audio se genera automáticamente
- Puede incluir efectos de sonido, música ambiente
- **SÍ genera diálogo inteligible** con formato simple

---

## 📝 **Ejemplos de Prompts Completos**

### ✅ Ejemplo que funcionó (Video 2):
```
A man falling rapidly through the sky screaming in terror and shock, 
he is yelling 'desgraciado me ha empujado' with terror on his face, 
wind blowing his hair dramatically, fast motion blur, dynamic action shot, 
clouds rushing past, intense falling motion, cinematic action scene
```

### ✅ Ejemplo simple de diálogo:
```
A woman in a coffee shop, she says 'have you been waiting long?' 
with a warm smile, steam rising from her coffee cup
```

### ✅ Ejemplo de grito:
```
A person falling from a building, he is screaming 'help me!' 
in desperation, clothes fluttering in the wind
```

---

## 🚀 **Workflow Recomendado**

1. **Confirmar con el usuario** antes de generar (¡IMPORTANTE!)
2. **Mostrar prompt exacto** que se va a enviar
3. **Indicar tiempo estimado** de generación
4. **Análisis de imagen** (si es I2V): Usar LLM multimodal para describir
5. **Prompt base**: Definir acción principal en 1 oración
6. **Agregar detalles**: Movimiento, ambiente, cámara
7. **Incluir diálogo** (si aplica): Usar `he is yelling 'texto'` simple
8. **Especificar preservación**: Qué debe mantenerse igual
9. **Prueba corta**: 4-5 segundos para validar
10. **Ajustar**: Si hay problemas, simplificar o especificar más

---

## 🎙️ **Negative Prompt Recomendado**

**Default (ya incluido en el script):**
```
blurry, low quality, still frame, frames, watermark, 
overlay, titles, has blurbox, has subtitles
```

**Para preservar características faciales:**
```
long hair, growing hair, hair transformation, hair morphing, 
hair style change, face distortion, facial deformation
```

**Uso:**
- **Normal**: `--negative-prompt "motion blur, distorted"`
  - Se **aprende** al default
- **Override completo**: `--negative-prompt "!solo-tu-texto"`
  - **Reemplaza** el default

---

## ⚠️ **NOTA IMPORTANTE - LECCIONES APRENDIDAS**

### **ANTES DE GENERAR VIDEO (SIEMPRE):**
1. ✅ **Confirmar con el usuario** qué se va a generar
2. ✅ **Mostrar prompt exacto** que se enviará al broker
3. ✅ **Indicar tiempo estimado** de generación (ej: "Tardará unos 3-5 minutos")
4. ✅ **Esperar aprobación** antes de ejecutar
5. ❌ **NO generar por cuenta propia** sin confirmar
6. ❌ **NO asumir que la confirmación anterior aplica** a futuras generaciones

### **FORMATO DE DIÁLOGO CONFIRMADO:**
- ✅ `he is yelling 'desgraciado me ha empujado' with terror on his face`
- ❌ `"DESGRACIADO..." he screams at the top of his lungs`

**Video de referencia que funcionó:** `padre-video2.mp4` (Seed: 1301718174)

### **TIEMPOS ESTIMADOS DE GENERACIÓN:**
- **Video 20s @ 720p**: 3-8 minutos (dependiendo del broker)
- **Video 10s @ 720p**: 2-4 minutos
- **Video 5s @ 720p**: 1-3 minutos
- **Siempre indicar**: "Tardará unos X minutos..." antes de generar

---

*Última actualización: 2026-03-08*
*Fuente: sandner.art, Reddit r/StableDiffusion, LTX-2.run, dev.to, documentación oficial LTX-Video, tests confirmados con Raúl*

## 🔗 **Referencias**
- https://dev.to/gary_yan_86eb77d35e0070f5/ltx-2-prompting-guide-master-ai-video-generation-with-expert-techniques-2ejk
- https://ltx-2.run/blog/ltx-2-prompting-guide/
- https://ltx.studio/blog/how-to-generate-video-from-audio-in-ltx
- https://www.reddit.com/r/StableDiffusion/comments/1rlz6l8/i_benchmarked_ltx_2_3/

## 📌 **LECCIONES APRENDIDAS (2026-03-08)**
1. **Confirmar siempre antes de generar videos** (son costosos en tiempo)
2. **Indicar tiempo estimado** ANTES de generar (ej: "Tardará unos 3-5 minutos")
3. **Formato de diálogo simple funciona mejor**: `he is yelling 'texto'`
4. **No usar comillas dobles ni formatos narrativos complejos**
5. **Video 2 (padre-video2.mp4) es la referencia** de lo que funciona
6. **Siempre comunicar qué se va a hacer**, aunque el usuario haya confirmado antes