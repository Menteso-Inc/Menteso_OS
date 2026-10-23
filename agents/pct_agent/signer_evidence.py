"""Link printed signature identities to independently verified contact blocks.

Signatures provide selection evidence, never a new email or an inferred employer.
The local path reads only matching, explicitly labelled signature values.
"""
import re

SIGNATURE = re.compile(r'\bsignature\s+(?:of|du|de|des)\b|\bassinatura\b|\bunterschrift\b|\bfirma\s+del\b|出願人.*署名', re.I)
PERSON_LABEL = re.compile(r'^(?:name of signatory|nom du signataire|nome do signat[aá]rio|nome de quem assina|nombre del firmante|name der unterzeichnenden person|署名者の氏名)\s*:?$', re.I)
NAME_LABEL = re.compile(r'^(?:name|nom|nome|nombre|名称|氏名)(?:\s*\([^)]*\))?\s*[:：•·]?$', re.I)
CAPACITY = re.compile(r'^(?:capacity|qualit[eé]|qualidade|capacidad|calidad|eigenschaft)\b|^権限', re.I)
STOP = re.compile(r'for receiving office|for international bureau|r[eé]serv[eé].*office|vom anmeldeamt|reservado.*oficina|受理官庁記入欄', re.I)


def labelled_values(scan):
    """Read same-row value cells in a bounded, explicitly labelled signature table."""
    found = []
    for page in scan['pages']:
        lines = [line for line in scan['lines'] if line['page'] == page['page']]
        headings = [line for line in lines if line['rect'][0] < page['width'] * .4
                    and SIGNATURE.search(line['text'])]
        for heading in headings:
            x, top = heading['rect'][:2]
            bottom = min([line['rect'][1] for line in lines
                          if line['rect'][1] > top + 8 and STOP.search(line['text'])]
                         + [top + 150, page['height']])
            labels = sorted([line for line in lines if top + 8 < line['rect'][1] < bottom
                             and abs(line['rect'][0] - x) < 18
                             and (PERSON_LABEL.fullmatch(line['text'])
                                  or NAME_LABEL.fullmatch(line['text'])
                                  or CAPACITY.search(line['text']))], key=lambda line: line['rect'][1])
            has_person = any(PERSON_LABEL.fullmatch(line['text']) for line in labels)
            for index, label in enumerate(labels):
                if CAPACITY.search(label['text']):
                    continue
                end = labels[index + 1]['rect'][1] - 1 if index + 1 < len(labels) else min(bottom, label['rect'][1] + 35)
                values = sorted([line for line in lines
                                 if line['rect'][0] > max(label['rect'][2] + 8, page['width'] * .38)
                                 and label['rect'][1] - 3 <= line['rect'][1] < end
                                 and line['rect'][3] <= end + 3], key=lambda line: (line['rect'][1], line['rect'][0]))
                if not values or abs(values[0]['rect'][1] - label['rect'][1]) > 5:
                    continue
                kind = 'signer_name' if PERSON_LABEL.fullmatch(label['text']) or not has_person else 'signer_entity'
                found.append({'kind': kind, 'ids': [line['id'] for line in values],
                              'section': heading['text'], 'page': page['page'],
                              'block_id': f"signature-p{page['page']}-{heading['id']}",
                              'bounds': {'page': page['page'], 'rect': [max(label['rect'][2]+8, page['width']*.38),
                                         label['rect'][1]-3, page['width']-1, max(end-1, max(v['rect'][3] for v in values)+2)]},
                              'text': ' '.join(line['text'] for line in values)})
    return found


def matching_contact(fields, identity, kind):
    from .contact_policy import words
    owners = {fields[0].entity}
    if any(words(owner) == words(identity) for owner in owners):
        return True
    # A person's LAST, First order may differ; no partial name or domain inference.
    tokens = lambda value: sorted(re.findall(r'\w+', value.casefold()))
    return kind == 'signer_name' and any(tokens(owner) == tokens(identity) for owner in owners)


def signature_fields(extraction, page_numbers):
    from .contact_policy import words
    valid = []
    for field in extraction.fields:
        if (field.kind not in {'signer_entity', 'signer_name'} or not field.legible
                or field.role != 'other' or field.page not in page_numbers
                or not field.block_id.startswith('signature-') or not SIGNATURE.search(field.section)
                or not words(field.value) or words(field.value) not in words(field.evidence)):
            continue
        valid.append(field)
    return valid


def resolve(extraction, groups, page_numbers):
    from .contact_policy import values, unique_contact
    contacts = [fields for fields in groups.values() if values(fields, 'email')]
    signatures = {}
    for field in signature_fields(extraction, page_numbers):
        signatures.setdefault(field.block_id, []).append(field)
    resolved = []
    for observations in signatures.values():
        # An explicit signing organisation takes precedence over a person's name.
        identities = [field for field in observations if field.kind == 'signer_entity'] or observations
        if any(not any(matching_contact(fields, field.value, field.kind) for fields in contacts)
               for field in identities):
            return None, {'status': 'unresolved', 'reason': 'A signing identity has no verified contact-owner match'}
        candidates = [fields for fields in contacts if any(
            matching_contact(fields, field.value, field.kind) for field in identities)]
        chosen = unique_contact(candidates)
        if chosen is None:
            return None, {'status': 'unresolved', 'reason': 'Signer has no unique verified email contact'}
        resolved.append((chosen, identities))
    if not resolved:
        return None, {'status': 'unavailable'}
    selected = unique_contact([fields for fields, _ in resolved])
    if selected is None:
        return None, {'status': 'unresolved', 'reason': 'Multiple signers link to different email contacts'}
    return selected, {'status': 'confirmed', 'contact_block_id': selected[0].block_id,
                      'contact_owner': selected[0].entity,
                      'evidence': [field.model_dump() for _, identity in resolved for field in identity]}


def verify_local(pdf, scan, fields, folder, record, step):
    from . import ai_verifier as ai, contact_policy as policy, local_evidence as local
    extraction = ai.VisualExtraction(fields=fields, reviewed_pages=[page['page'] for page in scan['pages']], uncertainties=[])
    groups, _ = policy.valid_fields(extraction, ai.load_rules(), extraction.reviewed_pages)
    contacts = [values for values in groups.values() if values[0].role == 'agent' and policy.values(values, 'email')]
    original = policy._select_primary(extraction, ai.load_rules(), extraction.reviewed_pages, ai._empty_contacts)
    if original.get('contact_role') != 'agent':
        return []
    # One distinct email needs no additional model requests to decide the email.
    if len({policy.value_key('email', value) for group in contacts for value in policy.values(group, 'email')}) < 2:
        return []
    lookup = {line['id']: line for line in scan['lines']}
    candidates = labelled_values(scan)
    by_signature = {}
    for item in candidates:
        by_signature.setdefault(item['block_id'], []).append(item)
    if len(by_signature) > 1:
        record.setdefault('signature_review', []).append({'reason': 'Multiple signature blocks require selection review'})
        return []
    verified = []
    for items in by_signature.values():
        identities = [item for item in items if item['kind'] == 'signer_entity'] or items
        if len(identities) != 1:
            record.setdefault('signature_review', []).append({'reason': 'Multiple signing identities require selection review'})
            continue
        for item in identities:
            if not any(matching_contact(group, item['text'], item['kind']) for group in contacts):
                record.setdefault('signature_review', []).append({'page': item['page'], 'reason': 'Printed signer has no exact contact-owner match'})
                continue
            values, trace = local.verify_value(pdf, item['ids'], lookup, 'name', folder, step)
            trace['purpose'] = 'signature_contact_selection'
            record['checks'].append(trace)
            for value in values:
                verified.append(ai.ContactField(kind=item['kind'], value=value, entity=value,
                    role='other', page=item['page'], evidence=value, legible=True,
                    block_id=item['block_id'], section=item['section'], entity_type='unknown'))
    if verified:
        step('[Contact selection] Printed signing identity independently checked against the original image')
    return verified
