# ACE Step 1.5 — songs and scores

Umbrella rule: use `generate_song.py` for any musical audio. Two modes — `song` (vocals or instrumental) and `score` (cinematic backing track). Output is uncompressed WAV.

## Script

```bash
uv run /root/.hermes/skills/media/comfyui-local/scripts/generate_song.py \
  --mode song|score \
  --prompt "<style/genre/instruments>" \
  [--lyrics "<verse/chorus/bridge...>"]   # song only; omit/empty = instrumental
  --duration <seconds> \
  --filename "<output>",
```

- `--mode song`: `--lyrics` optional (empty = instrumental). `--duration` default 300, range 1–600.
- `--mode score`: `--instrumental` (no vocals). `--duration` typically 120–300.
- Output format: WAV (lossless, uncompressed).

## Length targets

- 360 s ≈ 6 min → full song with intro/verse/chorus/bridge/outro
- 300 s ≈ 5 min → standard song
- 120–180 s → short / single section
- Score: match the cut length of the footage it backs (verify against the timeline, not a guess)

## Draft vs final (quality modes)

- **Draft**: faster, lower quality — use to iterate on prompt/structure/arrangement.
- **Final**: slower, highest quality — use only for the delivery render.
- Workflow: draft → adjust prompt (genre / instruments / vocals / structure) → re-draft → compare → final render.

## Iteration rules

- Change ONE dimension per pass (genre, instrumentation, vocal style, structure) so you can attribute the change.
- Regenerate the same seed range to compare like-for-like; only move seeds to escape a bad roll.
- For scores, state the emotional arc and where the peak lands ("builds over 40 s to a sustained climax, then resolves") — "epic" alone is not a prompt.

## Tag rules (avoid collisions)

- NEVER combine `epic choir` + `dense orchestration` in the same prompt — the two fight for the low/mid and the result is muddy. Pick the choir OR the orchestral density, not both.
- If you want both a choral layer and orchestral body, weight them ("warm choir under a sparse orchestral bed") rather than maxing both.

## Verification

- `ffprobe` the output: confirm duration matches `--duration`, confirm an audio stream is present, note the sample rate/channels.
- Listen before delivery — do not ship an unverified render.

## Delivery

- Deliver the WAV to the user as-is (it is already lossless). No re-encode unless the pipeline demands a specific format (then do it in the assembly step, not here).
