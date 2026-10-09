"""Stop one explicitly identified run and durably capture its completed rows.

Never kill the dashboard. If the run cannot stop or results do not validate,
leave the service in place and refuse the deployment handoff.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import requests
from dotenv import dotenv_values, load_dotenv


def save(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(args.live_root / ".env")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agents.pct_agent.agent import read_input_excel
    from agents.pct_agent.resume import file_hash, load_handoff, policy_fingerprint

    config = dotenv_values(args.live_root / ".env")
    session = requests.Session()
    base = "http://127.0.0.1:8010/api"
    session.post(base + "/login", json={"username": config.get("MENTESO_OS_ADMIN_USER", "admin"),
                 "password": config.get("MENTESO_OS_ADMIN_PASSWORD", "")}, timeout=10).raise_for_status()
    def status():
        response = session.get(base + "/agents/pct_agent/run-status", timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("run_id") != args.run_id:
            raise ValueError("Run identity changed; refusing handoff")
        return data
    initial = status()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save(args.output_dir / "before-stop.json", initial)
    if initial["status"] == "running":
        session.post(base + "/agents/pct_agent/stop", timeout=30).raise_for_status()
        print("Stop requested; waiting for the agent to save results", flush=True)
    deadline = time.monotonic() + 600
    while True:
        current = status()
        if current["status"] == "idle":
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Run has not stopped; dashboard must remain running")
        time.sleep(2)
    save(args.output_dir / "stopped-run.json", current)
    result = current.get("lastEvent", {}).get("result", {})
    results = result.get("results")
    if not results or len(results) < int(initial.get("metrics", {}).get("processedRows", 0)):
        raise ValueError("Saved results are missing completed rows; do not restart dashboard")
    source = Path(result.get("input_file") or initial["input"]["file_path"])
    original = Path(initial["input"]["file_path"])
    if file_hash(source) != file_hash(original):
        raise ValueError("Archived input differs from uploaded input")
    rows = read_input_excel(source)
    handoff = {"version": 1, "source_run_id": args.run_id, "input_file": str(source),
               "input_sha256": file_hash(source), "total": len(rows),
               "policy_fingerprint": policy_fingerprint(), "results": results}
    target = args.output_dir / "resume.json"
    save(target, handoff)
    validated = load_handoff(target, source, rows)
    done = {row["row"] for row in validated}
    print(json.dumps({"status": "handoff_saved", "completed": len(validated), "total": len(rows),
                      "next_row": next((i for i in range(1, len(rows) + 1) if i not in done), None),
                      "resume_path": str(target), "input_file": str(source)}), flush=True)


if __name__ == "__main__":
    main()
