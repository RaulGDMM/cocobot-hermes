#!/usr/bin/env bash

load_copilot_work_account() {
  local gh_config_dir="${HERMES_COPILOT_GH_CONFIG_DIR:-$HOME/.config/gh-work}"
  local token=""

  if [[ -n "${COPILOT_GITHUB_TOKEN:-}" ]]; then
    echo "[copilot] Cuenta fijada mediante COPILOT_GITHUB_TOKEN"
    return 0
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "[copilot] Aviso: gh no esta instalado; no se pudo cargar la cuenta de trabajo"
    return 0
  fi

  token="$(GH_CONFIG_DIR="$gh_config_dir" gh auth token --hostname github.com 2>/dev/null || true)"
  if [[ -z "$token" ]]; then
    echo "[copilot] Aviso: la cuenta de trabajo no esta autenticada en $gh_config_dir"
    return 0
  fi

  export COPILOT_GITHUB_TOKEN="$token"
  echo "[copilot] Modelos fijados a la cuenta de trabajo ($gh_config_dir)"
}

check_copilot_work_account() {
  local response_file=""
  local status=""

  load_copilot_work_account >/dev/null
  response_file="$(mktemp)"
  trap 'rm -f "$response_file"' RETURN
  status="$(curl -sS -o "$response_file" -w '%{http_code}' \
    -H "Authorization: token $COPILOT_GITHUB_TOKEN" \
    -H "User-Agent: GitHubCopilotChat/0.26.7" \
    -H "Editor-Version: vscode/1.104.1" \
    -H "Accept: application/json" \
    https://api.github.com/copilot_internal/v2/token)"

  if [[ "$status" == "200" ]]; then
    echo "[OK] La cuenta de trabajo tiene acceso a GitHub Copilot"
    return 0
  fi

  echo "[!] GitHub Copilot rechazo la cuenta de trabajo (HTTP $status)"
  python3 -c 'import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(data.get("message") or data.get("error") or data.get("error_description") or "Sin detalle")
except Exception:
  text = open(sys.argv[1], encoding="utf-8", errors="replace").read(500).strip()
  print(text or "Respuesta vacia")' "$response_file"
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ -f "$HOME/.hermes/.env" ]]; then
    set -a
    set +u
    # shellcheck disable=SC1091
    source "$HOME/.hermes/.env"
    set -u
    set +a
  fi
  if [[ "${1:-}" == "--check-api" ]]; then
    check_copilot_work_account
  else
    load_copilot_work_account
    [[ -n "${COPILOT_GITHUB_TOKEN:-}" ]]
  fi
fi