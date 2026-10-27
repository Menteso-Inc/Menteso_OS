"""Offline runtime checks; all artifacts, logs and memories use temporary roots."""

import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shared import llm
from shared.research_runtime import BudgetExceeded, ResearchSession, RunBudget, RunCancelled, redact, run_recovery


def request(**overrides):
    values = dict(deadline_seconds=60, max_queries=2, max_candidates=3,
                  max_pages_per_firm=2, max_llm_calls=2, max_verifications=1,
                  max_input_tokens=10000, max_output_tokens=1500,
                  budget_usd=1, unit_costs={})
    values.update(overrides)
    return SimpleNamespace(**values)


class BudgetTests(unittest.TestCase):
    def test_reservations_reject_before_increment_and_cost_decimal_boundary(self):
        budget = RunBudget(request(max_queries=4, budget_usd=0.3, unit_costs={"queries": 0.1}))
        budget.consume("queries", 3)
        self.assertEqual(budget.snapshot()["reserved_cost_usd"], 0.3)
        with self.assertRaises(BudgetExceeded):
            budget.consume("queries")
        self.assertEqual(budget.counts["queries"], 3)
        self.assertIn("actual billed spend is unknown", budget.snapshot()["cost_basis"])

    def test_each_counter_and_aggregate_page_limit(self):
        budget = RunBudget(request())
        for kind, limit in budget.limits.items():
            budget.consume(kind, limit)
            with self.assertRaises(BudgetExceeded):
                budget.consume(kind)
        self.assertEqual(budget.counts["pages"], 36)
        with self.assertRaises(ValueError):
            budget.consume("invented")
        with self.assertRaises(ValueError):
            budget.consume("queries", -1)

    def test_deadline_uses_monotonic_clock_and_cancellation(self):
        with patch("shared.research_runtime.time.monotonic", return_value=100):
            budget = RunBudget(request(deadline_seconds=5))
        with patch("shared.research_runtime.time.monotonic", return_value=106):
            with self.assertRaises(BudgetExceeded):
                budget.check()
            self.assertEqual(budget.remaining_seconds(), 0)
        event = threading.Event()
        cancelled = RunBudget(request(), cancelled=event)
        event.set()
        with self.assertRaises(RunCancelled):
            cancelled.consume("pages")
        flag = RunBudget(request(), cancelled=lambda: True)
        with self.assertRaises(RunCancelled):
            flag.check()

    def test_invalid_nonfinite_budgets_are_rejected(self):
        for overrides in ({"deadline_seconds": float("inf")}, {"budget_usd": float("nan")},
                          {"unit_costs": {"queries": -1}}, {"max_pages_per_firm": True}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                RunBudget(request(**overrides))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def session(self, run_id="pilot", agent="prospect_research_agent"):
        return ResearchSession(agent, run_id, state_dir=self.root / "state", memory_dir=self.root / "agents")

    def finish(self, run_id, outcome, duration=1):
        return self.session(run_id).finish({"rows": [{"name": "Private Firm"}]}, outcome,
                                          "standard", "private@example.com business insight", duration)

    def test_restart_preserves_full_checkpoint_and_secret_redaction(self):
        original = {"rows": [{"email": "contact@firm.example", "name": "Private Firm"}],
                    "request": {"max_input_tokens": 10000}, "api_key": "fixture-sensitive",
                    "error": "provider failed fixture-sensitive"}
        with patch.dict(os.environ, {"TEST_API_KEY": "fixture-sensitive"}):
            path = self.session().checkpoint(original)
            restarted = self.session().read_checkpoint()
        self.assertTrue(Path(path).is_file())
        self.assertEqual(restarted["rows"], original["rows"])
        self.assertEqual(restarted["request"]["max_input_tokens"], 10000)
        self.assertEqual(restarted["api_key"], "[REDACTED]")
        self.assertNotIn("fixture-sensitive", restarted["error"])
        self.assertIsNone(self.session("missing").read_checkpoint())

    def test_artifacts_keep_business_records_and_logs_memory_exclude_them(self):
        manifest = self.finish("one", "success")
        dataset = json.loads(Path(manifest["artifact_path"]).read_text(encoding="utf-8"))
        self.assertEqual(dataset["rows"][0]["name"], "Private Firm")
        memory_text = self.session("one").memory_path.read_text(encoding="utf-8")
        log_text = self.session("one").log_path.read_text(encoding="utf-8")
        self.assertNotIn("Private Firm", memory_text + log_text)
        self.assertNotIn("private@example.com", memory_text + log_text)
        self.assertEqual(manifest["stats"]["successful_runs"], 1)

    def test_traversal_and_corrupt_state_are_rejected_without_overwrite(self):
        for identifier in ("../escape", "..", "absolute/path", "C:\\escape", "a.b", ""):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.session(agent=identifier)
        with self.assertRaises(ValueError):
            self.session(run_id="../escape")
        session = self.session()
        session.memory_path.parent.mkdir(parents=True)
        session.memory_path.write_text("{ broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            session.load_memory()
        self.assertEqual(session.memory_path.read_text(encoding="utf-8"), "{ broken")

    def test_atomic_replace_failure_keeps_previous_artifact_and_cleans_temp(self):
        session = self.session()
        session.checkpoint({"version": 1})
        with patch("shared.research_runtime.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                session.checkpoint({"version": 2})
        self.assertEqual(session.read_checkpoint(), {"version": 1})
        self.assertEqual(list(session.run_dir.glob("*.tmp")), [])

    def test_lifetime_statistics_remain_correct_after_pruning(self):
        for number in range(10):
            self.finish(f"success_{number}", "success", 2)
        for number in range(100):
            manifest = self.finish(f"failure_{number}", "failure", 1)
        stats = manifest["stats"]
        self.assertEqual(stats["total_runs"], 110)
        self.assertEqual(stats["evaluated_runs"], 110)
        self.assertEqual(stats["successful_runs"], 10)
        self.assertAlmostEqual(stats["success_rate"], 10 / 110)
        self.assertAlmostEqual(stats["avg_execution_time"], 120 / 110)
        self.assertTrue(stats["review_required"])
        self.assertEqual(len(self.session().load_memory()["learnings"]), 100)

    def test_unevaluated_runs_do_not_erase_rolling_evaluated_history(self):
        for number in range(10):
            self.finish(f"bad_{number}", "failure")
        for number in range(101):
            manifest = self.finish(f"pending_{number}", "preflight")
        self.assertEqual(manifest["stats"]["evaluated_runs"], 10)
        self.assertEqual(manifest["stats"]["rolling_10_success_rate"], 0)
        self.assertTrue(manifest["review_required"])

    def test_completed_run_is_idempotent_and_resume_updates_once(self):
        self.finish("resume", "partial", 2)
        manifest = self.finish("resume", "success", 3)
        replay = self.finish("resume", "success", 9)
        self.assertEqual(replay["stats"]["total_runs"], 1)
        self.assertEqual(replay["stats"]["evaluated_runs"], 1)
        self.assertEqual(replay["stats"]["avg_execution_time"], 3)
        self.assertEqual(manifest["stats"]["successful_runs"], 1)
        self.assertEqual(len(self.session().log_path.read_text(encoding="utf-8").splitlines()), 2)
        corrected = self.finish("resume", "failure", 4)
        self.assertEqual(corrected["stats"]["avg_execution_time"], 4)
        self.assertEqual(corrected["stats"]["successful_runs"], 0)
        self.assertEqual(corrected["stats"]["failed_runs"], 1)

    def test_strategy_changes_are_versioned_and_each_agent_memory_is_private(self):
        first = self.session("first")
        self.assertEqual(first.best_strategy("prospect_research"), "standard")
        self.finish("first", "failure")
        second = self.session("second")
        self.assertEqual(second.best_strategy("prospect_research"), "focused")
        memory = second.load_memory()
        self.assertEqual(memory["refined_prompts"]["prospect_research"]["version"], 2)
        self.assertEqual(len(memory["adaptations"]), 2)
        self.assertEqual(self.session(agent="lexmom_marketing_agent").load_memory()["learnings"], [])

    def test_recovered_strategy_and_debug_summary_never_copy_business_errors(self):
        session = self.session()
        session.best_strategy("prospect_research")
        result = {"data": {"firms": [{"research_errors": ["private@firm.example bad source"]}]},
                  "tests": {"passed": True}, "errors": [{"error": "firm.example failed"}],
                  "budget": {"counts": {"queries": 1, "pages": 3, "business_name": "Private Firm"}}}
        session.finish(result, "success", "focused", "private@firm.example insight", 1)
        memory = session.load_memory()
        self.assertEqual(memory["refined_prompts"]["prospect_research"]["version"], 2)
        summary = memory["learnings"][-1]["validation_summary"]
        self.assertEqual(summary["record_debug_event_count"], 1)
        self.assertTrue(summary["self_tests_passed"])
        self.assertEqual(summary["operation_counts"], {"queries": 1, "pages": 3})
        self.assertNotIn("firm.example", json.dumps(memory))

    def test_threaded_finishes_do_not_lose_lifetime_counts(self):
        errors = []

        def finish(number):
            try:
                self.finish(f"thread_{number}", "success")
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=finish, args=(number,)) for number in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.session().load_memory()["stats"]["successful_runs"], 8)

    def test_execution_lock_serializes_same_run_and_keeps_memory_lock_independent(self):
        events = []
        errors = []

        def execute(number):
            try:
                session = self.session("shared_execution")
                with session.execution_lock():
                    events.append(("start", number))
                    session.load_memory()
                    session.checkpoint({"worker": number})
                    time.sleep(0.02)
                    events.append(("end", number))
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=execute, args=(number,)) for number in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual([event[0] for event in events], ["start", "end", "start", "end"])
        self.assertEqual(events[0][1], events[1][1])


class LLMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load shared .env once, then every test overrides values without exposing them.
        from shared import config  # noqa: F401

    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_import_is_offline_and_live_readiness_requires_nonplaceholder_key(self):
        with patch.dict(sys.modules, {"crewai": None}):
            importlib.reload(llm)
            self.assertEqual(llm.llm_settings().model, "openai/gpt-4o-mini")
            for key in ("", "your-api-key", "<OPENAI_API_KEY>", "changeme"):
                os.environ["OPENAI_API_KEY"] = key
                with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                    llm.validate_llm_readiness()

    def test_lazy_factory_clamps_limits_disables_hidden_retries(self):
        constructor = Mock(return_value=object())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-key"}), patch.dict(sys.modules, {"crewai": SimpleNamespace(LLM=constructor)}):
            llm.create_crewai_llm(max_tokens=1000, timeout=1.5)
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs["model"], "openai/gpt-4o-mini")
        self.assertEqual(kwargs["max_tokens"], 1000)
        self.assertEqual(kwargs["timeout"], 1.5)
        self.assertEqual(kwargs["max_retries"], 0)
        self.assertEqual(kwargs["temperature"], 0)

    def test_anthropic_config_requires_actual_explicit_model(self):
        os.environ["PROSPECT_RESEARCH_AGENT_LLM_PROVIDER"] = "anthropic"
        with self.assertRaises(ValueError):
            llm.llm_settings()

        os.environ["ANTHROPIC_MODEL"] = "claude-sonnet-4-20250514"
        self.assertEqual(llm.llm_settings().model, "anthropic/claude-sonnet-4-20250514")
        os.environ["PROSPECT_RESEARCH_AGENT_LLM_MODEL"] = "Codex-sonnet-4-20250514"
        with self.assertRaises(ValueError):
            llm.llm_settings()
        os.environ["PROSPECT_RESEARCH_AGENT_LLM_MODEL"] = "openai/gpt-4o-mini"
        with self.assertRaises(ValueError):
            llm.llm_settings()

    def test_dedicated_provider_key_reaches_sdk_without_shared_key(self):
        for provider, model in (("openai", "gpt-4o-mini"), ("anthropic", "claude-sonnet-4-20250514")):
            with self.subTest(provider=provider):
                constructor = Mock(return_value=object())
                key_name = f"{provider.upper()}_API_KEY"
                environment = {
                    "PROSPECT_RESEARCH_AGENT_LLM_PROVIDER": provider,
                    "PROSPECT_RESEARCH_AGENT_LLM_MODEL": model,
                    key_name: "fixture-shared",
                    f"PROSPECT_RESEARCH_AGENT_{key_name}": "fixture-dedicated",
                }
                with patch.dict(os.environ, environment), patch.dict(sys.modules, {"crewai": SimpleNamespace(LLM=constructor)}):
                    llm.create_crewai_llm()
                self.assertEqual(constructor.call_args.kwargs["api_key"], "fixture-dedicated")

    def test_blank_dedicated_key_cannot_fall_back_to_shared_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-shared", "PROSPECT_RESEARCH_AGENT_OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "PROSPECT_RESEARCH_AGENT_OPENAI_API_KEY"):
                llm.validate_llm_readiness()

    def test_explicit_shared_model_is_preserved(self):
        os.environ["DEFAULT_LLM_MODEL"] = "gpt-4o"
        self.assertEqual(llm.llm_settings().model, "openai/gpt-4o")

    def test_nonfinite_and_unbounded_llm_settings_reject_early(self):
        for name, value in (("LLM_TIMEOUT_SECONDS", "inf"), ("LLM_MAX_TOKENS", "4001"),
                            ("LLM_MAX_INPUT_TOKENS", "20001"), ("LLM_MAX_TOKENS", "1.5")):
            with patch.dict(os.environ, {f"PROSPECT_RESEARCH_AGENT_{name}": value}):
                with self.assertRaises(ValueError):
                    llm.llm_settings()


class RecoveryTests(unittest.TestCase):
    def test_recovery_changes_strategy_and_preserves_redacted_chain(self):
        attempts = []

        def run(strategy, attempt, error):
            attempts.append((strategy, attempt, error))
            if attempt < 3:
                raise ValueError("api_key=fixture-sensitive token=credential")
            return {"validated": True}

        result = run_recovery(run)
        self.assertEqual([row[0] for row in attempts], ["standard", "focused", "minimal_evidence"])
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(len(result["errors"]), 2)
        self.assertNotIn("fixture-sensitive", json.dumps(result))
        self.assertEqual(attempts[1][2]["error_type"], "ValueError")

    def test_exhaustion_is_structured_and_limits_are_not_retried(self):
        failed = run_recovery(Mock(side_effect=RuntimeError("invalid output")))
        self.assertEqual(failed["status"], "failure")
        self.assertEqual(len(failed["errors"]), 3)
        stop = Mock(side_effect=RunCancelled("cancelled"))
        with self.assertRaises(RunCancelled):
            run_recovery(stop)
        self.assertEqual(stop.call_count, 1)

    def test_redaction_preserves_schema_tokens_and_removes_credentials(self):
        payload = {"max_output_tokens": 1500, "refresh_token": "sensitive",
                   "url": "https://search.example/?api_key=sensitive&q=firm"}
        redacted = redact(payload)
        self.assertEqual(redacted["max_output_tokens"], 1500)
        self.assertEqual(redacted["refresh_token"], "[REDACTED]")
        self.assertNotIn("sensitive", redacted["url"])


if __name__ == "__main__":
    unittest.main()
