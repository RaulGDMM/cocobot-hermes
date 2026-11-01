# llama.cpp Changelog: b9050 → b9085 (2026-05-07 → ~2026-05-27)

Source: https://github.com/ggml-org/llama.cpp/releases (pages 1-5)

## CUDA-relevant changes (NVIDIA RTX 50xx / Blackwell)

| Build | PR | Change |
|-------|-----|--------|
| b9066 | #22651 | Batch `out_prod` inner loop with `cublasSgemmStridedBatched`. Extended to HIP/MUSA. |
| b9075 | #22667 | CUDA snake activation fusion (`ggml_cuda_op_snake_fused`, F32/F16/BF16). Fuses 5-op decomposition from BigVGAN/Vocos audio decoders. |
| b9073 | #22820 | PCI bus ID lower-cased for ggml consistency. |
| b9010 | #22533 | Fix PCI bus ID de-dupe OOM (ignored other GPUs). Extended to HIP/MUSA. |

## Server / API changes

| Build | PR | Change |
|-------|-----|--------|
| b9077 | #22545 | Vertex AI compatible API support (`AIP_MODE` env var). |
| b9076 | #22683 | `/v1/models` exposes child model info from router. |
| b9023 | #21848 | `/models?reload=1` endpoint. |
| b9009 | #22558 | Server checkpoint: avoid host memory copies. |
| b9018 | #22649 | Added `get_datetime` server tool. |
| b9030 | #22686 | Vendor update: cpp-httplib → 0.43.3. |

## Core / common changes

| Build | PR | Change |
|-------|-----|--------|
| b9085 | #22812 | MiMo-V2.5 flash attention: MMA/Tiles for `d_kq=192 d_v=128`, GQA fix. |
| b9080 | #22804 | Model support: `Gemma4_26B_A4B_NVFP4`. |
| b9079 | #22740 | Reverted reasoning budget `+inf` logit bias. |
| b9064 | #22805 | Fix device state save/load functionality. |
| b9062 | #22634 | Chat: preserve media markers for typed-content templates. |
| b9058 | #22797 | Remove unnecessary `seq_id` check during state restore. |
| b9031 | #22290 | Only load backends when required (saves memory). |
| b9028 | #22679 | Option to save memory in device buffers. |
| b9026 | #22631 | Fast Walsh-Hadamard transform for KV rotation. |
| b9020 | #22654 | Autoparser: newline handling / forced tool call fixes. |
| b9012 | #22612 | Mistral format YaRN `apply_scale` support in `convert_hf_to_gguf.py`. |
| b9019 | #22004 | Architectural refactor: `load_hparams`/`load_tensors` per-model definition. |

## Non-relevant for CUDA (backend-specific)

- **Hexagon (Qualcomm):** b9000 (HMX flash attention overhaul), b9037 (M-tail rows), b9082 (L2_NORM), b9084 (Gated Delta Net)
- **OpenCL (Adreno):** b9006 (MoE MxFP4), b9063 (opfilter regex), b9070 (q4_0 MoE GEMM)
- **Vulkan:** b9015 (dead macro removal), b9072 (spv shadowing fix)
- **SYCL (Intel):** b9060 (FILL, CUMSUM, DIAG, SOLVE_TRI, SSM_SCAN, GATED_DELTA_NET ops)
- **WebGPU:** b9014 (layer norm ops)

## Session notes (2026-05-09)

User's setup: RTX 5090 32GB, Qwen3.6-27B Q4_K_XL, llama-server :30000 on Windows via WSL.
Binary at `E:\Workspace\Openclaw\llama-cpp\llama-server.exe`, source at `E:\Workspace\Openclaw\ik_llama.cpp-src\`.
Backups follow naming: `llama-cpp-bXXXX-backup` (last: b9010).
Veredicto: no critical updates between b9050→b9085 for single-GPU text inference. b9066 (batch optimization) and b9031 (lazy backend loading) are the most interesting for this setup.
