import time
from datetime import datetime, timezone

from shared.memory import load_memory, save_learning, get_best_strategy
from shared.self_debug import run_with_self_debug
from .tools import get_system_info, get_python_info, get_disk_info, get_env_status
from .tests import tests


AGENT_CONFIG = {
    "name": "Test Agent",
    "description": (
        "A test agent that collects system information. "
        "Used to verify the agent framework is working correctly."
    ),
    "role": "System Reporter",
    "goal": "Collect and report system information accurately",
    "status": "active",
    "version": "1.0.0",
    "requires_llm": False,
}


def run_agent(input_data=None, on_step=None):
    """Execute the test agent with full lifecycle: memory -> execute -> test -> learn."""
    STEP_DELAY = 0.4  # seconds between steps for real-time dashboard visibility
    start_time = time.time()
    agent_name = "test_agent"

    # --- Step 1: Load memory ---
    if on_step:
        on_step("Loading agent memory...")
    time.sleep(STEP_DELAY)
    memory = load_memory(agent_name)
    runs = memory["stats"]["total_runs"]
    rate = memory["stats"]["success_rate"]
    if on_step:
        on_step(f"Memory loaded — {runs} past runs, {rate:.0%} success rate")
    time.sleep(STEP_DELAY)

    # --- Step 2: Select strategy ---
    if on_step:
        on_step("Selecting best strategy from past learnings...")
    time.sleep(STEP_DELAY)
    strategy = get_best_strategy(agent_name, "system_report", default="full_collection")
    if on_step:
        on_step(f"Strategy selected: {strategy}")
    time.sleep(STEP_DELAY)

    # --- Step 3: Execute with self-debug ---
    if on_step:
        on_step("Executing task: Collect system information...")
    time.sleep(STEP_DELAY)

    def execute():
        return {
            "system": get_system_info(),
            "python": get_python_info(),
            "disk": get_disk_info(),
            "env_status": get_env_status(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    run_result = run_with_self_debug(execute, max_retries=3, on_step=on_step)

    if run_result["status"] != "success":
        if on_step:
            on_step(f"Agent FAILED after {run_result['attempts']} attempts")
        last_error = run_result["errors"][-1]["error"]
        save_learning(
            agent_name, "system_report", "failure",
            f"Execution failed: {last_error}", "debug_required",
        )
        return {"status": "failure", "errors": run_result["errors"]}

    result = run_result["result"]

    # --- Step 4: Self-test ---
    if on_step:
        on_step("Running self-tests on output...")
    time.sleep(STEP_DELAY)
    test_result = tests.run(result)

    if not test_result["passed"]:
        if on_step:
            on_step(f"Self-tests FAILED: {test_result['failures']}")
        save_learning(
            agent_name, "system_report", "failure",
            f"Tests failed: {[f['name'] for f in test_result['failures']]}", "fix_output",
        )
        return {"status": "test_failure", "data": result, "tests": test_result}

    if on_step:
        on_step(f"All {test_result['total']} self-tests passed!")
    time.sleep(STEP_DELAY)

    # --- Step 5: Save learning ---
    execution_time = time.time() - start_time
    save_learning(
        agent_name, "system_report", "success",
        "Successfully collected system info", strategy, execution_time,
    )
    if on_step:
        on_step(f"Learning saved. Execution time: {execution_time:.2f}s")
    time.sleep(STEP_DELAY)

    return {
        "status": "success",
        "data": result,
        "tests": test_result,
        "attempts": run_result["attempts"],
        "execution_time": round(execution_time, 2),
    }
