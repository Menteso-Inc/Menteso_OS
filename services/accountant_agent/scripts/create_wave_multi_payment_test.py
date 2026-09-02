"""Create two idempotent $0.50 live Wave invoices for the internal Stripe test."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from src.companies import MENTESO
from src.config import get_config
from src.models import InvoiceDetails
from src.wave_client import WaveClient, _INVOICE_CREATE

APPROVED_RECIPIENTS = {"sajan@menteso.com", "shweta@menteso.com", "azam@menteso.com"}
PRODUCT_NAME = "Professional Services (automated)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--confirm-live-test", action="store_true")
    args = parser.parse_args()
    recipient = args.recipient.strip().lower()
    if not args.confirm_live_test:
        raise SystemExit("Refusing to create live Wave invoices without --confirm-live-test")
    if recipient not in APPROVED_RECIPIENTS:
        raise SystemExit("Recipient must be an approved internal Menteso address")

    wave = WaveClient(get_config())
    customer_id = wave.ensure_customer(MENTESO.wave_business_id, InvoiceDetails(
        pid="STRIPE-LIVE-TEST-CUSTOMER", zoho_record_id="", customer_name="Menteso Stripe Payment Test",
        customer_email=recipient,
    ))
    product_id = wave.find_product(MENTESO.wave_business_id, PRODUCT_NAME)
    date = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    created = []
    for suffix in ("A", "B"):
        po_number = f"STRIPE-LIVE-TEST-{date}-{suffix}"
        existing = wave.find_invoice_by_pid(MENTESO.wave_business_id, po_number)
        if existing:
            created.append(existing)
            continue
        result = wave._gql(_INVOICE_CREATE, {"input": {
            "businessId": MENTESO.wave_business_id,
            "customerId": customer_id,
            "status": "SAVED",
            "currency": "USD",
            "invoiceDate": date,
            "dueDate": date,
            "poNumber": po_number,
            "memo": "CONTROLLED LIVE STRIPE TEST - internal only - $0.50",
            "items": [{"productId": product_id, "description": "Controlled Stripe integration test",
                       "quantity": 1, "unitPrice": 0.50}],
        }})["invoiceCreate"]
        if not result.get("didSucceed"):
            raise RuntimeError(f"Wave invoiceCreate failed: {result.get('inputErrors')}")
        created.append(result["invoice"])
    print(json.dumps({"customer_id": customer_id, "recipient": recipient,
                      "maximum_total_usd": 1.00, "invoices": created}, indent=2))


if __name__ == "__main__":
    main()
