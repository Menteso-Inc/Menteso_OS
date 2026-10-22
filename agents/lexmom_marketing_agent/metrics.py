"""Read-only business summary of preserved Lexmom runs, without provider calls."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit


def business_summary(state_root: Path) -> dict:
    # Reservations are safety allowances, not provider invoices. Revenue needs
    # payment attribution before either money metric can claim an actual total.
    summary = {"currency": "USD", "total_spend_usd": None, "total_revenue_usd": None,
               "qualified_leads": 0, "reserved_cost_usd": 0.0, "history_complete": True}
    firms, children = set(), set()
    reservation = Decimal("0")
    from .agent import resolve_research_artifact

    for receipt_path in (state_root / "lexmom_marketing_agent").glob("*/completion.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("agent") != "lexmom_marketing_agent":
                continue
            if receipt.get("run_id") != receipt_path.parent.name:
                raise ValueError("Mismatched manager receipt")
            manager = json.loads((receipt_path.parent / "result.json").read_text(encoding="utf-8"))
            child_id = manager.get("run_id")
            if not child_id or child_id in children:
                continue
            artifact = resolve_research_artifact(child_id, "result.json", state_root=state_root)
            if artifact is None:
                raise ValueError("Missing child artifact")
            child = json.loads(artifact.read_text(encoding="utf-8"))
            children.add(child_id)
            if child.get("mode") != "live":
                continue
            amount = Decimal(str(child.get("budget", {}).get("reserved_cost_usd", 0)))
            if not amount.is_finite() or amount < 0:
                raise ValueError("Invalid reservation")
            reservation += amount
            # Failure costs still count, but unvalidated output is not a lead.
            if child.get("tests", {}).get("passed") is not True:
                continue
            for firm in child.get("data", {}).get("firms", []):
                if firm.get("fit_status") != "qualified" or firm.get("provenance") != "live":
                    continue
                domain = firm.get("domain") or firm.get("website") or ""
                host = urlsplit(domain if "://" in domain else "https://" + domain).hostname
                if host:
                    firms.add(host.lower().removeprefix("www.").rstrip("."))
        except (OSError, ValueError, TypeError, AttributeError, InvalidOperation):
            summary["history_complete"] = False
    summary.update(qualified_leads=len(firms), reserved_cost_usd=float(reservation))
    return summary
