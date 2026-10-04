#!/usr/bin/env bash
set -euo pipefail

# ========================================
# Hermes Agent WSL Gateway Startup Script
# ========================================

# Ensure ~/.local/bin is on PATH (uv, hermes, etc.)
export PATH="$HOME/.local/bin:$PATH"

USE_MODEL="${USE_MODEL:-qwen38_27b_unsloth_q6k_mtp}"
USE_BROWSER_TOOL="${USE_BROWSER_TOOL:-on}"
USE_TAILSCALE="${USE_TAILSCALE:-off}"

LLAMA_PORT=30000
IS_STRATA=0
if [[ "${USE_MODEL}" == "qwen38_flashnext_nvfp4" ]]; then
  IS_STRATA=1
  LLAMA_PORT=8097
fi
# Resolve Windows host IP (WSL gateway) — replaces old host.docker.internal
LLAMA_HOST="$(ip route show default | awk '{print $3}')"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRATA_START_CMD="$SCRIPT_DIR/../Openclaw/strata-nvfp4/strata-nvfp4/start-cocobot.cmd"
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
  local name="llama-server" max_wait=180
  if (( IS_STRATA )); then name="Strata"; max_wait=300; fi
  echo "[hermes] Esperando a ${name} en ${LLAMA_HOST}:${LLAMA_PORT}..."
  local waited=0
  while (( waited < max_wait )); do
    if (( IS_STRATA )); then
      # Strata responde /health aunque el motor haya muerto: exigir loaded=true
      if curl -sf "http://${LLAMA_HOST}:${LLAMA_PORT}/health" 2>/dev/null | grep -Eq '"loaded": ?true'; then
        echo "[OK] ${name} listo"
        return 0
      fi
    elif curl -sf "http://${LLAMA_HOST}:${LLAMA_PORT}/health" >/dev/null 2>&1; then
      echo "[OK] ${name} listo"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
    if (( waited % 15 == 0 )); then
      echo "  Esperando ${name}... (${waited}s)"
    fi
  done
  echo "[!] ${name} no responde tras ${max_wait}s. Continuando de todas formas..."
  return 1
}

# Copia STRATA_API_KEY de start-cocobot.cmd (fuente de verdad) a ~/.hermes/.env
sync_strata_api_key() {
  local key env_file="$HOME/.hermes/.env"
  key="$(grep -oE 'STRATA_API_KEY=[^"[:space:]]+' "$STRATA_START_CMD" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '\r')"
  if [[ -z "$key" ]]; then
    echo "[!] No se encontro STRATA_API_KEY en $STRATA_START_CMD"
    return 1
  fi
  touch "$env_file" && chmod 600 "$env_file"
  if grep -q '^STRATA_API_KEY=' "$env_file"; then
    sed -i "s|^STRATA_API_KEY=.*|STRATA_API_KEY=${key}|" "$env_file"
  else
    printf '\nSTRATA_API_KEY=%s\n' "$key" >> "$env_file"
  fi
  echo "[config] STRATA_API_KEY sincronizada en ~/.hermes/.env"
}

# Conmuta model/auxiliares entre custom:llama-server (:30000) y custom:strata (:8097).
# El bloque custom_providers no se toca salvo para crear la entrada strata.
switch_llm_backend() {
  local target="$1"
  SWITCH_TO="$target" LLAMA_HOST="$LLAMA_HOST" python3 - "$HOME/.hermes/config.yaml" <<'PY'
import os, re, sys
path = sys.argv[1]
to_strata = os.environ["SWITCH_TO"] == "strata"
host = os.environ["LLAMA_HOST"]
with open(path, encoding="utf-8") as f:
    lines = f.read().split("\n")
out, in_cp, cp_idx, has_strata = [], False, None, False
for line in lines:
    if re.match(r"^\S", line):
        in_cp = line.startswith("custom_providers:")
        if in_cp:
            cp_idx = len(out)
    if in_cp:
        if re.match(r"^\s*(-\s*)?name:\s*strata\s*$", line):
            has_strata = True
    elif to_strata:
        line = line.replace("provider: custom:llama-server", "provider: custom:strata")
        line = re.sub(r"(base_url: http://[^/:\s]+):30000/v1", r"\1:8097/v1", line)
    else:
        line = line.replace("provider: custom:strata", "provider: custom:llama-server")
        line = re.sub(r"(base_url: http://[^/:\s]+):8097/v1", r"\1:30000/v1", line)
    out.append(line)
if not has_strata and cp_idx is not None:
    out[cp_idx + 1:cp_idx + 1] = [
        "  - api_key: ''",
        "    api_mode: chat_completions",
        f"    base_url: http://{host}:8097/v1",
        "    key_env: STRATA_API_KEY",
        "    models:",
        "      - qwen3.8-flash-next-nvfp4",
        "    name: strata",
    ]
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(f"[config] backend LLM -> custom:{'strata' if to_strata else 'llama-server'}")
PY
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
#
# 2026-09-01 fix: pkill -f matched FULL COMMAND LINES — so ANY agent terminal
# command containing the literal string "hermes gateway" (e.g. diagnostics
# like `ps aux | grep "hermes gateway"`) was SIGTERM-killed every time the
# launcher loop restarted the gateway. That made the agent's own commands
# die mid-execution during crash loops. Use `pkill -x hermes` (exact
# comm/name match: only the real gateway wrapper process) plus a targeted
# -f pattern that is specific enough not to match diagnostics.
kill_stale_gateway() {
  # Exact-name: only the real `hermes` wrapper binary (never agent terminals).
  pkill -x hermes 2>/dev/null || true
  # Venv-direct invocation (Desktop app restart-after-update path). The pattern
  # matches the venv python running the hermes entrypoint — specific enough
  # that diagnostic commands (grep/pkill themselves) don't match it.
  pkill -f '[h]ermes-agent/venv/bin/python3.*hermes gateway' 2>/dev/null || true
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
  qwen38_27b_unsloth_q6k_mtp) CTX_LEN=140000 ;;
  qwen38_27b_nvfp4_q8attn_mtp) CTX_LEN=230000 ;;
  qwen38_flashnext_nvfp4) CTX_LEN=262144 ;;
  gemma4)          CTX_LEN=100000 ;;
  *)               CTX_LEN=131072 ;;
esac
HERMES_CONFIG="$HOME/.hermes/config.yaml"
if [[ -f "$HERMES_CONFIG" ]]; then
  if (( IS_STRATA )); then
    sync_strata_api_key || true
    switch_llm_backend strata
  else
    switch_llm_backend llama-server
  fi
  sed -i "s/  context_length: .*/  context_length: ${CTX_LEN}/" "$HERMES_CONFIG"
  echo "[config] context_length actualizado a ${CTX_LEN}"
  case "${USE_MODEL}" in
    qwen38_flashnext_nvfp4) MODEL_ALIAS="qwen3.8-flash-next-nvfp4" ;;
    qwen38_27b_*)          MODEL_ALIAS="qwen3.8-27b" ;;
    gemma4)                MODEL_ALIAS="gemma4-31b" ;;
    *)                     MODEL_ALIAS="qwen3.8-27b" ;;
  esac
  if grep -q '^model:' "$HERMES_CONFIG"; then
    sed -i "0,/^  default: .*/s//  default: ${MODEL_ALIAS}/" "$HERMES_CONFIG"
    echo "[config] model.default=${MODEL_ALIAS}"
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
