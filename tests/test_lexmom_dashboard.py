"""HTTP boundary tests; no cloud, credentials, or paid providers are used."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from deploy import lexmom_dashboard as module
from agents.lexmom_marketing_agent import tools as configuration


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        root = patch.object(module, "ROOT", self.root)
        root.start()
        self.addCleanup(root.stop)
        self.client = TestClient(module.app)

    def upstream(self, role="operator", authenticated=True):
        async def get(request, path):
            if not authenticated:
                return httpx.Response(401, json={"error": "login_required"})
            if path == "/api/auth/me":
                return httpx.Response(200, json={"user": {"role": role}})
            return httpx.Response(200, json=[{"module_name": module.NAME, "name": "Old"},
                                            {"module_name": "accountant_agent", "name": "Accountant"}],
                                  request=httpx.Request("GET", "http://test"))
        return patch.object(module, "upstream", get)

    def test_all_private_routes_require_login(self):
        with self.upstream(authenticated=False):
            for path in ("/api/agents", module.BASE, module.BASE + "/dashboard-data", module.BASE + "/run-status", module.BASE + "/artifacts/test/result.json"):
                self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(self.client.post(module.BASE + "/run", json={}).status_code, 401)

    def test_metadata_updates_only_lexmom(self):
        with self.upstream():
            rows = self.client.get("/api/agents").json()
        self.assertEqual(rows[0]["name"], "Lexmom Sub Manager")
        self.assertEqual(rows[1], {"module_name": "accountant_agent", "name": "Accountant"})

    def test_imported_workloads_are_read_only_and_do_not_expose_secrets(self):
        (self.root / "state").mkdir()
        (self.root / "state/imported-workloads.json").write_text(json.dumps({
            "verified": True, "workflows": 40, "wlf_workflows": 38,
            "credentials": 11, "wlf_credentials": 7,
            "verified_at": "2026-10-09T12:00:00Z", "api_key": "private-test-value"}))
        with self.upstream(), patch.object(module, "control") as control:
            rows = self.client.get("/api/agents").json()
            self.assertEqual(len(rows), 4)
            for name in module.IMPORTED_WORKLOADS:
                response = self.client.get("/api/agents/" + name)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("private-test-value", response.text)
                self.assertFalse(response.json()["execution_enabled"])
                self.assertEqual(self.client.get("/api/agents/" + name + "/run-status").json()["status"], "paused")
                self.assertEqual(self.client.post("/api/agents/" + name + "/run", json={}, headers={"origin": module.ORIGIN}).status_code, 409)
            control.assert_not_called()
        with self.upstream(authenticated=False):
            self.assertEqual(self.client.get("/api/agents/wlf_sdr").status_code, 401)
        with self.upstream(role="viewer"):
            self.assertEqual(self.client.post("/api/agents/wlf_sdr/run", headers={"origin": module.ORIGIN}).status_code, 403)

    def test_unverified_migration_is_not_listed(self):
        (self.root / "state").mkdir()
        (self.root / "state/imported-workloads.json").write_text('{"verified": false}')
        with self.upstream():
            self.assertEqual(len(self.client.get("/api/agents").json()), 2)
            self.assertEqual(self.client.get("/api/agents/wlf_sdr").status_code, 404)

    def test_viewer_and_cross_origin_cannot_start_or_stop(self):
        with self.upstream(role="viewer"), patch.object(module, "control") as control:
            self.assertEqual(self.client.post(module.BASE + "/stop", headers={"origin": module.ORIGIN}).status_code, 403)
            control.assert_not_called()
        with self.upstream(), patch.object(module, "control") as control:
            self.assertEqual(self.client.post(module.BASE + "/stop", headers={"origin": "https://other.example"}).status_code, 403)
            control.assert_not_called()

    def test_duplicate_run_is_rejected_without_overwriting_profile(self):
        with self.upstream(), patch.object(module, "bounded_profile", return_value={"seed_urls": ["https://example.com"]}), patch.object(module, "run_status", return_value={"status": "running"}), patch.object(module, "control") as control:
            result = self.client.post(module.BASE + "/run", json={}, headers={"origin": module.ORIGIN})
        self.assertEqual(result.status_code, 409)
        self.assertFalse((self.root / "pilot.json").exists())
        control.assert_not_called()

    def test_quota_block_is_actionable_and_does_not_start(self):
        (self.root / "state").mkdir()
        (self.root / "state/providers.json").write_text(json.dumps({"search": {"remaining": 0}}))
        with self.upstream(), patch.object(module, "bounded_profile", return_value={"seed_urls": []}), patch.object(module, "control") as control:
            result = self.client.post(module.BASE + "/run", json={}, headers={"origin": module.ORIGIN})
        self.assertEqual(result.status_code, 503)
        self.assertIn("quota", result.json()["error"])
        control.assert_not_called()

    def test_artifact_must_pass_manifest_resolver(self):
        with self.upstream(), patch.object(module, "resolve_research_artifact", return_value=None):
            self.assertEqual(self.client.get(module.BASE + "/artifacts/test/private.env").status_code, 404)

    def test_profile_rejects_fixture_and_caps_cost_and_calls(self):
        with self.assertRaises(ValueError):
            module.bounded_profile({"mode": "fixture"})
        with patch.object(module, "live_preflight"):
            profile = module.bounded_profile({"budget_usd": 100, "max_llm_calls": 50})
        self.assertEqual(profile["budget_usd"], 1)
        self.assertEqual(profile["max_llm_calls"], 15)
        self.assertTrue(profile["enable_verification"])

    def test_saved_config_is_reloaded_and_invalid_config_fails_closed(self):
        path = self.root / "research_profile.json"
        with patch.object(configuration, "PROFILE_PATH", path):
            with self.assertRaises(ValueError):
                configuration.load_saved_profile()
            path.write_text(json.dumps({"mode": "live", "countries": ["India"]}))
            self.assertEqual(configuration.validate_profile({}).countries, ["India"])
            path.write_text(json.dumps({"mode": "live", "countries": ["United States"]}))
            self.assertEqual(configuration.validate_profile({}).countries, ["United States"])
            path.write_text('{invalid')
            with self.assertRaises(ValueError):
                configuration.load_saved_profile()
            path.write_text(json.dumps({"mode": "fixture"}))
            with self.assertRaises(ValueError):
                configuration.load_saved_profile()

    def test_browser_cannot_override_saved_targeting(self):
        with self.upstream(), patch.object(module, "control") as control:
            response = self.client.post(module.BASE + "/run", json={"countries": ["India"]}, headers={"origin": module.ORIGIN})
        self.assertEqual(response.status_code, 422)
        control.assert_not_called()

    def test_empty_run_request_uses_saved_json(self):
        profile = {"seed_urls": ["https://example.com"], "countries": ["India"]}
        (self.root / "state").mkdir()
        with self.upstream(), patch.object(module, "load_saved_profile", return_value=profile), patch.object(module, "bounded_profile", side_effect=lambda p: p) as bounded, patch.object(module, "control") as control, patch.object(module, "get_dashboard_data", return_value={}):
            with patch.object(module, "run_status", side_effect=[{"status": "idle"}, {"status": "idle", "receipt": {"status": "success"}}]):
                response = self.client.post(module.BASE + "/run", json={}, headers={"origin": module.ORIGIN})
        self.assertEqual(response.status_code, 200)
        bounded.assert_called_once_with(profile)
        control.assert_called_once_with("start")
        self.assertEqual(json.loads((self.root / "pilot.json").read_text()), profile)


if __name__ == "__main__":
    unittest.main()
