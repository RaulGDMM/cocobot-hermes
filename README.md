# 🥥 Cocobot-Hermes

One-click startup scripts for running [Hermes Agent](https://github.com/NousResearch/hermes-agent) locally on Windows with WSL, powered by a local LLM via [llama.cpp](https://github.com/ggerganov/llama.cpp).

This setup runs **everything locally** — no cloud APIs needed for the core LLM. Just a GPU, WSL, and a GGUF model.

## What This Does

`start-hermes.bat` launches all services in Windows Terminal tabs with a single click:

| Tab | Service | Description |
|-----|---------|-------------|
| **Hermes Startup** | Orchestrator | Launches everything, monitors health, handles cleanup |
| **llama-server** | LLM inference | Local GGUF model on GPU (llama.cpp) |
| **Hermes Gateway** | Agent gateway (WSL) | Telegram, WhatsApp, cron jobs, messaging |
| **Hermes Chat** | Chat TUI (WSL) | Interactive terminal chat interface |
| **ComfyUI Broker** | Media generation | Image/video/music via ComfyUI (optional) |

Background services (no tab): Whisper STT server, Wyoming STT/TTS bridges.

## Architecture

```
Windows                              WSL (Ubuntu)
┌─────────────────────┐             ┌──────────────────────┐
│ llama-server :30000  │◄───────────│ Hermes Agent gateway │
│ (GPU, GGUF model)   │            │ (Telegram, cron, etc)│
├─────────────────────┤            ├──────────────────────┤
│ Whisper STT :8787   │◄───────────│ Wyoming STT :10300   │
├─────────────────────┤            │ Wyoming TTS :10200   │
│ ComfyUI Broker :8791│◄───────────│                      │
└─────────────────────┘            └──────────────────────┘
```

## Requirements

- **Windows 10/11** with [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) (Ubuntu)
- **Windows Terminal** (for tabbed experience — pre-installed on Win 11)
- **NVIDIA GPU** — see [GPU Scaling Guide](#gpu-scaling-guide) below
- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** built with CUDA — place `llama-server.exe` in `../Openclaw/llama-cpp/`
- **A GGUF model** — recommended: [Qwen3.6-27B](https://huggingface.co/unsloth/Qwen3.6-27B-GGUF) (vision + thinking). Choose a quantization that fits your VRAM

### GPU Scaling Guide

The default configuration in this repo is tuned for an **RTX 5090 (32 GB VRAM)**. You will need to adjust the model quantization and context size to match your GPU:

| GPU (VRAM) | Recommended Model | Quantization | Context Size | Model Size |
|---|---|---|---|---|
| RTX 5090 / A100 (32+ GB) | Qwen3.6-27B | UD-Q4_K_XL | 204,800 | ~17.6 GB |
| RTX 4090 / 3090 (24 GB) | Qwen3.6-27B | Q3_K_M or IQ4_XS | 65,536 | ~12-14 GB |
| RTX 4080 / 3080 (16 GB) | Qwen3.6-27B | IQ2_M or Q2_K | 32,768 | ~8-10 GB |
| RTX 4070 / 3070 (12 GB) | Qwen3.6-27B | IQ2_XXS | 16,384 | ~7 GB |
| RTX 4060 (8 GB) | Qwen3 8B | Q4_K_M | 32,768 | ~5 GB |

**To adjust**, edit `start-hermes.ps1`:
- Change `$ctxSize` to match your available VRAM after model loading
- Point `$modelFile` to your chosen quantization GGUF

Also update Hermes config to match:
```bash
wsl -d Ubuntu -- bash -lc "hermes config set model.context_length YOUR_CTX_SIZE"
```

> **Tip:** Larger context = more VRAM. If you run out of VRAM, reduce context size first. The model weights must fit in VRAM; context uses the remaining space.

> **Tip:** Download different quantizations from [Unsloth's Qwen3.6-27B GGUF collection](https://huggingface.co/unsloth/Qwen3.6-27B-GGUF). Smaller quants trade quality for speed/VRAM.

### Optional

- **[ComfyUI](https://github.com/comfyanonymous/ComfyUI)** — for image/video/music generation via the broker
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — for local speech-to-text
- API keys for web search (Brave), image gen (FAL), Telegram bot, etc.

## Installation

### 1. Install Hermes Agent in WSL

```bash
wsl -d Ubuntu -- bash -lc "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
```

### 2. Install GitHub CLI in WSL (optional, for GitHub skills)

```bash
wsl -d Ubuntu -- bash -lc "sudo apt install gh -y && echo 'YOUR_GITHUB_PAT' | gh auth login --with-token"
```

### 3. Configure Hermes

Run the setup wizard:
```bash
wsl -d Ubuntu -- bash -lc "hermes setup"
```

Or configure manually:
```bash
# Point to your local llama-server
wsl -d Ubuntu -- bash -lc "hermes config set model.provider custom"
wsl -d Ubuntu -- bash -lc "hermes config set model.base_url http://host.docker.internal:30000/v1"
wsl -d Ubuntu -- bash -lc "hermes config set model.default qwen3.6-27b"
wsl -d Ubuntu -- bash -lc "hermes config set model.context_length 204800"
wsl -d Ubuntu -- bash -lc "hermes config set timezone Europe/Madrid"
```

### 4. Set up API keys

Copy the example and fill in your values:
```bash
cp .env.example .env
```

Then add the keys to Hermes' WSL config:
```bash
wsl -d Ubuntu -- bash -lc "nano ~/.hermes/.env"
```

### 5. Place the model and llama-server

Expected directory structure (relative to this repo's parent):
```
Workspace/
├── Hermes/                    ← this repo
│   ├── start-hermes.bat       ← double-click to start
│   ├── start-hermes.ps1       ← main orchestrator
│   ├── start-hermes-wsl.sh    ← WSL gateway script
│   └── start-hermes-chat.sh   ← WSL chat TUI script
└── Openclaw/                  ← shared resources
    ├── llama-cpp/
    │   └── llama-server.exe   ← llama.cpp binary
    ├── models/
    │   └── qwen36-27b/
    │       ├── Qwen3.6-27B-UD-Q4_K_XL.gguf
    │       └── mmproj-BF16.gguf
    ├── whisper-server.py      ← optional STT server
    └── comfyui-broker.py      ← optional media broker
```

### 6. Launch

Double-click `start-hermes.bat` or create a desktop shortcut to it.

## Configuration

### Model Selection

Edit the top of `start-hermes.ps1`:

```powershell
$useModel = "qwen36_27b"     # Options: "qwen36_27b", "qwen36", "qwen36q4", "qwen35", "gemma4"
$useLlamaInstall = "stable"  # "stable" or "latest"
$useBrowserTool = $true      # Enable/disable Playwright browser tool
```

> **Note:** The default model profiles and context sizes in the script are configured for an RTX 5090 (32 GB). See the [GPU Scaling Guide](#gpu-scaling-guide) to adapt them to your hardware.

### Hermes Auto-Evolution

Hermes has a self-improving learning loop. Recommended settings:

```bash
# Memory (learns about you and your environment)
hermes config set memory.memory_enabled true
hermes config set memory.user_profile_enabled true
hermes config set memory.nudge_interval 10

# Skill auto-creation (creates reusable skills from complex tasks)
hermes config set skills.creation_nudge_interval 15
hermes config set skills.inline_shell true

# Context compression (for long conversations)
hermes config set compression.enabled true
hermes config set compression.threshold 0.80

# External memory provider (optional — local semantic memory)
hermes config set memory.provider holographic
```

### Telegram Integration

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Add `TELEGRAM_BOT_TOKEN=your_token` to `~/.hermes/.env`
3. Add `TELEGRAM_ALLOWED_USERS=your_telegram_user_id` to `~/.hermes/.env`
4. The gateway will automatically connect when started

## Files

| File | Description |
|------|-------------|
| `start-hermes.bat` | One-click launcher (double-click this) |
| `start-hermes.ps1` | Main PowerShell orchestrator — launches all services as WT tabs |
| `start-hermes-wsl.sh` | WSL script for Hermes gateway (Telegram, cron, messaging) |
| `start-hermes-chat.sh` | WSL script for interactive chat TUI |
| `.env.example` | Template for API keys |
| `config/hermes.yaml` | Agent personality config |

## How It Works

1. **`start-hermes.bat`** launches PowerShell with `start-hermes.ps1`
2. The PS1 script detects Windows Terminal and re-launches inside it for tabs
3. Checks if llama-server is already running; if not, starts it in a new tab
4. Launches Hermes gateway in a WSL tab (`start-hermes-wsl.sh`)
5. Launches Hermes chat TUI in another WSL tab (`start-hermes-chat.sh`)
6. Starts Whisper STT server (hidden), ComfyUI broker (tab), Wyoming bridges (hidden)
7. Waits for llama-server health check, then sends a warm-up request to load the model into VRAM
8. Keeps running for cleanup — Ctrl+C stops Wyoming bridges and Whisper

## Credits

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) by [Nous Research](https://nousresearch.com/)
- [llama.cpp](https://github.com/ggerganov/llama.cpp) by Georgi Gerganov
- [OpenClaw](https://github.com/steipete/openclaw) by Peter Steinberger — original migration source

## License

MIT

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Verificar estado del servidor |
| `/v1/chat/completions` | POST | Completación de chat |
| `/v1/models` | GET | Listar modelos |

## Uso

### Ejemplo con curl

```bash
# Completación simple
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "Eres un asistente útil."},
      {"role": "user", "content": "¿Hola?"}
    ],
    "temperature": 0.7,
    "max_tokens": 512
  }'

# Completación con streaming
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-27b",
    "messages": [
      {"role": "user", "content": "Explícame la teoría de la relatividad"}
    ],
    "stream": true,
    "temperature": 0.7
  }'
```

### Ejemplo con Python

```python
import httpx

async def chat_with_hermes(message: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:3000/v1/chat/completions",
            json={
                "model": "qwen3.5-27b",
                "messages": [
                    {"role": "system", "content": "Eres un asistente útil."},
                    {"role": "user", "content": message}
                ],
                "temperature": 0.7,
                "max_tokens": 1024
            }
        )
        result = response.json()
        return result["choices"][0]["message"]["content"]

# Uso
import asyncio
response = asyncio.run(chat_with_hermes("¿Cuál es la capital de España?"))
print(response)
```

## Variables de Entorno

| Variable | Valor por Defecto | Descripción |
|----------|-------------------|-------------|
| `HERMES_MODEL_NAME` | `qwen3.5-27b` | Nombre del modelo |
| `HERMES_CONTEXT_SIZE` | `32768` | Tamaño del contexto |
| `HERMES_MAX_TOKENS` | `8192` | Tokens máximos por respuesta |
| `HERMES_TEMPERATURE` | `0.7` | Temperatura de generación |
| `HERMES_TOP_P` | `0.9` | Top-p sampling |
| `LLAMA_SERVER_URL` | `http://localhost:8082` | URL del servidor llama.cpp |
| `HERMES_AGENT_PORT` | `3000` | Puerto del agente Hermes |

## Configuración

La configuración principal se encuentra en `config/hermes.yaml`. Puedes modificar:

- Parámetros de inferencia (temperatura, top_p, etc.)
- Configuración del servidor (puerto, host)
- Configuración de llama-server
- Opciones de logging
- Herramientas habilitadas

## Estructura del Proyecto

```
Hermes/
├── app/                    # Aplicación principal
│   ├── __init__.py
│   └── main.py            # FastAPI application
├── config/                # Configuración
│   └── hermes.yaml        # Configuración YAML
├── data/                  # Datos persistentes
├── models/                # Modelos de IA
│   └── qwen3.5-27b/       # Directorio del modelo
├── Dockerfile            # Imagen de Docker
├── docker-compose.yml    # Orquestación de contenedores
├── requirements.txt      # Dependencias de Python
├── start.bat            # Script de inicio (Windows)
└── README.md            # Esta documentación
```

## Troubleshooting

### Problema: El modelo no se encuentra

**Solución**: Verifica que el archivo del modelo exista en la ruta correcta:
```bash
ls models/qwen3.5-27b/Qwen3.5-27B-Q4_K_M.gguf
```

### Problema: Error de conexión con llama-server

**Solución**: Espera a que llama-server termine de cargar el modelo (puede tomar varios minutos):
```bash
docker-compose logs llama-server
```

### Problema: Out of memory

**Solución**: Reduce el tamaño del contexto o usa una cuantización más agresiva (Q4_K_S en lugar de Q4_K_M).

## Licencia

MIT License

## Créditos

- **Qwen3.5 27B**: Desarrollado por Alibaba Cloud
- **llama.cpp**: Desarrollado por Georgi Gerganov
- **FastAPI**: Framework de API de alto rendimiento