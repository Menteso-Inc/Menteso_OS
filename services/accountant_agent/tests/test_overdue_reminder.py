from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json

from pypdf import PdfReader

from overdue_reminder_agent.agent import Group, OverdueReminderAgent, reminder_gmail_config
from overdue_reminder_agent.checkout import CheckoutToken, StripeCheckout, cents, verify_stripe_event
from overdue_reminder_agent.ses_sender import ReminderSesSender

def test_ses_sender_uses_accounts_from_reply_to_and_configuration_set():
    captured={}
    class Ses:
        def send_email(self,**kwargs): captured.update(kwargs); return {"MessageId":"ses-1"}
    sender=ReminderSesSender(client=Ses())
    assert sender.send_message(["sajan@menteso.com"],"Test","Body") == "ses-1"
    raw=captured["Content"]["Raw"]["Data"].decode("utf-8", "replace")
    assert "accounts@menteso.com" in raw
    assert "Reply-To: accounts@menteso.com" in raw
    assert captured["ConfigurationSetName"] == "invoice-reminder-agent"

def test_ses_sender_preserves_cc_recipients():
    captured={}
    class Ses:
        def send_email(self,**kwargs): captured.update(kwargs); return {"MessageId":"ses-cc"}
    sender=ReminderSesSender(client=Ses())
    sender.send_message("azam@menteso.com","Test","Body",cc=["sajan@menteso.com","shweta@menteso.com"])
    raw=captured["Content"]["Raw"]["Data"].decode("utf-8", "replace")
    assert "Cc: sajan@menteso.com, shweta@menteso.com" in raw
    assert captured["Destination"]["CcAddresses"]==["sajan@menteso.com","shweta@menteso.com"]

def inv(number="1", status="OVERDUE", sent=True):
    return {"invoiceNumber":number,"status":status,"dueDate":"2025-01-01","viewUrl":"https://pay.test/1","amountDue":{"value":"100.00","currency":{"code":"USD"}},"invoiceReminders":[{"sent":sent}]}

def test_only_after_wave_reminders_finished():
    assert OverdueReminderAgent.wave_finished(inv())
    assert not OverdueReminderAgent.wave_finished(inv(sent=False))
    x=inv(); x["invoiceReminders"]=[]; assert not OverdueReminderAgent.wave_finished(x)

def test_reminder_ownership_hands_off_between_agent_and_wave():
    no_wave_flow=inv(); no_wave_flow["invoiceReminders"]=[]
    assert OverdueReminderAgent.reminder_owner(no_wave_flow)=="agent"
    assert OverdueReminderAgent.reminder_owner(inv(sent=False))=="wave"
    assert OverdueReminderAgent.reminder_owner(inv(sent=True))=="agent"

def test_collect_builds_disjoint_live_dashboard_summary():
    no_flow=dict(inv("agent-1"), id="a", customer={"id":"c1","name":"A","email":"a@test"})
    no_flow["invoiceReminders"]=[]
    wave_pending=dict(inv("wave-1",sent=False), id="w", customer={"id":"c2","name":"W","email":"w@test"})
    missing=dict(inv("missing-1"), id="m", customer={"id":"c3","name":"M","email":""})
    paid=dict(inv("paid-1",status="PAID"), id="p", customer={"id":"c4","name":"P","email":"p@test"})
    agent=object.__new__(OverdueReminderAgent)
    class Wave:
        def _gql(self,*_args,**_kwargs):
            return {"business":{"invoices":{"pageInfo":{"totalPages":1},"edges":[{"node":x} for x in [no_flow,wave_pending,missing,paid]]}}}
    agent.wave=Wave()
    groups=agent.collect()
    assert [g.customer_id for g in groups]==["c1"]
    assert agent._scan_summary=={
        "overdue_total":3,
        "wave_reminder_invoices":1,
        "agent_reminder_invoices":1,
        "missing_email_invoices":1,
        "agent_collection_totals":{"USD":100.0},
    }

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

def test_live_sender_requires_two_independent_safety_switches(monkeypatch, tmp_path):
    agent=object.__new__(OverdueReminderAgent); agent.state_path=tmp_path/"state.json"
    agent.state={"mode":"test","paused":False,"customers":{}}
    monkeypatch.setenv("INVOICE_REMINDER_SINGLE_LIVE_ENABLED","true")
    try: agent.send_live_singles()
    except RuntimeError as exc: assert "single_live" in str(exc)
    else: raise AssertionError("test mode sent live mail")

def test_live_sender_hard_blocks_multiple_invoice_groups(monkeypatch, tmp_path):
    single=Group("one","One Client","one@example.com",[inv("1")])
    multiple=Group("many","Many Client","many@example.com",[inv("2"),inv("3")])
    agent=object.__new__(OverdueReminderAgent); agent.state_path=tmp_path/"state.json"
    agent.state={"mode":"single_live","paused":False,"customers":{}}
    agent.collect=lambda:[single,multiple]; agent.sync_dashboard=lambda groups:None
    agent.attachment=lambda group:(b"pdf","invoice.pdf")
    class Ses:
        def __init__(self,*_): pass
        def send_message(self,to,*_args): assert to==["one@example.com"]; return "message-1"
    monkeypatch.setenv("INVOICE_REMINDER_SINGLE_LIVE_ENABLED","true")
    monkeypatch.setattr("overdue_reminder_agent.agent.ReminderSesSender",Ses)
    agent.cfg=object()
    sent=agent.send_live_singles()
    assert [row["customer_id"] for row in sent]==["one"]
    assert agent.state["customers"]["one"]["first_live_sent_at"]
    assert agent.state["customers"]["one"]["last_live_sent_at"]

def test_multi_live_sender_requires_switch_and_only_sends_multiple(monkeypatch, tmp_path):
    single=Group("one","One Client","one@example.com",[inv("1")])
    multiple=Group("many","Many Client","many@example.com",[inv("2"),inv("3")])
    agent=object.__new__(OverdueReminderAgent); agent.state_path=tmp_path/"state.json"
    agent.state={"mode":"single_live","paused":False,"customers":{}}
    agent.collect=lambda:[single,multiple]; agent.sync_dashboard=lambda groups:None
    agent.attachment=lambda group:(b"pdf","statement.pdf")
    try: agent.send_live_multiples()
    except RuntimeError as exc: assert "MULTI_LIVE" in str(exc)
    else: raise AssertionError("multi-live sender ran without its switch")
    class Ses:
        def __init__(self,*_): pass
        def send_message(self,to,*_args,**_kwargs): assert to==["many@example.com"]; return "multi-1"
    monkeypatch.setenv("INVOICE_REMINDER_MULTI_LIVE_ENABLED","true")
    monkeypatch.setenv("INVOICE_REMINDER_PORTAL_SECRET","x"*32)
    monkeypatch.setattr("overdue_reminder_agent.agent.ReminderSesSender",Ses)
    sent=agent.send_live_multiples()
    assert [row["customer_id"] for row in sent]==["many"]
    assert agent.state["customers"]["many"]["next_follow_up"]

def test_multi_payment_test_is_limited_to_internal_one_dollar_customer(monkeypatch, tmp_path):
    invoices=[dict(inv("T-1"),id="wave-1"),dict(inv("T-2"),id="wave-2")]
    for invoice in invoices: invoice["amountDue"]["value"]="0.50"
    group=Group("test-customer","Menteso Stripe Payment Test","sajan@menteso.com",invoices)
    agent=object.__new__(OverdueReminderAgent); agent.state_path=tmp_path/"state.json"
    agent.state={"mode":"single_live","paused":False,"customers":{}}
    agent.collect=lambda:[group]; agent.sync_dashboard=lambda groups:None
    agent.attachment=lambda group:(b"pdf","statement.pdf")
    class Ses:
        def send_message(self,to,*_args,**_kwargs): assert to==["sajan@menteso.com"]; return "message-test"
    monkeypatch.setattr("overdue_reminder_agent.agent.ReminderSesSender",Ses)
    monkeypatch.setenv("INVOICE_REMINDER_PORTAL_SECRET","x"*32)
    result=agent.send_multi_payment_test("test-customer","sajan@menteso.com")
    assert result["total"]==1.0
    assert agent.state["sent_emails"][0]["kind"]=="multi_payment_test"

def test_multi_payment_test_rejects_external_or_expensive_group(monkeypatch, tmp_path):
    invoices=[dict(inv("T-1"),id="wave-1"),dict(inv("T-2"),id="wave-2")]
    group=Group("test-customer","Menteso Stripe Payment Test","sajan@menteso.com",invoices)
    agent=object.__new__(OverdueReminderAgent); agent.state_path=tmp_path/"state.json"
    agent.state={"mode":"single_live","paused":False,"customers":{}}
    agent.collect=lambda:[group]; agent.sync_dashboard=lambda groups:None
    try: agent.send_multi_payment_test("test-customer","client@example.com")
    except ValueError as exc: assert "authorized" in str(exc)
    else: raise AssertionError("External payment-test recipient was accepted")
    try: agent.send_multi_payment_test("test-customer","sajan@menteso.com")
    except ValueError as exc: assert "$1.00" in str(exc)
    else: raise AssertionError("Payment test over $1 was accepted")

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
