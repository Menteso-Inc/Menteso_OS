"""Safety checks for the inactive marketing-agent placeholder."""

from shared.self_test import SelfTest

tests = SelfTest(
    agent_name="lexmom_marketing_agent",
    validations=[
        {
            "name": "awaiting_instructions",
            "check": lambda result: result.get("status") == "pending_setup"
            and bool(result.get("message")),
            "message": "The placeholder must clearly wait for instructions.",
        },
        {
            "name": "no_execution",
            "check": lambda result: result.get("executionEnabled") is False,
            "message": "Execution must stay disabled until work is defined.",
        },
        {
            "name": "no_schedule_or_integrations",
            "check": lambda result: result.get("schedule") == "Not configured"
            and result.get("integrations") == [],
            "message": "No schedules or external services should be enabled.",
        },
    ],
)


if __name__ == "__main__":
    from .agent import get_dashboard_data

    report = tests.run(get_dashboard_data())
    print(report)
    raise SystemExit(0 if report["passed"] else 1)
