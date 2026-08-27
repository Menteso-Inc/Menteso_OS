"""OpenAI-backed, structured interpretation of employee accounting replies."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests

from .cases import AccountingCase
from .config import Config
from .models import Attendee, EmailMessage
from .parser import _new_message_text

logger = logging.getLogger(__name__)


@dataclass
class ConversationDecision:
    intent: str
    updates: dict = field(default_factory=dict)
    crm_update: Optional[bool] = None
    send_to_client: Optional[bool] = None
    explanation: str = ""


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": [
            "approve", "cancel", "correction", "answer", "question", "other"
        ]},
        "customer_name": {"type": ["string", "null"]},
        "customer_email": {"type": ["string", "null"]},
        "customer_address": {"type": ["string", "null"]},
        "customer_phone": {"type": ["string", "null"]},
        "amount": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"], "description": "ISO YYYY-MM-DD when clear"},
        "discount_amount": {"type": ["number", "null"]},
        "bank_charge_amount": {"type": ["number", "null"]},
        "invoice_type": {"type": ["string", "null"], "enum": ["paid", "unpaid", "unspecified", None]},
        "attendees": {
            "type": ["array", "null"],
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": ["string", "null"]},
                },
                "required": ["name", "email"],
            },
        },
        "crm_update": {"type": ["boolean", "null"]},
        "send_to_client": {"type": ["boolean", "null"]},
        "explanation": {"type": "string"},
    },
    "required": [
        "intent", "customer_name", "customer_email", "customer_address",
        "customer_phone", "amount", "currency", "due_date",
        "discount_amount", "bank_charge_amount", "invoice_type", "attendees", "crm_update",
        "send_to_client", "explanation",
    ],
}


class OpenAIConversation:
    def __init__(self, config: Optional[Config]):
        self.key = config.openai_api_key if config else ""
        self.model = config.openai_model if config else "gpt-4.1-mini"

    def analyze_reply(self, message: EmailMessage, case: AccountingCase) -> ConversationDecision:
        newest = _new_message_text(message.body_text).strip()
        simple = newest.lower().strip(" .!\r\n")
        if re.fullmatch(r"(?:yes[, ]*)?(?:approved?|go ahead|proceed|do it)(?:[, ]+and update (?:the )?crm)?", simple):
            return ConversationDecision("approve", crm_update="update" in simple)
        if re.fullmatch(r"(?:cancel|stop|do not proceed|don't proceed)", simple):
            return ConversationDecision("cancel")
        fallback = self._deterministic_correction(newest)
        if fallback.updates or fallback.intent in {"question", "cancel"}:
            return fallback
        if not self.key:
            return ConversationDecision("other", explanation="OpenAI conversation parser is not configured")

        prompt = (
            "You classify the newest employee reply in an accounting email case. "
            "Quoted history is already removed. Never treat a question as approval. "
            "Only classify approve when the employee explicitly authorizes proceeding. "
            "Extract corrections without inventing missing values.\n\n"
            f"CASE STATE:\n{json.dumps(case.spec, ensure_ascii=False)}\n\n"
            f"NEWEST REPLY:\n{newest}"
        )
        try:
            data = self._structured(prompt)
        except Exception:
            logger.exception("OpenAI reply classification failed; using safe no-action fallback")
            return ConversationDecision(
                "other", explanation="AI classification unavailable; no accounting change was made"
            )
        updates = {
            key: value for key, value in data.items()
            if key not in {"intent", "crm_update", "send_to_client", "explanation"}
            and value is not None
        }
        return ConversationDecision(
            intent=data["intent"], updates=updates,
            crm_update=data.get("crm_update"),
            send_to_client=data.get("send_to_client"),
            explanation=data.get("explanation", ""),
        )

    @staticmethod
    def _deterministic_correction(text: str) -> ConversationDecision:
        """Cover common employee corrections even when the AI service is unavailable."""
        updates: dict = {}
        lower = text.lower()
        email = re.search(
            r"(?:email|e-mail)(?:\s+(?:address))?\s+(?:to|is|as)\s+"
            r"([a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,})",
            text, re.I,
        )
        if email:
            updates["customer_email"] = email.group(1)
        amount = re.search(
            r"(?:change|set|correct|update|use)?\s*(?:the\s+)?(?:invoice\s+)?amount\s+"
            r"(?:to|is|as)?\s*(?:USD|EUR|GBP|INR|\$|€|£)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
            text, re.I,
        )
        if amount:
            updates["amount"] = float(amount.group(1).replace(",", ""))
        discount = re.search(
            r"(?:discount|less)\s+(?:of\s+)?(?:USD|EUR|GBP|INR|\$|€|£)?\s*"
            r"([0-9][0-9,]*(?:\.\d{1,2})?)", text, re.I,
        )
        if discount:
            updates["discount_amount"] = float(discount.group(1).replace(",", ""))
        due = re.search(r"(?:due date|due)\s+(?:to|is|as|on)\s+(\d{4}-\d{2}-\d{2})", text, re.I)
        if due:
            updates["due_date"] = due.group(1)
        name = re.search(
            r"(?:customer|client|company)\s+name\s+(?:to|is|as)\s+([^\r\n,.;]+)", text, re.I
        )
        if name:
            updates["customer_name"] = name.group(1).strip()
        if re.search(r"(?:remove|no)\s+bank\s+charges?", lower):
            updates["bank_charge_amount"] = 0.0
        elif re.search(r"(?:add|include)\s+(?:the\s+)?(?:required\s+)?(?:bank\s+)?charges?", lower):
            updates["bank_charge_amount"] = 25.0
        bank = re.search(
            r"(?:bank\s+charges?)\s+(?:to|is|as|of)\s+(?:USD|\$)?\s*"
            r"([0-9][0-9,]*(?:\.\d{1,2})?)", text, re.I,
        )
        if bank:
            updates["bank_charge_amount"] = float(bank.group(1).replace(",", ""))
        if updates:
            return ConversationDecision("correction", updates=updates)
        if "?" in text or re.match(r"\s*(?:why|what|which|where|how|can|should|do we)\b", lower):
            return ConversationDecision("question")
        return ConversationDecision("other")

    def polish(self, factual_text: str) -> str:
        """Make a deterministic factual message sound natural without adding facts."""
        if not self.key:
            return factual_text
        payload = {
            "model": self.model,
            "store": False,
            "temperature": 0.2,
            "input": [{
                "role": "user",
                "content": (
                    "Rewrite this accounting email in a warm, concise, professional tone. "
                    "Preserve every number, name, warning, and requested action exactly. "
                    "Do not add facts, promises, recipients, or financial advice.\n\n"
                    + factual_text
                ),
            }],
        }
        try:
            response = self._post(payload)
            text = self._output_text(response)
            return text.strip() or factual_text
        except Exception:
            logger.exception("OpenAI reply polishing failed; using factual template")
            return factual_text

    def _structured(self, prompt: str) -> dict:
        payload = {
            "model": self.model,
            "store": False,
            "temperature": 0.1,
            "input": [{"role": "user", "content": prompt}],
            "text": {"format": {
                "type": "json_schema", "name": "accounting_reply",
                "strict": True, "schema": _SCHEMA,
            }},
        }
        response = self._post(payload)
        return json.loads(self._output_text(response))

    def _post(self, payload: dict) -> dict:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _output_text(response: dict) -> str:
        for item in response.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
        return ""
