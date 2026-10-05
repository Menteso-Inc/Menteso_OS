"""Reserved Lexmom marketing agent; no work runs until its scope is defined."""

from .tasks import SETUP_MESSAGE
from .tests import tests

AGENT_CONFIG = {
    "name": "Lexmom Marketing Agent",
    "description": "Lexmom marketing agent. Not configured.",
    "role": "Marketing",
    "version": "0.1.0",
    "status": "pending_setup",
    "ui_type": "pending_setup",
    "execution_enabled": False,
    "setup_message": SETUP_MESSAGE,
    "requires_llm": False,
    "accepts_upload": False,
    "group": "AWS Agents",
    "hosted_on": "aws",
    "sub_agents": [],
}


def get_dashboard_data():
    return {
        "status": "pending_setup",
        "message": SETUP_MESSAGE,
        "executionEnabled": False,
        "schedule": "Not configured",
        "integrations": [],
    }


def run_agent(*_args, **_kwargs):
    """Keep direct CLI/module calls inert as well as dashboard execution."""
    result = get_dashboard_data()
    report = tests.run(result)
    if not report["passed"]:
        raise RuntimeError("Lexmom placeholder self-test failed")
    return {**result, "tests": report}


if __name__ == "__main__":
    print(run_agent()["message"])
