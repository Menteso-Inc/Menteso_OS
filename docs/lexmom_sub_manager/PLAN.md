# Lexmom Sub Manager Architecture and Rollout Draft

Status: First research specialist and thin manager connector approved and implemented locally; later stages remain proposed. Updated 7 October 2026, Asia/Calcutta.

The manager will translate an agreed business outcome into bounded work for specialist agents, maintain the prospect's next action, and report customer and revenue outcomes. Build a repeatable first sales motion before expanding channels. Operational autonomy grows as behavior and economics are demonstrated.

## Manager authority

The founder sets product truth, market, price, budget, permitted channels, and commercial limits. The manager prioritizes work inside those limits, delegates to existing approved specialists, monitors results, and surfaces decisions requiring the founder.

Its recurring output should answer: which firms are qualified, which conversations need action, which demos happened, which firms experienced value or paid, what the work cost, and what should change next. Research and draft work can run independently. External action eligibility is enforced by deterministic policy checks.

Lexmom is the root business objective. The founder's clarified model is bootstrapped and AI native: routine growth work executes automatically within approved operating rules, without human review of each message or ad action. Customers can request human-led demos or video calls. Sample review validates the system before enabling a channel; it must not become a permanent manual queue. Product incidents and actions outside configured authority require an exception owner, to be defined during requirements discovery.

The founder's latest target includes solo, small, and mid-size firms in India, the United States, and other countries. Country is configurable, and numeric size boundaries and buyer role are campaign inputs. Keep country and product tags through research, personalization, and reporting; evaluate channel requirements for each enabled market during integration research.

This plan uses Lexmom Sub Manager as the intended display name. The existing `agents/lexmom_marketing_agent` module remains an inactive placeholder. Decide its eventual module migration and compatibility during implementation; do not create duplicate registered managers.

Guardian Review: The business objective includes activation and retention, so the manager cannot measure success solely through collected leads or sent messages. Future capabilities below are boundaries for later agents, not agents already built.

## Proposed specialist responsibilities

The proposed first build is **Prospect Research and Qualification**, defined in [the first-specialist build proposal](FIRST_AGENT_PLAN.md). It produces sourced firm/contact records and a handoff for later outreach. A thin manager connector can route this one specialist; broader manager reasoning and later specialists remain separate build stages.

| Specialist | Input | Output | Tools and first failure behavior |
| --- | --- | --- | --- |
| Growth Diagnostic | Product facts, funnel/cohort data, customer feedback | A sourced bottleneck hypothesis and one experiment with a decision rule | Read-only analytics/CRM/product access; flag insufficient data rather than invent rates |
| Prospect Research | Approved customer profile and source policy | Qualified firm/contact records with evidence and uncertainties | Approved web/search/CRM sources; quarantine unverified contacts |
| Outreach | Eligible lead, approved offer, evidence, campaign limits | A validated personalized message, automatic send receipt when enabled, and intended next action | Product knowledge and email tools; withhold unsupported claims or ineligible actions |
| Sales Conversation | New inbound message, thread history, product facts, lead state | Reply classification, grounded response, next action or escalation | Dedicated mailbox and CRM; escalate uncertain pricing, commitments, or requests outside product knowledge |
| Demo and Appointment | Qualified interest, buyer problem, approved assets, availability | A relevant demo link/brief and confirmed appointment record when applicable | Reviewed demo assets and booking/calendar; avoid promising an unconfirmed time |
| Activation and Customer Success | Trial/signup events, use case, onboarding progress | First-value support and a recorded outcome or owned product issue | Limited product-event/support access; escalate blocked setup rather than repeatedly sending reminders |
| Voice Sales | Eligible scheduled call, approved script, conversation context | Call outcome, requested handoff, and follow-up record | Later telephony/voice provider; stop on a decline and hand off unsupported requests |

The manager initially performs prioritization and experiment reporting as tasks. Routine deduplication, scheduling, budgeting, and arithmetic remain deterministic utilities. Content, ads, referrals, and partnerships can become additional specialists only when a specific workflow merits them.

Outreach and paid ads are separate acquisition branches. The Outreach Agent consumes qualified firm/contact records. An Ads Runner consumes a verified product offer, audience hypothesis, creative, landing page, conversion events, account access, and spending rules. Market research can inform both; researched email contacts are not automatically an advertising audience or an authorized upload list. Both branches feed the same signup, first-value, payment, and retention measurement.

## Workflow and state

```text
Founder goals and approved product facts
                 |
         Lexmom Sub Manager
                 |
       Diagnose and choose a pilot
                 |
    Research -> qualify -> personalize
                 |
    Eligibility and execution checks
                 |
         Contact -> handle replies
                 |
     Signup or requested demo -> first value
                 |
           Paid -> retained
                 |
      Cohort results -> next experiment
```

Keep Launch and Manage tagged throughout this flow. A referral, inbound enquiry, previous signup, and newly researched firm enter with different contact histories; they must not share an assumed permission or identical sequence.

Each prospect should carry its source, qualification, product, owner, communication history, suppression status, and next action. Commercial stage and contact eligibility are separate fields: an otherwise qualified firm can still be ineligible for a particular channel.

Read the latest state immediately before execution. A reply, decline, opt-out, complaint, booking, cancellation, purchase, or global pause can invalidate an already queued follow-up. After a positive reply, transition to the conversation workflow instead of continuing a generic sequence. An autoresponder does not count as interest. A booked demo does not count as attended. Payment requires authoritative billing evidence.

A worker that times out after sending must reconcile provider records before retrying. Preserve a unique action key and provider receipt for every send or booking. Provider acceptance, delivery, and business success are separate outcomes. For partial failures, resume from the last validated checkpoint. Cancelled jobs stop at a safe boundary and preserve completed-action receipts.

Guardian Review: Reply events and outbound jobs can race. Rechecking suppression and ownership at execution, plus action deduplication and receipt reconciliation, prevents stale follow-ups and duplicate sends. Unknown outcomes remain unresolved until reconciled.

## Python architecture

Follow the repository's Python, CrewAI, LangChain, and Pydantic requirements for new agent code. The current project does not yet install CrewAI/LangChain; the first implementation must introduce and verify compatible dependencies without rewriting unrelated agents.

Use CrewAI for bounded specialist tasks. [CrewAI Flows](https://docs.crewai.com/en/concepts/flows) is a candidate for the manager's structured routing and state transitions. Durable storage, delivery reconciliation, and policy enforcement remain explicit application responsibilities; orchestration alone does not establish production reliability. LangChain should serve reusable tools/chains where useful rather than adding a second competing orchestrator.

Reuse Menteso OS registration and dashboard conventions. Introduce generic reusable integrations under `shared/`; keep Lexmom product rules in its own modules. Extract generic Gmail/CRM utilities only with regression coverage for the accounting service. Do not import accounting billing behavior into the sales workflow.

Use a durable sales store and worker queue selected for the approved runtime and budget. The existing JSON snapshot store can support dashboard summaries but cannot alone provide transactional coordination between concurrent communication jobs. Database and queue selection remains open.

Pydantic contracts should include:

- **ProductBrief:** product, verified capabilities, price, claim/evidence references, prohibited promises, and version.
- **Lead:** firm/contact identifiers, source and timestamp, buyer fit, observed problem, verification state, contact basis, and suppression state.
- **Campaign:** product/segment, offer and asset versions, channels, limits, permitted actions, and decision rule.
- **Action:** unique key, lead/campaign, expected state version, actor, content/asset references, authorization basis, and provider receipt.
- **Outcome:** event source, stage, timestamp, cohort, cost, confidence, and next action.

Store business state separately from each agent's learning memory. Each run loads relevant private learning, chooses a versioned strategy, executes, self-tests, and records an outcome. Do not treat a single positive reply as proof of a winning strategy. Compare outcomes by product and cohort, and retain the experiment decision rule.

Error recovery distinguishes transient rate limits/timeouts from invalid input, expired access, missing credit, and permanent errors. Permit up to three meaningfully adjusted retries for retryable work, with provider-aware delays and an overall deadline. Non-retryable failures and exhausted retries return structured failures with redacted error history. Uncertain external writes enter reconciliation rather than this retry loop.

Runtime modification may change prompts, permitted tool preference, and bounded parameters. It cannot rewrite source code or independently broaden credentials, commercial authority, budgets, or contact policy. Flag an agent for review when its success rate falls below 50% over at least ten evaluated runs, consistent with the project rules.

Guardian Review: Shared business context does not require shared learning memory. Separate private memories preserve the project rule, while structured CRM records preserve handoffs. Costs and transitions are calculated in code rather than inferred from model prose.

## Stage by stage rollout

| Stage | Deliverable | Condition for advancing |
| --- | --- | --- |
| 0 Requirements and evidence | Chosen offer/segment, funnel baseline, product knowledge, budget, credential inventory, and approved pilot plan | Founder resolves the first-pilot decisions; the chosen product/demo route works |
| 1 Research and drafts | Manager plus the first approved research/outreach responsibilities; lead evidence, message drafts, and experiment report | A reviewed sample demonstrates buyer fit, accurate claims, sensible personalization, and visible cost |
| 2 Limited email pilot | Dedicated sender, durable action tracking, reply capture, suppression, and small policy-approved batches | Internal tests and replay/race tests pass; observed delivery and qualified conversations justify continuation |
| 3 Demos and first value | Reply workflow, booking, demo assets, onboarding events, and payment/retention attribution | Demo and activation events are verifiable; recurring founder intervention is understood and reduced |
| 4 Calling and additional channels | One newly selected channel at a time, with its provider and operational limits | A specific buyer/channel hypothesis, regional eligibility, accurate identity, handoff, and cost controls are established |
| 5 Expand proven work | Increased volume, validated experiments, reliable customer-success handoffs, and operating reports | Qualified outcomes, retained value, cost, and quality remain within agreed bounds |

Stages advance on evidence, not calendar promises. Stage 1 does not depend on building the voice stack or enabling advertising. Paid ad spend and email volume do not grow automatically because the system has unused capacity.

For an initial 90-day discussion, use this sequence: establish measurement and customer evidence, run one controlled sales pilot, then improve demo/activation and test the next channel. Numeric targets, sample sizes, time windows, and spending allocations await the founder's baseline and budget.

## Production verification

For each newly approved agent, first run it standalone with synthetic data. Validate Pydantic contracts, evidence/claim checks, private memory updates, recovery behavior, and redacted logs. Then test provider identities and internal-recipient behavior before enabling its approved live scope.

Required workflow tests include duplicate job/webhook delivery, restart after a partial operation, timeout after provider acceptance, opt-out racing a scheduled send, reply during a sequence, expired authorization, LLM/provider outage, budget exhaustion, pause/cancel, and incorrect mailbox/workspace selection. Use sandbox demo records, not confidential legal matter data.

Monitor provider delivery and failures, queue health, state freshness, spend, qualified replies, held demos, activation, payment, and retained cohorts. Provide global and agent-specific pause controls. Each deployment changes only the target service, preserves current state, and has an explicit backup and rollback. Target runtime, alert destination, availability objective, and operating owner remain requirements decisions.

Guardian Review: The design avoids launching all specialists at once. The first useful output is a reviewed lead-and-message sample with a measurable experiment. Production gates apply to the enabled stage, and later channels remain future work until their prerequisites are resolved.
