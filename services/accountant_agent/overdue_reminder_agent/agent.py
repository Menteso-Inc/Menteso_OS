from __future__ import annotations

import io, json, os
from html import escape
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from src.companies import MENTESO
from src.email_client import GmailClient
from src.wave_client import WaveClient
from src.zoho_client import ZohoClient
from overdue_reminder_agent.checkout import CheckoutToken

TEST_RECIPIENT = "shweta@menteso.com"
AUTHORIZED_APPROVERS = {TEST_RECIPIENT, "sajan@menteso.com", "azam@menteso.com"}
FOLLOW_UP_DAYS = 7


def reminder_gmail_config(base_cfg):
    """Load the isolated Accounts OAuth bundle without touching invoice-request auth."""
    secret_name = os.getenv("INVOICE_REMINDER_AWS_SECRET_NAME", "invoice-reminder-agent/gmail")
    region = os.getenv("INVOICE_REMINDER_AWS_REGION", "us-east-2")
    import boto3

    secret = boto3.client("secretsmanager", region_name=region).get_secret_value(
        SecretId=secret_name
    )
    values = json.loads(secret["SecretString"])
    required = {
        "MAILBOX_ADDRESS", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN", "GOOGLE_SCOPES",
    }
    missing = sorted(key for key in required if not values.get(key))
    if missing:
        raise RuntimeError(f"Invoice Reminder Gmail secret is missing: {', '.join(missing)}")
    mailbox = str(values["MAILBOX_ADDRESS"]).strip().lower()
    if mailbox != "accounts@menteso.com":
        raise RuntimeError(f"Invoice Reminder Gmail secret has the wrong mailbox: {mailbox}")
    return replace(
        base_cfg,
        mailbox_address=mailbox,
        google_client_id=values["GOOGLE_CLIENT_ID"],
        google_client_secret=values["GOOGLE_CLIENT_SECRET"],
        google_refresh_token=values["GOOGLE_REFRESH_TOKEN"],
        # Clearing both fields is essential: GmailClient otherwise prefers the
        # Invoice Request service account over this dedicated OAuth grant.
        google_service_account_file="",
        google_service_account_json="",
    )

QUERY = '''query($id:ID!,$page:Int!){business(id:$id){id name invoices(page:$page,pageSize:100){pageInfo{totalPages} edges{node{id invoiceNumber poNumber status dueDate pdfUrl viewUrl lastSentAt amountDue{value currency{code}} customer{id name email} invoiceReminders{id daysDelta sent sentManually issueDate}}}}}}'''

@dataclass
class Group:
    customer_id: str
    name: str
    email: str
    invoices: list[dict]

class OverdueReminderAgent:
    def __init__(self, cfg, state_path: str):
        self.cfg=cfg; self.wave=WaveClient(cfg); self.state_path=Path(state_path)
        self.state=self._load()

    def _load(self):
        if self.state_path.exists(): return json.loads(self.state_path.read_text())
        return {"mode":"test","paused":False,"customers":{},"authorized_approvers":sorted(AUTHORIZED_APPROVERS)}

    def save(self):
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        self.state_path.write_text(json.dumps(self.state,indent=2,sort_keys=True))

    def customer_paused(self, customer_id: str) -> bool:
        return bool(self.state.get("customers", {}).get(customer_id, {}).get("paused"))

    def set_customer_paused(self, customer_id: str, paused: bool) -> None:
        row = self.state.setdefault("customers", {}).setdefault(customer_id, {})
        row["paused"] = bool(paused)
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def due_for_follow_up(self, customer_id: str, now=None) -> bool:
        if self.state.get("paused") or self.customer_paused(customer_id):
            return False
        last = self.state.get("customers", {}).get(customer_id, {}).get("last_live_sent_at")
        if not last:
            return True
        sent_at = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return (now or datetime.now(timezone.utc)) >= sent_at + timedelta(days=FOLLOW_UP_DAYS)

    @staticmethod
    def wave_finished(invoice):
        reminders=invoice.get("invoiceReminders") or []
        return bool(reminders) and all(r.get("sent") for r in reminders)

    def collect(self):
        grouped={}; page=1
        while True:
            conn=self.wave._gql(QUERY,{"id":MENTESO.wave_business_id,"page":page})["business"]["invoices"]
            for edge in conn["edges"]:
                inv=edge["node"]
                if inv["status"]!="OVERDUE" or not self.wave_finished(inv): continue
                customer=inv.get("customer") or {}; email=(customer.get("email") or "").strip()
                if not email: continue
                key=customer["id"]; grouped.setdefault(key,Group(key,customer.get("name") or "Customer",email,[])).invoices.append(inv)
            if page>=conn["pageInfo"]["totalPages"]: break
            page+=1
        return sorted(grouped.values(),key=lambda x:min(i["dueDate"] for i in x.invoices))

    @staticmethod
    def render(group):
        total=sum(float(i["amountDue"]["value"].replace(",","")) for i in group.invoices)
        currency=group.invoices[0]["amountDue"]["currency"]["code"]
        rows="\n".join(f"- Invoice {i['invoiceNumber']} | due {i['dueDate']} | {i['amountDue']['value']} {i['amountDue']['currency']['code']} | {i['viewUrl']}" for i in group.invoices)
        subject=(f"Quick follow-up on invoice {group.invoices[0]['invoiceNumber']}" if len(group.invoices)==1 else f"Quick follow-up on your {len(group.invoices)} outstanding invoices")
        first_name=OverdueReminderAgent.customer_first_name(group.name)
        body=f"""Hi {first_name},

I hope you are doing well.

I am writing to follow up on the overdue invoice payment below:\n{rows}

Total currently due: {total:.2f} {currency}

Could you please provide an update on the payment status and let us know when we can expect the outstanding amount to be settled? Understanding the timeline is important for our internal financial planning.

If payment has already been made, please reply with the payment details so we can reconcile our records. Please also let me know if you need any further information or documentation from our side.

Thank you for your prompt attention to this matter.

Best regards,
Menteso Accounts Team
accounts@menteso.com
"""
        return subject,body

    @staticmethod
    def customer_first_name(name: str) -> str:
        cleaned = name.replace("(Individual)", "").replace("Individual-", "").strip(" -")
        return (cleaned.split()[0] if cleaned else "there").title()

    @classmethod
    def render_html(cls, group: Group, test_banner: str = "") -> str:
        first_name = escape(cls.customer_first_name(group.name))
        invoice_count = len(group.invoices)
        if invoice_count == 1:
            invoice = group.invoices[0]
            detail = (
                f"I’m following up about invoice <strong>{escape(str(invoice['invoiceNumber']))}</strong>, "
                f"which was due on {escape(str(invoice['dueDate']))}. Our records still show "
                f"<strong>{escape(str(invoice['amountDue']['value']))} "
                f"{escape(invoice['amountDue']['currency']['code'])}</strong> outstanding."
            )
            actions = f"<div style='margin:20px 0'>{cls._pay_button(invoice.get('viewUrl') or '', 'Pay now')}</div>"
        else:
            total = sum(float(str(i["amountDue"]["value"]).replace(",", "")) for i in group.invoices)
            currency = escape(group.invoices[0]["amountDue"]["currency"]["code"])
            detail = (
                f"I’m following up on {invoice_count} invoices that remain overdue. "
                f"The current outstanding balance is <strong>{total:,.2f} {currency}</strong>. "
                "I’ve attached a statement for easy reference."
            )
            rows = []
            for invoice in group.invoices:
                rows.append(
                    f"<li style='margin-bottom:18px'><strong>Invoice {escape(str(invoice['invoiceNumber']))}</strong> "
                    f"- {escape(str(invoice['amountDue']['value']))} {escape(invoice['amountDue']['currency']['code'])}"
                    f"<div style='margin-top:5px'><a href='{escape(invoice.get('viewUrl') or '', quote=True)}'>Preview invoice</a></div></li>"
                )
            portal_url = cls.multi_invoice_portal_url(group.customer_id)
            actions = ("<ul style='padding-left:22px;margin:18px 0'>" + "".join(rows) + "</ul>" +
                       f"<div style='margin:20px 0'>{cls._pay_button(portal_url, 'Review and pay invoices')}</div>")
        banner = (
            f"<div style='background:#fff3cd;padding:10px;margin-bottom:18px'><strong>TEST MODE</strong><br>"
            f"{escape(test_banner)}</div>" if test_banner else ""
        )
        return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#172033;line-height:1.55">
<div style="max-width:640px;margin:auto;padding:24px">{banner}
<p>Hi {first_name},</p>
<p>I hope you are doing well.</p>
<p>{detail}</p>
{actions}
<p>Could you please provide an update on the payment status and let us know when we can expect the outstanding amount to be settled? Understanding the timeline is important for our internal financial planning.</p>
<p>If payment has already been made, please reply with the payment details so we can reconcile our records. Please also let me know if you need any further information or documentation from our side.</p>
<p>Thank you for your prompt attention to this matter.</p>
<p>Best regards,<br><strong>Menteso Accounts Team</strong><br>
<a href="mailto:accounts@menteso.com">accounts@menteso.com</a></p>
</div></body></html>"""

    @staticmethod
    def _pay_button(url: str, label: str) -> str:
        safe_url = escape(url, quote=True)
        return (
            f'<a href="{safe_url}" style="display:inline-block;background:#1d4ed8;color:#fff;'
            f'text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:bold">{escape(label)}</a>'
        )

    @staticmethod
    def multi_invoice_portal_url(customer_id: str) -> str:
        base = os.getenv("INVOICE_REMINDER_PORTAL_URL", "https://os.menteso.com/pay/invoices").rstrip("/")
        secret = os.getenv("INVOICE_REMINDER_PORTAL_SECRET")
        if not secret:
            # Test mode remains non-chargeable until the shared portal secret is installed.
            return f"{base}?unconfigured=1"
        token = CheckoutToken(secret).issue(customer_id)
        return f"{base}?token={token}"

    @staticmethod
    def statement_pdf(group: Group) -> bytes:
        """Create one statement PDF when a customer has multiple invoices."""
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream, pagesize=LETTER)
        _width, height = LETTER
        y = height - 54
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(54, y, "Menteso, Inc. - Overdue Invoice Statement")
        y -= 28
        pdf.setFont("Helvetica", 10)
        pdf.drawString(54, y, f"Customer: {group.name}")
        y -= 16
        pdf.drawString(54, y, f"Generated: {datetime.now(timezone.utc).date().isoformat()}")
        y -= 28
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(54, y, "Invoice")
        pdf.drawString(155, y, "Due date")
        pdf.drawString(260, y, "Amount due")
        pdf.drawString(380, y, "Payment link")
        y -= 14
        total = 0.0
        currency = group.invoices[0]["amountDue"]["currency"]["code"]
        pdf.setFont("Helvetica", 8)
        for invoice in group.invoices:
            if y < 72:
                pdf.showPage()
                y = height - 54
                pdf.setFont("Helvetica", 8)
            amount = float(str(invoice["amountDue"]["value"]).replace(",", ""))
            total += amount
            pdf.drawString(54, y, str(invoice["invoiceNumber"]))
            pdf.drawString(155, y, str(invoice["dueDate"]))
            pdf.drawRightString(350, y, f"{amount:,.2f} {invoice['amountDue']['currency']['code']}")
            pdf.drawString(380, y, str(invoice.get("viewUrl") or "")[:38])
            y -= 16
        y -= 10
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawRightString(350, y, f"Total due: {total:,.2f} {currency}")
        y -= 32
        pdf.setFont("Helvetica", 9)
        pdf.drawString(54, y, "Please reply to accounts@menteso.com with the expected payment date.")
        pdf.save()
        return stream.getvalue()

    def attachment(self, group: Group) -> tuple[bytes, str]:
        if len(group.invoices) == 1:
            invoice = group.invoices[0]
            return self.wave._download_pdf(invoice["pdfUrl"]), f"invoice-{invoice['invoiceNumber']}.pdf"
        return self.statement_pdf(group), f"statement-{group.customer_id}.pdf"

    def previews(self, limit=3):
        groups=self.collect()
        self.sync_dashboard(groups)
        singles=[g for g in groups if len(g.invoices)==1]
        multiples=[g for g in groups if len(g.invoices)>1]
        selected=(singles[:1]+multiples[:1]+singles[1:max(1,limit-1)])[:limit]
        out=[]
        for group in selected:
            subject,body=self.render(group)
            out.append({"customer_id":group.customer_id,"intended_to":group.email,"test_to":TEST_RECIPIENT,"customer":group.name,"invoice_count":len(group.invoices),"subject":subject,"body":body,"invoices":group.invoices})
        return out

    def sync_dashboard(self, groups=None):
        groups = groups if groups is not None else self.collect()
        now = datetime.now(timezone.utc)
        customers = self.state.setdefault("customers", {})
        live_ids = set()
        for group in groups:
            live_ids.add(group.customer_id)
            row = customers.setdefault(group.customer_id, {})
            row.update({
                "customer_id": group.customer_id,
                "customer": group.name,
                "email": group.email,
                "invoice_count": len(group.invoices),
                "invoice_numbers": [str(i["invoiceNumber"]) for i in group.invoices],
                "invoices": [{
                    "id": str(i["id"]), "number": str(i["invoiceNumber"]),
                    "pid": str(i.get("poNumber") or ""), "due_date": str(i["dueDate"]),
                    "amount_due": str(i["amountDue"]["value"]),
                    "currency": str(i["amountDue"]["currency"]["code"]),
                    "preview_url": str(i.get("viewUrl") or ""),
                } for i in group.invoices],
                "total_due": sum(float(str(i["amountDue"]["value"]).replace(",", "")) for i in group.invoices),
                "currency": group.invoices[0]["amountDue"]["currency"]["code"],
                "oldest_due_date": min(i["dueDate"] for i in group.invoices),
                "wave_reminders_finished": True,
                "status": "paused" if row.get("paused") else ("test_ready" if self.state.get("mode") == "test" else "ready"),
                "next_follow_up": None if row.get("paused") else self._next_follow_up(row, now),
            })
        for customer_id, row in customers.items():
            if customer_id not in live_ids:
                row["status"] = "resolved_or_ineligible"
        self.state["last_scan_at"] = now.isoformat()
        self.state["eligible_customers"] = len(groups)
        self.state["eligible_invoices"] = sum(len(g.invoices) for g in groups)
        self.save()
        return self.state

    @staticmethod
    def _next_follow_up(row, now):
        last = row.get("last_live_sent_at")
        if not last:
            return now.isoformat()
        return (datetime.fromisoformat(last.replace("Z", "+00:00")) + timedelta(days=FOLLOW_UP_DAYS)).isoformat()

    def send_tests(self, count=3, recipients=None):
        assert self.state.get("mode")=="test", "Test sender refuses to run outside test mode"
        recipients = recipients or [TEST_RECIPIENT]
        normalized = {str(address).strip().lower() for address in recipients}
        if not normalized or not normalized.issubset(AUTHORIZED_APPROVERS):
            raise ValueError("Test recipients must be authorized Menteso approvers")
        # Domain-wide delegation impersonates the real Accounts mailbox; test
        # mode still hard-locks every recipient to Shweta.
        gmail=GmailClient(reminder_gmail_config(self.cfg))
        sent=[]
        for p in self.previews(count):
            group=Group(p["customer_id"],p["customer"],p["intended_to"],p["invoices"])
            pdf_bytes,pdf_filename=self.attachment(group)
            banner=f"TEST MODE — DO NOT FORWARD\nIntended real recipient: {p['intended_to']}\nCustomer: {p['customer']}\n\n"
            subject=f"[OVERDUE AGENT TEST] {p['subject']}"
            html=self.render_html(group, f"Intended real recipient: {p['intended_to']} | Customer: {p['customer']}")
            sent.append(gmail.send_message(
                sorted(normalized),subject,banner+p["body"],pdf_bytes,pdf_filename,html
            ))
        self.state["last_test_at"]=datetime.now(timezone.utc).isoformat(); self.state["last_test_count"]=len(sent); self.save()
        return sent

    def reconcile_payments(self) -> dict:
        """Idempotently allocate verified Stripe events to Wave, then Zoho."""
        zoho = ZohoClient(self.cfg)
        today = datetime.now(timezone.utc).date().isoformat()
        for event_id, event in self.state.get("payment_events", {}).items():
            if event.get("status") == "reconciled":
                continue
            event.setdefault("allocations", {})
            try:
                for invoice in event.get("invoices", []):
                    allocation = event["allocations"].setdefault(invoice["id"], {})
                    if not allocation.get("wave_payment_id"):
                        allocation["wave_payment_id"] = self.wave.record_stripe_payment(
                            invoice["id"], invoice["amount_due"], today,
                            str(event.get("stripe_payment_intent") or event["stripe_session_id"]),
                        )
                        self.save()
                    if invoice.get("pid") and not allocation.get("zoho_updated"):
                        zoho.mark_invoice_paid(invoice["pid"], today, str(event.get("stripe_payment_intent") or ""))
                        allocation["zoho_updated"] = True
                        self.save()
                event["status"] = "reconciled"
                event["reconciled_at"] = datetime.now(timezone.utc).isoformat()
                row = self.state.get("customers", {}).get(event.get("customer_id"), {})
                row["status"] = "paid_reconciled"
            except Exception as exc:
                event["status"] = "reconciliation_retry"
                event["last_error"] = str(exc)
                event["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
            self.save()
        return self.state.get("payment_events", {})
