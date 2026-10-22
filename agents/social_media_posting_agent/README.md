# LexMom Social Media Posting

One specialist under Lexmom Sub Manager, with separate LexMom Manage and LexMom Launch content. The authenticated dashboard supports private previews, proposed calendar days, editing, local video rendering, destination-bound approval, pausing, official OAuth connections and read-only metrics.

Current verification: the isolated AWS runtime has private drafts/previews and monitor-only scheduling. The existing LexMom YouTube channel was authorized by menteso.com@gmail.com; exact-channel checks, independent token renewal and analytics read passed on AWS. Google verified and published the app's branding on 15 October; sensitive data-access verification still requires scope justifications and a demonstration video. LinkedIn's Community Management review is pending. See `docs/lexmom_sub_manager/SOCIAL_AGENT_SETUP_20261015.md` for acceptance limits. No upload or publication test is authorized.

## Setup mode

The owner's current authorization is **setup and deployment only**. Keep `LEXMOM_SOCIAL_AGENT_PUBLISHING_ENABLED=false` and `LEXMOM_SOCIAL_AGENT_PAID_GENERATION_ENABLED=false`. No public posts, YouTube uploads (including private/unlisted tests), armed schedules or paid generation are authorized. Preparing or approving a draft does not publish it. The provided social monitor never calls `publish_due`.

Starter content is in `content.json`: three LinkedIn drafts and two YouTube Shorts concepts. Rendered previews are silent twelve-second vertical promos made from previously approved AI campaign illustrations, with fades. They are labelled as illustrations; they are not recorded product walkthroughs. No image, voice or video generation provider is called.

## Dedicated connections

Keep all client secrets, tokens and app/Page/channel identifiers in the protected `.env`, using `LEXMOM_SOCIAL_AGENT_` names. Do not reuse another company's app or the Gmail client's authorization.

1. LinkedIn: create/verify the dedicated LexMom application against the existing LexMom company Page and obtain Community Management product access. Set the dedicated product-approval flag only after Products actually shows approval. Until then, Connect stays disabled and the server rejects new authorization attempts before creating state or contacting LinkedIn. Configure its client, secret and exact organization URN. Community Management OAuth requests `w_organization_social`, `rw_organization_admin` and `r_organization_social`. The provider's admin scope is used for Page-role/report reads; this agent does not edit Page settings. Verify actual token scopes and the approved LexMom Page role before saving any token.
2. YouTube: create a dedicated Google social OAuth web client, enable YouTube Data API v3 and YouTube Analytics API, configure its client/secret and exact LexMom channel identity. OAuth requests upload, channel-read and analytics-read scopes with offline access and PKCE. Select the LexMom Brand Account. Gmail access is neither requested nor reused.
3. Authorized redirect URIs are `https://os.menteso.com/api/agents/lexmom_marketing_agent/social/oauth/callback/linkedin` and the same prefix ending in `youtube`. Register only the matching URI with each provider. OAuth callback query strings must not be retained by gateway access logs; the isolated adapter already has access logging disabled.
4. Use **Connect** from the Social Media Posting tab. Consent state is short lived, single use, bound to an HttpOnly secure browser cookie, the signed-in operator and the exact configured app/destination. Pending verifiers remain in `.env`. Failed identity checks never install the candidate token.
5. Run **Check API connections**. Configuration alone is not a verified connection. Analytics availability is reported separately, so an analytics failure cannot falsely disconnect a verified channel. Missing app approval, token expiry, quota or wrong identity leaves content private.

## Workflow and recovery

`Approved product facts → private content → media validation/rendering → operator edits → exact media/content/destination approval → proposed calendar → paused`

Any later publishing activation is a separate owner decision. The dormant publication path requires approved media, the same destination, a timezone-aware schedule and the daily attempt ceiling. Transactional claims prevent concurrent workers duplicating a post. An interrupted/ambiguous provider write becomes reconciliation, never a blind retry. Editing invalidates approval. A new approval is required after the destination changes. Unknown platforms fail closed.

The on-demand agent loads and updates its own private memory, selects a bounded strategy, self-tests content and records aggregate learnings. Runtime changes are prompts/strategy only, never source rewriting. External read retries are bounded; no idle LLM calls occur.

## Operations

The isolated AWS runtime is `/home/menteso_os/agents/lexmom_sub_manager`; its app and virtualenv are separate from other agents. `lexmom-social-monitor.timer` checks account health every fifteen minutes. It cannot upload or publish. A separate `lexmom-social-publish.timer` is supplied and installed **disabled and inactive**. Setup must never start or enable that timer or service. Future owner-approved activation requires both the publishing flag and the worker timer; neither is activated today.

The dashboard exposes approval, local-time scheduling and **Publish due posts**. Scheduling/dispatch stay locked while the global flag is false; a scheduled draft must match its reviewed media and destination. After future activation, the minute-based worker submits due approved posts; the dashboard dispatch control invokes the same durable worker on demand. The API accepts no credential or enable-flag overrides. Queued/published/processing states and safe failure notes remain visible. Actual public publishing has not been tested because the owner prohibits uploads/posts during setup.

The LinkedIn/YouTube chips filter the posts table and separately indicate verified API health. A green dot requires current token configuration, verified identity and a check within thirty minutes; stale/error states never show green. The table includes created/posted dates, plain status labels and a details drawer for previews and editing. New rows record creation time once. Posted time records the first confirmation of public publication, not upload acceptance. Legacy rows without timestamps remain unknown rather than being assigned invented dates. All dates display in the browser's local timezone.

## Persistent access and provider limits

The fifteen-minute monitor runs on AWS without an open Chrome session. YouTube uses its dedicated offline refresh grant. If LinkedIn issues an eligible programmatic refresh grant, the monitor renews within seven days of access expiry, validates the new token's scopes and exact Page, then atomically saves token/expiry fields in the protected `.env`. Its fixed refresh expiry is not extended. A concurrent credential change blocks replacement. A failed renewal preserves existing tokens, waits six hours before a transient retry, and stops automatic refresh after a denied/invalid grant until owner reauthorization. A grant without a refresh token is reported honestly as requiring future owner reauthorization.

YouTube visibility defaults to `private` and is explicitly selectable as private/unlisted/public in draft editing. Visibility participates in the exact approval digest. Processed private/unlisted uploads are labelled Uploaded and never receive a public posted timestamp. No existing draft is approved or scheduled by this migration.

The YouTube account-controls section explains revocation and links to Google permissions and the app-specific privacy notice. Disconnect requires operator authorization, same-origin POST and an explicit confirmation payload; it revokes the current grant with Google before clearing its live protected credential, cached API data and upload receipt values. Authored drafts/media, unrelated settings and YouTube-hosted videos survive. Monitor/publisher/disconnect use the same finite worker lock; confirmed Google `invalid_grant` removes live YouTube authorized data without misclassifying invalid-client, transient or quota failures. Removal of retained operational copies is handled through the documented support request within seven days. Do not test this control against the live channel during setup.

Public verification disclosures only are served at `/api/agents/lexmom_marketing_agent/social/about` and `/api/agents/lexmom_marketing_agent/social/privacy`. All existing private data/media/write routes retain their authentication. Google scope review must describe the actual company-owned-channel use case, not claim a public multi-customer service. The review video must show real OAuth/scoped functionality; never substitute a campaign promo or fabricate an upload receipt. An unlisted verification-video upload or a controlled write demonstration requires a separate owner authorization while the no-upload instruction remains active.

LinkedIn currently shows Community Management review in progress; initial authorization has not completed. Provider approvals, refresh eligibility and revocation cannot be bypassed. Provider HTTP 429 responses pause requests for at least fifteen minutes and honor longer Retry-After windows (one hour by default), with durable per-platform cooldowns across worker restarts. Existing API grants are retained during a cooldown. No browser posting fallback, profile scraping, automated messages/engagement or review-bypass path is provided.

Official references: [LinkedIn refresh tokens](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens), [product access and permissions](https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access).

Run `python -m unittest tests.test_lexmom_social -q` for offline checks and `python -m agents.social_media_posting_agent.agent` for the standalone draft/self-test path. `python -m agents.social_media_posting_agent.scheduled_run` checks configured official APIs without posting. Rendering requires the isolated `imageio-ffmpeg` dependency.

Deployment must preserve the actual served/customized PCT JavaScript, existing email/research state, `.env`, media and unrelated runtimes. Do not restart the shared OS container or PCT keeper. Keep scoped rollback source and compact verification evidence; remove only inspected disposable task files after a successful deployment.

Guardian Review: one queue with two dedicated adapters is sufficient. Destination-bound approval prevents cross-brand writes; account identity and analytics are separate checks; setup monitoring has no publication path. Provider authorization and live deployment must be verified independently before reporting either as complete.
