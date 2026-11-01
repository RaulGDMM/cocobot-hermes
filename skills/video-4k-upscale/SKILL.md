---
name: video-4k-upscale
description: "Use when upscaling video to 4K. Lanczos pipeline."
version: 1.0.0
author: Cocobot
license: MIT
metadata:
  hermes:
    tags: [video, 4k, upscale, lanczos, ffmpeg]
    related_skills: [video-fps-interpolation, ai-video-post-production]
---

# Video 4K Upscale (Lanczos ffmpeg)

## When to Use
- User asks to upscale a video to 4K / UHD.
- Preparing an H3/LTX 720p master for delivery (Sonda Europa pattern: 4K first, then 60fps).

Upscale a source (typically 720p H3/LTX output, 1344×768) to 3840×2160 UHD.
Default: **Lanczos via ffmpeg** (Raúl's preference — NOT Real-ESRGAN):
prioritize temporal stability and naturalness over artificial sharpness,
especially on already-AI-generated footage (no doubling of AI artifacts).

## Why the scale-then-crop filter chain
Source 1344×768 is NOT exactly 16:9 (ratio 1.75, not 1.777).
A direct `scale=3840:2160` would stretch the image ~0.4%. Instead:
1. `scale=3840:2196:flags=lanczos` — keep the original aspect at 3840 wide
   (2196 ≈ 3840/1.75, rounded to even → 0.07% stretch, imperceptible).
2. `crop=3840:2160:0:18` — trim 18 px top/bottom to land on exact 2160.

Generalize for other sources: `H = even_round(3840 * Hsrc / Wsrc)`;
`crop y = (H - 2160) / 2`. If the source is exactly 16:9 (1280×720),
`scale=3840:2160:flags=lanczos` alone is fine (no distortion, no crop).

## Command (proven on "Yo vs Lovecraft" 44s and "Sonda Europa" 4:30)
```
ffmpeg -i in.mp4 -vf 'scale=3840:2196:flags=lanczos,crop=3840:2160:0:18' \
  -map 0:v:0 -map 0:a:0 -c:v libx264 -preset slow -crf 15 -pix_fmt yuv420p \
  -c:a copy -movflags +faststart out_4k.mp4
```
- CRF 15 + preset slow = master-quality 4K (intermediate; final delivery
  re-encodes happen later at CRF 18).
- `-c:a copy` — never re-encode audio at this step.
- `-movflags +faststart` — for web/streaming.
- 4K encodes are SLOW → run in background (`terminal background=true`);
  a 4:30 4K preset-slow encode far exceeds any foreground timeout.

## Verify
```
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,nb_frames
```
→ 3840×2160, same fps and frame count as source. Size sanity for this content
class: ~24 Mbps ≈ 823 MB for 4:30 at 24fps CRF15 (Sonda Europa observed).

## Pipeline order with 60fps (see `video-fps-interpolation` skill)
4K upscale FIRST (on the 24fps master) → AMT-L 60fps at full 4K → final
delivery encode (CRF 18 preset medium + audio). Do NOT interpolate at 720p
and upscale the result: AMT flow runs better at full res and you avoid one
extra 4K re-encode.

## Pitfalls
- Do NOT default to Real-ESRGAN (Raúl's explicit preference: Lanczos by
  default, no AI-upscaler artifacts on AI footage).
- One pass only — do not chain multiple Lanczos steps (720p→1080p→4K).
- Keep a 24fps 4K master with audio as the reference for later steps
  (the fps pipeline's interpolated masters are video-only).

## DEFAULT since 2026-10-15: DLSS 3x+NR (Raúl's A/B verdict)
Raúl compared DLSS 3x+NR vs Lanczos on pvsg-intro + culturista windows and chose
**DLSS 3x+NR as the new 4K default** (sharper/cleaner, no ringing, ~16 s/5 s clip
vs minutes). Lanczos below = FALLBACK when GPU/broker unavailable or on request.
Recipe and node plumbing: skill `dlss-comfyui-video` (mode `3× (Ultra Performance)`,
NR model M + mask on + skin 2.0 + structure 1.5). Output 4032×2304 (1.75:1 from
1344×768) → crop to 16:9 (4032:2268) then scale 3840×2160 for delivery.
YouTube line for DLSS masters:
`⬆️ Upscale: DLSS 3x + Neural Rendering — de 720p a 4K UHD, nitidez temporal sin artefactos`

## Legacy default: Lanczos ffmpeg

## YouTube description line (reused across the channel)
`⬆️ Upscale: Lanczos 4K — de 720p a 3840×2160 UHD, priorizando estabilidad temporal y naturalidad sobre nitidez artificial`

## Reference (Sonda Europa — completed)
- 720p build v29 (62 MB) → `sonda_europa_acto1_v29_4k.mp4`
  (3840×2160, 24fps, 6480f, 823 MB) → then AMT-L 60fps → final master.
- Same method documented in `Sonda Europa/PLAN.md` § "Estado final".
