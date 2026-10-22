"""Grounded product fit and research handoffs. This module never grants sending."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import PersonalizationBrief, ProductAssessment, QualificationPolicy

POLICY_PATH = Path(__file__).with_name("qualification_policy.json")
GENERIC_INBOXES = frozenset({"info", "contact", "hello", "office", "admin", "reception", "enquiries", "inquiries", "support", "team", "mail"})
NEED_SUBJECT = r"\b(?:we|our firm|our practice|the firm)\s+(?:are\s+|is\s+)?(?:looking for|seeking|need|needs|want|wants|plan to|plans to)\b"
MANAGE_NEED = re.compile(NEED_SUBJECT + r"[^.!?\n]{0,180}\b(?:case management|matter management|billing software|practice management|workflow system)\b", re.I)
LAUNCH_NEED = re.compile(NEED_SUBJECT + r"[^.!?\n]{0,180}\b(?:website|client intake|inquiry intake|online presence)\b", re.I)
WEBSITE_PROJECT = re.compile(r'\b(?:(?:our |new |official |this )?website (?:is (?:currently )?)?under (?:construction|development)|(?:our |an all )?new website (?:is )?coming soon)\b', re.I)
NEW_FIRM = re.compile(r"\b(?:launch(?:ed|ing)?|establish(?:ed|ing)?|open(?:ed|ing)?|found(?:ed|ing)?)\b[^.!?\n]{0,90}\b(?:law firm|law practice|legal practice|law offices?)\b|\bnew\s+(?:law firm|law practice|legal practice)\b|\b(?:law firm|law practice|law offices?)\b[^.!?\n]{0,100}\b(?:founded|established|launched) in 20\d{2}\b", re.I)


def load_policy():
    # Invalid/missing product configuration stops qualification rather than guessing.
    return QualificationPolicy.model_validate(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


def _fresh(value, days, now):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return 0 <= (now - parsed).total_seconds() <= days * 86400
    except (ValueError, TypeError, AttributeError):
        return False


def _role_match(role, roles):
    if role and 'operations' in roles and re.search(r'\bchief operating officer\b',role,re.I):
        role = role + ' operations'
    return bool(role and not re.search(r"\b(?:retired|former|emeritus|deceased)\b|in memoriam", role, re.I)
                and any(re.search(r"\b" + re.escape(value.casefold()) + r"\b", role.casefold()) for value in roles))


def enrich_product_fit(record, request, policy=None, now=None):
    """Use accepted evidence only; source assertions are never expressed interest."""
    policy = policy or load_policy()
    now = now or datetime.now(timezone.utc)
    record.practice_areas = list({area.casefold(): area for area in reversed(record.practice_areas)}.values())[::-1]
    assessments = {}
    for product in ("manage", "launch"):
        relevant = []
        for item in record.evidence:
            if product == "manage" and item.field == "workflow_need" and MANAGE_NEED.search(item.excerpt):
                relevant.append(item)
            if product == "launch" and item.field == "website_need" and LAUNCH_NEED.search(item.excerpt):
                relevant.append(item)
            if product == 'launch' and item.field == 'website_need' and WEBSITE_PROJECT.search(item.excerpt):
                from urllib.parse import urlsplit
                if urlsplit(item.source_url).path.rstrip('/') in {'','/landing','/welcome'}:
                    relevant.append(item)
            if product == "launch" and item.field == "firm_stage" and NEW_FIRM.search(item.excerpt):
                years = [int(value) for value in re.findall(r"\b20\d{2}\b", item.excerpt)]
                # An old or undated founding story cannot establish a new practice now.
                own_statement=bool(record.name and record.name.casefold() in item.excerpt.casefold() or re.search(r'\b(?:we|our (?:law )?firm|our practice)\b',item.excerpt,re.I))
                if years and own_statement and any(now.year - 1 <= year <= now.year for year in years):
                    relevant.append(item)
        if record.fit_status == "excluded":
            decision = ProductAssessment(status="no_current_fit", reasons=list(record.fit_reasons))
        elif record.fit_status != "qualified":
            decision = ProductAssessment(reasons=["Mandatory firm evidence is incomplete", *record.fit_reasons][:10])
        elif relevant:
            decision = ProductAssessment(status="potential_fit", confidence="medium", evidence=relevant[:20],
                reasons=[f"{record.name}: {relevant[0].excerpt}",
                         "This published statement supports a product-fit hypothesis; current need and buying intent remain unconfirmed"],
                hypothesis=policy.products[product].question)
        elif product == "manage":
            roster_label = 'published attorney roster' if record.size_basis == 'published_roster' else 'published attorney count'
            decision = ProductAssessment(status="potential_fit", confidence="low",
                evidence=[item for item in record.evidence if item.field in {"organization_type", "size", "practice_area"}][:20],
                reasons=[f"{record.name}: {record.size} attorneys ({roster_label}); practice areas include {', '.join(record.practice_areas[:3])}",
                         "These practices involve client matters and documents that Manage can connect; current tools, pain and buying intent remain unconfirmed"],
                hypothesis=policy.products[product].question)
        else:
            decision = ProductAssessment(reasons=["No current sourced website/intake need or recent practice-launch statement"])
        assessments[product] = decision
    record.product_assessments = assessments
    record.qualification_policy_version = policy.version
    record.qualification_policy_fingerprint = policy.fingerprint
    potential = [key for key, value in assessments.items() if value.status == "potential_fit"]
    if not potential:
        record.primary_product = "none"
    elif len(potential) == 1:
        record.primary_product = potential[0]
    else:
        # Stronger source-backed relevance wins over a broad firm-type hypothesis.
        strengths = {key: len([item for item in assessments[key].evidence if item.field in {"firm_stage", "workflow_need", "website_need"}]) for key in potential}
        record.primary_product = "both" if strengths["manage"] == strengths["launch"] else max(strengths, key=strengths.get)
    briefs = []
    for contact in record.contacts:
        local = (contact.email or "").split("@", 1)[0].casefold()
        contact.inbox_type = "named" if contact.association_status == "sourced" and contact.name else "generic" if local in GENERIC_INBOXES else "firm_unassigned" if contact.email else "unknown"
        reasons = []
        if record.fit_status != "qualified": reasons.append("Firm qualification is incomplete or excluded")
        if not contact.email: reasons.append("No published email")
        email_domain = (contact.email or "").rsplit("@", 1)[-1].casefold()
        same_firm = email_domain == record.domain or email_domain.endswith("." + record.domain)
        explicit_association = contact.association_status == "sourced" and record.name and any(
            all(value and value.casefold() in item.excerpt.casefold() for value in (record.name, contact.name, contact.role, contact.email))
            for item in contact.evidence)
        if contact.email and not (same_firm or explicit_association):
            reasons.append("Mailbox affiliation with this firm is unconfirmed")
        if contact.inbox_type not in {"named", "generic"}: reasons.append("Person association or general-inbox purpose is unconfirmed")
        if contact.inbox_type == "named" and not _role_match(contact.role, request.buyer_roles):
            reasons.append("Named person's current buyer role is missing or outside the profile")
        if contact.verification_status != "valid": reasons.append("Email verification is not valid")
        elif not _fresh(contact.verified_at, request.verification_freshness_days, now): reasons.append("Email verification is stale or undated")
        if not _fresh(record.researched_at, max(1, request.research_freshness_days), now): reasons.append("Firm research is stale or undated")
        if record.provenance != "live": reasons.append("Synthetic fixture cannot become a live campaign contact")
        contact.readiness_reasons = reasons
        contact.research_ready = not reasons
        if not contact.email:
            continue
        for product in potential:
            holds = list(reasons)
            if contact.inbox_type == "named" and not _role_match(contact.role, policy.products[product].buyer_roles):
                holds.append("Named person's role does not match this product's buyer profile")
            holds.append("Campaign provider, recipient basis, suppression and limits have not authorized sending")
            facts = [item for item in record.evidence if item.field in {"name", "country", "practice_area"}][:10]
            if contact.inbox_type == "named": facts += contact.evidence[:5]
            facts += assessments[product].evidence[:5]
            briefs.append(PersonalizationBrief(product=product, email=contact.email,
                audience="named" if contact.inbox_type == "named" else "firm",
                contact_name=contact.name if contact.inbox_type == "named" else None,
                product_policy_version=policy.version, facts=facts[:20],
                hypothesis=assessments[product].hypothesis, question=policy.products[product].question,
                research_ready=contact.research_ready and not any("role does not match" in reason for reason in holds),
                hold_reasons=holds))
    record.personalization_briefs = briefs
    record.outreach_eligible = False
    return record
