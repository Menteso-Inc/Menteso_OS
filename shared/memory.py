import json
import os
from datetime import datetime, timezone
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"


def _memory_path(agent_name):
    return AGENTS_DIR / agent_name / "memory.json"


def _default_memory(agent_name):
    return {
        "agent": agent_name,
        "learnings": [],
        "refined_prompts": {},
        "stats": {
            "total_runs": 0,
            "success_rate": 0.0,
            "avg_execution_time": 0.0,
        },
    }


def load_memory(agent_name):
    """Load an agent's memory. Returns default if no memory file exists."""
    path = _memory_path(agent_name)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return _default_memory(agent_name)


def save_learning(agent_name, task, outcome, insight, strategy, execution_time=0.0):
    """Append a learning entry and update stats."""
    memory = load_memory(agent_name)

    memory["learnings"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "outcome": outcome,
        "insight": insight,
        "strategy": strategy,
    })

    # Cap at 100 entries
    if len(memory["learnings"]) > 100:
        memory["learnings"] = memory["learnings"][-100:]

    # Update stats
    total_runs = memory["stats"]["total_runs"] + 1
    successes = sum(1 for l in memory["learnings"] if l["outcome"] == "success")
    count = len(memory["learnings"])
    prev_avg = memory["stats"]["avg_execution_time"]
    prev_total = memory["stats"]["total_runs"]

    memory["stats"]["total_runs"] = total_runs
    memory["stats"]["success_rate"] = round(successes / count, 3) if count else 0.0
    memory["stats"]["avg_execution_time"] = round(
        ((prev_avg * prev_total) + execution_time) / total_runs, 3
    ) if total_runs else 0.0

    path = _memory_path(agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(memory, f, indent=2)

    return memory


def get_best_strategy(agent_name, task_type, default="standard"):
    """Pick the most recent successful strategy for a task type."""
    memory = load_memory(agent_name)
    relevant = [l for l in memory["learnings"] if l["task"] == task_type]

    if not relevant:
        return default

    successes = [l for l in relevant if l["outcome"] == "success"]
    if successes:
        return successes[-1]["strategy"]

    # All past attempts failed — return default so caller can try something new
    return default
