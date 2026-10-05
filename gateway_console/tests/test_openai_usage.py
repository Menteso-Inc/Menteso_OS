import os
import json
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from openai_usage import (
    OpenAIAdminClient, OpenAIUsageError, _metadata_maps,
    build_dashboard_payload, get_openai_usage_dashboard,
)


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

    def test_inventory_includes_unused_keys_and_projects_without_leaking_values(self):
        payload = build_dashboard_payload(
            days=7, start_time=1_700_000_000, end_time=1_700_604_800,
            costs=[], usage={},
            key_metadata={"key_idle": {
                "name": "Unused service key", "project_id": "proj_idle",
                "redacted_value": "unexpected-sensitive-value",
                "owner": {"type": "service_account", "service_account": {"name": "Marketing worker"}},
            }},
            project_metadata={"proj_idle": {"name": "Idle project"}},
        )
        self.assertEqual(payload["summary"]["totalKeys"], 1)
        self.assertEqual(payload["summary"]["activeKeys"], 0)
        self.assertEqual(payload["summary"]["topConsumer"], "No usage")
        row = payload["apiKeys"][0]
        self.assertEqual(row["cost"], 0)
        self.assertFalse(row["hasActivity"])
        self.assertEqual(row["ownerName"], "Marketing worker")
        self.assertEqual(row["projects"][0]["name"], "Idle project")
        self.assertEqual(payload["projects"][0]["cost"], 0)
        self.assertNotIn("unexpected-sensitive-value", json.dumps(payload))

    def test_historical_key_retains_cost_model_and_api_breakdown(self):
        payload = build_dashboard_payload(
            days=7, start_time=1_700_000_000, end_time=1_700_604_800,
            costs=[{"start_time": 1_700_000_000, "results": [
                {"amount": {"value": 2}, "api_key_id": "retired", "project_id": "proj_a", "line_item": "Model input"}
            ]}],
            usage={"completions": [{"results": [
                {"api_key_id": "retired", "project_id": "proj_a", "model": "model-test", "input_tokens": 40, "num_model_requests": 2}
            ]}]},
        )
        row = payload["apiKeys"][0]
        self.assertEqual(row["inventoryStatus"], "historical_or_unavailable")
        self.assertEqual(row["costDrivers"], [{"name": "Model input", "cost": 2}])
        self.assertEqual(row["models"][0]["name"], "model-test")
        self.assertEqual(row["apiFamilies"], ["Completions / Responses"])

    def test_project_key_lookup_uses_full_inventory_not_admin_keys(self):
        class FakeClient:
            def get_all(self, path, params):
                if path == "/organization/projects":
                    self.project_params = params
                    return [{"id": "proj_a", "name": "Project A"}]
                if path == "/organization/projects/proj_a/api_keys":
                    self.key_params = params
                    return [{"id": "key_a", "name": "App key", "redacted_value": "masked...1234", "secret_value": "must-not-be-retained"}]
                raise AssertionError("Unexpected endpoint: " + path)

        client = FakeClient()
        keys, projects, warnings = _metadata_maps(client)
        self.assertEqual(client.project_params["include_archived"], "true")
        self.assertEqual(client.key_params["owner_project_access"], "any")
        self.assertEqual(keys["key_a"]["project_id"], "proj_a")
        self.assertNotIn("must-not-be-retained", json.dumps(keys))
        self.assertFalse(warnings)

    def test_inventory_failure_is_not_silently_hidden(self):
        class FakeClient:
            def get_all(self, path, params):
                if path == "/organization/projects":
                    return [{"id": "proj_a", "name": "Archived"}]
                raise OpenAIUsageError("Unavailable")
        keys, projects, warnings = _metadata_maps(FakeClient())
        self.assertFalse(keys)
        self.assertIn("Key inventory unavailable", warnings[0])

    def test_list_and_bucket_pagination(self):
        client = OpenAIAdminClient("test-placeholder")
        with patch.object(client, "_get", side_effect=[
            {"data": [{"id": "a"}], "has_more": True, "last_id": "a"},
            {"data": [{"id": "b"}], "has_more": False},
        ]) as getter:
            self.assertEqual(len(client.get_all("/organization/projects", {"limit": 1})), 2)
            self.assertEqual(getter.call_args_list[1].args[1]["after"], "a")
        with patch.object(client, "_get", side_effect=[
            {"data": [{"start_time": 1}], "has_more": True, "next_page": "page2"},
            {"data": [{"start_time": 2}], "has_more": False},
        ]) as getter:
            self.assertEqual(len(client.get_all("/organization/costs")), 2)
            self.assertEqual(getter.call_args_list[1].args[1]["page"], "page2")

    def test_bad_pagination_fails_instead_of_showing_partial_totals(self):
        client = OpenAIAdminClient("test-placeholder")
        with patch.object(client, "_get", return_value={"data": [], "has_more": True}):
            with self.assertRaises(OpenAIUsageError):
                client.get_all("/organization/costs")

    @unittest.skipUnless(shutil.which("node"), "Node is required for frontend checks")
    def test_frontend_inventory_search_breakdown_and_safe_csv(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const elements = {};
let exported = '';
const context = {
    Intl, Blob: class {constructor(parts) {this.parts = parts;}},
    URL: {createObjectURL: (blob) => {exported = blob.parts[0]; return 'blob:test';}, revokeObjectURL: () => {}},
    document: {
        getElementById: (id) => elements[id] ||= {innerHTML: '', textContent: '', addEventListener: () => {}},
        querySelectorAll: () => [], createElement: () => ({click: () => {}}),
    },
    fixture: {apiKeys: [{name: '=Formula key', id: 'key_idle', redactedValue: 'masked...1234',
        ownerName: 'Marketing', inventoryStatus: 'listed', hasActivity: false, projects: [{name: 'Project A'}],
        models: [{name: 'model-test', requests: 2, totalTokens: 40}], costDrivers: [{name: 'Input tokens', cost: 2}], apiFamilies: ['Completions'],
    }]},
};
const html = fs.readFileSync('openai-dashboard.html', 'utf8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\n\s*loadUsage\(false\);\s*$/, '');
vm.createContext(context); vm.runInContext(code, context);
vm.runInContext('state.data = fixture; renderKeys(state.data.apiKeys);', context);
assert(elements['keys-table'].innerHTML.includes('No activity in period'));
assert(elements['keys-table'].innerHTML.includes('Input tokens'));
assert(elements['keys-table'].innerHTML.includes('model-test'));
vm.runInContext('exportKeys()', context);
assert(exported.includes("'=Formula key"));
assert(exported.includes('masked...1234'));
vm.runInContext("state.search = 'nonexistent'; renderKeys(state.data.apiKeys);", context);
assert(elements['keys-table'].innerHTML.includes('No API keys match'));
'''
        result = subprocess.run(["node"], input=script, capture_output=True, text=True,
                                cwd=PROJECT_ROOT, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
