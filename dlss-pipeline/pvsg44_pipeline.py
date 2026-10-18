#!/usr/bin/env python3
"""Pipeline DLSS v2 sobre el master COMPLETO perros-vs-gatos_v44 (6574 f @24).

Pasos (retomables via pvsg44_state.json; volver a lanzar reanuda):
  0 CUTS   SSIM dip-rule -> cortes calibrados (CPU local)
  1 UP     upscale 3x (Ultra Performance) + NR preset M via broker
  2 SPLIT  partir master 4K24 por planos (local ffmpeg crf10)
  3 FG     DLSS FG 24->60 POR PLANO via broker (history reset por job)
  4 M60    concat FG + crop/scale -> master SDR60 intermedio
  5 HDR    RTXTrueHDR 1500 nits por chunks <=120f via broker (variante aprobada)
  6 FINAL  concat HDR + encode HDR10 10-bit bt2020/smpte2084 + audio de v44
"""
import json
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
SRC = Path("/root/workspace/perros vs gatos/montaje/perros-vs-gatos_v44.mp4")
FINAL = Path("/root/workspace/perros vs gatos/montaje/perros-vs-gatos_v44_4K_HDR60.mp4")
STATE = D / "pvsg44_state.json"
X = "\u00d7"
FPS = 24
CHUNK, NITS = 120, 1500  # variante HDR aprobada (hdr1500_run.py)
UP_TIMEOUT = 5400        # upscale master completo
FG_TIMEOUT = 5400        # FG por plano (cola del broker incluida)
HDR_TIMEOUT = 3600


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def st_load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def st_save(st):
    STATE.write_text(json.dumps(st, indent=1))


def last_saved(info):
    # los re-runs comparten prefijo: ComfyUI numera 00002, 00003...; elegir el
    # numero MAS ALTO (el de esta corrida), ignorando ecos de upload.
    import re as _re
    best = None
    for s in info["saved"]:
        if not isinstance(s, str) or s.startswith("DLFAIL") or "openclaw-upload" in s:
            continue
        m = _re.search(r"_(\d{5})_\.mp4$", s)
        if not m:
            continue
        num = int(m.group(1))
        if best is None or num > best[0]:
            best = (num, Path(s))
    if best:
        return best[1]
    raise RuntimeError(f"sin output util: {str(info)[:400]}")


def n_frames(path):
    return int(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip())


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


def step0_cuts(st):
    if "cut_frames" in st:
        log(f"CUTS: reanudando con {len(st['cut_frames'])} cortes")
        return
    import numpy as np
    import torch
    import torch.nn.functional as F
    sys.path.insert(0, "/root/workspace/rife/Practical-RIFE")
    from model.pytorch_msssim import ssim_matlab

    W = H = 32
    cap = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(SRC), "-vf", f"scale={W}:{H}:flags=bilinear",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, bufsize=W * H * 3 * 8)
    frbytes = W * H * 3

    def to_t(arr):
        return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).float().div(255.0)

    vals, prev, n = [], None, 0
    while True:
        buf = cap.stdout.read(frbytes)
        if len(buf) < frbytes:
            break
        t = to_t(np.frombuffer(buf, np.uint8).reshape(H, W, 3))
        # mismo pipeline que el metodo calibrado: interpolacion explicita a 32x32
        t = F.interpolate(t, (W, H), mode="bilinear", align_corners=False)
        if prev is not None:
            vals.append(float(ssim_matlab(prev, t).item()))
        prev = t
        n += 1
        if n % 1000 == 0:
            log(f"CUTS: {n} frames leidos")
    cap.stdout.close()
    cap.wait()
    cuts = []
    for i, v in enumerate(vals):
        lo = vals[i - 1] if i > 0 else 1.0
        hi = vals[i + 1] if i + 1 < len(vals) else 1.0
        if v < 0.60 and (lo > 0.62 or hi > 0.62):
            cuts.append(i + 1)
    log(f"CUTS: {n} frames, {len(cuts)} cortes")
    st["cut_frames"] = cuts
    st_save(st)


def step1_up(st):
    if "up_master" in st and Path(st["up_master"]).exists():
        log(f"UP: reanudando ({Path(st['up_master']).name})")
        return
    name = upload_file("http://172.23.176.1:8791", SRC)
    log(f"UP: subido {name}, lanzando upscale 3x+NR (preset M)")
    t0 = time.time()
    _, info = run_job("p44_up", upscale_wf(name, f"3{X} (Ultra Performance)", "dlssab/p44_up"), UP_TIMEOUT)
    up = last_saved(info)
    log(f"UP: {up.name} ({up.stat().st_size/1e9:.1f} GB) en {time.time()-t0:.0f}s")
    st["up_master"] = str(up)
    st_save(st)


def step2_split(st):
    up = Path(st["up_master"])
    total = n_frames(SRC)  # mismo nº de frames a 24 fps
    bounds = [0] + sorted(set(st["cut_frames"])) + [total]
    seg_paths = []
    if st.get("segs") and all(Path(p).exists() for p in st["segs"]):
        log(f"SPLIT: reanudando ({len(st['segs'])} segmentos)")
        return
    seg_paths = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        seg = D / f"p44_seg{i:02d}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{a/FPS:.6f}", "-to", f"{b/FPS:.6f}",
             "-i", str(up), "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
             "-pix_fmt", "yuv420p", "-an", str(seg)], check=True)
        seg_paths.append(str(seg))
    log(f"SPLIT: {len(seg_paths)} planos")
    st["segs"] = seg_paths
    st_save(st)


def step3_fg(st):
    segs = st["segs"]
    st.setdefault("fg", [None] * len(segs))
    todo = [i for i in range(len(segs)) if not (st["fg"][i] and Path(st["fg"][i]).exists())]
    log(f"FG: {len(todo)}/{len(segs)} planos pendientes")
    names = {}
    for i in todo:
        names[i] = upload_file("http://172.23.176.1:8791", Path(segs[i]))
        log(f"FG: subido plano {i}")

    def work(i):
        _n, info = run_job(f"p44fg{i:02d}", fg_wf(names[i], f"dlssab/p44fg{i:02d}"), FG_TIMEOUT)
        return i, str(last_saved(info))

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i, p in pool.map(work, todo):
            st["fg"][i] = p
            st_save(st)
            log(f"FG: plano {i} ok ({Path(p).name}) [{time.time()-t0:.0f}s]")


def step4_m60(st):
    m60 = D / "p44_m60sdr.mp4"
    if m60.exists() and st.get("m60_frames"):
        log(f"M60: reanudando ({st['m60_frames']} frames)")
        return
    lst = D / "p44_concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in st["fg"]))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", "crop=4032:2268:0:18,scale=3840:2160:flags=lanczos",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p",
         "-r", "60", str(m60)], check=True)
    st["m60"] = str(m60)
    st["m60_frames"] = n_frames(m60)
    st_save(st)
    log(f"M60: {m60.name} {st['m60_frames']} frames ({m60.stat().st_size/1e9:.1f} GB)")


def step5_hdr(st):
    m60 = Path(st["m60"])
    nframes = st["m60_frames"]
    nchunks = (nframes + CHUNK - 1) // CHUNK
    st.setdefault("hdr", [None] * nchunks)
    todo = [i for i in range(nchunks) if not (st["hdr"][i] and Path(st["hdr"][i]).exists())]
    log(f"HDR: {len(todo)}/{nchunks} chunks pendientes (1500 nits)")
    for i in todo:
        a = i * CHUNK
        ch = D / f"p44_ch{i:03d}.mp4"
        if not ch.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(m60),
                 "-vf", f"trim=start_frame={a}:end_frame={min(a+CHUNK, nframes)},setpts=PTS-STARTPTS",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p",
                 "-an", "-r", "60", str(ch)], check=True)
    names = {}
    for i in todo:
        names[i] = upload_file("http://172.23.176.1:8791", D / f"p44_ch{i:03d}.mp4")
        if i % 10 == 0:
            log(f"HDR: subido chunk {i}")

    def work(i):
        _n, info = run_job(f"p44h{i:03d}", hdr_wf(names[i], f"dlssab/p44h{i:03d}"), HDR_TIMEOUT)
        return i, str(last_saved(info))

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as pool:
        for i, p in pool.map(work, todo):
            st["hdr"][i] = p
            st_save(st)
            if i % 10 == 0:
                log(f"HDR: chunk {i} ok [{time.time()-t0:.0f}s]")
    log(f"HDR: {nchunks} chunks en {time.time()-t0:.0f}s")


def step6_final(st):
    if FINAL.exists():
        log(f"FINAL: ya existe {FINAL}")
        return
    lst = D / "p44_concat_hdr.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in st["hdr"]))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-i", str(SRC), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "medium", "-crf", "13", "-pix_fmt", "yuv420p10le",
         "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc",
         "-color_range", "tv", "-r", "60", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", "-shortest", str(FINAL)], check=True)
    log(f"FINAL: {FINAL} ({FINAL.stat().st_size/1e9:.2f} GB)")
    print("PIPELINE_FULL_OK", flush=True)


if __name__ == "__main__":
    only = set(sys.argv[1:])
    st = st_load()
    steps = [("cuts", step0_cuts), ("up", step1_up), ("split", step2_split),
             ("fg", step3_fg), ("m60", step4_m60), ("hdr", step5_hdr),
             ("final", step6_final)]
    t0 = time.time()
    for name, fn in steps:
        if only and name not in only:
            continue
        log(f"=== paso {name} ===")
        fn(st)
    log(f"pipeline completo en {(time.time()-t0)/60:.1f} min")
