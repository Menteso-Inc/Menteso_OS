"""Extract the PID and paid/unpaid intent from an email.

Hybrid strategy (per the plan):
  1. Try deterministic regex first — free, instant, works for well-formed
     requests like "Please send the invoice for PID: 10432 (unpaid)".
  2. If the regex can't confidently find a PID, fall back to Claude, which
     reliably handles free-form / messy phrasing.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from .models import Attendee, InvoiceType, ParsedRequest

logger = logging.getLogger(__name__)

# "Atty. Nino Don L. Lina (ninodonlina@gmail.com)" -> name + email
_ATTENDEE_RE = re.compile(
    r"([A-Za-z][A-Za-z.'\-\s&]{1,60}?)\s*\(\s*([\w.+-]+@[\w.-]+\.\w{2,})\s*\)"
)
# "apply 100 USD as a discount", "discount of $100", "100 USD discount"
_DISCOUNT_RES = [
    re.compile(r"discount(?:\s+code)?\s+of\s+(?:USD\s*)?\$?\s*(\d+(?:\.\d+)?)", re.I),
    re.compile(r"apply\s+(?:USD\s*)?\$?\s*(\d+(?:\.\d+)?)\s*(?:USD)?\s*(?:as\s+a\s+)?discount", re.I),
    re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:USD)?\s*discount", re.I),
]

# Order matters — first match wins.
# Matches: PID1615592 (canonical Zoho value) | PID: 12345 | PID#12345 |
#          Project ID 12345 | project id: ABC-99
_PID_PATTERNS = [
    # Canonical Zoho PID token: the letters "PID" immediately followed by digits,
    # e.g. "PID1615592". Captured whether or not a label precedes it.
    re.compile(r"\b(PID\d{3,})\b", re.I),
    re.compile(r"\bP\.?I\.?D\.?\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{1,40})", re.I),
    re.compile(r"\bproject\s*id\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{1,40})", re.I),
    re.compile(r"\bproject\s*[:#\-]\s*([A-Za-z0-9][A-Za-z0-9\-_/]{1,40})", re.I),
]

_PAID_HINT = re.compile(r"\b(paid|payment received|already paid|settled)\b", re.I)
_UNPAID_HINT = re.compile(r"\b(unpaid|outstanding|due|not paid|pending payment)\b", re.I)

# A PID in quoted history is not an instruction.  Require an explicit invoice
# action in the newest text so replies such as "Why ANF invoice?" cannot create
# or resend an invoice.
_ACTION_RE = re.compile(
    r"\b(?:please\s+)?(?:share|send|generate|create|make|prepare|raise|issue)\b"
    r"[^\n.!?]{0,80}\binvoice\b|"
    r"\b(?:please\s+)?invoice\b[^\n.!?]{0,80}\bpid\d*\b|"
    r"\binvoice\b[^\n.!?]{0,80}\b(?:for|of)\s+(?:project\s+)?(?:id\s*[:#-]?\s*)?pid\d+",
    re.I,
)
_REPLY_PREFIX_RE = re.compile(r"^\s*(?:re|fw|fwd)\s*:", re.I)
_QUOTE_BOUNDARY_RES = (
    re.compile(r"(?im)^\s*On .+ wrote:\s*$"),
    re.compile(r"(?im)^\s*-{2,}\s*Forwarded message\s*-{2,}\s*$"),
    re.compile(r"(?im)^\s*From:\s+.+$"),
)


def _new_message_text(body_text: str) -> str:
    """Return only text authored in the newest message, excluding history."""
    end = len(body_text)
    for pattern in _QUOTE_BOUNDARY_RES:
        match = pattern.search(body_text)
        if match:
            end = min(end, match.start())
    lines = []
    for line in body_text[:end].splitlines():
        if line.lstrip().startswith(">"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _has_explicit_action(subject: str, body_text: str) -> bool:
    newest = _new_message_text(body_text)
    # Subjects are useful for new requests, but a reply retains the old request
    # subject and therefore cannot establish a new action.
    candidate = newest if _REPLY_PREFIX_RE.match(subject or "") else f"{subject}\n{newest}"
    return bool(_ACTION_RE.search(candidate))


def _detect_intent(text: str) -> InvoiceType:
    # unpaid checked first: "not paid" also contains "paid"
    if _UNPAID_HINT.search(text):
        return "unpaid"
    if _PAID_HINT.search(text):
        return "paid"
    return "unspecified"


def _regex_extract(text: str) -> Optional[str]:
    for pattern in _PID_PATTERNS:
        m = pattern.search(text)
        if m:
            pid = m.group(1).strip().strip(".,;:)")
            if pid:
                # Every supported Zoho PID contains at least one digit. This
                # prevents prose such as "no PID. This is a test" from treating
                # the following word as a project identifier.
                if not re.search(r"\d", pid):
                    continue
                # Canonical PIDs (e.g. "pid1615592") are stored upper-case in Zoho.
                if re.fullmatch(r"(?i)pid\d+", pid):
                    pid = pid.upper()
                return pid
    return None


def _extract_attendees(text: str) -> list[Attendee]:
    """Find 'Name (email)' pairs, e.g. an event's delegate list. Deduped by email."""
    out: list[Attendee] = []
    seen: set[str] = set()
    for m in _ATTENDEE_RE.finditer(text):
        name = " ".join(m.group(1).split()).strip(" .,-")
        email = m.group(2).strip().lower()
        if not name or email in seen:
            continue
        seen.add(email)
        out.append(Attendee(name=name, email=email))
    return out


def _extract_discount(text: str) -> float:
    for pat in _DISCOUNT_RES:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return 0.0


def parse_request(subject: str, body_text: str, llm=None) -> ParsedRequest:
    """Return a ParsedRequest. `llm` is an optional callable used as fallback.

    `llm` signature: llm(subject, body_text) -> ParsedRequest | None
    (see src/llm.py). Passing llm=None disables the fallback (used in unit tests).
    """
    combined = f"{subject}\n{body_text}".strip()

    pid = _regex_extract(combined)
    intent = _detect_intent(combined)
    attendees = _extract_attendees(body_text)
    discount = _extract_discount(combined)
    action_requested = _has_explicit_action(subject, body_text)

    if pid:
        logger.info("PID %s via regex (intent=%s, attendees=%d, discount=%.2f)",
                    pid, intent, len(attendees), discount)
        return ParsedRequest(pid=pid, invoice_type=intent, confidence=0.95,
                             source="regex", attendees=attendees, discount_amount=discount,
                             action_requested=action_requested)

    # Regex failed to find a PID — try the LLM fallback if one was provided.
    if llm is not None:
        logger.info("Regex found no PID; falling back to Claude")
        result = llm(subject, body_text)
        if result and result.pid:
            if not result.attendees:
                result.attendees = attendees
            if not result.discount_amount:
                result.discount_amount = discount
            # Never let an LLM turn quoted history or a question into a financial
            # action. The newest message must contain an explicit request.
            result.action_requested = action_requested
            return result

    logger.warning("No PID could be extracted from the email")
    return ParsedRequest(pid=None, invoice_type=intent, confidence=0.0,
                        source="none", attendees=attendees, discount_amount=discount,
                        action_requested=action_requested)
