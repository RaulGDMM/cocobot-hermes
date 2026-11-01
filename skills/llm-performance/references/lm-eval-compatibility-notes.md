# lm-evaluation-harness: Notas de Compatibilidad

## Problemas encontrados (27/05/2026)

### v0.4.12 — `typing_extensions`
```
TypeError: _TypedDictMeta.__new__() got an unexpected keyword argument 'extra_items'
```
**Fix**: `pip install "typing_extensions>=4.13.0"`

### v0.4.9 — `transformers`
```
AttributeError: module transformers has no attribute AutoModelForVision2Seq
```
**Fix**: No hay — la versión 0.4.9 es incompatible con transformers 5.x

### `openai-chat-completions` model

**v0.4.12**: Usa `base_url` en `model_args`
```bash
lm_eval --model openai-chat-completions --model_args "base_url=http://..."
```

**v0.4.9**: Usa `api_base` en `model_args`
```bash
lm_eval --model openai-chat-completions --model_args "api_base=http://..."
```

**Ambas versiones**:
- Requieren `--apply_chat_template` o fallan con `AssertionError`
- Requieren `OPENAI_API_KEY` (puede ser dummy: `OPENAI_API_KEY=***`)
- `num_concurrent=1` por defecto — sin concurrent requests, el benchmark es lento

### `litellm-chat` model
- Requiere `litellm` instalado
- Falla con `AuthenticationError` si el servidor no es OpenAI real (verifica el API key)
- No es confiable para servidores llama.cpp

### `local-chat-completions` model
- Disponible en v0.4.12
- Funciona contra cualquier servidor OpenAI-compatible sin API key
- **Mejor opción** si lm-eval funciona:
```bash
lm_eval --model local-chat-completions --model_args "base_url=http://..."
```

## Veredicto

lm-evaluation-harness tiene problemas de compatibilidad constantes entre versiones. Para uso con llama.cpp local:

1. **Script custom** (`llm-intelligence-benchmark.py`) — más fiable, sin dependencias conflictivas
2. **`local-chat-completions`** — mejor opción dentro de lm-eval si funciona
3. **`openai-chat-completions`** — funciona pero con más fricción (API key dummy, apply_chat_template)
