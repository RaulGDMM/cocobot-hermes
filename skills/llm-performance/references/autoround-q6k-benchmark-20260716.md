# AutoRound Q6_K — Intelligence Benchmark 16/07/2026

**llama.cpp:** b15ca938a (updated from 11/07)
**Server:** 172.23.176.1:30000 | **GPU:** RTX 5090
**Config:** MTP + ngram, KV cache K Q8_0 / V Q5_1, ctx 160K

## Results

| Benchmark | 01/07 | **16/07** | Cambio |
|-----------|-------|----------|--------|
| GSM8K (51 samples) | 80.4% | **86.3%** | 🟢 +5.9pp |
| ARC Easy (30) | 100.0% | 100.0% | ⚪ Igual |
| HellaSwag (30) | 66.7% | 66.7% | ⚪ Igual |
| PIQA (20) | 100.0% | 100.0% | ⚪ Igual |
| **Promedio** | **86.8%** | **88.2%** | 🟢 +1.4pp |
| PPL WikiText-2 | 1.4440 | 1.4629 | 🔴 +0.0189 |

HumanEval pending (user requested to run after fast benchmarks).

## Analysis

- **GSM8K improvement (+5.9pp)** is the standout result. AutoRound Q6_K was previously noted to penalize math reasoning vs NVFP4 (80.4% vs 88.2%). The 16/07 result (86.3%) nearly closes that gap.
- Other benchmarks stable — ARC/PIQA at 100%, HellaSwag at 66.7%.
- PPL slightly worse (1.44→1.46), but within variance.
- Consistent with speed benchmarks showing improved MTP acceptance rate (91.2% on short prompts) at slight decode speed cost.

## Methodology

Fast benchmarks run via wrapper script (`/root/workspace/run-fast-bench.py`) that imports `llm-intelligence-benchmark.py` modules directly, skipping HumanEval. This avoids the 40+ min HumanEval run when only checking quick benchmarks.

Raw log: `/root/workspace/fast-bench-20260716.log`
