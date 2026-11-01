# Bartowski Q6_K_L — Intelligence Benchmark 30/07/2026

**Modelo:** `bartowski/Qwen3.6-27B-GGUF` → `Qwen3.6-27B-Q6_K_L.gguf`
**llama.cpp:** b10170 (updated from 16/07)
**Server:** <YOUR_LAN_IP>:30000 | **GPU:** RTX 5090
**Config:** MTP + ngram, KV cache K Q8_0 / V Q5_1, ctx 115K
**Carga del modelo:** ~3 min

## Results

| Benchmark | AutoRound Q6K (01/07) | AutoRound Q6K (16/07) | **Bartowski Q6K_L (30/07)** | NVFP4 1f (baseline) |
|-----------|----------------------|----------------------|---------------------------|---------------------|
| GSM8K (51 samples) | 80.4% | 86.3% | **86.3%** | 88.2% |
| ARC Easy (30) | 100.0% | 100.0% | **100.0%** | 100.0% |
| HellaSwag (30) | 66.7% | 66.7% | **66.7%** | 66.7% |
| PIQA (20) | 100.0% | 100.0% | **100.0%** | 100.0% |
| HumanEval (164) | 84.8% | — | **82.3%** | 86.0% |
| **Promedio** | **86.8%** | **88.2%** | **88.2%** | **90.4%** |
| PPL WikiText-2 | 1.4440 | 1.4629 | **1.4912** | 1.1255 |

**Tiempo total:** ~10 min (fast benchmarks) + ~30 min (HumanEval) + ~11 min (PPL)

## Speed (llama-benchy API)

| Metric | Value |
|--------|-------|
| PP 1024 | 2058 tok/s |
| PP 4096 | 2770 tok/s |
| PP 8192 | 2777 tok/s |
| TG 1024 | 100.6 tok/s (draft: 70%) |
| TG 4096 | 105.3 tok/s (draft: 72%) |
| TG 8192 | 108.0 tok/s (draft: 63%) |
| VRAM used | ~24.3 GB |

## Analysis

- **Bartowski Q6_K_L vs AutoRound Q6_K:** Essentially equivalent in most benchmarks.
  - GSM8K: 86.3% = 86.3% (identical to best AutoRound result)
  - ARC/PIQA: Perfect scores maintained
  - HellaSwag: 66.7% (same as all previous)
  - HumanEval: 82.3% vs 84.8% AutoRound (-2.5pp) — only metric where Bartowski loses
  - PPL: 1.4912 vs 1.4440 AutoRound — slightly worse but same ballpark
- **Context:** 115K vs 170K AutoRound — significant reduction, the main trade-off
- **VRAM:** 24.3 GB vs 30.6 GB AutoRound — Q6_K_L uses less VRAM despite "L" quantization
- **Speed:** Comparable to AutoRound (PP 2770 tok/s, TG 100-108 tok/s with MTP)
- **NVFP4 1f still leads** at 90.4% average, but Bartowski Q6_K_L is a strong alternative when 260K context isn't needed

## Verdict

Bartowski Q6_K_L is a solid Q6_K quantization that matches AutoRound Q6_K in reasoning benchmarks while using less VRAM (24.3 vs 30.6 GB). The 115K context limit is the main drawback. HumanEval is 2.5pp below AutoRound, possibly due to the different quantization recipe. For general use, it's comparable to AutoRound and a reasonable alternative.

## Raw data

- `/root/workspace/llm-eval-bartowski-q6kl-20260730.json` (full results)
- `/root/workspace/llm-eval-humaneval-bartowski-q6kl-20260730.json` (HumanEval details)
- `/root/workspace/benchmark-bartowski-q6kl-20260730.log` (fast benchmarks)
- `/root/workspace/benchmark-humaneval-bartowski-20260730.log` (HumanEval log)
- `/root/workspace/benchmark-bartowski-q6kl-part2-20260730.log` (PPL log)
