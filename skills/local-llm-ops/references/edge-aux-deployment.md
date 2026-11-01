# Edge / Auxiliary Model Deployment (Pi 5 / mini PC)

Full runbook absorbed from the former `local-auxiliary-model` skill. Deploy a local GGUF model on a Raspberry Pi or mini PC as an OpenAI-compatible auxiliary server for Hermes Agent, offloading non-critical tasks from your main GPU server.

## When to Use

- Free up cache-ram on your main inference server (RTX 5090, etc.)
- Offload async auxiliary tasks to a low-cost edge device
- Reduce context pressure on the main model during compression
- Run Hermes auxiliary tasks without cloud API calls

## Model Selection

For edge devices (Pi 5, mini PC, old laptop):

| Model | Size (Q4_K_M) | MTP | Notes |
|---|---|---|---|
| Qwen3.5-4B-MTP | 2.78 GB | ✅ | Best quality, native MTP |
| Qwen3-4B | 2.4 GB | ❌ | No MTP, slower gen |
| Qwen3-1.7B | ~1.2 GB | ❌ | Fastest, lower quality |
| Qwen3-0.6B | ~0.5 GB | ❌ | Ultra-fast, basic tasks only |

**Recommendation:** Qwen3.5-4B-MTP for quality + MTP speedup. Source: `prithivMLmods/Qwen3.5-4B-MTP-GGUF` on HuggingFace.

## Build llama.cpp on Pi 5 / ARM

### Option 1: OpenBLAS (simpler, baseline)
```bash
sudo apt-get install -y cmake build-essential libopenblas-dev
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS
cmake --build build --target llama-server llama-cli
```

### Option 2: BLIS (RECOMMENDED — +40% prompt processing speed)
```bash
sudo apt-get install -y cmake build-essential libblis-dev
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
rm -rf build && mkdir build
cd build
cmake .. -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=Generic \
  -DBLAS_LIBRARIES=/usr/lib/aarch64-linux-gnu/libblis.so \
  -DBLAS_INCLUDE_DIRS=/usr/include/aarch64-linux-gnu
make -j4 llama-server llama-cli
```

**Why BLIS?** BLIS is significantly faster on ARM64 than OpenBLAS, especially for matrix operations in prompt processing. Benchmarks show **+42-43% improvement** at 4K-6K tokens and consistent gains across all batch sizes.

| Tokens | OpenBLAS | BLIS | Improvement |
|--------|----------|------|-------------|
| 2,048 | 14.87 t/s | 15.57 t/s | +5% |
| 4,096 | 9.68 t/s | 13.75 t/s | **+42%** |
| 6,144 | 8.62 t/s | 12.35 t/s | **+43%** |
| 10,240 | - | 10.25 t/s | - |
| 20,480 | - | 7.15 t/s | - |

**Note:** BLIS requires manual path specification because `pkg-config` doesn't ship a `.pc` file for BLIS on Debian/Ubuntu ARM.

## Download Model

```bash
mkdir -p ~/models
curl -L -o ~/models/Qwen3.5-4B-MTP-Q4_K_M.gguf \
  'https://huggingface.co/prithivMLmods/Qwen3.5-4B-MTP-GGUF/resolve/main/Qwen3.5-4B.Q4_K_M.gguf'
```

## Server Command

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen3.5-4B-MTP-Q4_K_M.gguf \
  -t 4 -tb 4 \
  -c 98304 \
  --cache-type-k q5_1 --cache-type-v q4_0 \
  --host 0.0.0.0 \
  --port 8082 \
  --ubatch-size 2048 \
  --spec-type draft-mtp,ngram-simple \
  --spec-draft-n-max 3 \
  --reasoning off
```

**Flags explained:**
- `-c 98304` — context size. 96K is the sweet spot on Pi 5 (128K causes swap thrashing with active si/so)
- `--cache-type-k q5_1 --cache-type-v q4_0` — KV cache quantization. Reduces memory per token from 52B to 18B. Enables 96K context without OOM.
- `--ubatch-size 2048` — physical batch size. Improves prompt processing speed by 10-20%.
- `--spec-type draft-mtp,ngram-simple` — combined speculative decoding. MTP for model predictions, ngram for pattern repetition. Both work together.
- `--spec-draft-n-max 3` — max 3 draft tokens per MTP step
- `--reasoning off` — disables thinking mode (Qwen3.5 thinks by default). Use `--chat-template-kwargs '{"enable_thinking": false}'` on older llama.cpp versions.

## BLIS Build Notes

When building with BLIS on ARM64, the Pi may become unresponsive to SSH during compilation (4 cores at 100%). Use `nohup` and expect SSH timeouts:
```bash
cd ~/llama.cpp/build && nohup make -j4 llama-server llama-cli > /tmp/make.log 2>&1 &
# Wait 5-10 minutes, then check: tail -5 /tmp/make.log
```

**Flash Attention on CPU?** Not available. Flash Attention in llama.cpp is a CUDA-only feature (`GGML_CUDA_FA=ON`). For CPU/ARM the real improvements come from BLIS (+40% prompt processing) and `--ubatch-size`.

## KV Cache Math

For Qwen3.5-4B: 32 layers, 4 KV heads, **128 head_dim**

### Current config: K Q5_1 + V Q4_0 (~18 bytes/token)

| Component | Bytes/token | Formula |
|---|---|---|
| K (Q5_1) | 9 | `32 × 4 × 128 × 0.625B` |
| V (Q4_0) | 9 | `32 × 4 × 128 × 0.5B` |
| **Total** | **18** | **18 KB/token** |

| Context | KV Cache | Model + KV | RAM Needed |
|---|---|---|---|
| 8K | 144 MB | ~2.9 GB | OK |
| 16K | 288 MB | ~3.1 GB | OK |
| 32K | 576 MB | ~3.4 GB | OK |
| 64K | 1.15 GB | ~4.0 GB | OK |
| 96K | 1.73 GB | ~4.5 GB | OK |
| 128K | 2.3 GB | ~5.1 GB | Swap thrashing on Pi 5 |

### Previous config: K Q8_0 + V Q5_1 (~26 bytes/token) — DO NOT USE

| Context | KV Cache | Notes |
|---|---|---|
| 96K | 2.5 GB | +800 MB vs Q5_1/Q4_0 — not worth the quality gain |

**Rule of thumb:** Leave at least 1.5 GB free for OS + other services. On a Pi 5 with 7.9 GB total, **96K is the practical max** (128K causes swap thrashing with active si/so in `vmstat`).

**Why Q5_1/Q4_0 over Q8_0/Q5_1?** The quality difference is negligible for auxiliary tasks (classification, titles, triage), but the memory savings (~800 MB at 96K) are the difference between stable operation and swap thrashing.

## systemd Service (Auto-start)

```ini
# /etc/systemd/system/llama-server.service
[Unit]
Description=llama.cpp server (Qwen3.5-4B-MTP)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=cocobot
WorkingDirectory=/home/cocobot/llama.cpp/build
ExecStart=/home/cocobot/llama.cpp/build/bin/llama-server \
  -m /home/cocobot/models/Qwen3.5-4B-MTP-Q4_K_M.gguf \
  -t 4 -tb 4 -c 98304 \
  --cache-type-k q5_1 --cache-type-v q4_0 \
  --host 0.0.0.0 --port 8082 \
  --ubatch-size 2048 \
  --spec-type draft-mtp,ngram-simple --spec-draft-n-max 3 \
  --reasoning off
Restart=on-failure
RestartSec=10
StandardOutput=append:/home/cocobot/llama-server.log
StandardError=append:/home/cocobot/llama-server.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo mv llama-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable llama-server
sudo systemctl start llama-server
```

## Hermes Auxiliary Task Routing

Configure each auxiliary task independently via `hermes config set`:
```bash
# Point a task to the auxiliary server
hermes config set auxiliary.skills_hub.provider custom
hermes config set auxiliary.skills_hub.base_url http://<PI_IP>:8082/v1
```

**Recommended routing strategy:**

| Task | Provider | Reason |
|---|---|---|
| compression | auto (main) | Quality + speed critical |
| vision | auto (main) | High precision needed |
| web_extract | auto (main) | Long prompts, quality matters |
| session_search | auto (main) | Semantic search accuracy |
| mcp | auto (main) | Tool schema understanding |
| background_review | auto (main) | **40K+ tokens too slow on Pi (~40+ min)** |
| skills_hub | custom (edge) | Tolerates latency |
| title_generation | custom (edge) | Short output, fast |
| triage_specifier | custom (edge) | Classification, ~5 t/s OK |
| approval | custom (edge) | Simple decisions |
| tts_audio_tags | custom (edge) | Fast, short |
| kanban_decomposer | custom (edge) | Async |
| profile_describer | custom (edge) | Tolerates latency |
| curator | custom (edge) | Async, periodic |
| monitor | custom (edge) | Async |
| flush_memories | custom (edge) | Async |
| memory_query_rewrite | custom (edge) | Short queries |
| goal_judge | custom (edge) | Async |
| moa_reference | custom (edge) | Async |
| moa_aggregator | custom (edge) | Async |

**Benefit:** ~15 tasks offloaded, freeing main server cache-ram for compression and other latency-sensitive work.

## Performance Benchmarks (Pi 5, 4 cores, BLIS)

### Prompt processing (BLIS vs OpenBLAS)

| Tokens | OpenBLAS | BLIS | Improvement |
|--------|----------|------|-------------|
| 2,048 | 14.87 t/s | 15.57 t/s | +5% |
| 4,096 | 9.68 t/s | 13.75 t/s | **+42%** |
| 6,144 | 8.62 t/s | 12.35 t/s | **+43%** |
| 10,240 | - | 10.25 t/s | - |
| 20,480 | - | 7.15 t/s | - |

### Generation (with MTP + ngram)

| Task | Prompt t/s | Gen t/s | Notes |
|---|---|---|---|
| Poem (150 tokens) | 14.1 | 3.2 | MTP active |
| Classification (20 tokens) | 14.9 | 5.3 | Short output = faster |
| Entity extraction (100 tokens) | 16.6 | 6.2 | Structured output |
| Compression (200 tokens) | 16.7 | 4.9 | ~40s for 200 tokens |
| Hello (15 tokens) | 12.2 | 7.2 | MTP 100% hit |

### background_review timing

A `background_review` with ~40K tokens of context takes **~40-50 minutes** on the Pi (at ~7-14 t/s prompt processing). This exceeds the default 120s timeout and even the 5400s (90 min) timeout is tight. **Recommendation: keep `background_review` on the main GPU server** — it completes in ~3 minutes there.

**Key insight:** Short outputs (classification, titles) are fast enough (~5-6 t/s). Long outputs (200+ tokens) take 30-40 seconds — acceptable for async tasks, NOT for real-time interaction. Long context tasks (>20K tokens) should stay on the GPU.

## Verify MTP is Working

```bash
# Check server log for draft acceptance
grep 'draft acceptance' /home/cocobot/llama-server.log
# Expected: draft acceptance = 0.85-0.95
```

An 89.5% acceptance rate means MTP is working well. Below 60% indicates a problem.

## Common Pitfalls

1. **`--spec-type mtp` fails:** Use `--spec-type draft-mtp`. Valid types: `none,draft-simple,draft-eagle3,draft-mtp,draft-dflash,ngram-simple,...`
2. **Thinking mode always on:** Qwen3.5 generates reasoning by default. Use `--chat-template-kwargs '{"enable_thinking": false}'` or `--reasoning off`. The `extra_body` approach in the API does NOT work.
3. **Port conflicts:** 8080/8081 often occupied. Use 8082 or check with `ss -tlnp`.
4. **Slow HuggingFace download:** 2.8 GB can take 10-15 minutes on Pi. Run with `nohup`.
5. **RAM pressure at 32K:** Monitor with `free -h`. Pi had 1.8 GB free + 1 GB swap after loading model at 32K.
6. **Gateway restart blocked from inside:** Cannot run `hermes gateway restart` from within the gateway process (SIGTERM propagates). Restart from outside or use a detached subprocess.
7. **`session_search` and `flush_memories` warnings:** `hermes config set` may warn these are "not recognized config keys" but they are saved and used. This is expected behavior.
8. **128K context causes swap thrashing:** At 128K, the Pi runs out of RAM and starts active swap in/out (`vmstat` shows si/so > 0). Curls hang, latency degrades. **96K is the hard limit.**
9. **Cannot cancel running tasks via API:** llama.cpp has no `/cancel` endpoint. To kill a long-running task, restart the systemd service: `sudo systemctl restart llama-server`.
10. **SSH unresponsive during compilation:** `make -j4` saturates all 4 cores. SSH times out. Use `nohup` and wait before reconnecting.
11. **`background_review` too slow on Pi:** With 40K+ tokens of context, prompt processing takes 40-50 minutes at ~7-14 t/s. Keep this task on the main GPU server.
12. **BLIS not found by pkg-config:** BLIS doesn't ship a `.pc` file on Debian/ARM. You must specify paths manually: `-DBLAS_LIBRARIES=/usr/lib/aarch64-linux-gnu/libblis.so -DBLAS_INCLUDE_DIRS=/usr/include/aarch64-linux-gnu`.
13. **Flash Attention not available on CPU:** `GGML_CUDA_FA=ON` is GPU-only. For CPU/ARM, BLIS + `--ubatch-size` are the real prompt processing optimizations.
