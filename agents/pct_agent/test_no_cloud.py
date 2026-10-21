"""The PCT runtime must never fall back to a paid provider."""
import time
from pathlib import Path

import pytest
import requests

from agents.pct_agent import ai_verifier as ai
from agents.pct_agent.captcha_solver import agent as captcha
from agents.pct_agent.captcha_solver.solver_openai import solve_via_openai_vision
from agents.pct_agent.captcha_solver.solver_recaptcha_audio import solve_recaptcha_audio


@pytest.fixture(autouse=True)
def reject_network(monkeypatch):
    def network(*args, **kwargs):
        pytest.fail('This cloud-removal check must not contact any service')
    monkeypatch.setattr(requests.sessions.Session, 'request', network)


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'gpt-4o'])
def test_paid_provider_rejected_even_with_available_keys(monkeypatch, provider):
    monkeypatch.setenv('PCT_AI_PROVIDER', provider)
    monkeypatch.setenv('PCT_OPENAI_API_KEY', 'offline-placeholder')
    monkeypatch.setenv('OPENAI_API_KEY', 'shared-key-must-stay-untouched')
    with pytest.raises(ValueError, match='pct_ai_local_provider_required'):
        ai.validate_configuration(check_api=True)
    with pytest.raises(ValueError, match='pct_ai_local_provider_required'):
        ai._request([], None, {})


@pytest.mark.parametrize('legacy', ['vision,manual', 'diy,openai,manual', 'audio', 'ollama'])
def test_stale_captcha_settings_do_not_enable_model_calls(monkeypatch, legacy):
    monkeypatch.setenv('CAPTCHA_SOLVER_TIERS', legacy)
    for family in ['wipo_image_grid', 'wipo_text', 'recaptcha_v2', 'hcaptcha', 'turnstile', 'unknown']:
        assert captcha._enabled_tiers(family) == ('manual',)
    for tier in ['vision', 'openai', 'audio', 'diy', 'ollama']:
        assert captcha._run_tier(tier, None, 'unknown', None, time.time()+10) == (False, None, None)


def test_retired_public_entrypoints_cannot_call_a_provider():
    assert solve_via_openai_vision(None, 'wipo_image_grid') == (False, None, None)
    assert solve_recaptcha_audio(None) == (False, None, None)


def test_operator_confirmation_is_still_available(monkeypatch):
    calls = []
    monkeypatch.setattr(captcha, 'wait_for_manual', lambda page, **kwargs: (calls.append(page) or True, b'image'))
    page = object()
    assert captcha._run_tier('manual', page, 'unknown', None, time.time()+10) == (True, b'image', None)
    assert calls == [page]


def test_runtime_has_no_openai_endpoint_or_key_access():
    root = Path(ai.__file__).parent
    for path in root.rglob('*.py'):
        if path.name.startswith('test_') or path.name == 'conftest.py':
            continue
        source = path.read_text(encoding='utf-8')
        assert 'api.openai.com' not in source, path
        assert 'get_env("OPENAI_API_KEY")' not in source, path
        assert 'get_env("PCT_OPENAI_API_KEY")' not in source, path
