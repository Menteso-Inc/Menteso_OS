"""Durable, read-only URL tests. No search, model, verification or email calls.

A completed job covers its reviewed URL/navigation scope, never an entire site
by implication. Partial jobs retain their queue and unread records for continuation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.prospect_store import ProspectStore
from shared.research_runtime import BudgetExceeded, RunBudget, _atomic_json, _file_lock
from .directory_sources import access_decision
from .models import ResearchRequest
from .source_formats import extract_collection, recipe_fingerprint
from .tools import USER_AGENT, SourceError, SourceTools, utc_now, validate_public_url


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2000)
    refresh: bool = False

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        value = validate_public_url(value.strip(), allow_query=True)
        # The generic input accepts a URL, not passwords/tokens disguised as URLs.
        # SourceTools narrows pagination queries to the actual reviewed recipe.
        from .source_formats import QUERY_KEYS
        try:
            pairs = parse_qsl(urlsplit(value).query, strict_parsing=True, max_num_fields=20)
        except ValueError:
            raise ValueError("Use a public source URL without credentials or unsupported queries") from None
        if any(key not in QUERY_KEYS and not key.startswith("utm_") for key, _ in pairs):
            raise ValueError("Use a source URL without credentials; configure authentication privately in .env")
        return value


class SourceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=250)
    role: str | None = Field(default=None, max_length=250)
    email: str | None = Field(default=None, max_length=254)
    firm: str | None = Field(default=None, max_length=250)
    website: str | None = Field(default=None, max_length=2000)
    country: str | None = Field(default=None, max_length=250)
    source_url: str = Field(max_length=2000)
    retrieved_at: str = Field(max_length=80)
    evidence_excerpt: str = Field(max_length=500)
    evidence_path: str | None = Field(default=None, max_length=200)
    verification_status: Literal["not_checked"] = "not_checked"
    qualification_status: Literal["needs_research"] = "needs_research"
    outreach_eligible: Literal[False] = False
    change: Literal["new", "changed", "unchanged"] = "new"

    @field_validator("source_url", "website")
    @classmethod
    def url(cls, value):
        return validate_public_url(value, allow_query=True) if value else value


def _key(row):
    identity = row.get("email") or "|".join(row.get(key) or "" for key in ("name", "firm", "website", "source_url"))
    return hashlib.sha256(identity.casefold().encode()).hexdigest()


def _digest(row):
    return hashlib.sha256(json.dumps({key: row.get(key) for key in
        ("name", "role", "email", "firm", "website", "country")}, sort_keys=True).encode()).hexdigest()


def _same_month(timestamp):
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.tzinfo is not None and parsed.strftime("%Y-%m") == datetime.now(timezone.utc).strftime("%Y-%m") and parsed <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


class SourceImports:
    """One bounded job at a time; the process lock also protects multiple servers."""
    def __init__(self, directory, tools_factory=SourceTools):
        self.directory = Path(directory)
        if self.directory.is_symlink():
            raise ValueError("Source imports cannot use a linked state directory")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = ProspectStore(self.directory.parent)
        self.tools_factory = tools_factory
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="source-import")
        self.lock = threading.Lock()
        self.future = None
        self.active = None

    def _path(self, job_id):
        if len(job_id) != 64 or any(char not in "0123456789abcdef" for char in job_id):
            raise ValueError("Invalid source job")
        path = self.directory / (job_id + ".json")
        if path.is_symlink():
            raise ValueError("Source job cannot use a linked file")
        return path

    def _read(self, job_id):
        path = self._path(job_id)
        if not path.exists():
            return None
        if path.stat().st_size > 4_000_000:
            raise ValueError("Source job exceeds the state limit")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("job_id") != job_id or len(state.get("records", [])) > 500:
            raise ValueError("Invalid source job state")
        state["records"] = [SourceObservation.model_validate(row).model_dump() for row in state.get("records", [])]
        return state

    def _write(self, state):
        state["updated_at"] = utc_now()
        _atomic_json(self._path(state["job_id"]), state)
        _atomic_json(self.directory / "latest.json", {"job_id": state["job_id"]})

    @staticmethod
    def public(state):
        if state is None:
            return {"status": "idle", "records": []}
        return {key: state.get(key) for key in ("job_id", "source_url", "status", "message", "records",
            "pages_read", "updated_at", "completed_at", "coverage", "budget", "adapter", "truncated")}

    def latest(self):
        if self.active is not None and self.future is not None and not self.future.done():
            return self.get(self.active["job_id"])
        path = self.directory / "latest.json"
        if path.is_symlink():
            raise ValueError("Source pointer cannot use a linked file")
        if not path.exists():
            return self.public(None)
        return self.get(json.loads(path.read_text())["job_id"])

    def get(self, job_id):
        state = self._read(job_id)
        if state is None and self.active and self.active["job_id"] == job_id:
            state = self.active
        if state is None:
            raise ValueError("Source test not found")
        if state.get("status") in {"running", "queued"} and (self.future is None or self.future.done()):
            state = {**state, "status": "partial", "message": "Worker stopped; continue from preserved source progress."}
        return self.public(state)

    def start(self, payload):
        request = ImportRequest.model_validate(payload)
        with self.lock:
            if self.future is not None and not self.future.done():
                raise RuntimeError("A source test is already running")
            # No provider preflight: test URLs must not spend research credits.
            profile = ResearchRequest(extraction_mode="rules", spend_policy="free_allowance_only",
                max_llm_calls=0, max_verifications=0, enable_verification=False, deadline_seconds=120,
                request_timeout=15, max_candidates=10, max_pages_per_firm=1, budget_usd=0)
            budget = RunBudget(profile)
            budget.limits["pages"] = min(budget.limits["pages"], 20)
            tools = self.tools_factory(profile, budget)
            tools.source_access_store = self.store
            url = tools.collection_url(request.url)
            rule = tools.directory_policy.find(url)
            if rule:
                self._pace(tools, rule)
            recipe = rule.reader_for(url) if rule else None
            fingerprint = recipe_fingerprint(rule)
            job_id = hashlib.sha256((url + "|" + fingerprint).encode()).hexdigest()
            previous = self._read(job_id)
            fresh = request.refresh or previous is None or (previous.get("completed_at") and not _same_month(previous["completed_at"]))
            if fresh:
                state = {"job_id": job_id, "source_url": url, "fingerprint": fingerprint,
                         "queue": [url], "visited": [], "buffer": [], "records": [], "pages_read": 0,
                         "coverage": "reviewed_feed" if recipe and
                             any((recipe.next_path, recipe.next_selector, recipe.profile_link_selector)) else "page_only",
                         "previous": {_key(row): _digest(row) for row in (previous or {}).get("records", [])}}
            else:
                state = previous
            state.update(status="queued", message="Checking source access and saved progress.")
            self.active = state
            reset = request.refresh or bool(previous and previous.get("completed_at") and not _same_month(previous["completed_at"]))
            self.future = self.executor.submit(self._execute, state, tools, reset)
            return self.public(state)

    def _pace(self, tools, rule):
        transport = tools._transport
        def paced(url, *args):
            origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"
            robots = tools._robots.get(origin)
            delay = max(rule.min_interval_seconds, robots.crawl_delay(USER_AGENT) or 0) if robots else rule.min_interval_seconds
            rate = robots.request_rate(USER_AGENT) if robots else None
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
            wait = self.store.reserve_source_request(rule.host, delay, tools._timeout())
            if wait is None:
                raise BudgetExceeded("Source pacing cannot fit inside the remaining request deadline")
            if wait:
                time.sleep(wait)
            tools.budget.check()
            return transport(url, *args)
        tools._transport = paced

    def _execute(self, state, tools, fresh=False):
        acquired = False
        try:
            with _file_lock(self.directory / "execution.lock"):
                acquired = True
                # A different server may have finished this scope while this
                # job waited. Never overwrite its newer queue with a stale copy.
                latest = self._read(state["job_id"])
                if latest is not None and not fresh:
                    state = latest
                self._collect(state, tools)
        except Exception as error:
            # Provider exception text and raw payloads never reach the browser.
            state.update(status="failed", message="Source test stopped unexpectedly; completed records are preserved.")
            logging.getLogger(__name__).error("Source test %s stopped (%s)", state["job_id"], type(error).__name__)
            if acquired:
                self._write(state)

    def _collect(self, state, tools):
        state.update(status="running", message="Reading the selected source.")
        self._write(state)
        rule = tools.directory_policy.find(state["source_url"])
        try:
            if rule:
                decision = access_decision(state["source_url"], tools.directory_policy)
                if decision["source_access"] != "permitted":
                    raise SourceError("directory_" + decision["source_access"] + ": " + decision["reason"])
                tools._check_directory_terms(state["source_url"])
            if state.get("completed_at") and _same_month(state["completed_at"]):
                state.update(status="cached", message="Saved result reused for this URL scope this month; no profile/feed pages downloaded.")
                return
            initial_count, read_count = len(state["records"]), 0
            identities = {_key(row) for row in state["records"]}
            while state["buffer"] or state["queue"]:
                tools.budget.check()
                while state["buffer"] and len(state["records"]) - initial_count < 50 and len(state["records"]) < 500:
                    row = SourceObservation.model_validate(state["buffer"].pop(0)).model_dump()
                    key = _key(row)
                    if key not in identities:
                        prior = state["previous"].get(key)
                        row["change"] = "new" if prior is None else "unchanged" if prior == _digest(row) else "changed"
                        state["records"].append(row)
                        identities.add(key)
                # Preserve buffered rows before reading any additional page.
                self._write(state)
                if (state["buffer"] or state["queue"]) and len(state["records"]) >= 500:
                    state.update(status="held", message="This test reached 500 saved observations. Narrow the provider's reviewed feed scope; no whole-site completion is claimed.")
                    return
                if (state["buffer"] or state["queue"]) and (len(state["records"]) - initial_count >= 50 or read_count >= 10):
                    state.update(status="partial", message="Batch limit reached. Continue from saved progress; this is not a whole-site import.")
                    return
                if not state["queue"]:
                    break
                url = tools.collection_url(state["queue"][0])
                if url in state["visited"]:
                    raise SourceError("pagination_loop: source returned an already visited page; review navigation")
                if rule and (tools.directory_policy.find(url) != rule or
                             urlsplit(url).hostname != urlsplit(state["source_url"]).hostname):
                    raise SourceError("blocked_navigation: collection cannot leave the selected source host")
                page = tools._read_page(url, urlsplit(url).hostname, include_document=True)
                read_count += 1
                recipe = rule.reader_for(page["url"]) if rule else None
                if recipe:
                    data = extract_collection(page["document"], page, recipe, rule.host)
                elif rule:
                    data = self._directory_profile(page, rule)
                else:
                    data = self._public_page(page, tools.request)
                # Validate all records and all navigation before committing a page.
                rows = [SourceObservation.model_validate(row).model_dump() for row in data["records"]]
                navigation = [*data.get("profile_urls", []), *([data["next_url"]] if data.get("next_url") else [])]
                checked = []
                for link in navigation:
                    link = tools.collection_url(link)
                    if (not rule or tools.directory_policy.find(link) != rule or urlsplit(link).hostname != urlsplit(url).hostname
                            or (urlsplit(state["source_url"]).scheme == "https" and urlsplit(link).scheme != "https")
                            or access_decision(link, tools.directory_policy)["source_access"] != "permitted"):
                        raise SourceError("blocked_navigation: link is outside the reviewed source paths")
                    if link in state["visited"] or link == url:
                        if link == data.get("next_url"):
                            raise SourceError("pagination_loop: next link returns a completed page")
                        continue
                    if link not in state["queue"] and link not in checked:
                        checked.append(link)
                if len(state["queue"]) + len(checked) > 500:
                    raise SourceError("navigation_limit: too many links; narrow the reviewed source scope")
                state["queue"].pop(0)
                state["queue"].extend(checked)
                state["visited"].append(url)
                state["pages_read"] += 1
                state["buffer"].extend(rows)
                state["adapter"] = data["adapter"]
                self._write(state)
            state.update(status="complete", completed_at=utc_now(), message=(
                "Reviewed URL feed exhausted. These are unverified source records, not qualified leads."
                if state["coverage"] == "reviewed_feed" else "Selected page extracted. Whole-site coverage has not been established."))
        except BudgetExceeded:
            state.update(status="partial", message="Time or request budget reached. Completed records and the next page are saved.")
        except (SourceError, ValueError, TypeError, RecursionError) as error:
            # Controlled categories only; no upstream body or raw arbitrary error.
            if isinstance(error, SourceError):
                state.update(status="partial" if str(error).startswith(("directory_page_limit:", "source_delay_exceeds_budget:")) else "held", message=str(error)[:1000])
            else:
                state.update(status="held", message="Source format did not match the reviewed reader. Configure or review its extraction recipe.")
        finally:
            state["budget"] = tools.budget.snapshot()
            self._write(state)

    @staticmethod
    def _directory_profile(page, rule):
        from .directory_sources import profile_observation
        targets = list(dict.fromkeys(item["url"] for item in page.get("website_links", [])))
        website = targets[0] if len(targets) == 1 else None
        observed = profile_observation(page, website, rule.host)
        records = []
        for contact in observed["contacts"]:
            evidence = next((fact["excerpt"] for fact in observed["evidence"] if fact["field"] == "email" and fact["value"] == contact["email"]), "")
            records.append({**contact, "website": website, "source_url": page["url"],
                "retrieved_at": page["retrieved_at"], "evidence_excerpt": evidence,
                "verification_status": "not_checked", "qualification_status": "needs_research", "outreach_eligible": False})
        return {"records": records, "profile_urls": [], "next_url": None, "adapter": "directory-profile:rules"}

    @staticmethod
    def _public_page(page, request):
        from .models import ExtractedFirm
        from .rule_extraction import extract_rules
        extracted = ExtractedFirm.model_validate(extract_rules([page], request))
        records = []
        for contact in extracted.contacts:
            evidence = next((item.excerpt for item in extracted.evidence if item.field == "email" and item.value == contact.email), "")
            records.append({"name": contact.name, "role": contact.role, "email": contact.email,
                "firm": extracted.name, "website": page["url"], "country": extracted.country,
                "source_url": page["url"], "retrieved_at": page["retrieved_at"],
                "evidence_excerpt": evidence, "verification_status": "not_checked",
                "qualification_status": "needs_research", "outreach_eligible": False})
        return {"records": records, "profile_urls": [], "next_url": None, "adapter": "public-page:rules"}
