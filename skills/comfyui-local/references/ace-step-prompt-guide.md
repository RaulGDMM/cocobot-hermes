# ACE Step 1.5 — Complete Prompting Guide

Source: Official ACE Step 1.5 musician's guide + community best practices (deAPI.ai, Reddit r/LocalLLaMA, Civitai).

## Architecture overview

ACE Step has two "brains":
1. **Songwriter (LM)** — reads your description, fills in gaps (key, tempo, structure), creates a blueprint. Optional — skip for full control.
2. **Studio Engineer (DiT)** — takes the blueprint, starts with noise, shapes into music step-by-step. 8 steps (turbo) or 32-50 steps (SFT/base).

## Tags (caption) — the mixing board

**Formula:**
```
[genre], [mood], [2-3 specific instruments], [vocal type], [production style], [BPM] bpm
```

### Genre is always first
Anchors everything. One primary genre + one modifier max.

Good genre families:
- Orchestral: `cinematic, trailer music, orchestral score, baroque, minimalist`
- Ambient: `dark ambient, drone, new age, generative`
- Electronic: `techno, progressive house, trance, drum and bass`
- Rock: `indie rock, post-rock, shoegaze, dream pop`
- Pop: `synth-pop, city pop, k-pop, j-pop, hyperpop`
- Jazz: `bebop, fusion, smooth jazz, gypsy jazz`
- Acoustic: `indie folk, bluegrass, bossa nova, americana`

### Name instruments, not adjectives
`grand piano, upright bass, brushed drums` > `sophisticated, elegant, refined`

Rare instruments work on XL Turbo: `hammered dulcimer`, `theremin`, `shakuhachi`, `prepared piano`.

### Production tags shape the mix
- Fidelity: `hi-fi`, `lo-fi`, `dusty`, `polished`
- Character: `analog warmth`, `tape saturation`, `vinyl crackle`
- Spatial: `wide stereo`, `intimate`, `cinematic`
- Dynamics: `compressed`, `sidechain pumping`

### BPM — include in BOTH tags AND parameter
| Genre | Typical BPM range |
|-------|-------------------|
| Ballad / acoustic | 60-80 |
| Lo-fi hip-hop | 70-90 |
| Pop | 100-120 |
| House | 120-128 |
| Techno | 128-140 |
| Drum and bass | 170-180 |

Setting BPM in tags AND `--bpm` parameter tightens rhythmic output.

### Tag mistakes that ruin output
1. **Natural language**: `"A beautiful melancholic piano piece about autumn"` → WRONG. Use `piano ballad, melancholic, intimate, Parisian cafe, felt piano, 68 bpm`.
2. **Contradictory tags**: `aggressive, serene` or `lo-fi, hi-fi, polished` forces oscillation.
3. **BPM mismatch**: Tagging `techno` at `70 bpm` confuses the model. Slow and dark = `dark ambient` or `downtempo`, not slow techno.

## Lyrics — the song's architecture

### Section markers (lowercase, square brackets)
| Marker | Purpose |
|--------|---------|
| `[intro]` | Instrumental opening |
| `[verse]` | Verse |
| `[pre-chorus]` | Tension builder before the hook |
| `[chorus]` | The hook — repeat it |
| `[bridge]` | Contrasting section |
| `[inst]` | Instrumental solo or break |
| `[build-up]` | Rising tension (electronic) |
| `[drop]` | Peak energy release (EDM) |
| `[breakdown]` | Strip energy back (EDM) |
| `[outro]` | Ending |

**Marker with no text below = instrumental passage.**

### Language markers
Place at the start of a section, never mid-line:
`[en]`, `[zh]`, `[ru]`, `[es]`, `[ja]`, `[de]`, `[fr]`, `[pt]`, `[it]`, `[ko]`

Top 10 perform best. Others work but may underperform.

### Line length — CRITICAL
- **4-8 syllables per line** flows naturally.
- Over 10 syllables: vocal rhythm fractures — model crams words into beats that can't hold them.
- Repeat the chorus for consistent melody.
- AABB or ABAB rhyme schemes sound more natural than free verse.

### Instrumentals
Two ways:
1. Leave lyrics empty + add `no vocals` or `instrumental` to tags
2. Use only section markers with no text: `[intro]` → `[inst]` → `[outro]`

⚠️ Adding `no vocals` in tags while writing lyric text creates confusion — wordless vocalizations. Pick one approach.

## Quality models comparison

| Model | Steps | Guidance | Min duration | Niche genres | Long-form (200s+) | Vocal clarity |
|-------|-------|----------|-------------|-------------|------------------|---------------|
| Turbo (3.5B) | 8 fixed | 1 fixed | 10s | Sometimes misses | Loses coherence | Adequate |
| XL Turbo (~10B) | 8 fixed | 1 fixed | 10s | Handles well | **Holds together** | Clean |
| Base (3.5B) | 5-100 | 3-20 | 30s | Sometimes misses | Holds together | Cleanest |

**Recommended workflow:**
1. Sketch on Turbo (fast, find arrangement)
2. Refine on XL Turbo (better quality, most tracks done here)
3. Polish on Base with `steps=40-60` (maximum fidelity)

For Base: CFG 5-7 = loose and musical. CFG 10-12 = tracks tags closely. Above 15 = rigid, artifacts.

## Reference audio

All variants accept `--reference-audio` — a 5-60 second clip for style/timbre transfer.

**What works:**
- Dry instrumental fragments: 10-30 seconds, consistent style
- Clean guitar intro, isolated synth pad, drum loop

**What backfires:**
- Vocal-heavy mixes: model clones voice instead of production style
- Dense full mixes: turns to mud (averages all layers)
- Clips under 5 seconds: too little signal

On XL Turbo, even subtle cues transfer: specific reverb decay, tape compression, analog warmth.

## Complete examples

### Orchestral / cinematic (like Ori and the Blind Forest)
```
Tags: cinematic orchestral, ethereal, emotional, haunting, magical, swelling strings, solo piano, atmospheric pads, choir ooh, soft female vocals, wide stereo, hi-fi, 70 bpm

Lyrics:
[es]

[intro]

[verse]
En el silencio
un susurro de luz
entre las sombras
algo despierta

[inst]

[chorus]
Vuela espíritu
hacia el amanecer
donde el mundo
te está esperando

[inst]

[bridge]
Raíces de plata
cielo y corazón
lo que fue perdido
vuelve a nacer

[chorus]
Vuela espíritu
hacia el amanecer
donde el mundo
te está esperando

[outro]
```
Duration: 300s · BPM: 70 · Key: A minor · Quality: xl-turbo

### Dark ambient (long-form)
```
Tags: dark ambient, cinematic, atmospheric, ethereal, haunting, sustained analog drone, granular texture, reverb-heavy piano, field recording wind, distant choir, sub rumble, no vocals, slow evolving, hi-fi, wide stereo, 55 bpm

Lyrics:
[intro]

[inst]

[outro]
```
Duration: 270s · BPM: 55 · Quality: xl-turbo

At 270s, XL Turbo's advantage over 3.5B Turbo becomes audible. The smaller model loses coherence past 3 minutes.

## Common mistakes summary

1. Lines over 10 syllables → vocal timing fractures
2. Stacking 5+ niche genres → output collapses to noise
3. `[chorus]` with no text → generates silence, not a hook
4. Missing language marker `[es]` → sings Spanish with English phonetics
5. BPM only in parameter, not in tags → model guesses, often wrong
6. Natural language in tags → model expects keywords, not sentences
7. Timestamps in section markers → ACE Step does NOT understand `[0:00-0:45]`
