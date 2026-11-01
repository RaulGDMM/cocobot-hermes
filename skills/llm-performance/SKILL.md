---
name: llm-performance
description: "Complete LLM performance toolkit: inference optimization (speculative decoding, KV cache compression, quantization), intelligence benchmarking (GSM8K, HumanEval, ARC, HellaSwag, PIQA, PPL), and hardware-specific running configs for llama.cpp ecosystem."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [LLM, inference, benchmark, optimization, speculative-decoding, quantization, KV-cache, GGUF, llama.cpp, DFlash, NVFP4, TurboQuant, MTP, benchmarking, GSM8K, HumanEval]
    related_skills: [huggingface-hub, llama-cpp]
---

# LLM Performance — Optimization + Benchmarking

> Consolidated from `llm-inference-optimization` and `llm-intelligence-benchmark`.

Covers inference acceleration techniques (speculative decoding, KV cache compression, weight quantization) and intelligence benchmarking (GSM8K, HumanEval, ARC, HellaSwag, PIQA, Perplexity) against llama-server.

## Table of Contents

1. [Inference Optimization](#1-inference-optimization)
2. [Recommended Configurations](#2-recommended-configurations)
3. [Compatibility Matrix](#3-compatibility-matrix)
4. [Intelligence Benchmarking](#4-intelligence-benchmarking)
5. [Scripts](#5-scripts)
6. [Pitfalls](#6-pitfalls)

---

## 1. Inference Optimization

### Speculative Decoding

Replaces sequential autoregressive token generation with a draft-verify paradigm. A lightweight draft model proposes multiple tokens, and the target model verifies them in a single forward pass. Mathematically lossless — outputs identical at temp=0, distribution identical at temp>0.

**DFlash** (Z Lab, Feb 2026):
- Uses **block diffusion** for parallel drafting instead of autoregressive drafting
- Achieves >6x lossless acceleration; ~2.5x faster than EAGLE-3
- Models: `z-lab/Qwen3.6-27B-DFlash`, `z-lab/Qwen3.5-*-DFlash`
- **Backend support:** SGLang (full), vLLM v0.20.1+, MLX (Apple Silicon), BeeLlama.cpp (full), Transformers (limited)

**MTP (Multi-Token Prediction)**:
- Merged in llama.cpp main via PR #22673 (beta)
- Compatible with Qwen3.6 MTP GGUFs (e.g., `havenoammo/Qwen3.6-27B-MTP-UD-GGUF`)
- Use `--model-draft mtp-*.gguf --spec-type draft-mtp`
- **NVFP4 + MTP:** `LibertAIDAI/Qwen3.6-27B-NVFP4-MTP-GGUF` (Jun 2026) — benchmarked 74.4 → 90.8 tok/s (+22%) on RTX 5090

### KV Cache Compression

Reduces memory footprint of context memory at runtime.

**TurboQuant** (Google, ICLR 2026):
- Hadamard rotation + per-coordinate Lloyd-Max scalar quantization
- Keys: 3-bit (turbo3) or 4-bit (turbo4); Values: 2-4 bit
- ~4-5x compression vs FP16 with near-lossless quality
- **llama.cpp main:** PR #21089 open since early 2026 — NOT merged yet

**TCQ (Trellis-Coded Quantization):**
- Same idea as ADSL/VDSL modems — treats sequences as paths in a trellis graph
- **Critical at 2-3 bits:** `turbo2_tcq` quality close to 3-bit scalar, 10-44% KL reduction
- **Recommended:** `--cache-type-k turbo4 --cache-type-v turbo3_tcq`
- **macOS fallback:** use `turbo4` for K and `turbo3`/`turbo4` for V (TCQ not supported)

### Weight Quantization (GGUF)

**Standard GGUF:**
- `Q8_0` (~54GB for 27B) — highest quality
- `Q6_K` (~27GB) — very high quality
- `Q5_K_M` (~18GB) — best balance
- `Q4_K_M` (~15GB) — most popular
- `IQ4_XS` (~14GB) — compact

**NVFP4** (NVIDIA FP4):
- FP4 E2M1 weights, UE4M3 per-block scale (4.5 bits/element packed)
- **Blackwell (RTX 5090, sm_120):** native MMA tensor core acceleration. Prefill +43-68%
- **Ada (RTX 4090, sm_89):** falls back to dp4a/MMQ — size reduction only, NO speedup
- **Quality:** lands between Q3_K and Q4_0; PTQ GPTQ achieves 95-99% recovery
- **GGUF:** `LibertAIDAI/Qwen3.6-27B-NVFP4-MTP-GGUF` (best current option)
- See `references/nvfp4-status.md` for full ecosystem tracking

### llama.cpp Fork Comparison

See `references/llamacpp-forks-comparison.md` for comprehensive fork matrix (BeeLlama, TheTom, AtomicBot, spiritbuun) and non-llama.cpp alternatives (Genesis vLLM at 160-192 tok/s, qwen3.6-windows-server at 158 tok/s).

**Key:** Genesis vLLM patches are significantly faster than BeeLlama (~100 tok/s) but NEITHER supports vision. If multimodal required, BeeLlama remains most feature-complete.

---

## 2. Recommended Configurations

### RTX 5090 (32GB) — Qwen3.6-27B with DFlash + TurboQuant

```bash
./llama-server \
  -m Qwen3.6-27B-Q5_K_M.gguf \
  --mmproj mmproj-BF16.gguf \
  --spec-type dflash \
  --spec-draft-model Qwen3.6-27B-DFlash-Q4_K_M.gguf \
  --spec-draft-ngl all \
  --spec-dflash-cross-ctx 1024 \
  --ctx-size 122800 \
  --cache-type-k turbo4 \
  --cache-type-v turbo3_tcq \
  -b 2048 -ub 256 \
  -ngl all \
  --flash-attn on \
  --reasoning on \
  --port 8082
```

**VRAM:** ~18GB target + ~7GB draft + KV cache = 26-28GB total, ~100K-120K context

### Max Context (256K) with Checkpointing

```bash
./llama-server \
  -m Qwen3.6-27B-Q5_K_S.gguf \
  --mmproj mmproj-BF16.gguf \
  --no-mmproj-offload \
  --spec-type dflash \
  --spec-draft-model Qwen3.6-27B-DFlash-Q4_K_M.gguf \
  --spec-draft-ngl all \
  --spec-dflash-cross-ctx 1024 \
  --spec-draft-n-max 16 \
  --spec-dm-controller profit \
  --ctx-size 262144 \
  --cache-type-k turbo4 \
  --cache-type-v turbo3_tcq \
  --cache-ram 32768 \
  -b 2048 -ub 2048 \
  --checkpoint-every-n-tokens 8192 \
  -ngl all \
  --flash-attn on \
  --reasoning on \
  --port 8082
```

**Key flags:** `--cache-ram 32768` (32GB prompt cache), `--checkpoint-every-n-tokens 8192` (~32 checkpoints), `--no-mmproj-offload` (save VRAM for KV cache), `--spec-dm-controller profit` (adaptive draft depth).

See `references/beellama-256k-running-config.md` for full validated config.

---

## 3. Compatibility Matrix

### DFlash + KV Cache Quantization

| Backend | DFlash + TurboQuant/FP8 KV | Reason |
|---|---|---|
| **vLLM** | Incompatible | DFlash requires `causal=False`; all quantized KV backends reject non-causal |
| **BeeLlama.cpp** | Compatible | Drafter reads hidden states via eval callbacks |
| **SGLang** | Check version | DFlash integrated; KV quant compat depends on version |

### DFlash + Vision Models

| Backend | Vision Support | Status |
|---|---|---|
| **BeeLlama.cpp** | Flat DFlash with `--mmproj` | Fully working |
| **SGLang** | PR #18387 for Qwen3-VL | ~1.92x speedup on MMStar |
| **vLLM** | Unknown | Not confirmed for multimodal DFlash |

---

## 4. Intelligence Benchmarking

Evaluates **capability/intelligence** of models served via llama-server (not speed — for speed benchmarks see inference optimization). Measures mathematical reasoning, scientific knowledge, common sense, physical reasoning, and code generation.

### Running the Benchmark

```bash
python3 scripts/llm-intelligence-benchmark.py --host <HOST> --port <PORT> --model <MODEL>

# Example
python3 scripts/llm-intelligence-benchmark.py --host 172.23.176.1 --port 30000 --model qwen3.6-27b
```

### Benchmarks Included

| Benchmark | Samples | Evaluates | Parser |
|-----------|---------|-----------|--------|
| **GSM8K** | 51 | Mathematical reasoning | Last number or `boxed{}` |
| **ARC Easy** | 30 | Scientific reasoning | First letter A/B/C/D |
| **HellaSwag** | 30 | Common sense | Keyword in response |
| **PIQA** | 20 | Physical reasoning | "1" or "2" |
| **HumanEval** | 164 | Python programming (pass@1) | Execute code + assertions |
| **Perplexity** | WikiText-2 | Absolute model quality | Logprobs via `/completion` |

### Setup: HumanEval Dataset

```bash
mkdir -p ~/.hermes/skills/mlops/llm-performance/references
curl -sL "https://github.com/openai/human-eval/raw/master/data/HumanEval.jsonl.gz" | gunzip > ~/.hermes/skills/mlops/llm-performance/references/HumanEval.jsonl
```

### FP16 Baseline (Qwen3.6-27B paper)

| Benchmark | Score |
|-----------|-------|
| GSM8K | ~91% |
| ARC Challenge | ~70% |
| HellaSwag | ~80% |
| PIQA | ~80% |
| MMLU | ~85% |

### Statistical Variance

- **GSM8K (51 samples):** reliable for differences >2pp
- **HumanEval (164 samples):** reliable for differences >2pp
- **ARC/HellaSwag/PIQA (20-30):** only reliable for differences >10pp

See `references/q6k-vs-nvfp4-comparison.md` and `references/autoround-q6k-benchmark-20260612.md` for real benchmark data.

---

## 5. Scripts

- `scripts/dflash-benchmark.py` — **BROKEN:** missing tool calls, no speculative stats, short prompt truncates to 80 tokens. **DO NOT USE.**
- `~/.hermes/skills/.archive/llm-inference-benchmark/scripts/dflash-benchmark.py` — **WORKING version.** Full benchmark: text (short/medium/long) + tool calls + MTP acceptance stats. Saves JSON. Usage: `python3 ~/.hermes/skills/.archive/llm-inference-benchmark/scripts/dflash-benchmark.py --host 172.23.176.1 --port 30000 --runs 3 --max-tokens 512`
- `scripts/llm-intelligence-benchmark.py` — Full intelligence benchmark suite. Depends on `requests`.
- Benchmark tracking: `/mnt/e/Workspace/performance/benchmark-tracking.md` (historical comparison table, updated after each run)

---

## 3b. llama-benchy (HTTP client-side benchmark)

For OpenAI-compatible endpoint benchmarking from the client side (complements server-side `dflash-benchmark.py`):

```bash
uvx llama-benchy \
  --base-url http://172.23.176.1:30000/v1 \
  --model qwen3.6-27b \
  --tokenizer Qwen/Qwen3.6-27B \
  --pp 1024 4096 16384 \
  --tg 32 128 \
  --runs 3 \
  --format json \
  --save-result ~/.hermes/benchmarks/llama-benchy/$(date +%Y%m%d-%H%M%S).json
```

**Critical:** Always pass `--tokenizer Qwen/Qwen3.6-27B` — the gpt2 fallback gives wrong token counts.
Save results to `~/.hermes/benchmarks/llama-benchy/` for historical comparison.

**Do NOT benchmark a single-slot server that is actively serving a chat (e.g. the agent's own Hermes session running on it).** llama-server with `n_slots=1` queues bench requests behind live generation, so TG numbers come out ~10-15% low (observed 2026-08-15: llama-benchy 85-92 t/s vs 101.3 t/s median from the same server's `print_timing` log). For honest A/B, either run both measurements under identical serving conditions, or take the baseline while the server is idle, and cross-check with the server log's `slot print_timing` medians, which are ground truth.

## 4. Latency Diagnosis

Systematic approach for diagnosing high TTFT (Time To First Token) in local inference stacks:

1. **Direct server test** — measure TTFT from the inference server itself (bypasses Hermes gateway):
   ```python
   import urllib.request, json, time
   start = time.time()
   data = json.dumps({"model": "model-name", "prompt": "Test.", "max_tokens": 10}).encode()
   req = urllib.request.Request("http://HOST:PORT/v1/completions", data=data, headers={"Content-Type": "application/json"}, method="POST")
   with urllib.request.urlopen(req, timeout=60) as resp:
       json.loads(resp.read())
       print(f"TTFT: {time.time()-start:.2f}s")
   ```
2. **Multiple samples** — 3+ runs to detect variability (consistent = GPU bottleneck, variable = network/caching)
3. **Network path** — verify server location; WSL→host adds overhead
4. **Config review** — check `context_length`, `streaming.enabled`, `reasoning_effort` WITHOUT modifying

**Common bottlenecks:**
| Symptom | Cause | Fix |
|---------|-------|-----|
| TTFT > 2s | GPU underutilization | Increase `-b` batch |
| Variable TTFT | Network + caching | Colocate server |
| First slow, then fast | KV cache cold start | Pre-warm with dummy prompt |

**Rule:** Never modify config or restart services without explicit user permission.

## 3b. llama-benchy (HTTP client-side benchmark)

For OpenAI-compatible endpoint benchmarking from the client side (complements server-side `dflash-benchmark.py`):

```bash
uvx llama-benchy \
  --base-url http://172.23.176.1:30000/v1 \
  --model qwen3.6-27b \
  --tokenizer Qwen/Qwen3.6-27B \
  --pp 1024 4096 16384 \
  --tg 32 128 \
  --runs 3 \
  --format json \
  --save-result ~/.hermes/benchmarks/llama-benchy/$(date +%Y%m%d-%H%M%S).json
```

**Critical:** Always pass `--tokenizer Qwen/Qwen3.6-27B` — the gpt2 fallback gives wrong token counts.
Save results to `~/.hermes/benchmarks/llama-benchy/` for historical comparison.

**Do NOT benchmark a single-slot server that is actively serving a chat (e.g. the agent's own Hermes session running on it).** llama-server with `n_slots=1` queues bench requests behind live generation, so TG numbers come out ~10-15% low (observed 2026-08-15: llama-benchy 85-92 t/s vs 101.3 t/s median from the same server's `print_timing` log). For honest A/B, either run both measurements under identical serving conditions, or take the baseline while the server is idle, and cross-check with the server log's `slot print_timing` medians, which are ground truth.

## 4. Latency Diagnosis

Systematic approach for diagnosing high TTFT (Time To First Token) in local inference stacks:

1. **Direct server test** — measure TTFT from the inference server itself (bypasses Hermes gateway):
   ```python
   import urllib.request, json, time
   start = time.time()
   data = json.dumps({"model": "model-name", "prompt": "Test.", "max_tokens": 10}).encode()
   req = urllib.request.Request("http://HOST:PORT/v1/completions", data=data, headers={"Content-Type": "application/json"}, method="POST")
   with urllib.request.urlopen(req, timeout=60) as resp:
       json.loads(resp.read())
       print(f"TTFT: {time.time()-start:.2f}s")
   ```
2. **Multiple samples** — 3+ runs to detect variability (consistent = GPU bottleneck, variable = network/caching)
3. **Network path** — verify server location; WSL→host adds overhead
4. **Config review** — check `context_length`, `streaming.enabled`, `reasoning_effort` WITHOUT modifying

**Common bottlenecks:**
| Symptom | Cause | Fix |
|---------|-------|-----|
| TTFT > 2s | GPU underutilization | Increase `-b` batch |
| Variable TTFT | Network + caching | Colocate server |
| First slow, then fast | KV cache cold start | Pre-warm with dummy prompt |

**Rule:** Never modify config or restart services without explicit user permission.

## 6. Pitfalls

### Inference

- **DFlash suppressed by lazy grammar on tool calls:** Architectural limitation — lazy grammar enforces JSON schema token-by-token; DFlash generates blocks in parallel. DFlash still accelerates reasoning tokens (~80% of work) but NOT tool call tokens. Expected speedup with lazy grammar: ~1.3-1.6× total. **DO NOT use `--no-lazy-grammar` in agent systems.**
- **vLLM DFlash locks KV to BF16:** Non-causal attention requirement means no quantized KV cache. On 24GB GPUs, this halves effective context length.
- **Tree DFlash disabled with multimodal:** BeeLlama.cpp only allows flat DFlash when `--mmproj` is loaded.
- **Prompt cache with SWA models:** Qwen3.6 uses Sliding Window Attention — new prompts invalidate ALL checkpoints. Increase `--cache-ram` (32GB recommended).
- **NVFP4 GPU utilization ~75% vs 90%+ Q6_K:** Kernel immaturity — decode speed identical to Q6_K (memory-bandwidth bound). Prefill is the real win (+43-68%). GPU util will reach 85-90% with fused kernels.
- **NVFP4 hardware matters:** RTX 5090 IS Blackwell (sm_120) — full MMA acceleration. RTX 4090 is Ada (sm_89) — NO speedup over Q4_K_M.
- **llama.cpp main branch moves slowly:** TurboQuant PR #21089 open since early 2026. DFlash has no upstream PR. Expect main branch parity by Q4 2026.

### `--flash-attn` en llama.cpp

**NO es FA1 ni FA2 de Tri Dao.** Es una implementación propia de llama.cpp que sigue los principios de Flash Attention (tiling, online softmax, recomputación) con kernels CUDA escritos desde cero para inference con GGUF. Incorpora ideas de FA2 (cooperative matrix tiling, split-K parallelism) pero no usa la librería `flash-attention` de Dao-AILab. En la práctica, con `--flash-attn on` en una RTX 5090 (Blackwell) estás usando kernels optimizados con MMA de Tensor Cores.

### vLLM vs llama.cpp (2026) — Single User vs Multi-User

**Uso doméstico / single user:** llama.cpp gana claramente. Benchmark en Blackwell (modelos 8B-9B):
- **Decode speed:** llama.cpp 134-213 tok/s vs vLLM 83-89 tok/s (1.5-2.5x)
- **VRAM:** llama.cpp (Q4) ~35% menos que vLLM (BF16)
- **TTFT:** vLLM gana (33ms vs 129ms) — importa poco en conversación single-user
- **Prefill:** vLLM gana 3-4x (FlashAttention 2) — relevante solo para RAG con prompts enormes

**Multi-user / API serving:** vLLM domina. Con 4 usuarios concurrentes: 341 tok/s vs 123 tok/s (2.8x). PagedAttention + continuous batching es el diferenciador.

**Conclusión:** Para un solo usuario con GPU consumer, llama.cpp sigue siendo la opción más eficiente en VRAM y velocidad de decodificación.

### Benchmarking

- **`max_tokens` insufficient:** Models with thinking generate `reasoning_content` before `content`. **2000 tokens MINIMUM** for thinking models. Lower = truncation in reasoning → 0% scores.
- **HumanEval takes ~40+ min:** 164 samples × 2000 tokens. Use cron job one-shot or background with `notify_on_complete=true`.
- **HumanEval code extraction:** Qwen3.6 includes explanations before code. Use function anchor strategy (`def entry_point(`) — without it, ~20% fail with SyntaxError.
- **HumanEval dataset path:** Script looks for `references/HumanEval.jsonl` relative to its parent directory. If copying script elsewhere, adjust path or create symlink.
- **Foreground timeout 600s:** HumanEval exceeds hard timeout. Use cron job one-shot or run directly on the server machine.
- **Monitor long benchmarks with `process poll`, not cron:** When running intelligence benchmarks (especially HumanEval, ~40+ min), launch with `terminal(background=True, notify_on_complete=True)` then use `process(action='poll')` every ~10 min to check `/root/workspace/scripts/benchmarks/benchmark-progress.log` (los logs de benchmark viven en `scripts/benchmarks/` desde la reorganización de ago 2026; el script principal sigue en `/root/workspace/llm-intelligence-benchmark.py`). This is cleaner than a cron job and lets you see real-time progress.
- **Run benchmarks on the server machine:** Avoid WSL/remote timeouts and stdout buffering issues.
- **`dflash-benchmark.py` ngram cache contamination:** Running `--runs 3+` with identical prompts produces MASSIVELY inflated numbers on runs 2-3. The ngram draft cache learns the output pattern, so run 3 can be 3-5x faster than run 1 from cache alone — NOT from actual llama.cpp improvements. **ALWAYS use `--runs 1` for honest speed measurements.** Example: run 1 = 135 tok/s, run 2 = 243 tok/s, run 3 = 716 tok/s (same prompt).
- **Script uses server timings (fixed 2026-06-16):** The script was rewritten to use `timings.predicted_ms` from the server response, NOT client wall-clock. Before this fix, it reported 227-342 tok/s when the server showed 100.5 tok/s. The current version is correct.
- **Speculative stats NOT in API response:** Even with `timings_per_token: true`, the `/completion` endpoint does NOT populate `timings_per_token[].speculative` for MTP/ngram stats. The `spec_accepted/spec_attempted` fields in the response are empty. **The ONLY reliable source for speculative decoding stats is the server stdout logs** (`slot print_timing` and `statistics draft-mtp`). See `references/benchmark-methodology-pitfalls-20260616.md` for details.
- **Server logs are ground truth for speed:** When comparing llama.cpp versions, always check the server's `slot print_timing` logs (`eval time = X ms / Y tokens = Z tok/s`). These are more accurate than any API endpoint.
- **`/props` lies about MTP status:** `speculative.types` in `/props` reports `"none"` even when MTP IS active and running. This is a known discrepancy in llama.cpp's API. **ALWAYS verify with server logs** — grep for `draft-mtp` in the server stdout. If you see `statistics draft-mtp: #calls(b,g,a) = ...` lines, MTP is active regardless of what `/props` says. The user will know MTP is configured — trust them over `/props`.
- **Verify MTP/speculative status:** Check `speculative.types` in `/props` before interpreting results. MTP inactive (`"none"`) means you're measuring base decode speed, not MTP-accelerated. Previous benchmarks may have had MTP active — comparing base decode to MTP-accelerated numbers is comparing apples to oranges. **But see the pitfall above: `/props` may be wrong.**
- **MTP acceptance rate ≠ generation speed:** A llama.cpp update can improve MTP acceptance while degrading raw decode speed (observed 15/07: +17-25pp acceptance but -18-25% speed). Always benchmark BOTH — higher acceptance doesn't guarantee faster output if the base decode kernel regressed.
- **Broken dflash-benchmark.py in skill scripts:** The `scripts/dflash-benchmark.py` in this skill is broken — missing tool calls, no speculative stats, short prompt truncates to 80 tokens. **Always use the archived version:** `~/.hermes/skills/.archive/llm-inference-benchmark/scripts/dflash-benchmark.py` which has the complete benchmark (text + tool calls + MTP stats + JSON output).
- **llama.cpp source repo location:** `/mnt/e/Workspace/Openclaw/llama.cpp-src/`. Build at `build-cuda/bin/`. Check current version with `git log --oneline -1`. Backups of old `llama-server.exe` in `llama-cpp-backup-YYYY-MM-DD_HH-MM/` dirs.
- **BeeLlama binary location:** `/mnt/e/Workspace/Openclaw/beellama/bin/llama-server.exe` (server runs on PC Gaming at 172.23.176.1:30000).
- **Reasoning models eat token budget:** Models with `reasoning_content` (thinking blocks) consume most of `max_tokens` in reasoning before producing `content`. **Use `max_tokens=2048` MINIMUM** for benchmarks on thinking models. 256 tokens truncates reasoning → artificially low scores.
- **PPL ≠ intelligence:** Perplexity can be deceptively low (good) while reasoning is destroyed. NVFP4-Q8 had PPL 1.2470 (excellent) but scored 11% on reasoning benchmarks. PPL measures next-token prediction on fluent text, NOT reasoning ability. **Always benchmark reasoning tasks alongside PPL.**
- **NVFP4-Q8 without MTP is unusable:** Intelligence collapsed from 88.7% to 11% average. Only NVFP4 1f with MTP active is viable. See `references/nvfp4-q8-benchmark-20260717.md`.

### Quantization Comparison (Qwen3.6-27B, RTX 5090)

| Quantization | GSM8K | ARC Easy | HellaSwag | PIQA | Avg | HumanEval | PPL | Context |
|---|---|---|---|---|---|---|---|---|
| NVFP4 1f (michaelw9999) | 88.2% | 100% | 73.3% | 100% | 90.4% | 86.0% | 1.1050 | 260K |
| Q6_K | 88.2% | 100% | 63.3% | 100% | 87.9% | 85.4% | ? | 150K |
| AutoRound Q6_K (01/07) | 80.4% | 100% | 66.7% | 100% | 86.8% | 84.8% | 1.4440 | 160K |
| **AutoRound Q6_K (16/07)** | **86.3%** | **100%** | **66.7%** | **100%** | **88.2%** | **?** | **1.4629** | **160K** |
| **NVFP4-Q8 (no MTP, 17/07)** | **15.7%** | **10.0%** | **3.3%** | **15.0%** | **11.0%** | **?** | **1.2470** | **?** |

**Key change 16/07 vs 01/07:** GSM8K improved +5.9pp (80.4%→86.3%), closing the gap with NVFP4 1f. Last llama.cpp updates improved MTP precision at slight speed cost.

**⚠️ NVFP4-Q8 (no MTP) is UNUSABLE** — intelligence collapsed to 11% average (from 88.7% baseline). PPL was deceptively low (1.2470), masking the reasoning collapse. **Only NVFP4 1f with MTP is viable.** See `references/nvfp4-q8-benchmark-20260717.md`.

**Conclusion:** NVFP4 1f with MTP remains the best option — superior intelligence, speed, VRAM efficiency, and context vs alternatives. AutoRound Q6_K has improved significantly in math reasoning (16/07).

---

## References

- `references/nvfp4-status.md` — NVFP4 GGUF ecosystem tracking, QAT vs PTQ analysis, hardware matrix, MTP preservation
- `references/llamacpp-forks-comparison.md` — Fork comparison (BeeLlama, TheTom, etc.), TCQ explanation, non-llama.cpp alternatives
- `references/dflash-turboquant-compatibility.md` — vLLM incompatibility analysis, BeeLlama workaround
- `references/dflash-vision-support.md` — Qwen3-VL PR status, BeeLlama multimodal setup
- `references/beellama-256k-running-config.md` — Validated 256K context running config
- `references/qwen36-27b-gguf-options.md` — Available GGUF quantizations and VRAM tradeoffs
- `references/benchmarking.md` — How to benchmark D-Flash impact, measure TPS, ring buffer verification
- `references/humaneval-code-extraction.md` — 3-strategy code extraction workflow
- `references/humaneval-integration-notes.md` — HumanEval integration: extraction, execution, pitfalls
- `references/lm-eval-compatibility-notes.md` — lm-evaluation-harness compatibility issues
- `references/q6k-vs-nvfp4-comparison.md` — Real benchmark data: Q6_K vs NVFP4
- `references/autoround-q6k-benchmark-20260612.md` — AutoRound Q6_K benchmark results
- `references/kv-cache-q8q5-benchmark-20260617.md` — KV cache quantization (q8 K + q5_1 V) speed benchmark vs f16 baseline
- `references/nvfp4-1f-benchmark-20260529.md` — Full NVFP4 1f benchmark with context + vision
- `references/nvfp4-1f-update-20260530.md` — NVFP4 1f update confirms PPL + stable scores
- `references/nvfp4-quantization-comparison.md` — NVFP4 quantization approaches: ModelOpt vs per-tensor
- `references/nvfp4-community-research.md` — Community benchmarks, PPL, KLD from multiple sources
- `references/benchmark-methodology-pitfalls-20260616.md` — Critical pitfalls: ngram cache contamination, HTTP timing vs server timing, speculative stats not in API, server logs as ground truth
- `references/vllm-vs-llamacpp-comparison.md` — vLLM vs llama.cpp benchmarks (2026): single-user decode speed, VRAM efficiency, multi-user throughput, `--flash-attn` implementation details
