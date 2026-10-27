"""Bounded research execution and durable, private learning state.

Full business records belong in run artifacts. Memory and logs deliberately keep
only controlled learning phrases, counters and artifact pointers.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from shared.memory import _default_memory


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_TASK_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_COUNTERS = ("queries", "candidates", "pages", "llm_calls", "verifications")
_STRATEGIES = ("standard", "focused", "minimal_evidence")
_PROMPTS = {
    "standard": "Extract only facts supported by retrieved public evidence.",
    "focused": "Focus on required fields; omit unsupported optional facts.",
    "minimal_evidence": "Return only directly evidenced facts and explicit unknowns.",
}
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_SECRET_KEY = re.compile(r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization|credentials?)$", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must contain 1-80 ASCII letters, digits, underscores or hyphens")
    return value


def _request_value(request: Any, key: str, default: Any = None) -> Any:
    return request.get(key, default) if isinstance(request, dict) else getattr(request, key, default)


def redact(value: Any) -> Any:
    """Remove credential fields and known environment secret values recursively.

    Business names, domains and contact records remain in artifacts. Their text
    is never passed through to learning records or run logs.
    """
    secrets = [
        item for key, item in os.environ.items()
        if _SECRET_KEY.search(key) and isinstance(item, str) and len(item) >= 4
    ]

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else clean(val)
                    for key, val in item.items()}
        if isinstance(item, (list, tuple, set)):
            return [clean(part) for part in item]
        if isinstance(item, str):
            for secret in sorted(secrets, key=len, reverse=True):
                item = item.replace(secret, "[REDACTED]")
            item = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", item)
            item = re.sub(r"(?i)([?&](?:api[_-]?key|token|key|secret|password)=)[^&#\s]+",
                          r"\1[REDACTED]", item)
            item = re.sub(r"(?i)(\b(?:api[_-]?key|token|secret|password|authorization)\s*[:=]\s*)"
                          r"[^\s,;&#]+", r"\1[REDACTED]", item)
            return item
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, datetime):
            return item.isoformat()
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if hasattr(item, "model_dump"):
            return clean(item.model_dump(mode="json"))
        return clean(str(item))

    return clean(value)


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize before opening anything so invalid payloads preserve old state.
    serialized = json.dumps(redact(payload), ensure_ascii=False, indent=2, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(serialized + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _file_lock(path: Path):
    """Portable finite process lock; closing the file releases it after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Research state lock unavailable") from None
                time.sleep(0.01)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class BudgetExceeded(RuntimeError):
    """A finite run limit was exhausted before a new operation began."""


class RunCancelled(RuntimeError):
    """Cancellation was requested; callers should persist completed work."""


class RunBudget:
    """Reserve bounded operations before requests; costs are estimates, not bills."""

    def __init__(self, request: Any, cancelled: Any = None):
        seconds = float(_request_value(request, "deadline_seconds"))
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("deadline_seconds must be positive and finite")
        self.started_at = time.monotonic()
        self.deadline = self.started_at + seconds
        self.cancelled = cancelled
        self._lock = threading.RLock()
        pages_per_firm = _request_value(request, "max_pages_per_firm")
        if isinstance(pages_per_firm, bool) or not isinstance(pages_per_firm, int) or pages_per_firm < 0:
            raise ValueError("max_pages_per_firm must be a non-negative integer")
        self.limits = {
            "queries": _request_value(request, "max_queries"),
            "candidates": _request_value(request, "max_candidates"),
            # Network requests include robots.txt and up to three redirects per
            # fetch; the source tool separately caps actual content pages.
            "pages": _request_value(request, "max_candidates") * (pages_per_firm + 1) * 4,
            "llm_calls": _request_value(request, "max_llm_calls"),
            "verifications": _request_value(request, "max_verifications"),
        }
        if any(isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
               for limit in self.limits.values()):
            raise ValueError("Operation limits must be non-negative integers")
        self.counts = dict.fromkeys(_COUNTERS, 0)
        ceiling = _request_value(request, "budget_usd")
        if ceiling is not None and (not math.isfinite(float(ceiling)) or float(ceiling) < 0):
            raise ValueError("budget_usd must be finite and non-negative")
        self._ceiling = Decimal(str(ceiling)) if ceiling is not None else None
        self._reserved_cost = Decimal("0")
        costs = _request_value(request, "unit_costs", {}) or {}
        if any(key not in _COUNTERS or not math.isfinite(float(cost)) or float(cost) < 0
               for key, cost in costs.items()):
            raise ValueError("Unit costs must use supported counters and be finite and non-negative")
        self.unit_costs = {key: Decimal(str(cost)) for key, cost in costs.items()}
        self.spend_policy = _request_value(request, "spend_policy", "metered")
        if self.spend_policy == "free_allowance_only":
            self.limits["llm_calls"] = 0
            # SourceTools checks provider free-plan balances before credit operations.
            # Existing cash reservations are not actual charges for free allowances.
            self.unit_costs = dict.fromkeys(_COUNTERS, Decimal("0"))
        self.max_input_tokens = _request_value(request, "max_input_tokens", 10000)
        self.max_output_tokens = _request_value(request, "max_output_tokens", 1500)

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def check(self) -> None:
        signal = self.cancelled
        cancelled = signal() if callable(signal) else signal.is_set() if hasattr(signal, "is_set") else signal
        if cancelled:
            raise RunCancelled("Research run cancelled")
        if self.remaining_seconds() <= 0:
            raise BudgetExceeded("Research run deadline exhausted")

    def consume(self, kind: str, amount: int = 1) -> None:
        with self._lock:
            self.check()
            if kind not in self.counts:
                raise ValueError("Unsupported budget counter")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise ValueError("Reservation amount must be a non-negative integer")
            if self.counts[kind] + amount > self.limits[kind]:
                raise BudgetExceeded(f"Research {kind} limit exhausted")
            reservation = self.unit_costs.get(kind, Decimal("0")) * amount
            if self._ceiling is not None and self._reserved_cost + reservation > self._ceiling:
                raise BudgetExceeded("Research reserved cost ceiling exhausted")
            self.counts[kind] += amount
            self._reserved_cost += reservation

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counts": dict(self.counts), "limits": dict(self.limits),
                "remaining_seconds": round(self.remaining_seconds(), 3),
                "reserved_cost_usd": float(self._reserved_cost),
                "budget_usd": float(self._ceiling) if self._ceiling is not None else None,
                "cost_basis": "configured conservative reservations; actual billed spend is unknown",
                "max_input_tokens": self.max_input_tokens, "max_output_tokens": self.max_output_tokens,
                "spend_policy": self.spend_policy,
            }


class ResearchSession:
    """Durable artifacts plus per-agent learning with no business data in memory."""

    def __init__(self, agent_name: str, run_id: str | None = None,
                 state_dir: str | Path | None = None, memory_dir: str | Path | None = None):
        self.agent_name = _identifier(agent_name, "agent_name")
        self.run_id = _identifier(run_id or uuid.uuid4().hex, "run_id")
        self.state_root = Path(state_dir) if state_dir is not None else PROJECT_ROOT / "runtime-data"
        self.agent_dir = self.state_root.resolve() / self.agent_name
        self.run_dir = self.agent_dir / self.run_id
        self.checkpoint_path = self.run_dir / "checkpoint.json"
        self.artifact_path = self.run_dir / "result.json"
        self.receipt_path = self.run_dir / "completion.json"
        self.memory_path = (Path(memory_dir) if memory_dir is not None else PROJECT_ROOT / "agents").resolve() / self.agent_name / "memory.json"
        self.log_path = ((self.state_root / "logs") if state_dir is not None else PROJECT_ROOT / "logs") / self.agent_name / "runs.jsonl"
        self.task_type = "prospect_research"
        self._selection_reason = "No evaluated history; use default evidence strategy."
        lock_key = str(self.memory_path)
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(lock_key, threading.RLock())
            self._execution_thread_lock = _LOCKS.setdefault(str(self.run_dir / ".execution.lock"), threading.RLock())
        self._process_lock_path = self.agent_dir / (".memory-" + hashlib.sha256(lock_key.encode()).hexdigest()[:16] + ".lock")

    @contextmanager
    def _locked(self):
        """Serialize same-agent writes in threads and processes sharing a state root."""
        with self._lock, _file_lock(self._process_lock_path):
            yield

    @contextmanager
    def execution_lock(self):
        """Prevent competing executions/resumes for one stable run identifier."""
        if not self._execution_thread_lock.acquire(timeout=5):
            raise RuntimeError("Research run is already executing")
        try:
            with _file_lock(self.run_dir / ".execution.lock"):
                yield
        finally:
            self._execution_thread_lock.release()

    def _read_memory(self) -> dict:
        memory = self._read_json(self.memory_path) if self.memory_path.exists() else _default_memory(self.agent_name)
        if memory.get("agent") != self.agent_name or not isinstance(memory.get("learnings"), list):
            raise ValueError("Agent memory schema or identity is invalid")
        memory.setdefault("refined_prompts", {})
        memory.setdefault("adaptations", [])
        stats = memory.setdefault("stats", {})
        if "evaluated_runs" not in stats:
            old_total = int(stats.get("total_runs", 0))
            if old_total > len(memory["learnings"]):
                raise ValueError("Legacy memory requires lifetime statistics migration")
            evaluated = [item for item in memory["learnings"] if item.get("outcome") in {"success", "failure"}]
            stats.update({"evaluated_runs": len(evaluated),
                          "successful_runs": sum(item["outcome"] == "success" for item in evaluated),
                          "failed_runs": sum(item["outcome"] == "failure" for item in evaluated),
                          "recent_evaluated_outcomes": [item["outcome"] for item in evaluated[-10:]],
                          "recent_evaluated_runs": [{"run_id": item.get("run_id"), "outcome": item["outcome"]} for item in evaluated[-10:]],
                          "execution_time_total": float(stats.get("avg_execution_time", 0)) * old_total})
        stats.setdefault("total_runs", 0)
        stats.setdefault("recent_evaluated_runs", [
            {"run_id": item.get("run_id"), "outcome": item["outcome"]}
            for item in memory["learnings"] if item.get("outcome") in {"success", "failure"}
        ][-10:])
        return memory

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("Research state is unreadable or invalid JSON") from None
        if not isinstance(payload, dict):
            raise ValueError("Research state must be a JSON object")
        return payload

    def load_memory(self) -> dict:
        with self._locked():
            return self._read_memory()

    def best_strategy(self, task_type: str, default: str = "standard") -> str:
        if not _TASK_TYPE.fullmatch(task_type) or default not in _STRATEGIES:
            raise ValueError("A controlled task identifier and supported default strategy are required")
        with self._locked():
            memory = self._read_memory()
            relevant = [entry for entry in memory["learnings"] if entry.get("task") == task_type
                        and entry.get("outcome") in {"success", "failure"}]
            successes = [entry for entry in relevant if entry.get("outcome") == "success" and entry.get("strategy") in _STRATEGIES]
            if successes:
                strategy = successes[-1]["strategy"]
                reason = "Reuse most recent strategy with validated success."
            elif relevant:
                failed = {entry.get("strategy") for entry in relevant if entry.get("outcome") == "failure"}
                strategy = next((choice for choice in _STRATEGIES if choice not in failed), "minimal_evidence")
                reason = "Prior evaluated failures require a different evidence strategy."
            else:
                strategy, reason = default, "No evaluated history; use default evidence strategy."
            self.task_type, self._selection_reason = task_type, reason
            previous = memory["refined_prompts"].get(task_type, {})
            if not isinstance(previous, dict):
                previous = {}
            version = int(previous.get("version", 0))
            if previous.get("strategy") != strategy:
                version += 1
                memory["refined_prompts"][task_type] = {
                    "version": version, "strategy": strategy, "reason": reason,
                    "prompt": _PROMPTS[strategy],
                }
                memory["adaptations"] = (memory["adaptations"] + [{
                    "timestamp": _now(), "run_id": self.run_id, "task": task_type,
                    "version": version, "strategy": strategy, "reason": reason,
                }])[-100:]
                _atomic_json(self.memory_path, memory)
            return strategy

    def checkpoint(self, result: dict) -> str:
        if not isinstance(result, dict):
            raise ValueError("Research checkpoint must be a result object")
        with self._locked():
            _atomic_json(self.checkpoint_path, result)
        return str(self.checkpoint_path)

    def read_checkpoint(self) -> dict | None:
        with self._locked():
            return self._read_json(self.checkpoint_path) if self.checkpoint_path.exists() else None

    def finish(self, result: dict, outcome: str, strategy: str, insight: str,
               execution_time: float) -> dict:
        """Persist result and evaluated outcome once; free-form insight stays out of memory."""
        if not isinstance(result, dict) or outcome not in {"success", "failure", "partial", "cancelled", "preflight"}:
            raise ValueError("Result object and supported research outcome are required")
        if strategy not in _STRATEGIES or not math.isfinite(execution_time) or execution_time < 0:
            raise ValueError("Supported strategy and finite execution time are required")
        with self._locked():
            _atomic_json(self.checkpoint_path, result)
            _atomic_json(self.artifact_path, result)
            memory = self._read_memory()
            stats = memory["stats"]
            existing = next((entry for entry in reversed(memory["learnings"]) if entry.get("run_id") == self.run_id), None)
            receipt = self._read_json(self.receipt_path) if self.receipt_path.exists() else None
            previous = receipt or existing
            # A replay of a completed run must not duplicate lifetime counts.
            if previous is None:
                stats["total_runs"] += 1
                stats["execution_time_total"] += execution_time
            elif previous.get("outcome") != outcome:
                stats["execution_time_total"] += execution_time - float(previous.get("execution_time", 0))
            old_outcome = previous.get("outcome") if previous else None
            if previous is None or old_outcome != outcome:
                if old_outcome in {"success", "failure"}:
                    stats["evaluated_runs"] -= 1
                    stats["successful_runs" if old_outcome == "success" else "failed_runs"] -= 1
                if outcome in {"success", "failure"}:
                    stats["evaluated_runs"] += 1
                    stats["successful_runs" if outcome == "success" else "failed_runs"] += 1
                previous_prompt = memory["refined_prompts"].get(self.task_type, {})
                if not isinstance(previous_prompt, dict):
                    previous_prompt = {}
                version = int(previous_prompt.get("version", 0))
                if previous_prompt.get("strategy") != strategy:
                    version += 1
                    reason = "Runtime execution selected an adjusted evidence strategy."
                    memory["refined_prompts"][self.task_type] = {
                        "version": version, "strategy": strategy, "reason": reason, "prompt": _PROMPTS[strategy],
                    }
                    memory["adaptations"] = (memory["adaptations"] + [{
                        "timestamp": _now(), "run_id": self.run_id, "task": self.task_type,
                        "version": version, "strategy": strategy, "reason": reason,
                    }])[-100:]
                report = result.get("tests", {})
                data = result.get("data", {})
                rows = data.get("firms", result.get("rows", [])) if isinstance(data, dict) else []
                run_errors = result.get("errors", [])
                validation_summary = {
                    "self_tests_passed": report.get("passed") if isinstance(report, dict) and isinstance(report.get("passed"), bool) else None,
                    "run_error_count": len(run_errors) if isinstance(run_errors, list) else 0,
                    "record_debug_event_count": sum(len(row.get("research_errors", []))
                        for row in rows if isinstance(row, dict) and isinstance(row.get("research_errors", []), list)) if isinstance(rows, list) else 0,
                }
                budget_summary = result.get("budget", {})
                usage = budget_summary.get("counts", {}) if isinstance(budget_summary, dict) else {}
                validation_summary["operation_counts"] = {
                    kind: count for kind, count in usage.items()
                    if kind in _COUNTERS and isinstance(count, int) and not isinstance(count, bool) and count >= 0
                } if isinstance(usage, dict) else {}
                learning = {
                    "timestamp": _now(), "run_id": self.run_id, "task": self.task_type,
                    "outcome": outcome, "strategy": strategy, "execution_time": execution_time,
                    "insight": "Validated evidence strategy succeeded." if outcome == "success" else
                               "Validation or execution failed; use adjusted evidence strategy." if outcome == "failure" else
                               "Run ended before evaluation; preserve completed evidence for resume.",
                    "strategy_reason": self._selection_reason,
                    "strategy_version": version,
                    "validation_summary": validation_summary,
                }
                memory["learnings"] = [entry for entry in memory["learnings"] if entry.get("run_id") != self.run_id]
                memory["learnings"] = (memory["learnings"] + [learning])[-100:]
                recent_runs = [entry for entry in stats["recent_evaluated_runs"] if entry.get("run_id") != self.run_id]
                if outcome in {"success", "failure"}:
                    recent_runs.append({"run_id": self.run_id, "outcome": outcome})
                stats["recent_evaluated_runs"] = recent_runs[-10:]
                stats["recent_evaluated_outcomes"] = [entry["outcome"] for entry in recent_runs[-10:]]
            recent = stats["recent_evaluated_outcomes"]
            stats["success_rate"] = stats["successful_runs"] / stats["evaluated_runs"] if stats["evaluated_runs"] else 0.0
            stats["rolling_10_success_rate"] = recent.count("success") / len(recent) if recent else None
            stats["avg_execution_time"] = stats["execution_time_total"] / stats["total_runs"] if stats["total_runs"] else 0.0
            stats["review_required"] = len(recent) >= 10 and stats["rolling_10_success_rate"] < 0.5
            _atomic_json(self.memory_path, memory)
            accounted_time = float(previous.get("execution_time", execution_time)) if previous and old_outcome == outcome else execution_time
            summary = {
                "run_id": self.run_id, "agent": self.agent_name, "outcome": outcome,
                "strategy": strategy, "execution_time": accounted_time,
                "artifact_path": str(self.artifact_path), "checkpoint_path": str(self.checkpoint_path),
                "memory_path": str(self.memory_path), "review_required": stats["review_required"],
                "stats": dict(stats), "finished_at": _now(),
            }
            _atomic_json(self.receipt_path, summary)
            if previous is None or old_outcome != outcome:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(redact(summary), allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            return summary


def run_recovery(run_fn: Callable[[str, int, dict | None], Any], max_retries: int = 3) -> dict:
    """Run at most three meaningfully different strategies and expose errors.

    Error text can contain business or provider payloads, so the public error
    chain contains controlled exception types and redacted messages only.
    """
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 1 <= max_retries <= 3:
        raise ValueError("max_retries must be between one and three")
    errors = []
    for attempt, strategy in enumerate(_STRATEGIES[:max_retries], 1):
        try:
            result = run_fn(strategy, attempt, errors[-1] if errors else None)
            return {"status": "success", "result": result, "attempts": attempt,
                    "strategy": strategy, "errors": errors}
        except (BudgetExceeded, RunCancelled):
            raise
        except Exception as error:
            errors.append({"attempt": attempt, "strategy": strategy,
                           "error_type": type(error).__name__, "error": redact(str(error))[:1000]})
    return {"status": "failure", "result": None, "attempts": len(errors), "errors": errors}
