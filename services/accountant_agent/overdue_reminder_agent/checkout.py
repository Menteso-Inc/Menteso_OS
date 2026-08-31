"""Secure multi-invoice Stripe Checkout primitives.

No card data passes through Menteso.  A short-lived signed token identifies the
Wave customer, Stripe hosts the payment form, and webhook event IDs provide
idempotency before Wave/Zoho reconciliation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

import requests


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class CheckoutToken:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise ValueError("INVOICE_REMINDER_PORTAL_SECRET must contain at least 32 characters")
        self.secret = secret.encode()

    def issue(self, customer_id: str, ttl_seconds: int = 7 * 86400) -> str:
        body = _b64(json.dumps({"customer_id": customer_id, "exp": int(time.time()) + ttl_seconds},
                               separators=(",", ":"), sort_keys=True).encode())
        signature = _b64(hmac.new(self.secret, body.encode(), hashlib.sha256).digest())
        return f"{body}.{signature}"

    def verify(self, token: str, now: int | None = None) -> dict:
        try:
            body, supplied = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("Invalid checkout link") from exc
        expected = _b64(hmac.new(self.secret, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("Invalid checkout link")
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < int(time.time() if now is None else now):
            raise ValueError("Checkout link has expired")
        return payload


def cents(value: str) -> int:
    return int((Decimal(str(value).replace(",", "")) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class StripeCheckout:
    secret_key: str
    success_url: str
    cancel_url: str

    def create(self, customer_email: str, customer_id: str, invoices: list[dict]) -> dict:
        if len(invoices) < 2:
            raise ValueError("Multi-invoice checkout requires at least two invoices")
        currencies = {i["amountDue"]["currency"]["code"].lower() for i in invoices}
        if len(currencies) != 1:
            raise ValueError("Selected invoices must use one currency")
        form: list[tuple[str, str]] = [
            ("mode", "payment"), ("customer_email", customer_email),
            ("success_url", self.success_url), ("cancel_url", self.cancel_url),
            ("metadata[wave_customer_id]", customer_id),
            ("metadata[wave_invoice_ids]", ",".join(str(i["id"]) for i in invoices)),
            ("payment_intent_data[metadata][wave_customer_id]", customer_id),
            ("payment_intent_data[metadata][wave_invoice_ids]", ",".join(str(i["id"]) for i in invoices)),
        ]
        currency = next(iter(currencies))
        for index, invoice in enumerate(invoices):
            prefix = f"line_items[{index}]"
            form.extend([
                (f"{prefix}[quantity]", "1"),
                (f"{prefix}[price_data][currency]", currency),
                (f"{prefix}[price_data][unit_amount]", str(cents(invoice["amountDue"]["value"]))),
                (f"{prefix}[price_data][product_data][name]", f"Invoice {invoice['invoiceNumber']}"),
                (f"{prefix}[price_data][product_data][description]", f"Due {invoice['dueDate']}"),
            ])
        response = requests.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(self.secret_key, ""), data=form, timeout=30,
            headers={"Idempotency-Key": hashlib.sha256(urlencode(form).encode()).hexdigest()},
        )
        response.raise_for_status()
        return response.json()


def verify_stripe_event(payload: bytes, signature: str, webhook_secret: str,
                        tolerance: int = 300, now: int | None = None) -> dict:
    parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
    timestamp = int(parts.get("t", "0"))
    current = int(time.time() if now is None else now)
    if abs(current - timestamp) > tolerance:
        raise ValueError("Expired Stripe webhook signature")
    expected = hmac.new(webhook_secret.encode(), str(timestamp).encode() + b"." + payload,
                        hashlib.sha256).hexdigest()
    signatures = [item[3:] for item in signature.split(",") if item.startswith("v1=")]
    if not any(hmac.compare_digest(expected, item) for item in signatures):
        raise ValueError("Invalid Stripe webhook signature")
    return json.loads(payload)
