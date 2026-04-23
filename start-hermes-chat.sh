#!/usr/bin/env bash
# Helper: wait for llama-server then launch hermes chat TUI
trap 'exit 0' INT TERM
echo "Esperando a llama-server..."
while ! curl -sf http://host.docker.internal:30000/health >/dev/null 2>&1; do
  sleep 2
done
echo "llama-server listo. Abriendo chat..."
sleep 1
export PATH="$HOME/.local/bin:$PATH"
hermes || true
