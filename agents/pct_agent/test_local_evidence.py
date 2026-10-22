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
