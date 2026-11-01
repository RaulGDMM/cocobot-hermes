# Speculative Decoding — D-Flash & MTP Research Notes

## MTP (Multi-Token Prediction)

### What it is
Built into Qwen3.6 and Qwen3.5 model architecture. Additional prediction heads forecast N future tokens per forward pass. Verified within the same model.

### Qwen3.6 specifics
- Up to **2 extra tokens per step** (native, no draft model)
### GGUF naming: `UD-` prefix = Unified Decoder (MTP variant)
- llama.cpp auto-detects from GGUF metadata → no flags needed
- ⚠️ **WARNING: UD naming is NOT reliable**. Some GGUFs carry "UD" in the filename but lack MTP tensors. The architecture field in the GGUF metadata is the authoritative source (see "Verify MTP presence in GGUF" below).

### Verify MTP presence in GGUF (before trusting the filename)
The GGUF filename can be misleading. Example: `Qwen3.6-27B-UD-Q4_K_XL.gguf` was found to have `qwen35` architecture with SSM layers and **no MTP tensors**. Always verify:

**Method 1 — inspect GGUF metadata (no Python deps needed):**
```bash
# Read architecture from first 2MB of GGUF (metadata lives at start of file)
dd if=/path/to/model.gguf bs=1M count=2 2>/dev/null | strings | grep -E '^(general\.|qwen|arch\.)' | head -20
```
- `general.architecture` → should be `qwen3` or `qwen36` for Qwen3.6 with MTP
- `qwen35.*` → hybrid SSM-Transformer (Qwen3.5), **no MTP**
- `llama` → standard Llama, no MTP

**Method 2 — search for MTP tensors:**
```bash
dd if=/path/to/model.gguf bs=1M count=3 2>/dev/null | strings | grep -E '^mtp'
```
- If empty → **no MTP tensors** in the file
- Expected: `mtp.0`, `mtp_heads`, `mtp_norms`, etc.

**Method 3 — llama-server log:**
- Look for: `n_mtp_queries: N`, `Using MTP`, or `speculative decoding`
- Absence of these messages ≠ MTP disabled, but combined with methods 1+2 it confirms

**Method 4 — performance test (RTX 5090, Q4_K_XL 27B):**
- Without MTP: ~25-35 tok/s (greedy), ~70 tok/s with SSM hybrid
- With MTP active: ~40-80 tok/s (depends on acceptance rate)
- Note: SSM hybrid models (qwen35) can be fast without MTP, so speed alone is inconclusive

### Verify MTP is active at runtime
1. Check llama-server log: `n_mtp_queries: N` or `Using MTP`
2. Performance test: ~25-30 tok/s without vs ~40-80 tok/s with (RTX 5090, Qwen3.6-27B Q4)
3. GGUF contains tensors: `*.mtp_heads.*`, `*.mtp_norms.*`

---

## D-Flash (Block Diffusion Drafting)

### What it is
By Z-Lab (Feb 2026 paper). Uses a lightweight **block diffusion model** to draft entire token blocks in a single forward pass, conditioned on hidden states from the target model. Not autoregressive — constant-time drafting.

**Claims**: 6x speedup over standard AR, 2.5x faster than EAGLE-3. Real-world: 2-3.5x for Qwen models.

### How it works
1. Target LLM produces hidden states (deep context features)
2. Block diffusion drafter (5-layer, k=5 fused context vectors) proposes N tokens in parallel
3. Target model verifies entire block in a single batched forward pass
4. Lossless & distribution-preserving (matches target greedy output)

### Draft models (HuggingFace)
| Base Model | Draft Model |
|---|---|
| Qwen3.6-27B | `z-lab/Qwen3.6-27B-DFlash` |
| Qwen3.6-35B-A3B | `z-lab/Qwen3.6-35B-A3B-DFlash` |
| Qwen3.5-122B-A10B | `z-lab/Qwen3.5-122B-A10B-DFlash` |
| Qwen3.5-4B/9B/27B | Collection on z-lab |

### vLLM integration
- **Status**: Requires PR #40898 (causal SWA layer support)
- **Without fix**: Acceptance rates ~6-15% (interleaved SWA layers not supported in main branch)
- **With fix**: ~10.5% avg acceptance. Coding tasks peak at ~60 TPS
- **Usage**: `vllm serve --speculative-config '{"method": "dflash", "model": "z-lab/Qwen3.6-27B-DFlash", "num_speculative_tokens": 15}'`
- **num_speculative_tokens tuning**: Start at 4, not 15. Per-position acceptance drops to 0.000 after position 8 with 15 tokens

### llama.cpp integration (MTP)
**Merged in main llama.cpp b9180 (May 16, 2026)** — no forks needed.

- **Compatible models**: DeepSeek V3, Qwen3.5, **Qwen3.6** — all upstream in main
- **Usage**: `--spec-type draft-mtp --spec-draft-n-max 3` (or 4-5 for more aggressive speculation)

#### Per-request speculative config (dynamic n_max)
The CLI flags (`--spec-draft-n-max`, `--spec-draft-n-min`, etc.) are fixed at server startup. However, the server API **does accept a `speculative` field in the request body** to override draft token count per-request:

```json
POST /v1/completions
{
  "prompt": "...",
  "max_tokens": 256,
  "temperature": 0,
  "speculative": {"n_max": 2}
}
```

- Works on `/v1/completions`, `/v1/chat/completions`, and `/completion` endpoints
- Per-request `n_max` cannot exceed the global `--spec-draft-n-max` set at startup (that is the hard ceiling)
- Allows tuning speculation aggressiveness per task: lower `n_max` for creative/unpredictable output, higher for repetitive/code tasks
- ⚠️ Not officially documented in the server README — observed in practice (issue [#23658](https://github.com/ggml-org/llama.cpp/issues/23658)). Only `n_max` (and likely `n_min`) are supported; `p_min`, `p_split`, and `spec-type` are NOT adjustable per-request
- `POST /props` (with `--props` flag) changes global settings but does NOT appear to include speculative params — only sampling params (temperature, top_p, etc.)
- **Ollama**: Merged MTP ~May 2026, pre-release available
- **vLLM / SGLang**: Full MTP support
- **Performance**: 1.5x-2.5x throughput, ~80% acceptance rate (benchmarks from mlx-lm Qwen3.5: 15.3→23.3 tok/s on 27B Q4, M4 Pro). Qwen3.6-27B MTP n=3: ~87%/72%/61% acceptance per position, mean accepted length ≈ 3.0-4.0.

**GGUF repos with MTP tensors** (b9180+ required):
- `froggeric/Qwen3.6-27B-MTP-GGUF` — Q4-Q8 variants, text+vision
- `unsloth/Qwen3.6-27B-MTP-GGUF` — UD variants with MTP
- Verify MTP presence before trusting filename (see "Verify MTP presence in GGUF" above)
- **⚠️ Known issues (May 2026)**:
  - **Vision + MTP INCOMPATIBLE (permanent)**: Issue [#19712](https://github.com/ggml-org/llama.cpp/issues/19712) — **CLOSED** (stale, Mar 2026, feature request not implemented). Speculative decoding is NOT supported with multimodal models (`--mmproj`). Error: `srv load_model: speculative decoding is not supported with multimodal`. MTP heads are trained on text-only representations; vision tokens corrupt slot positions and cause OOM. You CANNOT use MTP and vision in the same server instance — no toggle per-request exists.
  - **Save/restore KV cache blocked**: Issues #19466, #21173, #21133 — slot logic marks all slots as multimodal when `--mmproj` loaded, preventing checkpoint save/restore
  - **Device state save/load is text-only**: PR #22805 (b9064) fixed buffer offsets in recurrent cache restoration, but saved state only includes KV cache + RNG + logits + embeddings. **Vision embeddings and encoder state are NOT saved.** Restoring state after processing images loses visual context — you must re-send images on restore.
  - **GGUF requirement**: Need GGUFs with MTP tensors included — not all HuggingFace GGUFs have them
- **Recommendation**: Wait for stabilization if you use vision models. Beta is usable for text-only Qwen3.5/3.6.

### Alternative: MTP Drafters (separate model approach)
- **Google Gemma 4 MTP drafters** (released May 5, 2026): Standalone drafter models paired with each Gemma 4 variant (31B, 26B A4B, E2B, E4B). Up to 3x speedup. Same output as target model.
- Supported by: Transformers, MLX, vLLM, SGLang, Ollama, LiteRT-LM
- **llama.cpp**: Feature request open at [#22747](https://github.com/ggml-org/llama.cpp/issues/22747) — not yet implemented
- Different from integrated MTP: uses a separate lightweight drafter model + speculative decoding, not MTP heads baked into the target model

### Performance benchmarks
- Qwen3.5-35B-A3B: 2-2.8x speedup
- Qwen3.5-9B: up to 3.5x speedup
- Qwen3.6-27B: **modest vs MTP** — does NOT consistently beat native MTP

### Limitations
- Draft model still under active training (preview status for Qwen3.6-27B)
- Quantized target models (AWQ etc.) hurt acceptance rates
- Fixed block size — no adaptive sizing
- Only Linux (vLLM/SGLang). No Windows support

### When D-Flash is useful
- Models WITHOUT native MTP (Llama, Mistral, Phi)
- Qwen3.5-A3B variants (MTP is weak or absent)
- Linux-only environments with vLLM + PR #40898
- **NOT useful** for Qwen3.6 on Windows with llama.cpp (MTP native is better)

### TurboQuant Status (main vs forks)

**What IS in main llama.cpp (b9180+):**
- **Walsh-Hadamard rotation** (PR #21038 by ggerganov) — the core TurboQuant primitive for rotating activations before quantization. Enables `turbo3` KV cache (3-bit WH rotation) that fits 262K context in 24GB VRAM (~8GB KV vs ~12GB for q4_0).
- **Fast Walsh-Hadamard transform** (PR #22631, b9026) — optimized FWT kernel for KV rotation.

**What is NOT in main (forks only):**
- **Full TurboQuant stack** (`tbq3_0`, `tbq4_0` quant types) — PR #21089 **rejected** by maintainers (too large, code quality concerns). Available in `TheTom/llama-cpp-turboquant` fork.
- **TurboQuant+** (attention-gated sparse dequantization, layer-aware V compression) — fork only (`TheTom/llama-cpp-turboquant`).
- **Triton GPU kernels** for TurboQuant — fork only; main has CPU implementation.

**Practical implication**: For llama.cpp/BeeLlama on Blackwell, main branch (b9180+) already has the core WH rotation primitives needed for turbo3 KV cache. The fork adds optimized GPU kernels and extended quant types but the fundamental rotation is in main.

### References
- Paper: https://arxiv.org/abs/2602.06036
- GitHub: https://github.com/z-lab/dflash
- HF Models: https://huggingface.co/collections/z-lab/dflash
- llama.cpp Discussion: https://github.com/ggml-org/llama.cpp/discussions/21569
- llama.cpp PR: https://github.com/ggml-org/llama.cpp/pull/22105
- vLLM PR: https://github.com/vllm-project/vllm/issues/32094
- TurboQuant PR (rejected): https://github.com/ggml-org/llama.cpp/pull/21089
- WH Rotation PR (merged): https://github.com/ggml-org/llama.cpp/pull/21038
- TurboQuant fork: https://github.com/TheTom/llama-cpp-turboquant
