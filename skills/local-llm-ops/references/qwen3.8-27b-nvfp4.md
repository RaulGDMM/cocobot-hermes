# Qwen3.8-27B NVFP4 options (state: Aug 2026)

Reference map for deciding NVFP4 vs Q6_K on a 32 GB RTX 5090 running llama.cpp.
Architecture: 64-layer dense, Gated DeltaNet (48 layers) + full attention (16 layers),
native 262K context (YaRN to ~1M), MTP head, native vision. Same shape as Qwen3.6-27B.

## Options

### 1. utautako/Qwen3.8-27B-NVFP4-MTP-Q8attn-GGUF — RECOMMENDED GGUF
- 17.81 GB (~5.60 BPW). NVFP4 MLP (self-quantized with NVIDIA ModelOpt, recipe
  `w4a16_nvfp4 / fp8_attn`, calibrated on cnn_dailymail). **Attention (q/k/v/o) AND
  DeltaNet projections (attn_qkv, attn_gate, ssm_out, ssm_alpha, ssm_beta) at Q8_0**
  — 308 tensors. MTP layer embedded (blk.64, Q6_K FFN + small Q4_K). F32 norms.
- Ships `mmproj-Qwen3.8-27B-NVFP4-BF16.gguf` (888 MiB) for vision.
- This is the first 3.8 GGUF that solves the 3.6 pitfall (linear_attn quantized
  down to NVFP4). "Capas importantes a alta precisión" — the layout Raúl wanted.
- Speed (author, RTX 5090, ngl 999, c=32768, KV q8_0): AR baseline 65-67 t/s;
  MTP n2 → 124 t/s (code) / 112 t/s (prose); n3 peaks ~129 t/s; draft-n ≥4 collapses.
- Context: author runs `-c 213056` text-only on a 32 GB 5090; `-c 163840` with mmproj.
- Real user reports (HF discussions, Aug 14-15 2026):
  - fuiru42 (DGX Spark): "works beautifully, ~20 t/s vs 15 t/s Q8_K"; found a metadata
    bug (llama-server reported it as Q4_K) — fixed and re-uploaded, now `ftype: NVFP4`.
  - kremerneil (LM Studio + OpenCode): only complaint = "overthinking pro max" —
    author confirms it is Qwen3.8's xhigh thinking, not the quant; suggests medium.
  - Reddit r/LocalLLM (thread 1vpfjzr, via search snippet only — Reddit data-blocked):
    "utautako's Q8attn model had higher draft acceptance in some tests, but was slower
    overall because the heavier layers made each verification [slower]" vs lighter
    NVFP4-everything tiers.
- No independent quality benchmark (Aider/KLD) published for the GGUF. Sample is thin:
  3.7k downloads, 9 likes, 2 days old at research time.

### 2. RadixArk/Qwen3.8-27B-NVFP4 — best VERIFIED quality, but NOT llama.cpp
- vLLM/SGLang-only (W4A4, group size 16; MLP + lm_head NVFP4, attention FP8,
  MTP/vision BF16). Validated on GB300; 30k downloads/month.
- Real quality benchmarks (4x B300 TP4 SGLang, thinking mode):
  - GSM8K: 97.27% (1283/1319)
  - Terminal-Bench 2.1: 73.81% pass@1 (84-task subset)
- SGLang day-0: 200+ tok/s decode on a single 5090 with DSpark spec (RadixArk/
  Qwen3.8-27B-DSpark). These numbers do NOT transfer to a llama.cpp GGUF.
- Cross-signal from Aider discord (r/LocalLLaMA, u/grumd): "someone ran NVFP4 qwen
  3.8 27B and got ~69%, I ran Q6_K_XL and got ~75%" — ~6pp behind Q6_K in code.

### 3. esatapedico/Qwen3.8-27B-NVFP4-MTP-GGUF — 8 tiers, attention in NVFP4
- Built from unsloth/Qwen3.8-27B-NVFP4 (mixed F8 + NVFP4 compressed-tensors).
- ORIG (33.13 GB): NVFP4 MLP + BF16 attention — source-faithful, doesn't fit 16 GB.
- **HIGHEST (23.19 GB, added 2026-08-18)**: source-faithful native NVFP4 MLP
  (layers 0-55, NOT re-quantized) + Q8_0 attention + Q8_0 lm_head + BF16 token_embd
  + BF16 MTP head. Best tier; author's answer to "FP8 attention" requests
  (FP8→Q8 = "better efficiency, nearly same accuracy" class).
- VERY-LOW/COMPACT-LOW/LOW/MEDIUM/HIGH/VERY-HIGH (14.9/14.1/15.5/16.4/17.6/19.7 GB):
  byte-identical 448-tensor NVFP4 backbone — ALL 64 layers' attention + MLP
  re-quantized to NVFP4 (second pass: F8→BF16→NVFP4 = precision loss exactly where
  it hurts most). Tiers differ only in lm_head / token_embd / MTP head ladder.
- Author states explicitly: "We did not run a proper benchmark."
- MTP embedded in every file; ships mmproj-BF16 (931 MB). 21k downloads/month.
- Likely faster decode than utautako (lighter layers) — the Reddit speed comparison
  suggests the Q8attn is the slower-but-more-accurate one of the two.
- Real user feedback (discussion #9, 2026-08-19): RTX5090 user tested 20+ NVFP4 GGUF
  variants, runs HIGH tier, "giving me the best results so far" (Qwen3.8 overthinking
  aside). Author considering building "COMPACT-VERY-HIGH" (Q8-centered, between HIGH
  and HIGHEST) on request.

## Conventional GGUF class (Q5/Q6) — quality floor

- **Q5_K_XL (unsloth UD-Q5_K_XL, 20.88 GB)**: ~2-4pp better than NVFP4 on Aider
  (anecdotal: Q6_K_XL ~75% vs NVFP4 ~69%); KLD class between Q4_0 and Q6.
- **Q6_K / Q6_K_XL (~22-23 GB)**: still the quality ceiling in the GGUF class —
  uniform 6-bit everywhere incl. DeltaNet (no FFN dropped to 4-bit). Aider ~75%
  (Q6_K_XL). ~5 GB heavier than utautako NVFP4 → less KV headroom (~8 GB → ~262K
  native vs ~500K for NVFP4). MTP works (Jackrong MTP-Q6_K 22.43 GB).
- Quality signal for this class: r/LocalLLaMA KLD study (Qwen3.6, same arch) ranked
  conventional GGUF Q5 as the sweet spot; NVFP4 W4A4 KLD substantially worse than
  size-matched Q4/Q5. Q5_K_M ≈ 97% of BF16 on 3.6 (PPL +0.15%).

### 4. unsloth/Qwen3.8-27B-NVFP4 (source, not a GGUF)
- Unsloth Dynamic V3.0 (preview): F8 group (attention, lm_head, MLP 56-63) +
  NVFP4 group (MLP 0-55). compressed-tensors — vLLM runtime; GGUF conversions derive
  from it. GGML has no F8 type, so any GGUF conversion dequantizes F8→BF16 (or
  re-quantizes) — that's why ORIG-style conversions balloon to 33 GB.

## Decision log

- **2026-08-19 — Qwen3.8-27B: stay on utautako NVFP4-Q8attn.** Raúl asked for same/smaller
  (and "a bit bigger OK") quants with better precision. Findings: esatapedico HIGHEST
  (23.2 GB, new 08-18) is the only meaningful up-grade but costs ~100k ctx (230k→~130k
  at his KV config K Q8_0/V Q5_1 + draft F16, mmproj, MTP n3) and its real gain over
  utautako is only late-FFN 56-63 + embeddings/MTP at higher precision (utautako's
  NVFP4 MLP is also ModelOpt-native from BF16, NOT a requant) → predicted suite
  tie. No AutoRound GGUF exists for 3.8 (all W4A16 vLLM-only; sphaela, who made the
  good Q6/Q8 AutoRound GGUFs for 3.6, has published nothing for 3.8 as of 08-19).
  User verdict: running model is fast, no perceived degradation → no switch.
  Revisit only if sphaela (or similar) ships a Q6/Q8 DeltaNet-aware AutoRound GGUF.
- Reference: unsloth docs confirm UD-Q4_K_XL/UD-Q5_K_XL as the recommended 4/5-bit
  GGUFs for 3.8; Q5_K_XL (20.88 GB) is the conventional sweet spot if one ever
  wants a non-NVFP4 fallback with MTP.

## Decision frame (5090 32 GB, current baseline Q6_K ~22.4 GB, KV K q8_0/V q5_1, MTP+ngram)
- KV grows only on the 16 full-attention layers → ~26 KB/token.
- Q6_K: ~8 GB KV headroom → ~262K (native ceiling). NVFP4 Q8attn (17.8 GB):
  ~12.5 GB headroom → ~500K+ (YaRN territory). NVFP4 is the ONLY path past 262K on
  one 5090.
- Benefits: MTP doubles decode (65→~124 t/s); prefill +43-68% with Blackwell NVFP4
  kernels (llama.cpp b8967+; PRs #21074, #22196, #21095 all merged by Jun 2026).
- Cost: ~6pp vs Q6_K on Aider (anecdotal); KLD of FFN-in-NVFP4 ≈ Q3/Q4 tier (3.6 data);
  community: "NVFP4 falls apart faster at higher context usage."
- Recommendation pattern: don't switch blind. A/B on the user's 5090 — Aider + one
  real Hermes task + perplexity/KLD vs the running Q6_K. Keep MTP on both.

## Verification techniques that worked (this session)
- HF discussions API: `curl -sL https://huggingface.co/api/models/<repo>/discussions?limit=20`
  (metadata only — no bodies), then `web_extract` on
  `https://huggingface.co/<repo>/discussions/<num>` for full comment text.
- HF model stats: `curl -sL https://huggingface.co/api/models/<repo>` → downloads/likes/dates.
- Reddit: ALL programmatic routes 403 (www .json, old.reddit .json, api.reddit.com,
  5 redlib mirrors, r.jina.ai). Only `web_search` snippets carry comment excerpts.
- `browser_exec` failed (no Chromium in the WSL harness at the time) — do not rely
  on it for blocked sites; try the data routes above first.
