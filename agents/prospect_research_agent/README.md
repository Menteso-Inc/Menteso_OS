# Prospect Research and Qualification

The first working specialist under **Lexmom Sub Manager**. It researches solo, small, and mid-size law firms across configurable countries and returns sourced firm/contact records. All agent logic is Python; CrewAI performs bounded extraction, LangChain wraps public research tools, and Pydantic validates contracts.

## Current capability

- Discover firm websites through SerpAPI, or research supplied public firm URLs.
- Read bounded public HTML pages, preserve field-level excerpts and retrieval dates, and deduplicate by canonical host.
- Qualify firms using published identity, location, legal practice and an explicit attorney count or bounded current legal-team roster. Roster counts are labelled separately; unknown or contradictory facts remain `needs_research`.
- Preserve published contacts and buyer-role matches. Name/role/email association is `unconfirmed` unless a supporting excerpt connects them; mailbox verification is separate.
- Optionally verify a published email through Hunter. Catch-all, pending, unknown, and dated verification remain visible. Research never grants outreach eligibility.
- Run automatic output checks, try up to three adjusted strategies, checkpoint work, support cancellation/resume, and update private versioned learning.
- Export the complete JSON dataset and show it through the manager's research dashboard.

The initial size defaults are solo=1 attorney, small=2-10, and mid-size=11-50. These are configurable campaign boundaries, not universal firm classifications. `small_firm_max`, `size_min`, and `size_max` can change them. Country filters accept recognized names or ISO codes; an empty list does not restrict country. The first version expects readable public HTML and explicit evidence. Javascript-only pages or missing size information may require further research.

The current saved profile uses a 50-contact inventory goal, separate from the
qualified-firm target. It counts only unique, sourced, research-ready contacts
with acceptable current email verification. A met goal reuses saved results
without new provider operations. See the [20 October team handoff](../../docs/lexmom_sub_manager/TEAM_HANDOFF_20261020.md)
for the last dated live result, service caps and what remains unfinished.

## Local setup

### Two-product pipeline — 13 October 2026

The saved manager profile now requests `product: "both"`, `extraction_mode: "rules"`,
`spend_policy: "free_allowance_only"`, a zero cash reservation ceiling and zero model
calls. This path requires no model credential: extraction uses explicit title/business
metadata, location/attorney-count syntax, practice labels and published firm-domain
emails. It deliberately retains unknown facts. The optional model path remains
available only under an explicitly metered profile with its existing preflight limits.

`qualification_policy.json` contains the editable product contexts, buyer roles,
search themes and questions. Every firm gets separate Manage/Launch assessments,
a primary product, contact readiness and source-backed personalization briefs.
Public research establishes potential relevance, never expressed interest or sending
permission. Named people and general inboxes produce different handoff variants.
Stale/undated verification, uncertain affiliation and synthetic fixtures remain held.

For readable pending records, resume the original saved profile with its
`resume_run_id` and `refresh_pending: true`. This re-enriches incomplete records
without a new search, carries all provider counters forward and archives the
original checkpoint as `before-enrichment.json`. Already charged candidates do
not consume a second candidate slot; further source requests still consume the
same cumulative page allowance. Blocked records without evidence stay held.

Search queries rotate transactionally across runs, with Manage and Launch themes
interleaved. Only recognized tracking parameters are stripped from source URLs;
unknown queries, credential URLs and non-public destinations remain blocked. Free
SerpAPI/Hunter account status and balances are checked before credit operations.
No automatic upgrades, overages or model inference occur on the free-only path.

`runtime-data/prospect_research_agent/prospects.sqlite3` stores the canonical live
inventory, per-run observations and query reservations. Fixture inventory stays in a
separate namespace. Target/profile and product-policy fingerprints prevent reusing
incompatible assessments. A worse failed refresh does not erase a better observation;
the dashboard recomputes readiness/freshness when viewing saved records. Agent
learning remains in its private memory file, separate from this business database.

The dashboard displays per-product fit/reasons, primary product, readiness and saved
inventory separately from a run's results. Email sending, mailbox synchronization,
demo-form ingestion and continuous scheduling are not enabled by this research
update. Rules extraction may retain more unresolved records than a funded model;
JavaScript-only/blocked sources, incomplete lawyer counts and no-website identity
sources need further enrichment rather than invented qualification.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This workspace has an isolated `.venv` with the tested dependencies installed. New agent requirements pin CrewAI 1.15.23 and LangChain 1.4.3. Use its Python for tests and runs.

Fill credentials privately in the ignored project-root `.env`:

- `PROSPECT_RESEARCH_AGENT_OPENAI_API_KEY` or `PROSPECT_RESEARCH_AGENT_ANTHROPIC_API_KEY` for the selected provider. A declared dedicated variable takes precedence even when blank, so it cannot silently use another agent's credential. Legacy shared provider variables are supported only when the dedicated variable is absent.
- `PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY` for discovery. Shared `SERPAPI_API_KEY` is used only when `PROSPECT_RESEARCH_AGENT_ALLOW_SHARED_SEARCH_KEY=true` explicitly permits it. Supplied seed URLs do not require discovery access.
- Optional `PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY` when email verification is enabled.

Select provider/model and token/time limits using the documented `PROSPECT_RESEARCH_AGENT_LLM_*` settings in `.env.example`. The default is OpenAI/gpt-4o-mini; an Anthropic model must be configured explicitly. Never use a reporting/admin key as a model-workload key.

Before live requests, configure positive conservative per-call reservations for the account's search, LLM, and enabled verification operations using `PROSPECT_RESEARCH_AGENT_QUERY_COST_USD`, `PROSPECT_RESEARCH_AGENT_LLM_CALL_COST_USD`, and `PROSPECT_RESEARCH_AGENT_VERIFICATION_COST_USD`. These must cover the selected model's bounded input/output and provider charges. `PROSPECT_RESEARCH_AGENT_BUDGET_USD` defaults to 1 per run and `PROSPECT_RESEARCH_AGENT_DEADLINE_SECONDS` to 180. Reservations are estimated limits; actual billed spend is not inferred from them. No prices are hardcoded.

## Run

```powershell
# Direct specialist; requires live configuration.
.venv\Scripts\python.exe -m agents.prospect_research_agent.agent

# Existing manager module identity, now displayed as Lexmom Sub Manager.
.venv\Scripts\python.exe main.py run lexmom_marketing_agent

# Start the local authenticated dashboard.
.venv\Scripts\python.exe main.py dashboard
```

For a custom profile, save JSON and pass `--input <path>` to the standalone module. Example live profile:

```json
{
  "mode": "live",
  "product": "manage",
  "countries": ["India", "United States"],
  "target_segments": ["solo", "small", "mid_size"],
  "buyer_roles": ["owner", "partner", "administrator"],
  "size_min": 1,
  "small_firm_max": 10,
  "size_max": 50,
  "target_count": 25,
  "budget_usd": 1
}
```

Every run stops at the first deadline, request, candidate, model-call, or reservation limit. Fewer than 25 qualifying firms produces a visible partial result. Exhausted model/source recovery produces a structured failure; missing configuration fails before provider requests. No run silently substitutes mock data.

Resume with the original profile plus its returned `resume_run_id`. The profile must match; saved counters and reservations carry forward. Run locks prevent concurrent resume writers. Dataset/checkpoint/receipt files live in ignored `runtime-data/prospect_research_agent/<run_id>/`. Per-agent learning stays in `agents/prospect_research_agent/memory.json`; logs store controlled outcomes and artifact pointers.

## Verification

```powershell
.venv\Scripts\python.exe -m agents.prospect_research_agent.tests
.venv\Scripts\python.exe -m unittest discover -s tests -p test_research_runtime.py -v
.venv\Scripts\python.exe -m unittest agents.lexmom_marketing_agent.test_placeholder -v
```

Tests use isolated temporary state, network mocks, explicit synthetic fixtures, and a real CrewAI task with an injected offline model. They cover source security, evidence rejection, mixed countries, attorney/staff distinctions, partial results, bounded calls, cancellation/resume, persistence, private learning, manager dispatch, and authenticated export boundaries. The browser accepts live profiles only; fixture mode is restricted to explicit programmatic/CLI tests.

On 7 October 2026, the specialist and manager were deployed to an isolated AWS runtime and connected to the authenticated public dashboard under **Lexmom Sub Manager**. OpenAI is reused from AWS under user authorization. Hunter and the newly provisioned Dev Team SerpAPI account are dedicated to Lexmom. No paid search plan was purchased. Supplied-site qualification and broad discovery are evaluated separately; directories/news are excluded from official-firm qualification. See [current deployment evidence](../../docs/lexmom_sub_manager/DEPLOYMENT.md) and the [demo guide](../../docs/lexmom_sub_manager/DEMO.md) for verified outcomes and limitations. Outreach, ads, calls, signup/payment handling and customer success remain later stages.

Supported GPT-4o models use `tiktoken` with framing headroom for the input guard. Other models retain a conservative byte-based bound. Public source material is additionally bounded before prompt construction. Each retry and model request remains subject to the same run budget.

## Discovery and repeated research

Search metadata is retained and ranked before candidate limits. Supported public directory profiles can resolve a single explicitly labelled website link; the resolved website still requires source-grounded qualification. Initial research leaves room within the existing three-page cap for targeted team/contact follow-up. `data.candidates` records every retained search candidate's decision and reason.

`research_freshness_days` (default 30, 0 to force refresh) skips recently completed, self-tested live firms under the same targeting profile. Known firms reference the previous run and do not count as newly collected leads. Unresolved or expired firms can be retried. New discovery tests run with `python -m unittest agents.prospect_research_agent.test_discovery`; all provider/HTTP responses are simulated. See docs/lexmom_sub_manager/DISCOVERY_REPAIR.md for scope, limits and pending live acceptance.
