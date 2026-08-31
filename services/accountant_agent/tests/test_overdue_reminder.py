from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json

from pypdf import PdfReader

from overdue_reminder_agent.agent import Group, OverdueReminderAgent, reminder_gmail_config
from overdue_reminder_agent.checkout import CheckoutToken, StripeCheckout, cents, verify_stripe_event

def inv(number="1", status="OVERDUE", sent=True):
    return {"invoiceNumber":number,"status":status,"dueDate":"2025-01-01","viewUrl":"https://pay.test/1","amountDue":{"value":"100.00","currency":{"code":"USD"}},"invoiceReminders":[{"sent":sent}]}

def test_only_after_wave_reminders_finished():
    assert OverdueReminderAgent.wave_finished(inv())
    assert not OverdueReminderAgent.wave_finished(inv(sent=False))
    x=inv(); x["invoiceReminders"]=[]; assert not OverdueReminderAgent.wave_finished(x)

def test_multiple_invoice_message_requests_payment_date():
    g=Group("c","Acme","billing@acme.test",[inv("1"),inv("2")])
    subject,body=OverdueReminderAgent.render(g)
    assert "2 outstanding invoices" in subject
    assert "when we can expect the outstanding amount" in body

def test_multiple_invoice_statement_contains_every_invoice():
    g=Group("c","Acme","billing@acme.test",[inv("INV-1"),inv("INV-2")])
    content=OverdueReminderAgent.statement_pdf(g)
    text="\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(content)).pages)
    assert "Menteso, Inc." in text
    assert "INV-1" in text and "INV-2" in text
    assert "Total due: 200.00 USD" in text

def test_personal_html_uses_first_name_and_short_payment_buttons():
    g=Group("c","Jarrel Byer (Individual)","billing@acme.test",[inv("INV-1")])
    html=OverdueReminderAgent.render_html(g)
    assert "Hi Jarrel," in html
    assert ">Pay now</a>" in html
    assert ">https://pay.test/1<" not in html

def test_multiple_invoice_html_has_one_portal_button(monkeypatch):
    monkeypatch.setenv("INVOICE_REMINDER_PORTAL_SECRET", "x" * 32)
    g=Group("c","Individual-Egypt Lawson","billing@acme.test",[inv("1"),inv("2")])
    html=OverdueReminderAgent.render_html(g)
    assert "Hi Egypt," in html
    assert html.count(">Review and pay invoices</a>") == 1
    assert html.count("Preview invoice</a>") == 2

def test_checkout_token_rejects_tampering_and_expiry(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1000)
    signer=CheckoutToken("x"*32); token=signer.issue("customer-1",60)
    assert signer.verify(token,1059)["customer_id"]=="customer-1"
    try: signer.verify(token+"x",1059)
    except ValueError: pass
    else: raise AssertionError("tampered token accepted")
    try: signer.verify(token,1061)
    except ValueError: pass
    else: raise AssertionError("expired token accepted")

def test_stripe_checkout_contains_selected_invoices(monkeypatch):
    captured={}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"id":"cs_test","url":"https://checkout.stripe.test"}
    def post(url,**kwargs): captured.update(kwargs); return Response()
    monkeypatch.setattr("requests.post",post)
    rows=[dict(inv("1"),id="wave-1"),dict(inv("2"),id="wave-2")]
    result=StripeCheckout("sk_test","https://ok","https://cancel").create("a@test","c",rows)
    assert result["id"]=="cs_test"
    assert ("metadata[wave_invoice_ids]","wave-1,wave-2") in captured["data"]
    assert cents("100.00")==10000

def test_stripe_webhook_signature():
    payload=b'{"id":"evt_1"}'; stamp=1000; secret="whsec_test"
    digest=__import__("hmac").new(secret.encode(),str(stamp).encode()+b"."+payload,__import__("hashlib").sha256).hexdigest()
    assert verify_stripe_event(payload,f"t={stamp},v1={digest}",secret,now=stamp)["id"]=="evt_1"

def test_weekly_schedule_and_manual_pause(tmp_path):
    agent=object.__new__(OverdueReminderAgent)
    agent.state_path=tmp_path/"state.json"
    agent.state={"mode":"test","paused":False,"customers":{}}
    now=datetime.now(timezone.utc)
    assert agent.due_for_follow_up("c",now)
    agent.state["customers"]["c"]={"last_live_sent_at":now.isoformat()}
    assert not agent.due_for_follow_up("c",now+timedelta(days=6))
    assert agent.due_for_follow_up("c",now+timedelta(days=7))
    agent.set_customer_paused("c",True)
    assert not agent.due_for_follow_up("c",now+timedelta(days=30))

def test_group_test_recipients_must_be_authorized():
    agent=object.__new__(OverdueReminderAgent)
    agent.state={"mode":"test"}
    try:
        agent.send_tests(1,["client@example.com"])
    except ValueError as exc:
        assert "authorized" in str(exc)
    else:
        raise AssertionError("External test recipient was accepted")

def test_reminder_gmail_config_is_isolated_from_invoice_request(monkeypatch):
    @dataclass(frozen=True)
    class FakeConfig:
        mailbox_address:str
        google_client_id:str
        google_client_secret:str
        google_refresh_token:str
        google_service_account_file:str
        google_service_account_json:str
    base=FakeConfig(
        mailbox_address="invoicerequest@menteso.com",
        google_client_id="old",google_client_secret="old",google_refresh_token="old",
        google_service_account_file="scripts/service_account.json",
        google_service_account_json="old-service-account",
    )
    payload={
        "MAILBOX_ADDRESS":"accounts@menteso.com",
        "GOOGLE_CLIENT_ID":"accounts-client",
        "GOOGLE_CLIENT_SECRET":"accounts-secret",
        "GOOGLE_REFRESH_TOKEN":"accounts-refresh",
        "GOOGLE_SCOPES":["https://www.googleapis.com/auth/gmail.modify"],
    }
    class Secrets:
        def get_secret_value(self,SecretId):
            assert SecretId=="invoice-reminder-agent/gmail"
            return {"SecretString":json.dumps(payload)}
    monkeypatch.setattr("boto3.client",lambda service,region_name: Secrets())
    cfg=reminder_gmail_config(base)
    assert cfg.mailbox_address=="accounts@menteso.com"
    assert cfg.google_refresh_token=="accounts-refresh"
    assert cfg.google_service_account_file==""
    assert cfg.google_service_account_json==""
