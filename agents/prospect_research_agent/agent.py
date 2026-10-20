"""Evidence-first, bounded prospect research with resumable manager handoffs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from shared import config as _config
from .models import ContactRecord, Evidence, ExtractedFirm, FirmRecord, ResearchRequest
from .tasks import extract_with_crew
from .tests import tests
from .discovery import recent_research, source_kind

AGENT_NAME = "prospect_research_agent"
AGENT_CONFIG = {
    "name": "Prospect Research and Qualification",
    "description": "Sourced firm and contact research for configurable business campaigns.",
    "role": "Prospect Research", "version": "1.0.0", "status": "active",
    "execution_enabled": True, "requires_llm": False, "accepts_upload": False,
    "group": "Lexmom Sub Manager", "parent_agent": "lexmom_marketing_agent",
    "hidden_from_dashboard": True,
}
STRATEGIES = ("standard", "focused", "minimal_evidence")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normal(text):
    return " ".join(str(text).casefold().split())


def _domain(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _country(value):
    if not value:
        return None
    import pycountry
    try:
        return pycountry.countries.lookup(value.strip()).alpha_2
    except LookupError:
        return None


def _profile_key(request):
    profile = request.model_dump(exclude={"resume_run_id", "refresh_pending"})
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def _record_quality(record):
    """Required facts outrank the number of incidental contact/practice quotes."""
    return (record.fit_status != "needs_research",
            sum(bool(value) for value in (record.name, record.country, record.size, record.practice_areas)),
            len(record.evidence))


def contact_target_count(records, request):
    """Count fresh, qualified unique contacts for the requested product(s)."""
    from .qualification import enrich_product_fit
    emails=set()
    for data in records:
        record=enrich_product_fit(FirmRecord.model_validate(data),request)
        products=('manage','launch') if request.product=='both' else (request.product,)
        for brief in record.personalization_briefs:
            if brief.product in products and brief.research_ready:emails.add(brief.email.casefold())
    return len(emails)


def validate_request(input_data=None):
    payload = dict(input_data or {})
    for field, setting in (("budget_usd", "BUDGET_USD"), ("deadline_seconds", "DEADLINE_SECONDS")):
        if field not in payload and os.getenv(f"PROSPECT_RESEARCH_AGENT_{setting}"):
            payload[field] = os.getenv(f"PROSPECT_RESEARCH_AGENT_{setting}")
    for kind, setting in (("queries", "QUERY_COST_USD"), ("llm_calls", "LLM_CALL_COST_USD"), ("verifications", "VERIFICATION_COST_USD")):
        value = os.getenv(f"PROSPECT_RESEARCH_AGENT_{setting}")
        if value and kind not in payload.get("unit_costs", {}):
            payload.setdefault("unit_costs", {})[kind] = float(value)
    return ResearchRequest.model_validate(payload)


def live_preflight(request):
    from shared.llm import validate_llm_readiness
    from .qualification import load_policy
    load_policy()
    if request.extraction_mode == "model":
        validate_llm_readiness()
    required = {"llm_calls"} if request.extraction_mode == "model" else set()
    if not request.seed_urls:
        required.add("queries")
        dedicated = os.getenv("PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY", "")
        allow_shared = os.getenv("PROSPECT_RESEARCH_AGENT_ALLOW_SHARED_SEARCH_KEY", "false").lower() == "true"
        shared = os.getenv("SERPAPI_API_KEY", "") if allow_shared else ""
        if not (dedicated or shared):
            raise ValueError("Configure PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY or explicitly authorize the shared search key")
    if request.enable_verification:
        required.add("verifications")
        if not os.getenv("PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY"):
            raise ValueError("PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY is required when verification is enabled")
    if request.spend_policy != "free_allowance_only" and any(request.unit_costs.get(kind, 0) <= 0 for kind in required):
        raise ValueError("Configure positive conservative unit costs for enabled provider calls before a live run")
    if any(_country(country) is None for country in request.countries):
        raise ValueError("Country filters must be recognized country names or ISO codes")


def _ground_evidence(extracted, pages):
    page_text = {page["url"]: _normal(page.get("text", "")) for page in pages}
    page_dates = {page["url"]: page.get("retrieved_at") for page in pages}
    valid = []
    rejected = 0
    number_words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    for item in extracted.evidence:
        excerpt = _normal(item.excerpt)
        value = _normal(item.value)
        value_present = value in excerpt
        if item.field == "country":
            # Normalize codes only against an explicit country name in the source.
            # Never infer a country from travel history, phone prefix, or a state.
            import pycountry
            code = _country(item.value)
            country_info = pycountry.countries.get(alpha_2=code) if code else None
            aliases = [getattr(country_info, key, "") for key in ("name", "official_name", "common_name")]
            value_present = bool(country_info and (
                any(alias and re.search(r"(?<!\w)" + re.escape(alias.casefold()) + r"(?!\w)", excerpt) for alias in aliases)
                or re.search(r"(?<!\w)(?:" + country_info.alpha_2 + "|" + country_info.alpha_3 + r")(?!\w)", item.excerpt)
            ))
            if not value_present:
                from .primary_facts import postal_country
                value_present = any(code == candidate and item.excerpt == quote
                    for page in pages if page['url'] == item.source_url for candidate, quote in postal_country(page))
        if item.field == "size" and value.isdigit():
            count = rf"(?:{re.escape(value)}|{number_words.get(int(value), 'UNMATCHABLE')})"
            value_present = bool(re.search(rf"\b{count}\s+(?:(?:experienced|senior|qualified|practicing|full-time|skilled|licensed|dedicated|award-winning|personal injury)\s+){{0,2}}(?:attorneys?|lawyers?|advocates?)\b", excerpt))
            if not value_present:
                from .primary_facts import attorney_roster
                value_present = any((roster := attorney_roster(page)) and roster['count'] == int(value)
                    and roster['excerpt'] == item.excerpt for page in pages if page['url'] == item.source_url)
            if value == "1" and re.search(r"\b(?:sole|solo)\s+(?:attorney|lawyer)\b", excerpt):
                value_present = True
        if item.source_url in page_text and excerpt in page_text[item.source_url] and value_present:
            item.retrieved_at = page_dates[item.source_url]
            valid.append(item)
        else:
            rejected += 1
    return valid, rejected


def qualify(url, extracted, pages, request):
    evidence, rejected = _ground_evidence(extracted, pages)
    def supported(field, value):
        return value is not None and any(item.field == field and (
            _normal(item.value) == _normal(value) or
            (field == "country" and _country(value) is not None and _country(item.value) == _country(value))
        ) for item in evidence)
    name = extracted.name if supported("name", extracted.name) else None
    raw_country = extracted.country if supported("country", extracted.country) else None
    country = _country(raw_country)
    countries = sorted({_country(item.value) for item in evidence if item.field == 'country' and _country(item.value)})
    size = extracted.size if supported("size", extracted.size) and extracted.size_unit == "attorneys" else None
    areas = [area for area in extracted.practice_areas if supported("practice_area", area)]
    firm_identity = extracted.source_type == "firm_website" and any(item.field == "organization_type" and item.value in {"LegalService", "Attorney"} for item in evidence)
    for page in pages:
        match = re.search(r"\b(?:law firm|law offices?|firm of attorneys|advocates|(?:sole|solo) (?:attorney|lawyer))\b", page.get("text", ""), re.I)
        if match and extracted.source_type == "firm_website":
            firm_identity = True
            evidence.append(Evidence(field="organization_type", value=match.group(), source_url=page["url"], excerpt=match.group(), retrieved_at=page.get("retrieved_at")))
            break
    contacts = []
    emails = set()
    for contact in extracted.contacts if extracted.source_type == "firm_website" else []:
        contact_name = contact.name if supported("contact_name", contact.name) else None
        role = contact.role if supported("contact_role", contact.role) else None
        email = contact.email.lower() if contact.email and supported("email", contact.email) and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact.email) else None
        if email and email in emails:
            continue
        if email:
            emails.add(email)
        if contact_name or role or email:
            contact_evidence = [item for item in evidence if (item.field, _normal(item.value)) in {
                ("contact_name", _normal(contact_name)), ("contact_role", _normal(role)), ("email", _normal(email))
            }]
            if role and contact_name and not any(all(_normal(value) in _normal(item.excerpt) for value in (contact_name, role)) for item in contact_evidence):
                role = None
            association = "sourced" if contact_name and email and any(
                all(_normal(value) in _normal(item.excerpt) for value in (contact_name, email))
                for item in contact_evidence
            ) else "unconfirmed"
            if association=='unconfirmed' and contact_name and email and role:
                from .primary_facts import profile_contact
                if any((profile:=profile_contact(page)) and profile['name']==contact_name and profile['email'].casefold()==email
                       and profile['role']==role for page in pages):association='sourced'
            from .qualification import _role_match
            role_match = _role_match(role, request.buyer_roles)
            contacts.append(ContactRecord(name=contact_name, role=role, email=email, evidence=contact_evidence,
                                          association_status=association, buyer_role_match=role_match))
    # Capture literal firm-domain addresses even when the model omits a general
    # inbox. Never assign that inbox to a person or invent a buyer role.
    from .tools import EMAIL_PATTERN
    domain = _domain(url)
    for page in pages if extracted.source_type == "firm_website" else []:
        text = page.get("text", "")
        for match in EMAIL_PATTERN.finditer(text):
            email = match.group().lower()
            if email in emails or email.rsplit("@", 1)[-1].removeprefix("www.") != domain or len(contacts) >= 50:
                continue
            excerpt = text[max(0, match.start() - 60):min(len(text), match.end() + 60)]
            item = Evidence(field="email", value=match.group(), source_url=page["url"], excerpt=excerpt,
                            retrieved_at=page.get("retrieved_at"))
            evidence.append(item)
            contacts.append(ContactRecord(email=email, evidence=[item]))
            emails.add(email)
    reasons = []
    segment = "solo" if size == 1 else "small" if size and size <= request.small_firm_max else "mid_size" if size and size <= request.size_max else None
    filters = {_country(value) for value in request.countries}
    excluded = (bool(countries) and bool(filters) and not set(countries).intersection(filters)) or (
        size is not None and not request.size_min <= size <= request.size_max
    ) or (segment is not None and segment not in request.target_segments)
    if extracted.source_type in {"directory", "news", "other"}:
        status = "excluded"
        reasons.append("Third-party source; research the firm's official website before qualification")
    elif excluded:
        status = "excluded"
        reasons.append("Sourced country or firm size does not match the configured profile")
    elif name and countries and size and areas and segment and firm_identity:
        status = "qualified"
        reasons.append("Published legal practice, location and attorney count match the campaign profile")
        reasons.append("Lexmom relevance is a campaign hypothesis; buying intent is unknown")
    else:
        status = "needs_research"
        if not name: reasons.append("Firm name evidence is missing")
        if not countries: reasons.append("Country evidence is missing or unrecognized")
        if not size: reasons.append("Explicit attorney-count evidence is missing")
        if not areas: reasons.append("Legal practice evidence is missing")
        if not firm_identity: reasons.append("Public law-firm identity evidence is missing")
        if size and not segment: reasons.append("Firm size is outside the supported segment definitions")
    domain = _domain(url)
    record = FirmRecord(
        firm_id=hashlib.sha256(domain.encode()).hexdigest()[:20], website=url, domain=domain,
        name=name, source_type=extracted.source_type, country=country,countries=countries, size=size, size_unit="attorneys" if size else "unknown",
        segment=segment, practice_areas=areas, contacts=contacts, evidence=evidence,
        fit_status=status, fit_reasons=reasons, product=request.product, researched_at=_now(),
        provenance=request.mode,
        research_errors=[f"Rejected {rejected} unsupported evidence items"] if rejected else [],
    )
    if size:
        from .primary_facts import attorney_roster
        record.size_basis = 'published_roster' if any((roster := attorney_roster(page)) and roster['count'] == size
            and any(e.field == 'size' and e.source_url == page['url'] and e.excerpt == roster['excerpt'] for e in evidence) for page in pages) else 'explicit_count'
    from .qualification import enrich_product_fit
    return enrich_product_fit(record, request)


def _result(request, session, records, pending, budget, status="success", errors=None):
    counts = Counter(row["fit_status"] for row in records)
    return {
        "status": status, "run_id": session.run_id, "mode": request.mode,
        "profile_fingerprint": _profile_key(request),
        "data": {"firms": records, "pending_urls": pending,
                 "directory_profiles": list(getattr(session, "directory_profiles", {}).values()),
                 "candidates": getattr(session, "discovery_audit", []), "summary": {
            **{state: counts[state] for state in ("qualified", "needs_research", "excluded")},
            "researched": len(records), "countries": dict(Counter(row.get("country") or "unknown" for row in records)),
            "target": request.target_count,
            "product_fit": {product: sum(row.get("product_assessments", {}).get(product, {}).get("status") in {"potential_fit", "confirmed_need"} for row in records) for product in ("manage", "launch")},
            "research_ready_contacts": sum(contact.get("research_ready") is True for row in records for contact in row.get("contacts", [])),
        }},
        "rows": records, "errors": errors or [], "budget": budget.snapshot(),
        "request_profile": request.model_dump(exclude={"resume_run_id", "refresh_pending"}),
    }


def get_dashboard_data():
    return {"status": "ready", "mode": "research_only", "schedule": "On demand",
            "message": "Live research requires validated provider credentials and cost limits.",
            "defaultProfile": ResearchRequest().model_dump(), "executionEnabled": True}


def _run_agent(input_data=None, on_step=None, cancelled=None, session=None, source_tools=None, extractor=None, initial_strategy=None):
    """Real execution defaults to live; synthetic data requires explicit fixture mode."""
    from shared.research_runtime import BudgetExceeded, ResearchSession, RunBudget, RunCancelled, redact
    from .tools import SourceTools, SourceError

    started = time.monotonic()
    try:
        request = validate_request(input_data)
    except (ValidationError, ValueError, TypeError):
        return {"status": "failure", "errors": [{"phase": "input", "error": "Invalid research profile; check allowed fields and limits"}], "data": {"firms": []}}
    session = session or ResearchSession(AGENT_NAME, run_id=request.resume_run_id)
    memory = session.load_memory()
    strategy = session.best_strategy("prospect_research", default="standard")
    if initial_strategy in STRATEGIES:
        strategy = initial_strategy
    if strategy not in STRATEGIES:
        strategy = "standard"
    budget = RunBudget(request, cancelled=cancelled)
    records, pending, errors = [], [], []
    reserved_candidates = set()
    enrichment_archive = None
    exhausted_firms = 0
    record = None
    audit = []
    session.discovery_audit = audit
    outcome = "preflight"
    try:
        from .qualification import load_policy
        policy = load_policy()
        from shared.prospect_store import ProspectStore, targeting_key
        inventory = ProspectStore(session.agent_dir)
        inventory_profile = targeting_key(request, policy.fingerprint)
        saved_inventory=inventory.records(inventory_profile,mode=request.mode) if request.target_contacts is not None else []
        if (not request.resume_run_id and request.target_contacts is not None
                and contact_target_count(saved_inventory,request)>=request.target_contacts):
            # Meeting an inventory goal must not spend new search/verification
            # credits merely because the dashboard Run button is clicked again.
            from .qualification import enrich_product_fit
            cached=[enrich_product_fit(FirmRecord.model_validate(row),request,policy).model_dump() for row in saved_inventory]
            result=_result(request,session,cached,[],budget,'success')
            result['data']['summary'].update(target_contacts=request.target_contacts,
                qualified_verified_inventory_contacts=contact_target_count(cached,request))
            result.update(reused_inventory=True,preflight=False,strategy=strategy,
                execution_time=round(time.monotonic()-started,3),free_allowance_checks=[],
                artifacts=[{'path':str(session.artifact_path),'name':'result.json','label':'Saved qualified prospect records'}])
            result['tests']=tests.run(result)
            result['status']='success' if result['tests']['passed'] else 'failure'
            session.finish(result,result['status'],strategy,'Validated saved research reused without provider operations.',result['execution_time'])
            return redact(result)
        if request.mode == "live":
            live_preflight(request)
        else:
            if not request.fixture_pages or not request.fixture_extractions:
                raise ValueError("Explicit fixture mode requires synthetic source pages and extractions")
        if request.resume_run_id:
            checkpoint = session.read_checkpoint()
            compatible = bool(checkpoint and checkpoint.get("profile_fingerprint") == _profile_key(request))
            # Defaults added later may be absent in old checkpoints. Validate the
            # exact original hash and require the normalized request to match.
            if checkpoint and not compatible:
                original = checkpoint.get("request_profile", {})
                original_hash = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
                try:
                    profile_only = {key: value for key, value in original.items() if key not in {"resume_run_id", "refresh_pending"}}
                    normalized = validate_request(profile_only).model_dump(exclude={"resume_run_id", "refresh_pending"})
                    control_free_hash = hashlib.sha256(json.dumps(profile_only, sort_keys=True).encode()).hexdigest()
                    compatible = checkpoint.get("profile_fingerprint") in {original_hash, control_free_hash} and normalized == request.model_dump(exclude={"resume_run_id", "refresh_pending"})
                except (ValidationError, ValueError, TypeError):
                    compatible = False
            if not compatible:
                raise ValueError("Resume requires a matching saved research profile")
            audit.extend(checkpoint["data"].get("candidates", []))
            from .qualification import enrich_product_fit
            records = [enrich_product_fit(FirmRecord.model_validate(row), request, policy).model_dump() for row in checkpoint["data"]["firms"]]
            pending = list(checkpoint["data"].get("pending_urls", []))
            reserved_candidates = {_domain(row["website"]) for row in records}
            if request.refresh_pending:
                retry = [row for row in records if row["fit_status"] == "needs_research" and row.get("evidence")]
                if retry:
                    from shared.research_runtime import _atomic_json
                    enrichment_archive = session.run_dir / "before-enrichment.json"
                    if not enrichment_archive.exists(): _atomic_json(enrichment_archive, checkpoint)
                    pending = list(dict.fromkeys([row["website"] for row in retry] + pending))
                    records = [row for row in records if row not in retry]
                    for entry in audit:
                        if _domain(entry.get("resolved_url") or entry.get("url") or "") in {_domain(row["website"]) for row in retry}:
                            entry.update(status="selected", reason="Resuming pending source enrichment; no new search")
            previous_counts = checkpoint.get("budget", {}).get("counts", {})
            for kind, amount in previous_counts.items():
                if amount:
                    budget.consume(kind, amount)
        tools = source_tools or SourceTools(request, budget)
        known, history_warnings = recent_research(session, request)
        errors.extend({"phase": "history", "error": warning} for warning in history_warnings)
        tools.known_domains = known
        tools.source_access_store = inventory
        if not hasattr(tools, "directory_profiles"):
            tools.directory_profiles = {}
        if request.resume_run_id:
            from .models import DirectoryProfile
            tools.directory_profiles.update({row["source_url"]: DirectoryProfile.model_validate(row).model_dump()
                for row in checkpoint["data"].get("directory_profiles", [])})
        session.directory_profiles = tools.directory_profiles
        tools.discovery_records = audit
        tools.query_reserver = lambda queries, limit: inventory.reserve_queries(inventory_profile, session.run_id, queries, limit)
        tools.incremental_read = True
        langchain_tools = tools.get_langchain_tools() if request.mode == "live" else None
        if not request.resume_run_id:
            if request.mode == "fixture":
                pending = list(dict.fromkeys(page["url"] for page in request.fixture_pages))
            else:
                try:
                    pending = request.seed_urls or langchain_tools["discover"].invoke({"strategy": strategy})
                except SourceError as exc:
                    # A later search failure must not discard earlier usable candidates.
                    pending = [item["url"] for item in audit if item.get("status") == "selected"]
                    if not pending:
                        raise
                    errors.append({"phase": "discovery", "error": str(redact(str(exc)))})
        completed = {_domain(row["website"]) for row in records}
        excluded_domains = {_domain("https://" + value.removeprefix("https://").removeprefix("http://")) for value in request.exclude_domains}
        selected = []
        for candidate_url in dict.fromkeys(pending):
            entry = next((item for item in audit if item.get("url") == candidate_url and item.get("status") in {"selected", "deferred"}), None)
            if entry is None:
                entry = {"url": candidate_url, "title": "", "snippet": "", "query": "",
                         "source_kind": source_kind(candidate_url), "status": "selected", "reason": "Supplied or resumed candidate"}
                audit.append(entry)
            entry["status"] = "selected"
            host = _domain(candidate_url)
            if host in completed | excluded_domains:
                entry.update(status="duplicate" if host in completed else "rejected", reason="Already processed in this run or excluded by profile")
            elif host in known:
                entry.update(status="already_known", reason="Recent validated research for this profile", previous_run_id=known[host]["run_id"])
            elif len(selected) >= request.max_candidates:
                entry.update(status="deferred", reason="Candidate allowance reached")
            else:
                selected.append(candidate_url)
        pending = selected
        session.checkpoint(_result(request, session, records, pending, budget, "running"))
        outcome = "failure"
        qualified = sum(row["fit_status"] == "qualified" for row in records)
        def target_met():
            if request.target_contacts is None:return qualified >= request.target_count
            combined={row['domain']:row for row in [*saved_inventory,*records]}
            return contact_target_count(combined.values(),request)>=request.target_contacts
        while pending and not target_met():
            record = None
            budget.check()
            url = pending[0]
            entry = next(item for item in audit if item.get("url") == url and item.get("status") == "selected")
            domain = _domain(url)
            if domain in completed:
                entry.update(status="duplicate", reason="Firm was already processed in this run")
                pending.pop(0)
                continue
            if domain not in reserved_candidates:
                budget.consume("candidates")
                reserved_candidates.add(domain)
            if request.mode == "live" and entry["source_kind"] == "directory":
                try:
                    resolved = langchain_tools["resolve_directory"].invoke({"url": url}) if "resolve_directory" in langchain_tools else None
                except (BudgetExceeded, RunCancelled):
                    raise
                except Exception as exc:
                    entry.update(status="needs_research", reason=str(redact(f"Directory resolution failed: {exc}")))
                    if "directory_" in str(exc):
                        entry["source_access"] = "blocked" if any(marker in str(exc) for marker in ("blocked", "challenge")) else "review_required"
                    pending.pop(0)
                    continue
                if not resolved:
                    entry.update(status="needs_research", reason="No single unambiguous published firm website link")
                    pending.pop(0)
                    continue
                entry["resolved_url"] = resolved
                url, domain = resolved, _domain(resolved)
                if domain in completed | excluded_domains or domain in known:
                    entry.update(status="already_known" if domain in known else "duplicate" if domain in completed else "rejected", reason="Resolved firm already researched or excluded")
                    if domain in known: entry["previous_run_id"] = known[domain]["run_id"]
                    pending.pop(0)
                    continue
            if on_step:
                on_step(f"Researching firm {len(records) + 1}: {domain}")
            pages = []
            record = None
            best_record = None
            firm_errors = []
            retry_memory = dict(memory)
            attempt_strategies = [strategy] + [item for item in STRATEGIES if item != strategy]
            for attempt_strategy in attempt_strategies:
                budget.check()
                extracting = False
                try:
                    if request.mode == "fixture":
                        pages = [page for page in request.fixture_pages if _domain(page["url"]) == domain]
                        # Fixture extractions are keyed by website to avoid pretending test rows are live facts.
                        proposed = next((item for item in request.fixture_extractions if _domain(item.get("website", "")) == domain), None)
                        if proposed is None:
                            raise ValueError("Missing explicit fixture extraction for source domain")
                        extracted = ExtractedFirm.model_validate({key: value for key, value in proposed.items() if key != "website"})
                    else:
                        if not pages:
                            pages = langchain_tools["read_firm"].invoke({"url": url, "strategy": attempt_strategy})
                        usable = [page for page in pages if page.get("text")]
                        if not usable:
                            source_errors = sorted({str(page.get("error")) for page in pages if page.get("error")})
                            detail = "; ".join(source_errors)[:500]
                            raise ValueError("No readable source evidence was returned" + (f": {detail}" if detail else ""))
                        extracting = True
                        from .rule_extraction import extract_rules
                        extraction = extract_rules if request.extraction_mode == "rules" else (extractor or extract_with_crew)
                        extracted = ExtractedFirm.model_validate(extraction(usable, request, budget, attempt_strategy, retry_memory))
                        extracting = False
                    record = qualify(url, extracted, pages, request)
                    # Source enrichment is bounded work, distinct from the three
                    # error-recovery attempts. A three-page default stays three;
                    # deeper runs can actually use their approved source limit.
                    if request.mode == 'live' and 'read_more' in langchain_tools:
                        for _ in range(max(0, request.max_pages_per_firm - len(pages))):
                            if record.fit_status == 'excluded': break
                            gaps = [field for field in ('name', 'country', 'size') if getattr(record, field) is None]
                            if not record.practice_areas: gaps.append('practice_area')
                            if not any(c.email for c in record.contacts): gaps.append('contacts')
                            if not gaps and not any(c.buyer_role_match for c in record.contacts): gaps.append('buyer_roles')
                            if not gaps: break
                            more = langchain_tools['read_more'].invoke({'url': url, 'missing_fields': gaps})
                            before = {page['url'] for page in pages if page.get('text')}
                            if not any(page.get('text') and page['url'] not in before for page in more): break
                            pages = more
                            extracted = ExtractedFirm.model_validate(extraction([p for p in pages if p.get('text')], request, budget, attempt_strategy, retry_memory))
                            record = qualify(url, extracted, pages, request)
                            if on_step: on_step('Enriched primary-source evidence within the firm page limit')
                    if best_record is None or record.fit_status != "needs_research" or _record_quality(record) >= _record_quality(best_record):
                        best_record = record
                    # Empty supported facts are a research gap, not a malformed
                    # extraction. Follow a new page below or retain the unknowns;
                    # re-prompting the same page cannot supply missing evidence.
                    record_report = tests.run(_result(request, session, [record.model_dump()], [], budget))
                    if not record_report["passed"]:
                        raise ValueError("Extracted firm failed automatic output validation")
                    missing = []
                    if record.fit_status == "needs_research":
                        missing = [field for field in ("name", "country", "size") if getattr(record, field) is None]
                        if not record.practice_areas: missing.append("practice_area")
                        if not any(item.field == "organization_type" for item in record.evidence): missing.append("organization_type")
                    if record.fit_status != "excluded" and not any(contact.email for contact in record.contacts):
                        missing.append("contacts")
                    if (request.mode == "live" and missing and "read_more" in langchain_tools
                            and attempt_strategy != attempt_strategies[-1]):
                        more = langchain_tools["read_more"].invoke({"url": url, "missing_fields": missing})
                        existing = {page["url"] for page in pages if page.get("text")}
                        if any(page.get("text") and page["url"] not in existing for page in more):
                            pages = more
                            retry_memory["recovery_context"] = {"missing_fields": missing,
                                "error": "Missing sourced facts: " + ", ".join(missing),
                                "previous_strategy": attempt_strategy}
                            if on_step: on_step("Following published links for missing firm details")
                            continue
                    # New sources take priority over re-prompting the same text.
                    # An unrelated bad contact quote must not trigger a repeat
                    # extraction just because the firm has an unknown size.
                    required = {field for field in ("name", "country", "size") if getattr(record, field) is None}
                    if not record.practice_areas: required.add("practice_area")
                    rejected_quotes = [item.model_dump(exclude={"retrieved_at"}) for item in extracted.evidence
                                       if item.field in required and not any(
                                           item.field == accepted.field and item.value == accepted.value
                                           and item.source_url == accepted.source_url for accepted in record.evidence)]
                    if (request.mode == "live" and record.fit_status == "needs_research"
                            and rejected_quotes and attempt_strategy != attempt_strategies[-1]):
                        missing_reason = "; ".join(record.fit_reasons)
                        record = None
                        raise ValueError("Source grounding rejected required facts: " + missing_reason + ". Each quote must contain its own value "
                                         "and appear on its cited page. For name, quote just the literal firm name. "
                                         "Rejected evidence: " + json.dumps(rejected_quotes, ensure_ascii=False)[:1200])
                    record.research_errors.extend(firm_errors)
                    strategy = attempt_strategy
                    break
                except (BudgetExceeded, RunCancelled):
                    raise
                except Exception as exc:
                    firm_errors.append(str(redact(f"{type(exc).__name__}: {exc}")))
                    if not extracting and not any(page.get("text") for page in pages) and any(
                        marker in str(exc) for marker in (
                            "robots_disallowed", "HTTP 401", "HTTP 403", "HTTP 404", "HTTP 410", "HTTP 429",
                            "unsafe_url", "unsafe_dns", "blocked_redirect", "unsupported_content",
                        )
                    ):
                        if on_step:
                            on_step("Source access is blocked or unavailable; retaining the failure without another request")
                        break
                    retry_memory["recovery_context"] = {
                        "error": firm_errors[-1], "traceback": str(redact(traceback.format_exc()))[-1000:],
                        "previous_strategy": attempt_strategy,
                    }
                    if not any(page.get("text") for page in pages):
                        pages = []
                    if extracting and any(marker in str(exc).casefold() for marker in ("401", "403", "authentication", "insufficient_quota", "invalid api key")):
                        raise
                    if on_step:
                        on_step(f"Research recovery: switching strategy after attempt {len(firm_errors)}")
            if best_record is not None and (record is None or _record_quality(record) < _record_quality(best_record)):
                record = best_record
                record.research_errors.extend(firm_errors)
            if record is None:
                exhausted_firms += 1
                record = qualify(url, ExtractedFirm(), pages, request)
                record.research_errors.extend(firm_errors)
                errors.append({"phase": "research", "error": "Firm research exhausted its adjusted strategies", "domain": domain})
            for page in pages:
                if page.get("error") and page["error"] not in record.research_errors:
                    record.research_errors.append(page["error"])
            entry.update(status="failed" if not record.evidence else record.fit_status, reason="; ".join(record.fit_reasons))
            records.append(record.model_dump())
            completed.add(domain)
            qualified += record.fit_status == "qualified"
            pending.pop(0)
            session.checkpoint(_result(request, session, records, pending, budget, "running"))
            if request.enable_verification and record.fit_status == "qualified":
                for contact in record.contacts:
                    # Do not spend verification credits on a contact that would
                    # still be held for an unsourced identity or non-buyer role.
                    non_verification_holds = [reason for reason in contact.readiness_reasons
                        if not reason.startswith(('Email verification',))]
                    if contact.email and not non_verification_holds:
                        try:
                            verification = langchain_tools["verify_email"].invoke({"email": contact.email})
                            contact.verification_status = verification.get("status", "unknown")
                            contact.verified_at = verification.get("verified_at")
                            contact.verification_provider = verification.get("provider")
                            if verification.get("error"):
                                record.research_errors.append(str(redact(verification["error"])))
                            from .qualification import enrich_product_fit
                            enrich_product_fit(record, request)
                            records[-1] = record.model_dump()
                            session.checkpoint(_result(request, session, records, pending, budget, "running"))
                        except (BudgetExceeded, RunCancelled):
                            raise
                        except Exception as exc:
                            record.research_errors.append(str(redact(f"Verification failed: {exc}")))
            records[-1] = record.model_dump()
        final_status = "failure" if exhausted_firms and exhausted_firms == len(records) else "success" if target_met() else "partial"
        result = _result(request, session, records, pending, budget, final_status, errors)
        if request.target_contacts is not None:
            combined={row['domain']:row for row in [*saved_inventory,*records]}
            result['data']['summary'].update(target_contacts=request.target_contacts,
                qualified_verified_inventory_contacts=contact_target_count(combined.values(),request))
        outcome = result["status"]
    except RunCancelled:
        if record is not None and record.domain not in {row["domain"] for row in records}:
            records.append(record.model_dump())
        result = _result(request, session, records, pending, budget, "cancelled", [{"phase": "execution", "error": "Run cancelled; completed records preserved"}])
        outcome = "cancelled"
    except BudgetExceeded:
        if record is not None and record.domain not in {row["domain"] for row in records}:
            records.append(record.model_dump())
        result = _result(request, session, records, pending, budget, "partial", [{"phase": "limits", "error": "Configured run limit reached; completed records preserved"}])
        outcome = "partial"
    except Exception as exc:
        result = _result(request, session, records, pending, budget, "failure", [{"phase": outcome, "error": str(redact(f"{type(exc).__name__}: {exc}"))}])
    # Every unprocessed candidate remains visible, including an interrupted source.
    by_domain = {row["domain"]: row for row in records}
    for entry in audit:
        if entry.get("status") == "selected":
            row = by_domain.get(_domain(entry.get("resolved_url") or entry.get("url") or ""))
            entry.update(status=row["fit_status"] if row else "deferred",
                         reason="; ".join(row["fit_reasons"]) if row else "Run ended before this candidate was researched")
    result["tests"] = tests.run(result)
    if not result["tests"]["passed"]:
        result["status"] = "failure"
        outcome = "failure"
        result["errors"].append({"phase": "self_test", "error": "Output validation failed; result cannot be accepted"})
    if result["tests"]["passed"] and records:
        try:
            for item in records:
                inventory.save(inventory_profile, session.run_id, item)
            result["inventory"] = {"saved_observations": len(records), "mode": request.mode,
                "unique_firms": len(inventory.records(inventory_profile, request.mode))}
        except (OSError, ValueError, sqlite3.Error):
            result["status"] = outcome = "failure"
            result["errors"].append({"phase": "storage", "error": "Prospect inventory could not be persisted; run artifact is retained"})
    if 'tools' in locals():
        result["free_allowance_checks"] = getattr(tools, "free_allowance_checks", [])
    result["execution_time"] = round(time.monotonic() - started, 3)
    result["preflight"] = outcome == "preflight"
    result["strategy"] = strategy
    result["artifacts"] = [{"path": str(session.artifact_path), "name": "result.json", "label": "Sourced prospect records"}]
    if enrichment_archive:
        result["artifacts"].append({"path": str(enrichment_archive), "name": enrichment_archive.name, "label": "Research before enrichment"})
    persistence = session.finish(result, outcome=outcome, strategy=strategy, insight="Validated sourced prospect research", execution_time=result["execution_time"])
    result["memory"] = {"stats": persistence["stats"], "review_required": persistence["review_required"]}
    return redact(result)


def run_agent(input_data=None, on_step=None, cancelled=None, session=None, source_tools=None, extractor=None, initial_strategy=None):
    from shared.research_runtime import ResearchSession
    try:
        request = validate_request(input_data)
    except (ValidationError, ValueError, TypeError):
        return {"status": "failure", "errors": [{"phase": "input", "error": "Invalid research profile; check allowed fields and limits"}], "data": {"firms": []}}
    if initial_strategy is not None and initial_strategy not in STRATEGIES:
        return {"status": "failure", "errors": [{"phase": "input", "error": "Unsupported internal research strategy"}], "data": {"firms": []}}
    session = session or ResearchSession(AGENT_NAME, run_id=request.resume_run_id)
    try:
        with session.execution_lock():
            return _run_agent(input_data, on_step, cancelled, session, source_tools, extractor, initial_strategy)
    except (TimeoutError, OSError):
        return {"status": "failure", "errors": [{"phase": "storage", "error": "Research state is busy or unavailable; retry after the active run completes"}], "data": {"firms": []}}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run bounded prospect research. Live is the default.")
    parser.add_argument("--input", type=Path, help="JSON research profile; synthetic fixtures must explicitly set mode=fixture")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8")) if args.input else None
    completed = run_agent(payload, on_step=print)
    print(json.dumps(completed, indent=2, ensure_ascii=False))
    raise SystemExit(0 if completed["status"] in {"success", "partial"} and completed.get("tests", {}).get("passed") else 1)
