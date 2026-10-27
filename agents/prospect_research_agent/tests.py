"""Automatic output validations run before every accepted research result."""

from shared.self_test import SelfTest

from .models import FirmRecord, DiscoveryDecision, DirectoryProfile


def valid_records(result):
    rows = result.get("data", {}).get("firms")
    if not isinstance(rows, list):
        return False
    for row in rows:
        FirmRecord.model_validate(row)
    for candidate in result.get("data", {}).get("candidates", []):
        DiscoveryDecision.model_validate(candidate)
    for profile in result.get("data", {}).get("directory_profiles", []):
        DirectoryProfile.model_validate(profile)
    return True


def unique_records(result):
    rows = result.get("data", {}).get("firms", [])
    return len({row["domain"] for row in rows}) == len(rows)


def grounded_qualification(result):
    for row in result.get("data", {}).get("firms", []):
        if row["fit_status"] == "qualified":
            if row.get("source_type") != "firm_website":
                return False
            fields = {item["field"] for item in row.get("evidence", [])}
            if not {"name", "country", "size", "practice_area", "organization_type"}.issubset(fields):
                return False
            if row.get("size_unit") != "attorneys" or not row.get("fit_reasons"):
                return False
        if row.get("outreach_eligible") is not False:
            return False
    return True


def counts_match(result):
    rows = result.get("data", {}).get("firms", [])
    summary = result.get("data", {}).get("summary", {})
    return all(summary.get(state) == sum(row["fit_status"] == state for row in rows)
               for state in ("qualified", "needs_research", "excluded"))


def separated_product_decisions(result):
    for row in result.get("data", {}).get("firms", []):
        if set(row.get("product_assessments", {})) != {"manage", "launch"}:
            return False
        for assessment in row["product_assessments"].values():
            # Public research cannot assert a prospect has expressed buying intent.
            if assessment.get("interest_status") != "unknown" or assessment.get("status") == "confirmed_need":
                return False
        for brief in row.get("personalization_briefs", []):
            if brief.get("outreach_eligible") is not False or not brief.get("hold_reasons"):
                return False
            if brief.get("audience") == "firm" and brief.get("contact_name"):
                return False
    return True


tests = SelfTest(
    agent_name="prospect_research_agent",
    validations=[
        {"name": "output_schema", "check": valid_records, "message": "Research output does not match its schema"},
        {"name": "unique_firms", "check": unique_records, "message": "Duplicate firms in research output"},
        {"name": "sourced_qualification", "check": grounded_qualification, "message": "Qualification lacks required evidence or improperly grants outreach eligibility"},
        {"name": "accurate_counts", "check": counts_match, "message": "Research summary does not match actual records"},
        {"name": "product_handoff", "check": separated_product_decisions, "message": "Product assessments or contact handoff improperly imply interest or sending permission"},
    ],
)


if __name__ == "__main__":
    import unittest

    suite = unittest.defaultTestLoader.discover("agents/prospect_research_agent", pattern="test_*.py", top_level_dir=".")
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
