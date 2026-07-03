#!/usr/bin/env bash
set -euo pipefail

# ==================================================
# Hermes Desktop Backend Startup Script (WSL)
# ==================================================
# Runs `hermes serve` -- the JSON-RPC/WebSocket API the Windows/macOS Desktop
# app connects to as a "Remote Gateway" -- as its own supervised process in
# its own tab, with the same crash-restart semantics as the messaging
# gateway (start-hermes-wsl.sh).
#
# Why its own tab instead of a background helper bolted onto the gateway
# script: the Desktop app's own "update" flow can kill this process
# independently of the gateway (it swaps files in the shared venv and kills
# every hermes process running out of it, this one included), so it needs
# its own restart loop rather than a polling side-loop that checks health
# every N seconds from an unrelated script.

export PATH="$HOME/.local/bin:$PATH"

DESKTOP_SERVE_PORT="${DESKTOP_SERVE_PORT:-9119}"
CLEANUP_DONE=0
HERMES_BIN=""

resolve_hermes_runtime() {
  local candidate
  candidate="$(command -v hermes 2>/dev/null || true)"

  if [[ -z "${candidate}" ]]; then
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

kill_stale_backend() {
  pkill -f "hermes serve --host 0.0.0.0 --port ${DESKTOP_SERVE_PORT}" 2>/dev/null || true
}

cleanup() {
  if (( CLEANUP_DONE )); then return; fi
  CLEANUP_DONE=1
  echo ""
  echo "[cleanup] Deteniendo Hermes Desktop backend..."
  kill_stale_backend
  echo "[OK] Hermes Desktop backend detenido"
  # Exit 0 so Windows Terminal auto-closes the tab
  exit 0
}
trap cleanup EXIT INT TERM

# ---- Main ----
echo "========================================"
echo "  Hermes Desktop Backend (WSL)"
echo "========================================"
echo "  Puerto: ${DESKTOP_SERVE_PORT}"
echo ""

resolve_hermes_runtime

# Load ~/.hermes/.env so HERMES_DASHBOARD_BASIC_AUTH_* reach `hermes serve`.
if [[ -f "$HOME/.hermes/.env" ]]; then
  set -a
  # Disable -u while sourcing: dotenv values can contain a literal $ (e.g. a
  # scrypt$... password hash), which bash would otherwise treat as an unbound
  # variable under set -u and abort startup. Values with $ should be
  # single-quoted in .env; this guard just avoids crashing if one isn't.
  set +u
  # shellcheck disable=SC1091
  source "$HOME/.hermes/.env"
  set -u
  set +a
fi

if [[ -z "${HERMES_DASHBOARD_BASIC_AUTH_USERNAME:-}" ]]; then
  echo "[!] Falta HERMES_DASHBOARD_BASIC_AUTH_USERNAME en ~/.hermes/.env"
fi
if [[ -z "${HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH:-}" && -z "${HERMES_DASHBOARD_BASIC_AUTH_PASSWORD:-}" ]]; then
  echo "[!] Falta HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH o HERMES_DASHBOARD_BASIC_AUTH_PASSWORD en ~/.hermes/.env"
fi
if [[ -z "${HERMES_DASHBOARD_BASIC_AUTH_SECRET:-}" ]]; then
  echo "[!] Falta HERMES_DASHBOARD_BASIC_AUTH_SECRET en ~/.hermes/.env; las sesiones se cerraran al reiniciar"
fi

echo ""
echo "[hermes] Arrancando Hermes Desktop backend..."
echo ""

# Restart loop mimics the gateway's (start-hermes-wsl.sh):
#   - exit 0   → clean shutdown, don't restart
#   - exit 1+  → crash or external stop, restart it
#   - SIGINT/SIGTERM from user Ctrl+C → handled by trap, script exits before loop continues
# Rapid-crash protection: if it crashes 5 times within 30s, stop looping
# instead of spinning forever on a permanently broken backend (e.g. missing
# deps after a failed update).
CRASH_COUNT=0
MAX_RAPID_CRASHES=5
RAPID_CRASH_WINDOW=30
LAST_START=0

while true; do
  # Kill any stale instance left over from a previous crash before (re)starting.
  kill_stale_backend
  LAST_START=$(date +%s)

  exit_code=0
  "${HERMES_BIN}" serve --host 0.0.0.0 --port "${DESKTOP_SERVE_PORT}" || exit_code=$?

  if [[ ${exit_code} -eq 0 ]]; then
    echo "[hermes] Desktop backend termino limpiamente (exit code 0)."
    break
  fi

  now=$(date +%s)
  runtime=$(( now - LAST_START ))
  if (( runtime < RAPID_CRASH_WINDOW )); then
    CRASH_COUNT=$(( CRASH_COUNT + 1 ))
  else
    CRASH_COUNT=1  # reset — it ran long enough, this is a fresh failure
  fi

  if (( CRASH_COUNT >= MAX_RAPID_CRASHES )); then
    echo "[hermes] Desktop backend crasheo ${CRASH_COUNT} veces en menos de ${RAPID_CRASH_WINDOW}s. Abortando."
    break
  fi

  echo ""
  echo "[hermes] Desktop backend termino con exit code ${exit_code}. Reiniciando en 3s... (intento ${CRASH_COUNT}/${MAX_RAPID_CRASHES})"
  sleep 3
done

# El backend salio del bucle (parada limpia o demasiados crashes). Mantener
# la pestana abierta para poder leer el motivo antes de que el trap EXIT la cierre.
echo ""
echo "[launcher] El Hermes Desktop backend se detuvo. Pulsa Enter para cerrar esta pestana..."
read -r _ || true
