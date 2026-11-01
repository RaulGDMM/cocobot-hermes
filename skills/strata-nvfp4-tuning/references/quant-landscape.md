# Flash-Next quant landscape on Strata — speed × precision × RAM

Source: Maximilian228/Qwen3.8-Flash-Next-NVFP4-GPTQ-Strata model card; its table was measured on a
9950X3D + 128 GB DDR5-5600 + RTX 5090 (Strata 0.1.42), greedy, MTP on, engine's own args per model.
Accuracy = % of tokens whose top-1 equals the Q8_0 pack's (5,153 mixed tokens, experts on CPU,
route-tail-skip off). GGUF rows run upstream's route-tail-skip by default: ~10% faster decode and
a little further from Q8_0 than the table shows. Note: the card's protocol differs from the fork's
`quant_quality.py` yardstick quoted in SKILL.md (e.g. UD-Q4_K_XL 94.1 vs 93.09) — use one protocol
consistently when comparing.

| pack | top-1 vs Q8_0 | decode (reference machine) | RAM in use / installed | on OUR 64 GB box |
|---|--:|--:|--:|---|
| Q8_0 (Maximilian228) | 100% (reference) | 47 t/s | 106 GiB / 128 GB | no install (setup gate) |
| NVFP4+Q8_0 mix | 95.0% | 91 t/s | 105 GiB / 128 GB | no install (setup gate) |
| Unsloth UD-Q4_K_XL | 94.1% | 169 t/s | 77 GiB / 96 GB | installs → RAM-budget mode, SSD-fed: 7-8.5 t/s |
| **NVFP4 GPTQ (ours)** | **93.6%** | 177 t/s | 69 GiB / 96 GB | low-RAM mode: **91-95 t/s measured** |
| NVIDIA NVFP4 | 92.9% | 167 t/s | 69 GiB / 96 GB | inferior quant (see SKILL, NVIDIA vs GPTQ) |
| Unsloth UD-Q3_K_XL | 90.7% | 208 t/s | 58 GiB / 96 GB | budget mode, SSD-bound |
| ISTA IQ3_S / IQ3_XXS / IQ2_XS / Q2_0 | 90.0 / 87.3 / 85.0 / 84.1% | 228-265 t/s | 37-52 GiB / 48-64 GB | fastest, worst accuracy |

Residency thresholds (setup ≥0.1.42-nvfp4.2): Unsloth GGUFs keep all experts in RAM only with ~16
GiB headroom → UD-Q4_K_XL needs ~88 GB installed; below that the RAM-budget mode streams experts
from the SSD — ~1.3-1.4 GB of expert bytes per token vs ~5-6 GB/s NVMe → single-digit t/s, an ~11x
collapse. The NVFP4 pack has a dedicated low-RAM mode that stays RAM-fed (~115 t/s theoretical at
64 GB on the reference CPU). Never compare a GGUF family's table speed against our low-RAM NVFP4
without checking which mode each side runs in.

## Extrapolating to this box (7800X3D 8c, 2×32 DDR5-4800)

MoE decode is bandwidth-bound → scale reference-table numbers by the platform factor: ≈0.79
(our GPTQ low-RAM 91 t/s vs 115 theoretical; bandwidth cap 4800/5600 = 0.86, 8 vs 16 cores covers
the rest). Examples (2026-10-24): mix ≈ 70-80, UD-Q4_K_XL full-resident ≈ 135-145, GPTQ in full-RAM
mode ≈ 140-150 t/s. Recompute the factor with the live probe (SKILL, 'Live decode probe') after
ANY hardware change — never reuse 0.79 blindly.

Remote hardware check (CPU/DIMM speed) from WSL:
`/root/.hermes/ssh-pc.sh "powershell -NoProfile -Command \"(gcim Win32_PhysicalMemory | select BankLabel,DeviceLocator,Capacity,Speed | format-table | out-string)\""`
PITFALL: avoid `$_`/`$PSItem` inside the ssh→powershell quoting chain — they survive as `\$` and
PS throws CommandNotFoundException; write $-free PowerShell: `(gcim X).Prop` or
`select ... | format-list | out-string`.

## Conclusions (state 2026-10-24)

- No published Strata quant beats NVFP4-GPTQ's accuracy at usable speed on 64 GB: the frontier is
  strictly monotonic, every higher-accuracy option needs 88-105 GiB resident. State RAM as the
  structural boundary of the analysis only — do NOT propose the purchase (Raúl's standing rule).
- hardhant/Qwen3.8-Flash-Next-FP4-Local-Strata (BF16 PLE, experts byte-identical to ours) is the
  only hidden accuracy candidate: no published top-1/KL vs Q8_0 and +47 GiB PLE — not a candidate
  without evidence.
- HF sweep 2026-10-24: 18 Strata repos exist for Flash-Next; the abliterated/uncensored ones are
  the same quants with refusal-direction edits — never treat them as accuracy upgrades. (HF
  models-search URL gotcha: `direction=-1` returns 400; plain `models?search=...` works.)
- Reevaluate this whole table on: RAM upgrade (then UD-Q4_K_XL ≈ +0.5 pp 'cheap', mix = +1.4 pp for
  ~half the speed), or Qwen4's release per the standing hold-until-Qwen4 decision.
