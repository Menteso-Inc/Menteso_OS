import io
from PIL import Image,ImageDraw
from agents.pct_agent import field_ocr,local_evidence as local
from agents.pct_agent.test_local_evidence import form,line


def reading(first='Example GmbH',second=None,score=.999):
    return {'windows':[{'text':first,'rect':[10,10,200,25]}],
            'rapidocr':[{'text':first if second is None else second,'score':score,'rect':[10,10,200,25]}],
            'width':500,'height':60,'seconds':.2}


def test_email_is_never_accepted_by_the_ocr_gate():
    assert field_ocr.accepted_value('email',reading('a@example.org')) is None
    scan=form();block=local.table_blocks(scan)[0]
    assert field_ocr.bounds_for(scan,block,'email') is None


def test_disagreement_confidence_and_clipping_all_require_vision():
    assert field_ocr.accepted_value('name',reading(second='Examples GmbH')) is None
    assert field_ocr.accepted_value('name',reading(score=.99)) is None
    assert field_ocr.accepted_value('name',reading(score=float('nan'))) is None
    value=reading();value['windows'][0]['rect'][1]=1
    assert field_ocr.accepted_value('name',value) is None
    assert field_ocr.accepted_value('phone',reading('1234')) is None
    assert field_ocr.accepted_value('phone',reading('Fax 0123456789')) is None


def test_full_field_suffix_cannot_be_silently_dropped():
    whole=reading('Example G. M. B. H.','Example')
    assert field_ocr.accepted_value('name',whole) is None
    whole['rapidocr'][0]['text']='Example G. M. B. H.'
    assert field_ocr.accepted_value('name',whole)=='Example G. M. B. H.'


def test_pixel_coverage_detects_both_lines_independently_of_ocr():
    image=Image.new('RGB',(180,80),'white');draw=ImageDraw.Draw(image)
    draw.line((2,0,2,79),fill='black',width=2)
    draw.rectangle((20,10,130,24),fill='black')
    draw.rectangle((20,40,65,54),fill='black')
    regions=field_ocr.line_regions(image)
    assert len(regions)==2 and regions[1][1]==40


def test_pixel_coverage_rejects_clipped_text_and_unexplained_noise():
    image=Image.new('RGB',(180,80),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((20,0,130,14),fill='black')
    assert field_ocr.line_regions(image)==[]
    image=Image.new('RGB',(180,80),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((20,10,130,24),fill='black');draw.rectangle((20,45,24,46),fill='black')
    assert field_ocr.line_regions(image)==[]


def test_field_bounds_cover_unrecognized_second_line_before_next_label():
    scan=form();block=local.table_blocks(scan)[0]
    bounds=field_ocr.bounds_for(scan,block,'name')
    assert bounds and bounds['rect'][1]<=140 and bounds['rect'][3]==159
    assert bounds['rect'][0]<250 and bounds['rect'][2]==599
    # A label inside the value column makes the geometry ambiguous.
    scan['lines'].append(line(99,'Telephone',400,150))
    assert field_ocr.bounds_for(scan,block,'name') is None


def test_unbounded_field_cannot_enable_shortcut():
    scan=form();block=local.table_blocks(scan)[0]
    scan['lines']=[l for l in scan['lines'] if l['rect'][1]<=149]
    assert field_ocr.bounds_for(scan,block,'name') is None


def test_enabled_name_gate_preserves_original_without_model_call(monkeypatch,tmp_path):
    data=io.BytesIO();Image.new('RGB',(500,60),'white').save(data,format='PNG')
    monkeypatch.setattr(local,'crop',lambda *a,**kw:data.getvalue())
    monkeypatch.setenv('PCT_OLLAMA_FIELD_OCR_GATE','true')
    monkeypatch.setattr(field_ocr,'recognize',lambda image:reading())
    monkeypatch.setattr(local,'read_crop',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Redundant model call')))
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'Example GmbH',10,10)},'name',tmp_path,
                                   bounds={'page':1,'rect':[0,0,100,30]})
    assert values==['Example GmbH'] and trace['calls']==[] and trace['field_ocr']


def test_ocr_failure_falls_back_and_email_still_calls_vision(monkeypatch,tmp_path):
    data=io.BytesIO();Image.new('RGB',(500,60),'white').save(data,format='PNG')
    monkeypatch.setattr(local,'crop',lambda *a,**kw:data.getvalue())
    monkeypatch.setenv('PCT_OLLAMA_FIELD_OCR_GATE','true')
    monkeypatch.setattr(field_ocr,'recognize',lambda image:(_ for _ in ()).throw(RuntimeError('OCR unavailable')))
    calls=[]
    def vision(data,kind,*a):calls.append(kind);return {'text':'Example GmbH' if kind=='name' else 'a@example.org','legible':True},{'seconds':1}
    monkeypatch.setattr(local,'read_crop',vision)
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'Example GmbH',10,10)},'name',tmp_path,
                                   bounds={'page':1,'rect':[0,0,100,30]})
    assert values==['Example GmbH'] and trace['field_ocr']['fallback']=='original vision verifier'
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'a@example.org',10,10)},'email',tmp_path)
    assert values==['a@example.org'] and calls==['name','email']
