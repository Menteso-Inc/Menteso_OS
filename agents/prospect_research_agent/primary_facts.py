"""Reproducible primary-source facts; no provider hints or guessed headcounts."""
import re
from urllib.parse import urlsplit

LEGAL_ROLE = re.compile(r'(?:co-founder and )?(?:(?:managing|founding|senior|equity|non-equity|associate)\s+)?(?:partner|attorney|lawyer|solicitor|associate|counsel)(?:\s*&\s*notary)?', re.I)


def legal_role(value):
    main=re.split(r'\s*[|,]\s*|\s+-\s+',value)[0]
    if re.search(r'\b(?:retired|former|trainee|pupil|paralegal|assistant|clerk|economist)\b',main,re.I):return False
    return bool(LEGAL_ROLE.fullmatch(main) or re.fullmatch(r'(?:(?:US|Senior|Managing|Founding|Associate|Of)\s+)*(?:Partner|Attorney|Solicitor|Barrister|Lawyer|Counsel)(?:\s*[&/]\s*[\w ]{2,60})?|Qualified Foreign Lawyer(?: \([\w ]+\))?|(?:Principal )?Knowledge Lawyer',main,re.I))


def directory_entries(page):
    """An exact name/title/phone/email entry has no adjacent-person ambiguity."""
    from .rule_extraction import _person_name
    from .tools import EMAIL_PATTERN
    lines=page.get('text','').splitlines(); entries=[]
    role_line=re.compile(r'(?:(?:retired|former|managing|founding|senior|equity|non-equity|associate)\s+)*(?:partner|attorney|lawyer|solicitor|associate|counsel|owner|founder|office administrator|operations manager|head of operations|executive director)',re.I)
    for i,name in enumerate(lines[:-1]):
        role=lines[i+1].strip()
        embedded=re.split(r'\s+-\s+',name,maxsplit=1)
        if len(embedded)==2 and _person_name(embedded[0]):name,role=embedded
        if not _person_name(name.strip()) or not (role_line.fullmatch(role) or legal_role(role)):continue
        for j in range(i+2,min(len(lines),i+7)):
            value=lines[j].strip()
            email_value=re.sub(r'^(?:E|Email)\s*:\s*','',value,flags=re.I)
            if EMAIL_PATTERN.fullmatch(email_value):
                entries.append({'name':name.strip(),'role':role,'email':email_value,'excerpt':'\n'.join(lines[i:j+1])});break
            if not re.fullmatch(r'(?:(?:Tel|Phone|Ph|Direct|Email|T|D)\s*:?\s*)?[+\d(). /-]{3,45}\s*[•·]?|(?:Tel|Phone|Direct|Email|T|D)\s*:?|',value,re.I):break
    return entries


def profile_contact(page):
    """Link one profile's heading to its explicit Contact section, not a footer.

    A long biography need not fit into a single 500-character quotation. Both
    quotations are independently grounded and the page relationship is checked.
    """
    from .rule_extraction import _person_name
    from .tools import EMAIL_PATTERN
    path=urlsplit(page['url']).path.strip('/')
    if path.count('/')<1:return None
    people=list(dict.fromkeys(h for h in page.get('headings',[]) if _person_name(h)))
    if not people:people=list(dict.fromkeys(h for h in page.get('contact_headings',[]) if _person_name(h)))
    if len(people)!=1:return None
    name=people[0]; text=page.get('text','');host=(urlsplit(page['url']).hostname or '').removeprefix('www.')
    for heading in re.finditer(r'(?m)^'+re.escape(name)+r'\s*$',text):
        after=text[heading.end():heading.end()+220]
        lines=after.strip().splitlines()
        role=next((line.strip() for line in lines[:3] if legal_role(line.strip()) or re.fullmatch(
            r'(?:Operations(?: and HR)? Manager|Head of Operations|Chief Operating Officer|Office Administrator|Founder|Owner)',line.strip(),re.I)),None)
        if not role:continue
        header_end=text.find(role,heading.end())+len(role)
        header=text[heading.start():header_end]
        for section in re.finditer(r'(?im)^Contact\s*$',text[header_end:]):
            start=header_end+section.start();contact=text[start:start+500]
            emails=list(dict.fromkeys(e for e in EMAIL_PATTERN.findall(contact) if e.rsplit('@',1)[-1].casefold()==host.casefold()))
            if len(emails)!=1:continue
            email=emails[0]
            if any(email in footer for footer in page.get('footer_blocks',[])):continue
            end=contact.index(email)+len(email);quote=contact[:end]
            if re.search(r'\b(?:assistant|secretary|legal PA)\b',quote,re.I):continue
            if any(other!=name and _person_name(other) and other in quote for other in page.get('contact_headings',[])):continue
            return dict(name=name,role=role,email=email,header=header,contact=quote)
    return None


def attorney_roster(page):
    """Count an unpaginated, explicitly labelled attorney-only section.

    This is a published roster count, never represented as an asserted payroll
    total. Mixed 'people' directories and incomplete lists cannot establish size.
    """
    path = urlsplit(page['url']).path.rstrip('/').casefold()
    if not path:
        # Some firms publish their entire attorney menu instead of a separate
        # directory. Each literal name must link to its own same-site profile.
        from .rule_extraction import _person_name
        for block in page.get('contact_blocks',[]):
            lines=block.splitlines()
            if not lines or lines[0] not in {'Attorneys','Our Attorneys','Lawyers','Our Lawyers'} or block not in page.get('text',''):continue
            names=list(dict.fromkeys(lines[1:]))
            if not 1<=len(names)<=100 or not all(_person_name(name) for name in names):continue
            host=(urlsplit(page['url']).hostname or '').removeprefix('www.')
            slugs={re.sub(r'[^a-z]','',urlsplit(link).path.strip('/').rsplit('/',1)[-1].casefold()) for link in page.get('links',[])
                   if (urlsplit(link).hostname or '').removeprefix('www.')==host}
            if all(re.sub(r'[^a-z]','',name.casefold()) in slugs for name in names):
                return {'count':len(names),'excerpt':block[:500],'names':names}
    directory_paths={'/people','/team','/our-team','/the-team','/our-people','/teams','/professionals'}
    if path not in {'/attorneys', '/lawyers', '/our-attorneys', '/our-lawyers',*directory_paths}:
        return None
    text = page.get('text', '')
    if len(text) >= 59000:
        return None
    if re.search(r'\b(?:load more|show more|next page|pagination|page \d+ of)\b', text, re.I):
        return None
    if re.search(r'filter by',text,re.I) and len(re.findall(r'Filter by\n[^\n]{1,50}\nAll\n',text,re.I)) != len(re.findall(r'filter by',text,re.I)):
        return None
    from .rule_extraction import _person_name
    if path in directory_paths:
        lines=text.splitlines()
        entries=[dict(name=lines[i].strip(),role=lines[i+1].strip(),excerpt='\n'.join(lines[i:i+2])) for i in range(len(lines)-1)
                 if (_person_name(lines[i].strip()) or _person_name(re.sub(r'[“”"�]','',lines[i].strip())))
                 and legal_role(lines[i+1].strip())]
        for line in lines:
            pair=re.split(r'\s+-\s+',line,maxsplit=1)
            if len(pair)==2 and _person_name(pair[0]) and legal_role(pair[1]):
                entries.append(dict(name=pair[0],role=pair[1],excerpt=line))
        legal={entry['name']:entry for entry in entries if legal_role(entry['role'])}
        directory_heading=any(re.fullmatch(r'(?:Our )?(?:People|Team|Professionals)',h.strip().rstrip('.'),re.I) for h in page.get('contact_headings',[]))
        if 1 <= len(legal) <= 100 and (directory_heading or re.search(r'\b(?:our (?:partner )?team|our people|our professionals|our attorneys|our lawyers|meet the team|meet the [^\n]{2,60} professionals)\b',text,re.I)):
            first=next(iter(legal.values()))
            return {'count':len(legal),'excerpt':first['excerpt'],'names':list(legal)}
        return None
    lines = text.splitlines()
    starts = [i for i, value in enumerate(lines) if value.strip().casefold() in {'attorneys', 'lawyers', 'our attorneys', 'our lawyers', 'meet our attorneys', 'meet our lawyers'}]
    candidates = []
    for start in starts:
        end = next((i for i in range(start + 1, len(lines)) if re.fullmatch(
            r'(?:professional staff|support staff|administrative staff|our staff|staff|contact(?: us)?|follow|sf office|nyc office|practice areas|published business structured data:)', lines[i].strip(), re.I)), len(lines))
        names = list(dict.fromkeys(value.strip() for value in lines[start + 1:end] if _person_name(value.strip())))
        # Names must also be headings or immediately paired with a literal email
        # on the roster. Incidental prose/name mentions are not roster entries.
        headings = set(page.get('contact_headings', []))
        names = [name for name in names if name in headings or re.search(
            re.escape(name) + r'\s+[^\s@]+@[^\s@]+\.[A-Za-z]{2,63}', text)]
        if 1 <= len(names) <= 100:
            excerpt = '\n'.join(lines[start:min(end, start + 14)])[:500].rstrip()
            candidates.append({'count': len(names), 'excerpt': excerpt, 'names': names})
    return max(candidates, key=lambda item: item['count']) if candidates else None


def postal_country(page):
    """Recognize supported complete postal addresses, never a state alone."""
    text = page.get('text', '')
    patterns = {
        'US': r'\b\d{1,6} [^\n]{2,100}\n(?:[^\n]{1,80}\n){0,2}[A-Za-z .\'-]{2,60},?\s+(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\s+\d{5}(?:-\d{4})?\b',
        'CA': r'\b\d{1,6} [^\n]{2,100}\n(?:[^\n]{1,80}\n){0,2}[A-Za-z .\'-]{2,60},?\s+(?:AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\b',
        'GB': r'\b\d{1,5}[A-Za-z]? [^\n]{2,100}\n(?:[^\n]{1,80}\n){0,2}(?:London|Manchester|Birmingham|Bristol|Leeds|Liverpool|Edinburgh|Cardiff|Glasgow|Belfast)[, \n]{1,4}[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',
        'AU': r'\b\d{1,6}[A-Za-z]? [^\n]{2,140}[,\n](?:[^\n]{1,80}\n){0,2}[^\n]{2,60}\b(?:NSW|VIC|QLD|SA|WA|TAS|ACT|NT)\s+\d{4}\b',
    }
    import pycountry
    states='|'.join(re.escape(state.name) for state in pycountry.subdivisions.get(country_code='US') if state.type=='State')
    patterns['US']=patterns['US'].replace('|DC)', '|DC|'+states+')')
    provinces='Alberta|British Columbia|Manitoba|New Brunswick|Newfoundland and Labrador|Nova Scotia|Ontario|Prince Edward Island|Quebec|Saskatchewan|Yukon|Northwest Territories|Nunavut'
    patterns['CA']=patterns['CA'].replace('|YT)', '|YT|'+provinces+')')
    patterns['CA'] += r'|\b\d{1,6} [^\n]{2,140}?,\s*[A-Za-z .\'-]{2,60},?\s*(?:ON|BC|AB|QC|'+provinces+r')\s*,?\s*[A-Z]\d[A-Z]\s?\d[A-Z]\d\b'
    patterns['GB'] += r'|\b\d{1,5}(?:-\d{1,5})?[A-Za-z]? [^\n]{2,100}?,\s*(?:London|Manchester|Birmingham|Bristol|Leeds|Liverpool|Edinburgh|Cardiff|Glasgow|Belfast)\s*,?\s*[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b'
    found = [(code, match.group()) for code, pattern in patterns.items() for match in re.finditer(pattern, text, re.I)]
    return found if len({code for code, _ in found}) == 1 else []
