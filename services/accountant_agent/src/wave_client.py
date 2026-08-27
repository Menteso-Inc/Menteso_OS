"""Wave client — create (or reuse) an invoice in the RIGHT company's Wave business.

Model (confirmed by schema introspection against the live Wave account):
  * The company/business is chosen by the pipeline (src/companies.py) from the
    Zoho deal's Events_or_Services; this client is told which business to use.
  * Invoice line items must reference a Product; we keep one reusable
    "Professional Services (automated)" product per business and override
    description/price per line. Attendees (event delegates) are named in the line.
  * The PID is stamped into `poNumber` — used to find/reuse an existing invoice
    for a PID (one invoice per PID) and for traceability.
  * Discounts are applied as a FIXED-amount invoice discount.
  * Invoices are created SAVED (approved, numbered, has a branded PDF from the
    business's own logo) — Wave does NOT auto-email; the agent sends the PDF.
  * Marking an invoice PAID is possible via invoicePaymentCreateManual but needs
    a per-business deposit account; that wiring is pending, so a "paid" request is
    logged and the invoice is left SAVED for now (safe — a human can mark it paid).

Requires a paid Wave plan (Pro/Advisor).
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .companies import Company, PROHIBITED_WAVE_BUSINESS_IDS
from .config import Config
from .models import GeneratedInvoice, InvoiceDetails

logger = logging.getLogger(__name__)

WAVE_ENDPOINT = "https://gql.waveapps.com/graphql/public"
_MAX_SEARCH_PAGES = 20
WLF_TITLE = "World Lawyers Forum"
WLF_SUBHEAD = "Managed by International Intellectual Property Law Association, Inc. (IIPLA)"
WLF_FOOTER = (
    "589 S 22nd St, San Jose, California 95116, USA\n"
    "Phone: +1 888 355 0013 | Email: mail@worldlawyersforum.org | "
    "Website: worldlawyersforum.org"
)

_INVOICES_BY_PAGE = """
query ($businessId: ID!, $page: Int!) {
  business(id: $businessId) {
    invoices(page: $page, pageSize: 50) {
      pageInfo { currentPage totalPages }
      edges { node { id poNumber invoiceNumber status pdfUrl viewUrl } } }
  }
}
"""
_CUSTOMERS_BY_PAGE = """
query ($businessId: ID!, $page: Int!) {
  business(id: $businessId) {
    customers(page: $page, pageSize: 50) {
      pageInfo { currentPage totalPages }
      edges { node { id name email } } }
  }
}
"""
_PRODUCTS_BY_PAGE = """
query ($businessId: ID!, $page: Int!) {
  business(id: $businessId) {
    products(page: $page, pageSize: 50) {
      pageInfo { currentPage totalPages }
      edges { node { id name } } }
  }
}
"""
_INVOICE_BY_ID = """
query ($businessId: ID!, $page: Int!) { business(id: $businessId) { invoices(page:$page,pageSize:100) { pageInfo { totalPages } edges { node {
  id poNumber invoiceNumber status pdfUrl viewUrl title subhead invoiceDate dueDate
  memo footer customer { name email }
  currency { code } subtotal { value } total { value } amountDue { value }
  items { description quantity unitPrice product { name } }
} } } } }
"""
_CUSTOMER_CREATE = """
mutation ($input: CustomerCreateInput!) {
  customerCreate(input: $input) {
    didSucceed inputErrors { code message path } customer { id name } }
}
"""
_PRODUCT_CREATE = """
mutation ($input: ProductCreateInput!) {
  productCreate(input: $input) {
    didSucceed inputErrors { code message path } product { id name } }
}
"""
_INVOICE_CREATE = """
mutation ($input: InvoiceCreateInput!) {
  invoiceCreate(input: $input) {
    didSucceed inputErrors { code message path }
    invoice { id invoiceNumber status poNumber pdfUrl viewUrl } }
}
"""
_INVOICE_PATCH = """
mutation ($input: InvoicePatchInput!) {
  invoicePatch(input: $input) {
    didSucceed inputErrors { code message path }
    invoice { id invoiceNumber status poNumber pdfUrl viewUrl }
  }
}
"""


class WaveClient:
    def __init__(self, config: Config):
        self._cfg = config
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {config.wave_api_token}",
             "Content-Type": "application/json"}
        )
        self._product_by_business: dict[str, str] = {}  # cache per business

    def _gql(self, query: str, variables: dict) -> dict:
        resp = self._session.post(
            WAVE_ENDPOINT, json={"query": query, "variables": variables}, timeout=45
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise RuntimeError(f"Wave GraphQL error: {payload['errors']}")
        return payload["data"]

    def get_invoice(self, business_id: str, invoice_id: str) -> dict:
        page=1
        while page <= _MAX_SEARCH_PAGES:
            conn=self._gql(_INVOICE_BY_ID,{"businessId":business_id,"page":page})["business"]["invoices"]
            for edge in conn["edges"]:
                if edge["node"]["id"] == invoice_id:
                    return edge["node"]
            if page >= conn["pageInfo"]["totalPages"]: break
            page += 1
        raise RuntimeError(f"Wave invoice {invoice_id} was not found in selected business")

    # --- dedupe by PID (within the given business) ----------------------
    def find_invoice_by_pid(self, business_id: str, pid: str) -> Optional[dict]:
        page = 1
        while page <= _MAX_SEARCH_PAGES:
            conn = self._gql(_INVOICES_BY_PAGE,
                             {"businessId": business_id, "page": page})["business"]["invoices"]
            for edge in conn["edges"]:
                if (edge["node"].get("poNumber") or "") == pid:
                    return edge["node"]
            if page >= conn["pageInfo"]["totalPages"]:
                break
            page += 1
        return None

    # --- reusable product ------------------------------------------------
    def find_product(self, business_id: str, product_name: str) -> str:
        cache_key = f"{business_id}:{product_name.lower()}"
        if cache_key in self._product_by_business:
            return self._product_by_business[cache_key]
        page = 1
        while page <= _MAX_SEARCH_PAGES:
            conn = self._gql(_PRODUCTS_BY_PAGE,
                             {"businessId": business_id, "page": page})["business"]["products"]
            for edge in conn["edges"]:
                if edge["node"]["name"].strip().lower() == product_name.strip().lower():
                    self._product_by_business[cache_key] = edge["node"]["id"]
                    return edge["node"]["id"]
            if page >= conn["pageInfo"]["totalPages"]:
                break
            page += 1
        raise RuntimeError(
            f"Approved Wave product {product_name!r} does not exist in the selected business"
        )

    # --- customer --------------------------------------------------------
    def ensure_customer(self, business_id: str, details: InvoiceDetails) -> str:
        want_name = details.customer_name.strip().lower()
        want_email = (details.customer_email or "").strip().lower()
        page = 1
        while page <= _MAX_SEARCH_PAGES:
            conn = self._gql(_CUSTOMERS_BY_PAGE,
                             {"businessId": business_id, "page": page})["business"]["customers"]
            for edge in conn["edges"]:
                node = edge["node"]
                if node["name"].strip().lower() == want_name or (
                    want_email and (node.get("email") or "").strip().lower() == want_email
                ):
                    return node["id"]
            if page >= conn["pageInfo"]["totalPages"]:
                break
            page += 1
        cust = {"businessId": business_id, "name": details.customer_name}
        if details.customer_email:
            cust["email"] = details.customer_email
        result = self._gql(_CUSTOMER_CREATE, {"input": cust})["customerCreate"]
        if not result["didSucceed"]:
            raise RuntimeError(f"Wave customerCreate failed: {result['inputErrors']}")
        return result["customer"]["id"]

    # --- create ----------------------------------------------------------
    def create_invoice(self, business_id: str, details: InvoiceDetails,
                       customer_id: str) -> dict:
        items = self._invoice_items(business_id, details)

        invoice_input = {
            "businessId": business_id,
            "customerId": customer_id,
            "status": "SAVED",
            "currency": details.currency or "USD",
            "poNumber": details.pid,
            "memo": details.memo,
            "items": items,
        }
        if "WLF" in (details.events_or_services or "").upper():
            invoice_input.update({"title": WLF_TITLE, "subhead": WLF_SUBHEAD,
                                  "footer": WLF_FOOTER})
        if details.due_date:
            invoice_input["dueDate"] = details.due_date
        if details.discount_amount and details.discount_amount > 0:
            invoice_input["discounts"] = [{
                "discountType": "FIXED", "name": "Discount",
                "amount": details.discount_amount,
            }]
        result = self._gql(_INVOICE_CREATE, {"input": invoice_input})["invoiceCreate"]
        if not result["didSucceed"]:
            raise RuntimeError(f"Wave invoiceCreate failed: {result['inputErrors']}")
        return result["invoice"]

    def _invoice_items(self, business_id: str, details: InvoiceDetails) -> list[dict]:
        source_items = details.line_items or []
        items = []
        for index, line in enumerate(source_items):
            description = line.description
            if index == 0 and details.attendees:
                names = "\n".join(a.name for a in details.attendees)
                description = f"{description}\n{names}"
            if not line.product_name:
                raise RuntimeError("Invoice line is missing an approved Wave product")
            items.append({
                "productId": self.find_product(business_id, line.product_name),
                "description": description,
                "quantity": line.quantity,
                "unitPrice": line.unit_price,
            })
        if not items:
            raise RuntimeError("Invoice has no approved line items")

        return items

    def update_invoice(self, invoice_id: str, details: InvoiceDetails,
                       company: Company) -> GeneratedInvoice:
        """Patch an existing Wave invoice and return its newly rendered PDF."""
        customer_id = self.ensure_customer(company.wave_business_id, details)
        patch = {
            "id": invoice_id,
            "customerId": customer_id,
            "currency": details.currency or "USD",
            "poNumber": details.pid,
            "memo": details.memo,
            "items": self._invoice_items(company.wave_business_id, details),
            "discounts": ([{
                "discountType": "FIXED", "name": "Discount",
                "amount": details.discount_amount,
            }] if details.discount_amount > 0 else []),
        }
        if "WLF" in (details.events_or_services or "").upper():
            patch.update({"title": WLF_TITLE, "subhead": WLF_SUBHEAD,
                          "footer": WLF_FOOTER})
        if details.due_date:
            patch["dueDate"] = details.due_date
        result = self._gql(_INVOICE_PATCH, {"input": patch})["invoicePatch"]
        if not result["didSucceed"]:
            raise RuntimeError(f"Wave invoicePatch failed: {result['inputErrors']}")
        invoice = self.get_invoice(company.wave_business_id, invoice_id)
        if not invoice.get("pdfUrl"):
            raise RuntimeError(f"Wave invoice {invoice_id} has no pdfUrl after correction")
        return GeneratedInvoice(
            wave_invoice_id=invoice["id"],
            invoice_number=invoice.get("invoiceNumber", ""),
            pdf_bytes=self._download_pdf(invoice["pdfUrl"]),
            view_url=invoice.get("viewUrl", ""),
            status=invoice.get("status", ""),
            invoice_data=invoice,
        )

    # --- orchestration ---------------------------------------------------
    def generate(self, details: InvoiceDetails, company: Company) -> GeneratedInvoice:
        """One invoice per PID in the routed company's business. Returns the PDF."""
        from .config import require_config
        require_config(self._cfg, {"WAVE_API_TOKEN": self._cfg.wave_api_token}, "section 3")
        bid = company.wave_business_id
        if bid in PROHIBITED_WAVE_BUSINESS_IDS:
            raise RuntimeError(
                "AccountantAgent policy forbids creating invoices in ANF Global Inc."
            )

        invoice = self.find_invoice_by_pid(bid, details.pid)
        if invoice:
            logger.info("Reusing Wave invoice %s for PID %s in %s",
                        invoice.get("invoiceNumber"), details.pid, company.name)
        else:
            customer_id = self.ensure_customer(bid, details)
            invoice = self.create_invoice(bid, details, customer_id)
            logger.info("Created Wave invoice %s for PID %s in %s",
                        invoice.get("invoiceNumber"), details.pid, company.name)

        if details.is_paid:
            # invoicePaymentCreateManual needs a per-business deposit account (not yet
            # wired). Leave SAVED (unpaid) rather than fake it; flag for follow-up.
            logger.warning("PID %s requested PAID — payment recording not yet wired; "
                           "invoice left SAVED. Mark paid in Wave for now.", details.pid)

        invoice = self.get_invoice(bid, invoice["id"])
        pdf_url = invoice.get("pdfUrl")
        if not pdf_url:
            raise RuntimeError(f"Wave invoice {invoice.get('id')} has no pdfUrl")

        return GeneratedInvoice(
            wave_invoice_id=invoice["id"],
            invoice_number=invoice.get("invoiceNumber", ""),
            pdf_bytes=self._download_pdf(pdf_url),
            view_url=invoice.get("viewUrl", ""),
            status=invoice.get("status", ""),
            invoice_data=invoice,
        )

    def _download_pdf(self, pdf_url: str) -> bytes:
        resp = requests.get(
            pdf_url, headers={"Authorization": f"Bearer {self._cfg.wave_api_token}"}, timeout=60,
        )
        resp.raise_for_status()
        return resp.content
