#!/usr/bin/env bash
# Helper: wait for llama-server then launch hermes chat TUI
trap 'exit 0' INT TERM
LLAMA_HOST="$(ip route show default | awk '{print $3}')"
echo "Esperando a llama-server en ${LLAMA_HOST}:30000..."
while ! curl -sf "http://${LLAMA_HOST}:30000/health" >/dev/null 2>&1; do
  sleep 2
done
echo "llama-server listo. Abriendo chat..."
sleep 1
export PATH="$HOME/.local/bin:$PATH"
hermes || true
