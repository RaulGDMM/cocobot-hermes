# Benchmark Methodology Pitfalls — 2026-06-16

**Context:** After updating llama.cpp (b9085 → b9671), ran `dflash-benchmark.py` and got suspiciously high numbers. Investigation revealed critical methodology issues. Script was rewritten to fix them.

## Pitfall 1: ngram draft cache contamination with `--runs 3+`

Running the same prompt multiple times inflates results because the ngram draft cache learns the output pattern:

| Run | Gen TPS (texto largo) | Cause |
|-----|:---:|---|
| 1 | 135.1 tok/s | Cold — real speed |
| 2 | 243.2 tok/s | MTP adapting |
| 3 | **716.5 tok/s** | ngram cache full — artifact |

**Fix:** Always use `--runs 1` for honest measurements.

## Pitfall 2: HTTP timing ≠ server internal timing (FIXED)

The OLD benchmark script calculated TPS from HTTP round-trip time:
```python
TPS = generated_tokens / (time.time() - start)  # WRONG
```

This includes network latency, JSON serialization, and HTTP overhead. The server's internal timing (`timings.predicted_ms`) is the ground truth.

| Measurement | Result |
|---|---:|
| Old script (HTTP timing) | 227-342 tok/s |
| Server (`predicted_tps`) | **100.5 tok/s** |

**Fix (applied 2026-06-16):** The script was rewritten to use EXCLUSIVELY `timings.predicted_ms` from the server response. No client wall-clock. The output now shows `server: X ms` instead of `total: X s`.

## Pitfall 3: Speculative stats NOT in API response

Even with `timings_per_token: true`, the `/completion` endpoint does NOT populate `timings_per_token[].speculative` for MTP/ngram stats. The `spec_accepted/spec_attempted` fields in the response are empty.

**The ONLY reliable source for speculative decoding stats is the server stdout logs:**

```
39.12.567.180 I slot print_timing: id  0 | task 27623 | draft acceptance = 0.74308 (  671 accepted /   903 generated), mean acceptance length =  3.23
39.12.567.223 I statistics        ngram-mod: #calls(b,g,a) =   33  27085    459, #gen drafts =    459, #acc drafts =   459, #gen tokens =  29308, #acc tokens =  6322, #mean acc len = 14.77
39.12.567.228 I statistics        draft-mtp: #calls(b,g,a) =   33  26626  26626, #gen drafts =  26626, #acc drafts = 24180, #gen tokens =  79878, #acc tokens = 64407, #mean acc len = 3.42
```

Parse `slot print_timing` for:
- `eval time = X ms / Y tokens = Z tok/s` — actual decode speed (with MTP)
- `draft acceptance = R (A accepted / G generated)` — overall acceptance rate
- `draft-mtp: #acc rate/pos = (p1, p2, p3)` — per-position acceptance for MTP heads
- `ngram-mod: #acc rate/pos = (...)` — per-position acceptance for ngram

## Pitfall 4: Server logs are ground truth

When comparing llama.cpp versions, the server's `slot print_timing` logs are MORE accurate than any API endpoint:

```
39.12.567.159 I slot print_timing: id  0 | task 27623 |        eval time =   11516.59 ms /   971 tokens (   11.86 ms per token,    84.31 tokens per second)
```

This 84.31 tok/s is the definitive number for that generation run.

## Corrected results (Qwen3.6-27B AutoRound Q6_K, RTX 5090)

| Metric | Before (12/06) | After (16/06, b9671) | Real Δ |
|---|---|---|---|
| Decode con MTP (largo, 971 tok) | 80-140 tok/s | **84.31 tok/s** | **-5% a +6%** |
| Decode con MTP (corto, 256 tok) | 80-140 tok/s | **100.52 tok/s** | **-20% a +25%** |
| Decode base (sin MTP) | 42-47 tok/s | 100.5 tok/s | **+115-140%** |
| Prefill cold | 2,200-2,800 tok/s | 2,369-2,524 tok/s | ~igual |
| Draft acceptance (MTP) | 50-90% | 74.3% | dentro del rango |

**Verdict:** llama.cpp b9671 vs b9085: **NO mejora significativa en decode+MTP**. Los números son esencialmente iguales. La mejora de +115% en decode base es real pero probablemente se debe a que el benchmark anterior medía con MTP activo y el nuevo test sin MTP era un caso diferente. Los cambios de b9085→b9671 (MTP padding removal, out_prod batched) son optimizaciones marginales que no se notan en la práctica.

## Key server config to verify before benchmarking

```bash
curl http://SERVER/props | python3 -c "import sys,json; p=json.load(sys.stdin); print(p.get('default_generation_settings',{}).get('params',{}).get('speculative.types','N/A'))"
```

If `speculative.types` is `"none"`, MTP is inactive — you're measuring base decode only.

## Pitfall 5: MTP acceptance rate ≠ generation speed (15/07 discovery)

**Critical pitfall:** Higher MTP acceptance rate does NOT guarantee higher generation speed. On 15/07, a llama.cpp update showed:

- MTP acceptance: **+17-25pp improvement** (75-88% vs 50-86%)
- Generation speed: **-18-25% regression** (98-113 tok/s vs 125-150 tok/s)

**Why:** The speculative decoding is more efficient (more correct drafts), but the **base decode kernel** (used when drafts are rejected) regressed. When MTP acceptance is high, you'd expect faster speeds — but if the fallback path is slower, the net effect can be negative.

**Lesson:** Always benchmark BOTH MTP acceptance AND raw generation speed. A llama.cpp update can improve one while hurting the other. Check `timings.predicted_per_second` from the server, not just draft acceptance.

## Pitfall 6: Warmup / draft KV cache effects

The `dflash-benchmark-warmup.py` script does a 1024-token warmup before measuring. This fills the draft KV cache and gives more realistic MTP acceptance numbers. However:

- **Run 1 post-warmup** is the most reliable cold measurement
- Subsequent runs show declining acceptance (55-61% on run 3 for short prompts) — the draft cache saturates with stale patterns
- For version comparison, always compare **run 1** values

## dflash-benchmark.py — Current state (2026-06-16)

The script has been rewritten to:
1. Use **server-reported timings exclusively** (`timings.predicted_ms`, `timings.prompt_ms`)
2. Show `server: X ms` in output (not client wall-clock)
3. Request `timings_per_token: true` on both `/completion` and `/v1/chat/completions`
4. Display speculative stats when available (though MTP stats are NOT populated by the API)
5. Default to `--runs 1` to avoid ngram cache contamination

## Quick HTTP streaming benchmark (when scripts unavailable)

When `dflash-benchmark.py` is not available (e.g., fresh session), use this inline Python to measure generation speed via the `/v1/chat/completions` streaming endpoint:

```python
import urllib.request, json, time

def benchmark(prompt, max_t):
    req = urllib.request.Request(
        'http://172.23.176.1:30000/v1/chat/completions',
        data=json.dumps({
            'model': 'qwen3.6-27b',
            'messages': [{'role':'user','content': prompt}],
            'max_tokens': max_t, 'stream': True, 'temperature': 0.7
        }).encode(),
        headers={'Content-Type':'application/json'}
    )
    start = time.time()
    ttfb = None; tokens = 0; prev = None
    with urllib.request.urlopen(req, timeout=600) as resp:
        for line in resp:
            line = line.decode().strip()
            if not line or not line.startswith('data:'): continue
            if line.startswith('data: [DONE]'): break
            now = time.time()
            if ttfb is None: ttfb = now - start
            prev = now; tokens += 1
    total = time.time() - start
    gen_time = total - ttfb
    print(f'Tokens: {tokens} | TTFB: {ttfb:.3f}s | Gen: {gen_time:.3f}s | Speed: {tokens/gen_time:.1f} tok/s')

benchmark('Escribe un resumen detallado...', 2000)
```

This measures client-side streaming speed. It's slightly less accurate than server timings but useful for quick checks.
