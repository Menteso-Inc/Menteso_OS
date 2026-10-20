"""Offline end-to-end discovery: real tools/lifecycle, simulated provider and HTML."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from .agent import run_agent
from .discovery import recent_research
from .models import ResearchRequest
from .tools import HTTPResult, SourceTools, SourceError
from shared.research_runtime import ResearchSession, RunBudget


ROOT = "https://alpha.example/"
TEAM = ROOT + "team"
CONTACT = ROOT + "contact"
HOME_TEXT = "Alpha Legal. Our law firm is in United States. Our legal practice is litigation."


def extract(pages, request, budget, strategy, memory):
    budget.consume("llm_calls")
    evidence = []
    facts = [("name", "Alpha Legal"), ("country", "United States"),
             ("practice_area", "litigation"), ("size", "3"), ("email", "hello@alpha.example")]
    for field, value in facts:
        for page in pages:
            quote = "3 attorneys" if field == "size" else value
            if quote in page["text"]:
                evidence.append(dict(field=field, value=value, source_url=page["url"], excerpt=quote))
                break
    fields = {item["field"] for item in evidence}
    return dict(name="Alpha Legal", source_type="firm_website", country="United States",
                size=3 if "size" in fields else None, size_unit="attorneys",
                practice_areas=["litigation"], evidence=evidence,
                contacts=[{"email": "hello@alpha.example"}] if "email" in fields else [])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.searches = []
        self.rows = [
            {"link": "https://software.example/", "title": "Law firm marketing software jobs"},
            {"link": ROOT, "title": "Alpha Legal law firm", "snippet": "Our team provides legal services"}]
        self.html = {
            ROOT: HOME_TEXT + "<a href='/contact'>Contact</a><a href='/team'>Team</a>",
            TEAM: "Our firm has 3 attorneys.", CONTACT: "Contact hello@alpha.example"}
        self.profile = dict(target_count=1, max_queries=1, max_candidates=1, max_pages_per_firm=3,
                            enable_verification=True, max_verifications=1, max_llm_calls=5)

    def session(self, name):
        return ResearchSession("prospect_research_agent", name, state_dir=self.root / "state", memory_dir=self.root / "memory")

    def transport(self, url, address, headers, max_bytes):
        self.calls.append(url)
        if url.endswith("robots.txt"):
            return HTTPResult(404, {}, b"", url)
        return HTTPResult(200, {"content-type": "text/html"}, self.html[url].encode(), url)

    def provider(self, name, url, headers=None):
        self.searches.append(name)
        if name == "serpapi":
            return 200, {"organic_results": self.rows}
        return 200, {"data": {"status": "valid", "verification": {"date": "2026-10-09"}}}

    def execute(self, name="run1", **overrides):
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "offline-search-token",
                                    "PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "offline-verify-token"}), \
             patch("agents.prospect_research_agent.agent.live_preflight"), \
             patch.object(SourceTools, "_provider_json", side_effect=self.provider), \
             patch.object(SourceTools, "_resolve_public_ips", return_value=["8.8.8.8"]), \
             patch.object(SourceTools, "_transport", side_effect=self.transport):
            return run_agent({**self.profile, **overrides}, session=self.session(name), extractor=extract)

    def test_search_ranking_then_targeted_pages_and_verification(self):
        result = self.execute()
        self.assertEqual(result["status"], "success", result["errors"])
        self.assertTrue(result["tests"]["passed"])
        self.assertEqual(self.calls, [ROOT + "robots.txt", ROOT, TEAM, CONTACT])
        self.assertEqual(result["budget"]["counts"]["queries"], 1)
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 3)
        self.assertEqual(result["budget"]["counts"]["verifications"], 1)
        self.assertEqual(result["data"]["firms"][0]["contacts"][0]["verification_status"], "valid")
        candidates = result["data"]["candidates"]
        self.assertEqual([item["status"] for item in candidates], ["rejected", "qualified"])
        self.assertEqual(candidates[1]["snippet"], self.rows[1]["snippet"])
        saved = json.loads(Path(result["artifacts"][0]["path"]).read_text())
        self.assertEqual(saved["data"]["candidates"], candidates)

    def test_new_evidence_is_fetched_before_retrying_a_bad_country_quote(self):
        self.html[ROOT] = "Alpha Legal law firm. Litigation. <a href='/contact'>Contact</a>"
        self.html[CONTACT] = HOME_TEXT + " Our firm has 3 attorneys. hello@alpha.example"
        original = extract
        seen = []
        def proposals(pages, request, budget, strategy, memory):
            seen.append([p['url'] for p in pages])
            proposed = original(pages, request, budget, strategy, memory)
            if len(pages) == 1:
                proposed['evidence'].append(dict(field='country', value='United States', source_url=ROOT, excerpt='Alpha Legal law firm.'))
            return proposed
        with patch(__name__ + '.extract', side_effect=proposals):
            result = self.execute()
        self.assertEqual(result['status'], 'success', result['errors'])
        self.assertEqual(len(seen), 2)
        self.assertIn(CONTACT, seen[1])

    def test_rate_limited_site_is_not_requested_three_times(self):
        def limited(url, *args):
            self.calls.append(url)
            return HTTPResult(404 if url.endswith('robots.txt') else 429, {}, b'', url)
        with patch.object(self, 'transport', side_effect=limited):
            result = self.execute()
        self.assertEqual(self.calls.count(ROOT), 1)
        self.assertEqual(result['budget']['counts']['llm_calls'], 0)

    def test_completed_fit_is_not_replaced_by_longer_partial_extraction(self):
        areas = ['contracts', 'tax', 'probate', 'employment', 'bankruptcy', 'family']
        self.html[ROOT] += ' Legal practice: ' + ', '.join(areas)
        self.html[TEAM] += ' Contact hello@alpha.example'
        original = extract
        def proposals(pages, request, budget, strategy, memory):
            proposed = original(pages, request, budget, strategy, memory)
            if len(pages) == 1:
                proposed['practice_areas'].extend(areas)
                proposed['evidence'].extend(dict(field='practice_area',value=area,source_url=ROOT,excerpt=area) for area in areas)
            return proposed
        with patch(__name__ + '.extract', side_effect=proposals):
            result = self.execute()
        self.assertEqual(result['data']['summary']['qualified'], 1)
        self.assertEqual(result['data']['firms'][0]['size'], 3)

    def test_recent_known_firm_skips_fetch_model_and_verification(self):
        self.execute()
        self.calls.clear()
        self.searches.clear()
        result = self.execute("run2")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.searches, ["serpapi"])
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 0)
        self.assertEqual(result["data"]["firms"], [])
        self.assertEqual(result["data"]["candidates"][1]["status"], "already_known")
        self.assertEqual(result["data"]["candidates"][1]["previous_run_id"], "run1")

    def test_known_firm_does_not_use_the_only_candidate_slot(self):
        self.execute()
        self.rows.append({"link": "https://new.example/", "title": "New law firm", "snippet": "Our team"})
        self.html["https://new.example/"] = "New law firm, no country or count published."
        self.calls.clear()
        result = self.execute("run2")
        self.assertNotIn(ROOT, self.calls)
        self.assertIn("https://new.example/", self.calls)
        self.assertEqual(result["data"]["firms"][0]["domain"], "new.example")

    def test_directory_resolves_published_website_before_qualification(self):
        listing = "https://lawzana.com/lawyer/alpha"
        self.rows = [{"link": listing, "title": "Alpha Legal law firm", "snippet": "Our team"}]
        self.html[listing] = f"Alpha Legal <a href='{ROOT}'>Visit website</a>"
        result = self.execute()
        self.assertEqual(result["status"], "success", result["errors"])
        self.assertEqual(result["data"]["firms"][0]["domain"], "alpha.example")
        self.assertEqual(result["data"]["candidates"][0]["resolved_url"], ROOT)
        self.assertTrue(all("lawzana.com" not in item["source_url"] for item in result["data"]["firms"][0]["evidence"]))

    def test_ambiguous_or_unsafe_directory_links_do_not_spend_model_calls(self):
        listing = "https://lawzana.com/lawyer/alpha"
        self.rows = [{"link": listing, "title": "Alpha law firm"}]
        for name, links in [("ambiguous", f"<a href='{ROOT}'>Website</a><a href='https://other.example/'>Website</a>"),
                            ("unsafe", "<a href='http://127.0.0.1/'>Website</a>")]:
            self.html[listing] = links
            result = self.execute(name)
            self.assertEqual(result["data"]["candidates"][0]["status"], "needs_research")
            self.assertEqual(result["budget"]["counts"]["llm_calls"], 0)

    def test_model_limit_preserves_already_sourced_partial_record(self):
        result = self.execute(max_llm_calls=1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["data"]["firms"][0]["name"], "Alpha Legal")
        self.assertEqual(result["data"]["firms"][0]["fit_status"], "needs_research")
        self.assertTrue(result["tests"]["passed"])

    def test_page_limit_never_repeats_a_model_call_without_new_evidence(self):
        result = self.execute(max_pages_per_firm=1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 1)
        self.assertEqual(self.calls, [ROOT + "robots.txt", ROOT])

    def test_profile_change_and_expired_history_are_researched_again(self):
        self.execute()
        prior = self.session("run1").artifact_path
        data = json.loads(prior.read_text())
        data["data"]["firms"][0]["researched_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        prior.write_text(json.dumps(data))
        self.calls.clear()
        self.execute("run2")
        self.assertIn(ROOT, self.calls)
        self.calls.clear()
        self.execute("run3", countries=["United States"])
        self.assertIn(ROOT, self.calls)

    def test_fixture_or_unvalidated_saved_result_is_not_reused(self):
        result = self.execute()
        prior = self.session("run1").artifact_path
        for fixture_mode, passed in [("fixture", True), ("live", False)]:
            result.update(mode=fixture_mode, tests={"passed": passed})
            prior.write_text(json.dumps(result))
            known, _ = recent_research(self.session("next"), ResearchRequest(**self.profile))
            self.assertEqual(known, {})

    def test_old_excluded_directory_is_not_cached_as_a_firm(self):
        result = self.execute()
        result["data"]["firms"][0].update(source_type="directory", fit_status="excluded")
        self.session("run1").artifact_path.write_text(json.dumps(result))
        known, _ = recent_research(self.session("next"), ResearchRequest(**self.profile))
        self.assertEqual(known, {})

    def test_force_refresh_can_bypass_fresh_history(self):
        self.execute()
        self.calls.clear()
        self.execute("run2", research_freshness_days=0)
        self.assertIn(ROOT, self.calls)

    def test_unsafe_search_urls_are_audited_without_persisting_query_secrets(self):
        self.rows = [{"link": "https://alpha.example/?token=private", "title": "Alpha law firm"}]
        result = self.execute()
        self.assertEqual(result["data"]["candidates"][0]["url"], None)
        self.assertNotIn("token=private", json.dumps(result))
        self.assertEqual(self.calls, [])

    def test_later_search_failure_keeps_candidates_from_first_search(self):
        original = self.provider
        def provider(name, url, headers=None):
            if name == "serpapi" and self.searches.count(name):
                raise SourceError("serpapi_request_failed: HTTP 400")
            return original(name, url, headers)
        self.provider = provider
        result = self.execute(max_queries=2, max_candidates=5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["firms"][0]["domain"], "alpha.example")
        self.assertEqual(result["errors"][0]["phase"], "discovery")

    def test_unavailable_team_page_uses_next_link_without_another_empty_extraction(self):
        self.html[ROOT] += "<a href='/about'>About</a>"
        self.html[ROOT + "about"] = "Our firm has 3 attorneys. Contact hello@alpha.example"
        original = self.transport
        def transport(url, address, headers, max_bytes):
            if url == TEAM:
                self.calls.append(url)
                return HTTPResult(403, {}, b"", url)
            return original(url, address, headers, max_bytes)
        self.transport = transport
        result = self.execute()
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.calls, [ROOT + "robots.txt", ROOT, TEAM, ROOT + "about"])
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 2)
        self.assertIn("HTTP 403", str(result["data"]["firms"][0]["research_errors"]))

    def test_no_more_results_become_discovered_leads_after_target_is_reached(self):
        self.rows.append({"link": "https://beta.example/", "title": "Beta law firm"})
        result = self.execute(max_candidates=2)
        self.assertEqual(result["data"]["candidates"][-1]["status"], "deferred")
        self.assertNotIn("https://beta.example/", self.calls)

    def test_corrupt_history_reports_warning_and_does_not_prevent_new_research(self):
        prior = self.session("bad").receipt_path
        prior.parent.mkdir(parents=True)
        prior.write_text("{broken")
        result = self.execute()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["errors"][0]["phase"], "history")

    def test_institutions_and_directory_indexes_do_not_take_firm_slots(self):
        self.rows = [
            {"link": "https://www.justice.gov/usao", "title": "Offices of the United States Attorneys"},
            {"link": "https://hls.harvard.edu/attorneys", "title": "Our attorneys law school"},
            {"link": "https://www.americanbar.org/groups/gpsolo/", "title": "Solo small firm lawyers"},
            {"link": "https://www.uslaw.org/", "title": "Legal services network"},
            {"link": "https://www.legal500.com/c/united-states/directory", "title": "Law firm directory"},
            {"link": ROOT, "title": "Alpha Legal law firm"},
        ]
        result = self.execute()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["budget"]["counts"]["candidates"], 1)
        self.assertEqual([item["status"] for item in result["data"]["candidates"]], ["rejected"] * 5 + ["qualified"])

    def test_blocked_firm_is_not_refetched_and_next_firm_can_complete(self):
        blocked = "https://blocked.example/"
        self.rows.insert(0, {"link": blocked, "title": "Boutique law firm attorneys"})
        original = self.transport
        def transport(url, address, headers, max_bytes):
            if url.startswith(blocked):
                self.calls.append(url)
                return HTTPResult(403, {}, b"", url)
            return original(url, address, headers, max_bytes)
        self.transport = transport
        result = self.execute(max_candidates=2)
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.calls.count(blocked + "robots.txt"), 1)
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 3)

    def test_unknown_page_without_links_does_not_repeat_extraction(self):
        self.html[ROOT] = "A placeholder page with no published firm details."
        result = self.execute()
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 1)
        self.assertEqual(result["data"]["summary"]["qualified"], 0)
        self.assertEqual(result["data"]["summary"]["needs_research"], 1)


if __name__ == "__main__":
    unittest.main()
