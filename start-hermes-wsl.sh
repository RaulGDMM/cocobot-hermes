#!/usr/bin/env bash
set -euo pipefail

# ========================================
# Hermes Agent WSL Gateway Startup Script
# ========================================
USE_MODEL="${USE_MODEL:-qwen36_27b}"
USE_BROWSER_TOOL="${USE_BROWSER_TOOL:-on}"

LLAMA_PORT=30000
LLAMA_HOST="host.docker.internal"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLEANUP_DONE=0
HERMES_BIN=""

resolve_hermes_runtime() {
  local candidate
  candidate="$(command -v hermes 2>/dev/null || true)"

  if [[ -z "${candidate}" ]]; then
    # Try the default install location
    if [[ -x "$HOME/.local/bin/hermes" ]]; then
      candidate="$HOME/.local/bin/hermes"
    else
      echo "[!] No se encontro el binario hermes en WSL"
      echo "    Instalar con: curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
      exit 1
    fi
  fi

  HERMES_BIN="${candidate}"
  echo "[hermes] bin: ${HERMES_BIN}"
  "${HERMES_BIN}" --version
}

wait_for_llama_server() {
  echo "[hermes] Esperando a llama-server en ${LLAMA_HOST}:${LLAMA_PORT}..."
  local max_wait=180
  local waited=0
  while (( waited < max_wait )); do
    if curl -sf "http://${LLAMA_HOST}:${LLAMA_PORT}/health" >/dev/null 2>&1; then
      echo "[OK] llama-server listo"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
    if (( waited % 15 == 0 )); then
      echo "  Esperando llama-server... (${waited}s)"
    fi
  done
  echo "[!] llama-server no responde tras ${max_wait}s. Continuando de todas formas..."
  return 1
}

wait_for_docker() {
  echo "[hermes] Comprobando Docker..."
  local max_wait=60
  local waited=0
  while (( waited < max_wait )); do
    if docker info >/dev/null 2>&1; then
      echo "[OK] Docker disponible"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "[!] Docker no disponible tras ${max_wait}s"
  return 1
}

cleanup() {
  if (( CLEANUP_DONE )); then return; fi
  CLEANUP_DONE=1
  echo ""
  echo "[cleanup] Deteniendo Hermes gateway..."
  pkill -f "hermes gateway" 2>/dev/null || true
  echo "[OK] Hermes gateway detenido"
  # Exit 0 so Windows Terminal auto-closes the tab
  exit 0
}
trap cleanup EXIT INT TERM

# ---- Main ----
echo "========================================"
echo "  Hermes Agent Gateway (WSL)"
echo "========================================"
echo "  Modelo: ${USE_MODEL}"
echo "  Browser: ${USE_BROWSER_TOOL}"
echo ""

resolve_hermes_runtime

# Wait for Docker (needed for terminal sandbox)
wait_for_docker || true

# Wait for llama-server to be ready
wait_for_llama_server || true

echo ""
echo "[hermes] Arrancando Hermes gateway..."
echo "  Config: ~/.hermes/config.yaml"
echo "  .env:   ~/.hermes/.env"
echo ""

# Kill any stale gateway (PID file race prevention)
pkill -f "hermes gateway" 2>/dev/null || true
rm -f ~/.hermes/gateway.pid 2>/dev/null || true
sleep 0.5

# Start the Hermes gateway (foreground — manages Telegram, WhatsApp, cron, etc.)
"${HERMES_BIN}" gateway || true
