---
name: llama-cpp
description: llama.cpp local GGUF inference + HF Hub model discovery.
version: 2.1.2
author: Orchestra Research
license: MIT
dependencies: [llama-cpp-python>=0.2.0]
metadata:
  hermes:
    tags: [llama.cpp, GGUF, Quantization, Hugging Face Hub, CPU Inference, Apple Silicon, Edge Deployment, AMD GPUs, Intel GPUs, NVIDIA, URL-first]
---

# llama.cpp + GGUF

Use this skill for local GGUF inference, quant selection, or Hugging Face repo discovery for llama.cpp.

## When to use

- Run local models on CPU, Apple Silicon, CUDA, ROCm, or Intel GPUs
- Find the right GGUF for a specific Hugging Face repo
- Build a `llama-server` or `llama-cli` command from the Hub
- Search the Hub for models that already support llama.cpp
- Enumerate available `.gguf` files and sizes for a repo
- Decide between Q4/Q5/Q6/IQ variants for the user's RAM or VRAM

## Model Discovery workflow

Prefer URL workflows before asking for `hf`, Python, or custom scripts.

1. Search for candidate repos on the Hub:
   - Base: `https://huggingface.co/models?apps=llama.cpp&sort=trending`
   - Add `search=<term>` for a model family
   - Add `num_parameters=min:0,max:24B` or similar when the user has size constraints
2. Open the repo with the llama.cpp local-app view:
   - `https://huggingface.co/<repo>?local-app=llama.cpp`
3. Treat the local-app snippet as the source of truth when it is visible:
   - copy the exact `llama-server` or `llama-cli` command
   - report the recommended quant exactly as HF shows it
4. Read the same `?local-app=llama.cpp` URL as page text or HTML and extract the section under `Hardware compatibility`:
   - prefer its exact quant labels and sizes over generic tables
   - keep repo-specific labels such as `UD-Q4_K_M` or `IQ4_NL_XL`
   - if that section is not visible in the fetched page source, say so and fall back to the tree API plus generic quant guidance
5. Query the tree API to confirm what actually exists:
   - `https://huggingface.co/api/models/<repo>/tree/main?recursive=true`
   - keep entries where `type` is `file` and `path` ends with `.gguf`
   - use `path` and `size` as the source of truth for filenames and byte sizes
   - separate quantized checkpoints from `mmproj-*.gguf` projector files and `BF16/` shard files
   - use `https://huggingface.co/<repo>/tree/main` only as a human fallback
6. If the local-app snippet is not text-visible, reconstruct the command from the repo plus the chosen quant:
   - shorthand quant selection: `llama-server -hf <repo>:<QUANT>`
   - exact-file fallback: `llama-server --hf-repo <repo> --hf-file <filename.gguf>`
7. Only suggest conversion from Transformers weights if the repo does not already expose GGUF files.

## Quick start

### Install llama.cpp

```bash
# macOS / Linux (simplest)
brew install llama.cpp
```

```bash
winget install llama.cpp
```

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release
```

### Run directly from the Hugging Face Hub

```bash
llama-cli -hf bartowski/Llama-3.2-3B-Instruct-GGUF:Q8_0
```

```bash
llama-server -hf bartowski/Llama-3.2-3B-Instruct-GGUF:Q8_0
```

### Run an exact GGUF file from the Hub

Use this when the tree API shows custom file naming or the exact HF snippet is missing.

```bash
llama-server \
    --hf-repo microsoft/Phi-3-mini-4k-instruct-gguf \
    --hf-file Phi-3-mini-4k-instruct-q4.gguf \
    -c 4096
```

### OpenAI-compatible server check

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Write a limerick about Python exceptions"}
    ]
  }'
```

## Python bindings (llama-cpp-python)

`pip install llama-cpp-python` (CUDA: `CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir`; Metal: `CMAKE_ARGS="-DGGML_METAL=on" ...`).

### Basic generation

```python
from llama_cpp import Llama

llm = Llama(
    model_path="./model-q4_k_m.gguf",
    n_ctx=4096,
    n_gpu_layers=35,     # 0 for CPU, 99 to offload everything
    n_threads=8,
)

out = llm("What is machine learning?", max_tokens=256, temperature=0.7)
print(out["choices"][0]["text"])
```

### Chat + streaming

```python
llm = Llama(
    model_path="./model-q4_k_m.gguf",
    n_ctx=4096,
    n_gpu_layers=35,
    chat_format="llama-3",   # or "chatml", "mistral", etc.
)

resp = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is Python?"},
    ],
    max_tokens=256,
)
print(resp["choices"][0]["message"]["content"])

# Streaming
for chunk in llm("Explain quantum computing:", max_tokens=256, stream=True):
    print(chunk["choices"][0]["text"], end="", flush=True)
```

### Embeddings

```python
llm = Llama(model_path="./model-q4_k_m.gguf", embedding=True, n_gpu_layers=35)
vec = llm.embed("This is a test sentence.")
print(f"Embedding dimension: {len(vec)}")
```

You can also load a GGUF straight from the Hub:

```python
llm = Llama.from_pretrained(
    repo_id="bartowski/Llama-3.2-3B-Instruct-GGUF",
    filename="*Q4_K_M.gguf",
    n_gpu_layers=35,
)
```

## Choosing a quant

Use the Hub page first, generic heuristics second.

- Prefer the exact quant that HF marks as compatible for the user's hardware profile.
- For general chat, start with `Q4_K_M`.
- For code or technical work, prefer `Q5_K_M` or `Q6_K` if memory allows.
- For very tight RAM budgets, consider `Q3_K_M`, `IQ` variants, or `Q2` variants only if the user explicitly prioritizes fit over quality.
- For multimodal repos, mention `mmproj-*.gguf` separately. The projector is not the main model file.
- Do not normalize repo-native labels. If the page says `UD-Q4_K_M`, report `UD-Q4_K_M`.

### AWQ-INT4 models — NOT compatible with llama.cpp

Models like `cyankiwi/Qwen3.6-27B-AWQ-INT4` are designed for vLLM/SGLang/AutoAWQ. They use a different quantization format that llama.cpp cannot load. AWQ can only be used as pre-processing (adjust FP16 weights → convert to GGUF → quantize with K-quants), not as a runtime format. For llama.cpp, Q6_K remains superior to any AWQ-INT4 conversion.

## Extracting available GGUFs from a repo

When the user asks what GGUFs exist, return:

- filename
- file size
- quant label
- whether it is a main model or an auxiliary projector

Ignore unless requested:

- README
- BF16 shard files
- imatrix blobs or calibration artifacts

Use the tree API for this step:

- `https://huggingface.co/api/models/<repo>/tree/main?recursive=true`

For a repo like `unsloth/Qwen3.6-35B-A3B-GGUF`, the local-app page can show quant chips such as `UD-Q4_K_M`, `UD-Q5_K_M`, `UD-Q6_K`, and `Q8_0`, while the tree API exposes exact file paths such as `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` and `Qwen3.6-35B-A3B-Q8_0.gguf` with byte sizes. Use the tree API to turn a quant label into an exact filename.

## Search patterns

Use these URL shapes directly:

```text
https://huggingface.co/models?apps=llama.cpp&sort=trending
https://huggingface.co/models?search=<term>&apps=llama.cpp&sort=trending
https://huggingface.co/models?search=<term>&apps=llama.cpp&num_parameters=min:0,max:24B&sort=trending
https://huggingface.co/<repo>?local-app=llama.cpp
https://huggingface.co/api/models/<repo>/tree/main?recursive=true
https://huggingface.co/<repo>/tree/main
```

## Output format

When answering discovery requests, prefer a compact structured result like:

```text
Repo: <repo>
Recommended quant from HF: <label> (<size>)
llama-server: <command>
Other GGUFs:
- <filename> - <size>
- <filename> - <size>
Source URLs:
- <local-app URL>
- <tree API URL>
```

## Agent Workloads (Hermes, OpenClaw, etc.)

⚠️ **Context compression + unified KV cache interaction**: When running agent frameworks that compress context (Hermes Agent, OpenClaw), the compression event sends a new request that can trigger expensive cache updates in llama.cpp's unified KV cache. This causes 10-20 minute slowdowns during compression.

**Quick fixes**:
- Raise `compression.threshold` to 0.70+ (compress at higher context usage)
- Use `--parallel 1` to avoid cross-slot cache interference
- Remove `--no-cache-idle-slots` to allow cache cleanup
- See [hermes-compression-kv-cache-interaction.md](references/hermes-compression-kv-cache-interaction.md) for full analysis

## Known Open Issues (llama.cpp)

When experiencing intermittent tool-call failures, grammar sampling loops, or Qwen3 crashes, check these **open upstream issues** before assuming a local misconfiguration:

| Issue | Affected | Symptom |
|-------|----------|---------|
| [#20033](https://github.com/ggml-org/llama.cpp/issues/20033) | All (cache reuse) | Prompt cache update takes 80s+ when overwriting existing cache item. Critical for agent workloads with context compression. |

| Issue | Affected | Symptom |
|-------|----------|---------|
| [#20837](https://github.com/ggerganov/llama.cpp/issues/20837) | Qwen3.5/3.6 + thinking | Tool calls printed as XML inside `<think>` block; model stops. Also happens in vLLM. |
| [#20260](https://github.com/ggerganov/llama.cpp/issues/20260) | Qwen3.5/3.6 thinking models | PEG parser fails when model outputs text before `<![CDATA[<tool_call>]]>` tags |
| [#22398](https://github.com/ggerganov/llama.cpp/issues/22398) | Qwen3.6-27B | Model outputs answers inside `<think>` tags or doubles tags; causes stops in agentic workloads |
| [#22072](https://github.com/ggerganov/llama.cpp/issues/22072) | Qwen3.x + tool calling | Malformed/incomplete JSON tool args (intermittent) |
| [#22381](https://github.com/ggerganov/llama.cpp/issues/22381) | All (since b8931) | GBNF grammar sampling → token-loop / unconstrained output |
| [#21771](https://github.com/ggerganov/llama.cpp/issues/21771) | Qwen3 TAG_WITH_TAGGED | PEG parser fails on `array<object>` params; history poisoning |
| [#22314](https://github.com/ggerganov/llama.cpp/issues/22314) | Tool schemas with PCRE | JSON Schema → GBNF grammar conversion fails |
| [#21903](https://github.com/ggerganov/llama.cpp/issues/21903) | Qwen3.5/3.6 | Tool call triggers full prompt reprocessing next turn |

Recently closed fixes that improved stability: #22812 (MiMo-V2.5 flash attention MMA/Tiles, b9085), #22837 (Hexagon Gated Delta Net HTP kernel, b9084), #22805 (device state save/load buffer offsets, b9064), #22804 (Gemma4_26B_A4B_NVFP4 support, b9080), #22820 (CUDA PCI bus ID lower-case standardization, b9073), #22667 (CUDA snake activation fusion for audio decoders, b9075), #22651 (CUDA batch out_prod cublasSgemmStridedBatched, b9066), #22679 (device buffer memory save option, b9028), #22290 (lazy backend loading, b9031), #22654 (autoparser newline/forced tool call fixes, b9020), #22686 (cpp-httplib → 0.43.3, b9030), #22558 (server checkpoint host copy avoidance, b9009), #22533 (CUDA PCI bus ID de-dupe OOM fix, b9010), #22631 (fast Walsh-Hadamard transform for KV rotation, b9026), #22384 (context checkpoint for hybrid models, 2026-04-26), #22234 (heap buffer overflow in grammar, 2026-04-22), #22304 (KV cache rebuild with tensor splitting, 2026-04-24), #21158 (Qwen3.5-27B tool call parsing with text before tags, 2026-03-29), #20970 (inhibit lazy grammar sampler while reasoning active).

## Active CVEs (May 2026)

| Severity | CVE | Description |
|----------|-----|-------------|
| 🔴 CRITICAL | GHSA-j8rj-fmpv-wcxw | RCE via `GRAPH_COMPUTE buffer=0` in RPC backend |
| 🟠 HIGH | GHSA-3p4r-fq3f-q74v | Heap buffer overflow in `mem_size` (bypass of CVE-2025-53630) |
| 🟠 HIGH | GHSA-96jg-mvhq-q7q7 | Heap buffer overflow in GGUF tensor parsing |
| 🟠 HIGH | GHSA-vgg9-87g3-85w8 | Integer overflow in GGUF parser → OOB read/write |
| 🟡 LOW | GHSA-8947-pfff-2f3c | OOB write in llama-server |

→ Update to latest release (b9180+, released 2026-05-16) if exposed to untrusted GGUFs or RPC. b9180 also includes native MTP support.

## References

- **[hub-discovery.md](references/hub-discovery.md)** - URL-only Hugging Face workflows, search patterns, GGUF extraction, and command reconstruction
- **[advanced-usage.md](references/advanced-usage.md)** — speculative decoding (MTP, D-Flash, draft models), batched inference, grammar-constrained generation, LoRA, multi-GPU, custom builds, benchmark scripts
- **[speculative-decoding.md](references/speculative-decoding.md)** — D-Flash research notes, MTP verification, performance benchmarks, vLLM/llama.cpp integration status, **TurboQuant main vs forks status**
- **[gguf-mtp-verification.md](references/gguf-mtp-verification.md)** — Session findings: GGUF filename vs metadata mismatch, MTP presence verification workflow
- **[quantization.md](references/quantization.md)** — quant quality tradeoffs, when to use Q4/Q5/Q6/IQ, model size scaling, imatrix, **NVFP4/FP4 for Blackwell GPUs (GGUF vs vLLM format ecosystems)**
- **[server.md](references/server.md)** — direct-from-Hub server launch, OpenAI API endpoints, Docker deployment, NGINX load balancing, monitoring
- **[optimization.md](references/optimization.md)** — CPU threading, BLAS, GPU offload heuristics, batch tuning, benchmarks
- **[tool-calling-thinking-bug.md](references/tool-calling-thinking-bug.md)** — Qwen3.5/3.6 tool calls inside thinking blocks: root cause, workarounds, affected issues
- **[troubleshooting.md](references/troubleshooting.md)** — install/convert/quantize/inference/server issues, Apple Silicon, debugging
- **[parallel-kv-unified.md](references/parallel-kv-unified.md)** — `--kv-cache-unified` parallel serving: flags, VRAM layout, benchmarking, WSL connectivity to Windows llama-server
- **[hermes-compression-kv-cache-interaction.md](references/hermes-compression-kv-cache-interaction.md)** — Hermes Agent compression + llama.cpp KV cache: root cause of 10-20 min slowdowns during compression, threshold calculation, configuration options
- **[large-context-optimization.md](references/large-context-optimization.md)** — 196K+ context optimization: VRAM budget analysis, compression flow math, parallel 2 strategy, accumulated degradation estimation
- **[changelog-b9050-b9085.md](references/changelog-b9050-b9085.md)** — b9050→b9085 release notes (2026-05-07 to ~2026-05-27): per-build changes, CUDA/server/core categorized

## Resources

- **GitHub**: https://github.com/ggml-org/llama.cpp
- **Hugging Face GGUF + llama.cpp docs**: https://huggingface.co/docs/hub/gguf-llamacpp
- **Hugging Face Local Apps docs**: https://huggingface.co/docs/hub/main/local-apps
- **Hugging Face Local Agents docs**: https://huggingface.co/docs/hub/agents-local
- **Example local-app page**: https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF?local-app=llama.cpp
- **Example tree API**: https://huggingface.co/api/models/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main?recursive=true
- **Example llama.cpp search**: https://huggingface.co/models?num_parameters=min:0,max:24B&apps=llama.cpp&sort=trending
- **License**: MIT
