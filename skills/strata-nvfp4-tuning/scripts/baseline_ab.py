#!/usr/bin/env python3
"""Strata warm-baseline / A-B de especulacion.
Corta strata.log por periodo (anclas `[strata] <fecha hora> engine started`),
filtra decodes >= --min-gen tokens, y agrupa por banda de profundidad de
contexto: n, mediana t/s, p25/p75 y aceptacion de drafts (sumA/sumB).
Uso:
  python3 baseline_ab.py --label "orca T1.0" --pre-anchor --tail 600
  python3 baseline_ab.py --label "gptq calido" --from "2026-10-18 00:00"
A-B: correr con la config actual (baseline) y tras el reinicio con el flag,
mismo ancla --from; comparar medianas por banda 32-80K / 80-140K en cálido.
"""
import argparse, re, statistics as st

ANCHOR = re.compile(r"\[strata\] (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) engine started: .*?--pack models/([a-z0-9\-]+)/pack")
DEC = re.compile(r"prompt (\d+) tokens = .*? (\d+) generated in \d+ ms \(([\d.]+) tok/s\), drafts accepted (\d+) of (\d+)")
SUF = re.compile(r"suffix drafts: (\d+) windows, (\d+) of (\d+) drafts accepted")
BANDS = [(0, 8000, "<8K"), (8000, 32000, "8-32K"), (32000, 80000, "32-80K"),
         (80000, 140000, "80-140K"), (140000, 10**9, ">=140K")]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="/mnt/e/Workspace/Openclaw/strata-nvfp4/strata-nvfp4/strata.log")
    ap.add_argument("--label", default="")
    ap.add_argument("--from", dest="tfrom", default=None)
    ap.add_argument("--to", dest="tto", default=None)
    ap.add_argument("--pre-anchor", action="store_true", help="filas anteriores a la primera ancla (era previa al pack actual)")
    ap.add_argument("--tail", type=int, default=0, help="usar solo las ultimas N filas del filtro")
    ap.add_argument("--min-gen", type=int, default=48)
    a = ap.parse_args()

    rows, suf, cur = [], {}, None
    for line in open(a.log, encoding="utf-8", errors="replace"):
        m = ANCHOR.search(line)
        if m:
            cur = m.group(1); continue
        m = DEC.search(line)
        if m and int(m.group(2)) >= a.min_gen:
            rows.append((cur, int(m.group(1)), float(m.group(3)), int(m.group(4)), int(m.group(5))))
            continue
        m = SUF.search(line)
        if m and cur is not None:
            if cur not in suf or int(m.group(1)) > suf[cur][0]:
                suf[cur] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    if a.pre_anchor:
        rows = [r for r in rows if r[0] is None]
        suf = {}
    else:
        rows = [r for r in rows if r[0]]
        if a.tfrom: rows = [r for r in rows if r[0] >= a.tfrom]
        if a.tto:   rows = [r for r in rows if r[0] <= a.tto]
        suf = {k: v for k, v in suf.items()
               if (not a.tfrom or k >= a.tfrom) and (not a.tto or k <= a.tto)}
    if a.tail:
        rows = rows[-a.tail:]

    print(f"== {a.label}  n={len(rows)} ==")
    print(f"{'banda':<9}{'n':>6}{'mediana':>9}{'p25':>7}{'p75':>7}{'acept%':>8}")
    for lo, hi, name in BANDS:
        b = [r for r in rows if lo <= r[1] < hi]
        if not b: continue
        v = sorted(x[2] for x in b)
        acc = 100.0 * sum(x[3] for x in b) / max(1, sum(x[4] for x in b))
        print(f"{name:<9}{len(b):>6}{st.median(v):>9.1f}{v[len(v)//4]:>7.1f}{v[min(len(v)-1,3*len(v)//4)]:>7.1f}{acc:>8.1f}")
    if rows:
        acc = 100.0 * sum(x[3] for x in rows) / max(1, sum(x[4] for x in rows))
        print(f"TOTAL    {len(rows):>6}{st.median(sorted(x[2] for x in rows)):>9.1f}{'':>14}{acc:>8.1f}")
    if suf:
        w = sum(v[0] for v in suf.values()); ac = sum(v[1] for v in suf.values()); t = sum(v[2] for v in suf.values())
        print(f"suffix drafts (max por periodo): {w} windows, {ac}/{t} aceptados ({100.0*ac/max(1,t):.1f}%)")

if __name__ == "__main__":
    main()
