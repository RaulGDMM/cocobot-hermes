# Large Context Optimization (196K+) with llama.cpp + Hermes Agent

Session findings from optimizing Qwen3.6-27B-NVFP4-Q8_0 on RTX 5090 (32 GB VRAM) with 196K context window.

## VRAM Budget (196K ctx, q8 KV, unified, parallel 2)

| Component | VRAM | Notes |
|-----------|------|-------|
| Model (NVFP4-Q8_0) | ~17.8 GB | FFN in NVFP4, attention/embeddings in Q8 |
| KV Cache (unified q8_0) | ~6.5 GB | 196K × 2 slots × q8_0 |
| Compute buffer | ~2.6 GB | FFN matmul workspace |
| Recurrent state | ~0.3 GB | Layer-wise state |
| **Total** | **~27.2 GB** | **4.8 GB headroom / 32 GB** |

### Context checkpoints

`--ctx-checkpoints 32` with `--cache-ram 16384` stores snapshots in **host RAM** (not VRAM). Each checkpoint is ~150 MB × 32 = ~4.8 GB RAM. Controlled by `--cache-ram` limit, does NOT consume VRAM.

## Compression Flow Analysis

With `threshold: 0.45`, `target_ratio: 0.2`, ctx 196K:

```
Context at 88.5K (45%) → compression triggers
    ↓
Tail preserved: 17.7K tokens (last ~10 turns)
    ↓
Summary generated: ~12K tokens
    ↓
New context: ~30K tokens (summary + tail)
    ↓
Available space: 166K tokens remaining
```

### Compression frequency estimation

For a typical tool-heavy session:
- Each turn: ~1.5K tokens (user + assistant + tool calls)
- From 30K to 88.5K: ~39 turns before next compression
- Total turns before hitting 196K: ~130 turns (without compression)
- With compression: ~39 turns per cycle, each cycle preserves 30K context

### Accumulated degradation

Each compression is lossy. Over multiple cycles:
- Cycle 1: 88K → 30K (68% information loss)
- Cycle 2: 88K → 30K (another 68% of remaining useful context)
- By cycle 3: ~50% of original context information preserved

**Mitigation**: Higher threshold = fewer compressions = less degradation. With threshold 0.70, compress at 137K instead of 88K — 55% more context preserved per cycle.

## Parallel 2 Strategy

**Why it matters**: With `--parallel 2`, one slot serves the user while the other handles compression. This avoids the 10-20 minute blocking that occurs with `--parallel 1`.

### Unified KV cache behavior with parallel 2

```
Slot 0: Active user session (growing context)
Slot 1: Idle (available for compression request)

When compression triggers:
  - Hermes sends compressed context to Slot 1
  - Slot 1 processes fresh request (no cache update needed)
  - Slot 0 continues serving user normally
  - Result: User sees no interruption
```

### Without parallel 2 (parallel 1)

```
Slot 0: Active user session
    ↓
Compression triggers → must reprocess entire context
    ↓
User waits 10-20 minutes for compression to complete
    ↓
System is blocked during compression
```

## Configuration Summary

### Current stable config (Qwen3.6-27B-NVFP4-Q8_0, RTX 5090)

```bash
llama-server \
  --model Qwen3.6-27B-NVFP4-Q8_0.gguf \
  --ctx-size 196608 \
  --parallel 2 \
  --kv-cache-unified \
  --ctx-checkpoints 32 \
  --cache-ram 16384 \
  --no-context-shift \
  --no-cache-idle-slots \
  -ctk q8_0 -ctv q8_0
```

```yaml
# Hermes config.yaml
compression:
  enabled: true
  threshold: 0.45
  target_ratio: 0.2
  protect_last_n: 20
```

### Alternative: Higher threshold (less compression, less degradation)

```yaml
compression:
  threshold: 0.70        # compress at 137K instead of 88K
  target_ratio: 0.20
```

### Alternative: Without unified KV (more VRAM, no cross-slot interference)

```bash
# Remove --kv-cache-unified
# Each slot has independent KV cache → ~13 GB total KV vs 6.5 GB unified
# Requires ~4 GB more VRAM total → tight on 32 GB card
```

## Future Improvements

### TurboQuant / Turbo3 / Turbo4 (KV cache optimization)

When these mature in llama.cpp, they could reduce KV cache VRAM by 50-70%:
- Current q8_0: 6.5 GB
- With TurboQuant q4_0: ~3.3 GB (50% reduction)
- With TurboQuant q2_0: ~1.6 GB (75% reduction)

### Dynamic KV quantization

Future llama.cpp may support:
- Hot tokens in q8_0/f16 (recent context)
- Cold tokens in q4_0/q2_0 (older context)
- Automatic migration as tokens age

### Hermes auxiliary compression fixes

When upstream fixes land:
- Configurable timeout (>45s for edge devices)
- No silent fallback to OpenRouter
- Proper context_length reading from config
- Would enable Pi 5 as compression offload target
