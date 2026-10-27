"""Bounded, declarative readers for reviewed HTML directories and JSON feeds.

Recipes are configuration, never executable selectors, scripts or model output.
Public visibility and a working parser do not grant collection rights.
"""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FIELDS = {"name", "role", "email", "firm", "website", "country"}
SELECTOR = re.compile(r"(?:[a-z][a-z0-9-]*)?(?:#[a-zA-Z_][\w-]*)?(?:\.[a-zA-Z_][\w-]*)*")
PATH = re.compile(r"[a-zA-Z_][\w-]*(?:\.[a-zA-Z_][\w-]*){0,7}")
QUERY_KEYS = {"page", "offset", "limit", "cursor", "after", "before", "per_page", "page_size"}


class CollectionRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    format: str = Field(default="html", pattern=r"^(html|json)$")
    revision: str = Field(default="1", min_length=1, max_length=40)
    record_selector: str | None = None
    field_selectors: dict[str, str] = Field(default_factory=dict, max_length=6)
    profile_link_selector: str | None = None
    next_selector: str | None = None
    records_path: str = ""
    field_paths: dict[str, str] = Field(default_factory=dict, max_length=6)
    next_path: str | None = None
    query_keys: list[str] = Field(default_factory=list, max_length=8)
    auth_env: str | None = Field(default=None, pattern=r"^PROSPECT_RESEARCH_AGENT_SOURCE_[A-Z0-9_]+_(TOKEN|KEY)$")
    auth_header: str = Field(default="Authorization", pattern=r"^(Authorization|X-API-Key)$")

    @field_validator("record_selector", "profile_link_selector", "next_selector")
    @classmethod
    def selector(cls, value):
        if value is not None and (not value or len(value) > 120 or not all(
                part and SELECTOR.fullmatch(part) for part in value.split(" ")) or len(value.split()) > 4):
            raise ValueError("Use up to four descendant tag, #id or .class selectors")
        return value

    @field_validator("field_selectors")
    @classmethod
    def selectors(cls, values):
        if not values.keys() <= FIELDS:
            raise ValueError("Unsupported contact field")
        for value in values.values():
            cls.selector(value)
        return values

    @field_validator("records_path", "next_path")
    @classmethod
    def path(cls, value):
        if value not in {None, ""} and (len(value) > 160 or not PATH.fullmatch(value)):
            raise ValueError("Use a bounded dotted JSON object path")
        return value

    @field_validator("field_paths")
    @classmethod
    def paths(cls, values):
        if not values.keys() <= FIELDS:
            raise ValueError("Unsupported contact field")
        for value in values.values():
            if not value:
                raise ValueError("A mapped field needs a JSON path")
            cls.path(value)
        return values

    @field_validator("query_keys")
    @classmethod
    def queries(cls, values):
        if not set(values) <= QUERY_KEYS:
            raise ValueError("Only reviewed pagination query keys are supported; credentials belong in .env")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def distinct_formats(self):
        if self.format == "json":
            if not self.field_paths or not {"name", "email"}.intersection(self.field_paths):
                raise ValueError("JSON feeds require an explicit contact field mapping")
            if any((self.record_selector, self.field_selectors, self.profile_link_selector, self.next_selector)):
                raise ValueError("HTML selectors cannot be applied to a JSON feed")
        elif self.field_paths or self.records_path or self.next_path or self.query_keys or self.auth_env:
            raise ValueError("JSON paths and pagination query keys require a JSON feed")
        if self.field_selectors and not self.record_selector:
            raise ValueError("HTML field mappings need a record container")
        return self


class CollectionRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_prefix: str = Field(min_length=2, max_length=200, pattern=r"^/[A-Za-z0-9_./-]+$")
    reader: CollectionRecipe

    @field_validator("path_prefix")
    @classmethod
    def path(cls, value):
        if any(part in {".", "..", ""} for part in value.strip("/").split("/")):
            raise ValueError("Use a bounded collection path")
        return value.rstrip("/")


class _Node:
    def __init__(self, tag="root", attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children, self.content = [], []

    def text(self):
        return " ".join(" ".join(part.text() if isinstance(part, _Node) else part
                                for part in self.content).split())


class _Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack, self.nodes = [self.root], []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if self.hidden:
            return
        if len(self.nodes) >= 10000 or len(self.stack) >= 80:
            raise ValueError("layout_too_complex: bounded HTML reader stopped")
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        self.stack[-1].content.append(node)
        self.nodes.append(node)
        if tag == "a" and node.attrs.get("href", "").lower().startswith("mailto:"):
            from urllib.parse import unquote
            node.content.append(unquote(node.attrs["href"][7:].split("?", 1)[0]))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden:
            if tag in {"script", "style", "noscript", "template"}:
                self.hidden -= 1
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.hidden:
            self.stack[-1].content.append(data)


def _matches(node, selector):
    tag = re.match(r"^[a-z][a-z0-9-]*", selector)
    identity = re.search(r"#([\w-]+)", selector)
    classes = re.findall(r"\.([\w-]+)", selector)
    return ((not tag or node.tag == tag[0]) and
            (not identity or node.attrs.get("id") == identity[1]) and
            set(classes) <= set(node.attrs.get("class", "").split()))


def _select(nodes, selector, root=None):
    if not selector:
        return []
    parts, found = selector.split(), []
    for node in nodes:
        if root is not None:
            parent = node
            while parent is not None and parent is not root:
                parent = parent.parent
            if parent is None:
                continue
        if not _matches(node, parts[-1]):
            continue
        ancestor, index = node.parent, len(parts) - 2
        while ancestor is not None and index >= 0:
            if _matches(ancestor, parts[index]):
                index -= 1
            if ancestor is root:
                break
            ancestor = ancestor.parent
        if index < 0:
            found.append(node)
    return found


def _get(payload, path):
    for key in path.split(".") if path else []:
        if not isinstance(payload, dict):
            return None
        payload = payload.get(key)
    return payload


def _contains(payload, path):
    for key in path.split("."):
        if not isinstance(payload, dict) or key not in payload:
            return False
        payload = payload[key]
    return True


def _record(values, source, retrieved, excerpt, *, evidence_path=None):
    from .tools import EMAIL_PATTERN, validate_public_url
    clean = {}
    for key, value in values.items():
        if not isinstance(value, str) or not value.strip():
            continue
        value = " ".join(value.split())
        if len(value) > (254 if key == "email" else 250):
            continue
        if key == "email":
            if not EMAIL_PATTERN.fullmatch(value):
                continue
            value = value.lower()
        if key == "website":
            try:
                value = validate_public_url(value)
            except ValueError:
                continue
            except RuntimeError:
                continue
        clean[key] = value
    if not (clean.get("name") or clean.get("email")):
        return None
    return {**clean, "source_url": source, "retrieved_at": retrieved,
            "evidence_excerpt": excerpt[:500], "evidence_path": evidence_path,
            "verification_status": "not_checked", "qualification_status": "needs_research",
            "outreach_eligible": False}


def extract_collection(document, page, recipe, directory_host=None):
    """Returns source observations and explicit navigation; never qualified leads.

    Repeated records remain bounded to 100 per page; navigation is validated by
    SourceTools before any request. Missing/mismatched layouts stop, not guess.
    """
    records, profiles, next_urls = [], [], []
    if recipe.format == "json":
        payload = json.loads(document)
        items = _get(payload, recipe.records_path)
        if not isinstance(items, list):
            raise ValueError("layout_changed: expected the reviewed JSON record array")
        if len(items) > 100:
            raise ValueError("page_too_large: request at most 100 records per API page")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("layout_changed: JSON records must be objects")
            values = {field: _get(item, path) for field, path in recipe.field_paths.items()}
            excerpt = json.dumps({key: value for key, value in values.items() if isinstance(value, str)}, ensure_ascii=False)
            record = _record(values, page["url"], page["retrieved_at"], excerpt,
                             evidence_path=f"{recipe.records_path or '$'}[{index}]")
            if record:
                records.append(record)
        if recipe.next_path:
            if not _contains(payload, recipe.next_path):
                raise ValueError("layout_changed: reviewed next-page field is missing")
            value = _get(payload, recipe.next_path)
            if value is not None and value != "":
                if not isinstance(value, str):
                    raise ValueError("layout_changed: next page must be a URL, not a guessed cursor")
                next_urls.append(urljoin(page["url"], value))
    else:
        dom = _Document()
        dom.feed(document)
        containers = _select(dom.nodes, recipe.record_selector)
        if recipe.record_selector and not containers:
            raise ValueError("layout_changed: reviewed record containers were not found")
        if len(containers) > 100:
            raise ValueError("page_too_large: HTML contains more than 100 reviewed records")
        for node in containers:
            values = {}
            excerpt = node.text()
            for field, selector in recipe.field_selectors.items():
                matches = _select(dom.nodes, selector, root=node)
                if len(matches) == 1:
                    value = matches[0].attrs.get("href", "") if field == "website" else matches[0].text()
                    if field == "email":
                        from .tools import EMAIL_PATTERN
                        emails = list(dict.fromkeys(EMAIL_PATTERN.findall(value)))
                        value = emails[0] if len(emails) == 1 else ""
                    values[field] = urljoin(page["url"], value) if field == "website" and value else value
            # A long card cannot provide a compact, unambiguous contact excerpt.
            if len(excerpt) <= 500:
                record = _record(values, page["url"], page["retrieved_at"], excerpt)
                if record:
                    records.append(record)
        for node in _select(dom.nodes, recipe.profile_link_selector):
            if node.tag == "a" and node.attrs.get("href"):
                profiles.append(urljoin(page["url"], node.attrs["href"]))
        for node in _select(dom.nodes, recipe.next_selector):
            if node.tag == "a" and node.attrs.get("href"):
                next_urls.append(urljoin(page["url"], node.attrs["href"]))
    next_urls = list(dict.fromkeys(next_urls))
    if len(next_urls) > 1:
        raise ValueError("layout_changed: multiple next-page destinations; navigation held")
    if not records and not profiles and not (recipe.format == "json" and items == []):
        raise ValueError("layout_changed: no usable records or reviewed profile links")
    if directory_host:
        records = [row for row in records if not row.get("email") or not (
            row["email"].rsplit("@", 1)[-1] == directory_host or row["email"].rsplit("@", 1)[-1].endswith("." + directory_host))]
    return {"records": records, "profile_urls": list(dict.fromkeys(profiles))[:100],
            "next_url": next_urls[0] if next_urls else None, "adapter": recipe.format + ":" + recipe.revision}


def recipe_fingerprint(rule):
    payload = rule.model_dump(mode="json") if rule is not None else {"source": "public_firm_html"}
    return hashlib.sha256(json.dumps({"reader": "source-import-1", "rule": payload}, sort_keys=True).encode()).hexdigest()
