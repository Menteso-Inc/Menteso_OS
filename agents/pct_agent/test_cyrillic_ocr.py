"""Language fallback cannot invent source roles or silently replace a valid scan."""
import hashlib
import pytest
from agents.pct_agent import cyrillic_ocr as cyrillic, local_evidence as local, contact_policy
from agents.pct_agent.test_local_evidence import line


def scan(heading='Unreadable', confidence=1.0):
    heading_line=line(1,heading,50,100)
    heading_line['ocr_confidence']=confidence
    return {'pages':[{'page':1,'width':600,'height':800}],
            'lines':[heading_line,line(2,'contact@example.org',250,140)],'seconds':2}


def test_cyrillic_model_is_optional_and_requires_exact_pinned_bytes(tmp_path, monkeypatch):
    monkeypatch.delenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL',raising=False)
    assert cyrillic.model_path() is None and cyrillic.cache_material()['enabled'] is False
    path=tmp_path/'model.onnx';path.write_bytes(b'wrong model')
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL',str(path))
    with pytest.raises(RuntimeError,match='model_unverified'):cyrillic.model_path()
    monkeypatch.setattr(cyrillic,'MODEL_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    assert cyrillic.model_path()==path and cyrillic.cache_material()['enabled'] is True


@pytest.mark.parametrize('heading', ['Applicant','Agent','ЗАЯВИТЕЛЬ','АГЕНТ ИЛИ ОБЩИЙ ПРЕДСТАВИТЕЛЬ'])
def test_existing_confirmed_role_does_not_trigger_another_scan(monkeypatch,heading):
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL','configured')
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**k:pytest.fail('Unneeded OCR'))
    original=scan(heading)
    chosen,receipt=cyrillic.choose_scan('unused',original,lambda _:None)
    assert chosen is original and receipt is None


@pytest.mark.parametrize('heading,confidence,accepted', [
    ('ЗАЯВИТЕЛЬ',.986,True), ('АГЕНТ ИЛИ ОБЩИЙ ПРЕДСТАВИТЕЛЬ',.98,True),
    ('ЗАЯВИТЕЛЬ',.8,False), ('ЗАЯВИТЕЛЬ',float('nan'),False),
    ('Подпись заявителя',.99,False),('Заявитель просит рассмотреть',.99,False),
    ('ИЗОБРЕТАТЕЛЬ',.99,False),('Applicant',.99,False)])
def test_only_confident_exact_cyrillic_role_can_select_fallback(monkeypatch,heading,confidence,accepted):
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL','configured')
    monkeypatch.setattr(cyrillic,'cache_material',lambda:{'enabled':True,'sha256':'fixture'})
    candidate=scan(heading,confidence);original=scan()
    def read(*a,**k):
        assert k=={'secondary':True,'cyrillic':True}
        return candidate
    monkeypatch.setattr(local,'scan_pdf',read)
    chosen,receipt=cyrillic.choose_scan('unused',original,lambda _:None)
    assert receipt['selected'] is accepted
    assert chosen is (candidate if accepted else original)
    assert chosen['seconds']==(4 if accepted else 2)


def test_cyrillic_scan_cannot_drop_original_pages(monkeypatch):
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL','configured')
    monkeypatch.setattr(cyrillic,'cache_material',lambda:{'enabled':True})
    candidate=scan('ЗАЯВИТЕЛЬ');original=scan()
    original['pages'].append({'page':2,'width':600,'height':800})
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**k:candidate)
    with pytest.raises(RuntimeError,match='incomplete_pages'):
        cyrillic.choose_scan('unused',original,lambda _:None)


def test_losing_declared_agent_role_cannot_merge_its_contacts_into_applicant(monkeypatch):
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL','configured')
    monkeypatch.setattr(cyrillic,'cache_material',lambda:{'enabled':True})
    original=scan();candidate=scan('ЗАЯВИТЕЛЬ')
    candidate['lines'].append(line(3,'Графа IV',50,250))
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**k:candidate)
    chosen,receipt=cyrillic.choose_scan('unused',original,lambda _:None)
    assert chosen is original and receipt['selected'] is False
    assert receipt['unconfirmed_declared_roles']==[{'page':1,'box':'IV'}]
    candidate['lines'].append(line(4,'АГЕНТ',120,250))
    chosen,receipt=cyrillic.choose_scan('unused',original,lambda _:None)
    assert chosen is candidate and receipt['selected'] is True


def test_cyrillic_roles_and_fax_have_distinct_policy_labels():
    assert contact_policy.APPLICANT_SECTION.search('ЗАЯВИТЕЛЬ')
    assert not contact_policy.AGENT_SECTION.search('ЗАЯВИТЕЛЬ')
    assert contact_policy.AGENT_SECTION.search('АГЕНТ ИЛИ ОБЩИЙ ПРЕДСТАВИТЕЛЬ')
    assert not contact_policy.APPLICANT_SECTION.search('АГЕНТ')
    assert contact_policy.FAX_LABEL.search('Факс №')


def test_cyrillic_scan_must_preserve_every_original_email_region(monkeypatch):
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL','configured')
    monkeypatch.setattr(cyrillic,'cache_material',lambda:{'enabled':True})
    original=scan();candidate=scan('ЗАЯВИТЕЛЬ')
    candidate['lines']=[candidate['lines'][0]]
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**k:candidate)
    chosen,receipt=cyrillic.choose_scan('unused',original,lambda _:None)
    assert chosen is original and receipt['selected'] is False
    assert receipt['preserved_email_regions'] is False


def test_classic_agent_correspondence_header_is_exact_not_signature_or_prose():
    header='АГЕНТ ИЛИ ОБЩИЙ ПРЕДСТАВИТЕЛЬ; ИЛИ АДРЕС ДЛЯ ПЕРЕПИСКИ'
    assert local.CYRILLIC_ROLE_HEADING.fullmatch(header)
    assert local.role_headings(scan(header)['lines'],600)
    assert not local.CYRILLIC_ROLE_HEADING.fullmatch('ПОДПИСЬ '+header)
    assert not local.CYRILLIC_ROLE_HEADING.fullmatch('АДРЕС ДЛЯ ПЕРЕПИСКИ')


@pytest.mark.parametrize('text,confidence,accepted',[
    ('ЗАЯВИТЕЛЬ',.98,True),('ЗАЯВИТЕЛЬ',.94,False),
    ('АГЕНТ',.99,False),('ЗАЯВИТЕЛЬ',float('nan'),False)])
def test_borderline_role_needs_matching_confident_original_crop(monkeypatch,text,confidence,accepted):
    candidate=scan('ЗАЯВИТЕЛЬ',.94)
    monkeypatch.setattr(cyrillic,'read_heading_crop',lambda *a:({'lines':[
        {'text':text,'confidence':confidence}]},'original-pixel-digest'))
    proof=cyrillic.refine_role_headings('unused',candidate)
    assert proof[0]['matching_read'] is accepted
    assert candidate['lines'][0]['ocr_confidence']==(.98 if accepted else .94)


def test_uncertain_applicant_cannot_disappear_when_agent_header_is_readable(monkeypatch):
    monkeypatch.setenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL','configured')
    monkeypatch.setattr(cyrillic,'cache_material',lambda:{'enabled':True})
    candidate=scan('ЗАЯВИТЕЛЬ',.8)
    candidate['lines'].append(line(3,'АГЕНТ',50,300))
    original=scan()
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**k:candidate)
    chosen,receipt=cyrillic.choose_scan('unused',original,lambda _:None)
    assert chosen is original and receipt['selected'] is False
    assert receipt['unconfirmed_role_heading_ids']==[1]
