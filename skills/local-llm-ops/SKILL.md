---
name: local-llm-ops
description: Operate & tune a local llama.cpp server for Hermes.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [local-llm, llama.cpp, speculative-decoding, MTP, reasoning-effort, quantization, nvfp4, long-context, edge-inference, auxiliary, video-input, mtmd, tuning]
    related_skills: [llama-cpp, llm-performance, llm-intelligence-suite]
---

# Local LLM Operations (llama.cpp)

Class skill for **operating and tuning a local llama.cpp inference server that Hermes talks to**. It sits on top of the `llama-cpp` skill (which covers *running* the server + HuggingFace model discovery) and pairs with `llm-performance` (the full speed/benchmarking toolkit: llama-benchy, intelligence suites).

Pick the subsection by what you are doing:

| You want to… | Section |
|---|---|
| Make it faster (MTP / ngram / n-max / temp) | [Speculative decoding & sampling](#1-speculative-decoding--sampling-tuning) |
| Control how much it thinks (reasoning effort) | [Thinking / reasoning effort](#2-thinking--reasoning-effort-control) |
| Decide if a new quant is worth switching to | [Quantization evaluation & verification](#3-quantization-evaluation--verification) |
| Check it doesn't degrade on long context | [Long-context degradation testing](#4-long-context-degradation-testing) |
| Offload auxiliary tasks to a Pi / mini PC | [Edge / auxiliary deployment](#5-edge--auxiliary-deployment) |
| Fix `input_video` hanging on a Windows server | [Windows video input (mtmd) workaround](#6-windows-video-input-mtmd-workaround) |
| Audit a non-llama.cpp engine (Strata NVFP4) for headroom | [Other engines: Strata NVFP4](#7-other-engines-strata-nvfp4) |
| Toggle a model's refusals (uncensor) without weight surgery | [Control vectors (uncensor toggle)](#8-control-vectors-uncensor-toggle) |

Cross-cutting rules:
- **Parse .ps1 launchers with the real parser before asking the user to restart.** (2026-09-21: an edit of the `--parallel` block in start-hermes.ps1 left a duplicated `} else {`; a manual brace-balance check passed, but the user hit a parse error on restart.) Validate with `[System.Management.Automation.Language.Parser]::ParseFile` via Windows PowerShell (`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe` from WSL — `pwsh`/PS7 is NOT installed). PS 5.1 has no `ElseClauseAst` type (only `IfStatementAst`), so keep the validator to ParseFile errors + token brace balance (count `@{` as open). Note: a stray `else` after a complete `if { } else { }` statement only errors on THAT statement and the rest of the script keeps running — the launched process can still be correct; verify its real CommandLine (`Get-CimInstance Win32_Process`) before assuming the restart was bad.
- **The server log is ground truth.** Grep it before trusting `/props`, `/health`, or any client-side metric.
- **Absence of an expected log line is NOT proof a feature is off.** A missing line usually means the code branch that prints it never ran (different memory mode, different engine path), not that the feature failed. Run the feature's own read-only state check and grep the binary's strings for the message to find its real branch before asserting a negative.
- **Report throughput bucketed by context length, never as one median.** Short-context runs are cold and slow, long-context runs warm and fast; pooling them invents a variance story. Median/p25/p90 per bucket, filtering to generations ≥100 tokens.
- **A/B everything with identical params both sides**, and confirm the *mechanism* moved in the log before claiming causality.
- **Published/vendor numbers don't transfer** to your GPU + KV config + workload. Verify on the user's hardware.
- **Never restart a server that is serving the live conversation** without the user's OK.

---

## 1. Speculative decoding & sampling tuning

**When:** user says the local model "feels slow"; you're about to change `--spec-draft-n-max`, `--temp`, `ubatch`, or `reasoning_effort`; you need to *prove* a change helped.

**Workflow**
1. **Diagnose from the server log first** (ground truth):
   ```bash
   grep -oE "draft acceptance = [0-9.]+ +\([0-9]+ accepted / +[0-9]+ generated\)(, mean len =  ?[0-9.]+)?" llama-server.log | tail -8
   grep -oE "mean len =  ?[0-9.]+?" llama-server.log | tail -10 | sort | uniq -c
   ```
   Bucket tok/s by context length (<10k / 10–20k / 50–100k) from `slot print_timing` — long-context slowdowns are usually **KV-cache bound, not spec-decoding bound**.
2. **Rank levers by cost/risk** (typical order for a slow *thinking* model):
   - `--spec-draft-n-max` — free speed, **zero quality impact** (speculative decoding is distribution-identical).
   - `--temp` — quality-relevant (see pitfall 1).
   - `ubatch` — prefill/TTFT only.
   - `reasoning_effort` — biggest real-world latency lever, but degrades depth (present as a trade-off, don't default it).
   - Quant change (NVFP4 etc.) — needs a model download + separate approval.
3. **Verify vendor-recommended sampling before recommending any temperature.** Thinking-only models have their own recommended temp (Qwen3.8 thinking-only: `temp=1.0, top_p=0.95, top_k=20`) that differs from non-thinking mode (0.6). Fetch the vendor doc; never cite a "range" from memory.
4. **Baseline first** with the `llm-performance` llama-benchy protocol, identical params both sides.
5. Apply to the **launch script** (single source of truth for env → CLI args); confirm the var actually flows to the `--flag` line.
6. Let the user restart if they own restarts.
7. **Verify the new args on the running process** after restart (Windows: `Get-CimInstance Win32_Process` + CommandLine filter; the `/props` endpoint can *lie* about spec status).
8. Re-run the identical benchmark, compare deltas, **and confirm the mechanism moved in the log** (n-max 2→3 should raise `mean len` ~2.5 → ~3.0; if not, the delta is noise).
9. Save both JSONs to `~/.hermes/benchmarks/llama-benchy/` with descriptive names.

**Pitfalls**
1. **Never recommend a non-default temperature from memory.** (2026-08-15: recommended temp 0.8 for Qwen3.8 from an unverified "0.6–1.0 range", conflating non-thinking 0.6 with thinking-only; user pushed back, official is 1.0. Reverted.) Fetch the doc for the exact model *and mode*; state the source.
2. **Attribute speed gains to the right lever.** The +7.3% TG came from n-max 2→3 (meanlen 2.5→3.0 in log), *not* the temp change. When two levers change at once, confirm each mechanism independently in the log.
3. **n-max is acceptance-dependent.** The 3rd draft token only pays off if acceptance is high (Qwen3.8: 65% at n-max 2). On low-acceptance models, n-max 3 wastes verify compute → wash or regression. Check acceptance/meanlen before & after.
4. **Single-slot live-server benchmarks run ~10–15% low** (bench requests queue behind live chat). Fine for A/B (same condition both sides), never for absolute claims.
5. **Caching inflates specific A/B cells** (repeated prompts feed the ngram draft cache). Report the mean; a couple of flat/losing cells while the mean moves is expected.
6. **Env-var wiring must be verified, not assumed** — grep the arg-construction lines before telling the user "it will apply on restart".

**Comparing spec methods (DFlash vs DSpark vs MTP):** vendor speedups are measured in *their* world (datacenter GPUs, BF16/FP8, short prompts, vLLM). Independent llama.cpp data on consumer hardware contradicts them for long outputs (DFlash decode collapsed 47→30 tok/s from 100→2000 tokens; MTP held 39–49). Check the drafter's trained target precision vs your quant (Q4 targets broke drafter-verify alignment; Q6_K is safer) and test with **long reasoning** prompts. Availability: HF API works without auth — `huggingface.co/api/models?search=...` for existence, `api/models/<repo>` `createdAt` for "how fast did the drafter follow the base model".

**DFlash2 + multimodal (mmproj) — known bug, NOT fixed upstream (verified 2026-09-01, latest release b10740).** With `--spec-type draft-dflash` + `--mmproj`, image requests break the 1-D draft KV cache (all image embedding rows land on a single position → positional hole → `llama_decode(ctx_dft)` rc=-1 → HTTP 500 / ~500 s stall on CUDA, fast fail on Vulkan). Text-only requests spec normally. Upstream [#27408](https://github.com/ggml-org/llama.cpp/issues/27408) is open; the complete fix PR [#27914](https://github.com/ggml-org/llama.cpp/pulls/27914) (3 surgical edits in `common/speculative.cpp`) was **closed unmerged** after a maintainer claimed "already fixed, reconvert your GGUF" — refuted by community confirmation of 0.0 draft acceptance on a fresh build (2026-08-30). Only working fix today lives in a Volta-oriented fork (`fishlikeX/sm70-attn`) — not a suitable base for Blackwell. Consequence: DFlash2 stays strictly better than MTP on **text-only** Qwen3.8-27B, but with images it degrades to ~baseline (our earlier measurement: acceptance ~1.8%, 27–43 tok/s) while MTP is unaffected — keep `qwen38_27b_unsloth_q6k_mtp` as default until a proper upstream fix lands. Full detail + monitor recipe: `references/dflash2-mtmd-bug-20260901.md`.

Deep dives (moved here): `references/spec-methods-2026-08.md` (landscape + independent evidence), `references/qwen38-nmax3-ab-20260815.md` (full A/B, log excerpts, final config).

---

## 2. Thinking / reasoning effort control

**When:** user wants to tune how much a local model thinks (depth/latency), or an agent framework's reasoning setting appears to do nothing.

**Core principle:** reasoning effort is a **chat-template feature**, not an OpenAI API field. It only works when the serving engine passes it into the model's Jinja template via `chat_template_kwargs` (llama.cpp) or an equivalent (vLLM `--reasoning-parser`). Models not trained with effort levels ignore or error on it.

**Per-server mechanics**
- **llama-server:** server default → `--chat-template-kwargs '{"enable_thinking":true,"reasoning_effort":"medium"}'` (or env `LLAMA_CHAT_TEMPLATE_KWARGS`, or `--reasoning-effort medium`; needs `--jinja`, restart). Per-request → add `"chat_template_kwargs": {"reasoning_effort":"low"}` to the body (llama-server forwards non-standard kwargs). **Hard off:** `{"enable_thinking": false}` is more robust than `reasoning_effort:"off"`. **Only valid level names work** — Qwen3.8-27B UD-Q6_K (2026-09-01, live probe) accepts `xhigh/high/medium/low`; `max/ultra/none/minimal` → HTTP 500 Jinja exception on EVERY request (server stays healthy; see `references/hermes-llama-cpp-reasoning-gap.md`). NOTE: the template's own error message underreports its accepted set (it says only `xhigh, medium, low`) — probe each level with one real request and check the response, never trust the error text.
- **vLLM:** top-level `reasoning_effort` in body; with `--reasoning-parser qwen3` it injects `enable_thinking` (`none`→off, else on). Server default: `--default-chat-template-kwargs '{"enable_thinking": false}'`.
- **Ollama:** **replaces the model's own template** with a generic one, so template-side effort settings are lost. You cannot turn thinking down through Ollama for Qwen3.8. Use llama-server with `--jinja` instead.

**Agent frameworks — the silent dead-end trap.** In Hermes (verified in source 2026-08-19): `agent.reasoning_effort` in config and `/reasoning [level]` only matter when the transport emits a reasoning field. The gate is `run_agent.py::AIAgent._supports_reasoning_extra_body()`:
- OpenRouter, GitHub Models, LM Studio, Ollama Cloud → emitted (works).
- **`provider: custom:*` (local llama-server) → returns False; nothing sent.** No error — silently ignored.
So "effort set in config" ≠ "effort active". For a local llama-server the real source is the launcher's `LLAMA_CHAT_TEMPLATE_KWARGS` / `--chat-template-kwargs`. To make a live framework toggle work, the request needs per-call `chat_template_kwargs` injection — see `references/hermes-llama-cpp-reasoning-gap.md` (source findings, measured Qwen3.8 latencies, analyzed fix options).

**Pitfalls**
1. **Wrong level name** → template errors every request; server looks healthy. Check the model's exact accepted set first.
2. **Ollama as middleman** → template control lost entirely.
3. **Framework setting as source of truth** → verify with one real request (measure thinking token count / latency change) before trusting any "effort" config.
4. **Global default lives server-side**, not in the agent — other clients (OpenWebUI, curl, cron) keep the server default.
5. **Shorter thinking is also faster per token** — the MTP/draft head predicts short direct answers better than long reasoning; latency gains compound.
6. **Stale launcher copies** — in WSL-clone vs real-Windows-script setups, confirm which launcher is actually running before editing.

---

## 3. Quantization evaluation & verification

**When:** "is there a version worth trying / is X better than what I'm running"; choosing between quants (Q6_K vs NVFP4) on a specific GPU; user wants "benchmarks verificados / bien probado" (real evidence, not publisher claims).

**Workflow**
1. **Map the landscape — format ecosystems differ.** GGUF (`.gguf`) runs in llama.cpp. modelopt / compressed-tensors (`model.safetensors` + `config.json`) is vLLM/SGLang-only — **NOT loadable in llama.cpp**. A repo named "X-NVFP4" can be either — check the actual files. An NVFP4 vLLM checkpoint's real quality benchmarks do NOT transfer if the user runs llama.cpp. **Match the runtime first.**
2. **Separate speed benchmarks from quality benchmarks** (the key step). Author-published NVFP4 GGUF numbers are usually **speed only** (tok/s, MTP acceptance) — that proves it runs fast, not that it is good. Quality = Aider / GSM8K / Terminal-Bench / KLD / PPL vs BF16, rarely published for community GGUFs. If only speed exists, say so. Never present a speed table as "quality". A single user's Aider comparison ("NVFP4 ~69% vs Q6_K_XL ~75%") is a weak anecdotal signal — label it.
3. **Verify with real user feedback (HF-discussions trick).** Reddit is **not** a data source (`.json`, `old.reddit`, `api.reddit`, redlib/libreddit, jina all 403/blocked to curl + web_extract; only `web_search` *snippets* include comment excerpts). The **HuggingFace discussions API works reliably**: `curl -sL "https://huggingface.co/api/models/<repo>/discussions?limit=20"` (titles/authors/dates/counts, no bodies) → then `web_extract` on `https://huggingface.co/<repo>/discussions/<num>` for full text.
4. **Account for architecture sensitivity.** Hybrid DeltaNet models (Qwen 3.5/3.6/3.8 27B: 48 of 64 layers are linear-attention DeltaNet) are the **most quantization-sensitive** and degrade worst at long context. An NVFP4 GGUF keeping attention + DeltaNet projections at **Q8_0** (NVFP4 only in MLP) is materially different from one dropping attention to NVFP4/Q4. Read the tensor layout in the model card. For long-context agent work, preserving attention/DeltaNet at high precision usually matters more than squeezing the FFN.
5. **Recommend A/B on the user's own hardware** (Aider + one real task + PPL/KLD vs current) before committing. User preference: verify with a real task, not a benchmark; waits for tech to stabilize.

**Pitfalls**
- Don't cite an author's speed table as "quality" — keep the two separate in the answer.
- Don't repeat "no NVFP4 GGUF preserves linear_attn" for Qwen3.8 — true for 3.6 (Jun 2026); `utautako`'s Q8attn resolves it for 3.8 (Q8_0 attention/DeltaNet, NVFP4 MLP).
- A vLLM checkpoint's GSM8K/Terminal-Bench score does **not** prove the llama.cpp GGUF is equivalent.
- Fresh model (days old, few thousand downloads) = thin sample of user reports. State the sample size, don't overclaim.
- **QAT/AutoRound is a dead end at 6-bit for Qwen3.8-27B (checked 2026-09-01).** QAT's value concentrates at 2–4 bits; at 6 bits an imatrix PTQ (Unsloth Q6_K) is near-lossless and nothing beats it. The only 27B QAT GGUF is `sdkyuan/qwen3.8-27B-qat-q2_0-gguf` (8.76 GB, efficient-QAT w/ teacher KD — beats PTQ only at its own size class; tool-calling KL 0.638, vision + fact recall degraded, author warns explicitly). `QUASAR-QAT/Qwen3.8-27B-QUASAR-NVFP4` is QAT but compressed-tensors/vLLM-only (no llama.cpp). The AutoRound repos (Intel, webhie) are Q4-only. Above Q6_K the only real quality step is Q8 (VRAM-limited on the 5090 at 140K ctx).

Too-big MoE on an alternative engine (Strata-type forks: download, lossless repack, placement, test-before-profile): `references/large-moe-checkpoint-prep.md`.

Deep dives (moved here): `references/qwen3.8-27b-nvfp4.md` (concrete options map: tensor layouts, sizes, speed + quality, real user feedback), `references/unsloth-nvfp4-vllm-ecosystem.md`.

---

## 4. Long-context degradation testing

**When:** after changing **quantization, KV-cache bits, llama.cpp build, or context size**; when the model "forgets" old facts in long chats and you must localize whether it's the model or the agent; to build/maintain a **comparable baseline** across quants/builds. **Not** for speed (llama-benchy) or pure reasoning (intelligence suite) — this is the third dimension: **reading in long context**.

Reference baseline: 19/08/2026 — Qwen3.8-27B NVFP4-Q8attn MTP, ctx 230k, K Q8_0 / V q5_1 → **25/25 to ~200k** (incl. multi-hop 4-sum @200k + distractors @200k). Detail in `references/long-context-baseline-20260819.md`.

**The 3 probe types** (what actually exposes degradation)
| Type | Difficulty | What it exposes |
|---|---|---|
| Needle-in-a-haystack | easy | Locate ONE datum at various depths/lengths. A degraded-attention model can **pass this** — don't stop here. |
| Multi-hop aggregation | med-high | N values scattered through context; read them all + do arithmetic. Retrieval failure appears here. |
| Distractor discrimination | high | N−1 near-identical records + 1 target. Confusion between similar records — the classic long-context failure. |
Plus a **~4k sanity baseline** to validate the harness itself.

**Run** (scripts moved to `scripts/`; working copies in `/mnt/e/Workspace/performance/`)
```bash
cd /mnt/e/Workspace/performance
python3 -u long_context_test.py        # easy: needle 32k-180k + 5-sum 64k/140k   (~15-20 min)
python3 -u long_context_hard_test.py   # hard: needle 200k + multi-hop 140/200k + distractors (~15 min)
```
Write incremental JSON to `results/long-context[-hard]-YYYYMMDD-HHMMSS.json`. `hard` imports from `long_context_test` — run from the same dir. Launch via Hermes background (`terminal background=true, notify_on_complete=true`); foreground 600s is not enough.

**Methodology rules**
- `temperature=0`, `max_tokens=1024`, exact string-inclusion parse.
- **Always check `finish_reason == "stop"`**: a `"length"` invalidates the probe (parser may have "matched" truncated text).
- Calibrate chars/token **live** via `usage.prompt_tokens` (~4.63 for Qwen with Spanish note filler). Don't hardcode.
- **Sequential** — the server is single-slot; parallel probes queue and contaminate.
- **Deterministic seeds** → reproducible context across runs (comparable baselines).

**Interpretation**
- No degradation = all correct across depths/lengths/types.
- **Latency ≠ quality**: a 200k prefill (~130–155s) is a cost, not a quality signal (speed is measured separately).
- **If the model "forgets" old facts in real long chats: suspect Hermes' conversation COMPRESSION first** (agent-level history summarization) before the model or the KV cache. The model can be perfect and the agent may have summarized the context away.

**Pitfalls**
- The needle alone is a **weak** test — always include multi-hop + distractors.
- Don't trust an 180k "pass" if real usage is 200k+ with multi-hop; run the hard suite.
- **PPL / next-token fluency is NOT proof of long context** (same trap as NVFP4-Q8: low PPL, reasoning destroyed).
- >200k needs more `cache-ram` / more compressed KV.

Scripts (moved here): `scripts/long_context_test.py`, `scripts/long_context_hard_test.py`. Reference: `references/long-context-baseline-20260819.md`.

---

## 5. Edge / auxiliary deployment

**When:** free up `cache-ram` on the main GPU server (RTX 5090, etc.); offload async auxiliary tasks to a cheap edge device (Pi 5 / mini PC); reduce context pressure on the main model during compression; run Hermes auxiliary tasks without cloud calls.

Full runbook moved to `references/edge-aux-deployment.md`. Summary of the load-bearing decisions:
- **Model:** Qwen3.5-4B-MTP (Q4_K_M, ~2.8 GB, native MTP) — best quality + MTP speedup for edge. Source `prithivMLmods/Qwen3.5-4B-MTP-GGUF`.
- **Build on ARM64: use BLIS, not OpenBLAS** — **+42–43% prompt-processing** at 4–6K tokens. BLIS has no `.pc` file on Debian/ARM, so pass paths manually (`-DBLAS_LIBRARIES=/usr/lib/aarch64-linux-gnu/libblis.so -DBLAS_INCLUDE_DIRS=/usr/include/aarch64-linux-gnu`). Flash Attention is CUDA-only — on CPU/ARM the real PP wins are BLIS + `--ubatch-size`.
- **KV cache:** K Q5_1 + V Q4_0 (~18 bytes/token) vs Q8_0/Q5_1 (~26). **96K is the practical max on a 7.9 GB Pi 5** (128K → swap thrashing, active si/so). Leave ~1.5 GB for OS.
- **Server flags:** `-t 4 -tb 4 -c 98304 --cache-type-k q5_1 --cache-type-v q4_0 --host 0.0.0.0 --port 8082 --ubatch-size 2048 --spec-type draft-mtp,ngram-simple --spec-draft-n-max 3 --reasoning off`.
- **Hermes routing:** keep latency-sensitive tasks (compression, vision, web_extract, session_search, mcp, background_review) on the main GPU; offload ~15 async/short tasks (skills_hub, title_generation, triage_specifier, approval, tts_audio_tags, kanban_decomposer, curator, monitor, flush_memories, memory_query_rewrite, goal_judge, moa_*, profile_describer) to the edge via `hermes config set auxiliary.<task>.provider custom` + `base_url http://<PI_IP>:8082/v1`. `background_review` (40K+ tokens ≈ 40–50 min) stays on the GPU.
- **Verify MTP:** `grep 'draft acceptance' llama-server.log` — expect 0.85–0.95; <0.60 is a problem.

**Top pitfalls:** `--spec-type mtp` fails → use `draft-mtp`; thinking is on by default for Qwen3.5 (`--reasoning off` / `enable_thinking:false`, `extra_body` does NOT work); ports 8080/8081 often busy → use 8082; SSH dies during `make -j4` (use `nohup`); no `/cancel` endpoint (restart the service); gateway can't `hermes gateway restart` from inside itself.

---

## 6. Windows video input (mtmd) workaround

**When:** `input_video` on a **Windows** llama-server hangs ~2 min then returns **0 decoded frames** (images fine). Upstream [#24429](https://github.com/ggml-org/llama.cpp/issues/24429) open/unconfirmed/no merged PR — don't wait on it. Validated 2026-08-20 (b10538, Windows host reached from WSL).

**Diagnosis (in order)**
1. **`usage.prompt_tokens` is the decisive metric.** Expected ≈ `n_frames × --image-min-tokens` (18 frames × 1024 ≈ 18K). A few hundred = **0 frames decoded**.
2. **Server log:** silent multi-minute gap + zero `ffmpeg|video|probe` lines ⇒ subprocess-level hang, not a decode error.
3. **Isolate ffmpeg:** run the exact command directly (from WSL works via `/mnt/`): `ffmpeg.exe -nostdin -i cache:pipe:0 -vf fps=4 -f rawvideo -pix_fmt rgb24 pipe:1 < test.mp4 > raw.bin`. Byte count must be `W*H*3*frames`. If fast + correct, ffmpeg is innocent.
4. **Rule out MP4 layout** (optional): faststart reproduces it, but the wrapper fixes all layouts.
5. **Check the build has MTMD_VIDEO** in `llama-server-impl.dll` (the 300 KB stub exe's `strings` is polluted by the bundled WebUI).

**Root cause:** `vendor/sheredom/subprocess.h` (Windows `CreateProcessW` path) keeps the parent's read end of the stdin pipe (`hStdInput`) open until `join`/`destroy`. `mtmd-helper.cpp` writes video bytes into that pipe from a feeder thread. `ffprobe` on a faststart MP4 reads the header and exits **without draining the pipe** → feeder blocks → `feeder.join()` hangs → ~2 min, 0 frames. **Restarting does not help.**

**Workaround — stdin-drain wrapper (no rebuild, no llama.cpp change):** a small C program installed *as* `ffmpeg.exe`/`ffprobe.exe` next to `llama-server.exe`. It drains its own stdin to a temp file (feeder always has a reader), rewrites `pipe:0`/`cache:pipe:0` args to that file, launches `<name>_real.exe` and inherits stdout/stderr. Full tested source: `templates/mtmd-wrapper.c`.
- Build (cross-compile from WSL, ~10 s): `x86_64-w64-mingw32-gcc -O2 -static -Wall -o mtmd_wrapper.exe mtmd-wrapper.c`.
- Deploy: `ffmpeg.exe`=wrapper, `ffprobe.exe`=wrapper, originals renamed `ffmpeg_real.exe`/`ffprobe_real.exe`. Same dir as `llama-server.exe` always resolves first. **No server restart** (resolved per request). Rollback: `mv ffmpeg_real.exe ffmpeg.exe && mv ffprobe_real.exe ffprobe.exe`.
- Verify: pipe a clip through the wrapper `ffprobe`/`ffmpeg`; `raw.bin` size must equal `W*H*3*frames`. End-to-end: `input_video` request → `prompt_tokens` in the thousands, wall time ~10–15 s for a 4.5 s clip.

**Pitfalls (all hit in the original session)**
- **CreateProcessW argv shift:** with `lpApplicationName` set, `lpCommandLine` MUST still start with the exe name or every arg shifts left (ffprobe errors, ffmpeg tolerates). Test **both** binaries.
- **8.3 short paths:** `GetTempPathA` can return `C:\Users\RAL~1\...` for non-ASCII profiles; BtbN builds choke — put the temp file next to the wrapper instead.
- **WSL env vars don't cross** into Win32 children — use the `-mtmddebug` sentinel ARG (not an env var) to dump the child cmdline.
- **`DeleteFileA`, not `RemoveFileA`** (the latter needs `shellapi.h`, won't link under `WIN32_LEAN_AND_MEAN`).
- **Reasoning eats the smoke-test budget:** with reasoning on/high effort, small `max_tokens` spends everything thinking → empty `content`. Use `reasoning_effort:"low"` + `max_tokens>=300`.
- **strings on the stub exe is a false positive** — check `llama-server-impl.dll` for MTMD symbols.
- **Hermes angle:** Hermes' `video_analyze` extracts frames locally and sends *images* to the auxiliary vision model — it does NOT route `input_video` to a llama.cpp server. For local video via llama.cpp, call the server API directly.

---

## 7. Other engines: Strata NVFP4

**When:** "is Qwen3.8-Flash-Next on Strata running as fast as it can on my system?" — a read-only headroom audit of the Strata engine (experts in RAM/SSD tiers, only a cache in VRAM). None of the llama.cpp flags or `/props` fields apply; the audit path, log format, memory-mode detection, per-mode knobs, and the author's own "tried and dropped" list are in `references/strata-nvfp4-audit.md`. Follow it instead of improvising llama.cpp intuitions, and read the engine's `docs/NVFP4.md` before proposing any flag change.

---

## 8. Control vectors (uncensor toggle)

**When:** "¿se puede tener el modelo X uncensored sin perder calidad de agente?"; comparando control vector vs pack abliterated; replicar en llama.cpp el toggle normal↔uncensored de Strata.

- **No hace falta ningún fork**: llama.cpp soporta control vectors de forma nativa — `--control-vector`, `--control-vector-scaled FNAME:SCALE`, `--control-vector-layer-range START END`. Verificar en el build local con `--help` (nunca con `strings` del stub exe — el código está en `llama.dll`).
- **El vector es model-específico** (validación `n_embd` + derivado sobre las activaciones de ese modelo): jamás transferir un vector entre modelos, ni de la misma familia. El toggle se monta como dos perfiles de arranque sobre el MISMO GGUF con/sin los flags (equivalente a los perfiles de Strata); ik_llama ofrece además hot-swap en runtime vía HTTP `/control-vectors/load` (verificar soporte de la arquitectura antes de proponerlo).
- **Decisión**: vector publicado > abliterated de fábrica. Los packs abliterated (huihui/orcarouter/0bserverx/HauhauCS para Qwen3.8-27B) son abliteration completa → degradan el agente en sesiones largas (medido) y conmutar = cambiar de pack (KV no cruza). Sin vector publicado, derivarlo es un proyecto aparte.
- **Expectativa honesta**: el vector toca la dirección de rechazo, no la capacidad — ni esperar ni prometer mejoras en benchmarks de razonamiento corto; el efecto se busca en estabilidad de sesiones largas y refusals.
- Landscape completo (flags, formatos vector-add, repos HF, recetas de búsqueda API): `references/control-vectors-uncensor.md`. El equivalente Strata y su A/B de fidelidad: skill `strata-nvfp4-tuning` (pack gptq + control vector) y `strata-profile-switch` (toggle por perfiles).
