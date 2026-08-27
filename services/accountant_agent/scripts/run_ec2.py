"""Run one safe EC2 polling cycle and publish a non-secret health summary."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from src.config import get_config  # noqa: E402
from src.pipeline import build_pipeline  # noqa: E402


def main() -> int:
    cfg = get_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    state_path = Path(os.environ.get(
        "AGENT_STATE_PATH", "/home/menteso_os/data/accountant_agent/status.json"
    ))

    def write_state(payload: dict) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=state_path.parent, prefix=".status-", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(temporary, state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def progress(stage: str, status: str, message: str) -> None:
        write_state({
            "agent": "accountant_agent", "runtime": "ec2-systemd",
            "last_run": datetime.now(timezone.utc).isoformat(),
            "stage": stage, "stage_status": status, "message": message,
            "processed": 0, "skipped": 0, "failed": 0,
        })

    progress("wake_up", "running", "Gmail notification received; agent woke up")
    pipeline = build_pipeline(cfg)
    pipeline._progress = progress
    results = pipeline.run()
    state = {
        "agent": "accountant_agent",
        "runtime": "ec2-systemd",
        "last_run": datetime.now(timezone.utc).isoformat(),
        "processed": sum(r.ok and not r.skipped_reason for r in results),
        "skipped": sum(bool(r.skipped_reason) for r in results),
        "failed": sum(not r.ok and not r.skipped_reason for r in results),
    }
    waiting = next((r for r in reversed(results) if r.case_state in {
        "payment_verification", "error"
    }), None)
    if waiting:
        state["stage"] = waiting.case_state
        state["stage_status"] = "error" if waiting.case_state == "error" else "waiting"
        messages = {
            "payment_verification": f"{waiting.pid}: waiting for payment verification",
            "error": f"{waiting.pid or 'Request'}: accounting action requires attention",
        }
        state["message"] = messages[waiting.case_state]
    elif any(r.case_state == "completed" and r.ok for r in results):
        completed = next(r for r in reversed(results) if r.case_state == "completed" and r.ok)
        state["stage"] = "invoice_sent_for_review"
        state["stage_status"] = "success"
        state["message"] = f"{completed.pid}: invoice sent to employee for review"
    else:
        state["stage"] = "sleeping"
        state["stage_status"] = "idle" if not state["failed"] else "error"
        state["message"] = "Waiting for the next invoice request" if not state["failed"] else "Last run requires attention"
    write_state(state)
    print(json.dumps(state))
    return 1 if state["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
