"""Zoho CRM client — look up a project's invoice details by PID.

Uses OAuth2 refresh-token flow for auth and COQL (CRM Object Query Language)
to query the Opportunities/Deals module by the custom Project ID field.

IMPORTANT — org-specific values you must confirm (docs/SETUP.md section 2):
  * ZOHO_MODULE     : the module API name (usually "Deals").
  * ZOHO_PID_FIELD  : the API name of your Project ID field (e.g. "Project_ID").
  * The field API names selected below (Deal_Name, Amount, ...) must exist in
    your org. Run scripts/inspect_zoho_module.py to list the real API names,
    then adjust FIELD_MAP if yours differ.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import requests

from .config import Config
from .models import InvoiceDetails, LineItem

logger = logging.getLogger(__name__)

# Zoho Deals field API names this client reads (confirmed via inspect_zoho_module.py
# against the menteso.com org). The Search API returns all populated fields, so we
# just read these by name in _to_invoice_details:
#   Deal_Name, Amount, Payment_Status, Invoice_Number, Client_Reference
# and the PID field from config (ZOHO_PID_FIELD = Project_ID_PID).


class ZohoClient:
    def __init__(self, config: Config):
        from .config import require_config

        require_config(
            config,
            {
                "ZOHO_CLIENT_ID": config.zoho_client_id,
                "ZOHO_CLIENT_SECRET": config.zoho_client_secret,
                "ZOHO_REFRESH_TOKEN": config.zoho_refresh_token,
            },
            "section 2",
        )
        self._cfg = config
        self._access_token: Optional[str] = None
        self._token_scopes: set[str] = set()

    # --- auth ------------------------------------------------------------
    def _refresh_access_token(self) -> str:
        resp = requests.post(
            f"{self._cfg.zoho_accounts_base}/oauth/v2/token",
            params={
                "refresh_token": self._cfg.zoho_refresh_token,
                "client_id": self._cfg.zoho_client_id,
                "client_secret": self._cfg.zoho_client_secret,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"Zoho token refresh failed: {data}")
        self._access_token = data["access_token"]
        self._token_scopes = set(str(data.get("scope") or "").split())
        return self._access_token

    def require_write_access(self) -> None:
        """Fail before Wave creation unless CRM write/attachment access is present."""
        if not self._access_token:
            self._refresh_access_token()
        if "ZohoCRM.modules.ALL" not in self._token_scopes:
            raise RuntimeError(
                "Zoho authorization is read-only. AccountantAgent did not create a Wave invoice. "
                "Regenerate the Zoho refresh token with "
                "ZohoCRM.modules.ALL,ZohoCRM.settings.READ."
            )

    def _headers(self) -> dict:
        if not self._access_token:
            self._refresh_access_token()
        return {"Authorization": f"Zoho-oauthtoken {self._access_token}"}

    # --- query -----------------------------------------------------------
    def find_by_pid(self, pid: str) -> Optional[InvoiceDetails]:
        """Return InvoiceDetails for the Deal whose PID field == pid, or None.

        Uses the Search Records API (criteria search), which works with the
        ZohoCRM.modules.READ scope. (COQL needs a separate ZohoCRM.coql.READ scope
        that our token doesn't carry.)
        """
        module = self._cfg.zoho_module
        pid_field = self._cfg.zoho_pid_field
        params = {"criteria": f"({pid_field}:equals:{pid})"}

        def _do_search() -> requests.Response:
            return requests.get(
                f"{self._cfg.zoho_api_base}/{module}/search",
                headers=self._headers(), params=params, timeout=30,
            )

        resp = _do_search()
        if resp.status_code == 401:  # token expired mid-run -> refresh once and retry
            self._refresh_access_token()
            resp = _do_search()
        # Zoho returns 204 (no body) when nothing matches.
        if resp.status_code == 204:
            logger.info("Zoho: no %s record found for PID %s", module, pid)
            return None
        resp.raise_for_status()

        records = resp.json().get("data", [])
        if not records:
            return None
        return self._to_invoice_details(pid, records[0])

    def _get_record(self, module: str, record_id: str) -> dict:
        resp = requests.get(
            f"{self._cfg.zoho_api_base}/{module}/{record_id}",
            headers=self._headers(), timeout=30,
        )
        if resp.status_code == 401:
            self._refresh_access_token()
            resp = requests.get(
                f"{self._cfg.zoho_api_base}/{module}/{record_id}",
                headers=self._headers(), timeout=30,
            )
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        return rows[0] if rows else {}

    def _to_invoice_details(self, pid: str, record: dict) -> InvoiceDetails:
        amount = float(record.get("Amount") or 0.0)
        account = record.get("Account_Name")
        contact = record.get("Contact_Name")
        account_id = str(account.get("id")) if isinstance(account, dict) and account.get("id") else None
        contact_id = str(contact.get("id")) if isinstance(contact, dict) and contact.get("id") else None
        account_record = self._get_record("Accounts", account_id) if account_id else {}
        contact_record = self._get_record("Contacts", contact_id) if contact_id else {}
        customer = (
            account.get("name") if isinstance(account, dict) else account
        ) or (
            contact.get("name") if isinstance(contact, dict) else contact
        ) or record.get("Deal_Name") or "Customer"
        ref = record.get("Client_Reference")
        # Events_or_Services is a multi-select (a list) -> normalize to a string;
        # companies.route() reads this to pick the Wave business.
        evt = record.get("Events_or_Services")
        if isinstance(evt, (list, tuple)):
            evt = ", ".join(str(x) for x in evt)
        details = InvoiceDetails(
            pid=pid,
            zoho_record_id=str(record.get("id")),
            customer_name=customer,
            customer_email=contact_record.get("Email"),
            currency=str(record.get("Currency") or "USD"),
            status=str(record.get("Payment_Status") or ""),
            memo=f"Invoice for project {pid}" + (f" (ref {ref})" if ref else ""),
            events_or_services=evt or "",
            account_id=account_id,
            contact_id=contact_id,
            customer_phone=contact_record.get("Phone") or account_record.get("Phone"),
            customer_address=self._address(contact_record, "Mailing") or self._address(account_record, "Billing"),
            service_type=str(record.get("Type") or ""),
            deal_name=str(record.get("Deal_Name") or ""),
        )
        # Single summary line item from the deal amount. Expand if your invoices
        # have itemized lines stored elsewhere in Zoho.
        description = evt or str(record.get("Deal_Name") or pid)
        details.line_items.append(
            LineItem(description=description, quantity=1.0, unit_price=amount)
        )
        return details

    @staticmethod
    def _address(record: dict, prefix: str) -> Optional[str]:
        parts = [
            record.get(f"{prefix}_Street"), record.get(f"{prefix}_City"),
            record.get(f"{prefix}_State"), record.get(f"{prefix}_Zip"),
            record.get(f"{prefix}_Country"),
        ]
        value = ", ".join(str(x).strip() for x in parts if x)
        return value or None

    def complete_invoice(self, details: InvoiceDetails, invoice_number: str,
                         wave_invoice_id: str, wave_view_url: str,
                         pdf_bytes: bytes, create_missing_contacts: bool = False) -> list[str]:
        """Update the Deal and attach the final PDF to relevant Zoho records."""
        filename = f"invoice-{details.pid}-{invoice_number}.pdf"
        updates = {"Invoice_Number": invoice_number}
        if details.is_paid:
            updates["Payment_Status"] = "Paid"
        resp = requests.put(
            f"{self._cfg.zoho_api_base}/{self._cfg.zoho_module}/{details.zoho_record_id}",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"data": [updates]}, timeout=30,
        )
        resp.raise_for_status()
        result = (resp.json().get("data") or [{}])[0]
        if result.get("status") != "success":
            raise RuntimeError(f"Zoho Deal update failed: {result}")

        attached = []
        if self._attach_if_changed(
            self._cfg.zoho_module, details.zoho_record_id, filename, pdf_bytes,
            details.pid, invoice_number,
        ):
            attached.append(f"{self._cfg.zoho_module}:{details.zoho_record_id}")
        if details.contact_id:
            if self._attach_if_changed(
                "Contacts", details.contact_id, filename, pdf_bytes,
                details.pid, invoice_number,
            ):
                attached.append(f"Contacts:{details.contact_id}")

        if create_missing_contacts:
            for attendee in details.attendees:
                contact_id = self._ensure_contact(attendee.name, attendee.email, details.account_id)
                if contact_id and contact_id != details.contact_id:
                    if self._attach_if_changed(
                        "Contacts", contact_id, filename, pdf_bytes,
                        details.pid, invoice_number,
                    ):
                        attached.append(f"Contacts:{contact_id}")

        note = {
            "Note_Title": f"Invoice {invoice_number} generated by AccountantAgent",
            "Note_Content": (
                f"PID: {details.pid}\nWave invoice ID: {wave_invoice_id}\n"
                f"Wave URL: {wave_view_url}\nStatus: {'Paid' if details.is_paid else 'Unpaid'}"
            ),
            "Parent_Id": details.zoho_record_id,
            "$se_module": self._cfg.zoho_module,
        }
        note_resp = requests.post(
            f"{self._cfg.zoho_api_base}/Notes",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"data": [note]}, timeout=30,
        )
        if not note_resp.ok:
            # Notes are useful audit metadata, but the Deal update and PDF
            # attachments above are the required accounting records. A custom
            # Zoho layout can reject Notes; do not withhold the employee's
            # invoice after the required CRM writes have succeeded.
            logger.warning(
                "Zoho optional Note was not created for PID %s (HTTP %s)",
                details.pid, note_resp.status_code,
            )
        return attached

    def _attach_if_changed(self, module: str, record_id: str, filename: str,
                           content: bytes, pid: str, invoice_number: str) -> bool:
        """Upload only when this exact invoice PDF is not already on the record.

        Zoho renames duplicate filenames, so filename equality alone is not safe.
        Candidate files are selected using PID + invoice number, then downloaded
        and compared by SHA-256. A corrected PDF is therefore still uploaded,
        while retries of identical content are idempotent.
        """
        url = f"{self._cfg.zoho_api_base}/{module}/{record_id}/Attachments"
        resp = requests.get(
            url, headers=self._headers(),
            params={"fields": "id,File_Name,Size", "per_page": 200}, timeout=30,
        )
        resp.raise_for_status()
        target_hash = hashlib.sha256(content).digest()
        pid_token = str(pid).lower()
        invoice_token = str(invoice_number).lower()
        for item in resp.json().get("data", []):
            existing_name = str(item.get("File_Name") or "").lower()
            if pid_token not in existing_name or invoice_token not in existing_name:
                continue
            if item.get("Size") is not None and int(item["Size"]) != len(content):
                continue
            attachment_id = item.get("id")
            if not attachment_id:
                continue
            existing = requests.get(
                f"{url}/{attachment_id}", headers=self._headers(), timeout=45,
            )
            existing.raise_for_status()
            if hashlib.sha256(existing.content).digest() == target_hash:
                logger.info(
                    "Skipping identical Zoho attachment %s on %s:%s",
                    filename, module, record_id,
                )
                return False
        self._attach(module, record_id, filename, content)
        return True

    def _attach(self, module: str, record_id: str, filename: str, content: bytes) -> None:
        resp = requests.post(
            f"{self._cfg.zoho_api_base}/{module}/{record_id}/Attachments",
            headers=self._headers(), files={"file": (filename, content, "application/pdf")},
            timeout=45,
        )
        resp.raise_for_status()
        result = (resp.json().get("data") or [{}])[0]
        if result.get("status") != "success":
            raise RuntimeError(f"Zoho attachment failed for {module}:{record_id}: {result}")

    def _ensure_contact(self, name: str, email: Optional[str], account_id: Optional[str]) -> Optional[str]:
        if email:
            resp = requests.get(
                f"{self._cfg.zoho_api_base}/Contacts/search",
                headers=self._headers(), params={"email": email}, timeout=30,
            )
            if resp.status_code == 200:
                rows = resp.json().get("data", [])
                if rows:
                    return str(rows[0]["id"])
            elif resp.status_code != 204:
                resp.raise_for_status()
        pieces = name.strip().split()
        payload = {
            "Last_Name": pieces[-1] if pieces else "Unknown",
            "First_Name": " ".join(pieces[:-1]) or None,
            "Email": email,
        }
        if account_id:
            payload["Account_Name"] = {"id": account_id}
        payload = {k: v for k, v in payload.items() if v}
        resp = requests.post(
            f"{self._cfg.zoho_api_base}/Contacts",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"data": [payload]}, timeout=30,
        )
        resp.raise_for_status()
        result = (resp.json().get("data") or [{}])[0]
        if result.get("status") != "success":
            raise RuntimeError(f"Zoho Contact create failed: {result}")
        return str(result.get("details", {}).get("id") or "") or None
