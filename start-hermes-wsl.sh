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
# Resolve Windows host IP (WSL gateway) — replaces old host.docker.internal
LLAMA_HOST="$(ip route show default | awk '{print $3}')"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/load-copilot-work-account.sh"
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

# Kill any gateway process regardless of how it was invoked.  "hermes gateway
# run" (our own launcher) and the Desktop app's own restart-after-update flow
# (which shells out to "<venv>/bin/python -m hermes_cli.main gateway run
# --replace" directly, bypassing the hermes wrapper) look completely
# different in `ps`, so a naive `pkill -f "hermes gateway"` only ever matched
# the first form. When the Desktop app updated Hermes and tried to restart
# the gateway itself, its process survived every cleanup pass here and our
# own gateway loop kept colliding with it ("Another gateway instance is
# already running"), crash-looping 5x and aborting (#issue: post-update
# gateway restart deadlock). Match both invocation shapes.
kill_stale_gateway() {
  pkill -f 'hermes_cli\.main gateway|hermes gateway' 2>/dev/null || true
}

cleanup() {
  if (( CLEANUP_DONE )); then return; fi
  CLEANUP_DONE=1
  echo ""
  echo "[cleanup] Deteniendo Hermes gateway..."
  kill_stale_gateway
  echo "[OK] Hermes gateway detenido"
  if (( TAILSCALE_STARTED )); then
    echo "[cleanup] Deteniendo Tailscale serve (Hermes WebUI)..."
    tailscale serve --https=8443 off 2>/dev/null || true
    echo "[OK] Tailscale serve detenido"
  fi
  # Exit 0 so Windows Terminal auto-closes the tab
  exit 0
}
trap cleanup EXIT HUP INT TERM

# ---- Main ----
echo "========================================"
echo "  Hermes Agent Gateway (WSL)"
echo "========================================"
echo "  Modelo: ${USE_MODEL}"
echo "  Browser: ${USE_BROWSER_TOOL}"
echo ""

resolve_hermes_runtime

# Export broker URL for ComfyUI scripts (dynamic Windows host IP)
export OPENCLAW_COMFYUI_LOCAL_BROKER_URL="http://${LLAMA_HOST}:8791"

# Wait for llama-server to be ready
wait_for_llama_server || true

echo ""

# Sync context_length in config.yaml based on model
case "${USE_MODEL}" in
  qwen36_27b_bee_q5) CTX_LEN=262144 ;;
  qwen36_27b_bee_q6) CTX_LEN=191608 ;;
  qwen36_27b)      CTX_LEN=200000 ;;
  qwen36q4)        CTX_LEN=200000 ;;
  qwen36)          CTX_LEN=100000 ;;
  qwen36_27b_q6)   CTX_LEN=131072 ;;
  qwen36_27b_q4_mtp) CTX_LEN=150000 ;;
  qwen36_27b_q5_mtp) CTX_LEN=130000 ;;
  qwen36_27b_q6_mtp) CTX_LEN=170000 ;;
  qwen36_27b_autoround_q6_mtp) CTX_LEN=150000 ;;
  gemma4)          CTX_LEN=100000 ;;
  *)               CTX_LEN=131072 ;;
esac
HERMES_CONFIG="$HOME/.hermes/config.yaml"
if [[ -f "$HERMES_CONFIG" ]]; then
  sed -i "s/  context_length: .*/  context_length: ${CTX_LEN}/" "$HERMES_CONFIG"
  echo "[config] context_length actualizado a ${CTX_LEN}"
  if grep -q '^model:' "$HERMES_CONFIG"; then
    sed -i '0,/^  default: .*/s//  default: qwen3.6-27b/' "$HERMES_CONFIG"
    echo "[config] model.default=qwen3.6-27b"
  fi
  if grep -q '^compression:' "$HERMES_CONFIG"; then
    sed -i "s/  protect_last_n: .*/  protect_last_n: 10/" "$HERMES_CONFIG"
    echo "[config] compression: protect_last_n=10"
  fi
fi

echo "[hermes] Arrancando Hermes gateway..."
echo "  Config: ~/.hermes/config.yaml"
echo "  .env:   ~/.hermes/.env"
echo ""

# Make tool/provider keys from ~/.hermes/.env visible to the gateway process.
# Hermes usually loads this file itself, but exporting it here avoids surprises
# when web providers rely on os.environ at tool registration time.
if [[ -f "$HOME/.hermes/.env" ]]; then
  set -a
  # Disable -u while sourcing: dotenv values can contain a literal $ (e.g. a
  # scrypt$... password hash), which bash would otherwise treat as an unbound
  # variable under set -u and abort the whole gateway startup. Values with $
  # should be single-quoted in .env; this guard just avoids crashing if one
  # slips through unquoted.
  set +u
  # shellcheck disable=SC1091
  source "$HOME/.hermes/.env"
  set -u
  set +a
fi
load_copilot_work_account
if [[ -n "${BRAVE_SEARCH_API_KEY:-}" ]]; then
  echo "[web] Brave Search: BRAVE_SEARCH_API_KEY cargada"
else
  echo "[web] Brave Search: BRAVE_SEARCH_API_KEY no encontrada"
fi
if [[ -n "${FIRECRAWL_API_KEY:-}" || -n "${FIRECRAWL_API_URL:-}" ]]; then
  echo "[web] Firecrawl: credenciales cargadas"
else
  echo "[web] Firecrawl: credenciales no encontradas"
fi

# Kill any stale gateway (PID file race prevention)
kill_stale_gateway
rm -f ~/.hermes/gateway.pid 2>/dev/null || true
sleep 0.5

echo ""

# ---- Tailscale: expose Open WebUI via secure mesh ----
start_tailscale() {
  echo "[tailscale] Iniciando Tailscale (acceso remoto a Hermes WebUI)..."

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

  # Expose Hermes WebUI (HTTPS, only within tailnet — not public Funnel)
  tailscale serve --bg --https=8443 http://127.0.0.1:8787 2>&1 | sed 's/^/  /'
  TAILSCALE_STARTED=1

  # Keep existing Funnel for Home Assistant
  tailscale funnel --bg 8123 >/dev/null 2>&1 || true

  echo "[OK] Hermes WebUI accesible en: https://desktop-gds672i.tail3b193a.ts.net:8443/"
  echo ""
}

if [[ "${USE_TAILSCALE}" == "on" ]]; then
  start_tailscale
else
  echo "[tailscale] Desactivado (USE_TAILSCALE=off)"
  echo ""
fi

# Start the Hermes gateway (foreground — manages Telegram, WhatsApp, cron, etc.)
# -vv = DEBUG verbosity: muestra tools llamadas, reasoning, contexto, errores detallados
# -v = INFO verbosity: solo eventos principales
# Sin flag = modo display box (poco informativo)
GATEWAY_VERBOSE="${GATEWAY_VERBOSE:-vv}"  # vv=DEBUG, v=INFO, vacío=silencioso

# Restart loop keeps the gateway in this tab across planned reloads:
#   - exit 0   → planned clean stop/reload, restart
#   - exit 75  → explicit restart request (hermes gateway restart)
#   - exit 1+  → failure or external stop (hermes gateway stop), restart it
#   - SIGHUP/SIGINT/SIGTERM to this launcher → handled by trap, don't restart
# Rapid-crash protection: if gateway crashes 5 times within 30s, stop looping.
CRASH_COUNT=0
MAX_RAPID_CRASHES=5
RAPID_CRASH_WINDOW=30
LAST_START=0

while true; do
  LAST_START=$(date +%s)

  # Capture exit code without triggering set -e
  exit_code=0
  if [[ -n "${GATEWAY_VERBOSE}" ]]; then
    "${HERMES_BIN}" gateway run -${GATEWAY_VERBOSE} || exit_code=$?
  else
    "${HERMES_BIN}" gateway || exit_code=$?
  fi

  # Rapid-restart detection also covers repeated clean reloads.
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

  if [[ ${exit_code} -eq 0 ]]; then
    echo ""
    echo "[hermes] Gateway terminó limpiamente para recargar (exit code 0). Reiniciando en 2s..."
  elif [[ ${exit_code} -eq 75 ]]; then
    echo ""
    echo "[hermes] Gateway solicitó reinicio (exit code 75). Reiniciando en 2s..."
  else
    echo ""
    echo "[hermes] Gateway terminó con exit code ${exit_code}. Reiniciando en 3s... (intento ${CRASH_COUNT}/${MAX_RAPID_CRASHES})"
  fi

  # Clean up stale PID before restarting
  kill_stale_gateway
  rm -f ~/.hermes/gateway.pid 2>/dev/null || true

  if [[ ${exit_code} -eq 0 || ${exit_code} -eq 75 ]]; then
    sleep 2
  else
    sleep 3
  fi
done

# El gateway salio del bucle (parada limpia o demasiados crashes). Mantener la
# pestana abierta para poder leer el motivo antes de que el trap EXIT la cierre.
echo ""
echo "[launcher] El gateway se detuvo. Pulsa Enter para cerrar esta pestana..."
read -r _ || true
