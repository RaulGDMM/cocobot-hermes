# Music-video & narrative-short pipelines (song-driven)

Two end-to-end pipelines. Shared engine rules are in SKILL.md; this file is the pipeline order, math, and per-engine quirks.

## A) Song-driven music video (ACE Step → images → LTX i2v → ffmpeg)

1. **Song** — `generate_song.py --tags "..." --lyrics "$(cat letra.txt)" --duration 240 --bpm 70 --key "D minor" --quality xl-turbo --language es --count 3`. Quality modes: `xl-turbo` fast/draft (can muddy vocals on dense orchestration); `xl-merge` cleaner on dense choruses. Tags: genre+mood+instrumentation; specify BPM/key/language; **NEVER `epic choir` with dense orchestration** (muddy choruses — use `soaring strings` or `dramatic brass`). Generate 3+ variants, pick the best. Tag/lyrics detail: `comfyui-local` → `references/ace-step-prompt-guide.md`.
2. **Scene plan** — ~22 clips × 12 s = 264 s minus 21 × 1 s crossfades ≈ 243 s covers a 240 s song. Map each clip to a song section (intro/verse/chorus/bridge/outro); write image prompts from the lyrical arc.
3. **Images** — `generate_image.py --prompts-json '[...]' --aspect 16:9` (FLUX.2 Klein 9B for environments/text, Z-Image-Turbo for fast character i2i); batches of 5–6, distinct `--filename` per batch, 3 variants for key scenes.
4. **Animate** — LTX 2.3 i2v 12 s per clip via `templates/generate-all-clips.sh` (sequential batch, `background=true`). NEVER prompt "singing" — LTX co-generates audio that clashes with your track; use gestures, landscapes, camera moves, instruments. >12 s accumulates tail errors.
5. **Assemble** — crossfade chain (`fade out 2 s`, `fade in 0 s`, 1 s overlap, concat) or the simpler concat-demuxer pass; final audio is ALWAYS the master song (`-an` on clips or map only the song); `-shortest` is fine here (single music track governs length).

File layout: `musica/<song>/{letra.txt,song.mp3,imagenes/NN-scene.png,videos/clip-NN.mp4,generate-clips.sh}`.

Gotchas: ComfyUI writes to `C:\ComfyUI\output` (`/mnt/c/ComfyUI/output`) — a "missing" clip is usually there; LTX native ambient audio must be replaced in assembly.

## B) Narrative short film (dialogue + score + SFX, H3-driven)

| Aspect | Music video | Narrative short |
|---|---|---|
| Engine | LTX 2.3 i2v (12 s) | H3 Ref2VA (15 s, native audio) |
| Audio | master song | score + dialogue + SFX |
| Upscale | per A/B | Lanczos (stability) |
| Length | 3–5 min | 30–60 s |

- Dialogue: `<d>[Spanish] "text"</d>` in the prompt; consistent character refs across scenes; no-speech layering per `references/h3-audio-lipsync.md` for non-dialog clips.
- Score: `generate_song.py --tags "orchestral, cinematic, ..." --format flac` (lossless masters); action 90–120 BPM, romance 60–80; multiple batches, pick best.
- H3's incidental music: strip via BandIt stems (`references/post-production.md`), mix score with sidechain ducking (same file).
- Delivery per SKILL.md "YouTube delivery"; verification checklist in `references/post-production.md`.

## Singer lip-synced to an EXISTING track

Multi-clip builds are sync-by-construction (exact-slice generation + tiling verification + master-song final audio): full pattern in `references/h3-audio-lipsync.md` §"Multi-clip lip-sync build". Architecture: `gen_clip.sh <name> <start> <dur> <ref> <prompt_file> [seed]` slices the song segment STEREO, runs H3 `--reference-audio seg.wav --preserve-reference-audio`, renames if the output lacks `.mp4`; `build.py` asserts `song_start == cumulative offset` (±0.05 s) and `sum(dur) == song duration` (±0.06 s) before rendering. Stills (no mouth) fill voiceless spans — zero desync risk.
