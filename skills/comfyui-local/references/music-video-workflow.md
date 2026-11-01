# Music Video Production Workflow

Complete pipeline for creating music videos from ACE Step 1.5 songs + LTX 2.3 video clips.

## Session example: "Tierra Rota" (war song, 4:30)

### Step 1: Generate song with ACE Step 1.5
```bash
uv run scripts/generate_song.py \
  --tags "Spanish guitar, flamenco ballad, acoustic guitar, soulful male vocals, deeply emotional, epic choir, choral backing" \
  --lyrics "..." \
  --filename "song.mp3" \
  --duration 270 \
  --language es \
  --key "E minor" \
  --bpm 72 \
  --quality xl-turbo \
  --count 2
```

### Step 2: Transcribe with Whisper (CRITICAL)
ACE Step 1.5 reinterprets lyrics — actual output differs from input. Get real timing:
```python
from faster_whisper import WhisperModel
model = WhisperModel('base', device='cpu', compute_type='int8')
segments, info = model.transcribe('song.mp3', beam_size=5)
for seg in segments:
    print(f'[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}')
```

### Step 3: Generate key images (FLUX.2 Klein 9B)
Generate 8-12 images representing different scenes/moods. Use `--prompts-json` for batch:
```bash
uv run scripts/generate_image.py \
  --prompts-json '["prompt 1", "prompt 2", "prompt 3"]' \
  --filename "scene" \
  --aspect 16:9 \
  --model flux2-klein-9b
```

**Image prompt tips**:
- Include `cinematic`, `photorealistic`, `16:9 widescreen`
- Describe mood: `melancholic`, `dramatic lighting`, `cold color palette`
- For war themes: `ruins`, `devastated landscape`, `smoke rising`, `grey sky`

### Step 4: Generate video clips (LTX 2.3)
**Duration: 10-12s max per clip** — 20s clips accumulate errors.

```bash
uv run scripts/generate_video.py \
  --image "scene-1.png" \
  --prompt "Slow camera pan across devastated landscape, wind blowing smoke, cinematic" \
  --filename "video-1.mp4" \
  --duration 12 \
  --resolution 720p \
  --aspect 16:9
```

**Video prompt tips**:
- Describe **motion**: `slow camera pan`, `wind blowing`, `fog drifting`
- Match song mood: `melancholic`, `cinematic`, `slow motion`
- **NEVER describe singing characters** — LTX generates its own audio, lip-sync won't match external music

### Step 5: Montage with ffmpeg
```python
# Python script for montage
import subprocess

videos = ["video-1.mp4", "video-2.mp4", ...]
filters = []
for i, _ in enumerate(videos):
    if i == 0:
        filters.append(f"[0:v]fade=t=out:st=10:d=2[v0]")
    elif i == len(videos) - 1:
        filters.append(f"[{i}:v]fade=t=in:st=0:d=2[v{i}]")
    else:
        filters.append(f"[{i}:v]fade=t=in:st=0:d=1,fade=t=out:st=10:d=2[v{i}]")

concat = "".join([f"[v{i}]" for i in range(len(videos))])
filters.append(f"{concat}concat=n={len(videos)}:v=1:a=0[vout]")

cmd = ["ffmpeg", "-y"]
for v in videos: cmd.extend(["-i", v])
cmd.extend(["-i", "song.mp3"])
cmd.extend([
    "-filter_complex", ",".join(filters),
    "-map", "[vout]", "-map", f"{len(videos)}:a",
    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    "-c:a", "aac", "-b:a", "320k", "-shortest",
    "final.mp4"
])
subprocess.run(cmd)
```

## Key learnings

| Pitfall | Fix |
|---------|-----|
| 20s clips have errors at end | Use 10-12s max, trim with `ffmpeg -t 10 -c copy` |
| Lip-sync mismatch with external audio | Never generate singing scenes — show instruments/landscapes |
| Lyrics don't match input | Always transcribe with Whisper before planning scenes |
| EQ artifacts on AI music | Use only normalize() + gentle volume boost, no frequency filtering |
| ffmpeg filters vary by version | Use static ffmpeg binary (`/tmp/ffmpeg-*-amd64-static/ffmpeg`) for advanced filters |

## Timing example (from "Tierra Rota")

| Time | Actual lyrics | Scene |
|------|--------------|-------|
| 0-30s | "La ventana de mi pueblo sonó vacíos..." | Empty windows of destroyed village |
| 30-53s | "Cada mañana otra casa... guitarra que no puede detener una bala" | Ruins + man with guitar |
| 53-67s | "Tierra rota, tierra de nadie donde los muertos no tienen tumba" | Devastated landscape |
| ... | ... | ... |

Total: ~22 clips of 10-12s each = ~260s, matching 270s song.

---

# H3 exact-audio music video: audio measurement & build verification

For lip-synced clips driven by a real song window (`--reference-audio <trozo> --preserve-reference-audio`), every timing decision must be MEASURED on the master/demucs stems — never taken from Whisper word timestamps alone.

## Real note/phrase boundaries (melisma)
- **Whisper word timestamps cut sustained sung notes short**: a belt reported ending at 211.4s actually rang until 213.9s. Measure sung-note ends on the RMS envelope of the demucs **vocals stem**, not on `word_timestamps`:
  ```bash
  ffmpeg -v error -i vocals.wav -ss A -to B -ac 1 -ar 16000 -f f32le -   # numpy: RMS every 20 ms
  ```
  Note end = last sustained frame (≈ −14 dB) before the drop (≈ −25 dB or worse).
- Whisper with a long window can hallucinate on sparse song sections: re-check with 2–3 short windows (≤ 7 s) or trust the envelope.
- End the clip window ≈ 0.1–0.15 s after the real note end and put a MOUTH-HOLD RULE in the prompt (jaw stays open through the very last frame) so the visual doesn't close before the audio does.

## Instrument choreography from the mix
- To choreograph non-singing performers (drummer…), derive the real hit pattern from the **no_vocals stem**: onsets = local maxima rising > 6 dB over ~30 ms with a percentile-70 threshold, deduped at 0.25 s; then a total + high-band (signal diff) RMS envelope at 10 ms to separate sparse / crescendo / total-silence zones.
- Write the result into the prompt as timed PHASES (clip time = song time − window start) plus the DRUM RHYTHM RULE: *one strike per audible hit, never faster than the music*; negate fast drumming/double-time. If the arrangement drops out (silence before a chorus), choreograph a freeze and verify it by motion profile.

## Verification recipes (measure, don't eyeball)
- **Motion profile** (freeze/stillness, crescendo energy): pipe the WHOLE clip once — `ffmpeg -i clip -vf fps=10,scale=64:36 -f rawvideo -pix_fmt rgb24 -` — then mean abs diff of consecutive frames grouped per phase. Per-frame `ffmpeg -ss` extraction returns empty bytes at sub-frame precision; never loop it.
- **Luma ramp for fades**: `trim=START:END,setpts=PTS-STARTPTS,fps=25,scale=1:1,signalstats,metadata=print` — use the trim filter, NOT `-ss` (seek shifts the pts_time mapping and fakes a bad ramp). Run ffmpeg with `-v verbose`: at `-v error`/`-v info` the `metadata=print` lines are suppressed and the parse yields zero samples. Parse `pts_time:` and `YAVG=` from SEPARATE stderr lines (a single-line regex finds nothing). **Pure black reads YAVG≈16, not 0** (libx264 yuv420p limited range) — don't chase 0.
- **Final cut positions**: `ffmpeg -ss A -to B -i final.mp4 -vf "select='gt(scene,0.25)',showinfo" -f null -` → pts_time of each cut. Cuts land within ±2 frames (−0.067 s @ 24 fps) of nominal: that's frame rounding, not drift — accept it. A cut the detector MISSES at threshold 0.25 is usually a sign of good shot-to-shot continuity — confirm it with a frame pair extracted either side of the nominal point.

## Continuity & identity audit (before intercutting or regenerating)
- **Character-presence audit**: before intercutting a character into a section, verify they appear — even small and dim in the background — in EVERY approved shot covering that time window. A character who stayed on stage (or is audible in the mix) must be visible at their position in all shots of the window; an intercut close-up exposes any shot where the background contradicts it. Audit by extracting one frame per shot in the window and checking presence/position before generating anything.
- **Clothing drift**: a loose clothing word in the video prompt ("black leather jacket") overrides the identity-anchor image (sleeveless vest) and forces a regeneration. State the canonical garment EXACTLY in an explicit CLOTHING RULE ("SLEEVELESS black leather vest, bare grey-and-white furry arms, epaulette straps") and add gemela negatives (`leather sleeves, sleeved jacket, long sleeves`) — the anchor image alone does not prevent drift.
- **Background performer synced across angles**: when a background character is also the subject of an intercut close-up, write the SAME timed phase timeline (sparse → crescendo → crash → freeze, in clip times) into BOTH prompts, and verify the background angle by motion profile of a CROPPED zone (`fps=10,scale=384:216,crop=w:h:x:y` over the background region) instead of the full frame — the foreground singer's movement contaminates whole-frame motion.
- **Keyframe edit chains**: to add a character to an approved keyframe, do ONE change per minimal NB-edit pass (add character → re-dim pass → position fix), each anchored to the character identity card. NB edits systematically BRIGHTEN the scene — always follow with a dim pass that uses the approved base keyframe as an explicit lighting reference ("make it much DARKER, exactly matching the near-darkness of image 2"). If an added background character sits too low/small, fix with a targeted re-seat edit referencing a correct example, not by redoing the whole scene.
- **Exact-audio remux check**: correlate the clip audio against master[window] (mono f32le) — expect corr ≈ 1.0000; anything less means the remux or window is wrong.

## Intercutting parallel shots of the same window
- `in_start > 0` is SAFE when `song_start = clip_generation_window_start + in_start`: the sub-range then lands on exactly the master audio that generated it, so lip-sync and hit timing stay locked. The "jamas in_start>0" rule only forbids placements that ignore the window start.
- Generate the parallel shot from the SAME audio window (identical duration), then take only the needed sub-range (e.g. the crescendo) and hard-cut between shots; the master audio runs unbroken under the cuts.

## Workflow gates (Raúl)
- New shot or new character: send the KEYFRAME image for his review BEFORE launching the H3 GPU job; launch only after his OK, one seed per clip, then wait for his verdict on the clip before iterating.
