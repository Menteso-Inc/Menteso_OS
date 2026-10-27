"""Auditable retries: original source rows, stable indices and no lost results."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

IDENTITY = {'patent_id':'id','title':'title','appl_no':'appl_no','applicant':'applicant',
            'researcher':'researcher','priority_date':'priority_date'}


def source_rows(path, expected_hash):
    from .agent import read_input_excel
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected_hash:
        raise ValueError('Original input changed; recovery refused')
    return read_input_excel(path)


def check_row(result, sources, index):
    if type(index) is not int or not 1<=index<=len(sources):
        raise ValueError('Invalid original row index')
    if any(result.get(k,'')!=sources[index-1].get(v,'') for k,v in IDENTITY.items()):
        raise ValueError(f'Source identity mismatch at original row {index}')
    if result.get('status') not in {'found','not_found','error'}:
        raise ValueError('An unfinished result cannot replace a saved row')


def journal_rows(path, sources):
    results=[];seen=set()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        if row.get('_meta'):continue
        index=row.get('row');check_row(row,sources,index)
        if index in seen:raise ValueError('Duplicate original row in journal')
        seen.add(index);results.append(row)
    return sorted(results,key=lambda r:r['row'])


def retry_indices(sources, results):
    by_row={row['row']:row for row in results}
    return [i for i in range(1,len(sources)+1)
            if i not in by_row or by_row[i]['status']!='found'
            or 'source readings disagree' in by_row[i].get('reason','')
            or 'Email withheld: domain mail routing unconfirmed' in by_row[i].get('reason','')]


def write_retry_input(sources, indices, path):
    """Only unworked filing metadata goes to extraction, never prior answers."""
    import openpyxl
    if len(set(indices))!=len(indices) or any(type(i) is not int or not 1<=i<=len(sources) for i in indices):
        raise ValueError('Invalid retry indices')
    wb=openpyxl.Workbook();ws=wb.active;ws.title='PCT recovery input'
    keys=['id','title','appl_no','applicant','researcher','priority_date']
    ws.append(['Publication No','Title','Application No.','Applicant','Researcher','Priorty Date'])
    for index in indices:ws.append([sources[index-1].get(k,'') for k in keys])
    wb.save(path);wb.close()


def contact_keys(row):
    from . import contact_policy as policy
    return ({policy.value_key('email',v) for v in policy.result_emails(row)},
            {policy.value_key('phone',v) for v in row.get('phones',[])})


def merge_results(sources, prior, retried, indices):
    """Replace only exact source identities; a worse retry preserves old data."""
    if len(set(indices))!=len(indices) or any(type(i) is not int or not 1<=i<=len(sources) for i in indices):
        raise ValueError('Invalid retry index mapping')
    merged={};audit=[];seen=set()
    for row in prior:
        index=row.get('row');check_row(row,sources,index)
        if index in merged:raise ValueError('Duplicate prior row')
        merged[index]=deepcopy(row)
    for result in retried:
        local_index=result.get('row')
        if type(local_index) is not int or not 1<=local_index<=len(indices) or local_index in seen:
            raise ValueError('Invalid or duplicate retry row')
        seen.add(local_index);index=indices[local_index-1]
        check_row(result,sources,index)
        old=merged.get(index);candidate=deepcopy(result);candidate['row']=index
        action='replace'
        if old and old['status']=='found':
            old_email,old_phone=contact_keys(old);new_email,new_phone=contact_keys(candidate)
            if candidate['status']!='found' or not old_email.issubset(new_email) or not old_phone.issubset(new_phone):
                action='retain_prior_contacts'
        if action=='replace':merged[index]=candidate
        audit.append({'row':index,'action':action,'previous_status':old.get('status') if old else None,
                      'new_status':candidate['status'],'previous_evidence':(old or {}).get('evidence_file'),
                      'new_evidence':candidate.get('evidence_file')})
    return sorted(merged.values(),key=lambda r:r['row']),audit


def coverage(sources, results):
    indices=[r['row'] for r in results]
    if len(indices)!=len(set(indices)):raise ValueError('Duplicate output row')
    for row in results:check_row(row,sources,row['row'])
    return {'total':len(sources),'processed':len(results),
            'found':sum(r['status']=='found' for r in results),
            'not_found':sum(r['status']=='not_found' for r in results),
            'errors':sum(r['status']=='error' for r in results),
            'unprocessed_rows':sorted(set(range(1,len(sources)+1))-set(indices))}
