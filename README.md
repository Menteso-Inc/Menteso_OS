# Menteso OS — Multi-Agent Virtual Office

A multi-agent system where AI agents function as virtual office employees. Each agent has a specific role, works autonomously, and performs real automated work — scraping, extracting, processing, and reporting.

Agents are general-purpose and not tied to any single sub-company. They are built one at a time, each capable of self-learning, self-debugging, self-testing, and self-modifying.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  main.py (CLI)                  │
│         python main.py [list|run|dashboard]     │
├─────────────────────────────────────────────────┤
│              server.py (FastAPI)                │
│        Web dashboard + REST API + SSE           │
├──────────────┬──────────────────────────────────┤
│  Agent       │  Shared Framework               │
│  Registry    │  ┌────────────────────────────┐  │
│              │  │ memory.py   — learning      │  │
│  agents/     │  │ self_debug.py — retry loop  │  │
│  ├─ test_    │  │ self_test.py  — validation  │  │
│  │  agent/   │  │ config.py   — env loader    │  │
│  ├─ pct_     │  │ agent_registry.py           │  │
│  │  agent/   │  └────────────────────────────┘  │
│  └─ ...      │                                  │
└──────────────┴──────────────────────────────────┘
```

## Current Agents

| Agent | Role | What It Does |
|-------|------|-------------|
| **Test Agent** | System Reporter | Collects system/environment info. Used to verify the framework works. |
| **PCT Agent** | Patent Data Processor | Processes WIPO PatentScope Excel sheets — scrapes patent pages, downloads RO/101 or 306 PDFs, extracts email/phone contacts. |

## Agent Lifecycle

Every agent run follows this flow:

1. **Load memory** — inject past learnings into context
2. **Select strategy** — pick the best approach from past runs
3. **Execute** — run the task with self-debug (up to 3 retries)
4. **Self-test** — validate output against agent-specific rules
5. **Save learning** — record outcome, insight, and strategy
6. **Update stats** — track success rate and execution time

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url>
cd Menteso_OS
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 3. Run
python main.py                  # List all agents
python main.py run test_agent   # Run an agent via CLI
python main.py dashboard        # Launch web dashboard at http://127.0.0.1:8000
```

## Project Structure

```
os_agents/
├── main.py                    # CLI entry point
├── server.py                  # FastAPI web server + dashboard API
├── requirements.txt
├── .env.example               # Environment template
├── agents/                    # Each agent in its own folder
│   ├── {agent_name}/
│   │   ├── agent.py           # Agent definition + run_agent()
│   │   ├── tools.py           # Agent-specific tools
│   │   ├── tasks.py           # Task definitions
│   │   ├── tests.py           # Self-test validation rules
│   │   └── memory.json        # Auto-managed learning memory
├── shared/                    # Shared framework
│   ├── config.py              # Loads .env, global defaults
│   ├── memory.py              # Read/write agent memory
│   ├── self_debug.py          # Retry loop with error diagnosis
│   ├── self_test.py           # Validation framework
│   └── agent_registry.py      # Auto-discovers agents
├── static/                    # Dashboard frontend (HTML/CSS/JS)
├── uploads/                   # Uploaded files (gitignored)
├── outputs/                   # Agent output files (gitignored)
└── logs/                      # Run logs (gitignored)
```

## Tech Stack

- **Language**: Python
- **Web**: FastAPI + Uvicorn
- **Frontend**: Vanilla HTML/CSS/JS dashboard
- **Agent Framework**: Custom lightweight framework (memory, self-debug, self-test, registry)
- **LLM Providers**: OpenAI, Anthropic (configured per agent)
- **Data**: openpyxl (Excel), PyMuPDF (PDF), requests (HTTP)

## Adding a New Agent

1. Create `agents/{name}/` with `__init__.py`, `agent.py`, `tools.py`, `tasks.py`, `tests.py`, `memory.json`
2. Define `AGENT_CONFIG` dict and `run_agent()` function in `agent.py`
3. Export both from `__init__.py`
4. The agent registry auto-discovers it — no manual registration needed
5. Add any new env vars to `.env` and `.env.example`

See [CLAUDE.md](CLAUDE.md) for the full agent development guide.

## Web Dashboard

Run `python main.py dashboard` to launch the web UI at `http://127.0.0.1:8000`.

Features:
- View all registered agents with status and stats
- Run agents with real-time SSE progress streaming
- Upload files (Excel) for agents that accept input
- Download agent output files
- View agent memory and learning history
