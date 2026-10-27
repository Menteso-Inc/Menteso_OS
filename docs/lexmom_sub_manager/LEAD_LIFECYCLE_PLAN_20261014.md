# Lexmom lead lifecycle and campaign behavior

Status: proposed lifecycle design, 2026-10-14. Campaigns remain disabled. The CEO's
latest structure is five campaign emails, superseding the earlier seven-day
draft requirement. See `EMAIL_SEQUENCE_DESIGN_20261014.md` for the current branches.

The contact/activity table is deployed. A complete lifecycle engine has not yet
been wired. This plan distinguishes business progress, observed engagement and
permission to send. No email open or product-link click establishes research fit,
permission, a booked demo, registration or payment.

## Lead identity and ownership

- Deduplicate contacts by normalized email, with separate firm associations.
- Keep one current acquisition sequence per person across Manage and Launch.
- Retain both product-fit assessments. Introduction can be Manage, Launch or a
  combined message when both fits are supported. A combined introduction remains
  one sequence; relevant clicks/preferences select subsequent product content.
- Prospect Research owns primary-source facts, evidence and freshness. Email
  Campaign owns draft preparation, delivery/reply handling and suppression.
  Lexmom Sub Manager coordinates next actions and human demo tasks.
- Track stage and heat separately. Heat is New/Opened/Warm/Hot/Replied/Unknown;
  suppression overrides heat. Lifecycle progress is driven by confirmed events.

## Stages and actions

| Stage | Entry evidence | Agent behavior and campaign |
| --- | --- | --- |
| Discovered | Actual contact/source found | Deduplicate, collect firm/person facts, retain source URLs. No sending. |
| Research held | Missing fit, identity, role or fresh verification | Research missing facts within saved quotas. Explain holds; never invent missing values. |
| Qualified / ready | Sourced product fit and contact checks pass | Prepare personalized copy for one product. Sending still requires recipient eligibility and separate activation. |
| Contacted | Provider accepts an enrolled message | Record one durable action; correlate delivery/events. Follow the selected sequence, cap and recipient local hours. Lost acceptance is reconciled before any retry. |
| Engaged | Tracked product CTA click | Warm; propose a follow-up about that product/use case. Do not accelerate frequency or restart day one. Opens remain a weaker Opened signal. |
| Reply review | Actual incoming reply | Immediately pause queued acquisition messages. Classify questions, interested, not now, decline or opt-out. Draft a relevant answer; uncertain intent requires review. |
| Interested | Confirmed positive reply or validated demo request | Hot; replace generic introductions with the requested answer or demo coordination. A form mentioning “demo” without validation is not sufficient. |
| Demo booked | Actual booking confirmation | Prepare research/context for the human demonstrator; send only approved booking-related messages. Stop the introduction sequence. |
| Registered / activated | Verified Lexmom signup and relevant product activity | Stop acquisition messages. Use product onboarding: Manage setup/workflow or Launch site brief/preview/publication. Registration and activation are separate events. |
| Paid | Verified payment-provider event | Stop acquisition. Begin customer onboarding/support. Attribute revenue once; process later refunds/cancellations separately. |
| Dormant / not now | Sequence finishes without response, or explicit timing request | Close the sequence. Respect a requested revisit date; otherwise apply a proposed 30-day cooldown. No endless follow-ups or automatic re-enrollment. |
| Declined / suppressed | Decline, unsubscribe, complaint, hard bounce or invalid contact | Cancel queued marketing for the contact across both products. Suppression takes precedence over scheduling and heat. |

## Campaign design for Manage and Launch

The new approved count is introduction, follow-up 1, follow-up 2, follow-up 3 and
final feedback: at most five acquisition messages per contact. Current runtime
still has the historical fourteen paused drafts; converting those contracts and
content is a separate implementation step, not performed by editing this plan.
A reply, demo booking, signup, payment or suppression stops the acquisition
sequence early. No activation is authorized by this plan.

- Manage: use sourced workflow context; its current CTA is a demo. Do not claim
  a prospect uses spreadsheets, has inefficient processes or needs automation
  without evidence.
- Launch: use sourced web-presence evidence and invite a site brief/preview. Do
  not say “we built your website” unless a real reviewed preview exists. Failure
  to find a website is not proof that no website exists.
- A product click changes message relevance, not the sending cap. A reply should
  receive a reply draft, not the next generic day-three/day-four introduction.
- Customer onboarding and requested demo reminders must use separate content
  from acquisition. Actual product and booking events are required to route them.
- Proposed timing for the five messages: days 1, 3, 6, 10 and 14, adjusted to
  recipient business hours. Timing remains a recommendation; only the count and
  step structure were supplied by the owner/CEO.

## Execution and safety boundaries

The existing Gmail/event monitor polls every two minutes and sends no campaigns.
A future lifecycle worker should be continuously supervised on the isolated AWS
runtime, use a durable event queue and unique event/action IDs, and operate within
configured research quotas and daily caps. It should not call paid AI on every
poll, duplicate events, replay uncertain sends or change its own source code.

Provider delivery/open/click events, mailbox replies, demo bookings, product
signup/activation and verified payments must be separate event sources. Each
transition needs an audit entry containing source, observed time, prior/new stage
and reason. An authentication outage holds sends and reports a blocker. A stale
webhook or mailbox replay must not fabricate recent interest.

## What is already implemented

- One live contact table: 15 unique published email contacts, 0 Hot, 0 Warm at
  deployment. These contacts still require research; they are not 15 qualified
  buyers. No prospect campaign has been sent.
- SES open/click event types configured on the dedicated destination while SES
  sending remains disabled. Correlation and duplicate filtering are tested;
  likely bot events are ignored. No new live campaign was sent to exercise them.
- Gmail sent/reply synchronization, automatic send hold on replies, and an
  operator action to confirm interest from an actual known-lead reply.
- Fifteen paused drafts across Launch, Manage and both, with five messages per
  route. Existing send guards remain; no sequence has been activated.

## Next implementation slice

1. Add a persistent lifecycle stage and event timeline per contact, preserving
   research and heat separately. Test duplicate/reordered/replayed events.
2. Route reply outcomes to held response/demo tasks and cancel superseded series.
   Start with reviewable drafts while sending remains disabled.
3. Connect validated Lexmom demo, signup, activation and payment events. Confirm
   endpoint owners/contracts, event signatures and product mapping first.
4. Add stage-specific content/sequence routing and a supervised worker. Keep all
   sending switches disabled until the owner explicitly authorizes a campaign.

The editable proposal is `lead_lifecycle.proposed.json`; it is documentation,
not a configuration currently consumed by the running agents.
