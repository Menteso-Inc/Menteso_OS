"""PCT policy regressions must never use the live inference service."""
import pytest
from agents.pct_agent import ollama_provider


@pytest.fixture(autouse=True)
def offline_model_metadata(monkeypatch):
    monkeypatch.setenv('PCT_AI_PROVIDER', 'ollama')
    monkeypatch.setattr(ollama_provider, 'model_identity', lambda config=None: {
        'provider': 'ollama', 'model': ollama_provider.settings()['model'], 'digest': 'a' * 64})
