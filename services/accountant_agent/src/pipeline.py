"""Conversational AccountantAgent orchestration for Gmail, Zoho and Wave."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from . import companies
from .billing_policy import default_bank_charge, select_product
from .cases import AccountingCase, CaseStore, build_case_store
from .config import Config
from .conversation import ConversationDecision, OpenAIConversation
from .email_client import GmailClient
from .idempotency import ProcessedStore
from .models import Attendee, EmailMessage, InvoiceDetails, LineItem, ProcessResult
from .parser import parse_request
from .wave_client import WaveClient
from .zoho_client import ZohoClient
from .wlf_pdf import brand_wlf_wave_pdf

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self, config: Config, gmail: GmailClient, zoho: ZohoClient,
        wave: WaveClient, store: ProcessedStore, llm: Optional[Callable] = None,
        dry_run: bool = False, progress: Optional[Callable] = None,
        cases: Optional[CaseStore] = None,
        conversation: Optional[OpenAIConversation] = None,
    ):
        self._cfg = config
        self._gmail = gmail
        self._zoho = zoho
        self._wave = wave
        self._store = store
        self._llm = llm
        self._dry_run = dry_run
        self._progress = progress or (lambda *_args, **_kwargs: None)
        self._cases = cases or build_case_store(in_memory=True)
        self._conversation = conversation or OpenAIConversation(config)

    @staticmethod
    def _employee_pdf(details, invoice):
        if "WLF" in (details.events_or_services or "").upper() and invoice.invoice_data:
            return brand_wlf_wave_pdf(
                invoice.pdf_bytes,
                "/home/menteso_os/agents/accountant_agent/assets/wlf-logo.jpeg",
            )
        return invoice.pdf_bytes

    def run(self, query: str = "in:inbox is:unread newer_than:2d") -> list[ProcessResult]:
        self._progress("mail_check", "running", "Checking the accounting mailbox")
        messages = self._gmail.fetch_unprocessed(query)
        self._progress(
            "mail_found" if messages else "sleeping",
            "running" if messages else "idle",
            f"Found {len(messages)} new email(s)" if messages else "No new mail; waiting for Gmail push",
        )
        return [self.process_one(message) for message in messages]

    def process_one(self, msg: EmailMessage) -> ProcessResult:
        mailbox = getattr(self._cfg, "mailbox_address", "")
        if mailbox and msg.from_address.strip().lower() == mailbox.strip().lower():
            return ProcessResult(msg.message_id, ok=True, skipped_reason="self_sent_message")
        if not self._store.claim(msg.message_id):
            return ProcessResult(msg.message_id, ok=True, skipped_reason="already_processed")
        case = self._cases.get(msg.thread_id)
        try:
            if not msg.from_address.lower().endswith("@menteso.com"):
                return self._finish(msg, ProcessResult(
                    msg.message_id, ok=False, skipped_reason="unauthorized_sender",
                    error="Only authorized Menteso employees can instruct AccountantAgent",
                ))
            if case:
                if case.state == "cancelled":
                    return self._handle_closed_case_reply(msg, case)
                return self._handle_case_reply(msg, case)
            return self._start_case(msg)
        except Exception as exc:
            logger.exception("Failed to process accounting message %s", msg.message_id)
            if case:
                case.state = "error"
                case.question = str(exc)
                self._cases.save(case)
            if not self._dry_run:
                try:
                    self._gmail.reply_text(msg, self._conversation.polish(
                        f"Hello {msg.from_name},\n\nI could not complete the accounting action for "
                        f"{case.pid if case else 'this request'}. Nothing was emailed to the external "
                        "client. The request has been flagged for administrator attention. You can reply "
                        "in this thread after the configuration issue is corrected."
                    ))
                except Exception:
                    logger.exception("Could not send accounting failure notice")
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=False, pid=case.pid if case else None,
                error=str(exc), case_state="error",
            ))

    def _handle_closed_case_reply(self, msg: EmailMessage,
                                  case: AccountingCase) -> ProcessResult:
        """Never reinterpret a reply to a closed thread as a new invoice request."""
        if case.state == "completed":
            text = (
                f"Hello {msg.from_name},\n\nInvoice {case.invoice_number or 'for ' + case.pid} "
                "has already been created. I will not silently modify or replace a finalized "
                "invoice. Please start a new email with the PID and correction required so it "
                "can be reviewed as a separate accounting case."
            )
            reason = "completed_case_requires_new_thread"
        else:
            text = (
                f"Hello {msg.from_name},\n\nThe accounting case for {case.pid} is cancelled. "
                "Please start a new email if you want to open a new request."
            )
            reason = "cancelled_case_requires_new_thread"
        if not self._dry_run:
            self._gmail.reply_text(msg, self._conversation.polish(text))
        return self._finish(msg, ProcessResult(
            msg.message_id, ok=True, pid=case.pid, company=case.company_key,
            skipped_reason=reason, case_state=case.state,
        ))

    def _start_case(self, msg: EmailMessage) -> ProcessResult:
        self._progress("parsing", "running", "Reading the employee request")
        parsed = parse_request(msg.subject, msg.body_text, llm=self._llm)
        if not parsed.is_actionable:
            reason = "no_explicit_invoice_action" if parsed.pid else "no_pid_found"
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=False, pid=parsed.pid, skipped_reason=reason,
                error="No explicit invoice request was found in the newest message",
            ))

        self._progress("zoho_lookup", "running", f"Checking Zoho for {parsed.pid}")
        details = self._zoho.find_by_pid(parsed.pid)
        if details is None:
            body = self._conversation.polish(
                f"Hello {msg.from_name},\n\nI could not find {parsed.pid} in Zoho CRM. "
                "Please check the PID and reply with the correct one. I have not created anything in Wave."
            )
            if not self._dry_run:
                self._gmail.reply_text(msg, body)
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=False, pid=parsed.pid,
                skipped_reason="pid_not_in_zoho", error="PID not found in Zoho",
            ))

        company = companies.route(details.events_or_services)
        if company is None:
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=False, pid=parsed.pid,
                zoho_record_id=details.zoho_record_id,
                skipped_reason="unrouted_company",
                error=f"No approved billing route for {details.events_or_services!r}",
            ))

        spec = self._details_to_spec(details, company.key, parsed.invoice_type,
                                     parsed.attendees, parsed.discount_amount)
        case = AccountingCase(
            thread_id=msg.thread_id, pid=parsed.pid,
            requester_email=msg.from_address, requester_name=msg.from_name,
            state="creating_invoice", company_key=company.key,
            zoho_record_id=details.zoho_record_id, spec=spec,
        )
        self._cases.save(case)
        if parsed.invoice_type == "paid":
            case.state = "payment_verification"
            case.question = "Payment must be verified in Wave before issuing a paid invoice."
            self._cases.save(case)
            if not self._dry_run:
                self._gmail.reply_text(msg, self._conversation.polish(
                    f"Hello {msg.from_name},\n\nI found {case.pid}, but payment must be verified "
                    "in Wave before I can issue it as paid. I have not created or emailed an invoice."
                ))
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid, company=case.company_key,
                skipped_reason="payment_verification_required", case_state=case.state,
            ))
        return self._execute_approved(msg, case, ConversationDecision("approve"))

    def _handle_case_reply(self, msg: EmailMessage, case: AccountingCase) -> ProcessResult:
        self._progress("reading_reply", "running", f"Reading reply for {case.pid}")
        decision = self._conversation.analyze_reply(msg, case)
        if decision.intent == "cancel":
            if case.wave_invoice_id:
                if not self._dry_run:
                    self._gmail.reply_text(msg, self._conversation.polish(
                        f"Hello {msg.from_name},\n\nInvoice {case.invoice_number} already exists in Wave, "
                        "so I did not delete or cancel it automatically. Please specify the correction "
                        "needed, or ask an administrator to void it."
                    ))
                return self._finish(msg, ProcessResult(
                    msg.message_id, ok=True, pid=case.pid,
                    skipped_reason="existing_invoice_cancel_requires_review", case_state=case.state,
                ))
            case.state = "cancelled"
            case.question = ""
            self._cases.save(case)
            if not self._dry_run:
                self._gmail.reply_text(msg, self._conversation.polish(
                    f"Hello {msg.from_name},\n\nThe accounting request for {case.pid} has been cancelled. "
                    "No new invoice was created."
                ))
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid,
                skipped_reason="cancelled", case_state=case.state,
            ))

        if decision.intent in {"correction", "answer"} and decision.updates:
            self._apply_updates(case.spec, decision.updates)
            if decision.crm_update is not None:
                case.spec["create_missing_contacts"] = decision.crm_update
            if decision.send_to_client is not None:
                case.spec["send_to_client"] = decision.send_to_client
            case.state = "correcting_invoice" if case.wave_invoice_id else "creating_invoice"
            case.question = ""
            self._cases.save(case)
            if case.wave_invoice_id:
                return self._execute_correction(msg, case, decision)
            return self._execute_approved(msg, case, decision)

        if decision.intent != "approve":
            action = (
                f"I did not change the existing invoice {case.invoice_number} for {case.pid}."
                if case.wave_invoice_id else
                f"I have not generated the invoice for {case.pid}."
            )
            text = (
                f"Hello {msg.from_name},\n\n{action} "
                "Please reply with the exact correction you want. If you are asking me to email an "
                "external client, change billing business, cancel an existing invoice, or mark it paid, "
                "I will ask for confirmation before taking that higher-risk action.\n\n"
                + self._summary(case)
            )
            if not self._dry_run:
                self._gmail.reply_text(msg, self._conversation.polish(text))
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid,
                skipped_reason="waiting_clarification", case_state=case.state,
            ))

        if case.wave_invoice_id:
            if not self._dry_run:
                self._gmail.reply_text(msg, self._conversation.polish(
                    f"Hello {msg.from_name},\n\nInvoice {case.invoice_number} was already created and "
                    "sent to you for review. Reply with any correction and I will update that same invoice."
                ))
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid,
                skipped_reason="already_generated", case_state=case.state,
            ))

        if case.spec.get("invoice_type") == "paid":
            case.state = "payment_verification"
            case.question = (
                f"Payment must be verified in Wave before a paid invoice for {case.pid} can be issued. "
                "No invoice has been sent."
            )
            self._cases.save(case)
            if not self._dry_run:
                self._gmail.reply_text(msg, self._conversation.polish(case.question))
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid,
                skipped_reason="payment_verification_required", case_state=case.state,
            ))

        return self._execute_approved(msg, case, decision)

    def _execute_correction(self, msg: EmailMessage, case: AccountingCase,
                            decision: ConversationDecision) -> ProcessResult:
        self._progress("correcting_invoice", "running", f"Updating Wave invoice {case.invoice_number}")
        details = self._zoho.find_by_pid(case.pid)
        if details is None:
            raise RuntimeError(f"Zoho Deal for {case.pid} disappeared before correction")
        company = next((c for c in companies.ALL_COMPANIES if c.key == case.company_key), None)
        if company is None:
            raise RuntimeError(f"Billing company {case.company_key} is no longer allowed")
        # Upgrade cases created before business-specific products were enforced.
        if not case.spec.get("product_name"):
            case.spec["product_name"] = select_product(
                company.key, details.service_type, details.events_or_services, details.deal_name
            )
        if not case.spec.get("description") or str(case.spec.get("description")).startswith("Services -"):
            case.spec["description"] = details.events_or_services or details.deal_name
        self._cases.save(case)
        self._spec_to_details(case.spec, details)
        if self._dry_run:
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid,
                skipped_reason="dry_run", case_state="correcting_invoice",
            ))
        self._zoho.require_write_access()
        invoice = self._wave.update_invoice(case.wave_invoice_id, details, company)
        employee_pdf = self._employee_pdf(details, invoice)
        self._progress("updating_crm", "running", "Saving the corrected invoice in Zoho")
        self._zoho.complete_invoice(
            details, invoice.invoice_number, invoice.wave_invoice_id,
            invoice.view_url, invoice.pdf_bytes,
            create_missing_contacts=bool(
                decision.crm_update or case.spec.get("create_missing_contacts")
            ),
        )
        body = self._conversation.polish(
            f"Hello {msg.from_name},\n\nI updated invoice {invoice.invoice_number} for {case.pid} "
            "using your correction. The corrected PDF is attached for review, and the same Wave "
            "invoice and Zoho records were updated. Reply in this thread if anything else needs changing."
        )
        self._gmail.send_reply(
            msg, employee_pdf, body,
            pdf_filename=f"invoice-{case.pid}-{invoice.invoice_number}-corrected.pdf",
        )
        case.state = "completed"
        case.invoice_number = invoice.invoice_number
        self._cases.save(case)
        self._progress("complete", "success", f"Corrected invoice {invoice.invoice_number} sent for review")
        return self._finish(msg, ProcessResult(
            msg.message_id, ok=True, pid=case.pid, company=company.key,
            zoho_record_id=case.zoho_record_id,
            wave_invoice_id=invoice.wave_invoice_id, case_state=case.state,
        ), mark_read=False)

    def _execute_approved(self, msg: EmailMessage, case: AccountingCase,
                          decision: ConversationDecision) -> ProcessResult:
        self._progress("zoho_recheck", "running", f"Rechecking Zoho for {case.pid}")
        details = self._zoho.find_by_pid(case.pid)
        if details is None:
            raise RuntimeError(f"Zoho Deal for {case.pid} disappeared before approval")
        self._spec_to_details(case.spec, details)
        company = next((c for c in companies.ALL_COMPANIES if c.key == case.company_key), None)
        if company is None:
            raise RuntimeError(f"Billing company {case.company_key} is no longer allowed")

        if self._dry_run:
            case.state = "dry_run_approved"
            self._cases.save(case)
            return self._finish(msg, ProcessResult(
                msg.message_id, ok=True, pid=case.pid, company=company.key,
                skipped_reason="dry_run", case_state=case.state,
            ))

        self._progress("crm_permission_check", "running", "Verifying Zoho write authorization")
        self._zoho.require_write_access()
        self._progress("creating_invoice", "running", f"Creating Wave draft for {case.pid}")
        invoice = self._wave.generate(details, company)
        employee_pdf = self._employee_pdf(details, invoice)
        case.wave_invoice_id = invoice.wave_invoice_id
        case.invoice_number = invoice.invoice_number
        case.state = "updating_crm"
        self._cases.save(case)

        self._progress("updating_crm", "running", "Attaching invoice and updating Zoho")
        self._zoho.complete_invoice(
            details, invoice.invoice_number, invoice.wave_invoice_id,
            invoice.view_url, invoice.pdf_bytes,
            create_missing_contacts=bool(
                decision.crm_update or case.spec.get("create_missing_contacts")
            ),
        )

        body = self._conversation.polish(
            f"Hello {msg.from_name},\n\nInvoice {invoice.invoice_number} for {case.pid} is complete. "
            "The PDF is attached, and the Zoho Deal and linked Contact have been updated.\n\n"
            f"Billing business: {company.name}\nTotal: {details.net_total:.2f} {details.currency}\n\n"
            "If a correction is required, reply in this thread and describe the change."
        )
        self._progress("sending_email", "running", "Sending the completed invoice to the requester")
        self._gmail.send_reply(
            msg, employee_pdf, body,
            pdf_filename=f"invoice-{case.pid}-{invoice.invoice_number}.pdf",
        )
        self._gmail.mark_read(msg.message_id)
        case.state = "completed"
        case.question = ""
        self._cases.save(case)
        self._progress("complete", "success", f"Invoice {invoice.invoice_number} completed")
        return self._finish(msg, ProcessResult(
            msg.message_id, ok=True, pid=case.pid, company=company.key,
            zoho_record_id=case.zoho_record_id,
            wave_invoice_id=invoice.wave_invoice_id, case_state=case.state,
        ), mark_read=False)

    def _finish(self, msg: EmailMessage, result: ProcessResult,
                mark_read: bool = True) -> ProcessResult:
        self._store.record(result)
        if mark_read and not self._dry_run:
            self._gmail.mark_read(msg.message_id)
        return result

    @staticmethod
    def _details_to_spec(details: InvoiceDetails, company_key: str, invoice_type: str,
                         attendees: list[Attendee], discount: float) -> dict:
        base = details.line_items[0] if details.line_items else LineItem("Services", 1, 0)
        product_name = select_product(
            company_key, details.service_type, details.events_or_services, details.deal_name
        )
        bank_charge = default_bank_charge(
            company_key, details.events_or_services, invoice_type, details.status
        )
        return {
            "customer_name": details.customer_name,
            "customer_email": details.customer_email,
            "customer_address": details.customer_address,
            "customer_phone": details.customer_phone,
            "amount": base.unit_price * base.quantity,
            "quantity": base.quantity,
            "currency": details.currency,
            "due_date": details.due_date,
            "description": base.description,
            "product_name": product_name,
            "invoice_type": invoice_type,
            "discount_amount": discount,
            "bank_charge_amount": bank_charge,
            "attendees": [{"name": a.name, "email": a.email} for a in attendees],
            "create_missing_contacts": False,
            "send_to_client": False,
        }

    @staticmethod
    def _apply_updates(spec: dict, updates: dict) -> None:
        allowed = {
            "customer_name", "customer_email", "customer_address", "customer_phone",
            "amount", "currency", "due_date", "discount_amount", "invoice_type",
            "bank_charge_amount", "attendees",
        }
        for key, value in updates.items():
            if key in allowed and value is not None:
                spec[key] = value

    @staticmethod
    def _spec_to_details(spec: dict, details: InvoiceDetails) -> None:
        details.customer_name = spec.get("customer_name") or details.customer_name
        details.customer_email = spec.get("customer_email") or details.customer_email
        details.customer_address = spec.get("customer_address") or details.customer_address
        details.customer_phone = spec.get("customer_phone") or details.customer_phone
        details.currency = spec.get("currency") or details.currency
        details.due_date = spec.get("due_date") or details.due_date
        details.discount_amount = float(spec.get("discount_amount") or 0)
        details.bank_charge_amount = float(spec.get("bank_charge_amount") or 0)
        details.is_paid = spec.get("invoice_type") == "paid"
        details.attendees = [Attendee(a["name"], a.get("email")) for a in spec.get("attendees", [])]
        amount = float(spec.get("amount") or 0)
        quantity = float(spec.get("quantity") or 1)
        details.line_items = [LineItem(
            spec.get("description") or details.events_or_services or details.deal_name,
            quantity, amount / quantity, spec.get("product_name")
        )]
        if details.bank_charge_amount:
            details.line_items.append(LineItem("", 1, details.bank_charge_amount, "Bank charges"))

    def _approval_message(self, case: AccountingCase, corrected: bool = False) -> str:
        prefix = "I updated the accounting summary" if corrected else "I found the Zoho record and prepared the accounting summary"
        crm_prompt = ""
        if case.spec.get("attendees"):
            crm_prompt = (
                "\nThe employee email contains attendee details. Reply APPROVE AND UPDATE CRM "
                "if missing Contacts should be created and receive the invoice attachment."
            )
        return (
            f"Hello {case.requester_name},\n\n{prefix} for {case.pid}.\n\n"
            f"{self._summary(case)}\n\n"
            "I have not created or sent an invoice yet. Reply APPROVE to create it, attach it to the "
            "Zoho Deal and linked Contact, and return the PDF to you. Reply with corrections instead if anything is wrong."
            f"{crm_prompt}"
        )

    @staticmethod
    def _summary(case: AccountingCase) -> str:
        s = case.spec
        total = float(s.get("amount") or 0) + float(s.get("bank_charge_amount") or 0) - float(s.get("discount_amount") or 0)
        attendees = ", ".join(a.get("name", "") for a in s.get("attendees", [])) or "None listed"
        return (
            f"Billing business: {case.company_key}\n"
            f"Customer: {s.get('customer_name') or 'Missing'}\n"
            f"Customer email: {s.get('customer_email') or 'Missing'}\n"
            f"Service amount: {float(s.get('amount') or 0):.2f} {s.get('currency') or 'USD'}\n"
            f"Bank charges: {float(s.get('bank_charge_amount') or 0):.2f}\n"
            f"Discount: {float(s.get('discount_amount') or 0):.2f}\n"
            f"Final total: {total:.2f} {s.get('currency') or 'USD'}\n"
            f"Due date: {s.get('due_date') or 'Not provided'}\n"
            f"Attendees: {attendees}\n"
            f"Invoice type: {s.get('invoice_type') or 'unspecified'}"
        )


def build_pipeline(config: Config, dry_run: bool = False,
                   in_memory_store: bool = False) -> Pipeline:
    from .idempotency import build_store

    gmail = GmailClient(config)
    zoho = ZohoClient(config)
    wave = WaveClient(config)
    store = build_store(config, in_memory=in_memory_store)
    cases = build_case_store(in_memory=in_memory_store)
    conversation = OpenAIConversation(config)
    return Pipeline(
        config, gmail, zoho, wave, store, llm=None, dry_run=dry_run,
        cases=cases, conversation=conversation,
    )
