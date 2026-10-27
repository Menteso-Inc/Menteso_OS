"""Behavioral tests: real schemas/lifecycle with explicit synthetic evidence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.prospect_research_agent.agent import AGENT_NAME, qualify, run_agent, validate_request
from agents.prospect_research_agent.models import ExtractedFirm, ResearchRequest
from shared.research_runtime import ResearchSession, RunBudget


def fixture(domain="example.com", country="United States", size=3):
    url = f"https://{domain}/"
    name = f"Example Legal {country}"
    sentences = [name, f"Our law firm is in {country}.", f"Our firm has {size} attorneys.",
                 "Our legal practice is litigation.", "Jane Doe is our Managing Partner.", f"Contact jane@{domain}."]
    evidence = [
        {"field": "name", "value": name, "source_url": url, "excerpt": sentences[0]},
        {"field": "country", "value": country, "source_url": url, "excerpt": sentences[1]},
        {"field": "size", "value": str(size), "source_url": url, "excerpt": sentences[2]},
        {"field": "practice_area", "value": "litigation", "source_url": url, "excerpt": sentences[3]},
        {"field": "contact_name", "value": "Jane Doe", "source_url": url, "excerpt": sentences[4]},
        {"field": "contact_role", "value": "Managing Partner", "source_url": url, "excerpt": sentences[4]},
        {"field": "email", "value": f"jane@{domain}", "source_url": url, "excerpt": sentences[5]},
    ]
    page = {"url": url, "text": " ".join(sentences), "retrieved_at": "2026-10-07T00:00:00+00:00"}
    extraction = {"website": url, "name": name, "source_type": "firm_website", "country": country, "size": size, "size_unit": "attorneys",
                  "practice_areas": ["litigation"], "contacts": [{"name": "Jane Doe", "role": "Managing Partner", "email": f"jane@{domain}"}], "evidence": evidence}
    return page, extraction


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def session(self, run_id="test-run"):
        return ResearchSession(AGENT_NAME, run_id=run_id, state_dir=self.root / "state", memory_dir=self.root / "memory")

    def payload(self, examples=None, **overrides):
        examples = examples or [fixture()]
        return {"mode": "fixture", "target_count": 1, "fixture_pages": [item[0] for item in examples],
                "fixture_extractions": [item[1] for item in examples], **overrides}

    def test_qualified_records_and_durable_artifact(self):
        result = run_agent(self.payload(), session=self.session())
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["tests"]["passed"])
        self.assertEqual(result["data"]["summary"]["qualified"], 1)
        row = result["data"]["firms"][0]
        self.assertEqual(row["country"], "US")
        self.assertFalse(row["outreach_eligible"])
        self.assertEqual(row["contacts"][0]["verification_status"], "published_unverified")
        saved = json.loads(Path(result["artifacts"][0]["path"]).read_text())
        self.assertEqual(saved["data"]["firms"], result["data"]["firms"])

    def test_iso_country_requires_explicit_country_evidence(self):
        page, proposal = fixture()
        proposal['country'] = 'US'
        proposal['evidence'][1]['value'] = 'US'
        row = qualify(page['url'], ExtractedFirm.model_validate({k:v for k,v in proposal.items() if k != 'website'}), [page], ResearchRequest())
        self.assertEqual(row.country, 'US')
        proposal['evidence'][1]['excerpt'] = 'Contact us for business services.'
        page['text'] += ' Contact us for business services.'
        row = qualify(page['url'], ExtractedFirm.model_validate({k:v for k,v in proposal.items() if k != 'website'}), [page], ResearchRequest())
        self.assertIsNone(row.country)

    def test_multicountry_profile_does_not_assume_us(self):
        result = run_agent(self.payload([fixture(), fixture("example.org", "India", 1)], target_count=2), session=self.session())
        self.assertEqual(result["data"]["summary"]["countries"], {"US": 1, "IN": 1})
        self.assertEqual(result["status"], "success")

    def test_country_filter_excludes_other_country(self):
        result = run_agent(self.payload(countries=["India"]), session=self.session())
        self.assertEqual(result["data"]["summary"]["excluded"], 1)
        self.assertEqual(result["status"], "partial")

    def test_directory_with_complete_firm_facts_cannot_qualify_as_official_site(self):
        page, proposal = fixture()
        proposal['source_type'] = 'directory'
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertEqual(result['data']['summary']['qualified'], 0)
        self.assertEqual(result['data']['summary']['excluded'], 1)
        self.assertEqual(result['data']['firms'][0]['contacts'], [])

    def test_size_filter_and_selected_segment(self):
        result = run_agent(self.payload(target_segments=["solo"]), session=self.session())
        self.assertEqual(result["data"]["summary"]["excluded"], 1)

    def test_missing_size_is_not_guessed(self):
        page, proposal = fixture()
        proposal["evidence"] = [item for item in proposal["evidence"] if item["field"] != "size"]
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertIsNone(result["data"]["firms"][0]["size"])
        self.assertEqual(result["data"]["summary"]["needs_research"], 1)

    def test_published_firm_inbox_survives_model_omission_without_person_assignment(self):
        page, proposal = fixture()
        proposal['contacts'] = []
        proposal['evidence'] = [item for item in proposal['evidence'] if item['field'] not in {'email', 'contact_name', 'contact_role'}]
        page['text'] += ' Outside vendor: vendor@unrelated.example.'
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        contacts = result['data']['firms'][0]['contacts']
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]['email'], 'jane@example.com')
        self.assertIsNone(contacts[0]['name'])
        self.assertEqual(contacts[0]['association_status'], 'unconfirmed')

    def test_staff_are_not_attorneys(self):
        page, proposal = fixture()
        proposal["size_unit"] = "people"
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertIsNone(result["data"]["firms"][0]["size"])

    def test_inhouse_legal_team_is_not_a_law_firm(self):
        page, proposal = fixture()
        page["text"] = page["text"].replace("Our law firm", "Our internal legal department")
        proposal["evidence"][1]["excerpt"] = proposal["evidence"][1]["excerpt"].replace("Our law firm", "Our internal legal department")
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertEqual(result["data"]["summary"]["needs_research"], 1)

    def test_mid_size_ceiling_is_configurable(self):
        result = run_agent(self.payload([fixture(size=70)], size_max=80), session=self.session())
        self.assertEqual(result["data"]["firms"][0]["segment"], "mid_size")
        self.assertEqual(result["status"], "success")

    def test_address_number_cannot_be_lawyer_count(self):
        page, proposal = fixture()
        text = "We have attorneys at 3 Main Street."
        page["text"] = page["text"].replace("Our firm has 3 attorneys.", text)
        next(item for item in proposal["evidence"] if item["field"] == "size")["excerpt"] = text
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertIsNone(result["data"]["firms"][0]["size"])

    def test_invented_excerpt_and_email_are_removed(self):
        page, proposal = fixture()
        proposal["contacts"][0]["email"] = "invented@example.com"
        proposal["evidence"][-1].update(value="invented@example.com", excerpt="Email invented@example.com.")
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertIsNone(result["data"]["firms"][0]["contacts"][0]["email"])
        self.assertTrue(result["data"]["firms"][0]["research_errors"])

    def test_cross_page_fabricated_source_is_removed(self):
        page, proposal = fixture()
        proposal["evidence"][0]["source_url"] = "https://unfetched.example.net/"
        result = run_agent(self.payload([(page, proposal)]), session=self.session())
        self.assertIsNone(result["data"]["firms"][0]["name"])

    def test_multiple_pages_do_not_duplicate_a_firm(self):
        page, proposal = fixture()
        second = {**page, "url": page["url"] + "team"}
        result = run_agent(self.payload([(page, proposal), (second, proposal)], target_count=2), session=self.session())
        self.assertEqual(result["data"]["summary"]["researched"], 1)

    def test_fixture_mode_never_calls_provider(self):
        with patch("agents.prospect_research_agent.tools.SourceTools.discover", side_effect=AssertionError("network")), patch("agents.prospect_research_agent.tools.SourceTools.read_firm", side_effect=AssertionError("network")):
            self.assertEqual(run_agent(self.payload(), session=self.session())["status"], "success")

    def test_live_cannot_accept_fixture_payload(self):
        payload = self.payload(mode="live")
        result = run_agent(payload, session=self.session())
        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["errors"][0]["phase"], "input")

    def test_live_startup_missing_key_fails_before_sources(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "PROSPECT_RESEARCH_AGENT_LLM_PROVIDER": "openai"}), patch("agents.prospect_research_agent.tools.SourceTools.discover", side_effect=AssertionError("network")):
            result = run_agent({}, session=self.session())
        self.assertEqual(result["status"], "failure")
        self.assertTrue(result["preflight"])
        self.assertEqual(result["budget"]["counts"]["queries"], 0)

    def test_unsafe_or_unbounded_profile_is_rejected(self):
        for payload in ({"target_count": 100}, {"size_min": 20, "size_max": 2}, {"seed_urls": ["file:///private"]}, {"publish": True}, {"resume_run_id": "../../private"}):
            with self.subTest(payload=payload):
                self.assertEqual(run_agent(payload, session=self.session())["status"], "failure")

    def test_cancel_preserves_first_checkpoint_and_resume_deduplicates(self):
        session = self.session()
        payload = self.payload([fixture(), fixture("example.org", "India", 1)], target_count=2)
        cancel = {"flag": False}
        checkpoint = session.checkpoint
        def save_and_cancel(result):
            path = checkpoint(result)
            if len(result["data"]["firms"]) == 1:
                cancel["flag"] = True
            return path
        session.checkpoint = save_and_cancel
        stopped = run_agent(payload, session=session, cancelled=lambda: cancel["flag"])
        self.assertEqual(stopped["status"], "cancelled")
        self.assertEqual(len(stopped["data"]["firms"]), 1)
        resumed = run_agent({**payload, "resume_run_id": "test-run"}, session=self.session())
        self.assertEqual(resumed["status"], "success")
        self.assertEqual(len(resumed["data"]["firms"]), 2)
        self.assertEqual(resumed["budget"]["counts"]["candidates"], 2)
        self.assertEqual(len(resumed["data"]["candidates"]), 2)

    def test_resume_accepts_exact_legacy_profile_before_freshness_setting(self):
        import hashlib
        session = self.session()
        payload = self.payload()
        run_agent(payload, session=session)
        saved = session.read_checkpoint()
        profile = saved["request_profile"]
        profile.pop("research_freshness_days")
        saved["profile_fingerprint"] = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
        session.checkpoint(saved)
        result = run_agent({**payload, "resume_run_id": "test-run"}, session=session)
        self.assertEqual(result["status"], "success")

    def test_resume_profile_mismatch_is_rejected(self):
        run_agent(self.payload(), session=self.session())
        result = run_agent(self.payload(resume_run_id="test-run", countries=["India"]), session=self.session())
        self.assertEqual(result["status"], "failure")

    def test_learning_is_private_and_not_prospect_data(self):
        result = run_agent(self.payload(), session=self.session())
        memory = self.session().load_memory()
        encoded = json.dumps(memory)
        self.assertNotIn("jane@example.com", encoded)
        self.assertNotIn("Example Legal", encoded)
        self.assertEqual(memory["stats"]["evaluated_runs"], 1)

    def live_tools(self, page, budget_holder, *, first_read_fails=False, source_error="temporary network timeout"):
        class Invocation:
            def __init__(self, callback): self.callback = callback
            def invoke(self, payload): return self.callback(**payload)
        class Providers:
            def __init__(self): self.read_strategies = []
            def discover(self, strategy): return [page["url"]]
            def read_firm(self, url, strategy):
                self.read_strategies.append(strategy)
                if first_read_fails and len(self.read_strategies) == 1:
                    return [{"url": url, "text": "", "error": source_error}]
                return [page]
            def verify_email(self, email):
                budget_holder["budget"].consume("verifications")
                return {"status": "valid", "verified_at": "2026-10-07", "provider": "offline-test"}
            def get_langchain_tools(self):
                return {"discover": Invocation(self.discover), "read_firm": Invocation(self.read_firm), "verify_email": Invocation(self.verify_email)}
        return Providers()

    def test_live_workflow_recovery_feeds_redacted_error_to_changed_strategy(self):
        page, proposal = fixture()
        holder, attempts = {}, []
        def extraction(pages, request, budget, strategy, memory):
            holder["budget"] = budget
            budget.consume("llm_calls")
            attempts.append((strategy, memory.get("recovery_context")))
            if len(attempts) == 1:
                raise ValueError("Invalid extraction schema")
            return ExtractedFirm.model_validate({key: value for key, value in proposal.items() if key != "website"})
        with patch("agents.prospect_research_agent.agent.live_preflight"):
            result = run_agent({"target_count": 1}, session=self.session(), source_tools=self.live_tools(page, holder), extractor=extraction)
        self.assertEqual(result["status"], "success")
        self.assertEqual([item[0] for item in attempts], ["standard", "focused"])
        self.assertIn("error", attempts[1][1])
        self.assertEqual(result["budget"]["counts"]["llm_calls"], 2)

    def test_failed_pages_are_refetched_on_adjusted_recovery(self):
        page, proposal = fixture()
        holder = {}
        providers = self.live_tools(page, holder, first_read_fails=True)
        def extraction(pages, request, budget, strategy, memory):
            return ExtractedFirm.model_validate({key: value for key, value in proposal.items() if key != "website"})
        with patch("agents.prospect_research_agent.agent.live_preflight"):
            result = run_agent({"target_count": 1}, session=self.session(), source_tools=providers, extractor=extraction)
        self.assertEqual(result["status"], "success")
        self.assertEqual(providers.read_strategies, ["standard", "focused"])

    def test_rejected_required_quote_triggers_grounded_recovery(self):
        page, proposal = fixture()
        attempts = []
        def extraction(pages, request, budget, strategy, memory):
            attempts.append(strategy)
            output = copy.deepcopy(proposal)
            if len(attempts) == 1:
                output['evidence'][0]['excerpt'] = 'Invented firm heading'
            else:
                self.assertIn('Firm name evidence is missing', memory['recovery_context']['error'])
            return ExtractedFirm.model_validate({k: v for k, v in output.items() if k != 'website'})
        with patch('agents.prospect_research_agent.agent.live_preflight'):
            result = run_agent({'target_count': 1}, session=self.session(),
                               source_tools=self.live_tools(page, {}), extractor=extraction)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(attempts, ['standard', 'focused'])

    def test_source_403_is_not_a_global_provider_authentication_failure(self):
        page, proposal = fixture()
        providers = self.live_tools(page, {}, first_read_fails=True, source_error="robots_unavailable: HTTP 403")
        extraction = lambda *args: ExtractedFirm.model_validate({k: v for k, v in proposal.items() if k != "website"})
        with patch("agents.prospect_research_agent.agent.live_preflight"):
            result = run_agent({"target_count": 1}, session=self.session(), source_tools=providers, extractor=extraction)
        self.assertEqual(result["status"], "failure")
        self.assertEqual(providers.read_strategies, ["standard"])
        self.assertEqual(result["errors"][0]["phase"], "research")
        self.assertIn("HTTP 403", result["data"]["firms"][0]["research_errors"][0])

    def test_optional_verification_limit_preserves_qualified_firm(self):
        page, proposal = fixture()
        associated = 'Jane Doe is our Managing Partner. Contact jane@example.com.'
        page['text'] += ' ' + associated
        for item in proposal['evidence']:
            if item['field'] in {'contact_name', 'contact_role', 'email'}: item['excerpt'] = associated
        holder = {}
        def extraction(pages, request, budget, strategy, memory):
            holder["budget"] = budget
            return ExtractedFirm.model_validate({key: value for key, value in proposal.items() if key != "website"})
        with patch("agents.prospect_research_agent.agent.live_preflight"):
            result = run_agent({"target_count": 1, "enable_verification": True, "max_verifications": 0},
                               session=self.session(), source_tools=self.live_tools(page, holder), extractor=extraction)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["data"]["summary"]["qualified"], 1)
        self.assertEqual(result["data"]["firms"][0]["contacts"][0]["verification_status"], "published_unverified")

    def test_exhausted_extractions_are_evaluated_failures(self):
        page, _ = fixture()
        holder, strategies = {}, []
        def extraction(pages, request, budget, strategy, memory):
            strategies.append(strategy)
            raise ValueError("Invalid extraction schema")
        with patch("agents.prospect_research_agent.agent.live_preflight"):
            result = run_agent({"target_count": 1}, session=self.session(), source_tools=self.live_tools(page, holder), extractor=extraction)
        self.assertEqual(strategies, ["standard", "focused", "minimal_evidence"])
        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["memory"]["stats"]["failed_runs"], 1)


class FrameworkIntegrationTests(unittest.TestCase):
    def test_openai_token_budget_handles_long_source_text_and_rejects_oversized_tokens(self):
        from agents.prospect_research_agent.tasks import input_token_reservation
        text = "A law firm provides legal services. " * 1000
        messages = [{"role": "user", "content": text}]
        self.assertGreater(len(json.dumps(messages)), 20000)
        self.assertLess(input_token_reservation(messages, "openai/gpt-4o-mini"), 20000)
        self.assertGreater(input_token_reservation([{"role": "user", "content": "law " * 21000}], "openai/gpt-4o-mini"), 20000)
        self.assertGreater(input_token_reservation(messages, "unsupported-model"), 20000)

    def test_prompt_preserves_later_contact_pages_and_footers(self):
        from agents.prospect_research_agent.tasks import extraction_prompt
        pages = [{'url':'https://example.com/', 'text':'Legal practice. ' * 9000 + ' FIRST_FOOTER'},
                 {'url':'https://example.com/contact', 'text':'Contact Jane. ' * 6000 + ' CONTACT_FOOTER'}]
        prompt = extraction_prompt(pages, ResearchRequest(max_input_tokens=20000))
        self.assertIn('FIRST_FOOTER', prompt)
        self.assertIn('CONTACT_FOOTER', prompt)
        self.assertIn('https://example.com/contact', prompt)

    def test_source_secrets_are_redacted_before_prompt_creation(self):
        import uuid
        from agents.prospect_research_agent.tasks import extraction_prompt
        page, _ = fixture()
        secret = uuid.uuid4().hex
        page["text"] += " API_KEY=" + secret
        with patch.dict("os.environ", {"OPENAI_API_KEY": secret}):
            prompt = extraction_prompt([page], ResearchRequest())
        self.assertNotIn(secret, prompt)
        self.assertIn("[REDACTED]", prompt)

    def test_real_crewai_task_runs_with_injected_offline_llm(self):
        from crewai import BaseLLM
        from agents.prospect_research_agent.tasks import extract_with_crew
        page, proposal = fixture()
        expected = {key: value for key, value in proposal.items() if key != "website"}
        class OfflineLLM(BaseLLM):
            def __init__(self):
                super().__init__(model="offline-fixture", temperature=0)
            def call(self, messages, **kwargs):
                return json.dumps(expected)
            def supports_stop_words(self):
                return False
        request = ResearchRequest(max_input_tokens=20000)
        budget = RunBudget(request)
        with patch("shared.llm.create_crewai_llm", return_value=OfflineLLM()):
            extracted = extract_with_crew([page], request, budget)
        self.assertEqual(extracted.name, expected["name"])
        self.assertGreaterEqual(budget.snapshot()["counts"]["llm_calls"], 1)


class ManagerIntegrationTests(unittest.TestCase):
    def test_real_manager_and_specialist_complete_fixture_handoff_and_export(self):
        from agents.lexmom_marketing_agent.agent import run_agent as run_manager, resolve_research_artifact
        real_session = ResearchSession
        page, proposal = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def isolated_session(agent_name, run_id=None, **kwargs):
                return real_session(agent_name, run_id=run_id, state_dir=root / "state", memory_dir=root / "memory")
            parent = isolated_session("lexmom_marketing_agent", "manager-integration")
            with patch("shared.research_runtime.ResearchSession", side_effect=isolated_session):
                result = run_manager({"mode": "fixture", "target_count": 1,
                                      "fixture_pages": [page], "fixture_extractions": [proposal]}, session=parent)
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["tests"]["passed"])
            self.assertTrue(result["specialist_tests"]["passed"])
            self.assertEqual(len(result["rows"]), 1)
            approved = resolve_research_artifact(result["run_id"], "result.json", state_root=root / "state")
            self.assertIsNotNone(approved)
            self.assertEqual(json.loads(approved.read_text())["data"]["firms"], result["rows"])


if __name__ == "__main__":
    unittest.main()
