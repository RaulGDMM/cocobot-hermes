#!/usr/bin/env python3
"""Regenera el master HDR a 1500 nits desde p30v2_m60sdr.mp4 (HDR+encode solo)."""
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, "/root/workspace/dlss-ab")
from dlss_ab_send import run_job  # noqa: E402
sys.path.insert(0, "/root/.hermes/skills/media/comfyui-local/scripts")
from generate_video import upload_file  # noqa: E402

D = Path("/root/workspace/dlss-ab")
M60 = D / "p30v2_m60sdr.mp4"
CHUNK, NITS = 120, 1500


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def last_saved(info):
    for s in info["saved"]:
        if isinstance(s, str) and not s.startswith("DLFAIL") and "_0000" in s:
            return Path(s)
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


nframes = 1800
chunk_paths = []
for i, a in enumerate(range(0, nframes, CHUNK)):
    ch = D / f"p30v3_ch{i:02d}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(M60),
         "-vf", f"trim=start_frame={a}:end_frame={min(a+CHUNK, nframes)},setpts=PTS-STARTPTS",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p",
         "-an", "-r", "60", str(ch)],
        check=True)
    chunk_paths.append(ch)
log(f"{len(chunk_paths)} chunks troceados")
chunk_names = [upload_file("http://172.23.176.1:8791", p) for p in chunk_paths]
log("subidos, lanzando HDR 1500")
t0 = time.time()
with ThreadPoolExecutor(max_workers=len(chunk_names)) as pool:
    futs = [pool.submit(run_job, f"p30v3h{i:02d}", hdr_wf(n, f"dlssab/p30v3h{i:02d}"), 1800)
            for i, n in enumerate(chunk_names)]
    infos = [f.result()[1] for f in futs]
hdr_paths = [last_saved(i) for i in infos]
log(f"HDR 1500: {len(hdr_paths)} chunks en {time.time()-t0:.0f}s")

final = D / "pvsg30_FINAL_HDR1500.mp4"
lst = D / "p30v3_concat.txt"
lst.write_text("".join(f"file '{p}'\n" for p in hdr_paths))
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
     "-i", str(D / "pvsg30_src.mp4"), "-map", "0:v:0", "-map", "1:a:0",
     "-c:v", "libx264", "-preset", "medium", "-crf", "13", "-pix_fmt", "yuv420p10le",
     "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc",
     "-color_range", "tv", "-r", "60", "-c:a", "aac", "-b:a", "192k",
     "-movflags", "+faststart", "-shortest", str(final)],
    check=True)
log(f"FINAL: {final.name} ({final.stat().st_size/1e6:.0f} MB)")
print("HDR1500_OK")
