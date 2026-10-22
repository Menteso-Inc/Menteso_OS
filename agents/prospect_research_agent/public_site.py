"""Autonomous, bounded public-page discovery and factual contact observations.

Uses lxml, the maintained HTML parser used by Scrapy's link extractor. Network
access remains in SourceTools so parser changes cannot bypass transport policy.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlsplit

from lxml import etree, html

from .qualification import GENERIC_INBOXES
from .rule_extraction import CONTACT_ROLE, _person_name

REVISION = "public-linked-pages-v2"
MAX_SITE_PAGES = 30
_INFORMATION = re.compile(r"/(?:contact(?:-us)?|about(?:-us)?|our-(?:team|firm|people)|team|people|attorneys?|lawyers?|partners?|staff|leadership|advisory-board|speakers?)(?:/|-|$)", re.I)
_EXCLUDE = re.compile(r"/(?:login|sign-in|sign-up|register|apply|application|nomination|submit|join|account|checkout|cart|privacy|terms|refund|copyright|cookie|news|blog|articles?|insights|wp-admin|api)(?:/|-|$)", re.I)
_LABEL = re.compile(r"^(?:(?:meet|our|the|all|view|browse)\s+)*(?:contact(?:\s+us)?|get in touch|about(?:\s+us)?|team|people|attorneys|lawyers|partners|staff|leadership|advisory board|speakers)$", re.I)
_UI_LABEL = re.compile(r'^(?:read|view|learn|explore|see|become|join|browse|show|meet|find|contact|get|sign|book|start|submit|request|follow)\b', re.I)
_PUBLIC_ROLE = re.compile(r'^(?:speaker|moderator|participant|panelist|panellist|member|board member|advisor|adviser|chair|president|CEO|COO|CTO)$', re.I)
_PEOPLE = './/h1|.//h2|.//h3|.//h4|.//strong|.//*[@itemprop="name"]|.//*[contains(concat(" ",normalize-space(@class)," ")," font-semibold ") or contains(concat(" ",normalize-space(@class)," ")," font-bold ")]'


def _document(page):
    source = page.get("document", "")
    if not source.strip(): return None
    try:
        document = html.fromstring(source, parser=html.HTMLParser(no_network=True, recover=True))
        # React streams a public Suspense segment in a temporary hidden holder,
        # then moves it to its placeholder with $RC. Recognize that exact pair;
        # never execute script or expose unrelated intentionally hidden content.
        for script in document.xpath('//script'):
            for placeholder, segment in re.findall(r'''\$RC\(\s*["'](B:\d+)["']\s*,\s*["'](S:\d+)["']\s*\)''', script.text or ''):
                if document.xpath('//template[@id=$identifier]', identifier=placeholder):
                    for holder in document.xpath('//div[@hidden and @id=$identifier]', identifier=segment):
                        holder.attrib.pop('hidden', None)
        for node in document.xpath('//*[@hidden or @style]'):
            if 'hidden' in node.attrib or re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!important)?\s*(?:;|$)', node.get('style', ''), re.I):
                if node.getparent() is not None: node.getparent().remove(node)
        return document
    except (etree.ParserError, ValueError): return None


def same_site(url, seed):
    target, origin = urlsplit(url), urlsplit(seed)
    return ((target.hostname or "").removeprefix("www.").lower() ==
            (origin.hostname or "").removeprefix("www.").lower()
            and (origin.scheme != "https" or target.scheme == "https"))


def information_links(page, seed):
    """Returned contact/people links by URL or label; no guessed routes."""
    from .tools import SourceError, normalize_source_url
    found = set()
    document = _document(page)
    if document is not None:
        for anchor in document.xpath('//a[@href]')[:1000]:
            if 'nofollow' in anchor.get('rel', '').lower().split(): continue
            try: link = normalize_source_url(urljoin(page['url'], anchor.get('href')))
            except (SourceError, ValueError): continue
            path = urlsplit(link).path
            label = ' '.join(anchor.text_content().split())
            card_text = ' '.join(' '.join(anchor.getparent().itertext()).split()) if anchor.getparent() is not None else ''
            named_profile = (_person_name(label) and not _UI_LABEL.search(label)
                             and len(card_text) <= 500 and CONTACT_ROLE.search(card_text))
            if (same_site(link, seed) and not _EXCLUDE.search(path)
                and (_INFORMATION.search(path) or _LABEL.fullmatch(label) or named_profile)):
                found.add(link)
    else:
        for link in page.get('links', []):
            if same_site(link, seed) and not _EXCLUDE.search(urlsplit(link).path) and _INFORMATION.search(urlsplit(link).path):
                found.add(link)
    def priority(link):
        path = urlsplit(link).path.lower()
        lane = 0 if "contact" in path else 1 if any(part in path for part in ("team", "people", "board", "speaker")) else 2
        return lane, path.count("/"), len(path), path
    return sorted(found, key=priority)[:100]


def public_observations(page, request):
    """Capture published facts without claiming product fit or email verification."""
    from .models import ExtractedFirm
    from .rule_extraction import extract_rules
    from .tools import EMAIL_PATTERN, _PublicHTML
    document = _document(page)
    if document is not None:
        # Rebuild the text/cards after discarding hidden HTML. This preserves the
        # existing extractor's email and evidence rules without trusting scripts.
        parser = _PublicHTML()
        parser.feed(html.tostring(document, encoding='unicode'))
        page = {**page, 'text': parser.text(), 'contact_blocks': parser.contact_blocks,
                'contact_headings': parser.contact_headings, 'footer_blocks': parser.footer_blocks,
                'structured_data': parser.structured_parts, 'headings': parser.headings[:5], 'titles': parser.titles[:3]}
    extracted = ExtractedFirm.model_validate(extract_rules([page], request))
    text = page.get("text", "")
    base = {"source_url": page["url"], "retrieved_at": page["retrieved_at"],
        "verification_status": "not_checked", "qualification_status": "needs_research", "outreach_eligible": False}
    records = []
    for contact in extracted.contacts:
        excerpt = next((item.excerpt for item in extracted.evidence if item.field == "email" and item.value == contact.email), "")
        records.append({**base, "name": contact.name, "role": contact.role, "email": contact.email,
            "firm": extracted.name, "website": page["url"], "country": extracted.country, "evidence_excerpt": excerpt})
    # Public external mailboxes are unassigned; proximity is not affiliation.
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group().lower()
        if any((row.get("email") or "").casefold() == email for row in records): continue
        records.append({**base, "email": email, "firm": None, "website": None,
            "evidence_excerpt": text[max(0, match.start()-100):match.end()+100]})
        if len(records) >= 100: break
    if document is None: return records
    # Carousel slides commonly have aria-hidden while their public cards remain
    # in the document. ARIA controls accessibility, not factual visibility.
    for node in document.xpath('//script|//style|//noscript|//template|//nav|//header|//footer|//*[@hidden]'):
        if node.getparent() is not None: node.getparent().remove(node)
    for anchor in document.xpath('//a[@href]'):
        href = anchor.get('href', '')
        if href.lower().startswith('mailto:'):
            address = unquote(href[7:].split('?', 1)[0])
            if EMAIL_PATTERN.fullmatch(address) and address not in anchor.text_content():
                anchor.text = (anchor.text or '') + ' ' + address
    headings = document.xpath(_PEOPLE)[:1000]
    for heading in headings:
        if len(records) >= 100: break
        name = ' '.join(heading.text_content().split())
        if not _person_name(name) or _UI_LABEL.search(name): continue
        container = heading.getparent()
        for _ in range(5):
            if container is None: break
            lines = [' '.join(chunk.split()) for chunk in container.itertext() if chunk.strip()]
            excerpt = '\n'.join(lines)
            nested_names = {value for node in container.xpath(_PEOPLE)
                            if _person_name(value := ' '.join(node.text_content().split())) and not _UI_LABEL.search(value)}
            roles = list(dict.fromkeys(line for line in lines if (CONTACT_ROLE.search(line) or _PUBLIC_ROLE.fullmatch(line)) and len(line) <= 150 and '@' not in line and len(line.split()) <= 14))
            if len(excerpt) <= 500 and nested_names == {name} and len(roles) == 1:
                role = roles[0]
                emails = list(dict.fromkeys(email.lower() for email in EMAIL_PATTERN.findall(excerpt)))
                email = emails[0] if len(emails) == 1 and emails[0].split('@', 1)[0] not in GENERIC_INBOXES else None
                if any(row.get('name') == name and row.get('role') == role for row in records): break
                existing = next((row for row in records if email and (row.get('email') or '').casefold() == email), None)
                row = {**base, 'name': name, 'role': role, 'email': email, 'firm': None, 'website': None,
                       'country': None, 'evidence_excerpt': excerpt}
                if existing is not None and not existing.get('name'): existing.update(row)
                elif existing is None: records.append(row)
                break
            container = container.getparent()
    return records
