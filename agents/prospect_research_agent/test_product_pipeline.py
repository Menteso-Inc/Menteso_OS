"""Product routing, readiness and zero-spend tests with simulated real boundaries."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from .agent import qualify, run_agent
from .models import ExtractedFirm, ResearchRequest
from .qualification import enrich_product_fit, load_policy
from .rule_extraction import extract_rules
from .test_workflow import fixture
from .tools import HTTPResult, SourceError, SourceTools, normalize_source_url
from shared.prospect_store import ProspectStore, targeting_key
from shared.research_runtime import ResearchSession, RunBudget, BudgetExceeded


class ProductPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def firm(self, additions=""):
        page, proposal = fixture()
        page["text"] += " " + additions
        for field, marker in (("firm_stage", "launched"), ("website_need", "website"), ("workflow_need", "management")):
            if marker in additions:
                proposal["evidence"].append(dict(field=field, value=additions, excerpt=additions, source_url=page["url"]))
        return qualify(page["url"], ExtractedFirm.model_validate({key: value for key, value in proposal.items() if key != "website"}), [page], ResearchRequest(product="both"))

    def test_recent_new_practice_prioritizes_launch_and_keeps_manage_potential(self):
        row = self.firm(f"We launched our law firm in {datetime.now().year}.")
        self.assertEqual(row.primary_product, "launch")
        self.assertEqual(row.product_assessments["launch"].status, "potential_fit")
        self.assertEqual(row.product_assessments["manage"].confidence, "low")
        self.assertEqual(row.product_assessments["launch"].interest_status, "unknown")

    def test_old_founding_story_does_not_establish_launch_need(self):
        row = self.firm("We launched our law firm in 2001.")
        self.assertEqual(row.product_assessments["launch"].status, "unknown")
        self.assertEqual(row.primary_product, "manage")

    def test_two_sourced_needs_are_retained_without_two_firm_records(self):
        row = self.firm("We are seeking matter management software and a website.")
        self.assertEqual(row.primary_product, "both")
        self.assertEqual(set(row.product_assessments), {"manage", "launch"})
        self.assertTrue(all(value.status == "potential_fit" for value in row.product_assessments.values()))

    def test_forged_need_quote_is_not_accepted(self):
        page, proposal = fixture()
        proposal["evidence"].append(dict(field="website_need", value="We need a website", excerpt="We need a website", source_url=page["url"]))
        row = qualify(page["url"], ExtractedFirm.model_validate({key: value for key, value in proposal.items() if key != "website"}), [page], ResearchRequest(product="both"))
        self.assertEqual(row.product_assessments["launch"].status, "unknown")
        self.assertTrue(row.research_errors)

    def test_service_claim_is_not_mistaken_for_the_firms_need(self):
        row = self.firm("We help clients who are seeking case management and website services.")
        self.assertEqual(row.product_assessments["launch"].status, "unknown")

    def test_missing_size_blocks_both_product_readiness(self):
        page, proposal = fixture()
        proposal["evidence"] = [item for item in proposal["evidence"] if item["field"] != "size"]
        row = qualify(page["url"], ExtractedFirm.model_validate({key: value for key, value in proposal.items() if key != "website"}), [page], ResearchRequest(product="both"))
        self.assertTrue(all(value.status == "unknown" for value in row.product_assessments.values()))
        self.assertFalse(any(contact.research_ready for contact in row.contacts))

    def test_generic_mailbox_has_firm_message_and_sending_remains_off(self):
        row = self.firm()
        contact = row.contacts[0]
        contact.email, contact.name, contact.role = "info@example.com", None, None
        contact.verification_status = "valid"
        contact.verified_at = datetime.now(timezone.utc).date().isoformat()
        row.provenance = "live"
        enrich_product_fit(row, ResearchRequest(product="both"))
        self.assertEqual(contact.inbox_type, "generic")
        self.assertTrue(contact.research_ready)
        self.assertFalse(row.outreach_eligible)
        self.assertEqual(row.personalization_briefs[0].audience, "firm")
        self.assertIsNone(row.personalization_briefs[0].contact_name)
        self.assertTrue(row.personalization_briefs[0].hold_reasons)

    def test_stale_or_undated_verification_and_fixture_cannot_be_ready(self):
        for verified, mode in [(None, "live"), ((datetime.now(timezone.utc) - timedelta(days=9)).date().isoformat(), "live"), (datetime.now(timezone.utc).date().isoformat(), "fixture")]:
            row = self.firm()
            row.provenance = mode
            contact = row.contacts[0]
            contact.email, contact.name = "info@example.com", None
            contact.verification_status, contact.verified_at = "valid", verified
            enrich_product_fit(row, ResearchRequest())
            self.assertFalse(contact.research_ready)

    def test_external_footer_inbox_cannot_be_ready_for_this_firm(self):
        row = self.firm()
        row.provenance = "live"
        contact = row.contacts[0]
        contact.email, contact.name = "info@unrelated.example", None
        contact.verification_status = "valid"
        contact.verified_at = datetime.now(timezone.utc).date().isoformat()
        enrich_product_fit(row, ResearchRequest())
        self.assertFalse(contact.research_ready)
        self.assertIn("Mailbox affiliation", "; ".join(contact.readiness_reasons))

    def test_rules_withhold_conflicting_counts_and_do_not_guess_person(self):
        page = {"url": "https://example.com/", "titles": ["Example Law"],
                "text": "Example Law. Our law firm is in United States. Our firm has 3 attorneys. Our firm has 5 attorneys. Litigation. hello@example.com"}
        output = extract_rules([page], ResearchRequest(extraction_mode="rules"))
        self.assertIsNone(output["size"])
        self.assertIsNone(output["contacts"][0]["name"])

    def test_rules_do_not_count_a_clients_attorneys_or_infer_country_from_service_area(self):
        page = {"url": "https://example.com/", "titles": ["Example Law"],
                "text": "Example Law law firm. We advise 3 attorneys serving clients in United States. Litigation."}
        output = extract_rules([page], ResearchRequest(extraction_mode="rules"))
        self.assertIsNone(output["size"])
        self.assertIsNone(output["country"])

    def test_legal_structured_data_works_without_an_invented_country_or_business_type(self):
        raw = json.dumps({"@type": "LegalService", "name": "Example Law", "url": "https://example.com/", "address": {"addressCountry": "US"}})
        page = {"url": "https://example.com/", "text": raw + " Our firm has 3 attorneys. Litigation.", "structured_data": [raw]}
        proposed = ExtractedFirm.model_validate(extract_rules([page], ResearchRequest(extraction_mode="rules")))
        record = qualify(page["url"], proposed, [page], ResearchRequest(extraction_mode="rules"))
        self.assertEqual(record.fit_status, "qualified")
        self.assertEqual(record.country, "US")

    def test_practice_schema_name_is_not_a_firm_name_and_title_brand_is_retained(self):
        raw = json.dumps({"@type": "LegalService", "name": "Litigation", "url": "https://example.com/litigation"})
        page = {"url": "https://example.com/litigation", "titles": ["Litigation | Example Partners"],
                "text": "Litigation | Example Partners. Our law firm is in United States. Our firm has 3 attorneys. " + raw, "structured_data": [raw]}
        output = extract_rules([page], ResearchRequest(extraction_mode="rules"))
        self.assertEqual(output["name"], "Example Partners")

    def test_explicit_named_contact_uses_the_literal_role_email_association(self):
        page = {"url": "https://example.com/", "text": "Example Law. Our law firm. Jane Doe is our Managing Partner, email jane@example.com", "titles": ["Example Law"]}
        proposed = ExtractedFirm.model_validate(extract_rules([page], ResearchRequest(extraction_mode="rules")))
        row = qualify(page["url"], proposed, [page], ResearchRequest(extraction_mode="rules"))
        self.assertEqual(row.contacts[0].name, "Jane Doe")
        self.assertEqual(row.contacts[0].association_status, "sourced")

    def test_state_names_and_indirect_service_areas_do_not_become_countries(self):
        for statement in ("Office: New Jersey.", "Our law firm is based in Georgia.", "Our office serves customers based in India."):
            page={"url":"https://example.com/","titles":["Example Law"],"text":"Example Law law firm. " + statement}
            self.assertIsNone(extract_rules([page],ResearchRequest(extraction_mode="rules"))["country"],statement)

    def test_explicit_typed_country_disambiguates_jersey(self):
        page={"url":"https://example.com/","titles":["Example Law"],"text":"Example Law law firm. Country: Jersey."}
        self.assertEqual(extract_rules([page],ResearchRequest(extraction_mode="rules"))["country"],"Jersey")

    def test_pending_enrichment_resumes_saved_candidates_without_another_search(self):
        root_url, detail_url = "https://example.com/", "https://example.com/about"
        source = "<title>Example Law</title>Our law firm. Our firm has 3 attorneys. Litigation. info@example.com"
        html = {root_url:source, detail_url:source}
        queries = []
        def provider(name, url, headers=None):
            if "account.json" in url: return 200, {"plan_id":"free","plan_monthly_price":0,"plan_searches_left":10}
            queries.append(url)
            return 200, {"organic_results":[{"link":detail_url,"title":"Example Law law firm"}]}
        def transport(url,*args):
            return HTTPResult(404 if url.endswith("robots.txt") else 200, {"content-type":"text/html"}, b"" if url.endswith("robots.txt") else html[url].encode(),url)
        profile={"extraction_mode":"rules","spend_policy":"free_allowance_only","budget_usd":0,"max_llm_calls":0,"max_queries":1,"target_count":1}
        def session(): return ResearchSession("prospect_research_agent","resume-source",state_dir=self.root/'state',memory_dir=self.root/'memory')
        with patch.dict(os.environ,{"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY":"test-only"}), patch.object(SourceTools,"_provider_json",side_effect=provider), \
            patch.object(SourceTools,"_resolve_public_ips",return_value=["8.8.8.8"]), patch.object(SourceTools,"_transport",side_effect=transport):
            first=run_agent(profile,session=session())
            self.assertEqual(first['status'],'partial')
            html[root_url]+=" Our law firm is in United States."
            resumed=run_agent({**profile,"resume_run_id":"resume-source","refresh_pending":True},session=session())
        self.assertEqual(resumed['status'],'success',resumed['errors'])
        self.assertEqual(len(queries),1)
        self.assertEqual(resumed['budget']['counts']['queries'],1)
        self.assertEqual(resumed['budget']['counts']['candidates'],1)
        self.assertEqual(resumed['budget']['counts']['llm_calls'],0)
        ResearchRequest.model_validate(resumed['request_profile'])
        archive=session().run_dir/'before-enrichment.json'
        self.assertEqual(json.loads(archive.read_text())['data']['firms'][0]['fit_status'],'needs_research')

    def test_only_supported_tracking_queries_are_stripped(self):
        self.assertEqual(normalize_source_url("https://example.com/about?utm_source=search&gclid=123#section"), "https://example.com/about")
        for url in ("https://example.com/?token=private", "http://127.0.0.1/?utm_source=x", "https://user:password@example.com/?utm_source=x", "https://example.com/?utm_source=x&api_key=private"):
            with self.assertRaises(SourceError): normalize_source_url(url)

    def test_free_policy_rejects_models_and_hard_blocks_model_reservations(self):
        with self.assertRaises(ValueError): ResearchRequest(spend_policy="free_allowance_only")
        budget = RunBudget(ResearchRequest(extraction_mode="rules", spend_policy="free_allowance_only", budget_usd=0))
        with self.assertRaises(BudgetExceeded): budget.consume("llm_calls")
        self.assertEqual(budget.snapshot()["reserved_cost_usd"], 0)

    def test_provider_unknown_paid_or_exhausted_balance_prevents_search(self):
        request = ResearchRequest(extraction_mode="rules", spend_policy="free_allowance_only", budget_usd=0, max_queries=1)
        for account in ({}, {"plan_name": "Paid", "plan_monthly_price": 10, "plan_searches_left": 10}, {"plan_id": "free", "plan_monthly_price": 0, "plan_searches_left": 0}):
            source = SourceTools(request, RunBudget(request))
            calls = []
            def response(name, url, headers=None):
                calls.append(url)
                return 200, account
            with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "test-only"}), patch.object(source, "_provider_json", side_effect=response):
                with self.assertRaisesRegex(SourceError, "free_allowance_unavailable"): source.discover()
            self.assertTrue(all("account.json" in url for url in calls))
            self.assertEqual(source.budget.counts["queries"], 0)

    def test_query_rotation_persists_is_idempotent_and_policy_changes_invalidate_inventory(self):
        policy, request = load_policy(), ResearchRequest(product="both")
        store = ProspectStore(self.root)
        key = targeting_key(request, policy.fingerprint)
        self.assertEqual(store.reserve_queries(key, "one", ["manage", "launch"], 1), ["manage"])
        self.assertEqual(ProspectStore(self.root).reserve_queries(key, "two", ["manage", "launch"], 1), ["launch"])
        self.assertEqual(store.reserve_queries(key, "one", ["manage", "launch"], 1), ["manage"])
        row = self.firm().model_dump()
        row["provenance"] = "live"
        store.save(key, "one", row); store.save(key, "two", row)
        self.assertEqual(len(store.records(key)), 1)
        self.assertEqual(store.records(targeting_key(request, "changed-policy")), [])
        fixture_row = copy.deepcopy(row); fixture_row["provenance"] = "fixture"
        store.save(key, "fixture", fixture_row)
        self.assertEqual(len(store.records(key, "fixture")), 1)
        self.assertEqual(len(store.records(key)), 1)

    def test_independent_simulated_discovery_qualifies_both_without_any_model_call(self):
        url = "https://example.com/"
        html = f"<title>Example Law</title><h1>Example Law</h1><p>Our law firm is in United States.</p><p>Our firm has 3 attorneys.</p><p>Litigation.</p><p>We launched our law firm in {datetime.now().year}.</p><p>Contact info@example.com</p>"
        provider_calls = []
        def provider(name, target, headers=None):
            provider_calls.append(target)
            if "serpapi.com/account" in target: return 200, {"plan_id": "free", "plan_monthly_price": 0, "plan_searches_left": 10}
            if "serpapi.com/search" in target: return 200, {"organic_results": [{"title": "Example Law law firm", "link": url + "?utm_source=search"}]}
            if target.endswith("/account"): return 200, {"data": {"plan_name": "Free", "requests": {"credits": {"remaining": 5}}}}
            return 200, {"data": {"status": "valid", "verification": {"date": datetime.now(timezone.utc).date().isoformat()}}}
        def transport(target, *args):
            return HTTPResult(404 if target.endswith("robots.txt") else 200, {"content-type": "text/html"}, b"" if target.endswith("robots.txt") else html.encode(), target)
        session = ResearchSession("prospect_research_agent", "independent", state_dir=self.root / "state", memory_dir=self.root / "memory")
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "test-only", "PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "test-only"}), \
             patch.object(SourceTools, "_provider_json", side_effect=provider), patch.object(SourceTools, "_resolve_public_ips", return_value=["8.8.8.8"]), \
             patch.object(SourceTools, "_transport", side_effect=transport), patch("shared.llm.validate_llm_readiness", side_effect=AssertionError("paid model readiness must not be invoked")):
            result = run_agent({"product": "both", "extraction_mode": "rules", "spend_policy": "free_allowance_only", "budget_usd": 0,
                "max_llm_calls": 0, "max_queries": 1, "target_count": 1, "enable_verification": True}, session=session)
        self.assertEqual(result["status"], "success", result["errors"])
        self.assertTrue(result["tests"]["passed"])
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 0)
        row = result["data"]["firms"][0]
        self.assertEqual(row["primary_product"], "launch")
        self.assertTrue(row["contacts"][0]["research_ready"])
        self.assertFalse(row["outreach_eligible"])
        self.assertEqual(result["inventory"]["unique_firms"], 1)
        self.assertTrue(all(brief["audience"] == "firm" for brief in row["personalization_briefs"]))
        memory = json.loads(session.memory_path.read_text())
        self.assertEqual(memory["stats"]["total_runs"], 1)


if __name__ == "__main__":
    unittest.main()
