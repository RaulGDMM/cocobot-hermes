# Post-production — stems, mixing, assembly, loudness, 4K, YouTube

Depth for the assembly/mixing/delivery rules in SKILL.md. All ffmpeg patterns verified on the 5090 box.

## ffmpeg fade gotcha: fade-to-black followed by MORE content

`fade=t=out` once completed **stays black for the rest of the file** (it never un-fades) — audio keeps playing, so by ear the build sounds right while everything after the fade is black video. When a montage fades to black at a scene boundary and a still/next scene follows, add timeline enable so the filter switches off exactly at the boundary: `fade=t=out:st=S:d=D:enable='lte(t,B)'` (B = boundary). Verify by measuring frame luma AFTER the boundary, not just at the end of the file.

**Mirror fades at a video split**: when one video ends fading to black and its sequel opens by lighting up, do BOTH ramps deterministically in the build — `fade=t=out:st=S:d=D:enable='lte(t,B)'` at the tail of part 1 and `fade=t=in:st=B:d=D:enable='gte(t,B)'` when placing part 2's first clip. **The fade-in has the mirror gotcha too**: without `enable='gte(t,B)'` it outputs BLACK for every frame BEFORE `st` (alpha factor pinned at 0), so the entire preceding video goes black while audio plays — symptom: file size collapses (black encodes tiny) and the user sees "completely black video". Chain both fades comma-separated on the same stream with complementary enables. Generators do not reliably execute a light-up/light-down ramp at the first/last seconds of a clip; the deterministic pair guarantees the two files meet at exact luma 0 and the seam is invisible. VERIFY: sample luma at ~10 points across the WHOLE timeline (not just the seam) — a collapsed output size is a red flag.

## Stem separation (BandIt v2)

- H3 joint audio (dialogue+SFX+music): separate with BandIt v2, **DnR v3 checkpoint** (cinematic DME, not vocals/accompaniment) via the ComfyUI broker `/v1/gpu-exec` — command: `E:\Workspace\Openclaw\bandit-v2\bandit.exe -i in.mp4 -o outdir -c dnr-v3 -s speech,music,sfx`, `timeout_seconds 7200`, `wsl:false`. Outputs `speech.wav`, `music.wav`, `sfx.wav`.
- Keep speech+sfx, discard H3's music — but **inspect the music stem first**: punch/impact transients can be misclassified into music; if impacts weaken, reintroduce only that stem during the action window at −10…−6 dB, keeping dialogue and finale clean.
- Status 2026-10-13: `E:\Workspace\Openclaw\bandit-v2\bandit.exe` NO LONGER EXISTS on the PC (broker answers `Command not found`, and `dir /b E:\Workspace\Openclaw | findstr bandit` is empty) — don't retry stem separation until Raúl reinstalls BandIt; the broker itself is healthy. For "where does a sustained vocal note end" questions, ask the user or use Whisper+spectral heuristics (periodicity in the 180-1100 Hz band can't separate vocals from sustained power chords — verified inconclusive).

## Assembly — always with a data-driven build.py

Complex montages use a centralized `build.py` (copy `templates/build_template.py`): `CLIPS = [{seg, src, start, dur, sfx}]`; the still is ALWAYS the last element with `src` ending `.png` and `dur=0` (computed); the script extracts segments (video-only), concats, pre-mixes SFX, does the final mix, verifies per-span levels, cleans temp files. Never hand-build a multi-clip ffmpeg chain — it is unreproducible and drift-prone.

Hard ffmpeg rules (each was a burned session):
- Extract segments with `-an -c:v libx264` — **never `-c:v copy` on H3 clips** (non-standard keyframes → empty files).
- Concat demuxer needs the list in a FILE (`printf "file 'x.mp4'\n" > list.txt`) — heredoc stdin fails with "Invalid argument".
- Exact duration via `-t <total>` — `-shortest` truncates early when stills/audio lengths differ.
- Still: `ffmpeg -loop 1 -i img.png -t <dur> -c:v libx264 -pix_fmt yuv420p -r 24 still.mp4`; detect stills by `src.endswith(".png")`; never mutate `CLIPS[-1]` to fake a still.
- In Python, pass `filter_complex` as one double-quoted variable (f-string newlines break the filter).

## Multi-track SFX over a full music track

Per SFX: `volume=<X>dB` → `adelay=<ms>|<ms>` (delays are MILLISECONDS; `:all=1` for all channels) → `apad=whole_dur=<total>` into its own silent full-duration track; then ONE final `amix=inputs=N:duration=longest:normalize=0` and `atrim=0:<total>`.

- `duration=first` truncates everything to the shortest input; `normalize=1` attenuates by input count (8 inputs ≈ −9 dB).
- `amerge` truncates the music when SFX end earlier — `apad` the SFX mix before amerging.
- Inline `adelay` >30 s inside one big `filter_complex` causes "Non-monotonic DTS" corruption → pre-mix each delayed SFX into its own full-duration track first (build.py does this).
- Forgot-adelay signature: SFX audible before their clip starts — check by listening to the first spans.
- Music: full independent track at original gain, no `atrim` unless the edit demands it. Verify: music-only spans within ±1 dB of the source (`volumedetect` on 2 SFX-free spans, source vs output).
- Prompt H3 for clean SFX: "Add sound effects: … No music, only natural sound effects".

## Score ducking (sidechain)

`[music][speech]sidechaincompress=threshold=-20dB:ratio=8:attack=100:release=300`, final `loudnorm=I=-18:TP=-1.5:LRA=11` (YouTube). With adjacent dialogue lines: ONE continuous duck from before the first line to after the last — never restore between lines; disable the word-level sidechain inside that span if it pumps. Measure the isolated bed across first-line/gap/second-line — levels must stay effectively constant. Verify short lines in an isolated window with Whisper Medium (full-track ASR can omit a brief final line).

## Hybrid clip assembly: insert-length changes shift ALL downstream source offsets

When concatenating pieces from exact-audio clips (footage t must equal song t), the concat timeline is rigid: if an earlier insert grows by Δ (e.g. user asks the opening guitarist shot to go 0.5→1.0s), the next SUNG segment must start at source_offset += Δ, otherwise its mouth runs Δ ahead of the master audio (looks fine early because motion is generic, but syllables land early — the user WILL notice on the last phrase). Verify per piece: source_in_start + sum(prev durations) == song_time − clip_song_start. Audio corr=1.0 only validates the remux, NEVER the video alignment — video sync is verified arithmetically or by frames-vs-word-timestamps.

## Narration loudness matching (replacing one VO clip)

Match perceived loudness, not peaks or by-ear gain:
1. `loudnorm=...:print_format=json` over the whole cohort; reference = **median LUFS-I of the unchanged clips**; cohort true-peak ceiling as output ceiling.
2. Two-pass EBU R128 (`linear=true` with the measured values) — raw gain is only OK if it can't breach the ceiling.
3. Gate: within ±0.5 LU of median, TP ≤ ceiling, duration unchanged, sample rate/channels/codec preserved; keep the original source WAV.
4. A replaced WAV at the same path can still be heard from a cached preview — restart/hard-refresh the review surface and confirm the exposed port.

## Speed ramp without deleting a shot

Trim before/target/after; `setpts=0.5*(PTS-STARTPTS)` on the video span + `atempo=2.0` on its audio; join with `filter_complex concat`. Re-check transition frames and shifted dialogue timestamps.

## 4K upscaling

- Always A/B a 3 s sharpness-critical sample first. Lanczos = default (temporal stability, no halos/plastic skin; nearly instant). Real-ESRGAN x4plus = natural/detail balance if AI is wanted. 4x-UltraSharp = most detail, most halos/plastic/shimmer. Avoid anime models and face restoration on photoreal identity-critical footage.
- H3 1344×768 path: upscale x4 → 5376×3072, center-crop 5376×3024 (`y=24`), Lanczos down to 3840×2160, keep fps.
- After video processing, remux the audio with stream copy and compare extracted ADTS SHA-256 for bit-exact AAC; delete temp frames only after verification.

## YouTube delivery

- Clean publishable filename FIRST (YouTube pre-fills the title from it) → ffprobe after rename → update PLAN.md.
- Title: `<Nombre> — <tipo de pieza> 100% generado con IA local` + 2 hook variants; double meanings welcome ("Yo vs Lovecraft").
- Description built from PLAN.md + ffprobe, never invented: "todo local" ONLY if every component is local (external API → soften and name it); CURRENT model names; ALL image models listed; H.264 CRF 15 / AAC 320k.
- Final QA: audio hash matches source, frame count matches, no black frames in a contact sheet, dialogue intelligible via Whisper, LUFS ≈ −18, TP ≤ −1.5 dB.
