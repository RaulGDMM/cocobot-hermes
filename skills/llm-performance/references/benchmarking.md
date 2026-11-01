# Benchmarking D-Flash and Speculative Decoding Performance

## What to measure

| Metric | Meaning | Endpoint |
|--------|---------|----------|
| **Prompt TPS** | Prefill speed (tokens/second processing the input) | `/completion` timings |
| **Gen TPS** | Decoding speed (tokens/second generating output) | `/completion` timings |
| **D-Flash acceptance rate** | Accepted / attempted draft tokens | `timings_per_token[].speculative` |
| **D-Flash active vs suppressed** | Compare plain text vs tool-call generation | `/completion` vs `/v1/chat/completions` with tools |

## Key insight: D-Flash suppression with tool calls

When `lazy grammar` is active (required for robust tool calls in agent systems), D-Flash is **automatically suppressed** when the model emits a `raw tool marker`. This is architectural, not a bug: lazy grammar validates token-by-token, while D-Flash generates blocks in parallel.

**To benchmark the impact:**
- **Plain text**: Use `/completion` endpoint — D-Flash active in reasoning tokens
- **Tool calls**: Use `/v1/chat/completions` with `tools` array — D-Flash suppressed

The speedup from D-Flash in agent workloads is typically **1.3-1.6× total** (not the theoretical 2-3×) because tool call tokens (~20% of output) run at full autoregressive speed.

## Server idle detection

When running benchmarks against a llama-server shared with the Hermes agent, the server may be busy processing agent requests. Before each benchmark run:

1. Poll `/queue` endpoint
2. Check `size` or `n_tasks` field
3. Wait until queue is empty before proceeding
4. Timeout after 300s (initial) or 120s (between runs)

If timeout reached, proceed anyway with a warning — the benchmark will just be slower.

## D-Flash ring buffer verification

To confirm D-Flash is actually active during a request, check llama-server logs for:

```
DFLASH_DBG ring_state_load: write_pos=3676 filled=4096 committed=56924 entries=4096 gpu=1
```

| Field | Meaning |
|-------|---------|
| `write_pos` | Current write position in ring buffer |
| `filled` | Slots currently occupied |
| `committed` | Tokens accepted and confirmed to target model |
| `entries` | Total ring capacity |
| `gpu` | Running on GPU (1) or CPU (0) |

If `gpu=0`, D-Flash may be falling back to CPU — check GPU memory and `--spec-draft-ngl` settings.

## Recommended benchmark methodology

1. **Warm-up**: Run 1-2 dummy requests to ensure model is loaded and GPU is warm
2. **Plain text**: 3 prompt sizes (short ~50 tok, medium ~800 tok, long ~5000 tok)
3. **Tool calls**: Same 3 prompt sizes with 5+ tool definitions
4. **Control**: Run each test with `--spec-type none` to get baseline without D-Flash
5. **Compare**: Gen TPS (plain) / Gen TPS (tool calls) = D-Flash speedup ratio
6. **Acceptance**: Extract from `timings_per_token[].speculative.accepted / attempted`

## Prompt design for benchmarks

- **Short**: Simple question, ~10-50 tokens. Measures cold-start + small context.
- **Medium**: Structured request with ~800 tokens. Measures prefill at moderate scale.
- **Long**: Multi-chapter document (~5000+ tokens). Measures prefill at scale + KV cache pressure.
- **Deterministic**: Use `temperature=0, top_k=1` for reproducible token counts.
- **Cold cache**: Use `cache_prompt: false` to avoid KV cache contamination between runs.

## Interpreting results

| Scenario | Expected Gen TPS (RTX 5090, Qwen3.6-27B Q5) | D-Flash |
|----------|---------------------------------------------|---------|
| Plain text, short prompt | 40-60 tok/s | Active in reasoning |
| Plain text, long prompt | 35-55 tok/s | Active in reasoning |
| Tool calls, short | 25-40 tok/s | Suppressed |
| Tool calls, long | 20-35 tok/s | Suppressed |

If Gen TPS with D-Flash is **LOWER** than without, check:
1. Draft model quantization (Q4_K_M recommended, not Q8)
2. `--spec-dflash-cross-ctx` (1024 is good default)
3. `--spec-draft-n-max` (16 is good, but 32+ may hurt on 32GB VRAM)
4. VRAM pressure — if swapping to CPU, D-Flash overhead exceeds benefit
