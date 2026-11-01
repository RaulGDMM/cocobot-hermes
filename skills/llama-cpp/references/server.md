# Server Deployment Guide

Production deployment of llama.cpp server with OpenAI-compatible API.

## Direct from Hugging Face Hub

Prefer the model repo's local-app page first:

```text
https://huggingface.co/<repo>?local-app=llama.cpp
```

If the page shows an exact snippet, copy it. If not, use one of these forms:

```bash
# Choose a quant label directly from the Hub repo
llama-server -hf bartowski/Llama-3.2-3B-Instruct-GGUF:Q8_0
```

```bash
# Pin an exact GGUF file from the repo tree
llama-server \
    --hf-repo microsoft/Phi-3-mini-4k-instruct-gguf \
    --hf-file Phi-3-mini-4k-instruct-q4.gguf \
    -c 4096
```

Use the file-specific form when the repo has custom naming or when you already extracted the exact filename from the tree API.

## Server Modes

### llama-server

```bash
# Basic server
./llama-server \
    -m models/llama-2-7b-chat.Q4_K_M.gguf \
    --host 0.0.0.0 \
    --port 8080 \
    -c 4096  # Context size

# With GPU acceleration
./llama-server \
    -m models/llama-2-70b.Q4_K_M.gguf \
    -ngl 40  # Offload 40 layers to GPU
```

## OpenAI-Compatible API

### Chat completions
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2",
    "messages": [
      {"role": "system", "content": "You are helpful"},
      {"role": "user", "content": "Hello"}
    ],
    "temperature": 0.7,
    "max_tokens": 100
  }'
```

### Streaming
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2",
    "messages": [{"role": "user", "content": "Count to 10"}],
    "stream": true
  }'
```

## Docker Deployment

**Dockerfile**:
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y git build-essential
RUN git clone https://github.com/ggerganov/llama.cpp
WORKDIR /llama.cpp
RUN make LLAMA_CUDA=1
COPY models/ /models/
EXPOSE 8080
CMD ["./llama-server", "-m", "/models/model.gguf", "--host", "0.0.0.0", "--port", "8080"]
```

**Run**:
```bash
docker run --gpus all -p 8080:8080 llama-cpp:latest
```

## Monitoring

```bash
# Server metrics endpoint
curl http://localhost:8080/metrics

# Health check
curl http://localhost:8080/health
```

**Metrics**:
- requests_total
- tokens_generated
- prompt_tokens
- completion_tokens
- kv_cache_tokens

## Load Balancing

**NGINX**:
```nginx
upstream llama_cpp {
    server llama1:8080;
    server llama2:8080;
}

server {
    location / {
        proxy_pass http://llama_cpp;
        proxy_read_timeout 300s;
    }
}
```

## Performance Tuning

**Parallel requests**:\n```bash
./llama-server \
    -m model.gguf \
    -np 4  # 4 parallel slots (legacy)
```

**Parallel with kv-cache-unified (recommended, modern)**:\n```bash
./llama-server \
    -m model.gguf \
    --parallel 2 \
    --kv-cache-unified \
    --ctx-checkpoints 32 \
    --cont-batching \
    -ctk q8_0 \
    -ctv q8_0
```

See **[parallel-kv-unified.md](references/parallel-kv-unified.md)** for full details: VRAM layout, benchmarking, common pitfalls.

**Continuous batching**:\n```bash
./llama-server \
    -m model.gguf \
    --cont-batching  # Enable continuous batching
```

**Context caching**:\n```bash
./llama-server \
    -m model.gguf \
    --cache-prompt  # Cache processed prompts
```

**No context shift**:\n```bash
./llama-server \
    -m model.gguf \
    --no-context-shift  # Disable automatic context shifting
```

### Context Shift Behavior

By default, when the context fills up, llama-server performs a "context shift":
- Removes oldest tokens from KV cache
- Keeps system prompt + newest tokens
- **Full re-tokenization/re-processing** of all remaining tokens → massive latency spike

`--no-context-shift` disables this behavior:
- Server returns an error when context is full
- **No reprocessing** → predictable latency
- Client-side control: you decide when to reset the context
- Ideal for long sessions where you want to manage context manually

### When to Use Each

| Scenario | Flag | Reason |
|---|---|---|
| Chat apps, short context | Default | Auto-shift handles overflow gracefully |
| Long sessions, predictable latency | `--no-context-shift` | Avoid reprocessing spikes |
| RAG, batch processing | `--no-context-shift` | Full control over context window |
| Real-time streaming | Default | Auto-shift prevents hard stops |
