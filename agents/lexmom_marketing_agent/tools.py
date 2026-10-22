"""Explicit manager delegation to the reusable research specialist."""

from importlib import import_module
import json
from pathlib import Path

TOOLS = ("prospect_research_agent",)
PROFILE_PATH = Path(__file__).with_name("research_profile.json")


def load_saved_profile():
    """Read the editable targeting configuration fresh for each run; fail closed."""
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("Research configuration is missing or invalid") from None
    if not isinstance(profile, dict) or profile.get("mode") != "live" or any(
        key in profile for key in ("fixture_pages", "fixture_extractions", "unit_costs", "resume_run_id")
    ):
        raise ValueError("Saved research configuration must contain live targeting rules only")
    model = import_module("agents.prospect_research_agent.models").ResearchRequest
    return model.model_validate(profile).model_dump(exclude={"unit_costs", "resume_run_id"})


def delegate_research(profile, on_step=None, cancelled=None, initial_strategy=None):
    """One real child run; shared registry target restrictions still apply."""
    from shared.agent_registry import get_agent_runner

    return get_agent_runner("prospect_research_agent")(
        input_data=profile, on_step=on_step, cancelled=cancelled, initial_strategy=initial_strategy
    )


def validate_profile(payload=None, *, browser=False):
    """Validate with the specialist contract before starting any work."""
    model = import_module("agents.prospect_research_agent.models").ResearchRequest
    profile = dict(payload) if payload else load_saved_profile()
    if browser:
        # Provider pricing comes from server .env, never browser estimates.
        forbidden = {"fixture_pages", "fixture_extractions", "unit_costs"}
        if forbidden.intersection(profile) or profile.get("mode", "live") != "live":
            raise ValueError("Dashboard runs require live research and server-configured provider costs")
    return model.model_validate(profile)
