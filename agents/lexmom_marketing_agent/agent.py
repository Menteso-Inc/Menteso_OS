"""Thin Lexmom Sub Manager connector for the first approved specialist."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

from shared.memory import load_memory
from shared.research_runtime import ResearchSession, _atomic_json, redact
from .tasks import DISABLED_CAPABILITIES, RESEARCH_MESSAGE
from .tests import tests
from .tools import delegate_research, validate_profile, load_saved_profile
from .metrics import business_summary

AGENT_NAME = "lexmom_marketing_agent"  # Stable registry/module identity.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = PROJECT_ROOT / "runtime-data" / AGENT_NAME / "last-research.json"
CAPABILITIES = {"research": True, **{name: False for name in DISABLED_CAPABILITIES}}
AGENT_CONFIG = {
    "name": "Lexmom Sub Manager",
    "description": "Lexmom research manager: sourced firm qualification and contact discovery.",
    "role": "Research Manager", "version": "0.2.0", "status": "ready",
    "ui_type": "lexmom_research", "execution_enabled": True,
    "requires_llm": False, "accepts_upload": False, "group": "AWS Agents",
    "hosted_on": "aws", "sub_agents": ["Prospect Research", "Email Campaign", "Social Media Posting"], "capabilities": CAPABILITIES,
}


def resolve_research_artifact(run_id, filename, *, state_root=None):
    """Resolve only files recorded by the specialist's completed run manifest."""
    if (not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(run_id or ""))
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", str(filename or ""))):
        return None
    root = Path(state_root or PROJECT_ROOT / "runtime-data").resolve()
    base = (root / "prospect_research_agent").resolve()
    directory = (base / run_id).resolve()
    candidate = (directory / filename).resolve()
    if base not in directory.parents or directory not in candidate.parents or not candidate.is_file():
        return None
    try:
        receipt = json.loads((directory / "completion.json").read_text(encoding="utf-8"))
        if receipt.get("agent") != "prospect_research_agent" or receipt.get("run_id") != run_id:
            return None
        result_path = Path(receipt["artifact_path"]).resolve()
        if result_path != directory / "result.json":
            return None
        result = json.loads(result_path.read_text(encoding="utf-8"))
        allowed = {result_path}
        for artifact in result.get("artifacts", []):
            if isinstance(artifact, dict) and artifact.get("path"):
                path = Path(artifact["path"]).resolve()
                if directory in path.parents:
                    allowed.add(path)
        return candidate if candidate in allowed else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def get_dashboard_data():
    try:
        last_result = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        run_id = last_result.get("run_id")
        artifact = resolve_research_artifact(run_id, "result.json")
        if artifact is not None:
            researched = json.loads(artifact.read_text(encoding="utf-8"))
            last_result["data"] = researched.get("data", last_result.get("data", {}))
            last_result["rows"] = researched.get("rows", [])
    except (OSError, ValueError, TypeError):
        last_result = None
    memory = load_memory(AGENT_NAME)
    try:
        defaults, profile_error = load_saved_profile(), ""
    except ValueError:
        defaults, profile_error = {}, "Research configuration needs attention."
    inventory, inventory_error = [], ""
    if defaults:
        try:
            from agents.prospect_research_agent.models import ResearchRequest, FirmRecord
            from agents.prospect_research_agent.qualification import load_policy, enrich_product_fit
            from shared.prospect_store import ProspectStore, targeting_key
            request, policy = ResearchRequest.model_validate(defaults), load_policy()
            store = ProspectStore(STATE_FILE.parent.parent / "prospect_research_agent")
            inventory = [enrich_product_fit(FirmRecord.model_validate(row), request, policy).model_dump()
                         for row in store.records(targeting_key(request, policy.fingerprint))]
        except (ValueError, OSError, sqlite3.Error):
            inventory_error = "Saved prospect inventory needs attention; run artifacts are preserved."
    from agents.email_campaign_agent.engagement import lead_table
    try:
        from agents.email_campaign_agent.models import Settings as EmailSettings
        from agents.email_campaign_agent.store import Store as EmailStore
        lead_activity = EmailStore(EmailSettings.from_env().state_dir).engagement_activity()
        leads = lead_table(inventory, lead_activity)
    except (ValueError, OSError, sqlite3.Error):
        leads = lead_table(inventory, {}, available=False)
    directory_sources, directory_error = [], ""
    try:
        from agents.prospect_research_agent.directory_sources import access_decision, load_directory_policy
        directory_policy = load_directory_policy()
        for rule in directory_policy.sources:
            sample = rule.homepage.rstrip("/") + (rule.profile_path_prefixes[0] if rule.profile_path_prefixes else "/")
            decision = access_decision(sample, directory_policy)
            hold = store.source_hold(rule.host) if defaults and not inventory_error else None
            directory_sources.append({"name": rule.name, "homepage": rule.homepage,
                "state": "blocked" if hold else decision["source_access"],
                "reason": hold or decision["reason"], "terms_url": rule.terms_url,
                "reviewed_on": rule.reviewed_on.isoformat() if rule.reviewed_on else None})
    except (ValueError, OSError, sqlite3.Error):
        directory_error = "Directory source rules need attention; profile collection is held."
    return {
        "status": "ready", "message": RESEARCH_MESSAGE, "executionEnabled": True,
        "schedule": "On demand", "capabilities": dict(CAPABILITIES),
        "integrations": ["Prospect Research"], "lastResult": last_result,
        "stats": memory.get("stats", {}),
        "defaults": defaults, "profileError": profile_error,
        "prospectInventory": inventory, "inventoryError": inventory_error,
        "leadTable": leads,
        "directorySources": directory_sources, "directoryError": directory_error,
        "businessSummary": business_summary(STATE_FILE.parent.parent),
        "workflowAgents": [{"id": "prospect_research_agent", "name": "Prospect Research", "enabled": True},
                           {"id":"email_campaign_agent","name":"Email Campaign","enabled":False},
                           {"id":"social_media_posting_agent","name":"Social Media Posting","enabled":False}],
    }


def run_agent(input_data=None, on_step=None, cancelled=None, session=None):
    """Call one research specialist, validate its handoff, and preserve its state."""
    started = time.monotonic()
    controls = dict(input_data or {})
    input_stop_requested = controls.pop("stop_requested", None)
    stop_requested = cancelled or input_stop_requested
    manager_run_id = controls.pop("run_id", None)
    for key in ("get_live_fast_level", "register_stop_handler"):
        controls.pop(key, None)
    session = session or ResearchSession(AGENT_NAME, run_id=manager_run_id)
    session.load_memory()
    strategy = session.best_strategy("lexmom_research", default="standard")
    preflight = True
    if callable(on_step):
        on_step({"type": "step", "message": "Lexmom Sub Manager is validating the research profile."})
    try:
        profile = validate_profile(controls)
        preflight = False
        request = profile.model_dump()
        if profile.mode == "fixture":
            request["fixture_pages"] = profile.fixture_pages
            request["fixture_extractions"] = profile.fixture_extractions
        if callable(on_step):
            on_step({"type": "step", "message": "Delegating the approved profile to Prospect Research."})
        child = delegate_research(request, on_step=on_step, cancelled=stop_requested, initial_strategy=strategy)
        if not isinstance(child, dict):
            raise ValueError("Prospect Research returned an invalid handoff")
        result = dict(child)
        preflight = child.get("outcome") == "preflight" or child.get("preflight") is True
        result["specialist_tests"] = child.get("tests")
        result.setdefault("data", {"firms": [], "summary": {}})
        result.setdefault("rows", result["data"].get("firms", []))
        result.setdefault("artifacts", [])
    except Exception as exc:
        result = {"status": "failure", "error": redact(str(exc)), "errors": [redact(str(exc))],
                  "data": {"firms": [], "summary": {}}, "rows": [], "artifacts": []}
    result.update({"manager": AGENT_NAME, "manager_run_id": session.run_id,
                   "workspaceId": "lexmom", "capabilities": dict(CAPABILITIES),
                   "execution_time": round(time.monotonic() - started, 3)})
    result["summary"] = result.get("data", {}).get("summary", {})
    result["tests"] = tests.run(result)
    if not result["tests"]["passed"]:
        result["specialist_status"] = result.get("status")
        result["status"] = "failure"
        preflight = False
        result.setdefault("errors", []).append("Manager handoff validation failed")
        result["error"] = "Manager handoff validation failed"
    # Datasets remain in specialist artifacts; manager memory/state stores handoff metadata.
    lightweight = {key: value for key, value in result.items() if key not in {"data", "rows", "results"}}
    lightweight["data"] = {"firms": [], "summary": result["summary"]}
    receipt = session.finish(lightweight, "preflight" if preflight else result["status"], strategy,
                             "Research specialist handoff validated.", result["execution_time"])
    result["human_review_required"] = receipt["review_required"]
    result["manager_stats"] = receipt["stats"]
    lightweight["human_review_required"] = receipt["review_required"]
    lightweight["manager_stats"] = receipt["stats"]
    _atomic_json(session.agent_dir / "last-research.json", lightweight)
    return redact(result)


if __name__ == "__main__":
    print(json.dumps(run_agent(), indent=2))
