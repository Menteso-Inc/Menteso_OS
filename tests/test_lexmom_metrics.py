"""Business summary never treats reservations or repeated demos as new income/leads."""
import json
import tempfile
import unittest
from pathlib import Path

from agents.lexmom_marketing_agent.metrics import business_summary


class BusinessSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def saved_run(self, manager_id, child_id, *, mode="live", domain="example.com", passed=True, cost=.15):
        manager = self.root / "lexmom_marketing_agent" / manager_id
        child = self.root / "prospect_research_agent" / child_id
        manager.mkdir(parents=True, exist_ok=True)
        child.mkdir(parents=True, exist_ok=True)
        (manager / "completion.json").write_text(json.dumps({"agent": "lexmom_marketing_agent", "run_id": manager_id}))
        (manager / "result.json").write_text(json.dumps({"run_id": child_id}))
        (child / "completion.json").write_text(json.dumps({"agent": "prospect_research_agent", "run_id": child_id, "artifact_path": str(child / "result.json")}))
        (child / "result.json").write_text(json.dumps({"mode": mode, "tests": {"passed": passed},
            "budget": {"reserved_cost_usd": cost}, "data": {"firms": [
                {"domain": domain, "provenance": mode, "fit_status": "qualified"}]}}))

    def test_deduplicates_domains_and_child_handoffs_excludes_fixtures(self):
        self.saved_run("manager1", "child1")
        self.saved_run("manager2", "child1")
        self.saved_run("manager3", "child2", domain="https://WWW.EXAMPLE.COM/about")
        self.saved_run("manager4", "fixture", mode="fixture", domain="fake.example", cost=99)
        summary = business_summary(self.root)
        self.assertEqual(summary["qualified_leads"], 1)
        self.assertEqual(summary["reserved_cost_usd"], .30)
        self.assertIsNone(summary["total_spend_usd"])
        self.assertIsNone(summary["total_revenue_usd"])
        self.assertTrue(summary["history_complete"])

    def test_failed_validation_cost_is_preserved_but_is_not_a_lead(self):
        self.saved_run("failed", "failed-child", passed=False, cost=.25)
        summary = business_summary(self.root)
        self.assertEqual(summary["qualified_leads"], 0)
        self.assertEqual(summary["reserved_cost_usd"], .25)

    def test_missing_artifact_marks_history_incomplete(self):
        self.saved_run("manager", "child")
        (self.root / "prospect_research_agent/child/result.json").unlink()
        self.assertFalse(business_summary(self.root)["history_complete"])


if __name__ == "__main__":
    unittest.main()
