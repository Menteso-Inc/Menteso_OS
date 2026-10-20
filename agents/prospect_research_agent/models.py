"""Validated contracts for sourced business research; no network or LLM imports."""

from __future__ import annotations

import math
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def web_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("A public HTTP(S) URL without embedded credentials is required")
    return value


class Evidence(Contract):
    field: Literal["name", "country", "size", "practice_area", "organization_type", "contact_name", "contact_role", "email", "firm_stage", "workflow_need", "website_need"]
    value: str = Field(min_length=1, max_length=250)
    source_url: str = Field(max_length=2000)
    excerpt: str = Field(min_length=1, max_length=500)
    retrieved_at: str | None = None

    _url = field_validator("source_url")(web_url)


class ExtractedContact(Contract):
    name: str | None = Field(default=None, max_length=150)
    role: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=254)


class ExtractedFirm(Contract):
    """Model-proposed facts must be checked against fetched evidence before use."""

    name: str | None = Field(default=None, max_length=250)
    source_type: Literal["firm_website", "directory", "news", "other", "unknown"] = "unknown"
    country: str | None = Field(default=None, max_length=100)
    size: int | None = Field(default=None, ge=1, le=100000)
    size_unit: Literal["attorneys", "people", "unknown"] = "unknown"
    practice_areas: list[str] = Field(default_factory=list, max_length=20)
    contacts: list[ExtractedContact] = Field(default_factory=list, max_length=50)
    evidence: list[Evidence] = Field(default_factory=list, max_length=200)
    recovery_diagnosis: str | None = Field(default=None, max_length=500)


class DiscoveryDecision(Contract):
    query: str = Field(default="", max_length=500)
    title: str = Field(default="", max_length=1000)
    snippet: str = Field(default="", max_length=2000)
    position: int | None = Field(default=None, ge=1, le=100)
    discovered_at: str | None = None
    url: str | None = None
    resolved_url: str | None = None
    source_kind: Literal["website", "directory", "unsupported"]
    score: int = Field(default=0, ge=-100, le=100)
    status: Literal["pending", "selected", "deferred", "rejected", "already_known", "duplicate", "qualified", "excluded", "needs_research", "failed"]
    reason: str = Field(max_length=2000)
    previous_run_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$")
    source_host: str | None = Field(default=None, max_length=253)
    source_access: Literal["permitted", "review_required", "restricted", "path_disallowed", "blocked"] | None = None
    directory_name: str | None = Field(default=None, max_length=100)
    terms_url: str | None = Field(default=None, max_length=2000)
    terms_reviewed_on: str | None = Field(default=None, max_length=10)

    @field_validator("url", "resolved_url", "terms_url")
    @classmethod
    def public_source(cls, value):
        if value is None:
            return None
        from .tools import validate_public_url
        return validate_public_url(value)


class DirectoryProfile(Contract):
    source_url: str
    retrieved_at: str
    contacts: list[ExtractedContact] = Field(default_factory=list, max_length=20)
    evidence: list[Evidence] = Field(default_factory=list, max_length=60)
    official_website: str | None = None
    research_status: Literal["needs_primary_research"] = "needs_primary_research"
    outreach_eligible: Literal[False] = False

    _source = field_validator("source_url")(web_url)

    @field_validator("official_website")
    @classmethod
    def public_website(cls, value):
        if value is not None:
            from .tools import validate_public_url
            return validate_public_url(value)
        return value


class ResearchRequest(Contract):
    mode: Literal["live", "fixture"] = "live"
    product: Literal["manage", "launch", "both"] = "manage"
    extraction_mode: Literal["model", "rules"] = "model"
    spend_policy: Literal["metered", "free_allowance_only"] = "metered"
    countries: list[str] = Field(default_factory=list, max_length=25)
    priority_countries: list[str] = Field(default_factory=list, max_length=25)
    target_segments: list[Literal["solo", "small", "mid_size"]] = Field(
        default_factory=lambda: ["solo", "small", "mid_size"], min_length=1, max_length=3
    )
    buyer_roles: list[str] = Field(default_factory=lambda: ["owner", "founder", "partner", "administrator", "operations"], min_length=1, max_length=20)
    size_min: int = Field(default=1, ge=1, le=1000)
    size_max: int = Field(default=50, ge=1, le=1000)
    small_firm_max: int = Field(default=10, ge=2, le=1000)
    size_unit: Literal["attorneys"] = "attorneys"
    query_terms: list[str] = Field(default_factory=list, max_length=10)
    discover_directories: bool = False
    seed_urls: list[str] = Field(default_factory=list, max_length=50)
    exclude_domains: list[str] = Field(default_factory=list, max_length=500)
    target_count: int = Field(default=25, ge=1, le=25)
    target_contacts: int | None = Field(default=None, ge=1, le=500)
    max_candidates: int = Field(default=50, ge=1, le=50)
    max_queries: int = Field(default=10, ge=1, le=10)
    max_pages_per_firm: int = Field(default=3, ge=1, le=12)
    max_llm_calls: int = Field(default=25, ge=0, le=50)
    max_verifications: int = Field(default=25, ge=0, le=50)
    deadline_seconds: int = Field(default=180, ge=10, le=900)
    request_timeout: int = Field(default=20, ge=1, le=60)
    max_input_tokens: int = Field(default=10000, ge=1000, le=20000)
    max_output_tokens: int = Field(default=1500, ge=256, le=4000)
    budget_usd: float = Field(default=1.0, ge=0, le=100)
    unit_costs: dict[str, float] = Field(default_factory=dict)
    enable_verification: bool = False
    research_freshness_days: int = Field(default=30, ge=0, le=365)
    verification_freshness_days: int = Field(default=7, ge=1, le=30)
    resume_run_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$")
    refresh_pending: bool = False
    fixture_pages: list[dict] = Field(default_factory=list, max_length=150, exclude=True)
    fixture_extractions: list[dict] = Field(default_factory=list, max_length=50, exclude=True)

    @field_validator("countries", "priority_countries", "query_terms", "exclude_domains", "buyer_roles")
    @classmethod
    def bounded_strings(cls, values):
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("Profile entries must contain at most 200 characters")
        return list(dict.fromkeys(value.strip() for value in values))

    @field_validator("seed_urls")
    @classmethod
    def valid_urls(cls, values):
        return [web_url(value) for value in values]

    @field_validator("unit_costs")
    @classmethod
    def valid_costs(cls, values):
        allowed = {"queries", "pages", "candidates", "llm_calls", "verifications"}
        if any(key not in allowed or not math.isfinite(value) or value < 0 for key, value in values.items()):
            raise ValueError("Unit costs must be finite, non-negative and use supported counter names")
        return values

    @model_validator(mode="after")
    def valid_profile(self):
        if self.size_min > self.size_max:
            raise ValueError("size_min cannot exceed size_max")
        if self.mode == "live" and (self.fixture_pages or self.fixture_extractions):
            raise ValueError("Fixture input is permitted only in explicit fixture mode")
        if self.mode == "fixture" and self.enable_verification:
            raise ValueError("Fixture mode cannot use live email verification")
        if self.spend_policy == "free_allowance_only" and self.extraction_mode != "rules":
            raise ValueError("Free-allowance-only research requires rules extraction; paid models are blocked")
        if self.extraction_mode == "model" and self.max_llm_calls == 0:
            raise ValueError("Model extraction requires a nonzero model-call allowance")
        if self.refresh_pending and not self.resume_run_id:
            raise ValueError("Pending enrichment requires a saved run to resume")
        return self


class ContactRecord(Contract):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    verification_status: str = "published_unverified"
    verified_at: str | None = None
    verification_provider: str | None = None
    association_status: Literal["sourced", "unconfirmed"] = "unconfirmed"
    buyer_role_match: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    inbox_type: Literal["named", "generic", "firm_unassigned", "unknown"] = "unknown"
    research_ready: bool = False
    readiness_reasons: list[str] = Field(default_factory=list)


class ProductAssessment(Contract):
    status: Literal["potential_fit", "confirmed_need", "no_current_fit", "unknown"] = "unknown"
    confidence: Literal["low", "medium", "high"] = "low"
    reasons: list[str] = Field(default_factory=list, max_length=10)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    hypothesis: str | None = Field(default=None, max_length=500)
    interest_status: Literal["unknown", "expressed"] = "unknown"


class PersonalizationBrief(Contract):
    product: Literal["manage", "launch"]
    email: str
    audience: Literal["named", "firm"]
    contact_name: str | None = None
    product_policy_version: str
    facts: list[Evidence] = Field(default_factory=list, max_length=20)
    hypothesis: str | None = None
    question: str
    research_ready: bool = False
    hold_reasons: list[str] = Field(default_factory=list)
    outreach_eligible: Literal[False] = False


class ProductRule(Contract):
    query_terms: list[str] = Field(min_length=1, max_length=8)
    buyer_roles: list[str] = Field(min_length=1, max_length=20)
    context: str = Field(min_length=1, max_length=500)
    question: str = Field(min_length=1, max_length=500)

    @field_validator("query_terms", "buyer_roles")
    @classmethod
    def bounded_entries(cls, values):
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("Product profile entries must contain at most 200 characters")
        return list(dict.fromkeys(value.strip() for value in values))


class QualificationPolicy(Contract):
    version: str = Field(min_length=1, max_length=80)
    products: dict[Literal["manage", "launch"], ProductRule]

    @model_validator(mode="after")
    def both_products(self):
        if set(self.products) != {"manage", "launch"}:
            raise ValueError("Both Manage and Launch definitions are required")
        return self

    @property
    def fingerprint(self):
        import hashlib
        import json
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


class FirmRecord(Contract):
    firm_id: str
    website: str
    domain: str
    source_type: Literal["firm_website", "directory", "news", "other", "unknown"] = "unknown"
    name: str | None = None
    country: str | None = None
    countries: list[str] = Field(default_factory=list, max_length=25)
    size: int | None = None
    size_unit: str = "unknown"
    size_basis: Literal["explicit_count", "published_roster", "unknown"] = "unknown"
    segment: Literal["solo", "small", "mid_size"] | None = None
    practice_areas: list[str] = Field(default_factory=list)
    contacts: list[ContactRecord] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    fit_status: Literal["qualified", "needs_research", "excluded"]
    fit_reasons: list[str]
    research_errors: list[str] = Field(default_factory=list)
    product: str
    researched_at: str
    provenance: Literal["live", "fixture"]
    outreach_eligible: bool = False
    qualification_policy_version: str | None = None
    qualification_policy_fingerprint: str | None = None
    product_assessments: dict[Literal["manage", "launch"], ProductAssessment] = Field(default_factory=dict)
    primary_product: Literal["manage", "launch", "both", "none"] = "none"
    personalization_briefs: list[PersonalizationBrief] = Field(default_factory=list)

    _url = field_validator("website")(web_url)
