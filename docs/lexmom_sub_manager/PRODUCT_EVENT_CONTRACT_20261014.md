# Lexmom product-to-email lifecycle contract

Proposed contract only. The owner deferred backend integration and messaging
the active Lexmom task on 14 October. These endpoints and dedicated signing
secrets are not installed. Prospect sends and customer replies remain disabled;
one separate internal draft-review email to Sajan is authorized.

Receiver origin: `https://os.menteso.com`.

- Product events: POST `/api/agents/lexmom_marketing_agent/email/events/product`.
  Events: `demo_requested`, `demo_booked`, `signed_up`, `activated`, `connection_check`.
- Verified billing events: POST `/api/agents/lexmom_marketing_agent/email/events/payment`.
  Events: `paid`, `connection_check`.
- Both lanes use `X-Lexmom-Event-Time` (Unix seconds) and
  `X-Lexmom-Event-Signature` (hex HMAC-SHA256 of `timestamp + '.' + raw_body`).
  Timestamp tolerance: 300 seconds. Replays use the same stable event ID.
- Dedicated shared secrets in protected `.env`: `LEXMOM_EMAIL_AGENT_PRODUCT_EVENTS_SECRET`
  and `LEXMOM_EMAIL_AGENT_PAYMENT_EVENTS_SECRET`. Never reuse IIPLA/Meta/Stripe keys
  or send secret values through task messages, Git, logs or chat.
- Payload: `event_id` (stable <=120 characters), `event_type`, `email`, `product`
  (`manage` or `launch`), `occurred_at` (timezone-aware), and `payment_verified:true`
  for `paid`. Connection checks have no customer email or payment claim.
- Billing origin must verify its provider webhook and successful real payment
  before sending `paid`. A checkout click, complimentary access, free trial,
  IIPLA entitlement or partner claim is not a Lexmom payment.
- Emit after durable transaction commit via a persistent outbox. Network failures
  retain the item for a bounded retry with the same event ID. Do not undo signup,
  entitlement or payment if the OS receiver is unavailable.
- Receiver acknowledges duplicates safely and atomically updates the contact
  stage/cancels pending acquisition actions. It never sends a campaign in response.

Required origin hooks: Manage signup/demo/first meaningful workflow action and
confirmed native payment; Launch registration/demo/first meaningful site action
and confirmed native payment. Keep their existing partner/native business logic
and deployment gates intact. Frontend clicks are engagement, not conversion.

This contract is being implemented in Menteso OS. Integration with the existing
Lexmom task must be coordinated before changing its active release/worktrees.
