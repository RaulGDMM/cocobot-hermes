# Framerate & 4K upscaling (24 → 60 fps)

Umbrella rule: 4K uses Lanczos as the default (temporal stability, no halos/plastic skin); 24→60 fps uses RIFE v4.25 as the default, AMT-L only when large moving objects + embedded text shimmer. Both run through the broker GPU-swap.

## When to use which

- **Lanczos (4K, default)** — temporally stable, preserves detail without AI halos/plastic skin. Use for the 4K master and any shot where temporal consistency matters.
- **AI upscaler (Real-ESRGAN, AMT)** — only after a 3 s A/B on a sharpness-critical shot. Do not make it the default.
- **RIFE v4.25 (24→60, default)** — best general motion interpolation; clean on most content.
- **AMT-L (24→60, fallback)** — use when RIFE shows shimmer on large moving objects or on embedded text (credits, UI, signage).

## RIFE pipeline

- Script: `/root/workspace/rife/rife_interp.py`
- Model: `/root/workspace/rife/train_log/`
- venv: `/root/workspace/biblia-gato-video/upscale_env/bin/python3`
- Broker GPU-swap: the job needs the 5090 exclusively — llama-server is stopped for the duration of the run (expected; it comes back after).

Steps:
1. Probe the input: `ffprobe` → resolution, fps, duration, frame count.
2. GPU-swap: stop llama-server (broker).
3. Run RIFE at the target fps (e.g. 60).
4. Verify output: `ffprobe` → fps, frame count ≈ `input_frames * (60/24)`, duration unchanged.
5. Restart llama-server.

## AMT-L pipeline

- Use the same broker GPU-swap and venv pattern as RIFE.
- Trigger: shimmer artifacts on large moving objects or embedded text after an RIFE pass.
- Verify the same way: fps, frame count, duration; plus a visual A/B of the specific shimmering region vs the RIFE output.

## Verification (mandatory before delivery)

- `ffprobe` the output: confirm fps = target, frame count consistent with the rate change, duration preserved.
- For a 24→60 pass, expect ≈ 2.5× the frame count. A big deviation means the interpolation dropped/added frames — re-run.
- Spot-check motion (a fast pan or a whip) and any embedded text (credits/UI) for ghosting/shimmer.

## Delivery

- Deliver the interpolated file as the 60 fps master; keep the 24 fps source.
- Note the method (RIFE or AMT-L) in the project PLAN.md so the next pass is reproducible.
