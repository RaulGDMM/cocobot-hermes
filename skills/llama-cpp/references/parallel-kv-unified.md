# Parallel Serving with --kv-cache-unified

Modern llama.cpp supports `--kv-cache-unified` for shared KV cache across parallel slots. This replaces the old per-slot KV cache duplication approach.

## Key Flags

| Flag | Purpose |
|------|---------|
| `--parallel 2` | Number of concurrent slots (streams) |
| `--kv-cache-unified` | Share single KV cache across all slots |
| `--ctx-checkpoints N` | Number of context checkpoints (default: 8) |
| `--checkpoint-every-n-tokens N` | Checkpoint interval in tokens |
| `--cache-ram N` | RAM cache size in MB |
| `--no-context-shift` | Disable auto context-shift on overflow |
| `--no-cache-idle-slots` | Don't cache inactive slots |
| `-ctk q8_0` / `-ctv q8_0` | KV cache quantization (keys/values) |

## Example: Qwen3.6-27B on RTX 5090

```bash
llama-server \
    --model models/Qwen3.6-27B-UD-Q4_K_XL.gguf \
    --ctx-size 200000 \
    --parallel 2 \
    --n-gpu-layers 99 \
    --flash-attn on \
    --batch-size 2048 \
    --ubatch-size 2048 \
    --cont-batching \
    --kv-cache-unified \
    --ctx-checkpoints 32 \
    --checkpoint-every-n-tokens 1024 \
    --cache-ram 16384 \
    --no-context-shift \
    --no-cache-idle-slots \
    -ctk q8_0 \
    -ctv q8_0 \
    --host 0.0.0.0 \
    --port 30000
```

## VRAM Layout

With kv-unified, memory is shared — not duplicated:

```
┌─────────────────────────────────────────┐
│ GPU: model + SHARED context + compute   │
│ Model:  16 GB                           │
│ KV:      7 GB (shared, all slots)       │
│ Compute: 2.6 GB                         │
│ ─────────────────────────────────────   │
│ Total:  ~25.6 GB → 5 GB margin          │
└─────────────────────────────────────────┘
```

Without kv-unified, each slot would duplicate its own KV cache → 2× the memory.

## Performance Characteristics

Benchmarked on RTX 5090 + Qwen3.6-27B Q4_K_XL (Unsloth Dynamic 2.0, MTP active):

| Metric | Single Stream | 2 Concurrent |
|--------|--------------|--------------|
| Speed/stream | ~56 tok/s | ~31 tok/s (avg) |
| Throughput total | ~56 tok/s | **~62 tok/s** |
| Penalty/stream | — | ~44% |
| VRAM | stable | stable (no growth) |

**Key insight**: Combined throughput (62) > single stream (56). The GPU is better utilized with parallel streams due to batch filling. The ~44% penalty per stream is the tradeoff.

## Common Pitfalls

### `--parallel` specified multiple times

If your startup script sets `--parallel 1` as default and then overrides it per-model, llama.cpp will emit:

```
DEPRECATED: argument '--parallel' specified multiple times,
use comma-separated values instead (only last value will be used)
```

**Fix**: Remove the default `--parallel` from the base config and let each model profile specify its own value. Or use the new comma-separated format: `--parallel 2,3` for different slot configs.

## Verifying kv-unified is Active

Check the startup log for:
```
llama_context: kv_unified    = true
llama_context: n_seq_max     = 2
slot   load_model: id  0 | task -1 | new slot, n_ctx = 200192
slot   load_model: id  1 | task -1 | new slot, n_ctx = 200192
```

Both `kv_unified = true` AND 2 slots (id 0 and 1) should appear.

## WSL Access to Windows llama-server

When llama-server runs on Windows and you're accessing from WSL:

- **Do NOT use `grep nameserver /etc/resolv.conf`** — Tailscale hijacks this and returns `100.100.100.100` (its own DNS proxy)
- **Use the WSL2 default gateway**: `ip route | grep default | awk '{print $3}'` → typically `172.x.x.x`
- The host IP changes on each reboot (WSL2 DHCP), so resolve it dynamically

```python
import subprocess
hip = subprocess.check_output("ip route | grep default | awk '{print $3}'", shell=True).decode().strip()
base = f"http://{hip}:30000"
```

Ensure llama-server binds to `0.0.0.0` (not `127.0.0.1`) — this is the default in most launch scripts.

## Benchmarking Concurrent Streams

Python script for concurrent request benchmarking:

```python
import json, time, urllib.request, threading

base = "http://<llama-server-ip>:30000"

def chat(prompt, max_tok=80):
    payload = json.dumps({
        "model": "model-id",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tok, "temperature": 0, "stream": False
    })
    start = time.time()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=payload.encode(),
        headers={"Content-Type": "application/json"}
    )
    data = json.loads(urllib.request.urlopen(req, timeout=120).read())
    elapsed = time.time() - start
    tok = data.get('usage',{}).get('completion_tokens', 0)
    return {'tokens': tok, 'elapsed': elapsed, 'speed': tok/elapsed}

# Concurrent test
results = {}
def req(name, prompt, tok):
    results[name] = chat(prompt, tok)

tA = threading.Thread(target=req, args=("A", "Long prompt A", 100))
tB = threading.Thread(target=req, args=("B", "Long prompt B", 80))
tA.start(); tB.start()
tA.join(); tB.join()

print(f"A: {results['A']['speed']:.1f} tok/s")
print(f"B: {results['B']['speed']:.1f} tok/s")
```
