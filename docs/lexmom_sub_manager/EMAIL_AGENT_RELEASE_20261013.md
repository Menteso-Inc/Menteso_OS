# Lexmom Email Campaign setup release — 13 October 2026

## Verified in production

- Isolated Lexmom dashboard and mailbox monitor are running on Menteso OS. Timer runs about every two minutes and uses dedicated office Gmail authorization. Five messages synced: four incoming messages and exactly one internal review in Sent.
- Manage and Launch each have seven paused daily drafts with fourteen distinct AI robotics illustrations, official LexMom logo, purple/white/lavender styling, shorter headings and readable feature points. No plants/leaves. Campaign definitions and brand profile are versioned JSON.
- Exactly one combined review was sent from `mail@lexmom.com` to `sajan@menteso.com`, Reply-To `support@lexmom.com`. Sender Sent receipt and the live dashboard were verified. Sajan's actual receiving-folder placement is not verified because his connector requires reauthentication. No prospect or campaign emails were sent.
- SES sender `hello@meetlexmom.com`, domain/DKIM/custom MAIL FROM, TLS, scoped role and event queue were previously verified. Campaign sending remains disabled in application and SES, and the recipient restriction remains in place. The earlier single test was observed in the office Inbox.
- The monitor imports saved research without new searches, email verification or inference. Fifteen published contacts remain held; this does not make them qualified or enrolled. Product selection, sourced personalization, research readiness and daily-series permission holds persist.
- Incoming known-contact replies suppress future actions. Demo/reply review tasks deduplicate by message and hold outbound responses. Zero live reply tasks yet; no demo request or client response was manufactured for testing.
- Authenticated dashboard shows drafts, daily images, Sent, Inbox & replies, held reasons and delivery metrics. No activation/send control. Anonymous mailbox access returns 401; approved public artwork returns 200. Source and message text are escaped.

## Verification and preservation

37 meaningful email/SES/dashboard tests pass locally and on AWS. The standalone draft agent validates all fourteen previews through its four self-tests. Gmail checks verify exact office identity and read/insert permissions, token retry boundaries, durable history cursors, expired-history recovery and archive acceptance reconciliation. Reply tasks, evidence handoff, suppression, event ordering and access boundaries are covered.

Live desktop UI showed connected mailbox, seven paused drafts per product, daily art and the single review in Sent. Phone viewport 390×844 had no page overflow: page width 390, email workspace width 348. Original viewport restored. Screenshots: `email-workspace-20261013.png`, `email-sent-review-20261013.png`, `email-mobile-20261013.png`.

Only the isolated Lexmom adapter and owned email monitor were restarted. Existing PCT source/dashboard changes and runtime were preserved; the shared `menteso-os` container retained its October 5 start time. n8n/WLF remain paused. Private state, existing `.env`, source and rollback releases retained; no keys/customer data uploaded to GitHub and no commit/merge created.

## Unfinished configuration

**Pub/Sub is not connected.** Its API was enabled and captured in private setup evidence, but topic creation was not confirmed before browser control failed. No verified Gmail publisher grant, authenticated subscription, callback or active `users.watch` renewal exists yet. The office Chrome session refuses debugger control; the alternate Dev session requires Google identity verification. No Google password, passkey or broader admin token was collected to bypass this. Two-minute Gmail synchronization remains working.

When access works again: inspect whether the dedicated topic already exists; do not duplicate it. Grant the Gmail publishing identity only topic publish access. Configure a private authenticated notification route/subscription with exact OIDC audience and service identity validation, durable deduplication, bounded payloads and poll fallback. Register the office mailbox watch in the same OAuth project and renew daily. Verify a genuine mailbox-change notification and resulting sync before reporting push readiness. See [Gmail push setup](https://developers.google.com/workspace/gmail/api/guides/push) and [authenticated push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions).

**Future campaign activation is not part of this release.** No recipient enrollment, schedule or bulk dispatch worker is active. Sender postal identity is still unset; future approved audience/frequency/limits, appropriate SES recipient access and end-to-end activation validation are required. No inbox-placement percentage or never-Spam guarantee can be inferred from Delivery events.

The internal review contained an encoding replacement for some punctuation during the local Windows-to-connector transfer. Source drafts/artwork and SES MIME rendering retain UTF-8. No second review email was sent to correct punctuation because only one internal review was authorized.

Cleanup receipts record exact disposable paths and space measurements. Active Pub/Sub follow-up helpers and protected credentials/evidence remain available for continuation.
