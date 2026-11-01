#!/usr/bin/env bash
# strata-profile.sh {status|normal|uncensored}
set -euo pipefail
D=/mnt/e/Workspace/Openclaw/strata-nvfp4/strata-nvfp4
PF=$D/config/strata-profile.txt
BROKER=http://172.23.176.1:8791
KEY=$(cat ~/.hermes/secrets/strata-api-key 2>/dev/null || true)
status() {
  echo "perfil configurado: $(cat $PF 2>/dev/null || echo 'normal (sin fichero)')"
  if grep -q control-vector $D/config/cocobot.json; then echo "cvec en cocobot.json: SI (uncensored)"; else echo "cvec en cocobot.json: NO (normal)"; fi
  echo -n "strata /health: "; curl -s --max-time 5 -H "Authorization: Bearer $KEY" http://172.23.176.1:8097/health | head -c 200 || echo down; echo
}
case "${1:-status}" in
  status) status ;;
  normal|uncensored)
    printf '%s' "$1" > $PF
    echo "perfil -> $1; pidiendo reinicio al broker..."
    curl -s --max-time 30 -X POST $BROKER/v1/gpu-exec -H 'Content-Type: application/json' \
      -d '{"command":["cmd","/c","exit","0"],"async":true,"needs_gpu":true,"timeout_seconds":60}'; echo
    echo "Strata se relanza en 1-3 min. Comprobar con: $0 status" ;;
  *) echo "uso: $0 {status|normal|uncensored}"; exit 2 ;;
esac
