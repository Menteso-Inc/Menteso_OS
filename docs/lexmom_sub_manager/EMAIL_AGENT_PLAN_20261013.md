# Email Campaign specialist — setup-only build plan

Owner requested a production-oriented Email Campaign specialist under Lexmom Sub Manager for both Manage and Launch, seven daily drafts per product, branded campaign images, sent-mail/reply visibility in os.menteso.com and exactly one combined internal review email to sajan@menteso.com. No prospect campaign sending is authorized.

## Concrete deliverable

- One Email Campaign specialist, with independent Manage and Launch versioned JSON campaigns. Fourteen daily drafts remain paused; their sequence dates are relative, not an armed schedule.
- Grounded named-contact and generic-firm variants using the existing Prospect Research product assessments, contacts and source evidence. Unqualified/unsourced contacts remain held. Daily-sequence sending requires a recipient's documented permission for that frequency; public email and fit alone do not confer permission.
- Two original product campaign illustrations matching the live Lexmom purple, white/lavender/soft-teal palette and typography. Text-first responsive HTML with a plain-text alternative; no invented testimonials, numbers, security/integration guarantees or results.
- Durable SQLite campaign/contact/action/receipt/event/mailbox state. Per-contact duplicate suppression; explicit unknown-send reconciliation; pause on reply, opt-out, complaint, hard bounce or conversion; bounded daily/rate limits. Draft generation costs no model tokens by default.
- AWS SES sending and SNS/SQS event integration with existing scoped credentials. Campaign gates remain disabled in application and SES, and no prospect jobs are executed. The internal review is one separate allowed action and cannot activate either campaign.
- Dedicated Gmail authorization for mail@lexmom.com, identity/scope verification, bounded initial sync and history-based reply/sent sync with expired-cursor recovery. Gmail readonly plus insert scopes support reply visibility and SES sent-message archival without Gmail sending/deletion permission. Connector access in this chat is verified but does not supply the AWS runtime a persistent token.
- Authenticated Email Campaign workspace: product chips, seven-day draft previews, sent mail, replies, held reasons, delivery/bounce/complaint totals and honest placement reporting. No fabricated inbox/spam percentage: provider delivery is distinct from recipient placement. Seed-mailbox observations and Google Postmaster aggregate metrics stay separately labeled.
- Supervised monitoring with no idle LLM calls and bounded transient retries. Monitoring may run while sending remains paused. Fresh readiness must distinguish working code, configured credentials, verified live integration and remaining activation prerequisites.
- Meaningful offline tests, isolated staged deployment, an internal review verification, desktop/mobile UI checks, rollback evidence and exact disposable-file cleanup. Preserve PCT, Accountant/SEO, research memory/data, shared container runtime and paused n8n/WLF.

## Design review

Bug/workflow review: reserve send actions transactionally and never retry an ambiguous send as a new send; last-moment suppression and mailbox freshness checks are required. A burst of seven daily prospect emails is not armed by a copy-preview request.

UX review: show paused campaign status, readable product-specific previews and actual mailbox content through authenticated endpoints; no implementation secrets in the interface. Send counts exclude drafts and imported inbox messages.

Cost/flow review: use deterministic verified templates; Gmail/event sync needs no paid LLM. No new mail subscription, advertising or paid API workload. SES transport remains metered. Inbox placement for arbitrary prospects cannot be observed through sender-side SES delivery events.

## External facts checked

Live Launch and Manage pages were rendered in the browser on 13 October. Their features support website/intake/review/publishing content for Launch and connected matter/tasks/documents/deadline/billing views for Manage. Public marketing numbers and testimonials were not independently substantiated and are excluded. Owner's two supplied example emails inform short problem-focused wording and a low-pressure walkthrough CTA; competitor-specific claims and private email details will not be copied into public assets.

Gmail supports [initial/full and partial history synchronization](https://developers.google.com/workspace/gmail/api/guides/sync) and [message insertion without sending](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/insert). Follow [Google sender requirements](https://support.google.com/mail/answer/81126); [SES events](https://docs.aws.amazon.com/ses/latest/dg/monitor-using-event-publishing.html) do not establish every recipient's folder placement.

## Remaining setup prerequisites

Dedicated Gmail OAuth app/client and mailbox authorization must be available to the AWS service. Do not reuse another agent's mailbox token. Google may require the app owner/Workspace administrator to complete consent or production app configuration. The build can proceed with explicit missing-credential status while this setup is completed; it cannot be declared fully connected until the runtime verifies mail@lexmom.com and actually synchronizes messages.

Before later campaign activation: approve actual recipient eligibility/frequency, sender signature/postal identity, offer, geography and operating limits; verify one-click unsubscribe and a healthy reply/event monitoring path. Both campaigns remain paused under the current request.
