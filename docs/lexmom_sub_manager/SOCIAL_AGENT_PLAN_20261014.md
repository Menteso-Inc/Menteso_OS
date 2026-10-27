# Social Media Posting Agent — build plan, 14 October 2026

Status: owner approved the setup-only build on 14 October and explicitly authorized completing connections and isolated AWS deployment on 15 October. The isolated AWS dashboard/monitor and dedicated provider apps are deployed/configured. LinkedIn product review and the YouTube owner's authenticated dashboard consent remain pending. Publishing, uploads, paid generation and armed schedules remain prohibited. Current evidence and renderer acceptance limits: `SOCIAL_AGENT_SETUP_20261015.md`.

## Verified accounts and integration gaps

- **LinkedIn:** the existing LexMom Page is associated with the new verified LexMom Social Media Agent app. Callback, privacy policy and business contact are configured; the Community Management Development Tier form was submitted. Business/product review is pending and no access token is granted yet. The World Lawyers Forum app remains untouched.
- **YouTube:** the existing LexMom channel, [@thelexmom](https://www.youtube.com/@thelexmom), is selected in the account managed through menteso.com@gmail.com. The channel has 1 subscriber, the description “Launch. Manage. Grow.” and available Customize channel/Manage videos controls. Several other company channels share this Google account, making exact destination verification essential. Browser access is verified; persistent API authorization for the AWS agent is not.
- **Existing code:** `shared/social_publishing.py` supports other company workspaces. Its unknown-workspace fallback selects PatentZoom. Do not pass Lexmom into that fallback or reuse another company's publishing token. New Lexmom transports must fail closed on unknown/mismatched destinations.
- **Meta:** keep Facebook/Instagram as a later integration phase until the existing app/account access restriction is resolved and exact Lexmom Page/Instagram identities and permissions are verified.

Guardian Review: company Page/channel existence is distinct from runtime API access. Reusing a broad Google account or an unknown shared workspace without destination checks risks publishing to another brand.

## One specialist under Lexmom Sub Manager

Create `agents/social_media_posting_agent/` following the repository's Python/CrewAI/LangChain/Pydantic conventions, with `agent.py`, `tools.py`, `tasks.py`, `tests.py`, an independently managed memory file and supporting models/store/connectors as needed. One specialist performs the content workflow through clear tasks; no additional company agents are needed for this first build.

Inputs: versioned Manage/Launch product facts and brand JSON, an approved content brief, authorized media, platform selection and timezone/calendar settings. Inputs must not contain prospect contact data or private client matters.

Outputs: platform-specific captions, visuals, video storyboards/rendered assets, preview calendar, publication receipts and aggregate performance summaries in the authenticated os.menteso.com dashboard. Manage and Launch remain separate content themes and destination links.

Initial capabilities:

1. **LinkedIn:** company Page text/image posts; short video support after the asset-upload path is verified. Captions use a specific problem, one demonstrated product benefit and a relevant CTA.
2. **YouTube:** actual video/Shorts files, titles, descriptions, thumbnails and upload/schedule handling. YouTube is a video destination; do not advertise an unsupported Community-post API as a completed feature. Draft scripts/storyboards alone are not upload-ready videos.
3. **Content production:** reuse approved official LexMom logo/assets and the purple/white/lavender AI/robotics direction. Use readable type, product-specific messaging and real product demonstrations or clearly labelled illustrations. Start with template-based copy and locally rendered motion/video assets to avoid paid inference. New paid image/video/voice providers remain disabled until authorized and configured.
4. **Dashboard:** platform connection status, product chips, content preview, calendar, approve/edit/pause controls, publishing status and results. Display actual clicks and demo requests when measured; do not present impressions as leads or fabricate revenue attribution.

Guardian Review: a single content queue with platform adapters is sufficient. A public social post does not require or expose the prospect database. YouTube needs a real media file and processing checks, not just a caption.

## Workflow and durable state

`Product brief → content draft → brand/fact/media validation → dashboard review → approved calendar → destination/quota checks → platform publish → receipt/reconciliation → metrics → learning`

- Prepare a starter week with separate Manage and Launch messages; suggested cadence is 3 LinkedIn posts and 2 YouTube Shorts, with previews and proposed dates only.
- Approval binds the exact caption, asset digest, product link, platform, destination and time. Editing content invalidates its approval. Publishing remains globally disabled during setup even if drafts are approved.
- Use durable transactional SQLite queues, worker leases and checkpoints. Each platform has its own receipt/state; a successful LinkedIn post must not be repeated because a YouTube upload failed.
- Use bounded timeouts and up to three meaningfully different recovery attempts for safe reads, rendering and resumable transfers. An ambiguous publication/upload outcome becomes a reconciliation task, not a blind duplicate submission.
- Supervised AWS worker/timer runs without idle LLM calls; timezone-aware UTC scheduling, missed-job handling, expiry alerts, pause/cancel and restart recovery are visible in the dashboard.
- Fail on wrong identity, missing scope, expired token, disallowed destination, missing media, unsupported content, broken product CTA, quota exhaustion or unavailable review/approval state. Record sanitized reasons and keep the draft available.
- Self-tests run before output/publication. Per-agent memory stores aggregate strategies and results, not secrets, contact data or private channel data. Adapt topic/hook/timing based on observed results; runtime never rewrites source or grants itself permission.

Guardian Review: per-platform state and reconciliation prevent duplicate public posts. The system can prepare and monitor content while public publishing remains disabled.

## APIs, credentials and production configuration

Use dedicated `LEXMOM_SOCIAL_AGENT_` environment variables and safe placeholders in `.env.example`. All credentials, client/account/channel IDs, provider tokens and resumable upload session URLs stay in protected `.env` files; none appears in source, logs or the UI.

- **LinkedIn:** dedicated application, exact Lexmom organization identity, Page/app verification and Community Management product approval. OAuth scopes must match approved organization posting/reading capabilities; verify the authorizing account's Page role. Use the supported Posts/Images/Video APIs and a supported version header. Token expiry/renewal capability must be reported honestly; no assumption of perpetual LinkedIn access or automatic refresh entitlement.
- **Google/YouTube:** dedicated social OAuth client and consent flow, YouTube Data API v3 plus YouTube Analytics API. Request upload, read-only channel inspection and read-only analytics permissions as needed; Gmail read/insert authorization does not grant YouTube access and is not reused. Select the LexMom Brand Account and verify the returned channel identity against protected configuration before every upload.
- **API key alone:** cannot authorize either company Page publishing or YouTube uploads. Persistent OAuth consent and verified destinations are required.
- **Video policy:** explicitly set privacy status; never rely on the API's default. During setup, no uploads. Any later test upload requires its own concrete authorized file/destination/privacy setting. Scheduling is activated only after content and publishing approval.
- **Quota/cost:** read actual project/account limits, reserve operations before calls, retain a daily ceiling and stop on uncertainty. No paid plan, ads, paid generation or credits purchase is part of this setup. Existing AWS hosting remains the runtime.

The [LinkedIn Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-05) describes organization write/read permissions and pre-uploaded media assets. [Community Management app review](https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review?view=li-lms-2026-05) requires business verification and product-access review; Page admin access alone is insufficient.

The [YouTube video insert method](https://developers.google.com/youtube/v3/docs/videos/insert), updated 8 October 2026, documents OAuth upload scopes, explicit privacy and publishAt handling. Its current method documentation says unverified API projects are not restricted to private viewing; the older video-resource overview still contains the earlier restriction. Verify actual runtime/account behavior rather than hardcoding the older restriction or promising unrestricted public uploads. [YouTube Analytics permissions](https://developers.google.com/youtube/analytics/reference) support read-only performance reports.

Guardian Review: scopes, token lifecycle, actual quota and publication privacy are separate readiness checks. The build must remain usable for drafts if a provider's access review is pending.

## Implementation and acceptance

1. Owner approves this setup-only build and the initial platforms/workflow.
2. Create the specialist, validated JSON configuration, queue/store, dedicated transports and autonomy/self-tests. Implement a real rendering path with meaningful media validation.
3. Add the authenticated Social Media tab under Lexmom Sub Manager, with previews, calendar and explicit per-platform connection blockers. Preserve the existing research, email and customized PCT dashboard.
4. Configure dedicated apps and OAuth through available signed-in accounts. If a provider requires a human challenge, legal-business confirmation or access review, preserve completed work and identify that exact remaining requirement.
5. Verify negative cases: wrong company/channel, expired token, edited approval, missing/bad media, quota failure, duplicate worker, ambiguous publish and restart recovery. Validate generated video readability, duration/dimensions and preview playback. No public test publication is included in this approval.
6. Deploy only the isolated Lexmom runtime after checks pass and active-work guards permit it. Preserve secrets/data, PCT keeper and paused n8n/WLF. Record release/rollback evidence and execute exact disposable-file cleanup under standing instructions.
7. Report working code, configured accounts, verified integrations and blocked activation prerequisites separately. Declare fully connected only after authenticated API identity/permission checks succeed; declare public publishing verified only after a separately authorized real publication has a confirmed receipt.

## Approval requested

Approve building and configuring this specialist for LinkedIn and YouTube with branded draft/asset production, dashboard/calendar, official API connections and monitoring, while public posting, uploads, armed schedules and paid generation remain disabled. Suggested later operating flow: approve a complete week's calendar once, then let the worker publish those exact approved posts at their scheduled times.

Repository requirement: `AGENTS.md`, “Adding a New Agent — Workflow,” step 4: **“Plan — Describe the agent in plain English. Get approval before coding.”** This is a new agent; the earlier Email Campaign build approval does not cover it.
