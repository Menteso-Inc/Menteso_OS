from datetime import datetime, timedelta, timezone
from io import BytesIO

from pypdf import PdfReader

from overdue_reminder_agent.agent import Group, OverdueReminderAgent

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

def test_multiple_invoice_html_has_one_pay_button_per_invoice():
    g=Group("c","Individual-Egypt Lawson","billing@acme.test",[inv("1"),inv("2")])
    html=OverdueReminderAgent.render_html(g)
    assert "Hi Egypt," in html
    assert html.count(">Pay now</a>") == 2

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
