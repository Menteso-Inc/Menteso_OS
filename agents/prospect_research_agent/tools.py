"""Bounded public research tools. Provider response bodies are never error messages.

API contracts: https://serpapi.com/search-api and
https://hunter.io/api-documentation/v2#email-verifier. Firm text is untrusted data.
DNS is resolved with a finite lifetime; the HTTP socket connects to that exact
validated address while retaining the original TLS SNI and certificate hostname.
No system proxy or automatic redirect machinery is used.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import os
import re
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from shared import config as _config  # Loads the project-root .env once.
from .discovery import domain, search_geographies, source_kind, score_candidate, select_candidates
from .directory_sources import DIRECTORY_HINT, access_decision, discovery_queries, load_directory_policy, profile_observation, terms_digest


USER_AGENT = "MentesoProspectResearch/1.0"
MAX_BODY_BYTES = 1_000_000
MAX_ROBOTS_BYTES = 64_000
MAX_REDIRECTS = 3
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}")
PAGE_HINTS = ("contact", "team", "about", "attorney", "lawyer", "people", "partner", "office", "practice")


class SourceError(RuntimeError):
    """An intentionally sanitized, actionable source/provider failure."""


def _public_ip(address) -> bool:
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if address.version == 6:
        embedded = address.ipv4_mapped or address.sixtofour
        if embedded and not _public_ip(embedded):
            return False
        if address.teredo and any(not _public_ip(part) for part in address.teredo):
            return False
    return True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_public_url(url: str, *, allow_query: bool = False) -> str:
    """Validate syntax only; DNS is checked immediately before every connection.

    Query strings are rejected on firm sources rather than guessing which query
    keys may contain credentials. Internal provider callers explicitly opt in.
    """
    if not isinstance(url, str) or len(url) > 2000 or re.search(r"[\x00-\x20\x7f\\]", url):
        raise SourceError("unsafe_url: malformed public URL")
    if re.search(r"[\x00-\x1f\x7f\\]", unquote(url)):
        raise SourceError("unsafe_url: encoded control character")
    try:
        parts = urlsplit(url)
        hostname = (parts.hostname or "").rstrip(".").lower().encode("idna").decode("ascii")
        port = parts.port
    except (ValueError, UnicodeError):
        raise SourceError("unsafe_url: malformed public URL") from None
    if parts.scheme not in {"http", "https"} or not hostname or parts.username is not None or parts.password is not None:
        raise SourceError("unsafe_url: public HTTP(S) URL required")
    if (parts.query or "?" in url) and not allow_query:
        raise SourceError("unsafe_url: query strings are not permitted on firm sources")
    if port is not None and port != (443 if parts.scheme == "https" else 80):
        raise SourceError("unsafe_url: nonstandard port")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal", ".invalid")):
        raise SourceError("unsafe_url: internal hostname")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname or not re.fullmatch(r"[a-z0-9.-]+", hostname):
            raise SourceError("unsafe_url: invalid public hostname") from None
    else:
        if not _public_ip(address):
            raise SourceError("unsafe_url: non-public IP address")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    return urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))


def normalize_source_url(url: str) -> str:
    """Strip only recognized tracking queries; preserve every network guard."""
    safe = validate_public_url(url, allow_query=True)
    parts = urlsplit(safe)
    if parts.query:
        try:
            pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=20)
        except ValueError:
            raise SourceError("unsafe_url: malformed source query") from None
        trackers = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "gclid", "fbclid", "msclkid"}
        if not pairs or any(key.casefold() not in trackers for key, _ in pairs):
            raise SourceError("unsafe_url: unsupported source query; no credential or arbitrary query is forwarded")
        safe = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    elif "?" in url:
        raise SourceError("unsafe_url: empty source query")
    return validate_public_url(safe)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


@dataclass
class HTTPResult:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, address: str, port: int, timeout: float, secure: bool):
        super().__init__(hostname, port=port, timeout=timeout)
        self.address = address
        self.secure = secure
        self.connection_deadline = time.monotonic() + timeout

    def connect(self):
        family = socket.AF_INET6 if ":" in self.address else socket.AF_INET
        raw_socket = socket.socket(family, socket.SOCK_STREAM)
        raw_socket.settimeout(self.timeout)
        try:
            raw_socket.connect((self.address, self.port))
            raw_socket.settimeout(max(0.001, self.connection_deadline - time.monotonic()))
            self.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=self.host) if self.secure else raw_socket
        except Exception:
            raw_socket.close()
            raise


class _PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.hidden_depth = 0
        self.anchors = []
        self._anchor = None
        self._json_ld = None
        self.structured_parts = []
        self.titles, self.headings = [], []
        self.contact_headings = []
        self._label_tag, self._label_text = None, ""
        self.contact_blocks = []
        self.footer_blocks = []
        self._elements = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not self.hidden_depth and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._json_ld = ""
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth += 1
        if self.hidden_depth:
            return
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            attributes = dict(attrs)
            marker = attributes.get("class", "") + " " + attributes.get("id", "")
            card = tag in {"article", "li"} or bool(re.search(r"(?:team[-_ ]member|staff[-_ ]member|attorney[-_ ]card|person[-_ ]card|vcard|profile[-_ ]card)", marker, re.I))
            self._elements.append((tag, len(self.parts), card))
        if tag in {"title", "h1", "h2", "h3"}:
            self._label_tag, self._label_text = tag, ""
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr", "section", "title"}:
            self.parts.append("\n")
        if tag == "a" and len(self.anchors) < 1000:
            href = dict(attrs).get("href")
            if href:
                if href not in self.links and len(self.links) < 500 and not href.lower().startswith(('mailto:', 'tel:', '#', 'javascript:')):
                    self.links.append(href)
                self._anchor = {"href": href, "label": ""}
                self.anchors.append(self._anchor)
                if href.lower().startswith("mailto:"):
                    self.parts.append("\n" + unquote(href[7:].split("?", 1)[0]) + "\n")

    def handle_endtag(self, tag):
        if not self.hidden_depth:
            for index in range(len(self._elements) - 1, -1, -1):
                if self._elements[index][0] == tag:
                    for element_tag, start, card in self._elements[index:]:
                        if element_tag == "footer" and len(self.footer_blocks) < 10:
                            footer = "\n".join(" ".join(line.split()) for line in "".join(self.parts[start:]).splitlines() if line.strip())
                            self.footer_blocks.append(footer[:10000])
                        if card and len(self.contact_blocks) < 100:
                            block = "\n".join(" ".join(line.split()) for line in "".join(self.parts[start:]).splitlines() if line.strip())
                            if 0 < len(block) <= 1000 and block not in self.contact_blocks:
                                self.contact_blocks.append(block)
                    del self._elements[index:]
                    break
        if tag == self._label_tag:
            value = " ".join(self._label_text.split())[:250]
            if value:
                if tag == "title": self.titles.append(value)
                else:
                    self.contact_headings.append(value)
                    if tag == "h1": self.headings.append(value)
            self._label_tag, self._label_text = None, ""
        if tag == "script" and self._json_ld is not None:
            try:
                payload = json.loads(self._json_ld)
                pending = [(payload, 0)]
                nodes = []
                while pending and len(nodes) < 100:
                    node, depth = pending.pop()
                    if depth > 8: continue
                    if isinstance(node, dict):
                        nodes.append(node)
                        pending.extend((value, depth + 1) for value in list(node.values())[:50] if isinstance(value, (dict, list)))
                    elif isinstance(node, list):
                        pending.extend((value, depth + 1) for value in node[:50])
                for node in nodes:
                    if not isinstance(node, dict) or len(self.structured_parts) >= 40: continue
                    types = node.get("@type", [])
                    if isinstance(types, str): types = [types]
                    if not isinstance(types, list) or not any(t in {"LegalService", "Attorney", "Organization", "LocalBusiness", "ProfessionalService", "Person"} for t in types if isinstance(t, str)): continue
                    if "Person" in types and not any(t in {"LegalService", "Attorney", "Organization", "LocalBusiness", "ProfessionalService"} for t in types):
                        if not all(isinstance(node.get(key), str) and node[key].strip() for key in ("name", "email", "jobTitle")):
                            continue
                    fields = {key:node[key] for key in ("@type", "name", "url", "address", "email", "telephone", "jobTitle") if key in node}
                    text = json.dumps(fields, ensure_ascii=False)
                    if len(text) <= 4000 and sum(len(part) for part in self.structured_parts) + len(text) <= 30000:
                        self.structured_parts.append(text)
            except (ValueError, TypeError, RecursionError):
                pass  # Malformed page metadata is not usable source evidence.
            self._json_ld = None
        if tag == "a":
            self._anchor = None
        if tag in {"script", "style", "noscript", "template"} and self.hidden_depth:
            self.hidden_depth -= 1
        if not self.hidden_depth and tag in {"p", "div", "li", "h1", "h2", "h3", "tr", "section"}:
            self.parts.append("\n")

    def handle_data(self, text):
        if self._json_ld is not None:
            self._json_ld += text[:max(0, 20000 - len(self._json_ld))]
        if not self.hidden_depth:
            self.parts.append(text + " ")
            if self._label_tag is not None:
                self._label_text += text[:250]
            if self._anchor is not None:
                self._anchor["label"] += text[:500]

    def text(self):
        visible = "\n".join(" ".join(line.split()) for line in "".join(self.parts).splitlines() if line.strip())
        metadata = "\nPublished business structured data:\n" + "\n".join(self.structured_parts) if self.structured_parts else ""
        return visible[:max(0, 60_000 - len(metadata))] + metadata


class SourceTools:
    """One instance per run: caches and limits persist across adjusted retries."""

    def __init__(self, request, budget):
        self.request = request
        self.budget = budget
        self.errors: list[str] = []
        self._query_count = 0
        self.discovery_records = []
        self.known_domains = {}
        self.incremental_read = False
        self._visited_pages = {}
        self._page_cache = {}
        self._firm_hosts: set[str] = set()
        self._robots: dict[str, RobotFileParser] = {}
        self._last_fetch: dict[str, float] = {}
        self._cache: dict[str, list[dict]] = {}
        self._published_emails: set[str] = set()
        self._request_deadline: float | None = None
        self.free_allowance_checks = []
        self.query_reserver = None
        self.directory_policy = load_directory_policy()
        self._directory_hosts = set()
        self._directory_terms_checked = set()
        self._directory_pages = {}
        self._source_holds = {}
        self.source_access_store = None
        self.directory_profiles = {}

    def _directory_host(self, url):
        rule = self.directory_policy.find(url)
        host = domain(url)
        return rule.host if rule else host if host in self._directory_hosts else None

    def _assert_source_available(self, url):
        host = self._directory_host(url)
        if not host:
            return
        hold = self._source_holds.get(host)
        reason = hold[0] if hold and (hold[1] is None or hold[1] > time.time()) else None
        if not reason and self.source_access_store is not None:
            reason = self.source_access_store.source_hold(host)
        if reason:
            raise SourceError("directory_blocked: " + reason)

    def _hold_directory(self, url, reason, retry_at=None):
        host = self._directory_host(url)
        if host:
            self._source_holds[host] = (reason, retry_at)
            if self.source_access_store is not None:
                self.source_access_store.hold_source(host, reason, retry_at)

    def _observe_directory_response(self, url, response):
        if not self._directory_host(url) or response.status not in {401, 403, 429, 451}:
            return
        retry_at = None
        reason = f"HTTP {response.status}; directory access stopped pending review"
        if response.status == 429:
            wait = 86400.0
            raw = response.headers.get("retry-after", "")
            try:
                wait = max(wait, float(raw)) if raw.isdigit() else max(wait, parsedate_to_datetime(raw).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
            # An extreme/malformed Retry-After requires review rather than
            # silently shortening the server's requested pause.
            retry_at = time.time() + wait if math.isfinite(wait) and wait <= 365 * 86400 else None
            reason = "HTTP 429; directory paused for at least 24 hours and the supplied Retry-After interval"
        self._hold_directory(url, reason, retry_at)

    def _check_directory_terms(self, url):
        """Check the reviewed policy page before profile collection, once per run."""
        if not self._directory_host(url):
            return None
        decision = access_decision(url, self.directory_policy)
        if decision["source_access"] != "permitted":
            raise SourceError("directory_" + decision["source_access"] + ": " + decision["reason"])
        self._assert_source_available(url)
        rule = self.directory_policy.find(url)
        if rule.host not in self._directory_terms_checked:
            try:
                self._confirm_directory_terms(rule)
            except SourceError:
                self._hold_directory(url, "Directory terms changed or could not be verified; review required")
                raise
            self._directory_terms_checked.add(rule.host)
        return rule

    def _confirm_directory_terms(self, rule):
        terms_url = rule.terms_url
        policy = self._robots_policy(terms_url)
        if not policy.can_fetch(USER_AGENT, terms_url):
            raise SourceError("directory_terms_unavailable: robots blocks the reviewed terms document")
        self._wait_for_source(terms_url, policy, rule.min_interval_seconds)
        response = self._fetch(terms_url, host=urlsplit(terms_url).hostname, policy=policy)
        self._last_fetch[_origin(response.url)] = time.monotonic()
        if response.status != 200:
            raise SourceError("directory_terms_unavailable: collection is held")
        if not any(kind in response.headers.get("content-type", "text/html") for kind in ("text/html", "text/plain")):
            raise SourceError("directory_terms_unavailable: unsupported terms content")
        document = response.body.decode("utf-8", errors="replace")
        parser = _PublicHTML()
        parser.feed(document)
        # Cover the full bounded document, beyond the ordinary 60k extraction.
        text = " ".join(parser.parts) if "html" in response.headers.get("content-type", "text/html") else document
        if terms_digest(text) != rule.reviewed_terms_sha256:
            raise SourceError("directory_terms_changed: review the current terms before further collection")

    def _timeout(self) -> float:
        self.budget.check()
        remaining = getattr(self.budget, "remaining_seconds", self.request.request_timeout)
        remaining = remaining() if callable(remaining) else remaining
        if self._request_deadline is not None:
            remaining = min(float(remaining), self._request_deadline - time.monotonic())
        if remaining <= 0:
            raise SourceError("network_timeout: source request deadline reached")
        return min(float(self.request.request_timeout), float(remaining))

    def _resolve_public_ips(self, hostname: str) -> list[str]:
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            try:
                import dns.exception
                import dns.resolver
            except ImportError:
                raise SourceError("dns_dependency_missing: install the declared dnspython dependency") from None
            resolver = dns.resolver.Resolver()
            addresses = []
            resolution_end = time.monotonic() + self._timeout()
            for record_type in ("A", "AAAA"):
                self.budget.check()
                lifetime = min(self._timeout(), resolution_end - time.monotonic())
                if lifetime <= 0:
                    raise SourceError("dns_timeout: source hostname lookup timed out")
                try:
                    answer = resolver.resolve(hostname, record_type, lifetime=lifetime)
                    addresses.extend(str(record) for record in answer)
                except dns.resolver.NoAnswer:
                    continue
                except dns.exception.DNSException:
                    raise SourceError("dns_failed: source hostname lookup failed") from None
        else:
            addresses = [str(literal)]
        if not addresses:
            raise SourceError("dns_failed: source has no public address")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                raise SourceError("unsafe_dns: source returned invalid addresses") from None
            if not _public_ip(parsed):
                raise SourceError("unsafe_dns: source resolves to a non-public destination")
        return list(dict.fromkeys(addresses))

    def _transport(self, url: str, address: str, headers: dict, max_bytes: int) -> HTTPResult:
        parts = urlsplit(url)
        port = 443 if parts.scheme == "https" else 80
        connection = _PinnedConnection(parts.hostname, address, port, self._timeout(), parts.scheme == "https")
        try:
            path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
            target = path + ("?" + parts.query if parts.query else "")
            connection.request("GET", target, headers=headers)
            if connection.sock:
                connection.sock.settimeout(self._timeout())
            response = connection.getresponse()
            response_headers = {key.lower(): value for key, value in response.getheaders()}
            if response_headers.get("content-encoding", "identity").lower() not in {"identity", ""}:
                raise SourceError("unsupported_encoding: compressed source response")
            chunks = []
            size = 0
            while True:
                timeout = self._timeout()
                if connection.sock:
                    connection.sock.settimeout(timeout)
                chunk = response.read(min(32_768, max_bytes + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise SourceError("source_too_large: response exceeds the body limit")
                chunks.append(chunk)
            return HTTPResult(response.status, response_headers, b"".join(chunks), url)
        finally:
            connection.close()

    def _fetch(self, url: str, *, host: str, provider: bool = False, headers: dict | None = None, max_bytes: int = MAX_BODY_BYTES, policy: RobotFileParser | None = None) -> HTTPResult:
        previous_deadline = self._request_deadline
        self._request_deadline = time.monotonic() + self._timeout()
        try:
            return self._fetch_redirects(url, host=host, provider=provider, headers=headers, max_bytes=max_bytes, policy=policy)
        finally:
            self._request_deadline = previous_deadline

    def _fetch_redirects(self, url: str, *, host: str, provider: bool, headers: dict | None, max_bytes: int, policy: RobotFileParser | None) -> HTTPResult:
        directory = self.directory_policy.find(url) if not provider else None
        profile_request = bool(directory and url != directory.terms_url and urlsplit(url).path != "/robots.txt")
        current = url
        request_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity", "Accept": "text/html,text/plain,application/json"}
        request_headers.update(headers or {})
        for redirect_index in range(MAX_REDIRECTS + 1):
            current = validate_public_url(current, allow_query=True) if provider else normalize_source_url(current)
            current_host = urlsplit(current).hostname
            same_site = current_host == host or (
                not provider and domain(current) == domain("https://" + host)
            )
            if not same_site:
                raise SourceError("blocked_redirect: destination leaves the approved host")
            if profile_request and access_decision(current, self.directory_policy)["source_access"] != "permitted":
                raise SourceError("blocked_redirect: destination leaves the reviewed directory profile paths")
            if urlsplit(url).scheme == "https" and urlsplit(current).scheme != "https":
                raise SourceError("blocked_redirect: insecure transport downgrade")
            if policy is not None and _origin(current) != _origin(url):
                # A protocol upgrade can have a different source policy.
                policy = self._robots_policy(current)
            if policy is not None and not policy.can_fetch(USER_AGENT, current):
                raise SourceError("robots_disallowed: redirect destination is blocked by source policy")
            if not provider:
                self._assert_source_available(current)
                if directory:
                    self._wait_for_source(current, policy, directory.min_interval_seconds)
            self.budget.check()
            addresses = self._resolve_public_ips(current_host)
            if not provider:
                self.budget.consume("pages")
            try:
                response = self._transport(current, addresses[0], request_headers, max_bytes)
            except (OSError, ValueError, http.client.HTTPException):
                # Never include an exception string: provider URLs contain keys.
                raise SourceError("network_failed: source request failed or timed out") from None
            if not provider:
                self._last_fetch[_origin(current)] = time.monotonic()
                self._observe_directory_response(current, response)
            if response.status not in {301, 302, 303, 307, 308}:
                return response
            if provider:
                raise SourceError("provider_redirect: provider redirects are not permitted")
            if redirect_index == MAX_REDIRECTS or not response.headers.get("location"):
                raise SourceError("blocked_redirect: redirect limit reached")
            current = urljoin(current, response.headers["location"])
        raise SourceError("blocked_redirect: redirect limit reached")

    def _provider_json(self, name: str, url: str, headers: dict | None = None) -> tuple[int, dict]:
        try:
            response = self._fetch(url, host=urlsplit(url).hostname, provider=True, headers=headers)
        except SourceError:
            raise SourceError(f"{name}_network_failed: provider request failed") from None
        if response.status == 202:
            return 202, {}
        if response.status != 200:
            category = "authentication_failed" if response.status == 401 else "limit_or_access_failed" if response.status in {402, 403, 429} else "request_failed"
            raise SourceError(f"{name}_{category}: HTTP {response.status}")
        try:
            payload = json.loads(response.body)
        except (ValueError, UnicodeError):
            raise SourceError(f"{name}_invalid_response: invalid JSON") from None
        if not isinstance(payload, dict) or payload.get("error") or payload.get("errors"):
            raise SourceError(f"{name}_provider_error: provider returned an error")
        return response.status, payload

    def discover(self, strategy: str = "standard") -> list[str]:
        """Discover public roots using SerpAPI; search geography is only a hint."""
        self.budget.check()
        if self.request.mode == "fixture":
            return []
        key = os.getenv("PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY", "").strip()
        if not key and os.getenv("PROSPECT_RESEARCH_AGENT_ALLOW_SHARED_SEARCH_KEY", "").lower() == "true":
            key = os.getenv("SERPAPI_API_KEY", "").strip()
        if not key:
            raise SourceError("PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY is not set; shared search requires explicit opt-in")
        from .qualification import load_policy
        policy = load_policy()
        product = getattr(self.request, "product", "manage")
        products = ("manage", "launch") if product == "both" else (product,)
        defaults = [policy.products[product].query_terms[index] for index in range(max(len(policy.products[product].query_terms) for product in products))
                    for product in products if index < len(policy.products[product].query_terms)]
        terms = self.request.query_terms or defaults
        countries = search_geographies(self.request)
        prioritised = bool(getattr(self.request, "priority_countries", []))
        pairs = ((term, country) for term in terms for country in countries) if prioritised else (
            (term, country) for country in countries for term in terms)
        queries = [" ".join(value for value in (term, country) if value) for term, country in pairs]
        if getattr(self.request, "discover_directories", False):
            queries = discovery_queries(queries, countries, self.directory_policy, round_robin=prioritised)
        if self.query_reserver:
            queries = self.query_reserver(queries, self.request.max_queries)
        if self._query_count >= self.request.max_queries:
            return []
        results: list[str] = []
        excluded = {domain(value if "://" in value else "https://" + value) for value in self.request.exclude_domains}
        for query in queries:
            if self._query_count >= self.request.max_queries or len(results) >= self.request.max_candidates:
                return results
            self._require_free_allowance("serpapi", key)
            self.budget.consume("queries")
            self._query_count += 1
            # Extraction recovery must not silently rewrite the campaign's
            # search query; restrictive extra words can eliminate firm sites.
            params = {"engine": "google", "q": query, "api_key": key, "output": "json", "hl": "en"}
            if os.getenv("PROSPECT_RESEARCH_AGENT_SERPAPI_ASYNC", "true").lower() == "true":
                params["async"] = "true"
            try:
                _, payload = self._provider_json("serpapi", "https://serpapi.com/search.json?" + urlencode(params))
            except SourceError as error:
                # Change from queued to synchronous retrieval on transient
                # failures, respecting the same run's search/cost ceiling.
                if not params.get("async") or not any(code in str(error) for code in ("network_failed", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")):
                    raise
                if self._query_count >= self.request.max_queries:
                    raise
                self._require_free_allowance("serpapi", key)
                self.budget.consume("queries")
                self._query_count += 1
                params.pop("async", None)
                _, payload = self._provider_json("serpapi", "https://serpapi.com/search.json?" + urlencode(params))
            metadata = payload.get("search_metadata", {})
            for _ in range(30):
                if not isinstance(metadata, dict) or metadata.get("status") not in {"Queued", "Processing"}:
                    break
                search_id = metadata.get("id", "")
                if not re.fullmatch(r"[a-fA-F0-9]{24}", str(search_id)):
                    raise SourceError("serpapi_incomplete_response: invalid pending search ID")
                time.sleep(min(2, self._timeout()))
                self.budget.check()
                # Archive polling retrieves the same search, not a new paid query.
                _, payload = self._provider_json("serpapi", f"https://serpapi.com/searches/{search_id}.json?" + urlencode({"api_key": key}))
                metadata = payload.get("search_metadata", {})
            if not isinstance(metadata, dict) or metadata.get("status") in {"Error", "Processing", "Queued"}:
                raise SourceError("serpapi_incomplete_response: search result is not completed")
            echoed_query = payload.get("search_parameters", {}).get("q")
            if echoed_query is not None and echoed_query != query:
                raise SourceError("serpapi_query_mismatch: response does not match the requested search")
            organic = payload.get("organic_results", [])
            if not isinstance(organic, list):
                raise SourceError("serpapi_invalid_response: organic results must be a list")
            # Retain bounded source context, then rank the entire result page.
            from shared.research_runtime import redact
            for position, result in enumerate(organic[:100], 1):
                if not isinstance(result, dict):
                    continue
                if not isinstance(result.get("link"), str) or key.lower() in result["link"].lower():
                    continue
                title = str(redact(str(result.get("title", ""))))[:1000].replace(key, "[redacted]")
                snippet = str(redact(str(result.get("snippet", ""))))[:2000].replace(key, "[redacted]")
                row = {"query": query, "title": title, "snippet": snippet, "position": position,
                       "discovered_at": utc_now(), "url": None, "source_kind": "unsupported",
                       "score": -100, "status": "rejected", "reason": "Unsafe or unsupported source URL"}
                self.discovery_records.append(row)
                try:
                    url = normalize_source_url(result["link"])
                except SourceError as exc:
                    row["reason"] = str(exc)
                    try:
                        row["source_host"] = urlsplit(result["link"]).hostname
                    except ValueError:
                        pass
                    continue
                row.update(url=url, source_kind=source_kind(url, title, snippet), score=score_candidate(url, title, snippet))
                if row["source_kind"] == "directory":
                    self._directory_hosts.add(domain(url))
                    row.update(access_decision(url, self.directory_policy))
                    try:
                        self._assert_source_available(url)
                    except SourceError as exc:
                        row.update(source_access="blocked", reason=str(exc))
                if urlsplit(url).path.lower().endswith((".pdf", "/pdf", ".doc", ".docx")):
                    row["reason"] = "Search result is a document, not a firm website"
                    continue
                row["status"] = "pending"
            results = select_candidates(self.discovery_records, self.request.max_candidates, self.known_domains, excluded)
        return results

    def _require_free_allowance(self, provider, key):
        """Read free account status immediately before an operation; fail closed."""
        if getattr(self.request, "spend_policy", "metered") != "free_allowance_only":
            return
        if provider == "serpapi":
            _, payload = self._provider_json("serpapi", "https://serpapi.com/account.json?" + urlencode({"api_key": key}))
            free = str(payload.get("plan_id", "")).casefold() == "free" or "free" in str(payload.get("plan_name", "")).casefold()
            free = free and payload.get("plan_monthly_price") == 0
            balance = payload.get("plan_searches_left")
        else:
            _, payload = self._provider_json("hunter", "https://api.hunter.io/v2/account", headers={"X-API-KEY": key})
            account = payload.get("data", {})
            free = str(account.get("plan_name", "")).casefold() in {"free", "free plan"}
            requests = account.get("requests", {})
            credit, unit = requests.get("credits"), requests.get("verifications")
            # The unified credit ledger is authoritative when present. Legacy
            # verification counters can still show capacity after credits run out.
            remaining = credit.get("remaining") if isinstance(credit, dict) else None
            balance = (remaining * 2 if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) else None) if credit is not None else (unit.get("remaining") if isinstance(unit, dict) else None)
        if not free or isinstance(balance, bool) or not isinstance(balance, (int, float)) or not math.isfinite(balance) or balance < 1:
            raise SourceError(f"{provider}_free_allowance_unavailable: free plan and remaining credits must be confirmed before work")
        self.free_allowance_checks.append({"provider": provider, "remaining_before_operation": balance, "checked_at": utc_now()})

    def _robots_policy(self, url: str) -> RobotFileParser:
        origin = _origin(url)
        if origin in self._robots:
            return self._robots[origin]
        response = self._fetch(urljoin(origin, "robots.txt"), host=urlsplit(url).hostname, max_bytes=MAX_ROBOTS_BYTES)
        policy = RobotFileParser()
        if response.status in {404, 410}:
            policy.parse([])
        elif response.status == 200:
            policy.parse(response.body.decode("utf-8", errors="replace").splitlines())
        else:
            raise SourceError(f"robots_unavailable: HTTP {response.status}; source is not fetched")
        self._robots[origin] = policy
        return policy

    def _wait_for_source(self, url, policy, minimum=0):
        delay = (policy.crawl_delay(USER_AGENT) or 0) if policy else 0
        rate = policy.request_rate(USER_AGENT) if policy else None
        if rate and rate.requests > 0:
            delay = max(delay, rate.seconds / rate.requests)
        origin = _origin(url)
        wait = max(0, max(delay, minimum) - (time.monotonic() - self._last_fetch.get(origin, 0)))
        if wait:
            if wait >= self._timeout():
                raise SourceError("robots_delay_exceeds_budget: source cannot be fetched within the deadline")
            time.sleep(wait)

    def _read_page(self, url: str, host: str) -> dict:
        directory = self._check_directory_terms(url)
        if directory and self._directory_pages.get(directory.host, 0) >= directory.max_profile_pages_per_run:
            raise SourceError("directory_page_limit: reviewed source page allowance reached")
        policy = self._robots_policy(url)
        if not policy.can_fetch(USER_AGENT, url):
            raise SourceError("robots_disallowed: public source policy blocks this page")
        self._wait_for_source(url, policy, directory.min_interval_seconds if directory else 0)
        if directory:
            self._directory_pages[directory.host] = self._directory_pages.get(directory.host, 0) + 1
        response = self._fetch(url, host=host, policy=policy)
        self._last_fetch[_origin(response.url)] = time.monotonic()
        if response.status != 200:
            raise SourceError(f"page_unavailable: HTTP {response.status}")
        if not policy.can_fetch(USER_AGENT, response.url):
            raise SourceError("robots_disallowed: redirected page is blocked by source policy")
        content_type = response.headers.get("content-type", "text/html")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise SourceError("unsupported_content: expected public HTML or plain text")
        charset = re.search(r"charset=([\w-]+)", content_type, re.I)
        if charset and charset.group(1).casefold() in {'iso-8859-1', 'windows-1252'} and re.search(br'charset=["\x27]?utf-8', response.body[:4000], re.I):
            charset = None  # Honour an explicit UTF-8 document declaration over a stale server default.
        try:
            document = response.body.decode(charset.group(1) if charset else "utf-8", errors="replace")
        except LookupError:
            document = response.body.decode("utf-8", errors="replace")
        parser = _PublicHTML()
        parser.feed(document)
        text = parser.text() if "text/html" in content_type else document[:60_000]
        if not directory and DIRECTORY_HINT.search(" ".join(parser.titles + parser.headings[:1])):
            self._directory_hosts.add(domain(url))
            raise SourceError("directory_review_required: newly identified directory; no contact details extracted before policy review")
        if directory and (response.headers.get("cf-mitigated") == "challenge" or re.search(
                r"verify (?:that )?you are (?:a )?human|checking your browser|access denied|^just a moment", text, re.I)):
            self._hold_directory(url, "Directory presented a challenge/access-denied page; review required")
            raise SourceError("directory_challenge: collection stopped; no bypass attempted")
        self._published_emails.update(email.lower() for email in EMAIL_PATTERN.findall(text))
        links = []
        for href in parser.links:
            try:
                link = normalize_source_url(urljoin(response.url, href))
            except SourceError:
                continue
            if domain(link) == domain(response.url) and link not in links:
                links.append(link)
        external = []
        for anchor in parser.anchors:
            label = " ".join(anchor["label"].lower().split())
            if not re.fullmatch(r"(?:(?:visit|view|go to|official|firm|company)\s+)*(?:web\s?site)(?:\s+(?:of|for)\s+.{1,100})?", label):
                continue
            try:
                link = normalize_source_url(urljoin(response.url, anchor["href"]))
            except SourceError:
                continue
            if domain(link) != domain(response.url) and source_kind(link) == "website":
                external.append({"url": link, "label": label})
        from .rule_extraction import _person_name
        profile_links=[]
        for anchor in parser.anchors:
            if not _person_name(' '.join(anchor['label'].split())):continue
            try:link=normalize_source_url(urljoin(response.url,anchor['href']))
            except SourceError:continue
            if domain(link)==domain(response.url) and link in links:profile_links.append(link)
        return {"url": response.url, "text": text, "retrieved_at": utc_now(), "links": links, "profile_links":list(dict.fromkeys(profile_links)),"website_links": external,
                "headings": parser.headings[:5], "titles": parser.titles[:3], "structured_data": parser.structured_parts,
                "contact_blocks": parser.contact_blocks, "contact_headings": parser.contact_headings[:100], "footer_blocks": parser.footer_blocks}

    def read_firm(self, url: str, strategy: str = "standard") -> list[dict]:
        """Read the root and bounded linked public information pages on one host."""
        self.budget.check()
        if self.request.mode == "fixture":
            return []
        url = validate_public_url(url)
        host = urlsplit(url).hostname
        if host not in self._firm_hosts and len(self._firm_hosts) >= self.request.max_candidates:
            raise SourceError("candidate_limit: maximum firm sources reached")
        self._firm_hosts.add(host)
        pages = self._page_cache.setdefault(host, [])
        visited = self._visited_pages.setdefault(host, set())
        if pages and any(page.get("text") for page in pages):
            return [dict(page) for page in pages]
        # One initial page in the agent workflow leaves room for targeted follow-up.
        target = 1 if self.incremental_read else self.request.max_pages_per_firm
        return self._read_selected(url, [], target, retry_failed=True)

    def _read_selected(self, url, missing_fields, target, retry_failed=False):
        host = urlsplit(url).hostname
        pages = self._page_cache.setdefault(host, [])
        visited = self._visited_pages.setdefault(host, set())
        if retry_failed and pages and not any(page.get("text") for page in pages):
            # An adjusted transient retry is allowed, still charged to the HTTP budget.
            visited.difference_update(page["url"] for page in pages if page.get("error"))
            pages.clear()
        while len(visited) < min(target, self.request.max_pages_per_firm):
            links = list(dict.fromkeys([url] + [link for page in pages for link in page.get("links", [])]))
            root_url = urljoin(url, "/")
            if any(field in missing_fields for field in ("name", "country", "organization_type")) and root_url not in visited:
                links.insert(0, root_url)
            profile_links={link for page in pages for link in page.get('profile_links',[])}
            links = [link for link in links if link not in visited and (link == url or urlsplit(link).path == "/" or link in profile_links or any(hint in urlsplit(link).path.lower() for hint in PAGE_HINTS))]
            if not links:
                break
            team_read = any(page.get("text") and any(hint in urlsplit(page["url"]).path.lower()
                            for hint in ("team", "attorney", "lawyer", "people", "about")) for page in pages)
            location_needed = any(item in missing_fields for item in ("country", "contacts"))
            hints = ("partner", "people", "attorney", "lawyer", "team", "about") if "buyer_roles" in missing_fields else ("contact", "office", "about") if location_needed and team_read else ("team", "attorney", "lawyer", "people", "about") if "size" in missing_fields else ("contact", "office", "about") if location_needed else ("practice", "about", "team", "contact")
            if not missing_fields: hints = ("contact", "about", "team", "office")
            def page_priority(link):
                path = urlsplit(link).path.lower()
                news = bool(re.search(r'/(?:news|firm-news|blog|press|insights|articles|cases?|results?)(?:/|-|$)', path))
                buyer = False
                if 'buyer_roles' in missing_fields:
                    from .qualification import _role_match
                    from .rule_extraction import _person_name
                    for page in pages:
                        lines=page.get('text','').splitlines()
                        for i,name in enumerate(lines[:-1]):
                            if _person_name(name) and _role_match(lines[i+1],self.request.buyer_roles):
                                slug=re.sub(r'[^a-z]','',name.casefold())
                                if slug and slug in re.sub(r'[^a-z]','',path.rsplit('/',2)[-2] if path.endswith('/') else path.rsplit('/',1)[-1]):buyer=True
                return (news, not buyer, 0 if link in profile_links and 'buyer_roles' in missing_fields else 1,
                    next((i for i, hint in enumerate(hints) if hint in path), len(hints)), path.count('/'), len(path))
            links.sort(key=page_priority)
            if "name" in missing_fields and root_url in links:
                links.remove(root_url); links.insert(0, root_url)
            page_url = links[0]
            visited.add(page_url)
            try:
                page = self._read_page(page_url, host)
            except SourceError as error:
                self.errors.append(str(error))
                page = {"url": page_url, "text": "", "retrieved_at": utc_now(), "error": str(error)}
            pages.append(page)
        return [dict(page) for page in pages]

    def read_more(self, url: str, missing_fields: list[str]) -> list[dict]:
        """Read a new linked page addressing missing facts, within the same firm cap."""
        self.budget.check()
        if self.request.mode == "fixture":
            return []
        url = validate_public_url(url)
        host = urlsplit(url).hostname
        if host not in self._firm_hosts:
            raise SourceError("unregistered_firm: initial research is required")
        visited = self._visited_pages.get(host, set())
        existing = {page["url"] for page in self._page_cache.get(host, []) if page.get("text")}
        pages = [dict(page) for page in self._page_cache.get(host, [])]
        while len(visited) < self.request.max_pages_per_firm:
            before = len(visited)
            pages = self._read_selected(url, missing_fields, before + 1)
            if len(visited) == before or any(page.get("text") and page["url"] not in existing for page in pages):
                break
        return pages

    def resolve_directory(self, url: str) -> str | None:
        """Follow one explicitly labelled website destination on a directory profile."""
        self.budget.check()
        if self.request.mode == "fixture":
            return None
        url = validate_public_url(url)
        if not self._directory_host(url):
            return None
        self._check_directory_terms(url)
        page = self._read_page(url, urlsplit(url).hostname)
        targets = {domain(item["url"]): item["url"] for item in page.get("website_links", [])}
        resolved = next(iter(targets.values())) if len(targets) == 1 else None
        self.directory_profiles[url] = profile_observation(page, resolved, self.directory_policy.find(url).host)
        if len(targets) != 1:
            return None
        return resolved

    def verify_email(self, email: str) -> dict:
        """Check only an already published contact; mailbox status grants no consent."""
        self.budget.check()
        email = str(email).strip().lower()
        base = {"status": "published_unverified", "verified_at": None, "provider": None}
        if self.request.mode == "fixture" or not self.request.enable_verification:
            return base
        if not EMAIL_PATTERN.fullmatch(email) or email not in self._published_emails:
            return {**base, "error": "verification_blocked: email has no retrieved public source"}
        key = os.getenv("PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY", "").strip()
        if not key:
            return {**base, "error": "PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY is not set"}
        url = "https://api.hunter.io/v2/email-verifier?" + urlencode({"email": email})
        for poll in range(3):
            try:
                self._require_free_allowance("hunter", key)
                self.budget.consume("verifications")
                status, payload = self._provider_json("hunter", url, headers={"X-API-KEY": key})
            except SourceError as error:
                self.errors.append(str(error))
                return {**base, "provider": "hunter", "error": str(error)}
            if status == 202:
                if poll < 2:
                    time.sleep(min(1.0, self._timeout()))
                    self.budget.check()
                continue
            record = payload.get("data", {})
            if not isinstance(record, dict):
                return {**base, "provider": "hunter", "error": "hunter_invalid_response: missing verification data"}
            raw_status = record.get("status", "unknown")
            mapped = {"valid": "valid", "invalid": "invalid", "accept_all": "catch_all", "unknown": "unknown", "disposable": "disposable", "webmail": "webmail"}.get(raw_status, "unknown")
            if record.get("accept_all") is True:
                mapped = "catch_all"
            verification = record.get("verification") or {}
            verified_at = verification.get("date") if isinstance(verification, dict) else None
            # Do not substitute request time for a provider's cached or absent date.
            try:
                if not isinstance(verified_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified_at):
                    raise ValueError("Invalid verification date")
                date.fromisoformat(verified_at)
            except ValueError:
                verified_at = None
            return {"status": mapped, "verified_at": verified_at, "provider": "hunter"}
        return {"status": "pending", "verified_at": None, "provider": "hunter"}

    def get_langchain_tools(self):
        """Return actual lazy StructuredTool wrappers without importing CrewAI."""
        try:
            from langchain_core.tools import StructuredTool
        except ImportError:
            raise SourceError("langchain_dependency_missing: install the declared LangChain dependency") from None
        return {
            "discover": StructuredTool.from_function(self.discover, name="discover_public_firms"),
            "read_firm": StructuredTool.from_function(self.read_firm, name="read_public_firm"),
            "read_more": StructuredTool.from_function(self.read_more, name="read_missing_firm_facts"),
            "resolve_directory": StructuredTool.from_function(self.resolve_directory, name="resolve_directory_website"),
            "verify_email": StructuredTool.from_function(self.verify_email, name="verify_published_email"),
        }
