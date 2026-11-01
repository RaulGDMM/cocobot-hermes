# Unsloth NVFP4 ecosystem: vLLM-only, no official GGUF (verified 2026-08-19)

Session: Raúl asked why Unsloth has no NVFP4 GGUF for llama.cpp ("lo tengo de utautako,
¿no lo sacan ellos mismos?"). Research findings:

## Facts (verified via web_search + HF tree API)

- **Unsloth DOES have NVFP4** — "Dynamic NVFP4" launched July 10, 2026 (Qwen3.6 first,
  claimed ~2.5x faster than other NVFP4 quants + FP8 KV calibration). Qwen3.8 versions
  use **Unsloth Dynamic V3.0 (preview)**. HF collection: `unsloth/nvfp4`
  (https://huggingface.co/collections/unsloth/nvfp4).
- `unsloth/Qwen3.8-27B-NVFP4` updated 2026-08-18. Tree (verified via
  `https://huggingface.co/api/models/unsloth/Qwen3.8-27B-NVFP4/tree/main`):
  `model.safetensors` 21.5 GB + `model_mtp.safetensors` 810 MB. **NO mmproj file** —
  the vision tower is embedded in the checkpoint (text-only for llama.cpp purposes).
  README: "This quant ONLY works in vLLM and **NOT SGLang**. The lm_head is quantized
  to FP8 and SGLang can't load it."
- Format: `compressed-tensors` mixed-precision (the format vLLM uses). **Not GGUF.
  Unsloth does not ship official NVFP4 GGUFs.**
- llama.cpp path = **community repacks to GGUF**:
  - `CodeFault/Unsloth-Qwen3.6-27B-NVFP4-GGUF` (3.6; converted with llama.cpp's
    converter after patching the convert script — the unsloth checkpoint uses
    `quant_method: compressed-tensors` + `format: mixed-precision` which fails
    out of the box; NVIDIA's own NVFP4 checkpoint converts cleanly).
  - esatapedico/Qwen3.8-27B-NVFP4-MTP-GGUF (8 tiers, built from the unsloth 3.8 source).
  - utautako/Qwen3.8-27B-NVFP4-MTP-Q8attn — independent ModelOpt self-quant, NOT
    derived from unsloth.
- Blog documenting the repack: boredconsultant.com "45 tok/s on a Laptop: Getting
  Qwen3.6-27B's NVFP4 Quants Running on llama.cpp" (2026-07-18).
- Community had already noticed the gap: in unsloth's own announcement thread
  (r/LocalLLaMA "2.5x faster Qwen3.6 NVFP4 Unsloth quants"), a comment asks whether
  llama-server's NVFP4 support is "good enough ... to make sense to offer GGUF
  conversions of these". No official unsloth answer found.

## Why they likely don't ship GGUF (analysis — label as such, not as fact)

1. NVFP4 kernel work is centered on vLLM (Marlin / FlashInfer / cutlass / cute-DSL
   — that's their docs' comparison surface).
2. GGUF K-quants (Dynamic 2.0) are the universal product: run on any GPU including
   Apple Silicon. An NVFP4 GGUF is Blackwell-only (RTX 50, B200/B300, DGX Spark) —
   a narrower artifact. Their docs steer non-Blackwell users to K-quant GGUFs.
3. Brand protection: they benchmark (Aider Polyglot, MMLU 5-shot, KL divergence) and
   own the quality claims. A GGUF whose quality suffers from llama.cpp kernel
   immaturity would land on their name.
4. Pipeline friction: the mixed-precision compressed-tensors checkpoint needs a
   ~3-line patch to the convert script; K-quants have the clean pipeline.

## vLLM vs llama.cpp for single-user agent workloads

- **User-measured (Raúl, months ago, RTX 5090): vLLM was less memory-efficient —
  he had to run less context than llama.cpp for the same model.**
- Structural cause: vLLM pins KV to VRAM. llama.cpp has `--cache-ram` +
  `--kv-unified` (KV/prompt cache can overflow to system RAM).
- **Heuristic: do NOT switch engines to vLLM just to test a vendor's vLLM-only NVFP4
  quant in a single-user agentic setup.** Test the community GGUF repack of the same
  quant in llama.cpp (one-line profile swap when already profiled). vLLM's real
  advantages (multi-user throughput, fastest FP4 prefill) don't apply to
  single-session agentic use; llama.cpp wins on flexible KV, MTP+ngram maturity for
  hybrid DeltaNet models, and native Windows.

## Answer pattern for future sessions

- "¿Tiene Unsloth NVFP4 para llama.cpp?" → official NVFP4 exists but is vLLM-only
  (compressed-tensors); llama.cpp users get community GGUF repacks; watch for an
  official GGUF if llama.cpp NVFP4 matures.
- "¿Tiene sentido probar vLLM con ese quant?" → No, unless the user explicitly wants
  to serve multi-user; the memory/ctx cost was already measured. Use the GGUF repack.
