"""Synthetic regression cases from the reviewed trial; no customer data."""
import json
from pathlib import Path
import pytest
from agents.pct_agent import ai_verifier as ai, contact_policy as policy, agent
from agents.pct_agent.test_contact_ownership import contact, select
from agents.pct_agent.test_ai_verifier import extraction, field, pdf


def test_phone_with_fax_label_is_excluded_even_if_model_says_phone():
    r=select(contact('phone','+1 212 555 0101',evidence='Telefax: +1 212 555 0101'),contact('email','mail@example.org'))
    assert r['phones']==[] and r['emails']==['mail@example.org']


def test_nonenglish_country_does_not_destroy_contacts():
    r=select(contact('email','mail@example.org'),contact('country','Österreich'))
    assert r['country']=='AT' and r['emails']==['mail@example.org']
    r=select(contact('email','mail@example.org'),contact('country','Uncertain place'))
    assert r['country']=='' and r['emails']==['mail@example.org']


def test_address_format_or_partial_evidence_does_not_destroy_email():
    for evidence in ['Address 1 Main Street City Australia','Address 1 Main Street']:
        r=select(contact('email','mail@example.org'),contact('address','1 Main Street, City, Australia',evidence=evidence))
        assert r['emails']==['mail@example.org']


def test_two_agents_with_identical_contacts_use_complete_primary_block():
    first=[contact('name','Peter Counsel'),contact('email','shared@example.org'),contact('phone','+1 212 555 0100')]
    first=[f.model_copy(update={'section':'IV-1 Agent'}) for f in first]
    second=[f.model_copy(update={'entity':'Other Counsel','value':'Other Counsel' if f.kind=='name' else f.value,
                                'evidence':'Name Other Counsel' if f.kind=='name' else f.evidence,'block_id':'agent2','section':'IV-2 Agent'}) for f in first]
    r=select(*first,*second)
    assert r['status']=='found' and r['contact_owner']=='Peter Counsel'
    assert r['agent_name']=='Peter Counsel'


def test_missing_name_uses_salutation_not_a_fabricated_identity(tmp_path,monkeypatch):
    r=select(contact('email','shared@example.org',entity='[unnamed contact]'))
    assert r['name']==r['agent_name']=='' and r['display_name']=="Sir/Ma'am"
    monkeypatch.setattr(agent,'PCT_OUTPUT_DIR',tmp_path)
    import openpyxl
    path,_=agent.write_pct_reports([dict(r,row=1,patent_id='WO1')])
    assert openpyxl.load_workbook(path).active.cell(2,9).value=="Sir/Ma'am"


def test_shared_applicant_agent_contacts_follow_address_rule():
    fs=[contact('email','same@example.org'),contact('address','1 First Street')]
    for address,role in [('1 First Street','applicant'),('2 Second Street','agent')]:
        app=[contact('email','same@example.org',role='applicant',entity='Applicant',section='II Applicant',block_id='app'),
             contact('address',address,role='applicant',entity='Applicant',section='II Applicant',block_id='app')]
        assert select(*fs,*app)['contact_role']==role


def test_same_email_and_missing_applicant_phone_still_uses_address_rule():
    app=[contact('email','same@example.org',role='applicant',entity='Applicant',section='II Applicant',block_id='app'),
         contact('address','2 Second Street',role='applicant',entity='Applicant',section='II Applicant',block_id='app')]
    r=select(contact('email','same@example.org'),contact('phone','+1 212 555 0100'),
             contact('address','1 First Street'),*app)
    assert r['contact_role']=='agent' and r['phones']==['+1 212 555 0100']


def test_duplicate_contacts_are_marked_only_within_run_without_losing_patents():
    rows=[dict(row=i,patent_id=f'WO{i}',status='found',contact_owner='Example Firm',contact_role='agent',
               emails=['same@example.org'],phones=['+1 212 555 0100'],category='Slf') for i in (1,2)]
    policy.mark_repeated(rows);policy.mark_repeated(rows)
    assert rows[0]['category']=='Slf' and rows[1]['category']=='Repeated'
    assert rows[1]['base_category']=='Slf' and rows[1]['repeated_of']==1
    assert [r['patent_id'] for r in rows]==['WO1','WO2']
    rows[1]['contact_owner']='Different Firm';policy.mark_repeated(rows)
    assert rows[1]['category']=='Slf'


def test_same_applicant_alone_does_not_mean_repeated():
    rows=[dict(row=i,patent_id=f'WO{i}',applicant='Same Applicant',status='not_found') for i in (1,2)]
    policy.mark_repeated(rows)
    assert all(r.get('category')!='Repeated' for r in rows)


def test_two_read_disagreement_withholds_email_but_keeps_matching_phone(tmp_path,monkeypatch):
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR',str(tmp_path/'audit'))
    phone=field('+1 212 555 0100',kind='phone',evidence='Telephone +1 212 555 0100')
    responses=iter([extraction(field('johnl@example.com'),phone),extraction(field('john1@example.com'),phone)])
    monkeypatch.setattr(ai,'_request',lambda *args:next(responses))
    r=ai.verify_contacts(pdf(tmp_path),{})
    assert r['emails']==[] and r['phones']==['+1 212 555 0100']
    assert 'both image readings' in r['reason']


def test_one_reader_missing_contact_is_not_no_info(tmp_path,monkeypatch):
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR',str(tmp_path/'audit'))
    responses=iter([extraction(),extraction(field())])
    monkeypatch.setattr(ai,'_request',lambda *args:next(responses))
    r=ai.verify_contacts(pdf(tmp_path),{})
    assert r['ai_status']=='needs_review' and r['category']!='No Info'


@pytest.mark.parametrize('status',['nxdomain','null_mx','unconfirmed'])
def test_domain_failure_withholds_email(tmp_path,monkeypatch,status):
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR',str(tmp_path/'audit'))
    monkeypatch.setattr(ai,'_request',lambda *args:extraction(field()))
    monkeypatch.setattr(policy,'email_domain_status',lambda email:status)
    r=ai.verify_contacts(pdf(tmp_path),{})
    assert r['emails']==[] and r['ai_status']=='needs_review'
    assert r['email_checks']['johnl@example.com']['mailbox']=='not_tested'


def test_unknown_company_type_does_not_guess_corp():
    assert select(contact('email','mail@example.org',entity_type='unknown'))['category']==''


def test_country_read_from_confirmed_address_tail_only():
    r=select(contact('email','mail@example.org'),contact('address','1 Main Street\nWien\nÖsterreich'))
    assert r['country']=='AT'
    assert policy.address_country('1 Austria Street, London SW1A 1AA')==''


def test_null_mx_is_not_deliverable(monkeypatch):
    from types import SimpleNamespace
    policy._DNS_CACHE.clear()
    monkeypatch.setattr(policy.dns.resolver,'resolve',lambda *a,**kw:[SimpleNamespace(exchange='.')])
    assert policy.email_domain_status('a@example.org')=='null_mx'


def test_ipv6_implicit_mail_routing(monkeypatch):
    policy._DNS_CACHE.clear()
    def resolve(domain,kind,**kw):
        if kind in {'MX','A'}:raise policy.dns.resolver.NoAnswer()
        return ['2001:db8::1']
    monkeypatch.setattr(policy.dns.resolver,'resolve',resolve)
    assert policy.email_domain_status('a@example.org')=='implicit_mx'


def test_transient_dns_failure_is_retried(monkeypatch):
    from types import SimpleNamespace
    policy._DNS_CACHE.clear()
    calls=[]
    def resolve(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:raise policy.dns.resolver.LifetimeTimeout()
        return [SimpleNamespace(exchange='mx.example.org.')]
    monkeypatch.setattr(policy.dns.resolver,'resolve',resolve)
    assert policy.email_domain_status('a@example.org')=='mx'
    assert len(calls)==2


def test_dead_local_proxy_falls_back_without_changing_remote_proxies(monkeypatch):
    from agents.pct_agent.browser import _reachable_local_proxy
    import socket
    def unavailable(*args,**kwargs):raise ConnectionRefusedError()
    monkeypatch.setattr(socket,'create_connection',unavailable)
    assert _reachable_local_proxy({'server':'socks5://127.0.0.1:9050'}) is None
    remote={'server':'http://proxy.example.org:8080'}
    assert _reachable_local_proxy(remote)==remote
