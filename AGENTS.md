# Menteso — Multi-Agent Virtual Office

## Project Overview

os_agents is a multi-agent system where AI agents function as virtual office employees. Each agent has a specific role, can work independently or delegate to sub-agents, and performs real automated work. Agents are general-purpose — not tied to any single Menteso sub-company.

Agents are built one at a time. No agent exists until explicitly requested and built.

### Core Principle — Every Agent is Autonomous

Every agent must be capable of:
- **Self-learning** — learns from past runs, stores insights, and improves over time
- **Self-debugging** — catches its own errors, diagnoses root causes, and retries with fixes
- **Self-testing** — validates its own output before returning results
- **Self-modifying** — adapts its approach, prompts, and tool usage based on what works

## Tech Stack

- **Language**: Python only
- **Agent Framework**: CrewAI for agent orchestration, LangChain for tools and chains
- **LLM Providers**: OpenAI, Anthropic (configured per agent)
- **Environment**: All secrets in `.env` — no exceptions
- **Validation**: Pydantic for input/output schemas

## Project Structure

```
os_agents/
  .env                        # all API keys (never committed)
  .env.example                # template with placeholders (safe to commit)
  .gitignore
  requirements.txt
  AGENTS.md
  main.py                     # entry point / orchestrator
  agents/                     # each agent gets its own folder
    __init__.py
    {agent_name}/
      __init__.py
      agent.py                # agent definition (role, goal, backstory)
      tools.py                # agent-specific tools
      tasks.py                # tasks the agent can perform
      tests.py                # self-test definitions (validation rules)
      memory.json             # agent's learning memory (auto-managed)
  shared/                     # shared utilities across all agents
    __init__.py
    llm.py                    # LLM provider setup and model config
    config.py                 # global config (loads .env, defaults)
    utils.py                  # common helpers
    memory.py                 # memory system for agent learning
    self_test.py              # self-testing framework
    self_debug.py             # self-debugging framework
  logs/                       # run logs for learning (gitignored)
    {agent_name}/
      runs.jsonl              # structured log of every run
```

- Each agent lives in its own folder under `agents/`
- Shared code goes in `shared/` — never duplicate logic across agents
- `main.py` is the entry point that wires agents together
- `logs/` stores run history that agents use for self-learning (gitignored)

## Security Rules

- **Every secret lives in `.env`** — API keys, tokens, IDs. No exceptions.
- **Never hardcode credentials** — not even temporarily, not even in comments
- **Never log secret values** — `print(f"Key: {api_key}")` is a security violation
- **Validate on startup** — every agent must check its required env vars exist before running:
  ```python
  api_key = os.getenv("OPENAI_API_KEY")
  if not api_key:
      raise ValueError("OPENAI_API_KEY is not set")
  ```
- **Maintain `.env.example`** — when adding a new env var, add a placeholder to `.env.example` with a comment explaining where to get it
- **`.env` must be in `.gitignore`** — verify before any commit. Never commit secrets.
- **Prefix agent-specific keys** — use `{AGENT_NAME}_` prefix for clarity:
  ```
  EMAIL_AGENT_GMAIL_TOKEN=
  RESEARCH_AGENT_SERP_KEY=
  ```

## Adding a New Agent — Workflow

Follow this exact order every time a new agent is requested:

1. **Understand** — What is this agent's role? What specific work does it do?
2. **Research** — Identify required APIs, services, and libraries. Check docs and auth requirements.
3. **Clarify** — Ask targeted questions before writing code:
   - What data/services does this agent need access to?
   - What output should it produce?
   - Should it run on a schedule, on-demand, or event-driven?
   - Does it need to talk to other agents?
   - What does "success" look like?
4. **Plan** — Describe the agent in plain English. Get approval before coding.
5. **Build** — Create the agent folder and files:
   - `agents/{name}/__init__.py`
   - `agents/{name}/agent.py` — define role, goal, backstory + memory loading
   - `agents/{name}/tools.py` — custom tools the agent uses
   - `agents/{name}/tasks.py` — tasks the agent performs
   - `agents/{name}/tests.py` — self-test validation rules
   - `agents/{name}/memory.json` — empty initial memory (`{"agent": "name", "learnings": [], "refined_prompts": {}, "stats": {"total_runs": 0, "success_rate": 0.0}}`)
6. **Environment** — Add required env vars to `.env` and `.env.example`
7. **Test** — Run the agent standalone and verify it produces correct output
8. **Integrate** — Register the agent in `main.py` if it needs to work with others
9. **Verify** — Confirm end-to-end: agent runs, produces expected output, handles errors

## Agent Structure — How to Define an Agent

Each agent is defined with CrewAI's Agent class and wired into the autonomy systems:

```python
# agents/{name}/agent.py
from crewai import Agent
from .tools import custom_tool_1, custom_tool_2
from .tests import tests
from shared.memory import load_memory, save_learning
from shared.self_debug import run_with_self_debug

# Load past learnings
memory = load_memory("agent_name")

agent = Agent(
    role="The agent's job title",
    goal="What the agent is trying to achieve",
    backstory=(
        "Context about who this agent is and why it exists. "
        f"Past learnings: {memory.get('refined_prompts', {})}"
    ),
    tools=[custom_tool_1, custom_tool_2],
    verbose=True,
    llm="gpt-4o",  # or per-agent model override
)
```

Each agent's tasks are defined separately:

```python
# agents/{name}/tasks.py
from crewai import Task
from .agent import agent

task = Task(
    description="Detailed description of what to do",
    expected_output="What the result should look like",
    agent=agent,
)
```

Every agent must also have self-tests:

```python
# agents/{name}/tests.py
from shared.self_test import SelfTest

tests = SelfTest(
    agent_name="agent_name",
    validations=[
        {
            "name": "output_not_empty",
            "check": lambda r: r is not None and len(str(r)) > 0,
            "message": "Agent returned empty output",
        },
        # Add agent-specific validations here
    ],
)
```

## Agent Communication

- **Crews**: Group agents that work together into a CrewAI `Crew`
- **Sequential**: Agents execute tasks in order, each receiving the previous agent's output
- **Hierarchical**: A manager agent delegates tasks to specialist agents
- **Delegation**: An agent can delegate sub-tasks to other agents when `allow_delegation=True`
- **Context sharing**: Tasks can reference other tasks' output via the `context` parameter

```python
from crewai import Crew, Process

crew = Crew(
    agents=[agent_1, agent_2],
    tasks=[task_1, task_2],
    process=Process.sequential,  # or Process.hierarchical
    verbose=True,
)

result = crew.kickoff()
```

## Self-Learning

Every agent maintains a `memory.json` file in its folder. This file is auto-managed — agents write to it after every run.

**What gets stored:**
- Successful strategies and approaches that worked
- Failed attempts and why they failed
- Refined prompts that produced better output
- Edge cases encountered and how they were handled
- Performance metrics (execution time, token usage, success rate)

**How it works:**
1. Before a run, the agent loads its memory and includes relevant past learnings in its context
2. After a run, the agent evaluates the result and writes a learning entry
3. Over time, the agent's prompt context is enriched with proven strategies

```python
# shared/memory.py — provides read/write for agent memory
# Each agent's memory.json structure:
{
    "agent": "agent_name",
    "learnings": [
        {
            "timestamp": "2026-04-10T12:00:00Z",
            "task": "what was attempted",
            "outcome": "success | failure",
            "insight": "what was learned",
            "strategy": "what to do differently or repeat"
        }
    ],
    "refined_prompts": {
        "task_type": "improved prompt text based on experience"
    },
    "stats": {
        "total_runs": 0,
        "success_rate": 0.0,
        "avg_execution_time": 0.0
    }
}
```

**Rules:**
- Memory is per-agent, never shared (agents learn independently)
- Cap memory at 100 entries — oldest entries get pruned when full
- Agents must reference memory before every run, not just store it

## Self-Debugging

Every agent must handle its own errors before escalating. The self-debug loop:

1. **Catch** — wrap the core task execution in a try/except
2. **Diagnose** — use the LLM to analyze the error message and traceback
3. **Fix** — adjust the approach (change tool parameters, retry with different input, switch strategy)
4. **Retry** — attempt the task again with the fix applied
5. **Escalate** — if 3 retries fail, log the full error chain and return a structured failure

```python
# Pattern every agent must follow
import traceback
from shared.self_debug import diagnose_and_retry

async def run_with_self_debug(agent, task, max_retries=3):
    """
    Wraps agent task execution with self-debugging.
    On failure: diagnoses error, adjusts approach, retries.
    After max_retries: logs full error chain and returns failure.
    """
    errors = []
    for attempt in range(max_retries):
        try:
            result = agent.execute_task(task)
            return {"status": "success", "result": result, "attempts": attempt + 1}
        except Exception as e:
            error_info = {
                "attempt": attempt + 1,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            errors.append(error_info)
            # Agent uses LLM to diagnose and adjust
            fix = diagnose_and_retry(agent, task, error_info)
            task = fix.adjusted_task  # modified task with fix applied
    
    # All retries exhausted
    return {"status": "failure", "errors": errors}
```

**Debug diagnosis includes:**
- Is this an API error? (auth, rate limit, bad request)
- Is this a data error? (unexpected format, missing fields)
- Is this a logic error? (wrong tool, bad parameters)
- What specifically should change for the next attempt?

**Rules:**
- Never silently swallow errors — always log them
- Every retry must be meaningfully different from the last attempt
- Store all debug sessions in memory so the agent avoids the same mistakes

## Self-Testing

Every agent validates its own output before returning it. No agent should return unverified results.

**How it works:**
1. Each agent defines validation rules in `tests.py`
2. After producing output, the agent runs its own tests
3. If tests fail, the agent re-executes with adjustments (feeds into self-debug loop)

```python
# agents/{name}/tests.py
from shared.self_test import SelfTest

tests = SelfTest(
    agent_name="agent_name",
    validations=[
        {
            "name": "output_not_empty",
            "check": lambda result: result is not None and len(str(result)) > 0,
            "message": "Agent returned empty output",
        },
        {
            "name": "output_format_valid",
            "check": lambda result: isinstance(result, dict) and "data" in result,
            "message": "Output missing required 'data' field",
        },
        {
            "name": "no_hallucinated_urls",
            "check": lambda result: not contains_fake_urls(result),
            "message": "Output contains URLs that don't resolve",
        },
    ],
)
```

**Every agent must test for:**
- Output is not empty or null
- Output matches the expected format/schema
- Output contains no obvious errors or hallucinations
- Output is relevant to the input task
- Any agent-specific quality checks

**Rules:**
- Tests run automatically after every task execution — not optional
- Failed tests trigger the self-debug loop (retry with adjustments)
- Test results are logged to memory for learning

## Self-Modifying

Agents adapt their behavior based on accumulated learnings. This is NOT agents rewriting their own source code — it's agents dynamically adjusting their runtime behavior.

**What agents can modify at runtime:**
- **Prompts** — refine task descriptions based on what produces better output
- **Tool selection** — prefer tools that have higher success rates for a given task type
- **Parameters** — adjust temperature, max tokens, timeout values based on past performance
- **Strategy** — switch between approaches (e.g., try API A first, fall back to API B)

**How it works:**
1. Agent loads its `memory.json` before each run
2. Checks past success/failure rates for the current task type
3. Selects the strategy and prompt variant with the best track record
4. After the run, updates memory with the outcome

```python
# Pattern for self-modifying behavior
def get_best_strategy(memory, task_type):
    """
    Looks at past runs for this task type.
    Returns the strategy/prompt variant with the highest success rate.
    Falls back to default if no history exists.
    """
    relevant = [l for l in memory["learnings"] if l["task"] == task_type]
    if not relevant:
        return default_strategy(task_type)
    
    successes = [l for l in relevant if l["outcome"] == "success"]
    if successes:
        # Use the most recent successful strategy
        return successes[-1]["strategy"]
    
    # All past attempts failed — try a different approach
    failed_strategies = {l["strategy"] for l in relevant}
    return pick_alternative(task_type, exclude=failed_strategies)
```

**Rules:**
- Source code is never modified at runtime — only prompts, configs, and strategy selection
- Every modification is logged to memory with the reason
- If an agent's success rate drops below 50% over 10 runs, flag it for human review

## LLM Configuration

- Default model is set in `shared/llm.py`
- Each agent can override the model in its `agent.py`
- Supported providers: OpenAI (`gpt-4o`, `gpt-4o-mini`), Anthropic (`Codex-sonnet-4-20250514`)
- Model selection is driven by task complexity and cost:
  - Complex reasoning: `gpt-4o` or `Codex-sonnet-4-20250514`
  - Simple/fast tasks: `gpt-4o-mini`

## Testing & Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run a specific agent standalone (for testing)
python -m agents.{agent_name}.agent

# Run an agent's self-tests only
python -m agents.{agent_name}.tests

# Run the full orchestrator
python main.py
```

- Always test an agent standalone before integrating it with others
- Check output quality, error handling, and env var validation
- Use `verbose=True` during development to see agent reasoning
- Verify self-tests pass before considering an agent "done"
- Check `memory.json` after runs to confirm learning entries are being written

## Agent Execution Flow — Full Lifecycle

Every agent run follows this lifecycle:

```
1. Load memory.json → inject past learnings into agent context
2. Select best strategy for this task type (self-modify)
3. Execute the task
4. Run self-tests on the output
   ├─ PASS → log success to memory, return result
   └─ FAIL → enter self-debug loop
              ├─ Diagnose error with LLM
              ├─ Adjust approach
              ├─ Retry (up to 3 times)
              ├─ PASS → log recovery to memory, return result
              └─ ALL RETRIES FAIL → log failure, return structured error
5. Update memory.json with learnings from this run
6. Update stats (success rate, execution time)
```

## When Something Fails

Agents handle most failures themselves via self-debug. Human intervention needed when:

1. **Agent self-debug exhausted** — 3 retries failed, check the logged error chain
2. **Success rate below 50%** — agent flagged for review, check its `memory.json`
3. **Environment issue** — missing env var, expired API key, service outage
4. Most common root causes:
   - **Missing env var** — key not set in `.env`
   - **Wrong model name** — typo in LLM model string
   - **API auth failure** — expired key, wrong format, rate limit hit
   - **Tool error** — tool function raised an exception
5. Fix the issue, clear the bad learnings from memory if needed, test standalone, re-integrate
