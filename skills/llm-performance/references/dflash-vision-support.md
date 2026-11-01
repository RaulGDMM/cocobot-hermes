# DFlash + Vision Models Support

## SGLang — Qwen3-VL (PR #18387)

### Status
- PR: https://github.com/sgl-project/sglang/pull/18387
- Author: @EanWang211123, @dcw02
- Status: Awaiting review from multiple code owners
- Dependency: Requires PR #16818 (base DFlash integration)

### Performance (NVIDIA 4090D)
| Metric | DFlash | Baseline |
|---|---|---|
| Throughput (tok/s) | 45.48 | 23.60 |
| Acceptance Length | 2.8 | N/A |
| Speedup | ~1.92x | — |

### Key Implementation Details
- Follows standalone-style multimodal speculative decoding (e.g., Qwen3-8B-VL + Qwen3-0.6B)
- Reuses MRoPE adaptation logic for consistent multimodal handling
- **Bug fix**: SHM feature decoding failure on first image request with tp_size=2
  - Root cause: DFlash draft worker initialization deepcopy'd server_args with skip_tokenizer_init=True, overwriting global server_args
  - Fix: Save and restore global server_args after DFlash worker initialization in dflash_worker.py

### Source
- PR: https://github.com/sgl-project/sglang/pull/18387
- Benchmark: `benchmark/dflash/bench_dflash_mmstar.py`
- Model: `python/sglang/srt/models/qwen3_vl.py`

## BeeLlama.cpp — Multimodal Support

### Status
- Fully working in BeeLlama.cpp
- Flat DFlash allowed with `--mmproj`
- Tree DFlash and non-DFlash spec decode disabled when mmproj is loaded

### Setup
```bash
./llama-server \
  -m target-model.gguf \
  --mmproj mmproj-BF16.gguf \
  --spec-type dflash \
  --spec-draft-model draft-model.gguf \
  --no-mmproj-offload  # Run mmproj on CPU to save VRAM (skip on macOS/unified memory)
```

### Limitations
- Only **flat DFlash** works with multimodal (no tree/branch budget)
- Non-DFlash speculative decoding is disabled when mmproj is loaded
- mmproj adds ~0.5GB VRAM if offloaded to GPU

### Source
- Quickstart: `docs/quickstart-qwen36-dflash.md`
- Features: `docs/beellama-features.md`
- GitHub: https://github.com/Anbeeld/beellama.cpp
