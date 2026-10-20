# Lexmom Sub Manager Requirements Draft

Status: First research stage approved and implemented locally; live credentials and campaign validation remain open. Updated 7 October 2026, Asia/Calcutta.

The Lexmom Sub Manager will coordinate the work needed to acquire, activate, and retain paying Lexmom customers. It will operate within Menteso OS, with specialist agents introduced one at a time as their work is defined and approved. This draft records the founder's requirements and the decisions needed for the first pilot. It does not enable any agent or external action.

Related documents: [Integration inventory](INTEGRATIONS.md), [architecture and rollout plan](PLAN.md), and [first-specialist build proposal](FIRST_AGENT_PLAN.md).

## Founder requirements

The founder reports approximately two years developing Lexmom, unsuccessful advertising, and disappointing results from freelance marketing. The desired system should reduce the work that one founder must personally perform across customer acquisition and sales.

Confirmed requirements:

- Use the name **Lexmom Sub Manager**, replacing the marketing-only concept in the design.
- Support **India, the United States, and other countries**, with country configurable and preserved in each prospect record. The latest clarification supersedes the earlier US-only targeting assumption.
- Target **solo, small, and mid-size firms**. Numeric size boundaries and the initial buyer role remain to be defined in the campaign profile.
- Place specialist agents under this manager and build them stage by stage.
- Find appropriate prospective customers, contact them, manage conversations, arrange or share demos, and follow through toward sales.
- Include calling in the longer-term scope.
- Reuse suitable project infrastructure and integrations, and identify missing requirements before implementation.
- Create and maintain documentation before building the system.
- Support the project autonomy requirements: learning from outcomes, diagnosing errors, validating results, and adjusting runtime strategies.

The long-term business ambition guides the scope. It is not a revenue forecast. The first objective is a repeatable path to retained paying firms, within an agreed operating budget.

## Business root and intended autonomy

On 7 October, the founder clarified that **Lexmom is the business root**. The manager and its specialists are the operating system serving that business. The intended company is bootstrapped without VC and currently has no sales or marketing team.

The desired default is automatic execution of routine lead collection, qualification, email outreach, replies, advertising, and reporting inside previously defined campaign, budget, identity, and contact rules. The founder does not want to approve each routine message or ad operation. Human participation should be available when a customer requests a demo, video call, or similar interaction. Broader company operations can be added as specific workflows are defined.

Initial sample review establishes product truth and validates the system before a channel is enabled; it is not a permanent per-message approval queue. External actions still require suitable provider access and a configured policy. Unresolved product incidents, commercial exceptions, or ambiguous actions must pause or escalate to an accountable owner rather than be falsely reported as completed. Exception ownership remains to be defined.

See the [public product and market assessment](ASSESSMENT.md) for the current evidence and proposed validation sequence.

## Product and buyer boundaries

The public [Lexmom homepage](https://lexmom.com/) currently separates two offers:

| Product | Publicly presented job | Candidate buyer to validate | First-value candidate to validate |
| --- | --- | --- | --- |
| Launch | Create a law-firm website, publish its presence, and capture inquiries | A solo lawyer or new/small firm needing a website and intake | A usable website preview followed by a tested intake flow |
| Manage | Organize clients, matters, work, documents, and financial visibility | A firm owner or operations lead managing fragmented workflows | A real client and matter with a useful task, deadline, or team handoff |

Public descriptions are inputs to product verification, not proof that every feature works. The first sales pilot should select one product and one narrowly defined buyer. Keep Launch and Manage campaigns, messages, activation definitions, and results separate unless customer evidence supports a combined journey.

Prospects are buyers of Lexmom software. Their legal clients and case data are outside the acquisition system's default access.

During a public browser check on 6 October, the homepage and Manage page rendered. The Launch route returned a 504 Gateway Time-out. Recheck that route and the chosen signup/demo path before directing traffic. A single observation does not establish the duration or cause of an outage.

## Requirements still to resolve

| Decision | Information needed | Why it matters |
| --- | --- | --- |
| First offer | Launch or Manage, current price, trial, onboarding help, and promised outcome | Sets the sales pitch and first-value milestone |
| First customer | Solo, small, and mid-size firms across configurable countries; numeric size boundaries, buyer role, practice area if relevant, and language remain open | Defines qualification and channel eligibility |
| Business baseline | Signups, behaviorally active firms, paying firms, retention, and revenue | Makes improvement measurable |
| Past acquisition | Ad spend and funnel counts over the same date range, with destinations and attribution | Distinguishes targeting, conversion, activation, and retention problems |
| Budget | Monthly total and allocations for AI, data, mail, calls, ads, and infrastructure | Establishes enforceable spending limits |
| Pilot outcome | Agreed numbers for qualified conversations, completed demos, activation, payment, and founder time | Defines success without rewarding activity alone |
| Contact source | Existing leads, permission records, referrals, customer requests, or an approved prospect source | Establishes provenance and permitted contact methods |
| Sender | Lexmom mailbox, display name, domain, owner, and authorized access | Determines who prospects hear from |
| Demo | Reviewed recording or sandbox, booking method, presenter, and availability | Prevents outreach without a useful next step |
| Product evidence | Verified feature list, approved claims, pricing, examples, and common objections | Prevents invented capabilities or promises |
| System access | Analytics, product events, CRM, billing, mailbox, calendar, and deployment access | Determines which steps can be automated |
| Autonomy | Actions allowed automatically, escalation owner, and limits on offers or commitments | Defines the manager's authority |

Values remain open until supplied or verified. Access to a key does not prove the account, permissions, available credit, or integration is suitable for Lexmom.

## Customer lifecycle requirements

The complete lifecycle is:

`market evidence -> suitable firm -> qualified contact -> relevant conversation -> signup or requested demo -> activation -> paid -> retained`

The first version must preserve the source and reason for each qualified lead, prepare messages using approved product facts, capture replies, stop unwanted contact, and maintain a visible next action for each prospect. Demo preparation must match the buyer's problem. Follow-up must continue through first product value and payment, with unresolved setup problems assigned to an owner.

### Prospect-to-paid conversion

The founder's intended workflow is an autonomous acquisition-to-paid system, not only a lead list or an email-writing tool. For the initial Manage discussion, it should:

- Find suitable firms and relevant business contacts, retaining the source, verification state, and qualification reason.
- Personalize messages with verified firm facts and a relevant, verified Lexmom capability. Do not invent a firm's internal problems, previous conversations, or customer results.
- Send eligible messages automatically within configured campaign limits, capture replies, answer supported questions, and adapt follow-up to the actual conversation. A human does not review each routine email.
- Guide an interested prospect to the correct signup route, a reviewed product walkthrough, or a requested human demo. Support the first-value workflow and offer an authorized subscription checkout when appropriate; the customer chooses and completes the purchase.
- Confirm payment from billing records, stop acquisition follow-ups after purchase, and transition the firm to onboarding and retention. Track cost and founder effort per retained paying firm alongside counts at each earlier stage.

Automation can execute and improve this process; it cannot guarantee that a particular prospect will buy. Personalized communication, signup, activation, collected payment, and retention remain distinct outcomes. The first implementation requires a working product path, an authorized Lexmom sender, lead-source access, product events, and billing confirmation before claiming the complete journey is operational.

Longer-term channels include approved calling, partnerships, referrals, educational content, SEO, webinars, and paid advertising. Their priority depends on evidence from the selected buyer and budget; they are not all first-version requirements.

## Evidence and measurement

No confident diagnosis of the previous marketing failures is possible from the founder's report alone. Begin with hypotheses and test the earliest material loss in each product's funnel.

| Hypothesis to test | Evidence that would help distinguish it |
| --- | --- |
| Audience and product promise do not match | Campaign/lead cohorts by product, buyer type, country, and stated problem |
| Visitors cannot reach a clear next step | Loaded-page, CTA, signup/demo, and error counts on the actual destination |
| Registrations fail to experience value | First-value events, time to value, assisted-onboarding results, and inactive-user interviews |
| Value is insufficient for payment or return | Activated cohorts, payment/renewal events, objections, and churn reasons |

Two initial positioning hypotheses, subject to product verification:

- Launch: help a new solo firm move from a firm brief to a reviewed website and working intake without coordinating a separate agency.
- Manage: help a growing small firm keep matter context and responsibility visible so the owner spends less time chasing updates.

Neither is an established competitive advantage until target buyers understand the promise and product behavior supports it.

Report counts alongside rates, with cohort, product, channel, and date range. Primary outcomes should include qualified positive replies, demos actually held, first-value completion, paid firms, and meaningful return or renewal. Track cost per activated/paid firm and founder time per sale. Replies expressing interest are different from autoresponders, opt-outs, or complaints. Email opens are supporting observations, not the primary sales outcome.

The sources of truth should be provider receipts for communication, calendar/CRM outcomes for demos, product events for activation, and billing records for payment. A reply saying "I paid" is not payment confirmation.

## Acceptance requirements

Before the pilot is considered production ready:

- Every prospect has an evidence-backed qualification and contact-source record; uncertain facts are labeled.
- The sender identity is verified and belongs to the approved Lexmom workflow.
- Schema, relevance, contact eligibility, and approved-claim checks pass before an external action.
- Replaying a job or webhook does not duplicate a send, booking, or recorded conversion.
- Replies, opt-outs, bounces, cancellations, and pauses stop or change queued actions before execution.
- Failed calls to providers have bounded recovery; ambiguous send outcomes are reconciled instead of blindly retried.
- Spending limits, per-channel limits, per-agent pause, global pause, and an escalation owner are configured and tested.
- Each agent loads its own learning memory before a run, validates output, and records an outcome after it. Agents share business records through the CRM, not one combined learning-memory file.
- No secrets appear in prompts, logs, status payloads, documentation, or source control.
- Synthetic tests, internal-recipient tests, and a limited approved live pilot establish behavior before volume grows.

The founder approved the first Prospect Research and Qualification build on 7 October, following [AGENTS.md](../../AGENTS.md). Lexmom's former placeholder now exposes a research-only manager connector. Runtime credentials, cost reservations, and real output quality must be verified for a live pilot. Later agents and external marketing actions remain separate scope decisions.
