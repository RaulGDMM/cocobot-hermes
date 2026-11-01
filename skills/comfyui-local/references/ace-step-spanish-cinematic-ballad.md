# ACE Step 1.5 — Spanish Cinematic Ballad Example

Session: 2026-07-18, user request for song inspired by "Just Look My Way" (Helluva Boss) — mystical, broken love, male vocals, ~4 min.

## Complete working example

**Tags:**
```
cinematic ballad, dark orchestral, mystical, passionate, melancholic, grand piano, cello, orchestral strings, atmospheric percussion, dramatic brass, male vocals, wide stereo, hi-fi, 70 bpm
```

**Parameters:**
```
--duration 240 --bpm 70 --key "D minor" --quality xl-turbo --language es --count 3
```

**Lyrics** (all lines 4-8 syllables):
```
[es]

[intro]

[verse]
Guardián de la noche
sin ti no tengo estrellas
la luna me abandona
y el cielo se apaga

[verse]
Un pacto de sombras
un beso de fuego
tu nombre en las nubes
tu ausencia en mi pecho

[pre-chorus]
¿No sentiste el cielo
temblar al besarte?
¿O prefieres la oscuridad
de un mundo sin luna?

[chorus]
Mira las estrellas
donde brilla lo que fuimos
no me importa el silencio
si tu luz llega aquí
Mira las estrellas
donde aún vivo por ti
sin ti soy la noche
sin estrellas

[verse]
Levanto la mirada
busco tu reflejo
cada estrella cae
como una lágrima

[pre-chorus]
¿No sentiste el cielo
temblar al besarte?
¿O prefieres la oscuridad
de un mundo sin luna?

[chorus]
Mira las estrellas
donde brilla lo que fuimos
no me importa el silencio
si tu luz llega aquí
Mira las estrellas
donde aún vivo por ti
sin ti soy la noche
sin estrellas

[bridge]
Soy guardián de la noche
sin ti sin estrellas
la luna se desvanece
el cielo se rompe
¿Cómo el mismo firmamento
que nos vio nacer
nos puede separar?

[inst]

[chorus]
¡Mira las estrellas!
¡Donde brilla lo que fuimos!
¡No me importa el silencio!
¡Si tu luz llega aquí!
¡Mira las estrellas!
¡Donde aún vivo por ti!
¡Sin ti soy la noche!
¡Sin estrellas!

[outro]
No me dejes...
sin ti no tengo estrellas...
sigo aquí...
```

## Duration estimation formula

For ~70 bpm ballad with short lines (4-8 syllables):

| Section | Lines | Time per line | Total |
|---------|-------|---------------|-------|
| [intro] | instrumental | — | 15-20s |
| [verse] | 4 | ~3s | ~12s |
| [pre-chorus] | 4 | ~2.5s | ~10s |
| [chorus] | 8 | ~2.5s | ~20s |
| [bridge] | 7 | ~2s | ~15s |
| [inst] | instrumental | — | 20-25s |
| [outro] | 3 | ~4s | ~12s |

Minimum structural time: ~178-183s. Add 20-30% for transitions and musical breathing room.
**Rule of thumb: structural minimum × 1.25 = target duration.**

For this song: 180s × 1.25 ≈ 225s. User chose 240s for extra expansiveness.

## Key lessons

1. **Count syllables BEFORE presenting lyrics** — don't write long lines and trim later. The 4-8 syllable range is the sweet spot; 10 is the hard ceiling where vocal timing starts fracturing.
2. **"Similar to X song" requests**: Extract the emotional core and musical style from the reference, translate to ACE Step tags (keywords only, no natural language). Don't copy the genre — capture the feeling.
3. **ALL CAPS in final chorus** = more intense delivery from the model. Use this for the climactic moment.
4. **Spanish lyrics require `[es]` marker** at the very start, before any section markers. Without it, the model sings Spanish words with English phonetics.
5. **`--quality xl-turbo` is mandatory for songs over ~200s** — the 3.5B model loses coherence past 3 minutes.
