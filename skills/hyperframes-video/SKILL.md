---
name: hyperframes-video
description: Create professional motion-graphics videos from HTML/CSS/JS using HeyGen's open-source HyperFrames framework. Covers project setup, TTS narration, procedural SFX, GSAP animations, linting, and local rendering to MP4.
version: 1.0.0
author: Cocobot
metadata:
  hermes:
    tags: [HyperFrames, Video, MotionGraphics, GSAP, HTML, MP4, Local, OpenSource, TTS, SFX]
    related_skills: [ai-video-production, ai-video-studio, comfyui-local]
---

# HyperFrames Video Generation

Create professional motion-graphics videos from HTML/CSS/JS using HeyGen's open-source HyperFrames framework. Audio narration, SFX, and background music are all supported. Runs 100% locally.

## Triggers

- User asks to create a promo video, explainer video, intro, motion graphic, or any video from text/code
- User mentions "HyperFrames" or wants to generate video without cloud services
- User wants "HTML to video" or "programmatic video"

## Prerequisites

- **Node.js 22+** — runtime for CLI and dev server
- **FFmpeg** — video encoding (pre-installed on most systems)
- No cloud accounts needed

## Workflow

> **Current HyperFrames contract wins:** Start every new task by loading `hyperframes`, then the routed workflow and the relevant `hyperframes-core`, `hyperframes-cli`, `hyperframes-creative`, `hyperframes-animation`, and `media-use` skills. This skill is a Cocobot workflow overlay; if an implementation detail here conflicts with the current framework skills or official documentation, follow the current framework contract.

For a narrated explanation of a technical product aimed at non-technical business stakeholders, read `references/business-narrated-explainers.md` before drafting. It covers jargon translation, narration-first approval, claim discipline, competitor framing, Spanish TTS phonetics, Whisper verification, and the corporate-dynamic visual midpoint.

When a scene paints boxes, semantic regions, cursors, or selection gestures over a screenshot, read `references/visual-overlay-geometry.md`. It defines the `object-fit` coordinate transform, synchronized drag choreography, 3D stacking fixes, and the mandatory start/mid/end snapshot pass.

When Studio runs in WSL/Linux but review happens on another machine, read `references/remote-preview-tunnel.md` before announcing a URL. Verify the listen address and prefer a temporary SSH reverse tunnel over firewall or port-forwarding changes.

When provisional TTS is replaced by one user recording per scene, read `references/user-recorded-voiceover.md`. It covers source preservation, timestamped ASR, hallucinated-tail rejection, PCM/loudness preparation, final-WAV retranscription, cumulative retiming, proportional GSAP retiming, and playback/resource verification.

Before a long local final render—or after capture calibration closes Chrome—read `references/render-resilience.md`. It defines the tracked background run shape, conservative one-worker retry, honest progress reporting, and the mandatory probe/decode/contact-sheet artifact gate.

### 1. Initialize project

```bash
cd /tmp && npx hyperframes init <project-name> --non-interactive --example blank
cd <project-name>
```

This creates `index.html`, `meta.json`, `hyperframes.json`, and installs 8 core skills.

### 2. Generate audio assets

**Narration (TTS):**
```bash
# Use text_to_speech tool → produces MP3
# Convert to WAV for HyperFrames:
ffmpeg -y -i <mp3-path> -ar 44100 -ac 1 assets/narration.wav
```

**Background music / SFX:**
- Generate procedurally with Python `wave` module (see `references/procedural-sfx.md`)
- Or use existing audio files placed in `assets/`

### 3. Write the composition

Edit `index.html`. **Critical rules:**

- **Root element** must have `data-composition-id`, `data-width="1920"`, `data-height="1080"`, `data-duration="<total-seconds>"`
- **Every timed element** needs `class="clip"`, `data-start`, `data-duration`, `data-track-index`
- **GSAP timeline** must be `{ paused: true }` and registered on `window.__timelines["<composition-id>"]`
- **CSS**: `.clip { visibility: hidden; }` — framework controls visibility
- **Audio**: use `<audio>` elements with `data-start`, `data-duration`, `data-track-index`, `data-volume`
- **Fonts**: Google Fonts work but are cached. For production, bundle fonts locally.

### 4. Structure scenes with tracks

```
Track 0-N:   Visual elements (background, glows, UI)
Track N+1:   Scene 1 elements
Track N+2:   Scene 2 elements
...
Track 20+:   Audio (narration, BGM, SFX) — keep audio on high track numbers
```

**Clips on the SAME track CANNOT overlap.** Each scene group gets its own track(s).

### 5. Animate with GSAP

Use explicit, seek-safe entrances and let the scene transition perform the exit:

```javascript
const tl = gsap.timeline({ paused: true });

tl.fromTo(
  "#element",
  { opacity: 0, scale: 0.8 },
  { opacity: 1, scale: 1, duration: 0.8, ease: "back.out(1.7)" },
  0.3,
);

window.__timelines["main"] = tl;
```

For multi-scene compositions, do not animate an outgoing scene away before the handoff. Keep it fully composed and let the selected transition handle the exit. Only the final scene may use its own fade-out. Follow `hyperframes-animation/transitions/` and the current `hyperframes-core` determinism rules.

### 6. Lint and fix

```bash
npx hyperframes check
```

**Common errors to fix:**
- `timed_element_missing_clip_class` → add `class="clip"`
- `overlapping_clips_same_track` → move overlapping clips to different `data-track-index`
- Sub-composition mount/timeline errors → verify host `data-composition-id`, inner id, and timeline key are identical
- `studio_missing_editable_id` → add stable `id` attributes (warnings, not blockers)

### 7. Render

```bash
npx hyperframes render --output output.mp4 --quality high
```

Quality presets: `draft` (fast, CRF 28), `standard` (CRF 18), `high` (CRF 15).

First render downloads bundled Chrome (~115MB). Subsequent renders are fast.

## Project structure

```
project/
├── index.html          # Main composition
├── compositions/       # Sub-compositions (optional)
├── assets/             # Audio, images, fonts
│   ├── narration.wav
│   ├── bg_pad.wav
│   ├── whoosh.wav
│   ├── boom.wav
│   └── ...
├── meta.json           # Project metadata
├── hyperframes.json    # Config
└── package.json        # Dependencies
```

## Pitfalls

1. **Overlapping clips on same track** — the #1 lint error. Every scene group needs separate track indices. Audio should use high track numbers (20+) to avoid conflicts.

2. **Scene exits belong to transitions** — in multi-scene work, do not fade or move the outgoing scene away before the transition. Keep it composed; the transition owns the handoff. The final scene is the only normal exception.

3. **Missing `class="clip"`** — elements without it stay visible the entire composition. Always add it to timed elements.

4. **Audio duration mismatch** — derive scene timings from the final processed audio, not source recordings or provisional TTS. Audio may intentionally be shorter than its scene to preserve lead-in and tail breathing room; assert that it fits without overflow and that cumulative starts/root duration close exactly. For sectioned user voice, follow `references/user-recorded-voiceover.md`.

5. **Google Fonts latency** — first render fetches fonts. They cache to `~/.cache/hyperframes/fonts/`. For deterministic builds, bundle fonts locally.

6. **Emoji in feature cards** — emojis render fine but font rendering varies by platform. For production, consider SVG icons.

7. **Browser GPU falls back to software** — on headless Linux without NVIDIA drivers, HyperFrames uses llvmpipe (software GL). This is fine for 1080p but slower. Use `--gpu` only when hardware encoding is actually available. If capture calibration closes Chrome or reports compositor starvation, do not blindly repeat auto mode; follow `references/render-resilience.md` for the conservative retry and final artifact gate.

## WSL-specific notes

- **Do not guess the preview URL**: inspect the listener with `ss -ltnp '( sport = :3002 )'`. If Studio listens on `127.0.0.1`, `<WSL-IP>:3002` is not reachable from another machine. Use `references/remote-preview-tunnel.md` for remote review.
- **Project persistence**: `/tmp/` is WSL-only. Copy durable projects to the intended workspace or mounted Windows drive.
- **index.html doesn't work standalone** — it needs the HyperFrames runtime. Open via `npx hyperframes preview`, not directly in the browser.

## References

- Business-facing narrated explainers: `references/business-narrated-explainers.md`
- Sectioned user voice replacing provisional TTS: `references/user-recorded-voiceover.md`
- Overlay geometry, drag choreography, and 3D stacking: `references/visual-overlay-geometry.md`
- Remote Studio review through SSH: `references/remote-preview-tunnel.md`
- Long local render resilience and MP4 verification: `references/render-resilience.md`
- Procedural SFX generation: `references/procedural-sfx.md`
- Official docs: https://hyperframes.heygen.com/
- GitHub: https://github.com/heygen-com/hyperframes
