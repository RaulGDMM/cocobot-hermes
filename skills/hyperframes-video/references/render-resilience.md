# Resilient local rendering and final MP4 verification

Use this when a long HyperFrames render runs on WSL/Linux, software GL, or another compositor-constrained host.

## Run shape

- Final renders belong in a tracked background process with completion notification.
- Set a runtime limit comfortably above the expected duration; a 3–4 minute, 1080p/30 fps composition can require well over ten minutes on screenshot capture.
- Status reports should name both HyperFrames' stage percentage and `framesCompleted/totalFrames`. The displayed percentage reserves time for assembly and is not the percentage of frames captured.

## Conservative retry after capture calibration failure

If automatic calibration reports `Page.captureScreenshot: Target closed`, closes Chrome, or falls back to one worker after compositor starvation, do not repeat the same auto configuration. Clean only the failed job's temporary `renders/work-<job-id>-*` directory and retry:

```bash
HF_DE_PARALLEL_ROUTER=false npx hyperframes render \
  --quality high \
  --workers 1 \
  --no-browser-gpu \
  --output renders/final.mp4
```

This disables the experimental parallel router, avoids browser-GPU instability, and trades speed for stability. A partial `video-only.mp4` or `audio.aac` inside a work directory is never the deliverable.

## Final artifact gate

Do not deliver merely because the render command exited zero.

1. Confirm the output exists and is non-empty.
2. Probe container and streams:

```bash
ffprobe -v error \
  -show_entries format=duration,size,bit_rate:stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels \
  -of json renders/final.mp4
```

3. Decode the complete video and audio streams:

```bash
ffmpeg -v error -i renders/final.mp4 \
  -map 0:v:0 -map 0:a:0 -f null -
```

4. Generate a contact sheet from the rendered MP4 itself, not from source snapshots, and inspect it for black frames, missing sub-compositions, absent media, clipping, or corruption:

```bash
ffmpeg -y -v error -i renders/final.mp4 \
  -vf "fps=1/20,scale=480:-1,tile=4x3:padding=8:margin=8" \
  -frames:v 1 renders/final-verification/contact-sheet.jpg
```

Choose the sampling interval and tile size so all major scenes are represented. Only after all three checks pass should the MP4 be attached to the user response.
