# vLLM vs llama.cpp — Single User vs Multi-User (2026)

## Benchmark: RTX PRO 6000 Blackwell (96GB VRAM), Qwen3.5-9B

Fuente: [Allen Kuo, Medium 2026](https://allenkuo.medium.com/vllm-or-ollama-on-blackwell-benchmarks-landmines-and-what-agents-actually-need-5dc539bb28ef)

| Métrica | Ollama/Q4_K_M (llama.cpp) | vLLM (BF16) | Vencedor |
|---|---|---|---|
| Decode speed | **134 tok/s** | 89 tok/s | llama.cpp 1.5x |
| TTFT | 129 ms | **33 ms** | vLLM 3.9x |
| Prefill (3000 tok) | 5,961 tok/s | **20,341 tok/s** | vLLM 3.4x |
| Concurrent (4 users) | 123.5 tok/s | **341.8 tok/s** | vLLM 2.8x |
| VRAM usado | **25.8 GiB** | 84.4 GiB | llama.cpp 3.3x |

## Benchmark: RTX 5090, modelos 8B

- **llama.cpp:** 185-213 tok/s
- **vLLM:** 83 tok/s
- **Ventaja llama.cpp:** ~2.5x en decodificación single-user

## Por qué llama.cpp gana en single-user

1. **Overhead de PagedAttention:** vLLM gestiona bloques KV por request — overhead constante que no se amortiza con 1 usuario
2. **GGUF quantization:** llama.cpp usa Q4/Q5/Q6 nativamente; vLLM necesita FP8/AWQ que en Blackwell puede ser más lento (dequant overhead > bandwidth savings para <20B)
3. **VRAM pre-allocation:** vLLM pre-aloja 90% del VRAM por defecto para el KV pool (mitigable con `--gpu-memory-utilization`)

## Por qué vLLM gana en multi-user

1. **Continuous batching:** interleava requests en el mismo forward pass
2. **PagedAttention:** 19-27% menos memory waste vs gestión lineal del KV cache
3. **Prefill en paralelo:** FlashAttention 2 procesa prompts largos 3-4x más rápido

## Flash Attention en llama.cpp

`--flash-attn` en llama.cpp **NO es la librería FA2 de Tri Dao**. Es una implementación propia:

- Kernels CUDA nativos (`fattn.cu`, `fattn-mma-f16.cuh`, etc.)
- Usa Tensor Cores (MMA/WMMA), inline dequant para Q4/Q8
- Incorpora principios FA2: tiling cooperativo, online softmax incremental, split-K
- Sintonizado por arquitectura (Ampere, Turing, Blackwell)
- Optimizado para inference (no training), GGUF, y cuantización

## Veredicto

| Escenario | Recomendación |
|---|---|
| Uso doméstico, 1 usuario, conversación | **llama.cpp** — más tok/s, menos VRAM, modelo menos cuantizado |
| API multi-tenant, >2 concurrentes | **vLLM** — throughput 2-3x superior |
| RAG con prompts enormes (>5K tok) | **vLLM** — prefill 3-4x más rápido |
| GPU consumer limitada en VRAM | **llama.cpp** — GGUF Q4/Q5 optimiza mejor |
| Blackwell + modelo <20B | **llama.cpp** — bandwidth no es bottleneck, quant overhead penaliza vLLM |
