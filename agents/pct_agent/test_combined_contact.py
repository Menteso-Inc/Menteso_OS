import io
import json
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from agents.pct_agent import combined_contact as batch, local_evidence as local


def image_bytes():
    image=Image.new('RGB',(100,40),'white')
    image.putpixel((30,15),(253,253,253))  # Faint punctuation must survive.
    image.putpixel((55,25),(0,0,0))
    out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()


def scan_and_block():
    lines=[{'id':i,'page':1,'text':text,'rect':rect,'ocr_confidence':1.0}
           for i,text,rect in [
               (1,'Agent',[20,20,75,30]),(2,'Name',[20,40,55,50]),
               (3,'EXAMPLE PERSON',[110,40,230,50]),
               (4,'Telephone',[20,60,80,70]),(5,'+1 202 555 0142',[110,60,215,70]),
               (6,'E-mail',[20,80,70,90]),(7,'person@example.test',[110,80,245,90]),
               (8,'Signature',[20,110,100,120])]]
    return {'pages':[{'page':1,'width':400,'height':500}],'lines':lines}, {
        'role':'agent','section':1,'name':[3],'phone':[5],'email':[7],
        'address':[],'country':[],'entity_type':'individual'}


def prepared(source='person@example.test'):
    return {'result':None,'source':source,'data':image_bytes(),'label':'email-7','field_check':None}


def test_field_images_preserve_original_pixels_and_do_not_embed_ocr_text():
    values={'name':prepared('DO NOT EMBED THIS OCR STRING'),'email':prepared()}
    data,places=batch.field_images(values)
    for index,place in enumerate(places):
        image=Image.open(io.BytesIO(data[index])).convert('RGB')
        original=Image.open(io.BytesIO(values[place['kind']]['data'])).convert('RGB')
        assert image.tobytes()==original.crop(place['retained_rect']).tobytes()
        assert place['image_index']==index+1
        assert place['scale']==1
        assert (253,253,253) in original.crop(place['retained_rect']).getdata()


@pytest.mark.parametrize('change',['page','other_role','reused_ids','unknown_heading'])
def test_eligibility_rejects_mixed_or_unconfirmed_source_regions(change):
    scan,block=scan_and_block()
    assert batch.eligible(scan,block)
    if change=='page':scan['lines'][6]['page']=2
    elif change=='other_role':scan['lines'][7]['rect']=[20,75,100,78]
    elif change=='reused_ids':block['phone']=block['name']
    else:scan['lines'][0]['text']='Agent reference number'
    assert not batch.eligible(scan,block)


@pytest.mark.parametrize('bad',[
    {},{'email':{'text':'a@example.test','legible':'true'}},
    {'email':{'text':'a@example.test','legible':True,'owner':'invented'}},
    {'email':{'text':['a@example.test'],'legible':True}},
    {'email':{'text':'a@example.test','legible':True},'phone':{'text':'123','legible':True}},
])
def test_strict_response_rejects_missing_extra_and_mistyped_fields(bad):
    assert not batch.valid_readings(bad,['email'])


def test_successful_combined_value_still_requires_exact_ocr_agreement(monkeypatch,tmp_path):
    monkeypatch.setattr(local,'read_crop',lambda *a,**k:pytest.fail('No extra call for agreement'))
    result,trace=local.verify_value(None,[7],{},'email',tmp_path,prepared=prepared(),
        initial_read={'reading':{'text':'person@example.test','legible':True},'record_id':'p1-b0'})
    assert result==['person@example.test']
    assert trace['initial_read_ref']=='p1-b0' and trace['calls']==[]


def test_batch_disagreement_uses_fresh_individual_read_and_cannot_guess(monkeypatch,tmp_path):
    monkeypatch.setenv('PCT_OLLAMA_SECONDARY_OCR','false')
    monkeypatch.setitem(sys.modules,'winocr',SimpleNamespace(recognize_pil_sync=lambda *a:{'text':'person@example.test'}))
    monkeypatch.setattr(local,'crop',lambda *a,**k:image_bytes())
    calls=[]
    def read(*args):
        calls.append(args[1]);return {'text':'someone@example.test','legible':True},{'phase':'email image check','seconds':1}
    monkeypatch.setattr(local,'read_crop',read)
    result,trace=local.verify_value(None,[7],{},'email',tmp_path,prepared=prepared(),
        initial_read={'reading':{'text':'wrong@example.test','legible':True},'record_id':'p1-b0'})
    assert result==[] and calls==['email']
    assert trace['withheld']=='Independent source readings disagree'


def test_mismatched_batch_can_recover_only_with_original_independent_rules(monkeypatch,tmp_path):
    monkeypatch.setenv('PCT_OLLAMA_SECONDARY_OCR','false')
    monkeypatch.setitem(sys.modules,'winocr',SimpleNamespace(recognize_pil_sync=lambda *a:{'text':'person@example.test'}))
    monkeypatch.setattr(local,'crop',lambda *a,**k:image_bytes())
    monkeypatch.setattr(local,'read_crop',lambda *a:({'text':'person@example.test','legible':True},{'phase':'email image check'}))
    result,trace=local.verify_value(None,[7],{},'email',tmp_path,prepared=prepared(),
        initial_read={'reading':{'text':'wrong@example.test','legible':True},'record_id':'p1-b0'})
    assert result==['person@example.test']
    assert trace['resolution']=='Second original-image reading agrees with both OCR readings'


def instrument_block(monkeypatch,accepted_kinds=()):
    monkeypatch.setenv('PCT_OLLAMA_FIELD_OCR_GATE','false')
    def prepare(pdf,ids,lookup,kind,*args):
        if kind in accepted_kinds:return {'result':([kind],{'calls':[]})}
        return prepared(lookup[ids[0]]['text'])
    monkeypatch.setattr(local,'prepare_value',prepare)
    used=[]
    def verify(pdf,ids,lookup,kind,*args,**kwargs):
        used.append((kind,kwargs['initial_read']))
        return [kind],{'calls':[]}
    monkeypatch.setattr(local,'verify_value',verify)
    return used


def test_three_fields_share_one_request_and_metadata_is_counted_once(monkeypatch,tmp_path):
    used=instrument_block(monkeypatch);calls=[]
    def read(data,kinds,*args):
        calls.append(kinds)
        return {k:{'text':k,'legible':True} for k in kinds},{'phase':'combined contact image check','seconds':2}
    monkeypatch.setattr(batch,'read_fields',read)
    scan,block=scan_and_block()
    result,record=batch.verify_block(None,scan,block,'p1-b0',tmp_path,lambda _:None)
    assert len(calls)==len(record['calls'])==1
    assert set(result)==set(batch.KINDS)
    assert all(value['record_id']=='p1-b0' for _,value in used)


def test_ocr_accepted_fields_do_not_add_combined_work(monkeypatch,tmp_path):
    used=instrument_block(monkeypatch,accepted_kinds=['name','phone'])
    monkeypatch.setattr(batch,'read_fields',lambda *a:pytest.fail('Only email needs vision'))
    scan,block=scan_and_block()
    _,record=batch.verify_block(None,scan,block,'p1-b0',tmp_path,lambda _:None)
    assert record['fallback']=='fewer_than_two_unresolved_fields'
    assert all(initial is None for _,initial in used)


@pytest.mark.parametrize('failure',['exception','invalid_schema'])
def test_failed_combination_falls_back_for_every_field_and_records_cost(monkeypatch,tmp_path,failure):
    used=instrument_block(monkeypatch)
    def read(*args):
        if failure=='exception':raise RuntimeError('ollama_compact_timeout')
        return {'email':{'text':'person@example.test','legible':True}},{'phase':'combined contact image check','seconds':2}
    monkeypatch.setattr(batch,'read_fields',read)
    scan,block=scan_and_block()
    result,record=batch.verify_block(None,scan,block,'p1-b0',tmp_path,lambda _:None)
    assert set(result)==set(batch.KINDS)
    assert all(initial is None for _,initial in used)
    assert record['attempt_seconds']>=0 and record['combined_fields_used']==[]


def test_prompt_contains_pixels_and_field_names_only(monkeypatch):
    captured={}
    def chat(messages,schema,**kwargs):captured.update(messages=messages,schema=schema);return {'name':None,'email':None},{}
    monkeypatch.setattr(local,'chat',chat)
    batch.read_fields([image_bytes(),image_bytes()],['name','email'])
    serialized=json.dumps(captured)
    assert 'person@example.test' not in serialized
    assert captured['schema']['required']==['name','email']
    assert len(captured['messages'][1]['images'])==2
    assert captured['messages'][1]['content']=='Images in order: 1=name, 2=email.'


def test_compact_response_keeps_uncertainty_and_exact_characters():
    result=batch.normalize_response({'name':None,'phone':'','email':' l1.I-1@example.test '},['name','phone','email'])
    assert result['name']=={'text':'','legible':False}
    assert result['phone']=={'text':'','legible':False}
    assert result['email']=={'text':' l1.I-1@example.test ','legible':True}


@pytest.mark.parametrize('raw',[{'email':True},{'email':123},{'email':['a@example.test']},{'phone':None},{}])
def test_compact_response_rejects_type_or_field_substitution(raw):
    with pytest.raises(ValueError,match='invalid_field_response'):batch.normalize_response(raw,['email'])


def test_mode_changes_verification_fingerprint_and_rejects_invalid_setting(monkeypatch):
    from agents.pct_agent import ai_verifier as ai
    monkeypatch.setenv('PCT_AI_PROVIDER','ollama')
    monkeypatch.setenv('PCT_OLLAMA_DOCUMENT_MODE','source_regions')
    monkeypatch.setenv('PCT_OLLAMA_COMBINED_CONTACTS','false');old=ai.verification_revision()
    monkeypatch.setenv('PCT_OLLAMA_COMBINED_CONTACTS','true');new=ai.verification_revision()
    assert old!=new
    monkeypatch.setenv('PCT_AI_VERIFY','true')
    monkeypatch.setenv('PCT_OLLAMA_COMBINED_CONTACTS','maybe')
    with pytest.raises(ValueError,match='invalid_combined_contacts'):ai.validate_configuration()
