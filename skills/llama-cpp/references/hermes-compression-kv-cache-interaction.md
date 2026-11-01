# Hermes Agent Compression + llama.cpp KV Cache Interaction

When running Hermes Agent with llama.cpp as a local backend, context compression triggers can interact poorly with llama.cpp's KV cache management, causing severe slowdowns (10-20 minutes) during compression events.

## Root Cause

Hermes Agent's `ContextCompressor` sends a new request to llama.cpp with a compressed context. When llama.cpp's unified KV cache has an existing slot with high similarity to the new request, it attempts to **update/overwrite** the cache rather than create a fresh slot. With large contexts and quantized KV cache (q8_0/q4_0), this cache update operation is extremely expensive.

### The Interaction Chain

```
Context grows → threshold reached (e.g., 0.45 × 196K = 88K tokens)
    ↓
Hermes compresses context → sends new request (~40K tokens)
    ↓
llama.cpp finds similar slot in unified KV cache (sim ~0.97, f_keep = 1.0)
    ↓
Cache UPDATE/OVERWRITE instead of new slot allocation
    ↓
REPROCESSING of entire old context with quantized KV → 10-20 minutes
```

## Upstream Issues

| Issue | Description | Relevance |
|-------|-------------|-----------|
| [llama.cpp #20033](https://github.com/ggml-org/llama.cpp/issues/20033) | Prompt cache update takes 80s when overwriting existing cache item | Direct match: cache reuse logic triggers expensive update |
| [llama.cpp #21179](https://github.com/ggml-org/llama.cpp/issues/21179) | Unified KV cache overflow handling interrupts active sessions | Related: cache management under pressure |
| [llama.cpp #19523](https://github.com/ggml-org/llama.cpp/issues/19523) | Inactive slots slow down token generation with unified KV | Related: cross-slot interference |
| [Hermes #3522](https://github.com/NousResearch/hermes-agent/issues/3522) | compression.threshold 0.50 causes compaction loops with local models | User raised threshold to 0.80 to avoid loops |
| [Hermes #18957](https://github.com/NousResearch/hermes-agent/issues/18957) | Proposal for context-aware threshold calculation | Formula: `threshold = 1 - (required_buffer / context_length)` |

## Configuration Flags That Compound The Problem

Three flags that work against each other in compression-heavy workloads:

| Flag | Intent | Problem during compression |
|------|--------|---------------------------|
| `--kv-unified` | Share cache across slots | Cache update/overwrite is expensive when slot content changes dramatically |
| `--no-context-shift` | Preserve full context | No sliding window fallback; must reprocess entire context |
| `--no-cache-idle-slots` | Retain inactive slot caches | Prevents cache eviction; forces updates instead of fresh allocation |

## Recommended Configurations

### Option A: Parallel 1 + High Threshold (Lowest Risk)

```yaml
# Hermes config.yaml
compression:
  enabled: true
  threshold: 0.70        # compress at 137K instead of 88K
  target_ratio: 0.20
  protect_last_n: 20
```

```bash
# llama-server
--parallel 1 \
--kv-cache-unified \
--ctx-checkpoints 32 \
--cache-ram 16384 \
--no-context-shift \
# Remove --no-cache-idle-slots to allow cache cleanup
-ctk q8_0 -ctv q8_0
```

**Trade-off**: Less parallelism, but avoids cross-slot cache interference. Higher threshold means fewer compression events.

### Option B: Parallel 2 Without Unified KV

```bash
--parallel 2 \
# Remove --kv-cache-unified \
--ctx-size 200000 \
-ctk q8_0 -ctv q8_0
```

**Trade-off**: Each slot has its own KV cache → more VRAM used, but no cross-slot update/overwrite problem.

### Option C: Unified KV + Aggressive Cache Limits

```bash
--kv-cache-unified \
--cache-ram 8192 \        # Force earlier eviction
--ctx-checkpoints 16 \    # Fewer checkpoints
--no-cache-idle-slots \   # Keep this to force eviction
```

**Trade-off**: Smaller cache means more frequent evictions but avoids the expensive update of a huge cache.

## Threshold Calculation Formula

From Hermes issue #18957, the optimal threshold accounts for output buffer needs:

```
required_buffer = max_tokens + thinking_budget + tool_buffer + safety_margin
recommended_threshold = 1 - (required_buffer / context_length)
```

Example for 196K context:
- max_tokens: 32,768
- thinking_budget (medium): 8,000
- tool_buffer: 15,000
- safety_margin (10%): 5,577
- **required_buffer**: ~61,345
- **recommended threshold**: 0.69 (compress at ~135K)

## Verification

After changing configuration, verify compression behavior:

1. Check Hermes logs for compression events:
   ```
   [compression] Context at 88K/196K (45%), triggering compression
   ```

2. Check llama-server logs for cache update timing:
   ```
   srv get_available: prompt cache update took XXX ms
   ```
   Values >10,000ms indicate the cache update problem.

3. Monitor `/slots` endpoint during compression to see if cache reuse is triggering updates.

## Pitfalls

- **Threshold too low (<0.50)**: Compression triggers too early, context never grows beyond ~50% of window. Wastes available context.
- **Threshold too high (>0.85)**: Risk of hitting context limit before compression can complete, especially with tool-heavy sessions.
- **`--no-cache-idle-slots` with unified KV**: Prevents cache cleanup, forcing expensive updates. Remove unless you specifically need inactive slot retention.
- **Q4_0 KV cache with large contexts**: Benchmarks show 92% slower prompt processing at 64K context due to dequantization overhead. Prefer q8_0 or f16 for large contexts.
- **Gateway session hygiene (85% threshold)**: Independent of agent compression. If agent compression threshold is too high, gateway hygiene may trigger first, causing unexpected session resets.
- **Auxiliary compression models**: Hermes supports `auxiliary.compression` config for offloading compression to a smaller model, but has critical bugs (see below).

## Auxiliary Compression Models (Hermes `auxiliary.compression`)

Hermes Agent can use a separate model for context compression via `config.yaml`:

```yaml
auxiliary:
  compression:
    enabled: true
    provider: "openai"
    model: "gpt-4o-mini"
    # or local:
    # provider: "custom:llama-server"
    # base_url: "http://localhost:8081"
    # model: "small-model.gguf"
```

### Known bugs (as of 2026-05)

| Bug | Description | Impact |
|-----|-------------|--------|
| Hardcoded timeout | `aiohttp.ClientTimeout(total=45)` in compressor | Small models (Pi 5, 3B) time out at 30-45s for large contexts |
| Silent fallback | On timeout, falls back to `openrouter:google/gemini-2.5-flash` | Uses OpenRouter API even if `auxiliary.compression` was configured for local model |
| Context length not read | `model_context_length` from config not used; defaults to 128K | Cannot use models with smaller context than main model |
| Context must be ≥ main model | Auxiliary model's context must be ≥ main model's context_length | A 32K model cannot compress a 196K context |

### Practical assessment

For a Pi 5 with llama.cpp running a 3B model:
- Speed: 4-7 tok/s for compression summary
- 50K tokens → ~12-20 minutes of compression time
- With 45s timeout: **will time out**
- Even without timeout: too slow for practical use

**Verdict**: Auxiliary compression on edge devices is **not viable** until Hermes fixes the timeout and the model can process at 20+ tok/s. For now, main-model compression with `parallel 2` is the only reliable option.
