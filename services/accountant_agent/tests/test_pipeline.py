"""Pipeline tests with fully mocked clients — run offline, no credentials.

    pytest tests/test_pipeline.py -v
"""
import sys
from types import SimpleNamespace

sys.path.insert(0, ".")
from src.idempotency import InMemoryStore  # noqa: E402
from src.models import EmailMessage, GeneratedInvoice, InvoiceDetails, LineItem  # noqa: E402
from src.pipeline import Pipeline  # noqa: E402
from src.conversation import ConversationDecision  # noqa: E402


class FakeGmail:
    def __init__(self, messages):
        self._messages = messages
        self.sent = []
        self.marked_read = []

    def fetch_unprocessed(self, query="is:unread newer_than:2d"):
        return self._messages

    def send_reply(self, original, pdf_bytes, body_text, pdf_filename="invoice.pdf"):
        self.sent.append((original.message_id, pdf_filename, pdf_bytes))
        return "sent-1"

    def reply_text(self, original, body_text):
        self.sent.append((original.message_id, "text", body_text))
        return "sent-text-1"

    def reply_all(self, original, pdf_bytes, body_text, pdf_filename="invoice.pdf"):
        self.sent.append((original.message_id, pdf_filename, pdf_bytes))
        return "sent-all-1"

    def mark_read(self, message_id):
        self.marked_read.append(message_id)


class FakeZoho:
    def __init__(self, mapping):
        self._mapping = mapping
        self.completed = []

    def find_by_pid(self, pid):
        return self._mapping.get(pid)

    def complete_invoice(self, details, invoice_number, wave_invoice_id,
                         view_url, pdf_bytes, create_missing_contacts=False):
        self.completed.append((details.pid, invoice_number, create_missing_contacts))

    def require_write_access(self):
        return None


class FakeWave:
    def __init__(self):
        self.calls = []
        self.details = []

    def generate(self, details, company):
        self.calls.append((details.pid, company.key))
        self.details.append(details)
        return GeneratedInvoice(
            wave_invoice_id="wave-1", invoice_number="INV-1",
            pdf_bytes=b"%PDF-1.4 fake", status="SAVED",
        )

    def update_invoice(self, invoice_id, details, company):
        self.calls.append((details.pid, company.key, "update", invoice_id))
        self.details.append(details)
        return GeneratedInvoice(
            wave_invoice_id=invoice_id, invoice_number="INV-1",
            pdf_bytes=b"%PDF-1.4 corrected", view_url="https://wave.test/invoice",
            status="SAVED",
        )


def _msg(mid="m1", subject="Invoice", body="Please invoice PID: 500",
         frm="anchal@menteso.com"):
    return EmailMessage(
        message_id=mid, thread_id="t1", rfc822_message_id="<x@mail>",
        from_address=frm, from_name="A", subject=subject, body_text=body,
    )


def _details(pid="500", events="Menteso Services", service_type="Services",
             deal_name="Utility Patent Drawing - sample"):
    d = InvoiceDetails(pid=pid, zoho_record_id="z1", customer_name="Acme",
                       customer_email="acme@x.com", currency="USD",
                       events_or_services=events, service_type=service_type,
                       deal_name=deal_name)
    d.line_items.append(LineItem("Services", 1, 1000.0))
    return d


def _pipeline(gmail, zoho, wave, dry_run=False):
    return Pipeline(config=None, gmail=gmail, zoho=zoho, wave=wave,
                    store=InMemoryStore(), llm=None, dry_run=dry_run)


class CorrectionConversation:
    key = ""

    def analyze_reply(self, message, case):
        return ConversationDecision(
            "correction", updates={"customer_email": "billing@acme.com", "amount": 1250.0},
            crm_update=True,
        )

    def polish(self, text):
        return text


def test_happy_path_generates_and_replies():
    gmail = FakeGmail([_msg()])
    zoho = FakeZoho({"500": _details()})
    wave = FakeWave()
    p = _pipeline(gmail, zoho, wave)
    results = p.run()
    assert results[0].ok is True
    assert results[0].skipped_reason is None
    assert results[0].wave_invoice_id == "wave-1"
    assert wave.calls == [("500", "MENTESO")]
    assert zoho.completed == [("500", "INV-1", False)]
    assert gmail.sent[-1][1] == "invoice-500-INV-1.pdf"


def test_correction_updates_same_invoice_and_resends():
    gmail = FakeGmail([_msg()])
    wave = FakeWave()
    p = _pipeline(gmail, FakeZoho({"500": _details()}), wave)
    p._conversation = CorrectionConversation()
    p.run()
    corrected = p.process_one(_msg(mid="m2", body="Use billing@acme.com and 1250"))
    case = p._cases.get("t1")
    assert corrected.ok and corrected.wave_invoice_id == "wave-1"
    assert case.spec["customer_email"] == "billing@acme.com"
    assert case.spec["amount"] == 1250.0
    assert case.spec["create_missing_contacts"] is True
    assert wave.calls == [
        ("500", "MENTESO"),
        ("500", "MENTESO", "update", "wave-1"),
    ]
    assert gmail.sent[-1][1] == "invoice-500-INV-1-corrected.pdf"


def test_unauthorized_sender_cannot_open_case():
    gmail = FakeGmail([_msg(frm="outsider@example.com")])
    wave = FakeWave()
    result = _pipeline(gmail, FakeZoho({"500": _details()}), wave).run()[0]
    assert result.skipped_reason == "unauthorized_sender"
    assert not wave.calls


def test_self_sent_message_is_ignored_before_claiming_or_replying():
    gmail = FakeGmail([])
    p = Pipeline(
        config=SimpleNamespace(mailbox_address="invoicerequest@menteso.com"),
        gmail=gmail, zoho=FakeZoho({}), wave=FakeWave(),
        store=InMemoryStore(), conversation=CorrectionConversation(),
    )
    result = p.process_one(_msg(frm="invoicerequest@menteso.com"))
    assert result.ok is True
    assert result.skipped_reason == "self_sent_message"
    assert not gmail.sent


def test_no_pid_is_recorded_as_failure():
    gmail = FakeGmail([_msg(body="just saying hi")])
    p = _pipeline(gmail, FakeZoho({}), FakeWave())
    results = p.run()
    assert results[0].ok is False
    assert results[0].skipped_reason == "no_pid_found"
    assert not gmail.sent


def test_unrouted_company_is_skipped():
    gmail = FakeGmail([_msg(body="Please generate invoice PID: 500")])
    p = _pipeline(gmail, FakeZoho({"500": _details(events="Some Random Event")}), FakeWave())
    results = p.run()
    assert results[0].ok is False
    assert results[0].skipped_reason == "unrouted_company"
    assert not gmail.sent


def test_routes_to_company_and_replies():
    gmail = FakeGmail([_msg(body="Please generate invoice PID: 500")])
    wave = FakeWave()
    p = _pipeline(gmail, FakeZoho({"500": _details(events="Menteso Services")}), wave)
    results = p.run()
    assert results[0].ok is True
    assert results[0].company == "MENTESO"
    assert results[0].skipped_reason is None
    assert wave.calls == [("500", "MENTESO")]
    assert gmail.sent


def test_wlf_routes_to_iipla_and_adds_unpaid_bank_charge():
    gmail = FakeGmail([_msg(body="Please generate unpaid invoice PID: 500")])
    wave = FakeWave()
    p = _pipeline(gmail, FakeZoho({"500": _details(events="WLF 2026 Europe", service_type="Delegate")}), wave)
    results = p.run()
    assert results[0].ok is True
    assert results[0].company == "IIPLA"
    assert results[0].skipped_reason is None
    assert wave.calls == [("500", "IIPLA")]
    assert wave.details[0].bank_charge_amount == 25.0
    assert wave.details[0].line_items[0].product_name == "Delegate Registration"
    assert wave.details[0].line_items[-1].product_name == "Bank charges"


def test_paid_request_is_held_until_payment_is_verified():
    gmail = FakeGmail([_msg(body="Please generate paid invoice PID: 500")])
    wave = FakeWave()
    p = _pipeline(gmail, FakeZoho({"500": _details(events="WLF 2026 Europe", service_type="Delegate")}), wave)
    results = p.run()
    assert results[0].skipped_reason == "payment_verification_required"
    assert not wave.calls
    assert gmail.sent


def test_human_reply_question_does_not_resend_invoice():
    body = (
        "Wait! What is this for? Why ANF invoice?\n\n"
        "On Wed wrote:\n> invoice ANF115 for project PID1615484"
    )
    gmail = FakeGmail([_msg(subject="Re: Generate the Invoice", body=body)])
    wave = FakeWave()
    p = _pipeline(gmail, FakeZoho({"PID1615484": _details("PID1615484")}), wave)
    results = p.run()
    assert results[0].skipped_reason == "no_explicit_invoice_action"
    assert not wave.calls
    assert not gmail.sent


def test_pid_not_in_zoho_is_handled():
    gmail = FakeGmail([_msg(body="Invoice PID: 999")])
    p = _pipeline(gmail, FakeZoho({"500": _details()}), FakeWave())
    results = p.run()
    assert results[0].ok is False
    assert results[0].skipped_reason == "pid_not_in_zoho"
    assert gmail.sent and gmail.sent[0][1] == "text"


def test_dry_run_does_not_send():
    gmail = FakeGmail([_msg()])
    p = _pipeline(gmail, FakeZoho({"500": _details()}), FakeWave(), dry_run=True)
    results = p.run()
    assert results[0].ok is True
    assert results[0].skipped_reason == "dry_run"
    assert not gmail.sent


def test_claim_is_exclusive_then_blocks():
    from src.models import ProcessResult
    s = InMemoryStore()
    assert s.claim("m1") is True       # first worker wins the claim
    assert s.claim("m1") is False      # second concurrent worker is blocked
    s.record(ProcessResult("m1", ok=True))
    assert s.claim("m1") is False      # completed -> never reprocessed


def test_failed_message_is_reclaimable():
    from src.models import ProcessResult
    s = InMemoryStore()
    assert s.claim("m2") is True
    s.record(ProcessResult("m2", ok=False, error="transient boom"))
    assert s.claim("m2") is True       # transient failure -> retryable


def test_terminal_skip_not_reclaimable():
    from src.models import ProcessResult
    s = InMemoryStore()
    s.claim("m3")
    s.record(ProcessResult("m3", ok=False, skipped_reason="pid_not_in_zoho"))
    assert s.claim("m3") is False      # decided skip -> not retried


def test_idempotency_skips_second_time():
    gmail = FakeGmail([_msg()])
    p = _pipeline(gmail, FakeZoho({"500": _details()}), FakeWave())
    p.run()
    # process the same message again through the same store
    second = p.process_one(_msg())
    assert second.skipped_reason == "already_processed"
