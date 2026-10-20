# Email Campaign specialist

This specialist prepares Launch, Manage and combined campaigns and monitors the Lexmom office mailbox. Current deployment is setup-only: fifteen short, image-free drafts are paused, no prospect sequence is armed, and the monitor cannot send email.

On 16 October, the owner approved “Regards, Sherry | LexMom team” across all fifteen templates (`20261016-signature-v3.2`). A separate, explicitly authorized five-message internal preview to Azam tests the combined copy and transport at five-minute intervals. It does not enroll a prospect or activate the campaign dispatcher. Evidence and remaining activation gaps are recorded in `docs/lexmom_sub_manager/EMAIL_RELEASE_20261016.md`.

## Current flow

1. Prospect Research saves sourced firms, product assessments, contacts, verification and personalization evidence.
2. The email monitor reads the existing inventory, without searches or model calls. Unqualified contacts, unresolved product preferences and missing permission remain held.
3. Three versioned JSON routes each provide five drafts: introduction, three follow-ups and final feedback. Proposed offsets are 0, 2, 5, 9 and 13 days. All current drafts are image-free, including the logo; combined drafts retain both approved product links. These offsets do not activate a schedule.
4. Dedicated Gmail authorization reads `mail@lexmom.com` and supports inserting SES sent copies. The allowed scopes are `gmail.readonly` and `gmail.insert`; the transport has no Gmail send/delete operation.
5. A supervised systemd timer checks Gmail history and SES events about every two minutes. Cursors advance only after durable storage; expired history recovers with a bounded full sync.
6. Incoming messages from saved contacts cancel their pending sequences. Relevant replies and demo subjects create deduplicated review tasks with outbound responses held. Message content is untrusted data, never an executable instruction. No automatic reply or booking is made.

## Dashboard

In `os.menteso.com`, select **Lexmom Sub Manager → Email Campaign**. Launch, Manage and Launch + Manage show their five drafts; Sent mail and Inbox & replies show cached live messages. Operator/admin authentication is required. Public asset routes retain the approved graphics and official logo, including historical artwork referenced by earlier Sent mail.

Saved drafts, cached mail and internal reviews are distinct from prospect send counts. Provider Delivery does not establish a recipient's Inbox/Spam placement. The previous SES test has an observed office Inbox placement; general prospect placement is unknown.

## Personalized copy — 14 October revision

`campaigns.json` contains the fallback `subject`, a `subject_named` template using `{contact_name}` and/or `{firm_name}`, a `subject_firm` template using `{firm_name}`, the named/general `body`, and a separate first-message `body_firm`. Body templates allow only `{firm_name}` and resolve it from sourced context, falling back to “your firm.” Subjects use the sourced display name; the renderer does not invent a first name for a general inbox. The dashboard's John/Example Law lines are clearly labeled examples, not prospects. A verified introductory source fact is bounded to 240 characters and omitted when unavailable; CEO document fact/name fields are explicit review placeholders.

The tone is short and question-led, with 35–45 words in each current main body. Named messages refer to the actual firm; firm-inbox introductions ask for the responsible colleague. The renderer provides plain text and simple HTML paragraphs, transparent text links, a text signature and opt-out footer. It includes no image, logo, hero, tracking image or promotional card. Source facts and names are escaped in HTML; nested attributes, conversions and unknown body fields are rejected.

Questions and conditional wording do not assert that a firm has no website, uses outdated tools or has a particular internal problem. “We built this for you” requires an actual generated, reviewed, recipient-specific preview with a working link. No such preview generator is part of this revision. The five-step definitions replace the older seven-day definitions. Installation cancels obsolete unsent prepared/queued actions and preserves accepted message history.

The owner deferred product backend integration on 14 October. Automatic product-choice branching, signup/demo/payment stops and the dispatch lifecycle remain future work. The previous combined review to Sajan remains historical and does not match the current `20261014-conversation-v3.1` definitions. The owner requested the three-tab Google Doc for CEO review and will forward it themselves; no replacement Sajan/CEO email was sent. Historical artwork remains available for old Sent mail and is not inserted into current drafts.

Current link labels use the full product names: “Explore LexMom Launch,” “Book a LexMom Manage demo,” and, in the combined route, “Explore LexMom Manage / Book a LexMom Manage demo.” Product destinations and sequence content are unchanged. The minor template-version bump preserves separation from previously prepared documents.

## Follow-up continuity — CEO review revision

Each of the twelve follow-ups explicitly recalls the immediately preceding email, adds one useful point or evaluation question, then asks for the next step. Launch progresses from a practice brief to a practice page, draft review, a focused walkthrough and final feedback. Manage moves from connected matter work to a chosen workflow, a one-matter demo, a specific setup/fit question and final feedback. The combined route introduces both products, offers two concrete evaluation starting points, explains their walkthroughs, asks the current priority and closes with product feedback.

Each step records `references_step` and `new_information` in the JSON; these are reviewer/agent metadata, not extra email copy. Validation requires a reference to the immediately preceding step and an explanation of the new value. Both the transactional reservation and dispatch preflight require a nonempty provider acceptance ID for the previous message in the same recipient/product/version sequence. Prepared, queued, ambiguous or other-product/version messages do not satisfy that guard. It confirms acceptance for sending, not delivery or reading. No open, click, reply or product choice is invented in the copy.

The existing Google Doc retains Launch, Manage and Launch + Manage tabs and audience/routing sections. All fifteen source bodies and subject variants were checked against saved browser exports. The Doc explains each follow-up's recap and added point outside the email copy. This revision still leaves every campaign paused and sends zero emails.

## Configuration and activation

All credentials and infrastructure identifiers stay in protected `.env` files under the `LEXMOM_EMAIL_AGENT_` namespace. `.env.example` documents placeholders. AWS uses the existing instance role to assume the scoped SES role; there are no new static AWS credentials.

Current barriers are intentional: application send/campaign switches false, SES configuration sending false, IAM recipients restricted to the earlier internal-test destination, no queued sequences, and no dashboard send activation. Future activation is separate work: approve eligible recipients/frequency, sender postal identity, offer, operating limits and permitted recipients; complete an activation worker/control flow and validate its full sending lifecycle before enabling it. This setup must not be described as a launched bulk campaign.

Google Pub/Sub API is enabled in the dedicated project. The owner's 14 October verification unlocked the office Cloud session, and the existing dedicated reply topic was found. It has no subscription; no publisher grant was saved and mailbox-watch integration remains unconnected. Browser controls still fail intermittently. Existing Gmail authorization was verified directly on AWS and the supervised 120-second polling monitor continues independently. Do not claim real-time push is working or grant broader Google/Gmail permissions as a workaround.

## Verification

```powershell
python -m unittest tests.test_lexmom_email_campaign tests.test_lexmom_email_transport tests.test_lexmom_dashboard
python -m agents.email_campaign_agent.agent
```

The standalone draft agent makes no provider calls or sends. `python -m agents.email_campaign_agent.monitor` reads the configured mailbox and SES queue; it still sends zero emails. State is a private SQLite database with durable send reservations, event deduplication, reply suppression, archive reconciliation and review tasks. Ambiguous provider acceptance is held for reconciliation, never automatically resent.

Deployment evidence and remaining work are in `docs/lexmom_sub_manager/EMAIL_AGENT_RELEASE_20261013.md`.
