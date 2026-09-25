"""Read-only dashboard adapter for the separately managed AccountantAgent service."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_STATUS_FILE = (
    Path("/app/accountant-status/status.json")
    if Path("/app").exists()
    else Path(__file__).resolve().parents[2] / "data" / "accountant_agent" / "status.json"
)
STATUS_FILE = Path(os.getenv("ACCOUNTANT_STATUS_FILE", str(_DEFAULT_STATUS_FILE)))

AGENT_CONFIG = {
    "name": "Accountant Agent",
    "description": "Monitors invoice requests, validates them in Zoho, creates Wave invoices, and replies with the PDF.",
    "role": "Invoice Automation",
    "version": "1.0",
    "status": "active",
    "ui_type": "accountant_monitor",
    "requires_llm": False,
    "accepts_upload": False,
    "group": "AWS Agents",
    "sub_agents": ["Gmail Intake", "Zoho Lookup", "Wave Billing", "Reply-All"],
}


def get_dashboard_data():
    state = {}
    if STATUS_FILE.exists():
        try:
            state = json.loads(STATUS_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            state = {}
    last_run = state.get("last_run", "")
    live = False
    if last_run:
        try:
            stamp = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            live = (datetime.now(timezone.utc) - stamp).total_seconds() < 300
        except ValueError:
            pass
    return {
        "live": bool(state),
        "status": "active" if state else "unavailable",
        "schedule": "Real-time Gmail push",
        "lastRun": last_run,
        "processed": int(state.get("processed", 0)),
        "skipped": int(state.get("skipped", 0)),
        "failed": int(state.get("failed", 0)),
        "runtime": state.get("runtime", "ec2-systemd"),
        "stage": state.get("stage", "sleeping"),
        "stageStatus": state.get("stage_status", "idle"),
        "message": state.get("message", "Waiting for the next invoice request"),
    }


def run_agent(*_args, **_kwargs):
    return {"status": "managed", "message": "This agent wakes automatically when Gmail sends a push notification."}
