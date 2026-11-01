---
name: dlss-comfyui-video
description: Use when enhancing video with DLSS ComfyUI nodes.
version: 1.3.0
author: Cocobot
license: MIT
metadata:
  hermes:
    tags: [video, dlss, comfyui, upscale, interpolation, nr]
    related_skills: [comfyui-local, video-4k-upscale, video-fps-interpolation]
---

## When to Use
- Upscale AI video (SR 1.5-3x), interpolate fps (DLSSG), or DLSS 5 NR material cleanup via ComfyUI.
- Evaluate or run the generative refine alternative **Open-H3-Regenerate-2K** (3-step H3 regeneration replacing the upscale+NR step). Rules below; weights/recipe in `references/open-h3-refine.md`.
- FINAL PIPELINE v2 (Raúl approved 2026-10-16): H3 → DLSS 3x+NR (4K default) → DLSS FG 60fps per-shot → RTX Video HDR (PQ, 1500 nits) → 10-bit HDR10 encode. 30 s A/B template: `pvsg30_pipeline_v2.py` (dlss-ab). Full-master runner: `pvsg44_pipeline.py` (dlss-ab) — same recipe made RESUMABLE via `pvsg44_state.json` (steps cuts/up/split/fg/m60/hdr/final; relaunch resumes at the first incomplete step, per-item FG/HDR results checkpointed too); run it with `/usr/bin/python3`.

# Alternative route: Open-H3-Regenerate-2K (generative refine)
Open replacement for MiniMax's closed H3-Regenerate-2K API: regenerates an H3 draft (or any ≤768P draft,
including other models' — LTX-2, SANA-Video) natively at 768P/1080P/2K/4K in 3 diffusion steps — it
redraws detail at target res instead of reconstructing it (DLSS NR). Full weights/node/recipe/staged-paths:
`references/open-h3-refine.md`. Hard rules:
- Feed the ORIGINAL H3 draft clip, never frames pulled from an already-upscaled/encoded master; mux master audio into the delivery.
- VRAM is the limiter, not time: the refine runs at TARGET resolution (the latent upscaler "saves time, not VRAM"). Always smoke a short clip at 1080P first, then 2K; native 4K on the 5090 is not viable.
- 4K delivery path if 2K fits: draft → refine @2560×1440 → DLSS 1.5×+NR → 4K (FG/HDR steps unchanged). A/B against the approved master arm with identity + mouth-envelope QA per the v2 protocol.
- **Identity drift**: the official σ0.909 schedule buys max detail by regenerating micro-attributes (nose color, iris, digit shapes) and, on wide multi-character shots, whole SPECIES/anatomy (cat → dog face, animal drummer → human, paws → human hands). Chroma anchor (ffmpeg `mergeplanes=0x001112`, free) fixes color only, never shape. Raúl's rule: prefer lower σ (less new detail) over identity changes — pick σ per shot by A/B on the busiest shot, QA-cropping EVERY character, background musician and hands, and always use a short per-shot refine prompt (never the long generation prompt). Length: snap drafts to the H3 17k+5 grid and size the AV latent with the official `temporal_shape` helpers. **Never use `MiniMaxH3MemoryEfficientSageAttentionPatch` (KJNodes) on clips >5 s**: its int8 Q/K + fp8 V quantisation degrades with sequence length (forcing fp32 accumulation does NOT help), so 5 s looks fine while 9.4 s comes out uniform blur/grid garbage with no error. Without it, 9.4 s @2K is clean (sharpness ~1200 vs draft ~670) in ~15 min; 15 s @2K OOMs → split ~7.5 s at camera motion or refine at 1080p. Prefer one job per camera shot up to ~9.5 s. Sweep table + harness: `references/open-h3-refine.md`.
- **Diagnose before you declare a limit**: when a long job comes out broken, isolate stages with cheap jobs before blaming anything: decode the upscaler output WITHOUT refining (~2.5 min) and with/without each optional patch. Toggle one component per job and batch them together. Check your own nodes and memory-saving patches before third-party code, and never tell Raúl "it can't do X" from one correlated log line. Judge outputs with a full-clip per-frame sharpness curve + playing the video, never a single face crop.
- **Respect Raúl's PC time**: when he says he needs the computer, finish the running job, launch nothing else, and leave the next batch STAGED (harness edited, not run) with a HANDOFF section listing the launch command and QA plan.
- Long shell commands on `/mnt/c`/`/mnt/e`, PowerShell or logs: always wrap in `timeout` (Raúl explicitly wants no hangs); find logs via the broker start script, never `find` over whole drives.

# DLSS nodes in ComfyUI (SR + Frame Gen + DLSS 5 NR)

ComfyUI core has NO native DLSS. The pack `ComfyUI-NVIDIA-DLSS-Frame-Interpolation`
(Konohamaru04, MIT, DLLs bundled via Git LFS, no pip deps) is installed at
`E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\ComfyUI-DLSS-Frame-Interpolation`.
Real NVIDIA NGX runtime (feature 18 = DLSS 5 NR), runs natively on Windows via the broker's ComfyUI.
RTX 50 series; driver 617.14 OK.

## Nodes (class_type for API workflows)
- `NvidiaDLSSVideoUpscale` — VIDEO→VIDEO, modes `"1× (DLAA / native)"`, `"1.5× (Quality)"`, `"1.724× (Balanced)"`, `"2× (Performance)"`, `"3× (Ultra Performance)"` (labels use U+00D7!). NR controls: `nr_preset/nr_style/nr_intensity/local_tone_strength/local_structure_strength/skin_structure_strength/automatic_mask/dlss_model_preset` (J/K/L/M; M = strongest skin/hair reconstruction), `output_detail_strength` 1–2.
- `NvidiaDLSSFrameInterpolation` — VIDEO→VIDEO, `output_fps` "60"/"120"..., `dlss_engine` Auto/Native DLSSG/Cascade (24→60 = cascade + decimation, exact CFR).
- `NvidiaDLSSImageUpscale` — IMAGE batch→IMAGE.

## Workflow JSON gotchas (API format via broker /v1/generate)
- Chain: `LoadVideo` (core, input `file` = name in ComfyUI input dir) → DLSS node → `SaveVideo`.
- **SaveVideo REQUIRES `"format"` (e.g. "mp4") and `"codec"` ("auto") inputs** in this ComfyUI (0.41) — omitting them → TypeError 500.
- Upload clips with `generate_video.upload_file()` → files land as `openclaw-upload-XXXX.mp4`.
- **Multiple jobs = submit them CONCURRENTLY** (thread pool, one `/v1/generate` per job, all in flight together): the broker groups jobs arriving within its batch window into ONE batch (batch_max 20) → one Strata stop/restore. Sequential `run_job` calls = Strata reload between every job (slow; Raúl flagged it). Helper: `run_batch()` in `openh3-ab/openh3_test.py`; give every job a unique prefix. Use sequential only when a later job depends on an earlier result — and then say so.
- Video codec widget: `"H.264 (NVIDIA NVENC)"` for speed.
- Orchestrator + workflow builders: `/root/workspace/dlss-ab/dlss_ab_send.py` (sends N jobs in one broker batch; fg_wf/upscale_wf/run_job reusable).
- gpu-exec from WSL: pass a SCRIPT FILE path, never `bash -c "..."` inline — wsl.exe joins argv unquoted (and remember the file must exist; a rejected `&` command never ran your `touch`).

## ffmpeg injection (no broker restart)
Nodes resolve ffmpeg at IMPORT time via `DLSS_FFMPEG_PATH`/`DLSS_FFPROBE_PATH` or PATH.
Broker env is fixed → injected via `C:\ComfyUI\.venv\Lib\site-packages\sitecustomize.py`
pointing to `E:\Workspace\Openclaw\llama-cpp\ffmpeg.exe`. If the pack updates and
stops working, check that file still exists.

## Verifying the neural pass actually ran
Broker responses DON'T include the report_json string output. Read reports from disk:
`E:\...\ComfyUI\temp\dlss5-video-output-*\reports\*.report.json` and `dlssfg-output-*\reports\`.
Key fields: `feature_18_confirmed` (true = NR ran), `nr_upscaling_active`, `nr_native_fallback`
(3× upscale currently ALWAYS falls back: DLSS SR first, NR at output res — documented, normal),
`applied_dlss_model_preset_name`. FG reports: `generated_frames/copied_frames/scene_cuts/elapsed_seconds`.
Verify CFR with `ffprobe -show_packets packet=pts_time` (timebases differ per encoder — use pts_time, not pts) **after sorting the pts list**: packets come in storage/DTS order and B-frame reordering makes raw consecutive deltas look random (false CFR failures).

## Measured on RTX 5090 (2026-10-15, 5s 1344×768 windows)
- NR 1× DLAA: ~14 fps of frames (~9 s/clip). 3× upscale+NR: ~7-8 fps (~16 s/clip). FG→60 @768p: 34 s; FG→60 @4K (4032×2304): 215 s (~43× source duration, similar compute to AMT-L 4K).
- **End-to-end validated** (pvsg 30 s, `pvsg30_pipeline.py` in dlss-ab — reuse as template): upscale 2.5 min + split/upload 20 s + FG 7 shots 4K one batch 23 min + concat/crop/scale/mux 2 min = **28 min total**; final CFR-perfect 1800f@60, cuts clean. Full 270 s montage ≈ 3.5-4 h.
- SSIM cut calibration for splitting: use the 32×32 ssim_matlab method (ssim_cuts_pvsg30.py) — full-res SSIM on CPU is 100x too slow; dips <0.60 vs neighbors >0.62 (clean separation in practice: real cuts 0.01-0.18, next dip 0.71).
- **The dip rule misses cuts between visually similar shots** (same set/costume/blocking keep SSIM >0.60) and can miss fade-to-black seams — always UNION detected cuts with the authoritative edit boundaries (the montage/build clip map) before splitting; merge the two lists treating cuts within ±2 frames as one (frame rounding differs between sources).
- **Per-shot FG at 24→60 rounds each odd-length shot UP (+0.5f)** → staircase A/V drift
  (~+217 ms over a 274 s/59-shot master: lips visibly late in 2nd half). Fix WITHOUT re-running
  GPU: rebuild the 60fps concat with per-shot target length `R(b_i+1)-R(b_i)`, R(x)=floor(x+.5)
  (telescopes to exact total, drift ≤0.5f everywhere; trim last frame of over-long shots —
  invisible at hard cuts). Template: `dlss-ab/m60_fix.py`. Verify: sum(fg_frames) vs 2.5*src.
- ffprobe `-show_packets packet=pts_time` lists packets in DTS/storage order (B-frames): SORT
  pts before delta-checking CFR, else a perfect CFR 60 looks like garbage deltas.
- CPU frame-scan env: torch+numpy live in the SYSTEM python (`/usr/bin/python3`), not the Hermes venv python; cv2 may be absent — decode with `ffmpeg -f rawvideo -pix_fmt rgb24` piped to numpy (let ffmpeg pre-scale to 32×32) instead of cv2.VideoCapture; a 4.5-min master then calibrates in <30 s.
- Recommended NR recipe (author measurements): dlss_model_preset M, automatic_mask on, skin_structure_strength 2.0, local_structure_strength 1.5, nr_intensity 1.0 (clamps at 1.0 on current builds).
- A/B verdicts (Raúl, 2026-10-15): DLSS 3x+NR = new 4K default (beats Lanczos, no ringing); NR = optional finishing step (convincing, esp. realistic); DLSS FG beats AMT-L at 768p, approved pending 4K (4K passed CFR+quality).

## CRITICAL: hard cuts — internal detector UNRELIABLE
FG internal scene-cut detector (`score>0.24` in guides.py, stage 0 only) reported
`scene_cuts: 0` on an obvious bright-stage→dark-closeup montage cut → produced 2-3
melted double-exposure frames BEFORE the cut (synthetic frames interpolated across
it). FIX (verified clean): **pre-split the master at calibrated cut points**
(ssim_calibrate.py from video-fps-interpolation), FG each shot as its own job
(all jobs in one broker batch; batch_max 20), concat outputs. Each segment starts
with history reset → hard cut stays hard. For a 270 s/60-cut montage: ~61 jobs,
3-4 batches.

## CRITICAL: per-shot FG rounds up → cumulative A/V drift
FG outputs `ceil(len×fps_out/fps_in)` frames per shot, so **every odd-length shot
adds +0.5 frame** and the error ACCUMULATES across the concat (26 odd shots on a
274 s master = +13f = 217 ms lip-sync drift by the end; a short test master can
cleanly hit the exact frame total and hide this entirely). Never concat FG
outputs directly: trim shot i to the **global-grid length**
`t_i = R(b_{i+1}×fps_out/fps_in) − R(b_i×fps_out/fps_in)`, R(x)=floor(x+0.5) — the
sum telescopes to the exact total, |drift| ≤ 0.5f at every cut, and dropping one
60fps frame immediately before a hard cut is invisible (duplicate the last frame
instead when `t_i >` actual). Do this in the m60 concat pass (per-input
`trim=end_frame=t_i` in one filter_complex + concat). QA gate before delivery:
`Σ nb_frames(FG outputs)` must equal `round(src_frames×fps_out/fps_in)`; if it
exceeds it, measure the drift curve at singing/close-up timestamps and fix before
shipping. A cheap HDR/final re-run fixes it without touching upscale or FG.

## Why FG is ~4x slower per-frame than upscale+NR (explained 2026-10-15)
In games FG is cheap because the engine provides per-pixel motion vectors for free;
video post must ESTIMATE dense optical flow per pair, plus cascade multiplies network
passes (~3 per pair for 24->60), plus raw RGBA8 frames cross a process pipe (~37 MB/frame
at 4K) plus NVENC/intermediate files. The network itself is ~1-2 ms — the plumbing around
it is the cost. Option if FG@4K becomes the bottleneck: FG at 768p BEFORE upscale
(measured 6x faster; untested quality — SR after FG might amplify FG artifacts).

## Non-integer ratios: go DIRECT, never 24→120→60
24→60 is DLSSG's native case (arbitrary time-scale is what cascade+decimation is
for — verified exact CFR on output packets). A two-pass 24→120→decimate-60 yields
the IDENTICAL output phase grid — over each 5-frame period the surviving frames
land on phases {0, 0.4, 0.8, 0.2, 0.6} either way — at ~2.7× the FG cost. Same
result, same potential quality; do not offer the two-pass route except as an
explicitly-motivated A/B.

# RTX Video HDR (official NVIDIA VFX Nodes)
Pack `Comfy-Org/ComfyUI_Nvidia_VFX_Nodes` (Apache-2.0) installed at
`...\custom_nodes\ComfyUI_Nvidia_VFX_Nodes`; pip dep `nvidia-vfx>=0.2` in `C:\ComfyUI\.venv`
(install with `/mnt/c/ComfyUI/.venv/Scripts/python.exe -m pip install`). Also contains
RTXVideoSuperResolution and RTXVideoFrameGeneration (RTX40+, auto shot detection — plan B
for FG cuts, untested). HDR node `RTXTrueHDR`: IMAGE batch→IMAGE (not VIDEO), inputs
`contrast/saturation/middle_gray` (100/100/50 defaults), `luminance` 400-2000 = mastering
peak nits, `debanding` True, `output_colorspace` `"HDR PQ"` or `"HDR"` (HLG).
Chain: `LoadVideo → GetVideoComponents (out0=images, out2=fps) → RTXTrueHDR → CreateVideo(images,fps) → SaveVideo`.

## HDR chunking + mastering (all verified 2026-10-16)
- **RTXTrueHDR is stateless per-frame** (verified: overlapping-batch diff ≈ double-encode
  control noise; only debanding dither ±2 LSB) → chunking any frame count is safe, no
  seam flicker. Chunk ≤120 frames at 4K60 (~12 GB float in+out; 64 GB PC with Strata
  unloaded). 120-frame 4K60 chunk ≈ 87 s wall incl. upload/encode/download.
- Full-master HDR cost: ~9 min per 30 s 4K60 (15 chunks). Pipeline v2 30 s total ≈ 37 min;
  270 s master ≈ 6 h (FG still dominates ~3.5 h).
- **Mastering peak: use `luminance: 1500`** (Raúl verdict after comparing 1000 — flagships
  reach 1500-2500 nits in small windows; 1000-nit displays tone-map back with no penalty).
- **Delivering HDR10**: `-c copy` does NOT write H.264 VUI color tags (stays bt709) —
  re-encode final: `-pix_fmt yuv420p10le -color_primaries bt2020 -color_trc smpte2084
  -colorspace bt2020nc -color_range tv` (HDR requires 10-bit). Verify with ffprobe field
  `color_transfer` (NOT `color_trc` — that key returns empty).
- **Seam/flicker check**: pipe whole file through `scale=1:1,format=gray -f rawvideo` and
  diff per-frame luma; spikes at chunk seams must match the SDR intermediate's deltas at
  the same frames (content changes, e.g. finale flashes, look identical in both — only
  HDR-only spikes are real seam artifacts).

## Pitfalls
- **YouTube HDR delivery needs more than color tags**: bt2020/smpte2084 VUI on an
  H.264 upload is NOT enough — YouTube classifies HDR from SMPTE ST 2086 mastering
  display metadata + MaxCLL (and prefers HEVC/VP9). Without it the video processes as
  SDR with a generic tone-map (washed colors, no HDR option in the quality menu).
  Recipe: HEVC main10 `-tag:v hvc1` + `-x265-params "master-display=G(8500,39850)
  B(6550,2300)R(35400,14600)WP(15635,16450)L(15000000,1):max-cll=1500,0"`. Scales:
  coords ×50000 (NOT ×100000 — double is silently accepted and yields garbage
  primaries; check a SEI parse before believing it), luminance ×10000 nits;
  max-cll separator is a COMMA (`:` is silently dropped with a warning).
  Verification: ffprobe does NOT expose HEVC in-band HDR SEI (137 MDCV / 144 CLL)
  as frame side_data — walk mdat's length-prefixed NAL units (4-byte) and parse
  SEI 137/144; a plain binary grep gives FALSE POSITIVES inside compressed data
  (it fooled us once). Script: `cocobot-hermes/dlss-pipeline/yt_hdr10_upload.sh`.
- **YouTube HDR is a lottery, not a pipeline** (18/10): even with fully verified
  SEI metadata, recognition/badge delay is unpredictable (community reports: hours
  to a week) with NO indication in Studio, and meanwhile every SDR/mobile viewer
  sees YouTube's OWN tone-map of the PQ master — which looked washed on ours.
  DEFAULT DELIVERY unless Raúl explicitly wants HDR: self-controlled tone-map to
  Rec.709 SDR (reviewable before upload):
  `-vf "zscale=transfer=linear:npl=203,format=gbrpf32le,tonemap=mobius:desat=2,
  zscale=transfer=bt709:matrix=bt709:primaries=bt709:range=tv,format=yuv420p"`
  + libx264 crf18 preset medium (~33 Mb/s 4K60, ~0.3x speed). This ffmpeg's
  tonemap has NO `bt2446a` algorithm and NO `max` option (both fail at init).
  QC: compare side-by-side frames + YAVG vs the last approved SDR build.
- **Don't use gpu-exec to touch Windows files.** Hermes WSL mounts the Windows drives read-write (`/mnt/e`, uid=0) — delete/inspect ComfyUI's `input`/`output`/`temp` directly with plain rm. gpu-exec exists ONLY for exclusive-GPU work; each call stops/restarts Strata (the agent's own LLM). (18/10: did two pointless gpu-exec calls to clean 198 MB; and the rm matched nothing because patterns were invented from sed-normalized `ls` output — always list REAL filenames before rm.)
- **Broker job queue is NOT FIFO** — parallel-pool jobs complete out of arrival order, and
  jobs sharing a `filename_prefix` get server-side numbering in completion order. Give every
  job a UNIQUE prefix and map outputs by prefix; if ambiguous, identify each output's chunk
  by correlating its first frame vs master frames (zscore'd gray 64×36 — robust to the PQ
  stretch; correct match ≥0.95 vs next ≤0.88).
- **Re-running a step with the SAME prefix** (resume after partial failure) → ComfyUI numbers
  outputs `_00002_`, `_00003_`…; any picker hardcoded to `_00001_` kills the pool with
  "sin output util" even though the job succeeded. Pick by HIGHEST number, skip
  `openclaw-upload` echoes (pvsg44_pipeline.last_saved fixed 18/10). Also: an exception
  inside `pool.map` iteration cancels all not-yet-started futures — completed-but-unconsumed
  outputs are already on disk; harvest them by glob before resuming.
- ffprobe `-count_frames` on a 4K 10-bit master decodes every frame (minutes, looks like a
  hang through WSL) — use stream field `nb_frames` (container metadata) for frame counts.
- Frame-exact clip extraction: `trim=start_frame=A:end_frame=B,setpts=PTS-STARTPTS,fps=60` —
  `-vsync 0` combined with `-r` is a hard ffmpeg error.
- Windows Defender may quarantine the worker `nvngx.dll` (dll-run-as-process pattern) — exclusion on the runtime folder if "worker could not start".
- Worker needs exclusive GPU: the broker already guarantees it (llama/Strata stopped during jobs).
- DLSS 5 NR reconstructs MATERIALS (skin/hair/fabric), does not restore faces the source lost; conservative without game engine buffers.
- Clone needs `git lfs` (nvngx_dlssnr.dll 159 MB); GitHub zip = pointer files.
- 3× from 1344×768 gives 4032×2304 (1.75:1) — crop to 4032:2268 then scale for 16:9 comparisons/delivery.
- Broker download of `temp`-type outputs fails (HTTP 400 "type must be output or input") — harmless; the SaveVideo output is what matters.
