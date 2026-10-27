# Lexmom Integration and Credential Inventory

Updated 7 October 2026, Asia/Calcutta. This inventory distinguishes reusable code from credentials that are actually accessible and verified. It contains variable names only.

## Local credential finding

### Current AWS rollout status

AWS access was restored on 7 October. The existing AWS OpenAI credential is reused under user authorization; the dedicated Hunter key and the user's newly created Dev Team SerpAPI key are installed in Lexmom's isolated `.env`. The new search account authenticated with 250 free searches available at provisioning. It replaces Lexmom's use of the exhausted shared search key without changing other agents' credentials. No paid plan was purchased.

The public dashboard now routes Lexmom to its isolated worker and displays the approved **Lexmom Sub Manager** name. Research forms, cancellation, evidence and artifact downloads are connected. Early live source failures remain in private history. A live supplied-site run qualified one real firm and Hunter returned valid for its published general inbox (provider verification date 20 September 2026). Broad discovery coverage remains under evaluation. See [deployment operations](DEPLOYMENT.md) for current outcomes. Earlier inventory and blocked-login entries below are historical.

The workspace contains these templates:

- Root `.env.example`.
- `services/accountant_agent/.env.example`.
- `services/accountant_agent/.env.reminder.example`.

An ignored root `.env` exists for the research implementation. The initial 7 October inspection found blank LLM, search, and Hunter credentials. Hunter has since been provisioned and authenticated as described below. The dedicated Hunter and new SerpAPI credentials are now local; the shared AWS LLM credential remains only on AWS. Local provider cost configuration still needs an explicit setup before local live runs. No other runtime `.env` file was found in this checkout.

[ENVIRONMENT_SETUP.md](../../ENVIRONMENT_SETUP.md) documents separate production sources on the local server and AWS. A subsequent read-only AWS check on 7 October verified access in `us-east-2`, inspected credential presence on the Menteso OS server, and inspected the two Invoice Reminder secrets listed below. Secret values were not displayed or copied into this checkout. Presence does not establish provider authentication, available credit, token expiry, or Lexmom permissions.

## Verified AWS credential presence â€” 7 October 2026

| Capability | Presence in inspected AWS configuration | Lexmom readiness |
| --- | --- | --- |
| OpenAI | `OPENAI_API_KEY` present in the application and Accountant environments | Available for an authorized reuse test; authentication and credits not checked |
| Anthropic | `ANTHROPIC_API_KEY` present in the application environment | Available as the alternative LLM; authentication and credits not checked |
| SerpAPI | `SERPAPI_API_KEY` present in the application environment | Available for discovery; research shared-key opt-in and cost settings still need configuration |
| Hunter | No Hunter key found in the inspected Menteso application or Accountant environments | Subsequently created a dedicated local Lexmom key; see provisioning record below |
| Google/Gmail | Application OAuth credentials, Accountant credentials, and `invoice-reminder-agent/gmail` fields present | Existing identities only; Lexmom mailbox authorization and identity remain unverified |
| Zoho CRM | Client ID, client secret, and refresh token present in the Accountant environment | Organization, scopes, and Lexmom sales mappings remain unverified |
| Meta | App secret, user token, and other brands' page credentials present in the application environment | Lexmom page/ad-account access remains unverified |
| Stripe | Invoice Reminder key/webhook fields present in the application environment and `invoice-reminder-agent/stripe-live` | These belong to Invoice Reminder integration; Lexmom subscription access remains unverified |
| Wave | API token and accounting identifiers present in the Accountant environment | Existing accounting integration; no Lexmom subscription integration established |
| Google Ads / voice / dedicated Lexmom booking | No dedicated credentials found in the inspected files/secrets | Select and configure when the corresponding specialist is built; Google Calendar scopes on existing OAuth were not inspected |

Checked server files: `/home/menteso_os/app/.env.aws` and `/home/menteso_os/agents/accountant_agent/.env`. Checked Secrets Manager entries: `invoice-reminder-agent/gmail` and `invoice-reminder-agent/stripe-live`. Unrelated AWS workloads and other regions were not inspected. This AWS check was a presence inventory, with no provider workload calls, email sends, advertising changes, or deployment.

## Hunter provisioned â€” 7 October 2026

- Completed free onboarding for `devteam@menteso.com`, selecting a separate team and inviting no colleagues.
- Created a new API key named **Lexmom Sub Manager**. The original unnamed key was not reused or changed.
- Saved the new value only in the ignored root `.env` as `PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY`. Values are excluded from this document and tool output.
- Verified the saved key with Hunter's account endpoint: HTTP 200, expected account identity, Free plan, 50 credits remaining, zero search/verification usage. No prospect verification was performed during this account check.
- This original provisioning entry is historical: the key has since been securely deployed to AWS and a live verification completed. See the current rollout status above.
- The user requested newly created keys named for Lexmom Sub Manager. Existing AWS credentials establish account availability; future Lexmom provisioning should use dedicated keys rather than silently adopting another agent's existing key.

When an authorized environment is accessible, inspect configuration privately and report only whether a value is missing, a placeholder, present, or provider-verified. Do not ask the founder to paste secret values into chat. New agent-specific secrets belong in an excluded `.env`, use a `LEXMOM_` prefix, and have explained placeholders in `.env.example`.

## Reuse decisions

| Capability | Existing code/configuration | Reuse assessment | What Lexmom still needs |
| --- | --- | --- | --- |
| LLM reasoning | OpenAI/Anthropic provider settings and existing request patterns | Candidate reuse; live keys and credit not verified locally | A selected provider/model, verified runtime access, cost accounting, and a bounded budget |
| Agent registration and dashboard | `shared/agent_registry.py`, `server.py`, `static/` | Reuse the registration and display conventions | A manager view and explicit action permissions after the plan is approved |
| Learning and output checks | `shared/memory.py`, `shared/self_test.py` | Reuse interfaces, with stronger agent-specific quality rules | Isolated memory, business outcome evaluation, and prompt/strategy versioning |
| Error recovery | `shared/self_debug.py` | Current helper classifies errors and repeats the same function; it does not implement adaptive fixes or send reconciliation | Provider-aware recovery, changed retry strategies, and structured escalation |
| Gmail | Accountant Gmail client and Google OAuth configuration | Reuse generic authentication, threading, and watch-renewal patterns; isolate from accounting business logic | A dedicated Lexmom sender, matching authorization, provider identity verification, and reply monitoring |
| Zoho CRM | Accountant Zoho OAuth/client patterns | Reuse generic HTTP/auth logic; current PID/deal billing behavior is not a prospect pipeline | Decide whether Zoho is the sales source of truth; verify lead/contact permissions and mappings |
| Social publishing | `shared/social_publishing.py` | Candidate reuse for posting to Lexmom-owned assets | Explicit Lexmom workspace mapping and verified asset permissions |
| Search/research | `SERPAPI_API_KEY` is declared; SEO topic research exists | Candidate reuse for research, not proof of a qualified contact database | Approved firm sources, provenance, freshness, and suitable contact verification |
| SEO content | Existing article generation and validation workflow | Reuse relevant ideas and checks after selecting a content channel | Verified Lexmom content destination; its public app is not proven to be WordPress |
| Calendar/demo booking | No Lexmom calendar-booking integration identified | New integration or approved booking link | Calendar owner, availability, timezone handling, and booking authentication if API-driven |
| Calling | No Lexmom voice integration identified | Later provider selection | Phone number, account/authentication, eligible call policy, scripts, handoff, and spend limits |
| Product/analytics/billing | Lexmom product backend and event access are not connected here | New verified access | Read access to reliable acquisition, activation, retention, and subscription events |
| Sales workflow storage | `shared/db_storage.py` currently stores JSON snapshots/events | Useful for display; insufficient by itself for transactional concurrent outreach | Durable workflow state, unique action keys, a worker queue, and recoverable business records |
| Hosting | Local/AWS deployment conventions exist | Reuse the target's operational patterns | Lexmom-specific runtime, state, health checks, backup, and scoped deployment |

Existing PCT contact reports concern patent filings. They are not established Lexmom prospect lists. Any proposed use needs a separately assessed buyer fit and approved contact source.

## Credential isolation

Production rollout attempt on 7 October: AWS CLI authentication had expired, and browser control timed out. AWS login was started for the user to complete; deployment and live research have not occurred. Dedicated provider slots `PROSPECT_RESEARCH_AGENT_OPENAI_API_KEY` and `PROSPECT_RESEARCH_AGENT_ANTHROPIC_API_KEY` are now supported and declared locally. A blank dedicated slot fails readiness rather than using shared credentials. These slots and the dedicated search key still need provisioning; Hunter remains configured. The bounded first-run profile is `agents/prospect_research_agent/live_pilot.json`.

Shared provider credentials may be reused where the account owner permits Lexmom usage and the permissions fit. Preserve the distinction between code reuse, an account shared by multiple workflows, and a token authorized for one specific identity or asset.

Invoice Request and Invoice Reminder tokens must remain attached to their original mailboxes. Changing a mailbox string does not change an OAuth token's authorized identity. A Lexmom mailbox needs its own authorization; first verify it through the provider's profile endpoint.

The existing social helper normalizes unsupported workspace IDs to a PatentZoom fallback. Lexmom must have an explicit mapping and reject unknown destinations before that helper is used. Never let a missing Lexmom configuration select another company's publishing identity.

Do not substitute an OpenAI reporting/admin credential for a model-workload credential. CRM, advertising, public-page publishing, and subscription billing also require their own verified permissions; a token for one operation is not automatically sufficient for another.

## Configuration groups to define during implementation

These names are proposals, not installed configuration:

| Group | Proposed variables |
| --- | --- |
| Identity and Gmail | `LEXMOM_MAILBOX_ADDRESS`, `LEXMOM_GOOGLE_CLIENT_ID`, `LEXMOM_GOOGLE_CLIENT_SECRET`, `LEXMOM_GOOGLE_REFRESH_TOKEN` |
| Runtime and budget | `LEXMOM_RUN_MODE`, `LEXMOM_MAX_DAILY_SENDS`, `LEXMOM_MONTHLY_BUDGET`, `LEXMOM_MODEL`, `LEXMOM_STATE_DIR` |
| CRM | `LEXMOM_CRM_PROVIDER` plus the selected provider's prefixed credentials |
| Booking | `LEXMOM_BOOKING_URL` or prefixed calendar settings/authorization |
| Research | Prefixed source-provider credentials only if a new service is selected |
| Voice and social | Provider-specific prefixed variables after the channel and account are approved |

Resolve shared-key fallback deliberately: an empty Lexmom value must not silently activate an unrelated account. Inventory secret names and status without storing their values in the CRM or agent memory.

## Provider requirements researched

First research implementation update, 7 October: `agents/prospect_research_agent/` now implements SerpAPI discovery, bounded public-page retrieval, and optional Hunter verification. CrewAI/LangChain dependencies, shared provider setup, and durable research learning/recovery are implemented. Hunter is now configured locally; LLM/search credentials and cost settings remain pending. See the [setup guide](../../agents/prospect_research_agent/README.md) for the installed agent-specific names and required cost reservations. Mail, ads, calendar, and product/billing access remain future integrations.

### First live research batch

| Service | Installed variable | Needed when |
| --- | --- | --- |
| LLM workload account | `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` with an explicit provider/model | Every live extraction run |
| [SerpAPI search](https://serpapi.com/search-api) | `PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY` | Discovering firms; supplied firm URLs can run without discovery |
| [Hunter Email Verifier](https://hunter.io/api-documentation/v2#email-verifier) | `PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY` | Optional verification of an already published email |

Set conservative `PROSPECT_RESEARCH_AGENT_QUERY_COST_USD` and `PROSPECT_RESEARCH_AGENT_LLM_CALL_COST_USD`, plus `PROSPECT_RESEARCH_AGENT_VERIFICATION_COST_USD` when verification is enabled, using the selected accounts' pricing and the configured request/token bounds. The run budget and deadline are already configurable. Shared search-key reuse must be enabled explicitly; keys remain private in `.env` and are never reported by value.

Keys enable live integration testing. Production acceptance still requires a bounded real batch that verifies provider access, source accuracy, duplicate handling, qualification yield, measured usage, and cancellation/resume. Later outbound specialists also need durable action state, duplicate-action protection, provider-specific identity checks, reply/bounce/opt-out handling, and deployment monitoring. The current research build does not establish those later capabilities.

Gmail access must use scopes appropriate to sending, drafting, or reading replies. Request the narrow permissions needed by the enabled stage, following [Google's Gmail scope documentation](https://developers.google.com/workspace/gmail/api/auth/scopes).

The sender setup must verify domain authentication, delivery monitoring, recipient eligibility, and opt-out handling against [Google's sender guidelines](https://support.google.com/mail/answer/81126). An API quota is not a recommended outreach volume or permission to contact every address.

API-driven demo booking requires calendar authorization for the actual operations enabled; availability and event creation are distinct permissions in [Google Calendar's scope documentation](https://developers.google.com/workspace/calendar/api/auth).

[Twilio Programmable Voice](https://www.twilio.com/docs/voice/api) is one provider candidate for later calling, not a selected vendor. If used, validate incoming request signatures and serve trusted HTTPS endpoints, as described in [Twilio's webhook security documentation](https://www.twilio.com/docs/usage/webhooks/webhooks-security). Voice generation, conversation management, and telephony are separate capabilities to evaluate.
