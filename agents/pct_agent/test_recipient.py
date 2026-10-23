import copy
import pytest
from agents.pct_agent import recipient, bibliography, signer_evidence, ai_verifier as ai, contact_policy as policy
from agents.pct_agent.test_signer_selection import block


def extraction(fields):
    return ai.VisualExtraction(fields=fields, reviewed_pages=[1,2], uncertainties=[])


def selected(fields):
    x=extraction(fields)
    return x,ai.select_contacts(x,ai.load_rules(),[1,2])


@pytest.mark.parametrize('source,expected', [
    ('GREEN, Dr. Alex','Alex GREEN'), ('Dr . Alex Green','Alex Green'),
    ('Alex Green 2179','Alex Green'), ('EXAMPLE IP, S.L.',''),
    ('EXAMPLE LTD',''), ('person@example.org',''), ('GREEN, Alex; JONES, Sam','')])
def test_person_formatting_does_not_make_a_firm_or_email_into_a_person(source,expected):
    assert recipient.person_name(source,True)==expected


def test_signature_changes_greeting_only_and_keeps_owned_contact_values():
    x,r=selected(block('Example Counsel LLP','contact@example.org',1))
    before=copy.deepcopy(r)
    identity={'name':'Dr. Alex Green','role':'agent','contact_block_id':'contact-1','verified':True}
    recipient.apply(r,x,ai.load_rules(),[identity])
    assert r['display_name']=='Alex Green' and r['category']=='Slf'
    for key in ['emails','phones','contact_owner','agent_name','country','additional_emails']:
        assert r[key]==before[key]


def test_selected_applicant_person_has_priority_over_other_applicant_signer():
    x,r=selected(block('GREEN, Alex','alex@example.org',1,role='applicant'))
    recipient.apply(r,x,ai.load_rules(),[{'name':'Sam Jones','role':'applicant','contact_block_id':'contact-2','verified':True}])
    assert r['display_name']=='Alex GREEN' and r['category']=='Ind'


def test_unrelated_agent_signer_does_not_replace_applicant_greeting():
    x,r=selected(block('Applicant Ltd','applicant@example.org',1,role='applicant')+
                 block('Other Counsel LLP','counsel@example.org',2))
    recipient.apply(r,x,ai.load_rules(),[{'name':'Alex Green','role':'agent','contact_block_id':'contact-2','verified':True}])
    assert r['display_name']=="Sir/Ma'am" and r['category']=='Corp'


def test_shared_email_named_agent_can_supply_greeting_even_when_phones_differ():
    x,r=selected(block('Applicant Ltd','shared@example.org',1,role='applicant')+
                 block('GREEN, Alex','shared@example.org',2))
    assert r['contact_role']=='applicant' and r['display_name']=='Alex GREEN' and r['category']=='Slf'


def test_multiple_signature_people_are_not_arbitrarily_selected():
    x,r=selected(block('Example Counsel LLP','contact@example.org',1))
    recipient.apply(r,x,ai.load_rules(),[{'name':name,'role':'agent','contact_block_id':'contact-1','verified':True}
                                      for name in ['Alex Green','Sam Jones']])
    assert r['name_is_placeholder']


def test_same_company_in_two_roles_can_supply_its_named_representative():
    from agents.pct_agent.test_signer_selection import signature
    fields=block('Example Company Ltd','shared@example.org',1,role='applicant')+block('Example Company Ltd','shared@example.org',2)
    fields += [signature('Example Company Ltd'),signature('Alex Green',kind='signer_name')]
    _,r=selected(fields)
    assert r['contact_role']=='applicant' and r['contact_owner']=='Example Company Ltd'
    assert r['display_name']=='Alex Green' and r['category']=='Slf'


def test_bibliography_capture_rejects_wrong_patent_and_inventor_fallback():
    text='Publication Number\nWO/2026/218037\nApplicants\nExample Ltd\nInventors\nGREEN, Alex\nAgents\nExample Counsel LLP'
    assert bibliography.parse(text,'WO2026000001','https://patentscope.wipo.int/')=={}
    data=bibliography.parse(text,'WO2026218037','https://patentscope.wipo.int/search/en/detail.jsf')
    _,r=selected(block('Example Counsel LLP','contact@example.org',1))
    bibliography.apply(r,{'id':'WO2026218037','_bibliography':data})
    assert r['name_is_placeholder']
    data['sections']['agents']=['GREEN, Alex']
    bibliography.apply(r,{'id':'WO2026218037','_bibliography':data})
    assert r['display_name']=='Alex GREEN'


def test_repeated_email_alone_does_not_mark_distinct_patents_and_owners_repeated():
    rows=[]
    for n,owner in enumerate(['First Counsel LLP','Second Counsel LLP'],1):
        _,r=selected(block(owner,'shared@example.org',n));r.update(row=n,patent_id=f'WO202600000{n}')
        rows.append(r)
    policy.mark_repeated(rows)
    assert all(r['category']=='Slf' for r in rows)


def test_bibliography_accepts_unique_download_name_but_reads_actual_publication():
    class Page:
        url='https://patentscope.wipo.int/search/en/detail.jsf?docId=WO2026218037'
        def locator(self,selector):
            assert selector=='body'
            return self
        def inner_text(self,timeout):
            return 'Publication Number\nWO/2026/218037\nAgents\nGREEN, Alex'
    result=bibliography.capture(Page(),'WO_2026_218037_run-abcd_row12')
    assert result['publication']=='WO2026218037'
    assert bibliography.capture(Page(),'WO_2026_000001_run-abcd_row12')=={}


@pytest.mark.parametrize('heading,name_label,person_label,capacity',[
    ('Unterschrift des Anmelders','Name','Name der unterzeichnenden Person','Eigenschaft'),
    ('出願人、代理人又は共通の代表者の署名','名称','署名者の氏名','権限'),
    ('Firma del solicitante','Nombre','Nombre del firmante','Calidad'),
    ('Signature du déposant','Nom •','Nom du signataire','Qualité'),
])
def test_signature_labels_keep_capacity_out_of_person_field(heading,name_label,person_label,capacity):
    from agents.pct_agent.test_local_evidence import line
    scan={'pages':[{'page':1,'width':600,'height':800}],'lines':[
        line(1,heading,50,100),line(2,name_label,50,120),line(3,'Example LLP',260,120),
        line(4,person_label,50,145),line(5,'Alex Green',260,145),
        line(6,capacity,50,170),line(7,'Agent',260,170)]}
    values=signer_evidence.labelled_values(scan)
    person=next(v for v in values if v['kind']=='signer_name')
    assert person['text']=='Alex Green' and person['bounds']['rect'][3]<170
    owner=next(v for v in values if v['kind']=='signer_entity')
    assert owner['text']=='Example LLP' and owner['block_id']==person['block_id']


def test_signature_name_label_requires_exact_label_and_signature_section():
    assert signer_evidence.NAME_LABEL.fullmatch('Nom •')
    assert not signer_evidence.NAME_LABEL.fullmatch('Nom du destinataire •')
    from agents.pct_agent.test_local_evidence import line
    scan={'pages':[{'page':1,'width':600,'height':800}], 'lines':[
        line(1,'Other contacts',50,100), line(2,'Nom •',50,120),
        line(3,'Unrelated Company',260,120)]}
    assert signer_evidence.labelled_values(scan)==[]
