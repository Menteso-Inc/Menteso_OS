"""Deterministic candidate triage and reuse of validated research history."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .models import FirmRecord

DIRECTORIES = frozenset({"lawzana.com", "legal500.com", "chambers.com", "avvo.com",
    "justia.com", "findlaw.com", "superlawyers.com", "justdial.com", "hg.org", "thelawyersglobal.org"})
SOCIAL_OR_NEWS = frozenset({"linkedin.com", "facebook.com", "instagram.com", "youtube.com",
    "wikipedia.org", "globalcompetitionreview.com", "dailyjournal.com", "wizehire.com", "law.com"})
NON_FIRM_ORGANIZATIONS = frozenset({"americanbar.org", "uslaw.org"})


def domain(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.").rstrip(".")


def matches_host(host, values):
    return any(host == item or host.endswith("." + item) for item in values)


def source_kind(url):
    host = domain(url)
    institutional = bool(re.search(r"\.(?:gov|edu)(?:\.[a-z]{2})?$|\.ac\.[a-z]{2}$", host))
    return "directory" if matches_host(host, DIRECTORIES) else "unsupported" if institutional or matches_host(host, SOCIAL_OR_NEWS | NON_FIRM_ORGANIZATIONS) else "website"


def score_candidate(url, title, snippet):
    """A ranking hint, never evidence that a firm meets the buying profile."""
    text = (title + " " + snippet).lower()
    score = 0
    if re.search(r"\b(law firm|law office|attorneys?|lawyers?|solicitors?|advocates?)\b", text):
        score += 5
    if re.search(r"\b(our firm|our team|our attorneys|we represent|legal services|boutique|solo)\b", text):
        score += 3
    if any(hint in urlsplit(url).path.lower() for hint in ("about", "team", "attorney", "contact")):
        score += 2
    if re.search(r"\b(top \d+|best \d+|rankings?|salary|jobs?|careers?|software|marketing agency)\b", text):
        score -= 8
    if source_kind(url) == "directory":
        score -= 2
    return score


def select_candidates(rows, limit, known, excluded):
    """Rank all observed results before the research cap; retain every decision."""
    seen, selected = set(), []
    for row in sorted(rows, key=lambda item: -item["score"]):
        if row["status"] not in {"pending", "selected", "deferred"}:
            continue
        url = row["url"]
        host = domain(url)
        kind = row["source_kind"]
        identity = url if kind == "directory" else host
        status, reason = "selected", "Candidate ranked for source research; fit not yet verified"
        if matches_host(host, excluded):
            status, reason = "rejected", "Domain excluded by targeting profile"
        elif kind == "unsupported" or row["score"] < 0 and kind != "directory":
            status, reason = "rejected", "Non-firm institution, social/news source or low-relevance search result"
        elif kind == "directory" and (urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1] in {"", "directory", "lawyers", "law-firms", "firms"} or row["score"] < 0):
            status, reason = "rejected", "Directory index or unrelated listing; no specific firm identified"
        elif host in known:
            status, reason = "already_known", "Recent validated research for this targeting profile"
            row["previous_run_id"] = known[host]["run_id"]
        elif identity in seen:
            status, reason = "duplicate", "Duplicate candidate in this discovery run"
        elif len(selected) >= limit:
            status, reason = "deferred", "Ranked below the current candidate allowance"
        else:
            selected.append(url)
        seen.add(identity)
        row.update(status=status, reason=reason)
    return selected


def matching_profile(profile):
    from .models import ResearchRequest
    parsed = ResearchRequest.model_validate({key: value for key, value in profile.items() if key not in {"resume_run_id", "refresh_pending"}})
    fields = ("countries", "target_segments", "buyer_roles", "size_min", "size_max", "small_firm_max", "size_unit")
    return {name: sorted(getattr(parsed, name)) if isinstance(getattr(parsed, name), list) else getattr(parsed, name) for name in fields}


def recent_research(session, request):
    """Completed, validated live results only; budgets/queries do not invalidate fit."""
    known, warnings = {}, []
    if request.mode != "live" or request.research_freshness_days == 0:
        return known, warnings
    now = datetime.now(timezone.utc)
    target = matching_profile(request.model_dump())
    from .qualification import load_policy
    fingerprint = load_policy().fingerprint
    for receipt_path in session.agent_dir.glob("*/completion.json"):
        if receipt_path.parent.name == session.run_id:
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("agent") != "prospect_research_agent" or receipt.get("run_id") != receipt_path.parent.name:
                raise ValueError("Invalid receipt")
            artifact = receipt_path.parent / "result.json"
            if artifact.is_symlink() or receipt_path.is_symlink():
                raise ValueError("Linked artifact")
            result = json.loads(artifact.read_text(encoding="utf-8"))
            if result.get("mode") != "live" or result.get("tests", {}).get("passed") is not True:
                continue
            if matching_profile(result.get("request_profile", {})) != target:
                continue
            for item in result.get("data", {}).get("firms", []):
                firm = FirmRecord.model_validate(item)
                if firm.qualification_policy_fingerprint != fingerprint or set(firm.product_assessments) != {"manage", "launch"}:
                    continue
                if firm.provenance != "live" or firm.source_type != "firm_website" or firm.fit_status not in {"qualified", "excluded"}:
                    continue
                researched = datetime.fromisoformat(firm.researched_at)
                age = (now - researched).total_seconds()
                if not 0 <= age <= request.research_freshness_days * 86400:
                    continue
                host = domain(firm.website)
                if host and (host not in known or researched > known[host]["researched_at"]):
                    known[host] = {"run_id": receipt["run_id"], "researched_at": researched}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            warnings.append("A saved research result could not be reused; its candidates may require fresh research")
    return known, list(dict.fromkeys(warnings))
