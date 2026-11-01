# ACE Step 1.5 - Best Practices

## 📋 Tags (Estilos)

### Formato
- **Comma-separated** (separados por comas)
- Describen género, instrumentos, mood y escena
- **No incluir BPM, key o metadata en los tags** (el modelo se confunde)

### Ejemplos de tags efectivos
```
electronic, playful, upbeat, male vocals
lo-fi, chill, ambient, piano, rainy mood
pop, female vocals, upbeat, guitar
steampunk, electro swing, jazz, piano, ticking clock
hard rock, electric guitar, power ballad
```

### Reglas para tags
1. **Sé específico**: "hard rock, electric guitar, power ballad" > "rock"
2. **Incluye tipo de vocal**: `male vocals`, `female vocals`, `duet`, `choir` o `no vocals`
3. **Múltiples tags**: Combina para más control (género + instrumentos + mood)
4. **Lenguaje mecánico**: ACE-Step responde mejor a componentes limpios y técnicos, no a lenguaje expresivo
5. **No meta-datos**: NO escribir "120bpm", "C major", etc. en los tags (eso es para parámetros separados)

---

## 📝 Lyrics (Letras)

### Formato de estructura
Usa **markers entre corchetes** para guiar la estructura:

```
[Verse 1]
Ticking tocking goes the clock
Turning keys and pick the lock

[Chorus]
Round and round we go today
In this smoky cabaret

[Verse 2]
Steam is rising, gears go round
Listen to that brassy sound

[Chorus]
Round and round we go today
In this smoky cabaret

[Bridge]
Fix the future, fix the past
Time is moving, make it last

[Chorus]
Round and round we go today
In this smoky cabaret
```

### Reglas para letras
1. **Estructura clara**: `[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]`, `[Intro]`
2. **Frases cortas**: Funcionan mejor que oraciones largas
3. **Repetición**: El modelo prefiere estructuras de canción con coros repetidos
4. **Palabras percusivas**: Generan resultados más estables
5. **Longitud**: Líneas cortas y rítmicas > párrafos largos
6. **Idioma**: Escribe letras en el mismo idioma que `--language`

---

## ⏱️ Duración

- **Recomendado para empezar**: 90-120 segundos (resultados más consistentes)
- **Máximo**: 240 segundos (4 minutos)
- **Duraciones largas** (180s+): Pueden requerir múltiples batches
- **Pruebas**: 30-60 segundos para validar prompts

---

## 🎛️ Parámetros Técnicos

### BPM (Beats Per Minute)
- **Pop/Upbeat**: 120-140 BPM
- **Lo-fi/Chill**: 70-95 BPM
- **Rock**: 100-160 BPM
- **Ambient**: 60-90 BPM

### Key (Tonalidad)
- Formato: `<root> <quality>` (ej. `C major`, `E minor`, `F# minor`)
- **Default**: `C major`
- Todas las raíces estándar soportadas

### Language
- `es` (Spanish - default)
- `en` (English)
- `ja` (Japanese), `zh` (Chinese), `de` (German), `fr` (French), etc.
- Soporta 50+ idiomas

---

## 🎯 Tips Pro

1. **Reference audio**: Usa `--reference-audio` para transferencia de timbre/estilo
2. **Consistencia de seed**: Usa la misma seed para reproducir resultados idénticos
3. **Variaciones**: Genera múltiples versiones del mismo prompt con seeds diferentes
4. **Instrumental**: Deja `--lyrics` vacío para música sin voz
5. **Calidad**: 
   - `--quality xl-turbo` (default): XL 4B decoder + 4B encoder, turbo mode (8 steps, CFG 1.0). Fast, great quality.
   - `--quality xl-merge`: XL SFT+Turbo merge (task arithmetic α=0.5). Same 8 steps as turbo but blended with SFT weights — less artifacts, better structure. Experimental.
   - `--quality high`: 2B base turbo + 4B encoder split. Original model.
   - `--quality standard`: AIO checkpoint con encoder más pequeño (más rápido, menor calidad)
6. **Tags duplicados**: Intenta usar los mismos tags en descripción de canción y caption de música para consistencia

---

## ❌ Errores Comunes

1. **Tags vagos**: "haga algo divertido" → ❌ | "electronic, playful, upbeat" → ✅
2. **Meta-datos en tags**: "120bpm, rock" → ❌ | "rock" + `--bpm 120` → ✅
3. **Letras sin estructura**: Párrafo largo sin markers → ❌ | `[Verse]`, `[Chorus]` claros → ✅
4. **Frases muy largas**: Líneas de 20+ palabras → ❌ | Frases de 5-10 palabras → ✅
5. **Duración excesiva inicial**: 240s de primera → ❌ | Empezar con 90s → ✅

---

## 📚 Referencias

- GitHub oficial: https://github.com/ace-step/ACE-Step-1.5
- Tutorial oficial: https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/Tutorial.md
- WaveSpeed AI API: https://wavespeed.ai/docs/docs-api/wavespeed-ai/ace-step-1.5
- Reddit tips: https://www.reddit.com/r/LocalLLaMA/comments/1r0904z/acestep_15_prompt_tips_how_i_get_more/

---

*Última actualización: 2026-04-12*