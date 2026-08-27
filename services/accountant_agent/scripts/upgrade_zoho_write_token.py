"""Privately replace the Zoho refresh token with one carrying CRM write access."""
from __future__ import annotations

import getpass
import os
import tempfile
from pathlib import Path

import requests
from dotenv import dotenv_values


ENV_PATH = Path("/home/menteso_os/secrets/accountant_agent.env")


def main() -> int:
    values = dotenv_values(ENV_PATH)
    dc = values.get("ZOHO_DC") or "com"
    client_id = values.get("ZOHO_CLIENT_ID") or ""
    client_secret = values.get("ZOHO_CLIENT_SECRET") or ""
    if not client_id or not client_secret:
        raise SystemExit("ZOHO_CLIENT_ID or ZOHO_CLIENT_SECRET is missing")
    grant = getpass.getpass("Paste the new Zoho grant code (input is hidden): ").strip()
    response = requests.post(
        f"https://accounts.zoho.{dc}/oauth/v2/token",
        params={"grant_type": "authorization_code", "client_id": client_id,
                "client_secret": client_secret, "code": grant},
        timeout=30,
    )
    data = response.json()
    token = data.get("refresh_token")
    scopes = set(str(data.get("scope") or "").split())
    if not token:
        raise SystemExit(f"Zoho rejected the grant: {data.get('error') or response.status_code}")
    if "ZohoCRM.modules.ALL" not in scopes:
        raise SystemExit("Grant lacks ZohoCRM.modules.ALL; secret file was not changed")

    original = ENV_PATH.read_text(encoding="utf-8").splitlines()
    replaced = False
    output = []
    for line in original:
        if line.startswith("ZOHO_REFRESH_TOKEN="):
            output.append(f"ZOHO_REFRESH_TOKEN={token}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"ZOHO_REFRESH_TOKEN={token}")

    fd, temporary = tempfile.mkstemp(dir=ENV_PATH.parent, prefix=".accountant-env-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, ENV_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Zoho write authorization installed successfully; no secret was displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
