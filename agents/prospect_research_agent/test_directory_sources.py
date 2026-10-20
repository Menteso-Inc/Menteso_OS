"""Directory rights, budgets and stop conditions tested without real provider calls."""
import json
import os
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from .directory_sources import DirectoryPolicy, DirectoryRule, access_decision, load_directory_policy, profile_observation, terms_digest
from .discovery import select_candidates, source_kind
from .models import DiscoveryDecision, ResearchRequest
from .test_tools import _Budget, request, response
from .tools import SourceError, SourceTools
from shared.prospect_store import ProspectStore


TERMS_TEXT = "Synthetic fixture: automated profile collection, storage and commercial research are permitted."
PROFILE = "https://directory.example/lawyer/jane"


def permitted_policy(host="directory.example", **overrides):
    fields = dict(host=host, name="Fixture directory", homepage=f"https://{host}/",
        state="permitted", terms_url=f"https://{host}/terms", note="Explicit fixture permission",
        reviewed_on=date.today(), automated_collection=True, storage_for_prospect_research=True,
        commercial_prospecting=True, permission_reference="Synthetic offline fixture permission; not a real licence",
        reviewed_terms_sha256=terms_digest(TERMS_TEXT), profile_path_prefixes=["/lawyer"],
        min_interval_seconds=1)
    fields.update(overrides)
    return DirectoryPolicy(version="fixture", discovery_queries=["lawyer directory"], sources=[DirectoryRule(**fields)])


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.budget = _Budget()
        self.tools = SourceTools(request(), self.budget)
        self.tools.directory_policy = permitted_policy()
        self.calls = []
        self.status = 200
        self.headers = {}
        self.terms = TERMS_TEXT
        self.body = b"Jane Example lawyer <a href='https://firm.example/'>Visit website</a>"
        def transport(url, *args):
            self.calls.append(url)
            if url.endswith("robots.txt"):
                return response(url, status=404)
            if url.endswith("/terms"):
                return response(url, body=self.terms.encode())
            return response(url, status=self.status, body=self.body, **self.headers)
        for patcher in (patch.object(self.tools, "_transport", side_effect=transport),
                        patch.object(self.tools, "_resolve_public_ips", return_value=["8.8.8.8"]),
                        patch("agents.prospect_research_agent.tools.time.sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_catalog_covers_requested_sites_and_extra_directories_without_claiming_permission(self):
        policy = load_directory_policy()
        self.assertEqual(len(policy.sources), 16)
        for host in ("justia.com", "avvo.com", "findlaw.com", "martindale.com", "lawyers.com", "lawrato.com"):
            self.assertIsNotNone(policy.find("https://" + host + "/"))
        self.assertTrue(all(rule.state != "permitted" for rule in policy.sources))

    def test_public_visibility_or_incomplete_permission_cannot_enable_collection(self):
        with self.assertRaises(ValidationError):
            DirectoryRule(host="directory.example", name="Public directory", homepage="https://directory.example/",
                          state="permitted", note="Publicly visible", automated_collection=True)

    def test_new_directories_are_held_instead_of_treated_as_firms(self):
        url = "https://unknown.example/lawyer/jane"
        self.assertEqual(source_kind(url, "Attorney directory profiles"), "directory")
        self.assertEqual(access_decision(url, self.tools.directory_policy)["source_access"], "review_required")
        self.assertEqual(source_kind("https://linkedin.com/in/jane", "Attorney directory"), "unsupported")
        self.assertEqual(source_kind("https://firm.example/team", "Our attorney profiles", "Find a lawyer at our firm"), "website")

    def test_lookalike_domain_is_not_an_approved_directory(self):
        self.assertIsNone(self.tools.directory_policy.find("https://directory.example.evil.example/lawyer/jane"))

    def test_stale_or_future_review_cannot_be_used(self):
        for day in (date.today() - timedelta(days=31), date.today() + timedelta(days=1)):
            self.tools.directory_policy = permitted_policy(reviewed_on=day)
            with self.assertRaisesRegex(SourceError, "review_required"):
                self.tools.resolve_directory(PROFILE)
        self.assertEqual(self.calls, [])

    def test_whole_site_and_unreviewed_paths_are_held_before_network(self):
        for path in ("/", "/lawyers", "/lawyer-other/jane", "/lawyer/../private", "/lawyer/%2e%2e/private", "/lawyer/%252e%252e/private"):
            with self.assertRaisesRegex(SourceError, "path_disallowed"):
                self.tools.resolve_directory("https://directory.example" + path)
        self.assertEqual(self.calls, [])

    def test_restricted_or_unreviewed_catalog_profiles_are_not_requested(self):
        self.tools.directory_policy = load_directory_policy()
        for url in ("https://lawyers.justia.com/lawyer/jane", "https://www.avvo.com/attorneys/jane.html",
                    "https://lawyers.findlaw.com/profile/jane", "https://www.martindale.com/attorney/jane/"):
            with self.assertRaisesRegex(SourceError, "directory_(restricted|review_required)"):
                self.tools.resolve_directory(url)
        self.assertEqual(self.calls, [])

    def test_permitted_profile_is_checked_then_resolves_official_site_only(self):
        self.assertEqual(self.tools.resolve_directory(PROFILE), "https://firm.example/")
        self.assertEqual(self.calls, ["https://directory.example/robots.txt", "https://directory.example/terms", PROFILE])
        self.assertEqual(self.budget.counts["pages"], 3)

    def test_terms_hash_change_stops_before_profile_and_survives_new_run(self):
        with tempfile.TemporaryDirectory() as folder:
            self.tools.source_access_store = ProspectStore(folder)
            self.terms = "Changed terms: automated access is prohibited."
            with self.assertRaisesRegex(SourceError, "terms_changed"):
                self.tools.resolve_directory(PROFILE)
            self.assertNotIn(PROFILE, self.calls)
            other = SourceTools(request(), _Budget())
            other.directory_policy = permitted_policy()
            other.source_access_store = ProspectStore(folder)
            with patch.object(other, "_transport") as transport, self.assertRaisesRegex(SourceError, "directory_blocked"):
                other.resolve_directory(PROFILE)
            transport.assert_not_called()

    def test_denied_terms_document_does_not_fetch_profile(self):
        original = self.tools._transport
        def transport(url, *args):
            return response(url, status=403) if url.endswith("/terms") else original(url, *args)
        with patch.object(self.tools, "_transport", side_effect=transport):
            with self.assertRaisesRegex(SourceError, "terms_unavailable"):
                self.tools.resolve_directory(PROFILE)
        self.assertNotIn(PROFILE, self.calls)

    def test_live_robots_restriction_overrides_recorded_permission(self):
        original = self.tools._transport
        def transport(url, *args):
            return response(url, body=b"User-agent: *\nDisallow: /lawyer\n") if url.endswith("robots.txt") else original(url, *args)
        with patch.object(self.tools, "_transport", side_effect=transport):
            with self.assertRaisesRegex(SourceError, "robots_disallowed"):
                self.tools.resolve_directory(PROFILE)
        self.assertNotIn(PROFILE, self.calls)

    def test_access_denials_stop_repeated_requests_including_other_profiles(self):
        for status in (401, 403, 451):
            self.tools._source_holds.clear()
            self.status = status
            with self.assertRaisesRegex(SourceError, "HTTP " + str(status)):
                self.tools.resolve_directory(PROFILE)
            count = len(self.calls)
            with self.assertRaisesRegex(SourceError, "directory_blocked"):
                self.tools.resolve_directory("https://directory.example/lawyer/another")
            self.assertEqual(len(self.calls), count)

    def test_rate_limit_honors_retry_after_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProspectStore(folder)
            self.tools.source_access_store = store
            self.status = 429
            self.headers = {"retry-after": "172800"}
            with self.assertRaisesRegex(SourceError, "HTTP 429"):
                self.tools.resolve_directory(PROFILE)
            with patch("shared.prospect_store.time.time", return_value=time.time() + 86401):
                self.assertIsNotNone(ProspectStore(folder).source_hold("directory.example"))
            with patch("shared.prospect_store.time.time", return_value=time.time() + 172801):
                self.assertIsNone(ProspectStore(folder).source_hold("directory.example"))

    def test_human_challenge_does_not_extract_contacts_or_retry(self):
        self.body = b"<title>Just a moment</title>Verify you are human. fake@directory.example"
        with self.assertRaisesRegex(SourceError, "directory_challenge"):
            self.tools.resolve_directory(PROFILE)
        self.assertNotIn("fake@directory.example", self.tools._published_emails)
        count = len(self.calls)
        with self.assertRaisesRegex(SourceError, "directory_blocked"):
            self.tools.resolve_directory(PROFILE)
        self.assertEqual(len(self.calls), count)

    def test_directory_profile_limit_is_shared_across_profiles(self):
        self.tools.directory_policy = permitted_policy(max_profile_pages_per_run=1)
        self.tools.resolve_directory(PROFILE)
        count = len(self.calls)
        with self.assertRaisesRegex(SourceError, "directory_page_limit"):
            self.tools.resolve_directory("https://directory.example/lawyer/another")
        self.assertEqual(len(self.calls), count)

    def test_unknown_directory_homepage_does_not_register_published_emails(self):
        self.body = b"<title>Lawyer Directory</title><p>fake@directory.example</p>"
        self.tools.directory_policy = permitted_policy("other.example")
        with self.assertRaisesRegex(SourceError, "directory_review_required"):
            self.tools._read_page(PROFILE, "directory.example")
        self.assertEqual(self.tools._published_emails, set())

    def test_directory_queries_share_search_cap_and_discovery_metadata_is_not_a_lead(self):
        self.tools.request = request(countries=["India"], discover_directories=True, max_queries=2)
        self.tools.directory_policy = load_directory_policy()
        payload = {"organic_results": [
            {"link": "https://www.martindale.com/attorney/jane", "title": "Jane Example lawyer"},
            {"link": "https://newdirectory.example/lawyer/jane", "title": "Lawyer directory profiles"}]}
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "offline-only"}), \
             patch.object(self.tools, "_provider_json", return_value=(200, payload)) as provider:
            self.assertEqual(self.tools.discover(), [])
        queries = [parse_qs(urlsplit(call.args[1]).query)["q"][0] for call in provider.call_args_list]
        self.assertEqual(len(queries), 2)
        self.assertIn("directory", queries[1])
        self.assertTrue(all("India" in query for query in queries))
        self.assertEqual(self.budget.counts["queries"], 2)
        self.assertEqual(self.budget.counts["pages"], 0)
        self.assertTrue(all(row["status"] == "needs_research" for row in self.tools.discovery_records))
        for row in self.tools.discovery_records:
            DiscoveryDecision.model_validate(row)

    def test_held_directory_does_not_use_candidate_slots(self):
        rows = [dict(url=PROFILE, source_kind="directory", source_access="restricted", score=20,
                     status="pending", reason="Terms prohibit collection"),
                dict(url="https://firm.example/", source_kind="website", score=5, status="pending")]
        self.assertEqual(select_candidates(rows, 1, {}, set()), ["https://firm.example/"])
        self.assertEqual(rows[0]["status"], "needs_research")

    def test_saved_profile_enables_directory_discovery_without_increasing_budgets(self):
        profile_path = Path(__file__).parents[1] / "lexmom_marketing_agent" / "research_profile.json"
        profile = ResearchRequest.model_validate(json.loads(profile_path.read_text()))
        self.assertTrue(profile.discover_directories)
        self.assertEqual(profile.max_queries, 3)
        self.assertEqual(profile.budget_usd, 0)
        self.assertEqual(profile.max_llm_calls, 0)

    def test_policy_validation_does_not_trust_path_wildcards_or_whole_site_permission(self):
        for paths in (["/"], ["/lawyer/%2e%2e/"], ["/lawyer/../private"]):
            with self.assertRaises(ValidationError):
                permitted_policy(profile_path_prefixes=paths)

    def test_source_profile_contacts_keep_evidence_but_are_never_verified_leads(self):
        block = "Jane Example\nManaging Partner\njane@firm.example"
        observed = profile_observation(dict(url=PROFILE, text=block, headings=["Jane Example"],
            contact_blocks=[block], retrieved_at="2026-10-20T12:00:00Z"), "https://firm.example/")
        self.assertEqual(observed["contacts"][0]["email"], "jane@firm.example")
        self.assertEqual(observed["contacts"][0]["role"], "Managing Partner")
        self.assertEqual(observed["research_status"], "needs_primary_research")
        self.assertFalse(observed["outreach_eligible"])
        self.assertTrue(all(item["source_url"] == PROFILE for item in observed["evidence"]))

    def test_directory_operator_footer_is_not_a_prospect(self):
        block = "Jane Example\nManaging Partner\ncontact@directory.example"
        observed = profile_observation(dict(url=PROFILE, text=block, headings=["Jane Example"],
            contact_blocks=[block], retrieved_at="2026-10-20T12:00:00Z"), None)
        self.assertEqual(observed["contacts"], [])
        block = "Jane Example\nManaging Partner\nfooter@firm.example"
        observed = profile_observation(dict(url=PROFILE, text=block, headings=["Jane Example"],
            contact_blocks=[block], footer_blocks=[block], retrieved_at="2026-10-20T12:00:00Z"), None)
        self.assertEqual(observed["contacts"], [])

    def test_extreme_retry_after_never_causes_an_early_retry(self):
        self.status = 429
        self.headers = {"retry-after": "99999999999999999999999999999999"}
        with self.assertRaisesRegex(SourceError, "HTTP 429"):
            self.tools.resolve_directory(PROFILE)
        self.assertIsNone(self.tools._source_holds["directory.example"][1])

    def test_redirect_cannot_leave_approved_profile_paths(self):
        self.status = 302
        self.headers = {"location": "/private"}
        with self.assertRaisesRegex(SourceError, "reviewed directory profile paths"):
            self.tools.resolve_directory(PROFILE)
        self.assertNotIn("https://directory.example/private", self.calls)

    def test_terms_change_after_ordinary_text_excerpt_is_detected(self):
        original = "policy " * 10001 + "automated collection allowed"
        self.tools.directory_policy = permitted_policy(reviewed_terms_sha256=terms_digest(original))
        self.terms = original.replace("automated collection allowed", "automated collection prohibited")
        with self.assertRaisesRegex(SourceError, "terms_changed"):
            self.tools.resolve_directory(PROFILE)
        self.assertNotIn(PROFILE, self.calls)

    def test_new_rate_limit_cannot_release_an_existing_review_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProspectStore(folder)
            store.hold_source("directory.example", "HTTP 403; operator review required")
            store.hold_source("directory.example", "Temporary rate limit", time.time() + 86400)
            with patch("shared.prospect_store.time.time", return_value=time.time() + 172800):
                self.assertIn("HTTP 403", store.source_hold("directory.example"))

    def test_source_pacing_covers_robots_and_redirect_requests(self):
        with patch.object(self.tools, "_wait_for_source", wraps=self.tools._wait_for_source) as pace:
            self.tools.resolve_directory(PROFILE)
        self.assertTrue(any(call.args[0].endswith("robots.txt") for call in pace.call_args_list))
        self.assertTrue(any(call.args[0] == PROFILE for call in pace.call_args_list))


if __name__ == "__main__":
    unittest.main()
