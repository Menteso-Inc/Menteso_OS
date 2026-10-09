"""Read-only deployment preflight. Exit 3 while the local dashboard has a run.

This script never copies files, changes configuration, stops a process or starts
a run. Use immediately before a separately managed maintenance deployment.
"""
import argparse
import json
from pathlib import Path

import requests
from dotenv import dotenv_values


def check(root):
    config = dotenv_values(root / ".env")
    with requests.Session() as session:
        base = "http://127.0.0.1:" + str(config.get("DASHBOARD_PORT") or "8010")
        response = session.post(base + "/api/login", json={
            "username": config.get("MENTESO_OS_ADMIN_USER", "admin"),
            "password": config.get("MENTESO_OS_ADMIN_PASSWORD", ""),
        }, timeout=10)
        response.raise_for_status()
        agents = session.get(base + "/api/agents", timeout=10)
        agents.raise_for_status()
        active = []
        for agent in agents.json():
            name = agent["module_name"]
            response = session.get(base + f"/api/agents/{name}/run-status", timeout=10)
            response.raise_for_status()
            status = response.json()
            if status.get("status") != "idle":
                active.append({"agent": name, "status": status.get("status"),
                               "run_id": status.get("run_id"), "metrics": status.get("metrics")})
        return {"ready_for_maintenance": not active, "active_runs": active,
                "production_changed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.live_root)
    except Exception as exc:
        # Fail closed without exposing credentials or response bodies.
        print(json.dumps({"ready_for_maintenance": False, "error": type(exc).__name__,
                          "production_changed": False}))
        raise SystemExit(2)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready_for_maintenance"] else 3)
