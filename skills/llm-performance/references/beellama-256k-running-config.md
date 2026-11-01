# BeeLlama.cpp 256K Context Running Config

Validated by user (May 2026) on RTX 5090 (32GB, Ada Lovelace SM 90).

## Running Configuration

```
Target:       Qwen3.6-27B-Q5_K_S.gguf
Draft:        Qwen3.6-27B-DFlash-Q4_K_M.gguf
KV Cache:     turbo4 (K), turbo3_tcq (V)
mmproj:       mmproj-BF16.gguf (--no-mmproj-offload)
Context:      262144 (256K)
Batch:        2048
Ubatch:       2048
Parallel:     1
Checkpoint:   every 8192 tokens
DFlash cross-ctx: 1024
DFlash draft-n-max: 16
DFlash dm-controller: profit
Reasoning:    on
Flash-attn:   on
MMproj:       CPU (--no-mmproj-offload)
Chat template: preserve_thinking=true
```

## Key Observations

- **256K context works** with turbo4/turbo3_tcq on 32GB VRAM
- **ubatch 2048** significantly improves prefill speed vs 512, especially with image prompts
- **checkpoint-every-n-tokens 8192** enables incremental re-inference when context grows beyond initial size
- **preserve_thinking:true** is mandatory for Qwen3.6 CoT — without it, thinking tags are stripped and model gets confused
- **--no-mmproj-offload** keeps vision projector on CPU, saving ~2-3GB VRAM for KV cache

## Tuning Notes

- If OOM: reduce checkpoint interval to 16384 (fewer checkpoints, less VRAM)
- If prefill slow with images: try ubatch 4096
- DFlash flags to consider:
  - `--spec-dflash-cross-ctx 1024` (more context visible to drafter → better acceptance)
  - `--spec-draft-n-max 16` (block size; 16 gives more speedup if drafter is good)
  - `--spec-dm-controller profit` (adaptive draft depth)

## Sources

- BeeLlama.cpp: fork of llama.cpp with DFlash + TurboQuant + vision support
- DFlash draft models: z-lab/Qwen3.6-27B-DFlash on HuggingFace
- GGUF target: Unsloth or cHunter quantizations
