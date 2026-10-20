"""Manager handoff checks run after every delegated research task."""

from shared.self_test import SelfTest

def valid_handoff(result):
    data = result.get("data")
    return (isinstance(data, dict) and isinstance(data.get("firms"), list)
            and isinstance(data.get("summary"), dict)
            and isinstance(result.get("artifacts", []), list))


tests = SelfTest(
    agent_name="lexmom_marketing_agent",
    validations=[
        {"name": "output_not_empty", "check": lambda r: isinstance(r, dict) and bool(r),
         "message": "The research handoff is empty."},
        {"name": "status_preserved", "check": lambda r: r.get("status") in
         {"success", "partial", "failure", "cancelled"}, "message": "Invalid specialist status."},
        {"name": "handoff_schema", "check": valid_handoff, "message": "Missing research records or summary."},
        {"name": "child_verified", "check": lambda r: r.get("status") in {"failure", "cancelled"}
         or (isinstance(r.get("specialist_tests"), dict) and r["specialist_tests"].get("passed") is True),
         "message": "The specialist returned results without passing self-tests."},
        {"name": "research_only", "check": lambda r: r.get("capabilities") == {"research": True,
         "outreach": False, "ads": False, "sales_conversation": False, "customer_success": False},
         "message": "An unapproved execution capability is enabled."},
        {"name": "no_outreach_eligibility", "check": lambda r: all(
         firm.get("outreach_eligible") is False for firm in r.get("data", {}).get("firms", [])),
         "message": "Research records cannot grant outreach eligibility."},
    ],
)


if __name__ == "__main__":
    sample = {"status": "failure", "data": {"firms": [], "summary": {}}, "artifacts": [],
              "capabilities": {"research": True, "outreach": False, "ads": False,
                               "sales_conversation": False, "customer_success": False}}
    report = tests.run(sample)
    print(report)
    raise SystemExit(0 if report["passed"] else 1)
