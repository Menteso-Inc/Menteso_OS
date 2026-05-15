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
| **SEO Posting Agent** | Daily SEO Publisher | Researches patent-law blog topics, generates SEO articles with OpenAI, and publishes WordPress drafts or posts for PatentZoom. |

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

PatentZoom setup guide:
- [PatentZoom SEO Posting Agent README](/C:/Users/New/Desktop/Menteso_OS/agents/patentzoom_seo_agent/README.md)

## PatentZoom AI SEO Dashboard

The repo now also includes a dedicated internal PatentZoom SEO operations platform:

- [Next.js dashboard](C:/Users/New/Desktop/Menteso_OS/apps/patentzoom-dashboard)
- [FastAPI control API](C:/Users/New/Desktop/Menteso_OS/services/seo-control-api)
- [BullMQ worker service](C:/Users/New/Desktop/Menteso_OS/services/seo-worker)
- [Shared SEO types](C:/Users/New/Desktop/Menteso_OS/packages/seo-types)

### What It Covers

- keyword discovery and editorial planning
- AI article generation
- WordPress publishing
- indexing requests
- automation/job visibility
- Search Console and analytics placeholders for phased expansion

### Local Run Order

```bash
# Python control API
pip install -r services/seo-control-api/requirements.txt
uvicorn app.main:app --app-dir services/seo-control-api --host 127.0.0.1 --port 8100

# Node workspace install
npm install

# Build shared packages and worker runtime dependencies
npm run seo-agent:build
npm run worker:build

# Start worker
npm --workspace @patentzoom/seo-worker run start

# Start dashboard
npm run dashboard:dev
```

Open:

- dashboard: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- control API: [http://127.0.0.1:8100/health](http://127.0.0.1:8100/health)

### Notes

- The new platform is internal and single-tenant for PatentZoom.
- The legacy `server.py` dashboard remains in the repo for current PCT tooling while the new UI becomes the main SEO workspace.
- Build the existing PatentZoom SEO agent before starting the worker, because the worker reuses its compiled TypeScript publishing pipeline.
