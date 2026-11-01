# Speculative decoding method landscape — snapshot 2026-08-15

Research gathered during the "DFlash/DSpark for Qwen3.8-27B?" discussion. Re-verify before relying on it (fast-moving area).

## What llama.cpp upstream has (docs/speculative.md on master)
`--spec-type`: `draft`, `draft-simple`, `draft-eagle3`, `draft-dflash`, `draft-dspark`, `draft-mtp`, `ngram-cache`, `ngram-simple`, `ngram-map-k`, `ngram-map-k4v`, `ngram-mod`.
- MTP: heads baked into the target GGUF (e.g. unsloth `*-MTP` variants) — no separate file.
- DFlash/DSpark: separate draft GGUF via `-md`, plus `--spec-draft-n-max` = drafter's trained block size.

## DFlash
- llama.cpp: PR #22105 (lym000000, "spec: add DFlash support") merged; v2 refactor #24904 (ruixiang63: "much simpler and offers better graph reuse").
- Drafter availability pattern: `z-lab/Qwen3.6-27B-DFlash` published 2026-04-23 — **2 days** after `Qwen/Qwen3.6-27B` (2026-04-21); Qwen3.6-35B-A3B-DFlash on 2026-04-17 (pre-trained, before the base). Community GGUFs: spiritbuun, Anbeeld, Alittlehammmer (Q4_K_M/Q8_0).
- As of 2026-08-15: **no DFlash drafter exists for Qwen3.8-27B** (HF search "Qwen3.8 DFlash" = 0 hits). HF discussion #54 on the 27B repo asks exactly this.
- Vendor claims (z-lab/Modal, vLLM/SGLang, BF16/FP8, datacenter GPUs): up to 3.61x speedup at concurrency 1, 2.89x at concurrency 32, "higher throughput than MTP at every matched setting".

## DSpark
- DeepSeek's extension of DFlash: adds a semi-autoregressive Markov confidence head that dynamically chooses the number of draft tokens; trained with SpecForge. Vendor: macro acceptance length +27–31% over EAGLE3, +16–18% over DFlash; a 2-layer DSpark beats 5-layer DFlash (gain = dependency modeling, not params).
- llama.cpp: **PR #25173 merged 2026-07-28** (merged by ggerganov). Usage: `-m target.gguf -md dspark.gguf --spec-type draft-dspark --spec-draft-n-max <block_size> -ngld 99`.
- Qwen3.8-27B drafter: **RadixArk/Qwen3.8-27B-DSpark** (published 2026-08-14, 1 day after the base). 1.36B draft params, block size 7 (verify width 8), 5 full-attention layers, aux feature layers 4/16/28/40/52, trained against `Qwen3.8-27B-FP8` via SGLang. Macro acceptance 3.35 across 11 workloads (GSM8K 4.57 best, Arena-Hard-v2 2.71 worst; thinking on, temp 0.6/top-k 20/top-p 0.95, N=1164).
- GGUF: erlidev (BF16 2.73 GB / Q8_0 1.46 GB) + magnitudedev (for Magnitude). erlidev warning verbatim: "highly experimental… unable to get a speedup using DSpark so far. It is very memory hungry for some reason."
- Official docs example: DeepSeek's own `deepseek-ai/dspark_qwen3_4b_block7` → Qwen3-4B.

## Independent llama.cpp evidence (consumer hardware)
- ianlpaterson.com (RTX 3090 Ti, Qwen3.6-27B Q4_K_M, `-c 131072 -fa on -ctk q4_0 -ctv q4_0`): DFlash decode **46.9 → 30.1 tok/s** as output grew 100→2000 ("Decode Collapse"); MTP held **39–49 tok/s flat** across the same range and shipped in prod with `--spec-draft-n-max 6 --spec-draft-p-min 0.75` (the p-min filter, PR #22397, flipped MTP's verdict). Also: single-prompt vendor benchmarks overstate DFlash gains by 30–60%; `--reasoning-budget 256` saved ~10 s/request with no quality regression.
- hackmd.io full sweep (RTX 3090, Q4 targets): DFlash **−44.6% vs baseline** despite 100% acceptance (real, in `common/speculative.cpp`); regression attributed to MoE+hybrid path "not yet optimal" + Q4 target shifting hidden states vs the BF16 the drafter was trained on → drafter–verifier misalignment. That test's conclusion: no llama.cpp spec method gave positive yield on consumer Ampere with Q4 target.
- r/LocalLLaMA "DFlash support merged into llama.cpp": with default params on Qwen3.6-27b "13% faster overall"; coding-heavy workloads favor DFlash.

## Regime notes for Raúl's setup (RTX 5090, Qwen3.8-27B Q6_K, thinking xhigh, MTP+ngram n-max 3)
- Long reasoning outputs are exactly the regime where DFlash collapsed and MTP held — the current MTP+ngram config is the known-good baseline.
- Q6_K target is much closer to FP16/BF16 hidden states than Q4, so the drafter–verifier mismatch risk is lower here than in the negative tests — but untested.
- A/B protocol: llama-benchy, identical params both sides, LONG reasoning prompts (not vendor-style short prompts), verify acceptance/meanlen moved in the server log before claiming causality.

## Checking drafter availability + model cards (works without auth for public repos)
```python
import json, urllib.request, urllib.parse
def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':'hermes/1.0'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())

# existence of draft models:
get("https://huggingface.co/api/models?search=" + urllib.parse.quote("Qwen3.8 DFlash"))
# repo dates (timeline calibration — base vs draft createdAt):
get("https://huggingface.co/api/models/Qwen/Qwen3.8-27B")          # createdAt 2026-08-05 (repo), weights 08-14
get("https://huggingface.co/api/models/RadixArk/Qwen3.8-27B-DSpark")
# full model card (HTML tables parse fine; numbers are SELF-REPORTED — always say so):
urllib.request.urlopen("https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md")
```

## Sources
- https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- https://github.com/ggml-org/llama.cpp/discussions/21569 (DFlash discussion, #22105/#24904)
- https://github.com/ggml-org/llama.cpp/discussions/25167 + PR #25173 (DSpark)
- https://huggingface.co/RadixArk/Qwen3.8-27B-DSpark, erlidev/Qwen3.8-27B-DSpark-GGUF
- https://ianlpaterson.com/blog/3090-ti-qwen-speedup-dflash-mtp
- https://hackmd.io/ODXuOQNzSiyUITz7g9mtBw (spec-mode sweep, v3_dflash_2026_05_07)
- https://huggingface.co/Qwen/Qwen3.8-27B (model card), /discussions/54
- https://kaitchup.substack.com/p/qwen38-27b-nemotron-35-muse-deepseek (weekly, 2026-08-14)
