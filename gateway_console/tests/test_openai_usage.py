import os
import sys
import unittest
from unittest.mock import patch


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from openai_usage import build_dashboard_payload, get_openai_usage_dashboard


class OpenAIUsageDashboardTests(unittest.TestCase):
    def test_unconfigured_dashboard_does_not_fall_back_to_workload_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "workload-secret"}, clear=True):
            payload = get_openai_usage_dashboard(7)
        self.assertFalse(payload["configured"])
        self.assertEqual(payload["setup"]["envVar"], "OPENAI_ADMIN_KEY")
        self.assertNotIn("workload-secret", str(payload))

    def test_dashboard_aggregates_cost_usage_and_concentration(self):
        payload = build_dashboard_payload(
            days=7,
            start_time=1_700_000_000,
            end_time=1_700_604_800,
            costs=[{
                "start_time": 1_700_000_000,
                "results": [
                    {"amount": {"value": 8, "currency": "usd"}, "api_key_id": "key_a", "project_id": "proj_a", "line_item": "GPT input"},
                    {"amount": {"value": 2, "currency": "usd"}, "api_key_id": "key_b", "project_id": "proj_b", "line_item": "GPT output"},
                ],
            }],
            usage={
                "completions": [{
                    "start_time": 1_700_000_000,
                    "results": [
                        {"api_key_id": "key_a", "project_id": "proj_a", "model": "gpt-test", "num_model_requests": 4, "input_tokens": 100, "output_tokens": 40},
                        {"api_key_id": "key_b", "project_id": "proj_b", "model": "gpt-test", "num_model_requests": 1, "input_tokens": 20, "output_tokens": 10},
                    ],
                }],
            },
            key_metadata={"key_a": {"name": "SEO publisher"}, "key_b": {"name": "PCT verifier"}},
            project_metadata={"proj_a": {"name": "Marketing"}, "proj_b": {"name": "Patents"}},
        )

        self.assertEqual(payload["summary"]["cost"], 10)
        self.assertEqual(payload["summary"]["requests"], 5)
        self.assertEqual(payload["summary"]["totalTokens"], 170)
        self.assertEqual(payload["apiKeys"][0]["name"], "SEO publisher")
        self.assertEqual(payload["apiKeys"][0]["share"], 0.8)
        self.assertEqual(payload["models"][0]["name"], "gpt-test")
        self.assertTrue(any(alert["title"] == "High API-key concentration" for alert in payload["alerts"]))


if __name__ == "__main__":
    unittest.main()
