# NVFP4-Q8 Benchmark — 2026-07-17

**CRITICAL FINDING: NVFP4-Q8 (without MTP) is NOT USEABLE for reasoning tasks.**

## Results

| Benchmark | NVFP4-Q8 | Q6_K AutoR (baseline) | Δ |
|-----------|----------|----------------------|-----|
| GSM8K | **15.7%** | 88.2% | **-72.5** |
| ARC Easy | **10.0%** | 100% | **-90.0** |
| HellaSwag | **3.3%** | 66.7% | **-63.4** |
| PIQA | **15.0%** | 100% | **-85.0** |
| **Average** | **11.0%** | **88.7%** | **-77.7** |
| PPL WikiText-2 | **1.2470** | — | — |

⏱️ Total: 563s, max_tokens=2048, server temperature

## Key Observations

- **PPL is deceptively low (1.2470)** — perplexity measures next-token prediction on fluent text, NOT reasoning ability. A model can have great PPL and still be functionally useless for reasoning.
- **Reasoning/thinking models require high max_tokens** — initial test with 256 tokens truncated reasoning content. Re-ran with 2048 tokens — same terrible results, confirming the problem is the quant, not token limits.
- **NVFP4-Q8 ≠ NVFP4 1f** — the NVFP4 1f quant (michaelw9999) with MTP scores 90.4% average. This NVFP4-Q8 (no MTP) scores 11%. The difference is MTP + the specific quant recipe.
- **Do NOT deploy NVFP4-Q8 without MTP** — the quant destroys the model's reasoning capability entirely.

## Conclusion

NVFP4-Q8 without MTP is **inusable**. The only viable NVFP4 option is NVFP4 1f with MTP active.
