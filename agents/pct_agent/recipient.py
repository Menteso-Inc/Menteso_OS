"""Source-backed greeting names and management categories, separate from email owners.

An inventor is not implicitly the email recipient. A printed signatory is used
only when the same signature block identifies the selected owner. No names are
constructed from email addresses or the human comparison workbook.
"""
import re
from . import contact_policy as policy, signer_evidence as signer

ORGANISATION = re.compile(
    r'\b(?:gmbh|g\s*\.?\s*m\s*\.?\s*b\s*\.?\s*h|llp|llc|ltd|limited|inc|incorporated|'
    r'corporation|company|aktiengesellschaft|ag|sarl|srl|sas|sa|bv|group|partners?|'
    r's\s*\.\s*l|b\s*\.\s*v|a\s*/\s*s|associates?|associ[eé]s|patent|patentanw[aä]lte|patentanwalts|attorneys?|'
    r'law|office|cabinet|association|university|institut\w*|societ\w*|co)\b', re.I)
TITLE = re.compile(r'^(?:(?:dr|prof)\s*\.\s*|(?:dr|prof)\s+)', re.I)


def person_name(value, explicit=False):
    """Format an evidenced person, never infer one from an organisation string."""
    value = ' '.join(value.strip(' /').split())
    while TITLE.match(value):
        value = TITLE.sub('', value, count=1).strip()
    # Numeric registration identifiers are not part of a person's name.
    if explicit:
        value = re.sub(r'\s+\d{3,}\s*$', '', value)
    if (not value or '@' in value or re.search(r'\d|[;&/]', value)
            or ORGANISATION.search(value)):
        return ''
    if value.count(',') == 1:
        last, first = (part.strip() for part in value.split(','))
        if not last or not first:
            return ''
        value = first + ' ' + last
    elif not explicit:
        return ''
    elif ',' in value:
        return ''
    while TITLE.match(value):
        value = TITLE.sub('', value, count=1).strip()
    return value if 2 <= len(value.split()) <= 9 else ''


def identity_key(value):
    return tuple(sorted(re.findall(r'\w+', person_name(value, True).casefold())))


def named_person(fields):
    names = {person_name(f.value, f.entity_type == 'individual')
             for f in fields if f.kind == 'name' and f.legible}
    names.discard('')
    return next(iter(names)) if len(names) == 1 else ''


def targets(result, extraction, rules):
    """Owners relevant to this greeting; unrelated additional contacts excluded."""
    groups, _ = policy.valid_fields(extraction, rules, extraction.reviewed_pages)
    selected = next((g for g in groups.values() if g[0].block_id == result.get('contact_block_id')
                     and g[0].role == result.get('contact_role')), None)
    if not selected:
        return []
    if named_person(selected):
        return [selected]
    associated = [g for g in groups.values() if g[0].role == 'agent'
                  and (g[0].block_id == selected[0].block_id
                       or ({v.casefold() for v in policy.values(selected, 'email')}
                           & {v.casefold() for v in policy.values(g, 'email')}))]
    people = [g for g in associated if named_person(g)]
    primary_person = people[0] if len(people) == 1 else policy.primary_contact(people, 'agent')
    if primary_person:
        return [primary_person, selected] if primary_person is not selected else [selected]
    if len(associated) == 1:
        return [associated[0], selected] if associated[0] is not selected else [selected]
    return [selected]


def matching_target(groups, value, kind):
    matches=[g for g in groups if signer.matching_contact(g,value,kind)]
    if len(matches)==1:
        return matches[0]
    # The same printed company can occupy both applicant and representative
    # blocks. Target order already gives its associated representative priority.
    if (matches and len({policy.words(g[0].entity) for g in matches})==1
            and set.intersection(*[{v.casefold() for v in policy.values(g,'email')} for g in matches])):
        return matches[0]
    return None


def apply(result, extraction, rules, identities=()):
    """Only display/category metadata changes; source contact ownership is retained."""
    if result.get('status') != 'found':
        return result
    relevant = targets(result, extraction, rules)
    identities=list(identities)
    signatures={}
    for field in signer.signature_fields(extraction, extraction.reviewed_pages):
        signatures.setdefault(field.block_id, []).append(field)
    for fields in signatures.values():
        people=[f for f in fields if f.kind=='signer_name']
        owners=[f for f in fields if f.kind=='signer_entity']
        if len(people)!=1 or len(owners)>1:
            continue
        owner=owners[0] if owners else people[0]
        linked=matching_target(relevant,owner.value,owner.kind)
        if linked:
            identities.append({'name':people[0].value,'owner':owner.value,'role':linked[0].role,
                               'contact_block_id':linked[0].block_id,'page':people[0].page,
                               'source_fields':[f.model_dump() for f in fields],'verified':True})
    chosen_person = ''
    recipient_role = result.get('contact_role', '')
    proof = []
    for group in relevant:
        chosen_person = named_person(group)
        if chosen_person:
            recipient_role = group[0].role
            proof = [f.model_dump() for f in group if f.kind == 'name']
            break
        matches = [item for item in identities
                   if item.get('contact_block_id') == group[0].block_id
                   and item.get('role') == group[0].role and item.get('verified') is True
                   and person_name(item.get('name', ''), True)]
        if len({identity_key(item['name']) for item in matches}) == 1:
            chosen_person = person_name(matches[0]['name'], True)
            recipient_role = group[0].role
            proof = matches
            break
    result.update(display_name=chosen_person or "Sir/Ma'am", name_is_placeholder=not bool(chosen_person),
                  recipient_role=recipient_role, recipient_evidence=proof,
                  recipient_status='verified' if chosen_person else 'person_not_confirmed')
    # These are worksheet management labels, not strings extracted from the PDF.
    selected = next((g for g in relevant if g[0].block_id == result.get('contact_block_id')), None)
    if recipient_role == 'agent':
        result['category'] = 'Slf'
    elif selected and selected[0].role == 'applicant':
        if named_person(selected):
            result['category'] = 'Ind'
        elif (any(f.entity_type == 'company' for f in selected)
              or ORGANISATION.search(selected[0].entity)):
            result['category'] = 'Corp'
    result['category_basis'] = 'Derived from verified recipient/contact role; duplicate handling is separate'
    if result.get('category'):
        result['reason']='; '.join(part.strip() for part in result.get('reason','').split(';')
                                  if part.strip() and part.strip()!='Business category requires review')
    return result


def enrich_local(pdf, scan, extraction, result, folder, record, step):
    """Verify only useful printed signature cells using independent source reads."""
    from . import ai_verifier as ai, local_evidence as local
    rules = ai.load_rules()
    relevant = targets(result, extraction, rules)
    if not relevant or named_person(relevant[0]):
        return apply(result, extraction, rules)
    lookup = {line['id']: line for line in scan['lines']}
    blocks = {}
    for item in signer.labelled_values(scan):
        blocks.setdefault(item['block_id'], []).append(item)
    identities = []
    review = record.setdefault('recipient_review', {'checks': [], 'identities': []})
    all_groups, _ = policy.valid_fields(extraction, rules, extraction.reviewed_pages)

    def verify(item):
        bounds={**item['bounds'], 'signature_cell': True,
                'source_ocr_engine': scan.get('engine', 'windows_en')}
        values, trace = local.verify_value(pdf, item['ids'], lookup, 'name', folder, step, bounds=bounds)
        trace['purpose'] = 'recipient_identity'
        review['checks'].append(trace)
        return values[0] if len(values) == 1 else ''

    for items in blocks.values():
        people = [item for item in items if item['kind'] == 'signer_name']
        organisations = [item for item in items if item['kind'] == 'signer_entity']
        if len(people) != 1 or len(organisations) > 1:
            continue
        person = people[0]
        # An explicit owner in the signature table must match a relevant owner.
        owner = organisations[0] if organisations else person
        candidate = matching_target(relevant, owner['text'], owner['kind'])
        if not organisations and ORGANISATION.search(person['text']):
            continue  # A firm in the signature Name cell supplies no person.
        if (not candidate and len(relevant)==1 and relevant[0][0].role=='applicant'
                and any(group[0].role=='agent' for group in all_groups.values())):
            review.setdefault('withheld', []).append('Unlinked signer with separate applicant/agent contacts')
            continue
        if not organisations and candidate is None:
            continue
        owner_value = verify(owner)
        candidate = matching_target(relevant, owner_value, owner['kind'])
        if not owner_value or candidate is None:
            continue
        name_value = verify(person) if organisations else owner_value
        if not person_name(name_value, True):
            continue
        identities.append({'name': name_value, 'owner': owner_value, 'role': candidate[0].role,
                           'contact_block_id': candidate[0].block_id,
                           'signature_block_id': person['block_id'], 'page': person['page'],
                           'source_ids': person['ids'], 'verified': True})
    review['identities'] = identities
    return apply(result, extraction, rules, identities)
