# NVFP4 Quantization Comparison — Qwen3.6-27B

## Cuantizaciones conocidas (mayo 2026)

### LibertAIDAI/Qwen3.6-27B-NVFP4-MTP-GGUF (en uso)
- **Tamaño**: ~19 GB (NVFP4-Q8_0)
- **Enfoque**: Regla fija — FFN → NVFP4, Atención/SSM → Q8_0, Norms → F32
- **Calibración**: NVIDIA ModelOpt v0.42 (activation-aware)
- **MTP**: Preservado, cuantizado a Q4 (~2GB)
- **Benchmark**: GSM8K 86.3%, HumanEval 84.8%, PPL ~6.90 (base BF16)

### michaelw9999/Qwen3.6-27B-NVFP4-MTP-GGUF (nuevo, 29/05/2026)
- **Tamaño**: ~15.5 GB (~3.5GB menos)
- **Enfoque**: Per-tensor con KLD gates + deep RSF search
- **Calibración**: imatrix (wikitrain) + auto-tuner
- **Quality gates**: KLD p99/p999 thresholds — si un tensor no pasa, se promueve a Q8_0/Q6_K
- **PPL reportado**: 7.01 (ratio 1.016 vs base 6.90 — excelente para su tamaño)
- **KL Divergence**: 0.0637, correlación log-PPL 98.51%

### Diferencia clave en enfoque

| Aspecto | LibertAIDAI (ModelOpt) | michaelw9999 (advanced-gguf-quantizer) |
|---------|----------------------|----------------------------------------|
| Decisiones | Regla fija por tipo de capa | Per-tensor, basado en KLD |
| Atención | Siempre Q8_0 | Solo los tensores que necesitan alta precisión |
| Calibración | Activation-aware | imatrix + RSF search |
| Quality gates | No | KLD p99/p999 durante cuantización |
| Tamaño | ~19 GB | ~15.5 GB |

### ¿Cómo puede michaelw9999 ser mejor siendo más pequeño?

1. **RSF (Residual Scale Factor) search**: Busca el factor de escala óptimo por tensor, no usa valor fijo. Reduce error de cuantización significativamente en NVFP4.
2. **No todos los tensores de atención necesitan Q8_0**: Los de proyección intermedia o capas menos profundas toleran bien NVFP4. El quantizer solo promueve a alta precisión los que realmente lo necesitan.
3. **KLD como gate activo**: Los tensores críticos terminan en alta precisión, pero solo los que lo necesitan, no todos por regla fija.

### Benchmark A/B recomendado

1. **PPL** — requiere `prompt_logprobs` en servidor (NO disponible en build OpenClaw v9368)
2. **GSM8K** — 51 muestras, fiable para diferencias >2pp
3. **HumanEval** — 164 muestras, fiable para diferencias >2pp
4. **Tool calls** — medir acceptance rate MTP y velocidad real
5. **Reasoning largo** — cadenas de 10+ pasos

### Línea base PPL (referencia)

| Modelo | PPL WikiText-2 |
|--------|---------------|
| Qwen3.6-27B BF16 | ~6.90 |
| michaelw9999 NVFP4 | ~7.01 (ratio 1.016) |
| LibertAIDAI NVFP4-Q8_0 | ? (no publicado, pero debería ser <7.01 por tener atención en Q8_0) |

### Limitación actual: servidor sin prompt_logprobs

El servidor activo en `172.23.176.1:30000` usa un binario pre-built de OpenClaw:
- **Build**: llama.cpp v9368 (commit `c6e408837`)
- **Compilador**: MSVC 19.50.35723.0, Windows AMD64
- **Ubicación**: `E:\Workspace\Openclaw\llama-cpp\llama-server.exe`
- **Logprobs**: ❌ No soportado — ni `/completion` ni `/v1/chat/completions` devuelven `prompt_logprobs`
- **Causa**: Binario precompilado de OpenClaw sin soporte de logprobs en la compilación

Para habilitar PPL: necesitaría recompilar llama.cpp upstream con `-DLLAMA_LOGPROBS=ON` (default en builds recientes) o usar un release pre-built que lo incluya.
