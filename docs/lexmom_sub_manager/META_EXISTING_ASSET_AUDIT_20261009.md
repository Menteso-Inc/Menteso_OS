# Lexmom Meta inventory and Ads Manager build proposal

Date: 2026-10-09. Status: read-only audit; implementation plan awaiting review.

## Scope

Inspect existing assets before creating anything. Prepare future management from os.menteso.com, including content generation, budgets and tracking. Keep Manage and Launch separate. The user explicitly requested no campaign launch or ad spend now.

No campaign, ad, budget, permission, token, Page, Pixel or production service was changed. Browser account/date/name filters were used only for inspection. n8n/WLF remain paused and PCT was not touched.

## Confirmed existing assets

| Location | Asset | Verified finding |
| --- | --- | --- |
| Menteso, Inc. | LexMom New ad account | Connected to the website's current dataset. Ads view returned no ads; campaign view displayed first-campaign setup message. Account Overview showed 0 active campaigns and $0.00 spent in the last 7 days. Historical delivery is not independently verified through the API. |
| Menteso, Inc. | LexMom Facebook Page | Exists; linked to Instagram thelexmom and LexMom Group. Page flags a review of people outside the business portfolio. No access assignments changed. |
| Menteso, Inc. | @thelexmom Instagram | Exists and is connected to the LexMom Page. |
| Menteso, Inc. | LexMom Website Data | Its Pixel ID matches the actual production HTML and JavaScript served by www.lexmom.com/manage/. Meta confirms browser Pixel and Conversions API activity. Connected ad account is LexMom New. |
| Menteso, Inc. | Conversions API System User | Existing Employee identity has CAPI app/pixel/dataset assets. No ad account or Page assignment was listed; it is not a verified Ads Manager identity. |
| Menteso, Inc. | Apps | Apps inventory displayed TrendTracker. The CAPI system user additionally lists Conversions API Application. No dedicated Lexmom Marketing API app was verified in this portfolio. |
| Menteso, Inc. | Domains | Settings showed No domains added. This does not prove lexmom.com is unverified in every other portfolio. |
| Older LexMom portfolio | LexMom Ad Account | Maximum date range showed one WFC Singapore Lead Generation draft campaign, one draft ad set and one draft ad. These are not verified Lexmom product campaigns. |
| Older LexMom portfolio | LexMom Account App | Existing app found. Marketing API capability and usable credentials not yet verified. |
| Older LexMom portfolio | LexMom Pixel | Different from the production site's Pixel; dataset reported no events. No Page or Instagram account was added in this portfolio. Preserve it; do not replace the production Pixel. |
| Menteso Main Ad Account | Remote Paralegal Leads / USA / Attorneys / TOF | Maximum range showed one campaign, one Leads (Website Conversion) by Naushad ad set, and 3 ads in the footer. Two visible ad rows were draft video copies. Campaign/ad set delivery showed No ads. Meta also displayed a business-information update warning. Do not assume this campaign promotes Lexmom without checking its creative/destination. |
| Original shared numeric account | Historical campaigns | 18 campaigns present; visible names included Menteso, IIPLA and WLF. Maximum range plus campaign-name contains Lex returned No campaigns found. This only rules out matching names, not Lexmom content inside differently named campaigns. Account Overview reported 0 active campaigns. |

Actual identifiers are kept only in the gitignored `runtime-data/lexmom-ads-audit/.env`. This is an inventory file, not live runtime configuration. App credentials remain blank; no new token was generated. Do not commit or expose environment contents.

## Tracking evidence

Events Manager range: September 11–October 8, 2026. LexMom Website Data listed lexmom.com plus two other websites whose details were not inspected.

| Event | Count | Displayed status |
| --- | ---: | --- |
| PageView | 546 | Active; Multiple integrations; last received 2 hours ago |
| View content | 41 | Active; Meta Pixel |
| Add to cart | 16 | No recent activity; Meta Pixel |
| Complete registration | 4 | Active; Meta Pixel |
| __missing_event | 3 | No recent activity; Meta Pixel |
| Schedule | 2 | No recent activity; Meta Pixel |
| Lead | 2 | No recent activity; Meta Pixel |

These are received event counts, not unique users, ad-attributed leads, or verified paid customers. No Purchase row appeared in the inspected event list. Diagnostics reported no active errors in its last-three-days window; this does not validate historical event semantics, event deduplication or revenue tracking. Setup checklist still displayed 50% complete. Investigate malformed event names, product attribution, signup/activation/purchase semantics, test/staging traffic and browser/server deduplication before optimizing paid campaigns.

Private screenshot evidence: `runtime-data/lexmom-ads-audit/lexmom-live-pixel-events.png`. The earlier `pixel-mismatch.png` captures the legacy portfolio only and must not be used to claim the production site is misconfigured.

## Credential checks

- Existing shared META_LONG_LIVED_USER_TOKEN failed the read-only permissions check with HTTP 401 / OAuth code 190.
- The migrated WLF Meta Lead Ads OAuth credential passed its permissions check but lacks ads_read and ads_management. Its Page enumeration returned one Page and no Lexmom Page. It is unsuitable for this integration.
- No usable Lexmom Marketing API token has been verified. Existing CAPI access is not proof of campaign-management access.
- Never repurpose or revoke shared credentials, print tokens, or reactivate paused workflows while setting this up.

## Proposed implementation for approval

1. Reuse the confirmed Menteso-owned LexMom New, Page, Instagram and current dataset. Resolve app ownership and provision a dedicated least-privilege automation identity; request action-time approval for any new access grant. Keep secrets server-side in a scoped .env and placeholders in .env.example.
2. Build Ads Manager as a specialist under Lexmom Sub Manager, with JSON product profiles for Manage and Launch. On demand, generate supported ad copy, headlines, creative briefs and image assets with provider/cost limits; previews and claim validation precede publication. Video support must explicitly distinguish scripts from rendered video.
3. Implement account-scoped inventory and reporting first, then campaign/ad set/ad creation, editing, pause/resume, budgets, schedules, audiences, placements, media and previews supported by Meta's API. Default to local drafts; any remote creation defaults PAUSED. Current setup keeps publication and spending disabled.
4. Add dashboard views for drafts/campaigns, content, budget controls, spend/results and tracking health. Show API freshness, currency, costs and unknown revenue honestly. Report Manage and Launch separately. The top-level Run button must not activate paid delivery unless the user explicitly enables it with a budget.
5. Validate Pixel/CAPI paths and reconcile with real signup, activation and payment records. Use event IDs for deduplication, UTMs for attribution and clear separation of Meta-reported revenue versus verified business revenue. Do not replace the existing working dataset.
6. Add Pydantic validation, per-agent memory/self-tests, bounded retries, rate-limit handling, idempotency/reconciliation, account/asset allowlists, spend limits, audit logs, token health and a kill switch. No source-code self-modification.
7. Test with mocks and read-only live requests while spending is disabled. A real paused-object write test and later delivery test are separate milestones. Deploy only through the documented scoped procedure, preserving PCT and paused WLF/n8n; verify and clean disposable outputs after an authorized deployment.

## Completion criteria and remaining input

Setup is ready only after correct app access and tokens are validated, the dashboard handles the supported campaign lifecycle, tests pass, tracking is reconciled, and the scoped deployment is verified. This audit is not a production-ready agent.

Required next: approval of this concrete build plan under AGENTS.md; app-admin access or owner participation if needed; action-time confirmation for dedicated Meta permissions/token creation. No budget or paid API purchase is needed to approve this setup-only plan. Budget, audience/geography and creatives must be settled before a later launch.

Some Meta billing, business verification, account restrictions and security renewals may still require an owner in Meta. The dashboard should expose these blockers rather than claim that all Meta UI actions can be automated.

## Follow-up readiness inspection and developer suspension

The user requested another configuration check and production credentials, followed by help resolving the developer-access failure.

- **Confirmed blocker:** opening the existing LexMom app redirects to the developer account error page. The official support link opens Account Status and explicitly reports **Developer account suspended**, citing Platform Term 7.e.i.2 (negatively impacting platform, products, data, or users). This is not simply an absent app role or missing API scope. No affected app or specific offending activity is identified on the visible notice.
- The same page displays an earlier appeal and redacted attachment dated August 19, 2026, describing WLF/IIPLA remediation. Those are historical claims, not newly validated findings. No decision/outcome for that appeal is shown in the inspected page.
- Prepared, but did not submit, a factual clarification/review appeal. It selects that the specific violation is not understood and that further remediation is not verified, requests the affected app/activity and the prior appeal outcome, and makes no assertion that the unspecified violation has been fixed. Submission awaits explicit user authorization. No attachment uploaded.
- **Billing:** LexMom New has an existing default payment method, USD currency, zero balance/no payment due and no recent spending. Meta displays a $26.95 daily spending limit. This is Meta's cap, not a user-approved campaign budget or a guarantee of future delivery. Payment data was not copied into project configuration.
- **Business:** Menteso, Inc. is Unverified, with no primary Page. The portfolio website is worlditforum.com. This is a shared business; do not replace its company details with Lexmom details without owner direction. Unverified status does not independently establish that every own-account API operation is blocked; the confirmed developer suspension is the immediate blocker.
- **Conversions:** business settings show no custom conversions added. Standard Pixel events already exist; custom conversions are not mandatory for every campaign.
- **Audiences/settings:** no saved audience records displayed; audience/placement controls, engaged audience and existing-customer segments are Not defined. No account controls, value-rule sets or naming templates are configured. Creative feature testing and WhatsApp marketing messages are Off; advertiser/payer defaults are Not added; third-party reporting is Unconnected. These are configuration choices to resolve for the selected campaign, not universal API prerequisites. No setting changed.
- Existing Page/Instagram connection is confirmed, but the app's production publishing scopes, access level, professional account type and valid publishing credential remain unverified because app access is suspended. API app credentials, Marketing API permissions, Page/Instagram publishing permissions, asset assignments and token expiry/revocation must be validated before labeling any credential production ready.
- Do not create alternate identities/apps to evade the suspension. Use Meta's review process. Tokens do not guarantee access after owner revocation or a Meta restriction, including tokens configured without a fixed expiry.

Private evidence: `runtime-data/lexmom-ads-audit/developer-access-blocked.png` and `developer-appeal-draft.png`. The browser appeal draft is kept open for review. No new production token, app secret, CAPI token or publishing credential was obtained during this follow-up.

API references checked: [Meta Marketing API collection](https://www.postman.com/meta/facebook-marketing-api/documentation/0zr4mes/facebook-marketing-api-mapi?entity=request-31691153-c1766121-a931-4df5-88f6-3797996daff5) and [Meta Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-894be833-d0b6-4877-859e-c61ae6474d64). Marketing own-account access and organic Instagram publishing must be validated separately; selecting all scopes is not a substitute for the required app/asset access.

### Appeal submitted — 2026-10-09

The user explicitly authorized submission of the prepared appeal. Submitted it once through the official Account Status form and confirmed the Submit response dialog. After reloading the page, the exact new response remained saved with its fields and Submit control disabled, confirming persistence. No new attachment uploaded. The developer account still shows suspended; no case number, review completion, restoration, or response-time commitment was displayed. No production credentials obtained. Evidence: runtime-data/lexmom-ads-audit/developer-appeal-submitted.png. The earlier awaiting-authorization statements above describe the pre-submission state and are superseded by this entry.
