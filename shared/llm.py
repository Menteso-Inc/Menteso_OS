"""Lazy provider configuration: agent discovery never requires live credentials."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key_env: str
    max_tokens: int
    max_input_tokens: int
    timeout: float


def _bounded_number(value, label: str, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive finite number") from None
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise ValueError(f"{label} must be positive, finite and within its hard limit")
    return number


def llm_settings(agent_prefix: str = "PROSPECT_RESEARCH_AGENT", *,
                 max_tokens: int | None = None, timeout: float | None = None) -> LLMSettings:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", agent_prefix):
        raise ValueError("LLM environment prefix must use uppercase letters, digits or underscores")
    # Shared configuration owns loading .env; avoid reading it during discovery.
    from shared import config  # noqa: F401

    provider = os.getenv(f"{agent_prefix}_LLM_PROVIDER", os.getenv("DEFAULT_LLM_PROVIDER", "openai")).strip().lower()
    if provider not in {"openai", "anthropic"}:
        raise ValueError("LLM provider must be openai or anthropic")
    default_model = os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini") if provider == "openai" else os.getenv("ANTHROPIC_MODEL", "")
    model = os.getenv(f"{agent_prefix}_LLM_MODEL", default_model).strip()
    if not model or any(part.isspace() for part in model) or len(model) > 150:
        raise ValueError("LLM model must be a non-empty model identifier")
    if "/" in model:
        selected_provider, model_id = model.split("/", 1)
        if selected_provider != provider or not model_id or "/" in model_id:
            raise ValueError("Configured model prefix does not match the selected provider")
    else:
        model = f"{provider}/{model}"
    if "codex-sonnet" in model.lower():
        raise ValueError("Configure an actual Anthropic Claude model identifier")
    output_limit = _bounded_number(os.getenv(f"{agent_prefix}_LLM_MAX_TOKENS", "1500"), "LLM_MAX_TOKENS", 4000)
    input_limit = _bounded_number(os.getenv(f"{agent_prefix}_LLM_MAX_INPUT_TOKENS", "10000"), "LLM_MAX_INPUT_TOKENS", 20000)
    if int(output_limit) != output_limit or int(input_limit) != input_limit:
        raise ValueError("LLM token limits must be integers")
    token_count = int(output_limit)
    if max_tokens is not None:
        requested = _bounded_number(max_tokens, "max_tokens", 4000)
        if requested != int(requested):
            raise ValueError("max_tokens must be an integer")
        token_count = min(token_count, int(requested))
    configured_timeout = _bounded_number(os.getenv(f"{agent_prefix}_LLM_TIMEOUT_SECONDS", "20"), "LLM_TIMEOUT_SECONDS", 60)
    if timeout is not None:
        configured_timeout = min(configured_timeout, _bounded_number(timeout, "timeout", 60))
    shared_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    dedicated_key_env = f"{agent_prefix}_{shared_key_env}"
    # An explicitly configured dedicated slot must never fall back to another
    # agent's account, including when that slot is blank or invalid.
    key_env = dedicated_key_env if dedicated_key_env in os.environ else shared_key_env
    return LLMSettings(provider, model, key_env,
                       token_count, int(input_limit), configured_timeout)


def validate_llm_readiness(agent_prefix: str = "PROSPECT_RESEARCH_AGENT", *,
                           max_tokens: int | None = None, timeout: float | None = None) -> LLMSettings:
    """Validate live settings without importing CrewAI or returning any secret."""
    settings = llm_settings(agent_prefix, max_tokens=max_tokens, timeout=timeout)
    key = os.getenv(settings.api_key_env, "").strip()
    placeholder = key.lower().replace("-", "_").replace(" ", "_")
    if not key or placeholder in {"changeme", "change_me", "your_api_key", "your_key", "todo", "none", "null", "...", "xxx"} or key.startswith("<") or "placeholder" in placeholder or "your_" in placeholder or "replace_" in placeholder or key.endswith("..."):
        raise ValueError(f"{settings.api_key_env} is not set")
    return settings


def create_crewai_llm(agent_prefix: str = "PROSPECT_RESEARCH_AGENT", *,
                      max_tokens: int | None = None, timeout: float | None = None):
    settings = validate_llm_readiness(agent_prefix, max_tokens=max_tokens, timeout=timeout)
    try:
        from crewai import LLM
    except ImportError:
        raise RuntimeError("CrewAI is required for live research; install requirements.txt") from None
    # Internal SDK retries would bypass the run's per-call reservations.
    return LLM(model=settings.model, api_key=os.environ[settings.api_key_env],
               max_tokens=settings.max_tokens, timeout=settings.timeout, max_retries=0,
               temperature=0)
