# CEO five-message sequence: event-driven design

2026-10-14. Owner supplied the five-message structure; cadence and automation
branches below are proposals. Sending remains disabled. This is a design, not
an announcement that the runtime already executes these branches.

## One sequence, three introduction routes

1. Launch only: sourced need for web presence/site creation.
2. Manage only: sourced fit for practice/workflow management.
3. Combined: both product fits supported; one introduction with clear product
   choices. Subsequent content follows explicit preference or relevant click.

One contact has one acquisition sequence across products. Never enroll that
person into two parallel five-message campaigns. A product switch does not reset
the step counter. There are fifteen basic route/step content slots (three routes
times five steps), with evidence-based personalization and a few reusable branch
rules; there is no need to prewrite every mathematical event permutation.

## What each of the five messages does

| Step | No new intent | Relevant click / stated product preference |
| --- | --- | --- |
| Introduction | Brief sourced reason for contact; one clear next action | Not applicable until the introduction is delivered |
| Follow-up 1 | New useful angle, not a repeated pitch | Answer the use case behind the selected product: Launch brief/real preview or Manage workflow/demo |
| Follow-up 2 | Show actual product evidence or a short demonstrable example | Address practical setup and the next useful product action; don't invent customer results |
| Follow-up 3 | Ask one question about fit, timing or a possible blocker | Address the known blocker or invite the relevant demo/preview; don't assume budget or process problems |
| Final feedback | Ask whether the offer was relevant and close the sequence | Ask what is preventing the next step, if still unresolved; finish rather than keep chasing |

Suggested dates: day 1, 3, 6, 10 and 14 in recipient-local business hours. These
are proposed dates, not an armed schedule. Clicks do not create extra emails or
shorten spacing. A missed worker run does not cause multiple catch-up sends.

## Event branches after the introduction or any later step

| Observed event | Lead decision | Next action |
| --- | --- | --- |
| No recorded activity | New / unengaged | Follow the selected five-step sequence if still eligible; email 5 closes it |
| Open only | Opened; weak signal | Keep cadence; try clearer value/CTA. Don't say we know they read the email |
| Product CTA click | Warm; potential interest | Change the next scheduled message's content to that product/use case, without increasing send count |
| Combined introduction → Launch click | Launch branch | Next remaining slot uses Launch content; step does not reset |
| Combined introduction → Manage click | Manage branch | Next remaining slot uses Manage content; step does not reset |
| Clicks on both products | Preference unresolved | Use one remaining follow-up to ask which need is the priority; don't run both series |
| Previously selected product conflicts with a later click | Ambiguous interest | Explicit preference/reply takes precedence. If unresolved, ask rather than flip repeatedly |
| Question or unclear reply | Conversation / review | Pause queued acquisition emails, prepare an answer, review unclear intent |
| Positive reply or validated demo request | Interested / Hot | Stop generic follow-ups; prepare the requested response or booking task |
| Demo booked | Demo stage | Stop introduction sequence. Prepare demonstrator brief and approved booking messages |
| Registered but not activated or paid | Onboarding | Stop acquisition; prepare help for the next real activation step |
| Verified payment | Customer / paid | Cancel unsent acquisition messages for both products; start appropriate onboarding. No automatic cross-sell |
| “Not now” with a date | Deferred | Hold until the requested revisit; recheck eligibility and freshness. Do not restart five emails automatically |
| Decline, unsubscribe, complaint or hard bounce | Suppressed | Cancel queued marketing across both products; do not send final feedback |
| No response after feedback | Dormant | Close sequence; proposed cooldown. No endless follow-up or daily re-enrollment |

Product examples are conditional: a Launch preview must really exist before we
claim it was created; failure to find a website is not proof of no website. A
Manage message must not claim the firm uses old tools without sourced evidence.

## Stronger events override weaker events

Before any dispatch, check current eligibility and stage in this order:
suppression → verified payment → booked demo → signup → actual reply → explicit
preference → relevant product click → open → no activity. A late open/click event
must never move a customer back into acquisition. Payment means a verified
provider event, not a checkout click or unverified email saying “paid.”

Any actual reply pauses queued marketing before intent classification. Unclear
replies remain held. Bot/scanner clicks, footer/unsubscribe links and unrelated
links must not drive product branches. Feedback choices need confirmed events;
automated link previews must not be mistaken for a person's choice.

## Message limits, reliability and current authorization

- Five is the maximum scheduled acquisition count, not a requirement to send
  every message. Success or a stop condition may end the sequence after one.
- The limit covers the same person's Launch/Manage/combined branch switches.
- Direct requested conversation, onboarding and booking content are separate
  purposes, with their own eligibility/caps; they are not a loophole for more
  unapproved marketing. They remain draft-only under current authorization.
- Use durable event/action IDs and recorded send acceptance. Do not blindly
  resend an email when acceptance is unknown. Delay/bounce events need their own
  handling; an open/click is not proof of payment or inbox placement.
- Recheck the stage immediately before dispatch and cancel queued actions after
  stronger events. An email already accepted by the provider cannot be unsent.

## Implementation still required

Campaign validation/content/UI/preparation now use five steps across Launch,
Manage and both. Email event tracking, Gmail synchronization and interest
confirmation are retained. Durable stage/branch state and verified booking,
signup, activation and payment integrations remain future work. The owner
explicitly deferred product integrations and task messaging on 14 October,
requesting drafts and one internal review to Sajan first. All prospect schedules
remain disabled. This design supersedes the older seven-message requirement.
