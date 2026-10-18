#!/usr/bin/env python3
"""SSIM dip-rule cut detection (metodo del skill: SSIM sobre 32x32, umbrales
0.60/0.62 calibrados con ese metodo). CPU, rapido."""
import sys
import cv2
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/workspace/rife/Practical-RIFE")
from model.pytorch_msssim import ssim_matlab

IN = "/root/workspace/dlss-ab/pvsg30_src.mp4"

def small(img):
    t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float().div(255.0)
    return F.interpolate(t, (32, 32), mode="bilinear", align_corners=False)

cap = cv2.VideoCapture(IN)
vals = []
prev = None
while True:
    ok, fr = cap.read()
    if not ok:
        break
    t = small(fr)
    if prev is not None:
        vals.append(float(ssim_matlab(prev, t).item()))
    prev = t

cuts = []
for i, v in enumerate(vals):  # vals[i] = ssim(frame i, frame i+1)
    lo = vals[i - 1] if i > 0 else 1.0
    hi = vals[i + 1] if i + 1 < len(vals) else 1.0
    if v < 0.60 and (lo > 0.62 or hi > 0.62):
        cuts.append(i + 1)
print(f"pares={len(vals)} cortes={len(cuts)}")
print("cut_frames:", cuts)
print("cut_seconds:", [round(c / 24.0, 4) for c in cuts])
dips = sorted((v, i) for i, v in enumerate(vals))[:12]
print("mayores dips (ssim, par):", [(round(v, 3), i) for v, i in dips])
with open("/root/workspace/dlss-ab/pvsg30_cuts.txt", "w") as f:
    for c in cuts:
        f.write(f"{c}\n")
