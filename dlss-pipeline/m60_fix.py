#!/usr/bin/env python3
"""Re-montaje m60 con recorte por plano a la rejilla global 60fps.

Causa del drift: FG redondea CADA plano impar hacia arriba (+0.5f), acumula
+13f (217 ms) al final -> desajuste labial en la 2a mitad.
Fix: longitud objetivo del plano i = R(b_{i+1}) - R(b_i), R(x)=floor(x+.5);
asi la deriva acumulada en todo corte es |deriva| <= 0.5f (8 ms) y el total
telescopa a R(6574*2.5)=16435 exacto. Se recorta el ultimo frame de los
planos recortados (inmediatamente antes de un corte duro: imperceptible).
Si algun objetivo supera al plano actual, se duplica el ultimo frame.
Tras montar: actualiza estado, borra chunks HDR antiguos y el FINAL viejo.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

D = Path("/root/workspace/dlss-ab")
STATE = D / "pvsg44_state.json"
M60 = D / "p44_m60sdr.mp4"
TOTAL24 = 6574
FINAL = Path("/root/workspace/perros vs gatos/montaje/perros-vs-gatos_v44_4K_HDR60.mp4")


def nbf(p):
    return int(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True).stdout.strip())


def R(x):
    return math.floor(x + 0.5)


st = json.loads(STATE.read_text())
bounds = [0] + sorted(set(st["cut_frames"])) + [TOTAL24]
targets, trims = [], []
for i in range(len(bounds) - 1):
    t = R(bounds[i + 1] * 2.5) - R(bounds[i] * 2.5)
    m = nbf(st["fg"][i])
    targets.append(t)
    if t != m:
        trims.append((i, m, t))
        assert 0 < t, f"plano {i} objetivo {t}"
    if t > m:
        print(f"AVISO: plano {i} necesita {t} > {m} (se duplicara frame final)", flush=True)
print("planos ajustados:", [(i, m, t) for i, m, t in trims], flush=True)

# filtro: por entrada [i] (dup ultima si hace falta) -> trim end_frame=t
parts, cat = [], ""
for i, t in enumerate(targets):
    lab = f"v{i}"
    if targets[i] > nbf(st["fg"][i]):  # duplicar ultimo frame para alcanzar t
        parts.append(
            f"[{i}:v]split[s{i}];[s{i}]trim=end_frame=1,setpts=0[d{i}];"
            f"[{i}:v][d{i}]concat=n=2:v=1:a=0,trim=end_frame={t},"
            f"setpts=PTS-STARTPTS[{lab}]")
    else:
        parts.append(f"[{i}:v]trim=end_frame={t},setpts=PTS-STARTPTS[{lab}]")
    cat += f"[{lab}]"
n_in = len(targets)
parts.append(f"{cat}concat=n={n_in}:v=1:a=0,crop=4032:2268:0:18,"
             f"scale=3840:2160:flags=lanczos[out]")

cmd = ["ffmpeg", "-y", "-v", "error"]
for p in st["fg"]:
    cmd += ["-i", p]
cmd += ["-filter_complex", ";".join(parts), "-map", "[out]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
        "-pix_fmt", "yuv420p", "-r", "60", str(M60)]
print("montando m60 corregido...", flush=True)
subprocess.run(cmd, check=True)

n = nbf(M60)
assert n == 16435, f"m60 tiene {n} frames, esperado 16435"
print(f"m60 OK: {n} frames ({M60.stat().st_size/1e9:.1f} GB)", flush=True)

# estado + limpieza para reHDR
st["m60"] = str(M60)
st["m60_frames"] = n
nchunks = (n + 119) // 120
st["hdr"] = [None] * nchunks
STATE.write_text(json.dumps(st, indent=1))
for ch in D.glob("p44_ch*.mp4"):
    ch.unlink()
if FINAL.exists():
    FINAL.unlink()
print(f"estado listo para HDR ({nchunks} chunks); FINAL viejo eliminado", flush=True)
