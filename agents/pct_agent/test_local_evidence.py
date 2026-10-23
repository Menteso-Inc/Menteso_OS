import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.pct_agent import local_evidence as local


@pytest.mark.parametrize('scale', [1, 2, 4])
def test_waiting_for_shared_slot_does_not_consume_model_deadline(monkeypatch, scale):
    monkeypatch.setenv('PCT_OLLAMA_COMPACT_TIMEOUT_SCALE', str(scale))
    clock = {'now': 0.0}
    class Slot:
        def __enter__(self): clock['now'] += 200
        def __exit__(self, *args): pass
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_lines(self):
            clock['now'] += 1
            yield json.dumps({'message': {'content': '{}'}, 'done': True,
                              'done_reason': 'stop'}).encode()
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            assert kwargs['timeout'] == (10, 180 * scale)
            return Response()
    monkeypatch.setattr(local, '_LOCK', Slot())
    monkeypatch.setattr(local.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(local.requests, 'Session', Session)
    monkeypatch.setattr(local.ollama_provider, 'settings', lambda: {
        'model': 'offline', 'num_thread': 4, 'base_url': 'http://127.0.0.1:11434'})
    monkeypatch.setattr(local.ollama_provider, 'model_identity', lambda c: {})
    value, meta = local.chat([{'content': 'Read source'}], {}, timeout=180)
    assert value == {}
    assert meta['queue_seconds'] == 200 and meta['request_seconds'] == 1
    assert meta['seconds'] == 201 and meta['first_token_seconds'] == 1


@pytest.mark.parametrize('value', ['nan', 'inf', '0', '-1', '5', 'bad'])
def test_invalid_compact_timeout_scale_refused_before_request(monkeypatch, value):
    monkeypatch.setenv('PCT_OLLAMA_COMPACT_TIMEOUT_SCALE', value)
    monkeypatch.setattr(local.ollama_provider, 'settings', lambda: {})
    with pytest.raises(ValueError, match='invalid_ollama_compact_timeout_scale'):
        local.chat([], {})


def test_duplicate_pdf_rows_keep_independent_evidence_files(tmp_path, monkeypatch):
    from agents.pct_agent import ai_verifier
    source = tmp_path/'same.pdf'
    source.write_bytes(b'identical original PDF bytes')
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR', str(tmp_path/'evidence'))
    monkeypatch.setattr(ai_verifier, 'verification_revision', lambda:'offline')
    def unavailable(*args):raise RuntimeError('ollama_offline_fixture')
    monkeypatch.setattr(local, 'scan_pdf', unavailable)
    first = local.verify(source, {}, context={'_row_idx':1})
    original = Path(first['evidence_file']).read_bytes()
    second = local.verify(source, {}, context={'_row_idx':2})
    assert first['evidence_file'] != second['evidence_file']
    assert Path(first['evidence_file']).read_bytes() == original
    assert Path(first['evidence_file']).parent.joinpath('source.pdf').read_bytes() == source.read_bytes()


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


def inventor_form(role):
    scan=form()
    scan['lines'] += [line(101,'Applicant and/or inventor',50,600),
                      line(102,'This person is',50,620),line(103,role,250,621),
                      line(104,'inventor@example.net',250,660)]
    return scan


def test_explicit_inventor_only_email_does_not_invalidate_valid_applicant():
    scan=inventor_form('Inventor only')
    assert local.required_email_ids(scan)=={16}
    assert local.table_blocks(scan)[0]['email']==[16]
    proof=local.excluded_inventor_regions(scan)[0]
    assert proof['role_label_id']==102 and proof['role_value_id']==103 and proof['email_ids']==[104]


def test_combined_role_without_inventor_only_confirmation_remains_required():
    for role in ['Applicant only','Applicant and inventor','Unknown']:
        scan=inventor_form(role)
        assert local.required_email_ids(scan)=={16,104}
        assert local.table_blocks(scan) is None


def test_inventor_role_from_other_position_cannot_exclude_an_email():
    scan=inventor_form('Inventor only');scan['lines'][-2]['rect'][1]+=20
    assert 104 in local.required_email_ids(scan)


def test_explicit_applicant_and_inventor_remains_an_applicant():
    scan=inventor_form('Applicant and inventor')
    scan['lines'] += [line(105,'Name',50,640),line(106,'SECOND, Applicant',250,641),line(107,'E-mail',50,659)]
    headings=local.role_headings(scan['lines'],600)
    assert 101 in {h['id'] for h in headings}
    proof=local.confirmed_combined_applicants(scan['lines'],600)
    assert proof[0]['role_label_id']==102 and proof[0]['role_value_id']==103
    blocks=local.table_blocks(scan)
    assert blocks[-1]['role']=='applicant' and blocks[-1]['email']==[104]


def test_inventor_only_or_unaligned_role_cannot_authorize_combined_applicant():
    scan=inventor_form('Inventor only')
    assert not local.confirmed_combined_applicants(scan['lines'],600)
    scan=inventor_form('Applicant and inventor');scan['lines'][-2]['rect'][1]+=20
    assert not local.confirmed_combined_applicants(scan['lines'],600)


@pytest.mark.parametrize('role', ['Apenas requerente', 'Requerente e inventor'])
def test_portuguese_combined_role_requires_printed_applicant_value(role):
    scan=inventor_form(role)
    scan['lines'][-4]['text']='Requerente e/ou inventor'
    scan['lines'][-3]['text']='Esta pessoa é:'
    scan['lines'] += [line(105,'Nome',50,640),line(106,'SECOND, Applicant',250,641),line(107,'E-mail',50,659)]
    proof=local.confirmed_combined_applicants(scan['lines'],600)
    assert proof[0]['heading_id']==101 and proof[0]['role_value_id']==103
    assert local.table_blocks(scan)[-1]['email']==[104]


@pytest.mark.parametrize('role', ['Apenas inventor', 'Desconhecido', 'Requerente para'])
def test_portuguese_inventor_or_unknown_role_is_not_an_applicant(role):
    scan=inventor_form(role)
    scan['lines'][-4]['text']='Requerente e/ou inventor'
    scan['lines'][-3]['text']='Esta pessoa é:'
    assert not local.confirmed_combined_applicants(scan['lines'],600)


def test_portuguese_role_requires_same_row_value():
    scan=inventor_form('Requerente e inventor')
    scan['lines'][-4]['text']='Requerente e/ou inventor'
    scan['lines'][-3]['text']='Esta pessoa é:'
    scan['lines'][-2]['rect'][1]+=20
    assert not local.confirmed_combined_applicants(scan['lines'],600)


def test_portuguese_inventor_email_excluded_only_with_aligned_explicit_role():
    scan=inventor_form('Apenas inventor')
    scan['lines'][-4]['text']='Requerente e/ou inventor'
    scan['lines'][-3]['text']='Esta pessoa é:'
    proof=local.excluded_inventor_regions(scan)
    assert proof[0]['role_value_id']==103 and proof[0]['email_ids']==[104]
    assert local.required_email_ids(scan)=={16}
    scan['lines'][-2]['rect'][1]+=20
    assert local.required_email_ids(scan)=={16,104}


@pytest.mark.parametrize('role', ['Déposant seulement','Déposant et inventeur'])
def test_french_combined_applicant_requires_explicit_aligned_role(role):
    scan=inventor_form(role)
    scan['lines'][-4]['text']='Déposant et/ou inventeur'
    scan['lines'][-3]['text']='Cette personne est :'
    assert local.confirmed_combined_applicants(scan['lines'],600)[0]['role_value_id']==103
    scan['lines'][-2]['rect'][1]+=20
    assert not local.confirmed_combined_applicants(scan['lines'],600)


@pytest.mark.parametrize('role,excluded', [('Inventeur seulement',True),
    ('Déposant et inventeur',False),('Inconnu',False)])
def test_french_inventor_only_email_is_excluded_only_with_printed_proof(role,excluded):
    scan=inventor_form(role)
    scan['lines'][-4]['text']='Déposant et/ou inventeur'
    scan['lines'][-3]['text']='Cette personne est :'
    assert bool(local.excluded_inventor_regions(scan)) is excluded
    assert (104 not in local.required_email_ids(scan)) is excluded
    scan['lines'][-2]['rect'][1]+=20
    assert 104 in local.required_email_ids(scan)


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


def test_spanish_contact_labels_exclude_heading_wrap_and_narrative():
    scan=form();scan['lines'][0]['text']='Mandatario o representante común; o'
    scan['lines'][1]['text']='solicitante(s) ante las administraciones'
    scan['lines'][3]['text']='Nombre (APELLIDOS, Nombre)'
    scan['lines'][5]['text']='Direcciön'
    scan['lines'][10]['text']='No. de teléfono'
    scan['lines'][14]['text']='Correo electrönico'
    scan['lines'].append(line(70,'dirección para la correspondencia',50,110))
    block=local.table_blocks(scan)[0]
    assert block['role']=='agent' and block['email']==[16] and block['phone']==[12]
    assert block['name']==[5] and block['address']==[7,8]


def test_french_contact_labels_keep_country_separate_from_nationality():
    scan=form();scan['lines'][0]['text']='Déposant'
    scan['lines'][1]['text']='Déposant pour :'
    scan['lines'][3]['text']='Nom:'
    scan['lines'][5]['text']='Adresse :'
    scan['lines'][8]['text']="Nationalité (nom de l'État) :"
    scan['lines'][10]['text']='n° de téléphone :'
    scan['lines'][14]['text']='Courrier électronique :'
    block=local.table_blocks(scan)[0]
    assert block['role']=='applicant' and block['country']==[8]
    assert block['email']==[16] and block['phone']==[12]
    assert local.policy.APPLICANT_SECTION.search('Déposant')


def test_spanish_combined_inventor_section_ends_preceding_applicant_block():
    scan=form();scan['lines'][0]['text']='Solicitante'
    scan['lines'][18]['text']='Solicitante y/o inventor'
    blocks=local.table_blocks(scan)
    assert len(blocks)==1 and blocks[0]['name']==[5] and blocks[0]['email']==[16]
    scan['lines'].append(line(99,'unassigned@example.net',250,450))
    assert local.table_blocks(scan) is None


def test_portuguese_form_maps_email_separately_from_address_and_fax():
    scan=form();scan['lines'][0]['text']='Requerente'
    scan['lines'][1]['text']='Requerente para'
    scan['lines'][3]['text']='Nome'
    scan['lines'][5]['text']='Endereço'
    scan['lines'][7]['text']='Brasil'
    scan['lines'][8]['text']='Nacionalidade (nome do Estado)'
    scan['lines'][10]['text']='No. de telefone'
    scan['lines'][12]['text']='No. de fax'
    scan['lines'][14]['text']='Endereço de correio electrónico'
    block=local.table_blocks(scan)[0]
    assert block['email']==[16] and block['phone']==[12] and block['address']==[7,8]
    assert block['country']==[8] and local.policy.country_code('Brasil')=='BR'
    assert local.policy.address_country('Rio de Janeiro Brasil')=='BR'


def test_portuguese_agent_heading_and_combined_inventor_boundary():
    scan=form();scan['lines'][0]['text']='Mandatário ou representante comun;'
    scan['lines'][18]['text']='Requerente e/ou inventor'
    scan['lines'].append(line(70,'nome do(s) requerente(s) perante as',50,110))
    blocks=local.table_blocks(scan)
    assert len(blocks)==1 and blocks[0]['role']=='agent' and blocks[0]['name']==[5]
    assert local.policy.AGENT_SECTION.search('Mandatário')


def test_portuguese_wrapped_signature_is_not_an_agent_heading():
    lines=[line(1,'Assinatura do requerente,',50,100),line(2,'mandatário ou do representante',50,112)]
    assert local.role_headings(lines,600)==[]


def test_second_ocr_cannot_erase_an_email_region():
    primary=form();alternate=form()
    assert local.preserves_email_regions(primary,alternate)
    alternate['lines'][15]['page']=2
    assert not local.preserves_email_regions(primary,alternate)
    alternate=form();alternate['lines'][15]['rect'][1]+=30
    alternate['lines'][15]['rect'][3]+=30
    assert not local.preserves_email_regions(primary,alternate)


def test_ambiguous_layout_uses_bounded_second_scan_and_records_time(monkeypatch):
    primary=form();primary['lines'][0]['text']='Damaged heading';primary['engine']='windows_en'
    alternate=form();alternate['engine']='rapidocr';alternate['seconds']=3
    monkeypatch.setenv('PCT_OLLAMA_SECONDARY_OCR','true')
    calls=[]
    def scan(path,secondary=False,page_numbers=None):calls.append((secondary,page_numbers));return alternate
    monkeypatch.setattr(local,'scan_pdf',scan)
    selected,audit=local.choose_source_scan('original.pdf',primary,lambda m:None)
    assert selected['lines']==alternate['lines'] and calls==[(True,[1])] and selected['seconds']==4
    assert audit['used'] and audit['preserved_email_regions']


def test_second_ocr_keeps_clear_pages_and_unique_source_ids(monkeypatch):
    primary=form();primary['engine']='windows_en'
    second=[dict(l,page=2,id=l['id']+100) for l in primary['lines']]
    second[0]['text']='Damaged heading'
    primary['lines']+=second
    primary['pages'].append({'page':2,'width':600,'height':800})
    alternate=form();alternate['lines']=[dict(l,page=2) for l in alternate['lines']]
    alternate['pages']=[{'page':2,'width':600,'height':800}];alternate['seconds']=3
    monkeypatch.setenv('PCT_OLLAMA_SECONDARY_OCR','true')
    called=[]
    def scan(path,**kwargs):called.append(kwargs['page_numbers']);return alternate
    monkeypatch.setattr(local,'scan_pdf',scan)
    selected,audit=local.choose_source_scan('source.pdf',primary,lambda m:None)
    assert called==[[2]] and audit['primary_pages_retained']==[1]
    assert [l['text'] for l in selected['lines'] if l['page']==1]==[l['text'] for l in primary['lines'] if l['page']==1]
    assert len({l['id'] for l in selected['lines']})==len(selected['lines'])
    assert selected['engine']=='mixed_windows_rapidocr' and audit['preserved_email_regions']


def test_second_ocr_cannot_silently_drop_an_email_region(monkeypatch):
    primary=form();primary['engine']='windows_en';primary['lines'][0]['text']='Damaged heading'
    alternate=form();alternate['lines']=[l for l in alternate['lines'] if '@' not in l['text']];alternate['seconds']=2
    monkeypatch.setenv('PCT_OLLAMA_SECONDARY_OCR','true')
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**kw:alternate)
    selected,audit=local.choose_source_scan('source.pdf',primary,lambda m:None)
    assert selected is primary and not audit['used'] and not audit['preserved_email_regions']


def test_clear_layout_does_not_repeat_ocr(monkeypatch):
    primary=form();primary['engine']='windows_en'
    monkeypatch.setenv('PCT_OLLAMA_SECONDARY_OCR','true')
    monkeypatch.setattr(local,'scan_pdf',lambda *a,**k:pytest.fail('Redundant scan'))
    assert local.choose_source_scan('original.pdf',primary,lambda m:None)==(primary,None)


def test_model_layout_calls_cannot_mix_ids_from_different_pages(monkeypatch):
    scan=form();second=[dict(l,page=2,id=l['id']+100) for l in scan['lines']]
    scan['lines']+=second
    calls=[]
    def chat(messages,schema,**kwargs):
        ids=schema['properties']['blocks']['items']['properties']['name']['items']['enum']
        calls.append(ids)
        return {'blocks':[]},{'seconds':1}
    monkeypatch.setattr(local,'chat',chat)
    _,meta=local.map_blocks(scan['lines'])
    assert len(calls)==2 and max(calls[0])<min(calls[1]) and meta['seconds']==2


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


def test_ocr_german_address_label_does_not_extend_contact_name():
    scan=form();scan['lines'][5]['text']='Anschrifi'
    block=local.table_blocks(scan)[0]
    assert block['name']==[5] and block['address']==[7,8] and block['country']==[8]


def test_german_box_prefix_confirms_role_but_inventor_does_not():
    lines=[line(1,'Feld Nr. 11 ANMELDER',40,20),
           line(2,'Feld Nr. IV ANWALT ODER GEMEINSAMER VERTRETER',40,200),
           line(3,'Feld Nr. III WEITERE ANMELDER UND/ODER ERFINDER',40,400)]
    assert [l['id'] for l in local.role_headings(lines,600)]==[1,2]


def test_german_narrative_does_not_cut_off_real_agent_block():
    scan=form();scan['lines'][0]['text']='Anwalt oder gemeinsamer Vertreter'
    scan['lines'].insert(1,line(50,'Anmelder vor den zuständigen inter-',50,115))
    blocks=local.table_blocks(scan)
    assert len(blocks)==1 and blocks[0]['role']=='agent' and blocks[0]['email']==[16]


def test_legacy_email_column_does_not_truncate_owner_below_email():
    lines=[line(1,'ANMELDER',120,300),line(2,'E-Mail-Adresse:',385,320),
           line(3,'mail@example.org',385,335),line(4,'Example GmbH',65,355),
           line(5,'Street 33',65,368),line(6,'Deutschland',65,395),
           line(7,'ANWALT',120,560)]
    scan={'pages':[{'page':1,'width':600,'height':800}],'lines':lines}
    kept={l['id'] for l in local.compact_regions(scan)}
    assert {1,2,3,4,5,6}.issubset(kept)


def test_german_additional_attorney_remains_a_separate_contact_block():
    scan=form();scan['lines'][0]['text']='Anwalt oder gemeinsamer Vertreter'
    second=[dict(l,page=2,id=l['id']+100) for l in scan['lines']]
    second[0]['text']='Weitere(r) Anwalt/Anwälte'
    scan['lines']+=second;scan['pages'].append({'page':2,'width':600,'height':800})
    blocks=local.table_blocks(scan)
    assert [(b['role'],b['name'],b['email']) for b in blocks]==[
        ('agent',[5],[16]),('agent',[105],[116])]


def test_at_sign_company_name_is_not_assumed_to_be_an_email():
    scan=form();scan['lines'][4]['text']='RESEARCH@CREATE LTD'
    regions=local.non_email_name_regions(scan)
    assert len(regions)==1 and regions[0]['line_id']==5 and regions[0]['label_id']==4
    assert local.required_email_ids(scan)=={16}
    scan['lines'][4]['text']='office@example.org Ltd'
    assert not local.non_email_name_regions(scan)
    assert local.required_email_ids(scan)=={5,16}


def test_company_word_in_email_field_cannot_exempt_it():
    scan=form();scan['lines'][15]['text']='RESEARCH@CREATE LTD'
    assert not local.non_email_name_regions(scan)
    assert 16 in local.required_email_ids(scan)


def test_brand_without_legal_suffix_needs_name_label_and_image_confirmation(monkeypatch,tmp_path):
    from agents.pct_agent import ai_verifier as ai
    scan=form();scan['lines'][4]['text']='EXAMPLE@CITY'
    scan['lines'].append(line(99,'UNLABELLED@CITY',250,600))
    assert [r['line_id'] for r in local.non_email_name_regions(scan)]==[5]
    assert local.required_email_ids(scan)=={16,99}
    source=tmp_path/'source.pdf';source.write_bytes(b'original')
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR',str(tmp_path/'evidence'))
    monkeypatch.setattr(ai,'verification_revision',lambda:'offline-test')
    monkeypatch.setattr(local,'scan_pdf',lambda path:scan)
    monkeypatch.setattr(local,'verify_value',lambda *a,**kw:([],{'withheld':'name image unclear'}))
    result=local.verify(source,{})
    assert result['status']=='error' and 'ollama_at_sign_name_unconfirmed' in result['reason']


def test_confirmed_noncontact_marker_page_cannot_abort_other_contact_mapping(monkeypatch):
    calls=[]
    def chat(messages,schema,**kwargs):
        calls.append(messages)
        return {'blocks':[]},{'seconds':1}
    monkeypatch.setattr(local,'chat',chat)
    rows=[{**line(1,'Applicant',50,100),'_contact_marker_required':False},
          {**line(2,'contact@example.org',250,140),'_contact_marker_required':True},
          {**line(3,'EXAMPLE@CITY',250,140),'page':2,'_contact_marker_required':False}]
    local.map_blocks(rows)
    assert len(calls)==1
    # Unconfirmed markers cannot use that exemption.
    rows[-1]['_contact_marker_required']=True
    with pytest.raises(RuntimeError,match='source_role_unconfirmed'):local.map_blocks(rows)


def test_absent_at_sign_is_not_proof_of_noncontact_page():
    rows=[{**line(1,'Email',50,100),'_contact_marker_required':False},
          {**line(2,'illegible source',250,100),'_contact_marker_required':False}]
    with pytest.raises(RuntimeError,match='source_role_unconfirmed'):local.map_blocks(rows)


def test_at_sign_company_name_needs_image_confirmation(monkeypatch,tmp_path):
    from agents.pct_agent import ai_verifier as ai
    scan=form();scan['lines'][4]['text']='RESEARCH@CREATE LTD'
    source=tmp_path/'source.pdf';source.write_bytes(b'original')
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR',str(tmp_path/'evidence'))
    monkeypatch.setattr(ai,'verification_revision',lambda:'offline-test')
    monkeypatch.setattr(local,'scan_pdf',lambda path:scan)
    monkeypatch.setattr(local,'verify_value',lambda *a,**kw:([],{'withheld':'unclear name'}))
    result=local.verify(source,{})
    assert result['status']=='error' and not result['emails']
    assert 'ollama_at_sign_name_unconfirmed' in result['reason']


def test_wrapped_ocr_domain_needs_two_matching_image_reads(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'ip-office@example.org','legible':True}]*2,'ip-office@example\n.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'ip—office@example . org',10,10)},'email',tmp_path)
    assert values==['ip-office@example.org'] and len(trace['calls'])==2


def test_two_image_reads_can_confirm_original_ocr_with_separator_spacing(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'patents.group@example.org','legible':True}]*2,'patents.group@example1.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'patents . group@example . org',10,10)},'email',tmp_path)
    assert values==['patents.group@example.org'] and len(trace['calls'])==2 and trace.get('resolution')


def test_separator_spacing_cannot_hide_disagreement_between_image_reads(monkeypatch,tmp_path):
    setup_crop(monkeypatch,[{'text':'patents.group@example.org','legible':True},
                           {'text':'patents.groups@example.org','legible':True}],'different@example.org')
    values,trace=local.verify_value('source.pdf',[1],{1:line(1,'patents . group@example . org',10,10)},'email',tmp_path)
    assert values==[] and 'withheld' in trace


def test_ocr_separator_join_cannot_correct_letters_or_extra_at():
    assert local.alternate_ocr_values('email','il1 @ example . org')==['il1@example.org']
    assert local.alternate_ocr_values('email','a@b @ example.org')==[]
    assert local.alternate_ocr_values('email','il1@example.org')!=['i11@example.org']


def test_uncertain_applicant_email_cannot_promote_agent_email():
    unresolved=[{'role':'applicant','block_id':'a'}]
    assert local.preferred_email_unconfirmed({'emails':['agent@example.org'],'contact_role':'agent'},unresolved)
    assert not local.preferred_email_unconfirmed({'emails':['applicant@example.org'],'contact_role':'applicant'},unresolved)
    assert not local.preferred_email_unconfirmed({'emails':['agent@example.org'],'contact_role':'agent'},[])


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
