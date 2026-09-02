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
REMINDER_STATUS_FILE = Path(os.getenv(
    "OVERDUE_REMINDER_STATUS_FILE",
    str(STATUS_FILE.parent / "overdue-reminder-status.json"),
))

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
    reminder = {}
    if REMINDER_STATUS_FILE.exists():
        try:
            reminder = json.loads(REMINDER_STATUS_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            reminder = {}
    reminder_customers = sorted(
        reminder.get("customers", {}).values(),
        key=lambda row: (row.get("status") == "resolved_or_ineligible", row.get("oldest_due_date") or "9999"),
    )
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
        "reminder": {
            "mode": reminder.get("mode", "test"),
            "paused": bool(reminder.get("paused", False)),
            "lastScanAt": reminder.get("last_scan_at", ""),
            "lastTestAt": reminder.get("last_test_at", ""),
            "eligibleCustomers": int(reminder.get("eligible_customers", 0)),
            "eligibleInvoices": int(reminder.get("eligible_invoices", 0)),
            "overdueTotal": int(reminder.get("overdue_total", reminder.get("eligible_invoices", 0))),
            "waveReminderInvoices": int(reminder.get("wave_reminder_invoices", 0)),
            "agentReminderInvoices": int(reminder.get("agent_reminder_invoices", reminder.get("eligible_invoices", 0))),
            "missingEmailInvoices": int(reminder.get("missing_email_invoices", 0)),
            "agentCollectionTotals": reminder.get("agent_collection_totals", {}),
            "singleInvoiceCustomers": int(reminder.get("single_invoice_customers", 0)),
            "multipleInvoiceCustomers": int(reminder.get("multiple_invoice_customers", 0)),
            "sentEmails": reminder.get("sent_emails", [])[:100],
            "customers": reminder_customers,
        },
    }


def run_agent(*_args, **_kwargs):
    return {"status": "managed", "message": "This agent wakes automatically when Gmail sends a push notification."}
