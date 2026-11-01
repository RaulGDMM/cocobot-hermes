# H3 audio — semantic vs exact, dialogue recipes, verification, rescue, lip-sync builds

## Modes

- `--reference-audio` alone = **semantic**: H3 regenerates voice/content jointly. Use for timbre-anchoring; the result is NOT your audio.
- `--reference-audio X --preserve-reference-audio` = **exact-audio**: H3 conditions the video on the reference (the mouth follows the real audio) and remuxes the ORIGINAL audio lossless (ALAC) into the clip → the final audio IS your song/voice.
- Hard limits: max 3 audio refs, each 2–15 s, ≤15 s total; audio cannot travel alone (needs ≥1 image/video ref); video 4–15 s per generation → a 15 s clip + 15 s audio is the exact fit.
- Slice a song into ≤15 s segments: `ffmpeg -ss X -t 15 -i song.mp3 -c copy seg.wav`.

## Song/voice-driven lip-sync (character sings over an EXISTING track)

- Identity drift is risk #1: the audio forces Ref2VA (semantic refs) → the character image does NOT anchor frame 0 (it's not `--image`). Mitigate: 1 main ref + "must remain the same individual throughout, do NOT transform" + negative `morphing, identity change, transformation` + 2-seed A/B; if it fails, `ref_image_size=max`.
- Singing ≠ speaking: H3 was trained on dialogue and generalizes to animals/animated; sustained-vowel mouth sync is *close, not perfect*. Always verify with Whisper (clip audio vs expected text) + vision frame-by-frame.
- Duets: exact-audio references one dominant voice per clip — either one wide shot with the mixed audio (the more prominent voice carries the sync) or alternating shots. Clean multi-voice: LongCat-Video-Avatar-1.5 (open-source, runs local on the 5090, multi-stream audio).
- Two refs (identity + band/scene photo that contains the singer's face in a static pose) DEGRADE lip-sync by default — the static face competes with the audio moving the mouth, and framing goes wide. Verified exception: the 2 refs work if (a) `detailed_description` forces the framing ("tight close-up ... he is the ONLY visible subject in the shot ... the background is nearly total darkness") AND (b) `retention_analysis` marks the scene ref `weak_reference` ("take ONLY the concert lighting mood and haze; IGNORE its wide framing and IGNORE every character in it"). Safer route: single identity ref, build the stage in the prompt. If the EXACT stage photo matters, pre-edit it with Nano Banana to remove the singer first (stage + lights + rest defocused), then declare it `weak_reference`.

## Dialogue with anchored voices (multi-character)

Two-character 15 s clip, one voice anchored: `--reference-audio voz.ogg` (semantic, NO `--preserve`) + each character with one exact quoted Spanish line; the anchored line declared "in the [warm mid-range female] voice timbre of Audio 1", the other "a natural mid-aged male voice with a clear Spanish accent". Rules that hold it (one seed was enough):
- Each line gets its own timestamp window in `detailed_description`.
- `overall_soundscape` lists both lines verbatim, capped: "THE ONLY speech in the entire clip are those two lines."
- The audio ref is `weak_reference` ("ONLY the timbre; its words IGNORED") so the ref's own words don't leak.
- Spanish lines go in `<d>[Spanish] "text" </d>` tags and are re-listed verbatim in `overall_soundscape`.

## No-speech layering

"ABSOLUTELY NO SPEECH" in `overall_soundscape` alone is NOT enough — H3 has invented English dialogue with it present. Layer at the character-behavior level too (verified on a two-person 15 s action clip — delivered audio transcribed as wordless screams, no dialogue):
- `detailed_description`: "NEITHER MAN SPEAKS ANY WORD — they only scream wordlessly, no dialogue, no language" (or "he does not speak at all" for solo).
- `overall_soundscape`: "SCREAMING WORDLESSLY — high-pitched primal screams with absolutely no words in any language. ABSOLUTELY NO SPEECH, NO WORDS, NO DIALOGUE, NO TALKING."
- Negative: `speech, words, dialogue, talking, language, singing, music`.

In action scenes, explicitly scripting "wordless screams" anchors better than pure silence. Pass signature (Whisper): a wordless-scream clip transcribes as a repeated exclamation with a low-confidence language guess (e.g. `en @ 0.48`, "No! No! No!") — that IS the pass; coherent sentences are the failure.

## Semantic-audio defects — verify by GLOBAL similarity, never keywords

Failure modes (a 16-clip series lost 11/16 to the first two):
- **A. Garbage BEFORE the line** — invented proper names or a RECITATION of the English prompt. The Whisper keyword-coverage score stays 100% (the real line still follows) → a keyword gate passes broken clips.
- **B. Trailing speech AFTER the line** — repeats the line's tail or reads fragments of the English negative prompt aloud.
- **C. Garbling MID-LINE** — the line breaks inside.

The correct metric is normalized GLOBAL transcription similarity vs the expected line:

```python
import difflib, unicodedata
def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace(":", ".").replace("—", " ").replace("–", " ")
    return " ".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s).split()
def sim(expected, whisper_text):
    e = " ".join(_norm(expected)); w = " ".join(_norm(whisper_text))
    return difflib.SequenceMatcher(None, e, w).ratio() if w else 0.0
```

Calibrated values: perfect = **1.000**; garbled-name / recited-prompt = **0.895–0.901** → threshold **0.93** separates cleanly; trailing speech = 0.5–0.78. Normalize accents + punctuation first or you get false negatives (`3:47` vs `3.47`).

Layered prompt fix that raises the hit rate (regenerate seed+1, up to 3×, when sim < 0.93):
1. `detailed_description`: "His VERY FIRST spoken word is the first word of that line — he does NOT say anything before it. He does NOT read, recite, narrate, mumble, or invent any other word, name, caption, stage direction or instruction; he does NOT say the English words 'picture', 'scene', 'opening', 'show'. THE ONLY speech in the entire clip is that single quoted Spanish line."
2. Negative: `reciting the prompt, reading instructions aloud, spoken English words, garbled names, invented words, mumbling before the line, extra speech, English`.
3. Keep the quoted line in `<d>[Spanish] ... </d>` tags and re-list it verbatim in `overall_soundscape`.

### Deterministic rescue (try BEFORE spending a regeneration attempt)

When the defect is purely in the audio and the VIDEO is approved, ffmpeg repair costs seconds, not GPU minutes.

- **Trailing speech (B)**: keywords pass but sim < 0.93 → align the expected line word-by-word with Whisper `word_timestamps=True` (WORD-level normalization, NOT char-level — char-level breaks the alignment) to find the END time of the last expected word, then cut:
```bash
ffmpeg -i in.mp4 -af "atrim=0:{cut},asetpts=PTS-STARTPTS,afade=t=out:st=0.25:d=0.35" -c:v copy -c:a aac -b:a 192k out.mp4
```
- **Mid-line garbling (C)**: the cut cannot fix a line broken inside — but sometimes the CORRECT ending exists at the very end of the clip (H3 repeats it). Then a manual audio splice works:
```bash
ffmpeg -i in.mp4 -filter_complex \
  "[0:a]atrim=0:{clean_end},asetpts=PTS-STARTPTS[a1];[0:a]atrim={tail_start}:{tail_end},asetpts=PTS-STARTPTS,afade=t=out:st=0.55:d=0.12[a2];[a1][a2]concat=n=2:v=0:a=1,apad=whole_dur={DUR}[ao]" \
  -map 0:v -map "[ao]" -c:v copy -c:a aac -b:a 192k out.mp4
```
(take clean head + the correct tail fragment from the clip end + pad back to full duration; video stream-copied). If the correct ending is NOT present in the clip, splice is impossible → that clip truly needs regeneration (or accept/report).
- **Video + audio together**: an audio-only cut silences the audio but stream-copies the video — the character keeps moving its mouth in silence ("se corta la voz pero sigue moviendo los labios"), even with Whisper sim 1.000. The default rescue cuts video AND audio to `line_end + ~0.8s` margin with a short fade, full re-encode:
```bash
ffmpeg -i in.mp4 -t {cut} -vf "fade=t=out:st={cut-0.4}:d=0.4" -af "afade=t=out:st={cut-0.4}:d=0.4" -c:v libx264 -c:a aac -b:a 192k out.mp4
```
Use the audio-only cut only when the tail video is genuinely fine (the character goes still). Re-verify with Whisper after ANY cut: the margin after the last expected word means no script line is lost.

## Exact-audio verification (does the clip's audio really carry the reference?)

**Gold rule — channel layout AND sample rate:** the reference segment cut from the MP3 is usually STEREO. Comparing a MONO extraction against the stereo segment (or vice versa) gives ≈0.03 = FALSE NEGATIVE: it looks like the remux failed when it didn't. Load both with the same channel count and compare channel by channel. Same trap on SAMPLE RATE: a hybrid clip whose audio was remuxed from a 48k source correlates ≈0.01 against a 44.1k master slice — resample the reference to the clip's rate (`-ar <clip_sr>`) before correlating; a suspicious ≈0.01 is a layout/rate mismatch first, a failed remux second.

```bash
# extract WITHOUT -ac/-ar (preserve layout):
ffmpeg -y -i clip.mp4 -vn -c:a pcm_s16le /tmp/clip.wav
```

```python
import wave, numpy as np
def load(p):
    with wave.open(p) as w:
        sr = w.getframerate(); ch = w.getnchannels(); n = w.getnframes()
        d = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    return sr, ch, d
sr, ch, seg = load("segmento.wav"); segL = seg[0::ch]          # channel L of the segment
for clip in ["/tmp/clip.wav"]:
    sr2, ch2, c = load(clip); cL = c[0::ch2]                   # SAME layout
    tr = min(len(cL), len(segL))
    print(f"{clip}: corr={np.corrcoef(cL[:tr], segL[:tr])[0,1]:.4f}")
    # optional lag search: correlate cL[off:] with segL in sr2*0.1 steps, take the max
```

Reading the result:

| corr @ 0 ms | Meaning |
|---|---|
| `1.0000` (±0.0000) | The clip carries the reference **bit-a-bit** (ALAC lossless remux OK) |
| `≈0.998` | Same track, re-encoded lossy (the AAC delivery version) |
| `≈0.03` | The clip's audio is **model regeneration** (remux failed — or channel-layout mismatch, check that first) |

Cross-checks: (1) Whisper of the extracted clip audio must transcribe the expected text (catches "says something else" / mouth not following timing even when the track is the right one) — run faster-whisper on demand with `uv run --no-project --with faster-whisper python3 …` (system python lacks it; `medium` int8 on CPU handles singing fine); (2) `ffprobe` audio duration == segment duration (not the video `--duration`); (3) script log line `Audio replaced with original (ALAC lossless)` — do NOT grep the script output with a narrow filter (it hides the failure warning).

## Delivery: ALAC-in-MP4 is silent on Windows

The track IS in the clip (verifiable) but the default Windows player doesn't decode ALAC inside MP4 → the user sees a muted video. Before delivery:

```bash
ffmpeg -i clip.mp4 -c:v copy -c:a aac -b:a 192k clip-aac.mp4
```

(video stream-copied; the ALAC master stays as archive). Same rule for every H3 master in a montage: deliver the AAC versions, keep ALAC masters in the project archive.

## Multi-clip lip-sync build (song over 4+ min, ~20 clips + stills)

Sync by CONSTRUCTION, not by luck. H3 generates ~15 s per clip with its own co-generated audio; simply concatenating clips under the song desyncs at every cut (the mouth was generated for the model's internal timing). The pattern:

1. Each singing clip is generated from its OWN exact slice `song[song_start .. song_start+dur]` (`--reference-audio <slice> --preserve-reference-audio`) → the mouth is conditioned on THAT portion.
2. The clip is placed at that SAME offset in the timeline (concat order + `dur` per clip).
3. Final audio = ALWAYS the master song (the original MP3); each clip contributes video only (`-an` on extraction).

Tiling the timeline with no gaps makes desync impossible: each clip's mouth matches the song portion that generated it, and that portion plays at exactly that moment.

- Architecture: `gen_clip.sh <name> <start> <dur> <personaje_ref> <prompt_file> [seed]` — slices the segment STEREO (`ffmpeg -ss <start> -t <dur> -i song.mp3 -c:a pcm_s16le seg.wav`, NO `-ac/-ar`, the layout must match for verification) → runs H3 with `--reference-image personaje.png --reference-audio seg.wav --preserve-reference-audio` → renames the output if it lands without `.mp4`. Clip durations 4–15 s (H3 limit); audio ref ≤15 s.
- `build.py` (centralized, see `templates/build_template.py`): data-driven `CLIPS = [{seg, kind, src, song_start, dur}]` — `kind="video"` → approved clip in `clips/v1/` (already generated from its slice); `kind="still"` → fixed image for instrumentals/gaps (no mouth → no desync risk; place in voiceless spans).
- **Tiling verification (the key)**: before render, `resolve_clips()` asserts `song_start_i == cumulative offset` (tolerance 0.05 s) and `sum(dur) == song duration` (tolerance 0.06 s); abort on mismatch.
- **Trimming exact-audio clips**: H3 clips come out slightly long (a 15 s request ≈ 15.08 s). Trim from the BACK only (`in_start=0`, `-t dur`) — the mouth represents the slice starting at clip t=0, so cutting the tail keeps sync while cutting the head (`in_start>0`) shifts the mouth off the master. To cover a SUB-WINDOW of a slice with an approved clip, set `in_start = window_start − slice_start` (a clip generated from song[38..44] covers song 42–44 with `in_start=4`) — approved clips can bridge timeline gaps with exact sync, no new generation.
- Pipeline: extract each segment video-only (normalize to fixed resolution/fps, e.g. 1344×768@24 with scale+pad+fps) → concat demuxer → mix the master song (`-map 0:v -map [aout]`, AAC 192k, `+faststart`) → verify duration + per-span levels → clean temp files.
- Verify: clip audio vs its slice = 1.0000 bit-a-bit correlation; final montage audio vs master song ≈ **0.997 @ 0 ms** (AAC re-encode — expect ~0.997, not 1.0000; 0.9999+ only if delivering the master without re-encode); lag must be 0 ms, else check `-t`/`-ss`. Frames at start/mid/end per clip (identity, mouth, framing) + Whisper of each clip's audio.
- Iteration (user rules): 2 seeds per clip, user picks; the approved stays SOLO in `clips/v1/`, the rest go to `clips/v1/descartadas/`; no regeneration without explicit permission when the user asked for diagnosis only; every build leaves a verifiable `montaje/<proyecto>_vN.mp4` (duration == song, streams, levels).

## Audio-driven cut timing (where to place camera cuts inside a clip)

Full-track Whisper DROPS quiet phrases that sit in an instrumental gap — it reports silence until the next loud line and can miss a singer's soft entry by 1–2 s. Before trusting a gap, measure a per-window RMS energy profile of the zone and transcribe the zone in short overlapping windows; use the first audible vocal onset from the windows, not the full-track transcript.

When the user asks "find with your tools where the guitar plays so the cuts land there", measure per-window band energy over the span (0.25 s windows, naive DFT over the target bands is fast enough on a 16k mono extract): energy in the BRILLIANT band (≈2.5–8 kHz, guitars/cymbals) plotted against the VOCAL band (≈200–1200 Hz) — windows where the brilliant band spikes while the vocal band is low are instrumental riffs; that is where cutaways to instrumentalists belong, and sung phrases mark where the singer's shot belongs. Combine with Whisper `word_timestamps` on the same span: riffs → cutaway windows, word starts/ends → exact lyric cut points (e.g. stop an insert "just before the word Y" = cut at Y's start timestamp). Present the resulting SHOT LIST (timings + who is on screen) to the user before generating.

## Instrumental performance sync (drummer / stroking performer vs master)

When the shot is an instrumentalist playing real hits from the master (no mouth to protect):

1. **Build a hit map before writing any prompt.** STFT flux per band over the span (e.g. win 1024/hop 128; kick 40–150 Hz, snare 160–420 Hz + 1.8–6 kHz noise, crash 6.5–13.5 kHz), then group per-band onsets within ≤90 ms into single strike events with a kind label. FAST GUITAR RUNS PRODUCE FAKE "SNARE/CRASH" ONSETS in a dense mix — a real drum hit needs a cymbal-band spike clearly above the guitar bed plus an RMS jump; sanity-check every candidate against the raw per-window band profile. When the user's ear contradicts your envelope reading ("I hear several hits, you say one"), re-measure per-band at finer resolution BEFORE defending the coarse reading — the ear is usually right.
2. **Prompt/negative recipe** lives in SKILL.md (instrumental-performer rule): LOW ready pose in the keyframe, rate-phrased "one stroke per audible hit", negatives that never ban fill/roll/multiple hits.
3. **Verify the performance with zone motion, not face frames.** Crop the sticks/limb region and diff frames: `ffmpeg -i clip.mp4 -vf "crop=iw*0.55:ih*0.40:iw*0.25:ih*0.30,fps=24,scale=200:80,format=gray" -f rawvideo -` → mean abs-diff per frame; bursts = frames above ~3×median. Compare burst times to the hit map modulo one constant offset — that offset is the placement fix, not a regeneration reason.
4. **Sync by placement (safe only because there is no mouth):** choose `in_start = first_hit_song_time − clip_first_burst_song_time` and place the entry at the hit window start (`in_start>0` head-trim would break a singing clip; here it's the tool). Example: bursts measured at clip-t 2.46/2.79/2.96/3.29 vs real hits 265.38/265.78/265.92 → `in_start=2.4, song_start=264.97` lands every stroke on its hit + one follow-through.
5. **End the shot on the master's silence:** extract the clip's LAST frame (`ffmpeg -sseof -0.1 -i clip.mp4 -update 1 -frames:v 1 last.png`) and use it as the final still covering the ring-out/silence to song end — a freeze on a triumph pose reads as intentional, and the build's `still-is-last` rule still holds.
6. **Probe both tracks before setting build `dur`:** an H3 mp4's VIDEO track can be longer than its audio track (5.6 s requested → 141 video frames = 5.875 s at 24 fps); `dur` must satisfy `in_start + dur ≤ video-track duration` or the segment comes out short and the tail freeze silently shrinks while the tiling check (metadata-only) passes.

## Borrowing inserts from a multi-shot generation: shot-boundary drift

The ACTUAL shot boundaries inside a generated multi-shot clip drift from the requested SHOT LIST — by +0.25–0.35 s typically, by +2–3 s when the model reflows the edit. NEVER compute a borrow offset from the requested shot list: locate the real boundaries first (scene-detect `select='gt(scene,0.15)',showinfo`, then a ≥12 fps grid around each candidate), pick the source offset INSIDE the confirmed shot, and QA the spliced result at ≥12 fps for intruder frames of the neighboring shot (a few leaked frames of the previous subject read as a glitch the coarse grid misses). If intruders appear, shift the source offset later into the shot and re-verify — do not regenerate.
