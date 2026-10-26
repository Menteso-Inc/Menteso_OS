"""DNS outages cannot erase independently confirmed source transcriptions."""
import copy

import pytest

from agents.pct_agent import ai_verifier as ai, contact_policy as policy, local_evidence as local
from agents.pct_agent.test_local_evidence import form


def verified_result():
    return {'emails': ['info-ip+patent@example.org'], 'phones': ['+49 123 456789'],
            'contact_owner': 'Example Company', 'contact_role': 'applicant',
            'display_name': 'Example Person', 'status': 'found',
            'additional_emails': [{'email': 'second@example.net', 'role': 'agent',
                                   'owner': 'Example Counsel', 'block_id': 'agent-1'}]}


def test_transient_dns_outage_preserves_primary_additional_and_ownership(monkeypatch):
    result = verified_result()
    original = copy.deepcopy(result)
    calls = []
    policy._DNS_CACHE.clear()
    def timeout(*args, **kwargs):
        calls.append(args)
        raise policy.dns.resolver.LifetimeTimeout()
    monkeypatch.setattr(policy.dns.resolver, 'resolve', timeout)
    issues = policy.check_email_domains(result, source='original_crop_and_ocr_agreement')
    assert len(calls) == 4  # bounded initial lookup and one retry per domain
    assert all(result[key] == value for key, value in original.items())
    assert all(value['domain'] == 'unconfirmed' and value['mailbox'] == 'not_tested'
               for value in result['email_checks'].values())
    assert all('email retained' in issue for issue in issues)


@pytest.mark.parametrize('negative', ['null_mx', 'nxdomain'])
def test_confirmed_negative_still_withholds_only_that_email(monkeypatch, negative):
    result = verified_result()
    monkeypatch.setattr(policy, 'email_domain_status',
                        lambda email: negative if email.endswith('@example.org') else 'unconfirmed')
    issues = policy.check_email_domains(result, source='original_crop_and_ocr_agreement')
    assert result['emails'] == []
    assert result['additional_emails'][0]['email'] == 'second@example.net'
    assert result['phones'] == ['+49 123 456789']
    assert any('Email withheld' in issue for issue in issues)
    assert result['email_checks']['second@example.net']['domain'] == 'unconfirmed'


@pytest.mark.parametrize('confirmed', [True, False])
def test_local_source_pipeline_keeps_confirmed_email_only(monkeypatch, tmp_path, confirmed):
    from agents.pct_agent import cyrillic_ocr, recipient, signer_evidence
    source = tmp_path / 'source.pdf'
    source.write_bytes(b'synthetic source, OCR and vision controlled below')
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR', str(tmp_path / 'evidence'))
    monkeypatch.setenv('PCT_OLLAMA_COMBINED_CONTACTS', 'false')
    monkeypatch.setenv('PCT_OLLAMA_FIELD_OCR_GATE', 'false')
    monkeypatch.setattr(ai, 'verification_revision', lambda: 'routing-test')
    monkeypatch.setattr(local, 'scan_pdf', lambda path: form())
    monkeypatch.setattr(local, 'choose_source_scan', lambda path, primary, step: (primary, None))
    monkeypatch.setattr(cyrillic_ocr, 'choose_scan', lambda path, scan, step: (scan, None))
    monkeypatch.setattr(signer_evidence, 'verify_local', lambda *args: [])
    monkeypatch.setattr(recipient, 'enrich_local', lambda path, scan, extraction, result, *args: result)
    def read(path, ids, lookup, kind, *args, **kwargs):
        values = [] if kind == 'email' and not confirmed else [' '.join(lookup[i]['text'] for i in ids)]
        return values, {'kind': kind, 'source_ids': ids}
    monkeypatch.setattr(local, 'verify_value', read)
    lookups = []
    def unknown(email):
        lookups.append(email)
        return 'unconfirmed'
    monkeypatch.setattr(policy, 'email_domain_status', unknown)
    result = local.verify(source, {'emails': ['UNVERIFIED@example.net']})
    if confirmed:
        assert result['status'] == 'found' and result['emails'] == ['hello@example.org']
        assert result['email_checks']['hello@example.org']['domain'] == 'unconfirmed'
        assert result['email_checks']['hello@example.org']['mailbox'] == 'not_tested'
        assert 'email retained' in result['reason']
    else:
        assert result['emails'] == [] and lookups == []
        assert result['status'] == 'found' and result['phones'] == ['+49 123 456789']
        assert result['email_checks'] == {}
        assert 'email withheld: source readings disagree' in result['reason']


def agent_contact():
    result = verified_result()
    result.update(emails=['agent@example.org'], contact_owner='Example Counsel',
                  contact_role='agent', agent_name='Example Counsel',
                  field_evidence=[{'kind':'email','value':'agent@example.org',
                      'entity':'Example Counsel','role':'agent','legible':True,
                      'block_id':'agent-1','page':2,'section':'IV Agent',
                      'evidence':'agent@example.org'}])
    return result


def test_uncertain_applicant_keeps_verified_agent_details_without_promoting_email():
    result = agent_contact()
    before = copy.deepcopy(result)
    assert local.defer_preferred_email(result, [{'role':'applicant','block_id':'applicant-1'}])
    assert result['emails'] == [] and result['ai_status'] == 'needs_review'
    for key in ['phones','display_name','contact_owner','contact_role','agent_name','status','field_evidence']:
        assert result[key] == before[key]
    assert result['additional_emails'][-1] == {
        'email':'agent@example.org','role':'agent','owner':'Example Counsel',
        'block_id':'agent-1','page':2,'section':'IV Agent','evidence':'agent@example.org'}
    assert result['additional_emails'][0] == before['additional_emails'][0]
    assert not local.defer_preferred_email(result, [{'role':'applicant'}])
    assert len(result['additional_emails']) == 2


def test_uncertain_primary_choice_without_verified_role_evidence_stays_closed():
    result = agent_contact()
    result['field_evidence'][0]['role'] = 'applicant'
    before = copy.deepcopy(result)
    with pytest.raises(RuntimeError, match='ollama_preferred_email_unconfirmed'):
        local.defer_preferred_email(result, [{'role':'applicant'}])
    assert result == before


@pytest.mark.parametrize('change', ['confirmed_signer','no_unresolved_applicant','applicant_selected'])
def test_confirmed_contact_selection_is_unchanged(change):
    result = agent_contact()
    unresolved = [{'role':'applicant'}]
    if change == 'confirmed_signer':result['signer_selection'] = {'status':'confirmed'}
    elif change == 'no_unresolved_applicant':unresolved = [{'role':'agent'}]
    else:result['contact_role'] = 'applicant'
    before = copy.deepcopy(result)
    assert not local.defer_preferred_email(result, unresolved)
    assert result == before
