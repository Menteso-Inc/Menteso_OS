"""Reviewed directory sources; discovery never implies collection permission.

An unknown/changed source stays on hold. A reviewed, permitted source still has
to pass robots, throttling, network and per-run limits in SourceTools.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


POLICY_PATH = Path(__file__).with_name("directory_sources.json")
DIRECTORY_HINT = re.compile(
    r"\b(?:lawyer|attorney|law firm|solicitor|advocate)s?\s+(?:directory|directories)\b"
    r"|\bdirectory of\s+(?:lawyers?|attorneys?|solicitors?)\b"
    r"|\b(?:claim|register|list) (?:your |a )?(?:lawyer|attorney) profile\b", re.I)


class DirectoryRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    host: str = Field(min_length=3, max_length=253)
    name: str = Field(min_length=1, max_length=100)
    homepage: str = Field(max_length=2000)
    state: Literal["review_required", "restricted", "permitted"] = "review_required"
    terms_url: str | None = Field(default=None, max_length=2000)
    note: str = Field(min_length=1, max_length=1000)
    reviewed_on: date | None = None
    review_valid_days: int = Field(default=30, ge=1, le=90)
    automated_collection: bool = False
    storage_for_prospect_research: bool = False
    commercial_prospecting: bool = False
    permission_reference: str | None = Field(default=None, max_length=1000)
    reviewed_terms_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    profile_path_prefixes: list[str] = Field(default_factory=list, max_length=20)
    max_profile_pages_per_run: int = Field(default=3, ge=1, le=20)
    min_interval_seconds: float = Field(default=5, ge=1, le=60)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value):
        value = value.casefold().removeprefix("www.")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,63}", value):
            raise ValueError("Directory host must be a DNS name, without a wildcard or URL")
        return value

    @field_validator("homepage", "terms_url")
    @classmethod
    def safe_document(cls, value):
        if value is not None:
            from .tools import validate_public_url
            value = validate_public_url(value)
        return value

    @field_validator("profile_path_prefixes")
    @classmethod
    def bounded_paths(cls, values):
        if any(not value.startswith("/") or value == "/" or len(value) > 200
               or re.search(r"[?#\\\x00-\x20]", value) or unquote(value) != value
               or any(part in {".", ".."} for part in value.split("/")) for value in values):
            raise ValueError("Specify bounded, unencoded profile path prefixes, never the whole site")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def documented_permission(self):
        if not host_matches(urlsplit(self.homepage).hostname or "", self.host):
            raise ValueError("Homepage must belong to the directory host")
        if self.state == "permitted" and not all((self.terms_url, self.reviewed_on,
                self.automated_collection, self.storage_for_prospect_research,
                self.commercial_prospecting, self.permission_reference,
                self.reviewed_terms_sha256, self.profile_path_prefixes)):
            raise ValueError("Permitted collection requires documented, dated terms and use rights")
        return self


class DirectoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=80)
    discovery_queries: list[str] = Field(min_length=1, max_length=5)
    sources: list[DirectoryRule] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_sources(self):
        hosts = [rule.host for rule in self.sources]
        if len(set(hosts)) != len(hosts):
            raise ValueError("Duplicate directory host")
        if any(not query.strip() or len(query) > 280 for query in self.discovery_queries):
            raise ValueError("Directory search queries must be short and nonempty")
        return self

    def find(self, url):
        host = (urlsplit(url).hostname or "").casefold().rstrip(".")
        matches = [rule for rule in self.sources if host_matches(host, rule.host)]
        return max(matches, key=lambda rule: len(rule.host), default=None)


def host_matches(host, expected):
    return host == expected or host.endswith("." + expected)


def load_directory_policy():
    # Read on each run, so a reviewed JSON change does not require a worker restart.
    try:
        return DirectoryPolicy.model_validate(json.loads(POLICY_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        raise ValueError("Directory source policy is missing or invalid; collection is blocked") from None


def terms_digest(text):
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def access_decision(url, policy, *, today=None):
    """Machine-enforce a recorded review, never infer rights from public visibility."""
    rule = policy.find(url)
    if rule is None:
        return {"source_access": "review_required", "reason": "New lawyer directory; review collection, storage and commercial-use terms before fetching profiles"}
    details = {"source_access": rule.state, "terms_url": rule.terms_url,
               "terms_reviewed_on": rule.reviewed_on.isoformat() if rule.reviewed_on else None,
               "directory_name": rule.name, "reason": rule.note}
    if rule.state != "permitted":
        return details
    age = ((today or date.today()) - rule.reviewed_on).days
    if not 0 <= age <= rule.review_valid_days:
        return {**details, "source_access": "review_required", "reason": "Directory terms review is stale or future-dated; collection is held"}
    path = unquote(urlsplit(url).path or "/")
    if "%" in path or any(part in {".", ".."} for part in path.split("/")) or not any(
            path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
            for prefix in rule.profile_path_prefixes):
        return {**details, "source_access": "path_disallowed", "reason": "URL is outside the reviewed profile paths; whole-directory downloads are disabled"}
    return {**details, "reason": "Reviewed directory profile; live terms and robots checks still required"}


def discovery_queries(website_queries, countries, policy, *, round_robin=False):
    """Share the existing query budget; directory discovery is not an extra allowance."""
    pairs = ((query, country) for query in policy.discovery_queries for country in countries) if round_robin else (
        (query, country) for country in countries for query in policy.discovery_queries)
    directory_queries = [" ".join(part for part in (query, country) if part) for query, country in pairs]
    combined = []
    for index in range(max(len(website_queries), len(directory_queries))):
        if index < len(website_queries):
            combined.append(website_queries[index])
        if index < len(directory_queries):
            combined.append(directory_queries[index])
    return list(dict.fromkeys(combined))


def profile_observation(page, official_website, directory_host=None):
    """Keep explicitly associated profile contacts as unqualified source observations.

    Never infer an email or associate an unlabelled footer with a lawyer. These
    observations are separate from the verified, primary-source lead inventory.
    """
    from .models import DirectoryProfile, Evidence, ExtractedContact
    from .rule_extraction import CONTACT_ROLE, _person_name
    from .tools import EMAIL_PATTERN
    text = page.get("text", "")
    names = list(dict.fromkeys(name for name in page.get("headings", []) if _person_name(name)))
    contacts, evidence = [], []
    blocks = list(page.get("contact_blocks", []))
    if len(names) == 1:
        start = text.find(names[0])
        if start >= 0:
            blocks.append(text[start:start + 500])
    for block in blocks:
        if not isinstance(block, str) or len(block) > 500 or block not in text:
            continue
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        people = list(dict.fromkeys(line for line in lines if _person_name(line)))
        emails = list(dict.fromkeys(EMAIL_PATTERN.findall(block)))
        roles = list(dict.fromkeys(line for line in lines if CONTACT_ROLE.search(line)
                    and line not in people and len(line) <= 150))
        if len(people) != 1 or len(emails) != 1 or len(roles) > 1:
            continue
        if any(emails[0] in footer for footer in page.get("footer_blocks", [])):
            continue
        if host_matches(emails[0].rsplit("@", 1)[1].casefold(), directory_host or (urlsplit(page["url"]).hostname or "").removeprefix("www.")):
            continue  # Directory operator contacts are not lawyer prospects.
        contact = ExtractedContact(name=people[0], role=roles[0] if roles else None, email=emails[0])
        if contact in contacts or len(contacts) == 20:
            continue
        contacts.append(contact)
        for field, value in (("contact_name", contact.name), ("contact_role", contact.role), ("email", contact.email)):
            if value:
                evidence.append(Evidence(field=field, value=value, source_url=page["url"],
                    excerpt=block, retrieved_at=page["retrieved_at"]))
    return DirectoryProfile(source_url=page["url"], retrieved_at=page["retrieved_at"],
        contacts=contacts, evidence=evidence, official_website=official_website).model_dump()
