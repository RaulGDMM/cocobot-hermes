---
name: video-fps-interpolation
description: "Use when upscaling video fps (24 to 60). AMT-L pipeline."
---

# Video FPS Interpolation (AMT-L)

Interpolate a video to a higher frame rate for smoother motion.

## Status 2026-10-15: DLSS FG won the A/B (Raúl) — pipeline per-shot
DLSS Frame Generation (ComfyUI node, skill `dlss-comfyui-video`): CFR-perfect,
34 s/5 s @768p, 215 s/5 s @4K — Raúl chose it over AMT-L. **Mandatory: pre-split at
calibrated cuts** (its internal cut detector missed a hard montage cut → melted
frames); FG each shot in one broker batch, concat. AMT-L remains the documented
fallback / offline path (cut-list machinery below still applies to it).

## Defaults (decided 18/08)
- **Model: AMT-L** (not AMT-S, not RIFE).
  - ckpt: `/root/workspace/rife/AMT/pretrained/amt-l.pth` (12.9M params)
  - cfg: `/root/workspace/rife/AMT/cfgs/AMT-L.yaml`
  - Why: AMT-L resolves motion artifacts (e.g. the moving-planet shimmer in Sonda Europa's Jupiter orbit) that AMT-S and RIFE left.
- **Pipeline: 24→120→60** (preferred): single 5x pass, then 2:1 decimation.
  - Cheaper alternative: 24→48→96→60 (two 2x passes) — ~33% less GPU, slight error compounding (2nd pass interpolates between synthetic frames).
  - 24→120 in one pass is possible: AMT is arbitrary-timestep (`embt`=k/N in [0,1]; repo ships `demo_8x.py` using embt=1/8..7/8).
- venv: `/root/workspace/biblia-gato-video/upscale_env/bin/python3` (torch cu130, cv2, numpy)
- Drivers: `/root/workspace/rife/amt_interp_5x.py` (Nx single pass, `--factor 5`), `/root/workspace/rife/amt_interp.py` (2x chained passes, `--passes 2`)

## Why interpolate ABOVE the target fps
60 is not a power-of-2 multiple of 24. Interpolate to 96 or 120 (above 60), then decimate down to 60 → every output frame is genuinely interpolated (no duplicated frames → clean CFR). If you interpolate to 48 and then upsample to 60, you'd duplicate frames → dirty frame pacing.

## Steps
1. **Calibrate hard cuts** (pre-step, CPU, on the 24fps source):
   - `ssim_calibrate.py` → SSIM per consecutive frame-pair.
   - Cut rule "isolated asymmetric dip": ssim < 0.60 with at least one neighbor > 0.62. (A flat 0.80 threshold gives ~446 false positives on fast motion → judder.)
   - Save `cut_list_<name>24.txt` = input frame indices.
   - Note: ffmpeg `select='gt(scene,0.25)'` misses some cuts (e.g. a cut at ssim 0.451); the SSIM dip rule catches them.
2. **Interpolate** (GPU, via broker — see below):
   - 5x single pass: `amt_interp_5x.py --input X.mp4 --output out_120.mp4 --factor 5 --cut-list cut_list.txt --scale 0.5 --crf 16`
   - 2x passes: `amt_interp.py --input X.mp4 --output out_96.mp4 --passes 2 --cut-list cut_list.txt --scale 0.5 --crf 16`
   - `--scale 0.5` = internal feature/flow resolution (output is always full-res). `--scale 1.0` = full-res flow, ~10% slower.
   - cut-list: exact input frame indices; a pair whose current frame index is in the list is NOT interpolated (hold prev).
3. **Decimate to target** (CPU): `ffmpeg -i out_120.mp4 -vf fps=60 -an dec_60.mp4`
4. **Encode final** (CPU, BACKGROUND — 4K60 takes >7min):
   - `ffmpeg -i dec_60.mp4 -i master_24fps.mp4 -map 0:v -map 1:a -c:v libx264 -preset medium -crf 18 -c:a aac final.mp4`
   - Audio comes from the 24fps master (the interpolated master has no audio).
5. **Verify CFR is perfect** (must pass):
   - `ffprobe -show_packets` → sort by PTS → every delta = 1/60 s (0 outliers, 0 duplicates, 0 skips).

## Broker GPU-swap (the RTX 5090 is occupied by llama.cpp)
- Broker `http://172.23.176.1:8791`, endpoint `/v1/gpu-exec` (blocking). It stops llama.cpp → runs your command in WSL → restarts llama.cpp.
- Payload: `{"command": [...], "timeout_seconds": N, "wsl": true}`. `timeout_seconds` = subprocess timeout; HTTP read wait = timeout + 120.
- **During the job the LLM drops** (it runs on the same 5090). After launching the orchestrator in the background, do NOT issue further tool calls — just wait for the completion notification / `process wait`.
- Orchestrator pattern: `amt_broker_job_*.py` (urlopen POST, blocking). Launch with `terminal(background=true, notify_on_complete=true)`.
- Health: `GET /health` → `queue_size`, `llama_running`, `gpu_exec_busy`.

## Pitfalls
- Do NOT interpolate across a hard cut → ghosting/mixing. Always pass a pre-calibrated `--cut-list` (not in-flight SSIM).
- `--passes` fps bug: output fps is `fps*2` per pass, NOT `2**(p+1)` (which double-accumulates → 192 instead of 96).
- ffprobe packets arrive in decode order (B-frames → negative deltas); sort by PTS before analyzing pacing.
- 4K 60fps encode > 7min → run in background (a foreground call times out).
- Input without audio: take audio from the 24fps master.
- Model requires H/W after `--scale` to be divisible by 16 → padding divisor = `16/scale` (e.g. 32 at scale 0.5).
- 8x/5x demos use a GoPro-trained ckpt; the standard ckpt is trained at 2x — A/B a short high-motion window first before committing a full run.

## A/B: 96→60 (2 pases 2x) vs 120→60 (pase 5x) — tested 18/08
Window 33–36s of Sonda Europa (highest measured motion, cut-free), 3s each.
- **CFR identical & perfect** in both: 178 packets @60, delta mean 16.6667ms, 0 outliers, 0 dups.
- **Pixel diff (178 frames aligned): mean 1.68/255 (0.66%), p95 2.1/255** → at/under x264 CRF16 noise floor.
- **Vision A/B: "prácticamente indistinguibles"**; the 2-pass 96 path measured a hair sharper on two fine details (rocket flame jet, planet limb), consistent with smaller interpolation steps = less shimmer. Part of the gap may be the decimation phase (96→60 = 8:5 re-maps vs 120→60 = clean 2:1) rather than raw VFI quality.
- **Cost: 5x path does 4 inferences/pair vs 3 for the 2-pass path → ~33% more GPU, no measurable gain.**
- **Conclusion for this class of content (slow camera, moderate motion): the 2-pass 96→60 path is sufficient and marginally better. Do NOT re-run a full master at 5x just to gain 120fps.** Use the 5x/120 path only if a future source has extreme high-speed motion where sub-frame steps between original frames matter.

## Reference (Sonda Europa Act 1 — completed)
- 24fps source: `sonda4k_full_24fps.mp4` (6480f, 3840×2160, with audio)
- 64 calibrated cuts: `cut_list_master24.txt`
- 96fps master: `sonda4k_full_amtL_96fps.mp4` (25917f, 1.1GB)
- Final 60fps: `Sonda Europa/videos/sonda_europa_acto1_v29_4k_60fps_amtL.mp4` (856MB, CRF18, CFR-perfect)
- 3s A/B test (18/08): `win3s_24fps.mp4` (72f), `win3s_120fps.mp4` (5x path), `win3s_96path_60fps.mp4` (current 96→60 path, both 180f @60fps) — window 33–36s (high motion, cut-free).
