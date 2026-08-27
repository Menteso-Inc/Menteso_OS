from src.cases import AccountingCase
from src.conversation import OpenAIConversation
from src.models import EmailMessage


def _case():
    return AccountingCase(
        thread_id="t1", pid="PID500", requester_email="anchal@menteso.com",
        requester_name="Anchal", state="completed", company_key="MENTESO",
        zoho_record_id="z1", spec={"amount": 1000.0}, wave_invoice_id="w1",
        invoice_number="INV-1",
    )


def _message(body):
    return EmailMessage(
        message_id="m2", thread_id="t1", rfc822_message_id="<m2@test>",
        from_address="anchal@menteso.com", from_name="Anchal",
        subject="Re: Invoice", body_text=body,
    )


def test_correction_fallback_extracts_email_and_amount_without_openai():
    decision = OpenAIConversation(None).analyze_reply(
        _message("Change the email to billing@client.com and invoice amount to USD 1,250"),
        _case(),
    )
    assert decision.intent == "correction"
    assert decision.updates["customer_email"] == "billing@client.com"
    assert decision.updates["amount"] == 1250.0


def test_question_is_not_treated_as_correction_or_approval():
    decision = OpenAIConversation(None).analyze_reply(
        _message("Why is this invoice under Menteso Inc.?"), _case()
    )
    assert decision.intent == "question"
    assert not decision.updates


def test_bank_charge_removal_is_a_direct_correction():
    decision = OpenAIConversation(None).analyze_reply(
        _message("Please remove bank charges"), _case()
    )
    assert decision.intent == "correction"
    assert decision.updates["bank_charge_amount"] == 0.0


def test_required_charges_adds_standard_bank_charge_without_openai():
    decision = OpenAIConversation(None).analyze_reply(
        _message("add the required charges there"), _case()
    )
    assert decision.intent == "correction"
    assert decision.updates["bank_charge_amount"] == 25.0


def test_openai_failure_returns_safe_no_action(monkeypatch):
    conversation = OpenAIConversation(None)
    conversation.key = "test-key"

    def unavailable(_prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(conversation, "_structured", unavailable)
    decision = conversation.analyze_reply(
        _message("Please handle this as discussed"), _case()
    )
    assert decision.intent == "other"
    assert decision.updates == {}
    assert "no accounting change" in decision.explanation
