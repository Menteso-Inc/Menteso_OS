"""Self-tests for the CAPTCHA solver agent.

These are invariants we expect every run to satisfy. They run after each
solve attempt and the result is folded back into the agent return dict.
"""
from shared.self_test import SelfTest


def _has_outcome(result):
    return isinstance(result, dict) and result.get("outcome") in {
        "solved", "manual_solved", "failed", "skipped", "stopped", "error"
    }


def _never_silent(result):
    return bool(result.get("tier_used"))


def _has_captcha_type(result):
    return bool(result.get("captcha_type"))


def _honored_timeout(result):
    return result.get("elapsed_seconds", 0) <= result.get("max_seconds", 120) + 1


def _attempts_logged(result):
    attempts = result.get("attempts")
    return isinstance(attempts, list) and len(attempts) >= 1


tests = SelfTest(
    agent_name="pct_agent/captcha_solver",
    validations=[
        {
            "name": "has_outcome",
            "check": _has_outcome,
            "message": "Solver returned without a recognized outcome",
        },
        {
            "name": "never_silent",
            "check": _never_silent,
            "message": "No tier_used recorded — solver returned silently",
        },
        {
            "name": "has_captcha_type",
            "check": _has_captcha_type,
            "message": "captcha_type field is empty",
        },
        {
            "name": "honored_timeout",
            "check": _honored_timeout,
            "message": "Solver exceeded the configured max_seconds",
        },
        {
            "name": "attempts_logged",
            "check": _attempts_logged,
            "message": "No per-tier attempts were logged",
        },
    ],
)


if __name__ == "__main__":
    fake_result = {
        "outcome": "solved",
        "tier_used": "diy",
        "captcha_type": "wipo_text",
        "elapsed_seconds": 1.2,
        "max_seconds": 120,
        "attempts": [{"tier": "diy", "result": "solved"}],
    }
    report = tests.run(fake_result)
    print(report)
