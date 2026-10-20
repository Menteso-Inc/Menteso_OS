"""On-demand production entry point; datasets stay in private run artifacts."""

from __future__ import annotations

import argparse
import json
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path

from shared.research_runtime import _atomic_json, redact
from .agent import run_agent


def main():
    parser = argparse.ArgumentParser(description="Run Lexmom's research specialist on demand")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    args = parser.parse_args()
    cancelled = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
    signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    profile = json.loads(args.input.read_text(encoding="utf-8"))
    if profile.get("mode", "live") != "live":
        parser.error("Production entry point accepts live profiles only")
    started_at = datetime.now(timezone.utc).isoformat()
    def report(step):
        message = step.get("message", "") if isinstance(step, dict) else str(step)
        _atomic_json(args.status_file, redact({"status": "running", "started_at": started_at,
                     "message": message, "updated_at": datetime.now(timezone.utc).isoformat()}))
    report("Preparing the research profile")
    result = run_agent(profile, on_step=report, cancelled=cancelled.is_set)
    receipt = redact({key: result.get(key) for key in (
        "status", "run_id", "manager_run_id", "summary", "budget", "errors",
        "tests", "specialist_tests", "execution_time", "human_review_required",
    )})
    receipt.update(started_at=started_at, completed_at=datetime.now(timezone.utc).isoformat())
    _atomic_json(args.status_file, receipt)
    print(json.dumps(receipt))
    return 0 if result.get("status") in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
