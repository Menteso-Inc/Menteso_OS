"""Conservative, zero-model extraction. Missing evidence remains missing."""
from __future__ import annotations

import json
import re
from html import unescape
from functools import lru_cache
from urllib.parse import urlsplit

from .models import Evidence, ExtractedContact, ExtractedFirm
from .qualification import GENERIC_INBOXES, LAUNCH_NEED, MANAGE_NEED, NEW_FIRM, WEBSITE_PROJECT

COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
COUNT_RE = re.compile(r"\b(?:our (?:firm|team|practice) (?:has|includes|comprises)|we (?:have|are a team of)|team of)\s+(\d{1,3}|" + "|".join(COUNTS) + r")\s+(?:(?:experienced|senior|qualified|practicing|full-time|skilled|licensed|dedicated|award-winning|personal injury)\s+){0,2}(?:attorneys|lawyers|advocates)\b(?!\s+(?:and|or)\s+(?:staff|other professionals|tax professionals))|\b(?:sole attorney|sole lawyer|solo attorney|solo lawyer)\b", re.I)
PRACTICES = re.compile(r"\b(?:litigation|immigration|intellectual property|family law|business law|corporate law|employment law|real estate|estate planning|criminal defense|criminal law|personal injury|tax law)\b", re.I)
FIRM_WORDS = re.compile(r"\b(?:law firm|law offices?|firm of attorneys|advocates|sole attorney|sole lawyer|solo attorney|solo lawyer)\b", re.I)
NAMED_CONTACT = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,3}) is our ((?:(?:Managing|Founding|Senior) )?Partner|Founder|Owner|Operations Manager)\b[^.!?\n]{0,100}?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63})")
AMBIGUOUS_COUNTRY_NAMES = frozenset({"jersey", "georgia", "jordan", "chad", "guinea", "congo"})
LOCATION_PREFIX = re.compile(r"\b(?:our (?:law firm|firm|practice)(?: is)?(?: (?:located|based))? in|we are (?:located|based) in|country\s*:|(?:office(?: location)?|business address|address)\s*:[^.!?\n]{0,80})\s*$", re.I)
CONTACT_ROLE = re.compile(r"\b(?:partner|founder|owner|administrator|operations|principal|director|attorney|lawyer|associate|solicitor|counsel|advocate)\b", re.I)
NON_PERSON_WORDS = re.compile(r"\b(?:law|legal|firm|team|practice|contact|services|areas|biography|clients|education|admissions|experience|news|insights|phone|email|fax|office|university|government|lawyers|attorneys|partners|LLP|LLC|Ltd|Inc|PLC|profile)\b", re.I)


@lru_cache(maxsize=1)
def _country_patterns():
    import pycountry
    return [(country,label,re.compile(r'(?<!\w)'+re.escape(label)+r'(?!\w)',re.I))
            for country in pycountry.countries for label in dict.fromkeys(getattr(country,key,'') for key in ('name','official_name','common_name')) if label]


def _person_name(value):
    if not isinstance(value, str) or not 3 <= len(value) <= 150:
        return False
    words = value.split()
    return (2 <= len(words) <= 6 and not CONTACT_ROLE.search(value) and not NON_PERSON_WORDS.search(value)
            and all((word[0].isupper() or i > 0 and word in {'von','van','de','der','den','del','da','di','du','la'})
                    and all(char.isalpha() or char in ".'-’" for char in word) for i,word in enumerate(words)))


def extract_rules(pages, request, budget=None, strategy="standard", memory=None):
    """Read factual syntax only; never invoke inference, network or a paid provider."""
    import pycountry
    if budget is not None:
        budget.check()
    evidence, contacts, names, countries, counts, areas = [], [], [], [], [], []
    preferred_names = []
    canonical_names = []
    rosters = []
    legal_metadata = False
    for page in pages:
        text = str(page.get("text", ""))
        url = page["url"]
        def add(field, value, excerpt):
            if field in {"practice_area", "name", "country", "size"} and any(item.field == field and item.value.casefold() == str(value).casefold() for item in evidence):
                return
            item = Evidence(field=field, value=str(value), source_url=url, excerpt=excerpt[:500], retrieved_at=page.get("retrieved_at"))
            if item not in evidence and len(evidence) < 200:
                evidence.append(item)
        def named_contact(name, role, email, excerpt):
            from .tools import EMAIL_PATTERN
            host = (urlsplit(url).hostname or "").removeprefix("www.").casefold()
            values = (name, email) if role is None else (name, role, email)
            if (not _person_name(name) or (role is not None and (not isinstance(role, str) or not 0 < len(role) <= 150))
                or not isinstance(email, str) or not EMAIL_PATTERN.fullmatch(email)
                or email.rsplit("@", 1)[-1].casefold() != host
                or email.split("@", 1)[0].casefold() in GENERIC_INBOXES
                or any(email in footer for footer in page.get("footer_blocks", []) if isinstance(footer, str))
                or len(excerpt) > 500 or not all(value in excerpt for value in values)
                or excerpt not in text):
                return
            for field, value in (("contact_name", name), ("contact_role", role), ("email", email)):
                if value is not None: add(field, value, excerpt)
            existing = next((item for item in contacts if item.email.casefold() == email.casefold()), None)
            if existing is not None:
                # A detail page can add a sourced association to a root-page inbox.
                if not existing.name:
                    existing.name, existing.role = name, role
                elif existing.name == name and existing.role is None and role is not None:
                    existing.role = role
            elif len(contacts) < 50:
                contacts.append(ExtractedContact(name=name, role=role, email=email))
            else:
                unassigned = next((item for item in reversed(contacts) if not item.name), None)
                if unassigned is not None:
                    contacts.remove(unassigned)
                    contacts.append(ExtractedContact(name=name, role=role, email=email))
        # Legal structured data can identify the firm; unrelated publishers cannot.
        for raw in page.get("structured_data", []):
            try:
                node = json.loads(raw)
            except (TypeError, ValueError):
                continue
            node_url = node.get("url")
            if node_url and (urlsplit(str(node_url)).hostname or "").removeprefix("www.") != (urlsplit(url).hostname or "").removeprefix("www."):
                continue
            kinds = node.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if not isinstance(kinds, list):
                continue
            if "Person" in kinds:
                named_contact(node.get("name"), node.get("jobTitle"), node.get("email"), raw)
                continue
            if not any(kind in {"LegalService", "Attorney", "Organization", "LocalBusiness", "ProfessionalService"} for kind in kinds):
                continue
            name = unescape(node.get("name", "")) if isinstance(node.get("name"), str) else None
            root_entity = not node_url or urlsplit(str(node_url)).path in {"", "/", "/index.html", "/index.php"}
            if (isinstance(name, str) and 0 < len(name) <= 250 and name in text
                and root_entity and not PRACTICES.fullmatch(name)):
                names.append(name); add("name", name, name)
                if node_url: canonical_names.append((not urlsplit(url).path.rstrip('/'),name))
                legal_metadata = True
                for kind in kinds:
                    if kind in {"LegalService", "Attorney"}:
                        position = raw.find(kind)
                        add("organization_type", kind, raw[max(0, position - 20):position + len(kind) + 20])
            address = node.get("address", {})
            addresses=address if isinstance(address,list) else [address]
            for address in addresses[:20]:
                raw_country=address.get('addressCountry') if isinstance(address,dict) else None
                if isinstance(raw_country,dict):raw_country=raw_country.get('name')
                if not isinstance(raw_country,str) or len(raw_country)>100:continue
                try:
                    value = pycountry.countries.lookup(raw_country).name
                except LookupError:
                    continue
                match = re.search(r'"addressCountry"\s*:\s*"' + re.escape(raw_country) + '"', raw)
                if match:
                    countries.append(value); add("country", raw_country, match.group())
        for line in page.get('titles', []):
            for part in re.split(r'\s*[|–—]\s*|\s+-\s+', line):
                if re.search(r'\b(?:LLP|LLC|PLLC|P\.?C\.?|Solicitors)\s*$', part) and part in text and len(part.split()) <= 12 and not re.match(r'(?:about|contact|our|meet|home|team|careers|practice|news)\b',part,re.I):
                    preferred_names.append(part); add('name', part, part)
        if not names:
            for line in [*page.get("titles", []), *page.get("headings", [])]:
                parts = re.split(r"\s*[|–—]\s*|\s+-\s+", line)
                for part in reversed(parts) if len(parts) > 1 else parts:
                    if (2 <= len(part) <= 150 and len(part.split()) <= 10
                        and not re.match(r"(?:best|top|experienced|find|contact|our|about|welcome|home)\b", part, re.I)
                        and not PRACTICES.fullmatch(part)
                        and (re.search(r"\b(?:law|legal|attorneys|solicitors|LLP)\b", part, re.I) or len(parts) > 1 and len(part.split()) >= 2)
                        and part in text):
                        names.append(part); add("name", part, part); break
                if names: break
        for match in COUNT_RE.finditer(text):
            prefix = text[max(0, match.start() - 100):match.start()]
            if re.search(r'\b(?:client|previous|formerly|previously|managed|led|represented|advised)\b[^.!?\n]*$', prefix, re.I):
                continue
            raw = (match.group(1) or "").casefold()
            count = int(raw) if raw.isdigit() else COUNTS.get(raw, 1)
            counts.append(count); add("size", count, match.group())
        from .primary_facts import attorney_roster, postal_country
        roster = attorney_roster(page)
        if roster:
            rosters.append(roster['count']); add('size', roster['count'], roster['excerpt'])
        for code, excerpt in postal_country(page):
            countries.append(pycountry.countries.get(alpha_2=code).name)
            add('country', code, excerpt)
        for match in PRACTICES.finditer(text):
            areas.append(match.group()); add("practice_area", match.group(), match.group())
        # Country names are literal; do not infer from a city, TLD or phone code.
        folded_text=text.casefold()
        for country,label,pattern in _country_patterns():
                if label.casefold() not in folded_text:continue
                for match in pattern.finditer(text):
                    location_context = text[max(0, match.start() - 100):match.start()]
                    ambiguous = label.casefold() in AMBIGUOUS_COUNTRY_NAMES
                    typed_country = bool(re.search(r"\bcountry\s*:\s*$", location_context, re.I))
                    prefix = LOCATION_PREFIX.search(location_context)
                    address_line = (urlsplit(url).path.rstrip('/').casefold() in {'/contact', '/contact-us', '/offices'}
                                    and label.casefold() == text[match.start():match.end()].casefold()
                                    and text[max(0,match.start()-1):match.start()] == '\n'
                                    and text[match.end():match.end()+1] in {'\n', ''}
                                    and bool(re.search(r'\d', location_context)))
                    if (prefix or address_line) and (not ambiguous or typed_country):
                        start = match.start() - len(location_context) + prefix.start() if prefix else max(0, match.start()-100)
                        countries.append(country.name); add("country", country.name, text[start:match.end()])
                        break
        from .tools import EMAIL_PATTERN
        # Explicit card boundaries prevent names being associated with a footer
        # or an adjacent person's email. Arbitrary nearby page text is not used.
        for block in page.get("contact_blocks", []):
            if not isinstance(block, str) or len(block) > 500 or block not in text:
                continue
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            block_names = [line for line in lines if _person_name(line)]
            roles = [line for line in lines if CONTACT_ROLE.search(line) and len(line) <= 100 and not _person_name(line)]
            emails = list(dict.fromkeys(EMAIL_PATTERN.findall(block)))
            if len(block_names) == len(emails) == 1 and len(roles) <= 1:
                named_contact(block_names[0], roles[0] if roles else None, emails[0], block)
        from .primary_facts import directory_entries
        for entry in directory_entries(page):
            named_contact(entry['name'],entry['role'],entry['email'],entry['excerpt'])
        from .primary_facts import profile_contact
        profile=profile_contact(page)
        if profile and profile['email'].split('@',1)[0].casefold() not in GENERIC_INBOXES:
            for field,key,quote in [('contact_name','name','header'),('contact_role','role','header'),('email','email','contact')]:
                add(field,profile[key],profile[quote])
            existing=next((c for c in contacts if c.email.casefold()==profile['email'].casefold()),None)
            if existing:
                existing.name,existing.role=profile['name'],profile['role']
            elif len(contacts)<50:
                contacts.append(ExtractedContact(name=profile['name'],role=profile['role'],email=profile['email']))
        # A single-person profile heading plus one nearby personal address and
        # literal job-title line is a source association, not an email-name guess.
        headings = page.get("contact_headings", page.get("headings", []))
        profile_names = list(dict.fromkeys(value for value in page.get('headings',[]) if _person_name(value)))
        if not profile_names:
            profile_names=list(dict.fromkeys(value for value in page.get('contact_headings',[]) if _person_name(value)))
        title_names = [re.split(r"\s*[|–—]\s*|\s+-\s+", value)[0] for value in page.get("titles", [])]
        title_names = [value for value in title_names if _person_name(value) and (value in headings or urlsplit(url).path not in {'', '/'} and text.count(value) >= 2)]
        if len(set(title_names)) == 1:
            profile_names = list(dict.fromkeys(title_names))
        if len(profile_names) == 1:
            name = profile_names[0]
            for match in list(re.finditer(re.escape(name), text))[:10]:
                start = max(0, match.start() - 70)
                excerpt = text[start:start + 500].rstrip()
                # A second person's assistant/contact section is a new boundary.
                boundary = re.search(r"\n(?:legal assistant|assistant|secretary)\s*:", excerpt, re.I)
                if boundary and boundary.start() > match.start() - start:
                    excerpt = excerpt[:boundary.start()]
                lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
                roles = [line for line in lines if CONTACT_ROLE.search(line) and len(line.split()) <= 8
                         and re.fullmatch(r"[\w .,&/|'’()-]{1,100}", line) and line != name
                         and not re.fullmatch(r'(?:attorney|lawyer) (?:bio|biography|profile)',line,re.I)]
                emails = [email for email in dict.fromkeys(EMAIL_PATTERN.findall(excerpt))
                          if email.split('@', 1)[0].casefold() not in GENERIC_INBOXES]
                if len(emails) == 1 and len(roles) <= 1:
                    named_contact(name, roles[0] if roles else None, emails[0], excerpt)
        for match in NAMED_CONTACT.finditer(text):
            name, role, email = match.groups()
            named_contact(name, role, email, match.group())
        for match in EMAIL_PATTERN.finditer(text):
            email = match.group()
            email_host = email.rsplit("@", 1)[-1].casefold()
            firm_host = (urlsplit(url).hostname or "").removeprefix("www.").casefold()
            if email_host != firm_host and not email_host.endswith("." + firm_host):
                continue  # Cross-domain footer/service-provider addresses are not firm inboxes.
            excerpt = text[max(0, match.start() - 100):min(len(text), match.end() + 100)]
            add("email", email, excerpt)
            if len(contacts) < 50 and not any(item.email.casefold() == email.casefold() for item in contacts):
                # Names/roles are not guessed from the address or adjacent footer text.
                contacts.append(ExtractedContact(email=email))
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if len(sentence) > 500: continue
            for field, matcher in (("firm_stage", NEW_FIRM), ("workflow_need", MANAGE_NEED), ("website_need", LAUNCH_NEED)):
                if matcher.search(sentence): add(field, sentence, sentence)
            if WEBSITE_PROJECT.search(sentence) and urlsplit(url).path.rstrip('/') in {'','/landing','/welcome'}:
                add('website_need',sentence,sentence)
    # Conflicting values are withheld, not resolved by choosing the first one.
    for contact in contacts:
        if not contact.name: continue
        current=[]
        from .primary_facts import legal_role
        from .qualification import _role_match
        for page in pages:
            path=urlsplit(page['url']).path.strip('/')
            roster=attorney_roster(page)
            heading_names=[name for name in (page.get('headings') or page.get('contact_headings',[])) if _person_name(name)]
            profile=path.count('/')>=1 and contact.name in heading_names
            if not roster and not profile:continue
            lines=page.get('text','').splitlines()
            for i,line in enumerate(lines[:-1]):
                if line.strip()!=contact.name:continue
                role=lines[i+1].strip()
                if legal_role(role):current.append((2 if profile else 1,role,page,'\n'.join(lines[i:i+2])))
        if current:
            states={_role_match(role,request.buyer_roles) for _,role,_,_ in current}
            if len(states)>1:contact.role=None
            else:
                _,role,page,quote=max(current,key=lambda item:item[0])
                contact.role=role
                if len(evidence)<200 and not any(e.field=='contact_role' and e.value==role and e.source_url==page['url']
                    and contact.name in e.excerpt and role in e.excerpt for e in evidence):
                    evidence.append(Evidence(field='contact_role',value=role,source_url=page['url'],excerpt=quote,retrieved_at=page.get('retrieved_at')))
    canonical = [name for root,name in canonical_names if root] or [name for root,name in canonical_names]
    names = list(dict.fromkeys(canonical or preferred_names or names))
    countries = list(dict.fromkeys(countries))
    counts = list(dict.fromkeys(counts or rosters))
    return ExtractedFirm(name=names[0] if len(names) == 1 else None,
        source_type="firm_website" if legal_metadata or any(FIRM_WORDS.search(str(page.get("text", ""))) for page in pages) else "unknown",
        country=countries[0] if len(countries) == 1 else None,
        size=counts[0] if len(counts) == 1 else None, size_unit="attorneys" if len(counts) == 1 else "unknown",
        practice_areas=list(dict.fromkeys(areas))[:20], contacts=contacts, evidence=evidence).model_dump()
