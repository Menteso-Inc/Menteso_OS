"""Install a console reporting credential from stdin, without logging its value.

Run as root on the gateway: sudo python3 configure_admin_env.py
This is an operator utility, not an HTTP endpoint. Never pass keys as arguments.
"""

import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

import requests

ENV_FILE = Path("/etc/menteso-console/console.env")


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run this utility as root on the server console.")
    key = sys.stdin.read(1024).strip()
    if not re.fullmatch(r"sk-admin-[A-Za-z0-9_-]{40,}", key):
        raise SystemExit("A valid Admin credential is required on stdin; value suppressed.")
    try:
        response = requests.get(
            "https://api.openai.com/v1/organization/costs",
            headers={"Authorization": "Bearer " + key},
            params={"start_time": int(time.time()) - 86400, "limit": 1},
            timeout=25,
        )
    except requests.RequestException:
        raise SystemExit("Could not verify reporting access; environment unchanged.")
    if not response.ok:
        raise SystemExit(f"Reporting verification returned HTTP {response.status_code}; environment unchanged.")
    if ENV_FILE.is_symlink() or not ENV_FILE.is_file():
        raise SystemExit("Expected a regular existing console environment file.")

    content = ENV_FILE.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines()
             if not re.match(r"^\s*(?:export\s+)?OPENAI_ADMIN_KEY\s*=", line)]
    lines.append("OPENAI_ADMIN_KEY=" + key)
    backup = ENV_FILE.with_name("console.env.before-openai-" + str(time.time_ns()))
    shutil.copy2(ENV_FILE, backup)
    os.chmod(backup, 0o600)
    fd, staged_path = tempfile.mkstemp(prefix=".console-env-", dir=ENV_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged_path, 0o600)
        os.replace(staged_path, ENV_FILE)
    finally:
        if os.path.exists(staged_path):
            os.unlink(staged_path)
    print("Admin reporting credential installed in the protected server environment; value not logged.")


if __name__ == "__main__":
    main()
