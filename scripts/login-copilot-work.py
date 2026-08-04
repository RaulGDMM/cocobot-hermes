#!/usr/bin/env python3
import json
import sys
import urllib.request

from hermes_cli.config import save_env_value
from hermes_cli.copilot_auth import copilot_device_code_login, exchange_copilot_token


EXPECTED_LOGIN = "rgarciademarina"


def github_login(token: str) -> str:
    request = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "HermesAgent/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return str(json.load(response).get("login", ""))


def main() -> int:
    print("Autenticacion Copilot para la cuenta de trabajo")
    print(f"Cuenta requerida: {EXPECTED_LOGIN}")
    print("Usa una ventana privada si GitHub tiene abierta tu cuenta personal.\n")

    token = copilot_device_code_login()
    if not token:
        print("[!] Autenticacion cancelada o fallida.")
        return 1

    login = github_login(token)
    if login.casefold() != EXPECTED_LOGIN.casefold():
        print(f"[!] Se autorizo la cuenta '{login}', no '{EXPECTED_LOGIN}'.")
        print("    No se guardo ninguna credencial. Repite el proceso en una ventana privada.")
        return 2

    exchange_copilot_token(token)
    save_env_value("COPILOT_GITHUB_TOKEN", token)
    print(f"[OK] Copilot autenticado y fijado a {login}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())