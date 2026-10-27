import copy
import pytest
from agents.pct_agent import recovery as r


def sample(count=500):
    sources=[{'id':f'WO/2025/{i:06}','title':f'Example {i}','appl_no':f'XX/{i}',
              'applicant':'Example applicant','researcher':'Tester','priority_date':'2026'} for i in range(count)]
    rows=[{'row':i+1,'status':'found','emails':[f'row{i}@example.org'],'phones':[],
           **{k:source[v] for k,v in r.IDENTITY.items()}} for i,source in enumerate(sources)]
    return sources,rows


def test_five_hundred_rows_survive_partial_retry_and_retain_source_order():
    sources,rows=sample();rows[4].update(status='error',emails=[])
    before=copy.deepcopy(rows);prior=rows[:490]
    indices=r.retry_indices(sources,prior)
    assert indices==[5,*range(491,501)]
    retry=copy.deepcopy([rows[i-1] for i in indices])
    for i,row in enumerate(retry,1):row.update(row=i,status='found',emails=['verified@example.org'])
    merged,audit=r.merge_results(sources,prior,retry,indices)
    assert [row['row'] for row in merged]==list(range(1,501))
    assert r.coverage(sources,merged)['processed']==500
    assert r.coverage(sources,merged)['found']==500
    assert merged[0]==before[0] and rows==before and len(audit)==11


def test_failed_retry_never_erases_saved_contact():
    sources,prior=sample(2);retry=copy.deepcopy(prior[0]);retry.update(status='error',emails=[])
    merged,audit=r.merge_results(sources,prior,[retry],[1])
    assert merged==prior and audit[0]['action']=='retain_prior_contacts'


def test_retry_email_change_requires_review_instead_of_losing_old_email():
    sources,prior=sample(2);retry=copy.deepcopy(prior[0]);retry['emails']=['different@example.org']
    merged,audit=r.merge_results(sources,prior,[retry],[1])
    assert merged==prior and audit[0]['action']=='retain_prior_contacts'


def test_wrong_patent_or_duplicate_rows_cannot_be_merged():
    sources,prior=sample(2)
    with pytest.raises(ValueError,match='identity'):r.merge_results(sources,prior,[prior[0]],[2])
    with pytest.raises(ValueError,match='duplicate'):r.merge_results(sources,prior,[prior[0],prior[0]],[1])
    with pytest.raises(ValueError,match='mapping'):r.merge_results(sources,prior,[],[1,1])


def test_unprocessed_rows_are_not_reported_as_completed_or_not_found():
    sources,prior=sample(500);summary=r.coverage(sources,prior[:280])
    assert summary['processed']==280 and len(summary['unprocessed_rows'])==220
    assert summary['not_found']==0


def test_phone_only_row_with_transient_dns_failure_is_retried():
    sources,prior=sample(2)
    prior[0].update(emails=[],phones=['123456789'],reason='Email withheld: domain mail routing unconfirmed')
    assert r.retry_indices(sources,prior)==[1]


def test_retry_workbook_contains_no_previously_collected_answers(tmp_path):
    from agents.pct_agent.agent import read_input_excel
    import openpyxl
    sources,prior=sample(3);target=tmp_path/'retry.xlsx'
    r.write_retry_input(sources,[3,1],target)
    parsed=read_input_excel(target)
    assert [v['id'] for v in parsed]==[sources[2]['id'],sources[0]['id']]
    wb=openpyxl.load_workbook(target)
    assert 'Email' not in [c.value for c in wb.active[1]]
    assert wb.active.max_row==3;wb.close()
