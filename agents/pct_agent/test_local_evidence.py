import json
import sys
from types import SimpleNamespace

import pytest

from agents.pct_agent import local_evidence as local


def line(i,text,x,y,page=1,width=90):
    return {'id':i,'text':text,'page':page,'rect':[x,y,x+width,y+8]}


def form():
    lines=[line(1,'Applicant',50,100),line(2,'Applicant for',50,120),
           line(3,'All designated States',250,120),line(4,'Name',50,140),
           line(5,'Example Industries Ltd',250,141),line(6,'Address',50,160),
           line(7,'1 Example Road',250,161),line(8,'Germany',250,175),
           line(9,'Nationality (State)',50,190),line(10,'France',250,191),
           line(11,'Telephone No.',50,210),line(12,'+49 123 456789',250,211),
           line(13,'Fax',50,230),line(14,'+49 123 999999',250,231),
           line(15,'E-mail',50,250),line(16,'hello@example.org',250,251),
           line(17,'E-mail authorization',50,270),line(18,'Electronic only',250,271),
           line(19,'Signature',50,400),line(20,'Name',50,420),line(21,'Not Contact',250,421)]
    return {'lines':lines,'pages':[{'page':1,'width':600,'height':800}],'seconds':1}


def test_table_uses_source_owner_excludes_fax_nationality_signature():
    block=local.table_blocks(form())[0]
    assert block=={'role':'applicant','section':1,'name':[5],'address':[7,8],
                   'phone':[12],'email':[16],'country':[8],'entity_type':'company'}


def test_compact_region_keeps_role_heading_not_applicant_for_label():
    lines=local.compact_regions(form())
    assert 1 in {l['id'] for l in lines}


def test_unassigned_email_forces_fallback_instead_of_silently_missing_it():
    scan=form();scan['lines'].append(line(99,'second@example.net',250,600))
    assert local.table_blocks(scan) is None


def test_two_owners_keep_different_blocks():
    scan=form();second=[dict(l,page=2,id=l['id']+100) for l in scan['lines']]
    second[0]['text']='Agent'
    scan['lines']+=second;scan['pages'].append({'page':2,'width':600,'height':800})
    blocks=local.table_blocks(scan)
    assert len(blocks)==2
    assert blocks[0]['role']=='applicant' and blocks[1]['role']=='agent'
    assert blocks[1]['email']==[116]


def test_japanese_contact_heading_with_printed_english_name():
    scan=form();scan['lines'][0]['text']='出願人'
    scan['lines'][1]['text']='右の指定国についての出願人である。'
    scan['lines'][10]['text']='電話番号'
    scan['lines'][12]['text']='ファクシミリ番号'
    scan['lines'][14]['text']='電子メ--ル'
    block=local.table_blocks(scan)[0]
    assert block['role']=='applicant' and block['email']==[16] and block['phone']==[12]
    assert local.policy.APPLICANT_SECTION.search('出願人')


def test_value_agent_does_not_terminate_primary_agent_block():
    scan=form();scan['lines'][0]['text']='Agent or common representative; or'
    scan['lines'] += [line(97,'Agent',250,110),line(98,"Applicant's or agent's file reference",50,60)]
    block=local.table_blocks(scan)[0]
    assert block['section']==1 and block['email']==[16] and block['name']==[5]


def test_wrapped_signature_not_a_contact_heading():
    lines=[line(1,'Signature of applicant, agent or',50,100),line(2,'common representative',50,112)]
    assert local.role_headings(lines,600)==[]


def test_primary_agent_number_preserved_from_margin():
    heading=line(2,'Agent or common representative',90,100)
    margin=line(1,'IV-I',55,100,width=20)
    assert local.source_section(heading,[heading,margin])=='IV-I Agent or common representative'


def test_mapper_rejects_invented_source_ids(monkeypatch):
    block={'role':'applicant','section':1,'name':[999],'email':[],'phone':[],
           'address':[],'country':[],'entity_type':'unknown'}
    monkeypatch.setattr(local,'chat',lambda *a,**kw:({'blocks':[block]},{}))
    with pytest.raises(RuntimeError,match='unknown_source_line'):
        local.map_blocks(form()['lines'])


def setup_crop(monkeypatch,readings,alternate=''):
    monkeypatch.setattr(local,'crop',lambda *a,**kw:b'image')
    monkeypatch.setattr(local.Image,'open',lambda *a:object())
    values=iter(readings)
    monkeypatch.setattr(local,'read_crop',lambda *a,**kw:(next(values),{'seconds':1}))
    monkeypatch.setitem(sys.modules,'winocr',SimpleNamespace(recognize_pil_sync=lambda *a:{'text':alternate}))


def test_exact_email_requires_visual_agreement(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'l1I@example.org','legible':True}])
    lookup={1:line(1,'l1I@example.org',10,10)}
    values,trace=local.verify_value('source.pdf',[1],lookup,'email',tmp_path)
    assert values==['l1I@example.org'] and 'withheld' not in trace


def test_disagreement_is_withheld_not_autocorrected(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'lll@example.org','legible':True}]*2,'l1I@example.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'l1I@example.org',10,10)},'email',tmp_path)
    assert values==[] and 'withheld' in trace


def test_disputed_spelling_needs_two_visual_reads_and_alternate_ocr(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'l1I@example.org','legible':True}]*2,'l1I@example.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'lll@example.org',10,10)},'email',tmp_path)
    assert values==['l1I@example.org'] and len(trace['calls'])==2


def test_second_image_read_agreeing_with_both_ocr_reads_resolves_initial_visual_error(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'lll@example.org','legible':True},
                           {'text':'l1I@example.org','legible':True}],'l1I@example.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'l1I@example.org',10,10)},'email',tmp_path)
    assert values==['l1I@example.org'] and trace.get('resolution')


def test_one_agreeing_ocr_signal_cannot_override_disagreeing_image_reads(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'lll@example.org','legible':True},
                           {'text':'l1I@example.org','legible':True}],'different@example.org')
    values,_=local.verify_value('source.pdf',[1],{1:line(1,'l1I@example.org',10,10)},'email',tmp_path)
    assert values==[]


def test_bounded_third_read_requires_same_value_as_second_and_alternate_ocr(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'MULLER PATENTS','legible':True},
                           {'text':'MÜLLER PATENTS','legible':True},
                           {'text':'MÜLLER PATENTS','legible':True}],'MÜLLER PATENTS')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'MULLFR PATENTS',10,10)},'name',tmp_path)
    assert values==['MÜLLER PATENTS'] and len(trace['calls'])==3


def test_third_read_cannot_accept_unconfirmed_candidate(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'muller@example.org','legible':True},
                           {'text':'mueller@example.org','legible':True},
                           {'text':'mueler@example.org','legible':True}],'mueller@example.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'mullfr@example.org',10,10)},'email',tmp_path)
    assert values==[] and 'withheld' in trace and len(trace['calls'])==3


def test_state_of_nationality_is_not_part_of_the_contact_address():
    scan=form();scan['lines'][8]['text']='State of nationality'
    block=local.table_blocks(scan)[0]
    assert block['address']==[7,8] and block['country']==[8]


def test_german_box_prefix_confirms_role_but_inventor_does_not():
    lines=[line(1,'Feld Nr. 11 ANMELDER',40,20),
           line(2,'Feld Nr. IV ANWALT ODER GEMEINSAMER VERTRETER',40,200),
           line(3,'Feld Nr. III WEITERE ANMELDER UND/ODER ERFINDER',40,400)]
    assert [l['id'] for l in local.role_headings(lines,600)]==[1,2]


def test_illegible_email_never_exports_ocr(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'a@example.org','legible':False}]*2,'a@example.org')
    values,_=local.verify_value('source.pdf',[1],{1:line(1,'a@example.org',10,10)},'email',tmp_path)
    assert values==[]


def test_vision_prompt_does_not_contain_expected_email(monkeypatch):
    captured=[]
    def fake(messages,*a,**kw):captured.extend(messages);return {},{}
    monkeypatch.setattr(local,'chat',fake)
    local.read_crop(b'original pixels','email')
    assert captured[1]['images'] and 'candidate' not in json.dumps(captured).lower()


def test_field_label_cannot_be_exported_as_contact_identity(monkeypatch,tmp_path):
    monkeypatch.setattr(local,'crop',lambda *a,**kw:pytest.fail('A label must not request vision'))
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'Name',10,10)},'name',tmp_path)
    assert values==[] and trace['withheld']=='Field label is not a contact name'


def test_only_unused_additional_names_can_skip_image_verification():
    lookup={1:line(1,'Additional agent(s)',40,20)}
    block={'role':'agent','section':1,'email':[],'phone':[]}
    fields=[SimpleNamespace(role='agent',block_id='primary',kind=k) for k in ['name','email']]
    assert local.redundant_additional_agent(block,lookup,fields)
    assert not local.redundant_additional_agent(block,lookup,fields[:1])
    assert not local.redundant_additional_agent(dict(block,email=[3]),lookup,fields)
    assert not local.redundant_additional_agent(block,{1:line(1,'Agent',40,20)},fields)


def test_omitting_contactless_additional_name_preserves_selected_output(monkeypatch):
    from agents.pct_agent import ai_verifier as ai
    from agents.pct_agent.test_ai_verifier import extraction,field
    monkeypatch.setattr(ai.policy,'email_domain_status',lambda email:'mx')
    primary=[field('mail@example.org',entity='EXAMPLE PATENTS'),
             field('EXAMPLE PATENTS',kind='name',entity='EXAMPLE PATENTS')]
    extra=field('ANOTHER, Agent',kind='name').model_copy(update={
        'block_id':'additional','entity':'ANOTHER, Agent','section':'Additional agents'})
    first=ai.select_contacts(extraction(*primary),ai.load_rules(),[1])
    second=ai.select_contacts(extraction(*primary,extra),ai.load_rules(),[1])
    assert first==second and first['status']=='found' and first['agent_name']=='EXAMPLE PATENTS'


def test_model_cannot_select_role_value_instead_of_actual_heading(monkeypatch):
    scan=form();scan['lines'].append(line(70,'Agent',250,125))
    invalid={'blocks':[{'role':'agent','section':70,'name':[5],'address':[7],
                       'country':[8],'phone':[12],'email':[16],'entity_type':'unknown'}]}
    monkeypatch.setattr(local,'chat',lambda *a,**kw:(invalid,{}))
    with pytest.raises(RuntimeError,match='ollama_source_role_unconfirmed'):
        local.map_blocks(scan['lines'])


def test_email_must_not_be_a_valid_suffix_of_a_malformed_address():
    assert local.exact_values('email','a@b@example.org')==[]
    assert local.exact_values('email','a@example.org; b@example.net')==['a@example.org','b@example.net']
    assert local.exact_values('email','Name <a@example.org>')==['a@example.org']


def test_failure_saves_evidence_and_no_raw_contact_fallback(monkeypatch,tmp_path):
    from agents.pct_agent import ai_verifier
    monkeypatch.setattr(ai_verifier,'verification_revision',lambda:'offline-test')
    source=tmp_path/'input.pdf';source.write_bytes(b'input')
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR',str(tmp_path/'evidence'))
    monkeypatch.setattr(local,'scan_pdf',lambda *a:(_ for _ in ()).throw(RuntimeError('ollama_compact_timeout')))
    result=local.verify(source,{'emails':['unverified@example.org']})
    assert result['status']=='error' and result['emails']==[]
    assert 'ollama_compact_timeout' in result['reason']
    assert json.loads(__import__('pathlib').Path(result['evidence_file']).read_text())['error']=='ollama_compact_timeout'
