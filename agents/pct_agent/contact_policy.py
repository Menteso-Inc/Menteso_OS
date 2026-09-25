"""Evidence checks and contact selection; no generated contact values."""
import re
import time
import unicodedata
from collections import defaultdict

import dns.resolver
import pycountry


def words(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def country_code(value):
    aliases = {'österreich': 'AT', 'osterreich': 'AT', 'deutschland': 'DE',
               'schweiz': 'CH', 'suisse': 'CH', 'italia': 'IT', 'españa': 'ES',
               'republic of korea': 'KR', 'south korea': 'KR', 'uk': 'GB',
               'p.r. china': 'CN', 'united states of america': 'US'}
    try:
        return pycountry.countries.lookup(aliases.get(value.strip().casefold(), value.strip())).alpha_2
    except LookupError:
        return ''


def address_country(address):
    """Match a printed country at the end of a confirmed address, never a phone/office."""
    candidates = [('Österreich', 'AT'), ('Deutschland', 'DE'), ('Schweiz', 'CH'),
                  ('Suisse', 'CH'), ('Italia', 'IT'), ('España', 'ES')]
    for country in pycountry.countries:
        for key in ('name', 'official_name', 'common_name'):
            name = getattr(country, key, '')
            if name:
                candidates.append((name, country.alpha_2))
    text = unicodedata.normalize('NFKC', address).strip(' ,.;\n').casefold()
    for name, code in sorted(candidates, key=lambda pair: -len(pair[0])):
        if re.search(r'(?:^|[\s,;])' + re.escape(name.casefold()) + r'$', text):
            return code
    return ''


def value_key(kind, value):
    if kind in {'phone', 'fax'}:
        return re.sub(r'\D', '', value)
    if kind == 'email':
        # Readers sometimes preserve different capitalization from the PDF.
        return value.strip().casefold()
    if kind == 'country':
        return country_code(value) or words(value)
    return words(value)


def field_key(field):
    return field.role, words(field.entity), field.kind, value_key(field.kind, field.value), field.page


def agreement_key(field):
    """Compare contact values without confusing a firm and its named attorney."""
    if field.kind in {'email', 'phone'}:
        return field.role, field.kind, value_key(field.kind, field.value), field.page
    return field_key(field)


def agree(first, second, ocr_emails=None):
    """Keep contacts confirmed by two image reads or an image read plus exact OCR."""
    other = {agreement_key(f): f for f in second.fields if f.legible}
    ocr_keys = {value_key('email', value) for value in (ocr_emails or [])}
    kept, issues = [], []
    kept_keys = set()
    for field in first.fields:
        key = agreement_key(field)
        match = other.get(key)
        if field.legible and match:
            # Conflicting type labels cannot decide a business category.
            if field.entity_type != match.entity_type:
                field = field.model_copy(update={'entity_type': 'unknown'})
            kept.append(field)
            kept_keys.add(key)
            if field.kind in {'email', 'phone'} and words(field.entity) != words(match.entity):
                issues.append(f'{field.kind} owner label differed between image readings; value retained')
        elif (field.legible and field.kind == 'email'
              and value_key('email', field.value) in ocr_keys):
            kept.append(field)
            kept_keys.add(key)
            issues.append('email confirmed by one image reading and independent OCR')
        elif field.kind in {'email', 'phone', 'name', 'country'}:
            issues.append(f'{field.kind} not confirmed by both image readings')
    first_keys = {agreement_key(f) for f in first.fields if f.legible}
    for field in second.fields:
        key = agreement_key(field)
        if key in first_keys or key in kept_keys:
            continue
        if (field.legible and field.kind == 'email'
                and value_key('email', field.value) in ocr_keys):
            kept.append(field)
            kept_keys.add(key)
            issues.append('email confirmed by one image reading and independent OCR')
        elif field.kind in {'email', 'phone', 'name', 'country'}:
            issues.append(f'{field.kind} not confirmed by both image readings')
    return first.model_copy(update={'fields': kept}), list(dict.fromkeys(issues))


FAX_LABEL = re.compile(r'fax|facsimile|telecop|télécop|传真|팩스', re.I)
AGENT_SECTION = re.compile(r'agent|attorney|representative|mandataire|vertreter|anwalt|procurador|representante|mandatario|대리인|代理|^IV\b', re.I)
APPLICANT_SECTION = re.compile(r'applicant|anmelder|demandeur|solicitante|申请人|출원인|^II\b', re.I)


EMAIL_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}"
)


def _valid_email_syntax(value):
    if not EMAIL_RE.fullmatch(value):
        return False
    local, domain = value.rsplit('@', 1)
    return not (local.startswith('.') or local.endswith('.') or '..' in local or any(
        not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?', label)
        for label in domain.split('.')))


def _email_values(value, evidence=''):
    """Split explicit lists and recognized ``Display Name <email>`` syntax."""
    value = value.strip()
    if _valid_email_syntax(value):
        return [value]
    parts = [part.strip(' <>[]()') for part in re.split(r'[;,\s]+', value) if part.strip()]
    if len(parts) > 1 and all(_valid_email_syntax(part) for part in parts):
        return parts
    bracketed = list(dict.fromkeys(
        candidate.strip() for candidate in re.findall(r'<([^<>]+)>', evidence + ' ' + value)
        if _valid_email_syntax(candidate.strip())
    ))
    if len(bracketed) == 1:
        return bracketed
    # OCR sometimes deletes angle brackets from ``H.Coleman <cosud@erols.com>``.
    # Recover only the exact valid suffix after a display-name-shaped prefix.
    if value.count('@') == 2:
        display_name, suffix = value.split('@', 1)
        if (re.fullmatch(r"[A-Za-z][A-Za-z.' -]{1,80}", display_name)
                and _valid_email_syntax(suffix)):
            return [suffix]
    return []


def valid_fields(extraction, rules, page_numbers):
    groups, issues = defaultdict(list), []
    bad_blocks = set()
    roles = defaultdict(set)
    contact_owners = defaultdict(lambda: defaultdict(set))
    expanded = []
    for original in extraction.fields:
        email_values = _email_values(original.value, original.evidence) if original.kind == 'email' else []
        if original.kind == 'email' and email_values:
            expanded.extend(original.model_copy(update={'value': value}) for value in email_values)
        else:
            expanded.append(original)
    for f in expanded:
        if f.role not in rules.include_roles or f.role in rules.exclude_roles or f.kind == 'fax':
            continue
        if f.kind == 'phone' and FAX_LABEL.search(f.evidence):
            issues.append('Fax-labeled value excluded from phones')
            continue
        section_ok = (AGENT_SECTION.search(f.section) if f.role == 'agent' else
                      APPLICANT_SECTION.search(f.section) if f.role == 'applicant' else False)
        if not (f.legible and f.page in page_numbers and f.entity.strip() and f.block_id.strip() and section_ok):
            issues.append(f'{f.kind}: missing or unclear source/owner/role')
            continue
        roles[f.block_id].add(f.role)
        if len(roles[f.block_id]) > 1:
            bad_blocks.add(f.block_id)
        if f.kind in {'email', 'phone'}:
            contact_owners[f.block_id][f.kind].add(words(f.entity))
            if len(contact_owners[f.block_id][f.kind]) > 1:
                bad_blocks.add(f.block_id)
        value = f.value.strip()
        # Address punctuation is formatting, but email punctuation is meaningful.
        supported = (value_key(f.kind, value) in value_key(f.kind, f.evidence)
                     if f.kind not in {'country', 'email'} else
                     (value.casefold() in f.evidence.casefold()
                      if f.kind == 'email' else words(value) in words(f.evidence)))
        if not value or not supported:
            issues.append(f'{f.kind}: incomplete supporting evidence')
            continue
        if f.kind == 'email':
            if not _valid_email_syntax(value):
                issues.append('Invalid email syntax')
                continue
            domain = value.rsplit('@', 1)[1].casefold()
            if any(domain == d.casefold() or domain.endswith('.' + d.casefold()) for d in rules.exclude_email_domains):
                continue
        if f.kind == 'phone' and (re.search(r'[A-Za-z]', value) or not 7 <= len(value_key('phone', value)) <= 15):
            issues.append('Invalid phone syntax')
            continue
        groups[f.block_id].append(f)
    for block in bad_blocks:
        groups.pop(block, None)
        issues.append('Inconsistent contact ownership or roles within a source block')
    return groups, issues


def values(fields, kind):
    return list(dict.fromkeys(f.value.strip() for f in fields if f.kind == kind))


def contact_signature(fields):
    return (tuple(sorted(value_key('email', v) for v in values(fields, 'email'))),
            tuple(sorted(value_key('phone', v) for v in values(fields, 'phone'))))


def shared_contacts(first, second):
    """A missing optional phone is not a conflicting phone value."""
    shared = False
    for left, right in zip(contact_signature(first), contact_signature(second)):
        if left and right:
            if left != right:
                return False
            shared = True
    return shared


def unique_contact(blocks):
    if not blocks:
        return None
    if len({contact_signature(fields) for fields in blocks}) > 1 and not all(
            shared_contacts(blocks[0], fields) for fields in blocks[1:]):
        return None
    # Identical contacts may be repeated under the primary firm and its attorney.
    # Keep one complete block, never assemble fields across different owners.
    return sorted(blocks, key=lambda fs: (-sum(bool(values(fs, kind)) for kind in ('email', 'phone')),
                  min(f.page for f in fs),
                  0 if any(re.search(r'IV\s*[-.]?\s*1\b', f.section, re.I) for f in fs) else 1,
                  0 if fs[0].entity_type == 'law_firm' else 1, fs[0].block_id))[0]


def primary_contact(blocks, role):
    """Use an explicitly primary PCT block, never an arbitrary peer contact."""
    if not blocks:
        return None
    if role == 'agent':
        primary = [fields for fields in blocks if any(
            re.search(r'IV\s*[-.]?\s*1(?:\D|$)', field.section, re.I) for field in fields
        )]
        return primary[0] if len(primary) == 1 else None
    if role == 'applicant':
        first_page = min(min(field.page for field in fields) for fields in blocks)
        primary = [fields for fields in blocks if min(field.page for field in fields) == first_page]
        return primary[0] if len(primary) == 1 else None
    return None


def _shared_result(app, ag, issues, extraction):
    """Retain only identical values when address cannot decide contact ownership."""
    agent_keys = {(f.kind, value_key(f.kind, f.value)) for f in ag
                  if f.kind in {'email', 'phone'}}
    shared = [f for f in app
              if (f.kind, value_key(f.kind, f.value)) in agent_keys]
    emails, phones = values(shared, 'email'), values(shared, 'phone')
    agent_name = next((name for name in values(ag, 'name')
                       if words(name) == words(ag[0].entity)), '')
    issues.append('Shared contact retained; applicant/agent ownership requires address review')
    return {'status': 'found', 'emails': emails, 'phones': phones, 'name': '',
            'agent_name': agent_name, 'display_name': agent_name or "Sir/Ma'am",
            'name_is_placeholder': not bool(agent_name), 'country': '', 'category': '',
            'contact_role': 'shared', 'contact_block_id': '', 'contact_owner': '',
            'selection_reason': 'Identical applicant/agent contact retained; address comparison unavailable',
            'ai_status': 'verified',
            'reason': '; '.join(dict.fromkeys(issues + extraction.uncertainties)),
            'field_evidence': [f.model_dump() for f in shared],
            'agent_name_evidence': [f.model_dump() for f in ag if f.kind == 'name']}


def _email_only_result(fields, issues, extraction, role, selection):
    """Keep source-agreed email while withholding ambiguous owner-dependent fields."""
    emails = []
    seen = set()
    evidence = []
    for field in fields:
        if field.kind != 'email':
            continue
        key = value_key('email', field.value)
        if key not in seen:
            emails.append(field.value.strip())
            seen.add(key)
        evidence.append(field)
    if not emails:
        return None
    issues.append('Email retained; contact owner-dependent fields require review')
    return {'status': 'found', 'emails': emails, 'phones': [], 'name': '',
            'agent_name': '', 'display_name': "Sir/Ma'am", 'name_is_placeholder': True,
            'country': '', 'category': '', 'contact_role': role, 'contact_block_id': '',
            'contact_owner': '', 'selection_reason': selection, 'ai_status': 'verified',
            'reason': '; '.join(dict.fromkeys(issues + extraction.uncertainties)),
            'field_evidence': [f.model_dump() for f in evidence], 'agent_name_evidence': []}


def select(extraction, rules, page_numbers, empty):
    groups, issues = valid_fields(extraction, rules, page_numbers)
    if set(extraction.reviewed_pages) != set(page_numbers):
        return empty(reason='Not all supplied pages were reviewed')
    contacts = [fs for fs in groups.values() if any(f.kind in {'email', 'phone'} for f in fs)]
    if not contacts:
        result = empty(ai_status='needs_review' if issues or extraction.uncertainties else 'no_wanted_contacts',
                       reason='; '.join(issues + extraction.uncertainties) or 'No usable applicant or agent contact in reviewed pages')
        result['category'] = 'No Info' if result['ai_status'] == 'no_wanted_contacts' else ''
        return result
    applicants = [fs for fs in contacts if fs[0].role == 'applicant']
    agents = [fs for fs in contacts if fs[0].role == 'agent']
    app = unique_contact(applicants) or primary_contact(applicants, 'applicant')
    ag = unique_contact(agents) or primary_contact(agents, 'agent')
    if applicants and app is None:
        applicant_emails = [f for fields in applicants for f in fields if f.kind == 'email']
        if len({value_key('email', f.value) for f in applicant_emails}) == 1:
            result = _email_only_result(
                applicant_emails, issues, extraction, 'applicant',
                'Multiple applicant blocks share one verified email; ownership fields withheld',
            )
            if result:
                return result
        return empty(reason='Multiple different contact owners require selection review')
    if agents and ag is None:
        if app:
            # If an unresolved agent block shares the applicant email, that
            # email is safe under either address outcome; other fields are not.
            agent_email_keys = {value_key('email', f.value) for fields in agents
                                for f in fields if f.kind == 'email'}
            shared_email_fields = [f for f in app if f.kind == 'email'
                                   and value_key('email', f.value) in agent_email_keys]
            if shared_email_fields:
                return _email_only_result(
                    shared_email_fields, issues, extraction, 'shared',
                    'Verified applicant email is also printed for an unresolved agent block',
                )
            chosen = app
            selection = 'Different applicant and agent contacts; select the unique applicant'
        else:
            agent_emails = [f for fields in agents for f in fields if f.kind == 'email']
            if len({value_key('email', f.value) for f in agent_emails}) == 1:
                result = _email_only_result(
                    agent_emails, issues, extraction, 'agent',
                    'Multiple agent blocks share one verified email; owner-dependent fields withheld',
                )
                if result:
                    return result
            return empty(reason='Multiple different contact owners require selection review')
    else:
        chosen = app or ag
        selection = 'Only one contact role has usable contact details'
    if app and ag:
        if not shared_contacts(app, ag):
            if values(app, 'email') or not values(ag, 'email'):
                chosen = app
                selection = 'Different contacts; select applicant when applicant email is available'
            else:
                chosen = ag
                selection = 'Applicant has no email; select the independently verified agent email block'
        else:
            aa, ga = values(app, 'address'), values(ag, 'address')
            if not aa or not ga:
                return _shared_result(app, ag, issues, extraction)
            chosen = app if {words(v) for v in aa} == {words(v) for v in ga} else ag
            selection = 'Process document: shared contacts; same address selects applicant, different address selects agent'
    names = values(chosen, 'name')
    owner = chosen[0].entity
    name = next((n for n in names if words(n) == words(owner)), '')
    if names and not name:
        issues.append('Contact name/owner mismatch; name withheld')
    agent_groups = [fs for fs in groups.values() if fs[0].role == 'agent' and values(fs, 'name')]
    named_agent = chosen if chosen[0].role == 'agent' else (ag or (agent_groups[0] if len(agent_groups) == 1 else None))
    agent_name = ''
    if named_agent:
        agent_name = next((n for n in values(named_agent, 'name') if words(n) == words(named_agent[0].entity)), '')
    # The display fallback is not a real extracted identity, and is never used for deduplication.
    display = agent_name or "Sir/Ma'am"
    codes = {country_code(v) for v in values(chosen, 'country')}
    if not codes:
        codes = {code for address in values(chosen, 'address') if (code := address_country(address))}
    country = next(iter(codes)) if len(codes) == 1 and '' not in codes else ''
    if values(chosen, 'country') and not country:
        issues.append('Country withheld: unrecognized or conflicting country')
    types = {f.entity_type for f in chosen}
    category = {'law_firm': 'Slf', 'company': 'Corp', 'individual': 'Ind'}.get(next(iter(types)), '') if len(types) == 1 else ''
    if not category and chosen[0].role == 'applicant' and re.search(r'\b(gmbh|ltd|limited|inc|incorporated|llc|plc)\.?$', owner, re.I):
        category = 'Corp'
    if not category:
        issues.append('Business category requires review')
    return {'status': 'found', 'emails': values(chosen, 'email'), 'phones': values(chosen, 'phone'),
            'name': name, 'agent_name': agent_name, 'display_name': display,
            'name_is_placeholder': not bool(agent_name), 'country': country, 'category': category,
            'contact_role': chosen[0].role, 'contact_block_id': chosen[0].block_id,
            'contact_owner': owner, 'selection_reason': selection, 'ai_status': 'verified',
            'reason': '; '.join(dict.fromkeys(issues + extraction.uncertainties)),
            'field_evidence': [f.model_dump() for f in chosen],
            'agent_name_evidence': [f.model_dump() for f in (named_agent or []) if f.kind == 'name']}


_DNS_CACHE = {}


def email_domain_status(email):
    """DNS routing only: never sends mail or claims that a mailbox exists."""
    domain = email.rsplit('@', 1)[-1].casefold()
    cached = _DNS_CACHE.get(domain)
    if cached and cached[1] != 'unconfirmed' and time.monotonic() - cached[0] < 300:
        return cached[1]
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=4)
        result = 'null_mx' if any(str(rr.exchange) == '.' for rr in answers) else 'mx'
    except dns.resolver.NoAnswer:
        result = 'unconfirmed'
        for record_type in ('A', 'AAAA'):
            try:
                dns.resolver.resolve(domain, record_type, lifetime=4)
                result = 'implicit_mx'
                break
            except dns.exception.DNSException:
                pass
    except dns.resolver.NXDOMAIN:
        result = 'nxdomain'
    except dns.exception.DNSException:
        # Retry a transient resolver failure once; never convert it to "invalid".
        try:
            answers = dns.resolver.resolve(domain, 'MX', lifetime=8)
            result = 'null_mx' if any(str(rr.exchange) == '.' for rr in answers) else 'mx'
        except dns.resolver.NXDOMAIN:
            result = 'nxdomain'
        except dns.exception.DNSException:
            result = 'unconfirmed'
    _DNS_CACHE[domain] = time.monotonic(), result
    return result


def mark_repeated(results):
    """Within one input/run only; preserve every row and all source fields."""
    seen_patents, seen_contacts = {}, {}
    for row in sorted(results, key=lambda r: r.get('row', 0)):
        if row.get('base_category') is not None:
            row['category'] = row['base_category']
        row.pop('repeated_of', None)
        patent = words(row.get('patent_id', ''))
        # Same verified email/phone set, including role+owner, not merely same applicant.
        contact = (words(row.get('contact_owner', '')), row.get('contact_role', ''),
                   tuple(sorted(value_key('email', v) for v in row.get('emails', []))),
                   tuple(sorted(value_key('phone', v) for v in row.get('phones', []))))
        has_contact = (row.get('status') == 'found' and bool(contact[0]) and bool(contact[2] or contact[3])
                       and row.get('contact_owner') != '[unnamed contact]')
        prior = seen_patents.get(patent) if patent else None
        if prior is None and has_contact:
            prior = seen_contacts.get(contact)
        if prior is not None:
            row['base_category'] = row.get('category', '')
            row['category'] = 'Repeated'
            row['repeated_of'] = prior
        if patent:
            seen_patents.setdefault(patent, row.get('row'))
        if has_contact:
            seen_contacts.setdefault(contact, row.get('row'))
