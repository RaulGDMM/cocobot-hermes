#!/usr/bin/env bash
set -euo pipefail

# ========================================
# Hermes Agent WSL Gateway Startup Script
# ========================================

# Ensure ~/.local/bin is on PATH (uv, hermes, etc.)
export PATH="$HOME/.local/bin:$PATH"

USE_MODEL="${USE_MODEL:-qwen36_27b}"
USE_BROWSER_TOOL="${USE_BROWSER_TOOL:-on}"
USE_TAILSCALE="${USE_TAILSCALE:-off}"

LLAMA_PORT=30000
LLAMA_HOST="host.docker.internal"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLEANUP_DONE=0
HERMES_BIN=""
TAILSCALE_STARTED=0

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

cleanup() {
  if (( CLEANUP_DONE )); then return; fi
  CLEANUP_DONE=1
  echo ""
  echo "[cleanup] Deteniendo Hermes gateway..."
  pkill -f "hermes gateway" 2>/dev/null || true
  echo "[OK] Hermes gateway detenido"
  if (( TAILSCALE_STARTED )); then
    echo "[cleanup] Deteniendo Tailscale serve (Open WebUI)..."
    tailscale serve --https=8443 off 2>/dev/null || true
    echo "[OK] Tailscale serve detenido"
  fi
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

# ---- Tailscale: expose Open WebUI via secure mesh ----
start_tailscale() {
  echo "[tailscale] Iniciando Tailscale (acceso remoto a Open WebUI)..."

  # Check if tailscaled is already running
  if tailscale status >/dev/null 2>&1; then
    local ts_ip
    ts_ip="$(tailscale ip -4 2>/dev/null || echo '?')"
    echo "[OK] Tailscale ya conectado (IP: ${ts_ip})"
  else
    echo "  Arrancando tailscaled..."
    sudo mkdir -p /run/tailscale /var/lib/tailscale
    sudo rm -f /run/tailscale/tailscaled.sock
    sudo nohup tailscaled \
      --state=/var/lib/tailscale/tailscaled.state \
      --socket=/run/tailscale/tailscaled.sock \
      </dev/null &>/var/log/tailscaled.log &
    disown

    # Wait for daemon
    local i
    for (( i=0; i<15; i++ )); do
      if tailscale status >/dev/null 2>&1; then break; fi
      sleep 1
    done

    if ! tailscale status >/dev/null 2>&1; then
      echo "[!] tailscaled no arranco a tiempo"
      return
    fi

    sudo tailscale up 2>&1 | while IFS= read -r line; do echo "  ${line}"; done
    local ts_ip
    ts_ip="$(tailscale ip -4 2>/dev/null || echo '?')"
    echo "[OK] Tailscale conectado (IP: ${ts_ip})"
  fi

  # Expose Open WebUI (HTTPS, only within tailnet — not public Funnel)
  tailscale serve --bg --https=8443 http://host.docker.internal:8080 2>&1 | sed 's/^/  /'
  TAILSCALE_STARTED=1

  # Keep existing Funnel for Home Assistant
  tailscale funnel --bg 8123 >/dev/null 2>&1 || true

  echo "[OK] Open WebUI accesible en: https://desktop-gds672i.tail3b193a.ts.net:8443/"
  echo ""
}

if [[ "${USE_TAILSCALE}" == "on" ]]; then
  start_tailscale
else
  echo "[tailscale] Desactivado (USE_TAILSCALE=off)"
  echo ""
fi

# Start the Hermes gateway (foreground — manages Telegram, WhatsApp, cron, etc.)
# Restart loop mimics systemd Restart=on-failure:
#   - exit 0   → clean shutdown, don't restart
#   - exit 75  → explicit restart request (hermes gateway restart)
#   - exit 1+  → failure or external stop (hermes gateway stop), restart it
#   - SIGINT/SIGTERM from user Ctrl+C → handled by trap, script exits before loop continues
# Rapid-crash protection: if gateway crashes 5 times within 30s, stop looping.
CRASH_COUNT=0
MAX_RAPID_CRASHES=5
RAPID_CRASH_WINDOW=30
LAST_START=0

while true; do
  LAST_START=$(date +%s)

  # Capture exit code without triggering set -e
  exit_code=0
  "${HERMES_BIN}" gateway || exit_code=$?

  # Clean exit → stop
  if [[ ${exit_code} -eq 0 ]]; then
    echo "[hermes] Gateway terminó limpiamente (exit code 0)."
    break
  fi

  # Rapid-crash detection: if it ran less than RAPID_CRASH_WINDOW seconds, count it
  now=$(date +%s)
  runtime=$(( now - LAST_START ))
  if (( runtime < RAPID_CRASH_WINDOW )); then
    CRASH_COUNT=$(( CRASH_COUNT + 1 ))
  else
    CRASH_COUNT=1  # reset — it ran long enough, this is a fresh failure
  fi

  if (( CRASH_COUNT >= MAX_RAPID_CRASHES )); then
    echo "[hermes] Gateway crasheó ${CRASH_COUNT} veces en menos de ${RAPID_CRASH_WINDOW}s. Abortando."
    break
  fi

  # Any non-zero exit: restart (code 75 = explicit, code 1 = external stop / systemd-style)
  if [[ ${exit_code} -eq 75 ]]; then
    echo ""
    echo "[hermes] Gateway solicitó reinicio (exit code 75). Reiniciando en 2s..."
  else
    echo ""
    echo "[hermes] Gateway terminó con exit code ${exit_code}. Reiniciando en 3s... (intento ${CRASH_COUNT}/${MAX_RAPID_CRASHES})"
  fi

  # Clean up stale PID before restarting
  pkill -f "hermes gateway" 2>/dev/null || true
  rm -f ~/.hermes/gateway.pid 2>/dev/null || true

  if [[ ${exit_code} -eq 75 ]]; then
    sleep 2
  else
    sleep 3
  fi
done
