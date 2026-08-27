"""Audited Zoho-to-Wave billing policy.

Never falls back to a generic Wave product. Unknown combinations must be
clarified by Accounts before an invoice is created.
"""
from __future__ import annotations

import re


class BillingPolicyError(ValueError):
    pass


EVENT_PRODUCTS = {
    "speaker": "Speaker Registration",
    "delegate": "Delegate Registration",
    "exhibitor": "Exhibitor",
}

MENTESO_SERVICE_PATTERNS = (
    (r"design patent(?: draw)?", "Design Patent Drawing"),
    (r"(?:utility )?patent draw|patent illustration", "Utility Patent Drawing"),
    (r"patentability (?:search|study)", "Patentability Search"),
    (r"patent application drafting and filing|complete specification", "Patent Application Drafting and Filing"),
    (r"patent application drafting|patent drafting", "Patent Application Drafting"),
    (r"patent application filing|patent filing", "Patent Application Filing"),
    (r"office action", "Office Action Response"),
)


def select_product(company_key: str, service_type: str, events: str,
                   deal_name: str) -> str:
    typ = (service_type or "").strip().lower()
    event = (events or "").strip().lower()
    deal = (deal_name or "").strip().lower()

    if company_key == "IIPLA" and ("iipla" in event or "wlf" in event):
        if typ in EVENT_PRODUCTS:
            return EVENT_PRODUCTS[typ]
        if typ == "courses" and ("cpva" in event or "cpva" in deal):
            return "Certified Patent Valuation Analyst Program (CPVA program)"
        raise BillingPolicyError(
            f"No approved IIPLA/WLF product mapping for Zoho Type {service_type!r}"
        )

    if company_key == "MENTESO":
        for pattern, product in MENTESO_SERVICE_PATTERNS:
            if re.search(pattern, deal):
                return product
        raise BillingPolicyError(
            "No approved Menteso/LexMom/MyEventTrip product mapping for this Zoho service"
        )

    raise BillingPolicyError(f"No billing product policy for company {company_key!r}")


def default_bank_charge(company_key: str, events: str, invoice_type: str,
                        zoho_status: str) -> float:
    """Human-issued event invoices show a $25 line on unpaid invoices.

    Fully-paid Zoho amounts commonly already include charges, so never add one
    while generating/retrieving a paid invoice.
    """
    event = (events or "").upper()
    unpaid = invoice_type == "unpaid" or (
        invoice_type == "unspecified" and "UNPAID" in (zoho_status or "").upper()
    )
    if company_key == "IIPLA" and unpaid and ("IIPLA" in event or "WLF" in event):
        return 25.0
    return 0.0
