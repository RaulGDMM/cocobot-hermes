#!/usr/bin/env python3
"""Pipeline v2 con HDR: upscale 3x+NR -> split planos -> FG por plano ->
concat+crop SDR60 -> RTX HDR por chunks (PQ 1000nits) -> concat 10-bit HDR10 + audio."""
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, "/root/workspace/dlss-ab")
from dlss_ab_send import upscale_wf, fg_wf, run_job  # noqa: E402

sys.path.insert(0, "/root/.hermes/skills/media/comfyui-local/scripts")
from generate_video import upload_file  # noqa: E402

D = Path("/root/workspace/dlss-ab")
X = "\u00d7"
CUT_FRAMES = [360, 384, 408, 456, 624, 672]  # ssim dip-rule, 24fps
FPS = 24
CHUNK = 120  # frames 4K60 por job HDR (~12 GB float in+out; probado en hdr_timed)
NITS = 1000


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def last_saved(info):
    for s in info["saved"]:
        if isinstance(s, str) and not s.startswith("DLFAIL"):
            p = Path(s)
            if "_00001_" in p.name:
                return p
    raise RuntimeError(f"sin output util: {info}")


def hdr_wf(up, prefix):
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": up}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "RTXTrueHDR", "inputs": {
            "images": ["2", 0], "contrast": 100, "saturation": 100, "middle_gray": 50,
            "luminance": NITS, "debanding": True, "output_colorspace": "HDR PQ"}},
        "4": {"class_type": "CreateVideo", "inputs": {"images": ["3", 0], "fps": ["2", 2]}},
        "5": {"class_type": "SaveVideo", "inputs": {
            "video": ["4", 0], "filename_prefix": prefix, "format": "mp4", "codec": "auto"}},
    }


# 1) Upscale 3x+NR
name30 = upload_file("http://172.23.176.1:8791", D / "pvsg30_src.mp4")
log(f"subido {name30}")
_, info = run_job("p30v2_up", upscale_wf(name30, f"3{X} (Ultra Performance)", "dlssab/p30v2_up"), 1200)
up_master = last_saved(info)
log(f"up master 4K24: {up_master.name} ({up_master.stat().st_size/1e6:.0f} MB)")

# 2) Split por planos
bounds = [0] + CUT_FRAMES + [720]
seg_paths = []
for i in range(len(bounds) - 1):
    a, b = bounds[i], bounds[i + 1]
    seg = D / f"p30v2_seg{i:02d}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{a/FPS:.6f}", "-to", f"{b/FPS:.6f}",
         "-i", str(up_master), "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
         "-pix_fmt", "yuv420p", "-an", str(seg)],
        check=True,
    )
    seg_paths.append(seg)
log(f"{len(seg_paths)} segmentos listos")

# 3) FG por plano (1 batch)
seg_names = [upload_file("http://172.23.176.1:8791", p) for p in seg_paths]
log("segmentos subidos, lanzando FG")
with ThreadPoolExecutor(max_workers=len(seg_names)) as pool:
    futs = [pool.submit(run_job, f"p30v2fg{i:02d}", fg_wf(n, f"dlssab/p30v2fg{i:02d}"), 2400)
            for i, n in enumerate(seg_names)]
    infos = [f.result()[1] for f in futs]
fg_paths = [last_saved(i) for i in infos]
log(f"FG listo: {len(fg_paths)} segmentos")

# 4) Concat FG + crop/scale -> master SDR60 intermedio (sin audio)
m60 = D / "p30v2_m60sdr.mp4"
lst = D / "p30v2_concat.txt"
lst.write_text("".join(f"file '{p}'\n" for p in fg_paths))
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
     "-vf", "crop=4032:2268:0:18,scale=3840:2160:flags=lanczos",
     "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p",
     "-r", "60", str(m60)],
    check=True,
)
log(f"master SDR60: {m60.name} ({m60.stat().st_size/1e6:.0f} MB)")

# 5) HDR por chunks de CHUNK frames
nframes = int(subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
     "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(m60)],
    capture_output=True, text=True, check=True).stdout.strip())
log(f"HDR: {nframes} frames en {(nframes + CHUNK - 1)//CHUNK} chunks")
chunk_paths = []
for i, a in enumerate(range(0, nframes, CHUNK)):
    ch = D / f"p30v2_ch{i:02d}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(m60),
         "-vf", f"trim=start_frame={a}:end_frame={min(a+CHUNK, nframes)},setpts=PTS-STARTPTS",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p",
         "-an", "-r", "60", str(ch)],
        check=True,
    )
    chunk_paths.append(ch)
chunk_names = [upload_file("http://172.23.176.1:8791", p) for p in chunk_paths]
log("chunks subidos, lanzando HDR")
t0 = time.time()
with ThreadPoolExecutor(max_workers=len(chunk_names)) as pool:
    futs = [pool.submit(run_job, f"p30v2h{i:02d}", hdr_wf(n, f"dlssab/p30v2h{i:02d}"), 1800)
            for i, n in enumerate(chunk_names)]
    infos = [f.result()[1] for f in futs]
hdr_paths = [last_saved(i) for i in infos]
log(f"HDR: {len(hdr_paths)} chunks en {time.time()-t0:.0f}s")

# 6) Concat chunks HDR -> encode 10-bit HDR10 + audio maestro
final = D / "pvsg30_FINAL_HDR.mp4"
lst2 = D / "p30v2_concat_hdr.txt"
lst2.write_text("".join(f"file '{p}'\n" for p in hdr_paths))
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst2),
     "-i", str(D / "pvsg30_src.mp4"),
     "-map", "0:v:0", "-map", "1:a:0",
     "-c:v", "libx264", "-preset", "medium", "-crf", "13", "-pix_fmt", "yuv420p10le",
     "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc",
     "-color_range", "tv", "-r", "60", "-c:a", "aac", "-b:a", "192k",
     "-movflags", "+faststart", "-shortest", str(final)],
    check=True,
)
log(f"FINAL HDR: {final} ({final.stat().st_size/1e6:.0f} MB)")
print("PIPELINE_V2_OK")
