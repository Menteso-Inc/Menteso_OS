"""Capture the already loaded WIPO bibliography without another navigation."""
import re

HEADINGS = {'Publication Number', 'Publication Date', 'International Application No.',
            'International Filing Date', 'Priority Data', 'Applicants', 'Inventors',
            'Agents', 'Title', 'Abstract', 'IPC', 'CPC', 'Designated States',
            'Related patent documents', 'Latest bibliographic data on file with the International Bureau'}


def patent_key(value):
    return re.sub(r'[^A-Z0-9]', '', str(value).upper())


def parse(text, expected, url):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if 'Publication Number' not in lines:
        return {}
    index = lines.index('Publication Number')
    if index + 1 >= len(lines) or patent_key(lines[index+1]) != patent_key(expected):
        return {}
    sections = {}
    for heading in ('Applicants', 'Inventors', 'Agents'):
        if lines.count(heading) != 1:
            continue
        start = lines.index(heading)+1
        end = next((i for i in range(start, len(lines)) if lines[i] in HEADINGS), len(lines))
        if end-start <= 100:
            sections[heading.lower()] = lines[start:end]
    return {'publication': patent_key(expected), 'source_url': url,
            'method': 'wipo_rendered_bibliography', 'sections': sections}


def capture(page, expected):
    url = str(page.url)
    if not re.match(r'^https://patentscope\.wipo\.int/', url):
        return {}
    # The downloader appends a run/row suffix to prevent PDF overwrites.
    match = re.match(r'^WO[_/]?(\d{4})[_/]?(\d{6})(?:_|$)', expected, re.I)
    if not match:
        return {}
    expected = 'WO'+match[1]+match[2]
    return parse(page.locator('body').inner_text(timeout=1500), expected, url)


def apply(result, context):
    """Only a single explicitly named representative can supply a fallback."""
    from .recipient import person_name
    data = (context or {}).get('_bibliography', {})
    if (result.get('status') != 'found' or not result.get('name_is_placeholder')
            or result.get('contact_role') != 'agent'
            or data.get('method') != 'wipo_rendered_bibliography'
            or data.get('publication') != patent_key((context or {}).get('id', ''))
            or not re.match(r'^https://patentscope\.wipo\.int/', data.get('source_url', ''))):
        return result
    lines = data.get('sections', {}).get('agents', [])
    # An isolated LAST, First entry is unambiguous. Postal lines or several
    # representatives require source review; never use the first inventor.
    if len(lines) != 1:
        return result
    name = person_name(re.sub(r'\s*\[[^\]]*\](?:/\[[^\]]*\])?\s*$', '', lines[0]))
    if name:
        result.update(display_name=name, name_is_placeholder=False, recipient_role='agent',
                      recipient_status='verified_bibliography', category='Slf',
                      recipient_evidence=[{'source': data, 'printed_name': lines[0]}])
    return result
