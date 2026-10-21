"""Offline provider contract, failure handling and preservation checks."""
import base64
import json
import re
import struct
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from agents.pct_agent import ai_verifier as ai, ollama_provider as local, resume
from agents.pct_agent.test_ai_verifier import extraction, field, pdf


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    import os
    for key in list(os.environ):
        if key.startswith('PCT_OLLAMA_'):
            monkeypatch.delenv(key)
    monkeypatch.setenv('PCT_AI_PROVIDER', 'ollama')
    monkeypatch.delenv('PCT_OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(local, 'model_identity', lambda config=None: {
        'provider': 'ollama', 'model': local.settings()['model'], 'digest': 'a' * 64})


def png(width=100, height=100):
    return b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack('>II', width, height)


def reply(text=None, **changes):
    return {'done': True, 'done_reason': 'stop',
            'message': {'role': 'assistant', 'content': text or extraction(field()).model_dump_json()},
            **changes}


def test_local_configuration_needs_no_openai_key(monkeypatch):
    monkeypatch.setenv('PCT_AI_MODEL', 'gpt-4o')
    ai.validate_configuration(check_api=True)
    assert ai.model_name() == 'qwen3.5:4b'
    monkeypatch.setenv('PCT_AI_PROVIDER', 'openai')
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        ai.validate_configuration()


def test_default_provider_preserves_openai(monkeypatch):
    monkeypatch.delenv('PCT_AI_PROVIDER')
    monkeypatch.delenv('PCT_AI_MODEL', raising=False)
    assert ai.provider_name() == 'openai'
    assert ai.model_name() == 'gpt-4o'
    monkeypatch.setenv('PCT_AI_PROVIDER', 'unexpected')
    with pytest.raises(ValueError, match='pct_ai_invalid_provider'):
        ai.validate_configuration()


def test_local_teaching_preserves_contact_rules_and_uses_only_synthetic_addresses(monkeypatch):
    monkeypatch.setenv('PCT_AI_PROVIDER', 'openai')
    baseline = ai.load_rules()
    monkeypatch.setenv('PCT_AI_PROVIDER', 'ollama')
    taught = ai.load_rules()
    assert taught.model_dump(exclude={'examples'}) == baseline.model_dump(exclude={'examples'})
    assert taught.examples[:len(baseline.examples)] == baseline.examples
    assert len(taught.examples) == len(baseline.examples) + 8
    additions = json.dumps([example.model_dump() for example in taught.examples[len(baseline.examples):]])
    addresses = re.findall(r'[\w.-]+@([\w.-]+\.[a-z]+)', additions)
    assert addresses and all(domain.endswith('.example') or domain in {
        'example.com', 'example.org', 'example.net', 'lighting.example.com'} for domain in addresses)


@pytest.mark.parametrize('url', ['https://ollama.com', 'http://192.168.1.20:11434',
    'http://user:secret@localhost:11434', 'http://localhost:11434/redirect',
    'http://localhost:11434?key=secret', 'http://localhost:notaport', 'http://localhost'])
def test_loopback_transport_rejects_external_or_credential_urls(monkeypatch, url):
    monkeypatch.setenv('PCT_OLLAMA_BASE_URL', url)
    with pytest.raises(ValueError, match='ollama_requires_loopback_url'):
        local.settings()


@pytest.mark.parametrize('model', ['qwen3.5:cloud', 'qwen3.5:397b-cloud'])
def test_cloud_model_names_are_rejected(monkeypatch, model):
    monkeypatch.setenv('PCT_OLLAMA_MODEL', model)
    with pytest.raises(ValueError, match='ollama_requires_local_model'):
        local.settings()


@pytest.mark.parametrize('response,code', [
    (reply(done=False), 'ollama_incomplete_response'),
    (reply(done_reason='length'), 'ollama_incomplete_response'),
    (reply(message={'content': '', 'tool_calls': []}), 'ollama_missing_output'),
    (reply(message={'content': '{}', 'tool_calls': [{}]}), 'ollama_missing_output'),
    (reply(text='not JSON'), 'ollama_invalid_extraction'),
    (reply(text='{"fields": [], "reviewed_pages": [], "uncertainties": []}'), 'ollama_incomplete_page_review'),
])
def test_incomplete_or_malformed_output_cannot_be_accepted(monkeypatch, response, code):
    monkeypatch.setattr(local, '_json_request', lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match=code):
        ai._request([(1, png())], ai.load_rules(), {})


def test_original_images_page_order_rules_and_schema_are_preserved(monkeypatch):
    seen = []
    result = extraction(field()).model_copy(update={'reviewed_pages': [2, 1]})
    def transport(config, route, payload, **kwargs):
        seen.append(payload)
        assert route == '/api/chat'
        assert kwargs['timeout'] == 1800
        return reply(result.model_dump_json())
    monkeypatch.setattr(local, '_json_request', transport)
    pages = [(2, png(120, 80)), (1, png(100, 100))]
    output = ai._request(pages, ai.load_rules(), {'id': 'WO-TEST', '_private': 'not metadata'})
    assert output == result
    payload = seen[0]
    assert payload['format'] == ai.VisualExtraction.model_json_schema()
    assert payload['options']['num_predict'] == 7000
    assert payload['options']['num_ctx'] == 65536
    assert payload['think'] is False
    assert 'Never borrow contacts across owners' in payload['messages'][0]['content']
    assert '_private' not in payload['messages'][1]['content']
    assert [m['content'] for m in payload['messages'][2:]] == ['Original PDF page 2', 'Original PDF page 1']
    assert [base64.b64decode(m['images'][0]) for m in payload['messages'][2:]] == [p[1] for p in pages]


def test_insufficient_context_rejects_before_chat_without_dropping_images(monkeypatch):
    monkeypatch.setenv('PCT_OLLAMA_CONTEXT_LENGTH', '8192')
    monkeypatch.setattr(local, '_json_request', lambda *args, **kwargs: pytest.fail('must not send truncated input'))
    with pytest.raises(RuntimeError, match='ollama_context_capacity'):
        ai._request([(1, png(2000, 2800))], ai.load_rules(), {})


def test_independent_readings_are_both_run_with_local_serial_bound(monkeypatch):
    active = peak = 0
    calls = []
    mutex = threading.Lock()
    def request(pages, *args):
        nonlocal active, peak
        with mutex:
            active += 1
            peak = max(peak, active)
            calls.append([p[0] for p in pages])
        time.sleep(.04)
        with mutex:
            active -= 1
        return extraction(field()).model_copy(update={'reviewed_pages': [1, 2]}).model_dump_json()
    monkeypatch.setattr(local, 'request', request)
    first, second = ai._read_original_pages([(1, png()), (2, png())], ai.load_rules(), {})
    assert sorted(calls) == [[1, 2], [2, 1]]
    assert peak == 1
    assert first.fields[0].value == second.fields[0].value


def test_timeout_is_error_and_never_exports_ocr_or_calls_openai(monkeypatch, tmp_path):
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR', str(tmp_path / 'evidence'))
    monkeypatch.setattr(ai.requests, 'post', lambda *args, **kwargs: pytest.fail('OpenAI fallback'))
    def timeout(*args, **kwargs):
        raise RuntimeError('ollama_timeout')
    monkeypatch.setattr(local, 'request', timeout)
    result = ai.verify_contacts(pdf(tmp_path), {'emails': ['unverified@example.org']})
    assert result['status'] == 'error'
    assert result['emails'] == []
    assert 'ollama_timeout' in result['reason']


def test_local_model_identity_and_context_invalidate_cache_and_handoff(monkeypatch):
    original = (ai.verification_revision(), resume.policy_fingerprint())
    monkeypatch.setenv('PCT_OLLAMA_CONTEXT_LENGTH', '32768')
    assert (ai.verification_revision(), resume.policy_fingerprint()) != original
    monkeypatch.setenv('PCT_OLLAMA_CONTEXT_LENGTH', '65536')
    monkeypatch.setattr(local, 'model_identity', lambda config=None: {
        'provider': 'ollama', 'model': 'qwen3.5:4b', 'digest': 'b' * 64})
    assert (ai.verification_revision(), resume.policy_fingerprint()) != original
    monkeypatch.setenv('PCT_AI_PROVIDER', 'openai')
    assert (ai.verification_revision(), resume.policy_fingerprint()) != original


def test_provider_preflight_blocks_before_browser(monkeypatch):
    from agents.pct_agent import agent
    def missing(config=None):
        raise RuntimeError('ollama_model_not_installed')
    monkeypatch.setattr(local, 'model_identity', missing)
    result = agent.run_agent({'mode': 'wipo_download'})
    assert result['status'] == 'failure'
    assert 'ollama_model_not_installed' in result['error']


@pytest.mark.parametrize('failure,code', [
    (requests.ReadTimeout('private document'), 'ollama_timeout'),
    (requests.ConnectionError('private configuration'), 'ollama_unreachable'),
])
def test_transport_errors_are_sanitized_and_proxy_is_disabled(monkeypatch, failure, code):
    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert self.trust_env is False
            assert kwargs['allow_redirects'] is False
            raise failure
    monkeypatch.setattr(local.requests, 'Session', Session)
    with pytest.raises(RuntimeError) as caught:
        local._json_request(local.settings(), '/api/tags')
    assert str(caught.value) == code


def test_http_error_never_echoes_body_or_follows_redirect(monkeypatch):
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert kwargs['allow_redirects'] is False
            return SimpleNamespace(status_code=302, json=lambda: {'error': 'private source content'})
    monkeypatch.setattr(local.requests, 'Session', Session)
    with pytest.raises(RuntimeError, match='^ollama_http_302$'):
        local._json_request(local.settings(), '/api/chat', {})


# Retain the actual function to test preflight despite the default network stub.
REAL_IDENTITY = local.model_identity


@pytest.mark.parametrize('scenario,code', [
    ('missing', 'ollama_model_not_installed'), ('digest', 'ollama_model_digest_changed'),
    ('cloud', 'ollama_cloud_model_forbidden'), ('text', 'ollama_vision_required'),
    ('family', 'ollama_model_family_not_validated'),
])
def test_local_preflight_rejects_unsuitable_models(monkeypatch, scenario, code):
    entry = {'name': 'qwen3.5:4b', 'digest': 'a' * 64}
    shown = {'capabilities': ['vision'], 'details': {'family': 'qwen35'}}
    if scenario == 'digest': monkeypatch.setenv('PCT_OLLAMA_MODEL_DIGEST', 'b' * 64)
    if scenario == 'cloud': shown['remote_host'] = 'https://ollama.com'
    if scenario == 'text': shown['capabilities'] = ['completion']
    if scenario == 'family': shown['details']['family'] = 'different'
    def response(config, route, *args):
        return {'models': [] if scenario == 'missing' else [entry]} if route == '/api/tags' else shown
    monkeypatch.setattr(local, '_json_request', response)
    with pytest.raises(RuntimeError, match=code):
        REAL_IDENTITY()


@pytest.mark.parametrize('metadata', [{'models': None}, {'models': [None]}, {'unexpected': []}])
def test_malformed_model_inventory_fails_closed(monkeypatch, metadata):
    monkeypatch.setattr(local, '_json_request', lambda *args: metadata)
    with pytest.raises(RuntimeError, match='ollama_invalid_model_metadata'):
        REAL_IDENTITY()


def test_transport_fingerprint_survives_windows_line_ending_conversion(monkeypatch, tmp_path):
    expected = local.cache_material()['transport_hash']
    source = Path(local.__file__).read_text(encoding='utf-8')
    windows_copy = tmp_path / 'transport.py'
    windows_copy.write_bytes(source.replace('\n', '\r\n').encode('utf-8'))
    monkeypatch.setattr(local, '__file__', str(windows_copy))
    assert local.cache_material()['transport_hash'] == expected
