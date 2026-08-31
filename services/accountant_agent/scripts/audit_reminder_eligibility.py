"""Read-only explanation of Wave invoice eligibility; prints counts, not client PII."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overdue_reminder_agent.agent import OverdueReminderAgent, QUERY
from src.companies import MENTESO
from src.config import get_config
from src.wave_client import WaveClient


wave = WaveClient(get_config())
status_counts: Counter[str] = Counter()
excluded: Counter[str] = Counter()
eligible_invoices = []
page = 1
while True:
    connection = wave._gql(QUERY, {"id": MENTESO.wave_business_id, "page": page})["business"]["invoices"]
    for edge in connection["edges"]:
        invoice = edge["node"]
        status = str(invoice.get("status") or "UNKNOWN")
        status_counts[status] += 1
        if status != "OVERDUE":
            continue
        customer = invoice.get("customer") or {}
        if not str(customer.get("email") or "").strip():
            excluded["missing_customer_email"] += 1
        elif not OverdueReminderAgent.wave_finished(invoice):
            excluded["wave_reminders_not_finished_or_not_configured"] += 1
        else:
            eligible_invoices.append(invoice)
    if page >= connection["pageInfo"]["totalPages"]:
        break
    page += 1

customer_counts = Counter(str((invoice.get("customer") or {}).get("id") or "") for invoice in eligible_invoices)
single_customers = sum(1 for count in customer_counts.values() if count == 1)
multiple_customers = sum(1 for count in customer_counts.values() if count > 1)

print("business=Menteso, Inc.")
print("status_counts=" + ",".join(f"{key}:{value}" for key, value in sorted(status_counts.items())))
print(f"overdue_total={status_counts['OVERDUE']}")
print(f"eligible_invoices={len(eligible_invoices)}")
print(f"eligible_customers={len(customer_counts)}")
print(f"single_invoice_customers={single_customers}")
print(f"multiple_invoice_customers={multiple_customers}")
for reason, count in sorted(excluded.items()):
    print(f"excluded_{reason}={count}")
print(f"reconciles={status_counts['OVERDUE'] == len(eligible_invoices) + sum(excluded.values())}")
