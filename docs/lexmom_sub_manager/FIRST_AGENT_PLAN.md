# First Specialist: Prospect Research and Qualification

Status: First-specialist scope approved and implemented locally. Live provider configuration and a real research pilot remain pending. Updated 7 October 2026, Asia/Calcutta.

This is the first specialist under **Lexmom Sub Manager**. Its job is to find suitable firms, research relevant business contacts, and return evidence-backed records that a later Outreach Agent can use. The founder approved starting this scope on 7 October. The research implementation and manager connector now exist; outreach, ads, and subsequent company operations remain future work. See the [agent's setup and run guide](../../agents/prospect_research_agent/README.md).

## Business scope

The founder's latest target is solo, small, and mid-size firms in India, the United States, and other countries. Country is a configurable field, not a fixed US restriction. Start with a Lexmom Manage campaign profile while Launch is being restored. A later Launch profile can use the same research machinery with its own buyer and qualification rules.

The proposed reusable package is `agents/prospect_research_agent/`; Lexmom-specific product facts and campaign settings are inputs. This follows the project principle that agent roles can serve different Menteso businesses.

The first output is up to 25 qualified firms per pilot run, with discovered contacts where evidence supports them. Missing contacts or insufficient qualification evidence must remain visible. A run that finds fewer suitable firms returns the real count and reasons; it must not invent rows to meet the target.

Guardian Review: Research fit, mailbox verification, buying intent, and outreach eligibility are separate concepts. Neither a search result nor an email verification establishes a firm's need for Lexmom or authority to contact it.

## What the specialist does

1. Load its learning memory and a validated campaign profile.
2. Discover firm websites through an authorized search provider, or research a supplied list of firm domains.
3. Read bounded public office, practice, team, and contact pages; record the evidence supporting each extracted fact.
4. Identify the firm, country/office, practice areas, size evidence, and relevant owner, partner, administrator, or operations contact when published.
5. Apply explicit campaign qualification rules and explain the result. Product relevance is a hypothesis grounded in the approved product brief, not a diagnosis of the firm's internal operations.
6. Deduplicate firms and contacts, retain verification status, validate output, and persist the dataset with a readable summary.
7. Return a handoff to the manager and record the run's validated outcome in private memory.

Routine runs operate autonomously inside the configured source, request, and budget limits. Initial sample review checks the system's accuracy before a live channel is enabled; it does not become per-record human approval.

## Inputs and outputs

| Contract | Required content |
| --- | --- |
| Campaign profile | Business/product, countries, size rules and their units, buyer roles, practice filters if any, verified product facts, approved sources, exclusion list, batch/request limits, and run budget |
| Firm record | Stable identity, canonical domain, name, country/office evidence, practice areas, size evidence or unknown, fit status, fit reasons, and field-level sources |
| Contact record | Firm link, name/role when evidenced, business email or contact route when found, discovery source/time, role evidence, and verification status/time |
| Evidence record | Source URL, retrieval time, short supporting excerpt, observed fact, and evidence state; conflicting or unavailable facts remain unresolved |
| Run result | Qualified/needs-research/excluded counts, data artifact location, country breakdown, source/provider usage, costs available from authoritative usage, errors, and next action |

Numeric size categories remain a campaign decision. Do not infer lawyer count from website appearance or equate all staff with attorneys. If the size rule cannot be established from evidence, record `needs_research` rather than silently qualifying the firm. A high search relevance score is not a qualification score.

Store full prospect datasets as versioned artifacts with a pointer in run history. Existing `shared/db_storage.py` provides dashboard summaries and artifacts; its run-summary writer drops top-level `rows`/`results`, so summaries alone cannot preserve the lead list. Business records remain separate from per-agent learning memory.

## Tools and credentials

First discovery candidate: **SerpAPI plus bounded firm-website retrieval**, because the repository already declares `SERPAPI_API_KEY`. The provider requires an `api_key`; search localization guides discovery, while actual firm geography must come from evidence. Credential reuse requires verified access and account-owner permission. [Official Search API](https://serpapi.com/search-api).

Optional contact enrichment/verification: **Hunter**. It is not required for a useful firm-research result. Preserve the provider's verification date, which may predate the request by up to a month. Catch-all results can have false positives; unknown and pending states must remain unresolved. A 202 response requires bounded polling rather than an immediate success label. [Official Hunter API](https://hunter.io/api-documentation/v2#email-verifier).

The previous workstation inventory found templates and no available live runtime keys. This proposal does not establish current production access. Use shared LLM configuration only after verification. Proposed new agent-specific settings include `PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY`, optional `PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY`, and bounded run settings. These names are not installed variables. Any new credentials belong in excluded `.env` configuration, with documented placeholders in `.env.example`; values must not appear in the dataset, memory, logs, or this plan.

The first version needs no mailbox, ad-account, calendar, or subscription-billing credential. Those belong to later capabilities. Website retrieval must preserve source boundaries, use finite timeouts/size limits, reject private/internal destinations, and treat page text as untrusted data rather than instructions to the agent.

Guardian Review: Optional enrichment failure must preserve useful firm research. Verification age, unknown states, and source evidence prevent a deliverability claim from silently turning into a buying or permission claim.

## Execution and failure behavior

Start on demand for standalone validation, then allow manager-triggered batches. A schedule is a later deployment choice, not installed by this proposal.

Proposed pilot bounds: target up to 25 qualified firms, inspect at most 50 candidate domains, make at most 10 discovery queries, and read at most three pages per candidate. Configure a finite run deadline, LLM-call/token bounds, provider-credit cap, and monetary ceiling before a live run. Stop when the first limit is reached and return checkpointed results and unfinished work.

Use deterministic normalization, filtering, deduplication, counts, and spending calculations. Use the LLM for bounded extraction/relevance work that needs it; cache source retrieval within its configured freshness window. Evidence and strategy versions must accompany results so a later corrected extraction can be distinguished from the original.

Handle invalid input or missing required credentials before external requests. Retry only recoverable errors, with at most three meaningfully adjusted recovery attempts and a run deadline. Authentication errors and exhausted credit return an actionable failure. Unavailable pages, missing contacts, and unresolved verification can yield partial results; they must not be marked as verified. Self-test failures enter recovery before output is accepted. Cancellation preserves completed artifacts and stops further requests.

## Repository build scope

- Create the required `__init__.py`, `agent.py`, `tools.py`, `tasks.py`, `tests.py`, and initial `memory.json` in `agents/prospect_research_agent/` only after approval.
- Introduce compatible CrewAI/LangChain dependencies and shared LLM/adaptive-recovery support where required. Existing helpers repeat an unchanged callable; they do not yet satisfy meaningful recovery and prompt adaptation on their own.
- Reuse shared configuration, Pydantic validation, private memory capped at 100 learnings, and dashboard/storage conventions. Add evaluated-run statistics and the required review flag for success below 50% over at least ten evaluated runs.
- Export the registry's stable agent configuration and standalone `run_agent` interface, then test the specialist independently before connecting it.
- Add an explicit thin Lexmom manager-to-specialist call and a simple status/result handoff. Current `sub_agents` metadata only supplies display snapshots; listing a child does not execute it. Preserve the existing module identity and use Lexmom Sub Manager as its display name until a deliberate compatibility migration is approved.
- Make the parent connector reachable through an explicit research-only launch path: update its `execution_enabled` configuration, pending-setup guards/status view, and inactivity tests as required after the specialist passes standalone checks. The launch must dispatch the research specialist, preserve returned artifacts, and show status/failure. Keep future outreach, ads, and sales capabilities disabled. Merely adding a child label or internal call is not acceptance.

This first stage does not build the full manager, Outreach, Sales Conversation, Ads Runner, or Customer Success agents. A manager connector routes the first specialist; it must not be presented as a complete operating company.

## Acceptance and next stages

The initial build is accepted when schemas validate, qualification evidence is inspectable, replay does not duplicate firms/contacts, unknown facts stay unknown, artifacts survive restart, and every completed run records self-tests and learning. Meaningful tests should cover mixed countries, inconsistent size units, missing/contradictory evidence, duplicate domains, missing contacts, blocked pages, hostile page instructions, provider authentication/limit failures, pending or stale verification, cancellation, and memory statistics. First use synthetic fixtures, then a bounded real research run with configured credentials and budget.

The manager should report data quality and useful researched firms at this stage. Paying-user conversion becomes measurable after Outreach, Sales Conversation, signup/activation, and authoritative billing events are connected.

```text
Lexmom Sub Manager
  |
  +-- Prospect Research -> Qualified firms/contacts -> Outreach
  |                                               -> Sales Conversation
  |                                               -> Signup or requested demo
  |                                               -> First value -> Paid -> Retained
  |
  +-- Offer + audience + landing page + tracking -> Ads Runner
                                                 -> Inbound signup/conversation
                                                 -> First value -> Paid -> Retained
```

Build order after this specialist: Outreach, Sales Conversation and requested-demo routing, then activation/payment/retention support. Introduce the Ads Runner as a separate bounded experiment when the offer, destination, attribution, ad access, and spending rules are ready. Research informs its audience hypothesis; it does not automatically supply an authorized contact-upload audience.

Guardian Review: The design starts with one specialist and a usable handoff. Repository review added an explicit research-only parent activation path because the current setup guards and tests would otherwise keep the connector unreachable. Other checks address lost datasets, compulsory demos, and the different inputs needed by ads and email outreach.

Approval applies to this first-specialist scope and was provided before coding, following [AGENTS.md](../../AGENTS.md). Defaults now use 1 attorney for solo, 2-10 for small, and 11-50 for mid-size; these are configurable campaign conventions. Conservative provider-call reservations and runtime credentials must be configured before a live run. The generated local `.env` contains blank credential placeholders; no live prospect batch has been claimed.
