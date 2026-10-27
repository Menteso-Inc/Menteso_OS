# Google verification packet — LexMom Social Media Agent

## Active continuation — 16 October 2026

The user resumed this work. The earlier pause checkpoint below is historical. The owner-profile OS session expired overnight; the user signed in to the exact Menteso OS tab and the dashboard sign-in was verified. The social workspace reports YouTube Connected, last account check 16 October 2026 at 09:45 IST, five drafts, zero approved and zero published. Uploads and scheduling remain disabled. The terminal AWS login also expired; the attempted read-only SSM audit stopped before submitting a command. This does not imply the deployed worker lost its Google grant.

A fresh same-client consent flow selected the existing owner and Lex Mom Youtube channel. Google again showed the unverified-app warning. The agent expanded Advanced only to expose the continuation link, then handed that final action to the owner; it did not bypass the warning. Do not treat an approximate user status as proof that the correct page changed: inspect the current actual screen before consent. Captures for this continuation are in runtime-data/lexmom-social-20261016. Partial browser screencast capture had event truncation/navigation gaps and is not evidence of an uninterrupted recording.

The user asked why the warning appears rather than completing the expanded-warning action. Explained that branding approval and sensitive YouTube permission review are separate, and that the existing AWS grant remains working while the new consent flow can stay paused. The warning has not been bypassed and permissions have not been recaptured. Asked to connect the existing mail@lexmom.com Chrome profile so the domain-review work can continue independently. Public about/privacy checks both returned HTTP 200 with the privacy link and CSP present. Public root-domain DNS has five Google site-verification records already; inspect actual Search Console ownership before adding any record. Existing DNS tokens were not printed or saved into source.

The user connected the app-admin mail@lexmom.com Chrome profile and completed Google's fresh sign-in. Verified the actual dedicated project's Console and the correct admin identity. Its Verification Center reports branding issues and unverified sensitive-scope access; review preparation is blocked until branding is verified/published. Scope justification remains saved at 985/1000 characters, exactly three scopes remain selected and the demonstration URL is blank. The single Web client is the existing LexMom Social Media Agent AWS dashboard client; its full identifier was privately compared to the live AWS-generated owner authorization flow and matches exactly. No new client, scopes, secrets or permissions were created. A task-created chooser for the unrelated Sajan account was closed.

Search Console for mail@lexmom.com has no verified domain properties. Prepared the Domain property for menteso.com. The suggested automatic GoDaddy flow would authorize Google to access the registrar account, so selected Any DNS provider / manual TXT instead; no registrar delegation was granted. Its exact challenge value is stored only in runtime-data/lexmom-social-20261016/.env, with a neighboring placeholder .env.example. A live DNS comparison confirms this exact challenge is not one of the five existing Google verification records. Do not print the value, overwrite an existing TXT record or remove any existing record.

The next required account access is the GoDaddy account or delegated portfolio that actually manages menteso.com. The opened portfolio in the available work profile redirects to GoDaddy sign-in, and there is no existing GoDaddy API configuration in the root environment. Asked the user to connect their signed-in domain account. One control request in that work profile requested a browser-extension update; the Google-admin profile remains controllable, and the two pending Google pages were preserved successfully there. Do not repeatedly reopen wrong-account sign-in pages.

After GoDaddy access is available, inspect the actual menteso.com DNS zone, prepare exactly one TXT record at @ with Google's saved value and the provider's standard TTL, then get the required action-time confirmation before saving the record and confirming Search Console ownership. Explain that this establishes persistent Google Search Console domain ownership for mail@lexmom.com. Nothing has been written to DNS or verified yet. No file/video upload or verification submission is authorized. Keep the working AWS grant and all publish gates unchanged.

Domain-ownership clarification from Google's current official documentation: because the app homepage is on os.menteso.com, the registrable domain to verify is **menteso.com**. Its Search Console owner must be associated with the dedicated Cloud project as an Owner or Editor; Google's domain troubleshooting guide specifically calls for the project-owner account and DNS-level Domain property. A verified subpath alone is not a substitute for that authorized-domain requirement. No ownership/access grant or DNS mutation has been made. Sources: https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification#authorized-domains and https://support.google.com/cloud/answer/13804266 . Once ownership is actually verified, observe the Console's requested 24-hour wait before retrying revised branding; waiting alone does not resolve missing proof.

## Resume checkpoint — user postponed warning review, 15 October 2026

The user explicitly said: "i will do it later remember where we are". Pause this setup work here. Do not retry consent, change settings, upload a video, submit verification, schedule publication or create a reminder until the user resumes.

At the last live verification, YouTube was connected on AWS to the existing LexMom / @thelexmom channel through its owner menteso.com@gmail.com. mail@lexmom.com is the dedicated Cloud-app administrator. Keep these roles distinct. Read-only monitoring remains active; uploads, publishing, paid generation and email campaigns remain disabled. Five unscheduled drafts remain, with zero approved/published and zero upload attempts.

Resume in this order:

1. Read this checkpoint and inspect current browser/account state. The pending OAuth state lasts ten minutes and may have expired; if necessary, start a fresh same-client/same-scope connection from the authenticated OS dashboard. Preserve the working AWS grant. Do not ask for passwords in chat or reuse/copy browser sessions.
2. The owner must personally handle Google's "hasn't verified this app" warning in Chrome's Menteso profile. The user has not completed this step yet. Stop before bypassing it; their decision to do it later is not permission for the agent to bypass it.
3. Capture the remaining real English OAuth/channel/permissions/client-identifier flow and update the local review cut. The existing MP4 is a 119-second captioned, edited preview with its missing portions disclosed; it is not a final Google submission recording.
4. Resolve Search Console ownership of os.menteso.com for the authorized app-admin/domain owner. Google requested ownership proof and a 24-hour wait before retrying revised branding. Scope justification and new app-specific links are already saved; do not repeat setup or rotate credentials.
5. Show the completed local video to the user first. No upload, including unlisted/private, is authorized. Only after a specific later upload authorization may its actual URL be supplied and verification submitted. Google, not the agent, decides approval.

LinkedIn Community Management approval remains a separate pending provider review. Do not retry/bypass it or use browser posting/scraping. Current deployed social UI is release 20261015-social-029. Preserve PCT/shared OS and all existing data, secrets and required rollback releases. No new cleanup attempt is needed; previously policy-blocked files remain untouched.

## Actual status

On 15 October 2026 Google verified the configured branding. Its Branding page subsequently confirmed: "Your branding has been verified and is being shown to users." This is branding approval, not approval of sensitive YouTube permissions.

The scope justification was saved in the Console on 15 October 2026 (985/1000 characters; the Console confirmed "Data access changes saved!"). The selected scope list is exactly YouTube read-only, YouTube upload and read-only YouTube Analytics. The demonstration-video URL remains blank. No sensitive-scope request has been submitted or approved.

The channel owner is menteso.com@gmail.com and the selected existing channel is LexMom / @thelexmom. mail@lexmom.com administers the Google Cloud app and receives developer/support correspondence. The app is for authorized LexMom operators managing LexMom's own channel. External OAuth is needed for the consumer Google owner account; changing the audience to Internal would exclude that owner. Do not describe it as a public multi-customer platform or add unrelated scopes to obtain approval.

Public social-specific homepage and privacy disclosures have been implemented at:

- https://os.menteso.com/api/agents/lexmom_marketing_agent/social/about
- https://os.menteso.com/api/agents/lexmom_marketing_agent/social/privacy

The homepage/privacy fields now point to these live app-specific pages. The Console confirmed "Branding changes saved!" but re-verification found that the new homepage is not registered to the app-admin account. Google explicitly requires ownership verification and a 24-hour wait before retrying. The previous verified branding remains the version shown to users; the revised branding has not been published. Do not report the new links as verified. Preserve the existing client, callback, owner grant and scope set. No new credential is required.

The mail@lexmom.com Search Console account currently opens its welcome screen without verified site properties. Public DNS identifies GoDaddy nameservers for menteso.com. Domain ownership must be proved through the authorized domain owner; no DNS record or Search Console ownership grant was changed in this pass.

## Local review video and current handoff

The local captioned preview is `artifacts/lexmom-google-verification-20261015/lexmom-google-verification-review.mp4`. Its editable Python assembly script and actual browser captures remain in `runtime-data/lexmom-social-20261015/`. A provenance manifest accompanies the MP4. This is an edited review cut, not an uninterrupted screen recording or a completed Google submission.

The real owner-account flow was opened with menteso.com@gmail.com, and the existing "Lex Mom Youtube" channel was selected. Google then displayed "Google hasn't verified this app". Browser-control rules require the owner to handle that security warning personally. The agent stopped there without bypassing it. The remaining permissions-screen capture is pending; the working AWS grant was not revoked or replaced. The incomplete sections are explicitly identified in the video. Nothing was uploaded, published, approved for posting or scheduled.

Live AWS checks exposed a deployment-created worker.lock owned by root. Its exact owner was corrected to the service account with mode 0600, then the actual monitor service completed successfully. OAuth configuration remained unchanged and publication attempts remained zero. The dashboard now shows a fresh verified YouTube connection. Static UI release 20261015-social-029 also suppresses an old failed-reconnect notice only when a later fresh API check confirms recovery; six recovery cases passed. No service restart was needed for this static correction.

## Scope justifications to save in the Console

### youtube.readonly

The signed-in LexMom operator connects the existing LexMom YouTube channel through OAuth. We call channels.list with mine=true to confirm that the granted account matches the configured channel before accepting or using a grant. For an operator-approved upload, videos.list reads its channel identity, processing status and visibility so the dashboard distinguishes processing, a completed private/unlisted upload and confirmed public posting. An API key cannot authenticate ownership or read the owned upload's private processing details. No broader account-write or video-deletion scope is requested.

### youtube.upload

The operator previews and edits a locally prepared LexMom video, chooses Private, Unlisted or Public visibility, approves the exact content/media/channel/visibility and chooses its publishing time. Once publishing is explicitly activated, the worker uses videos.insert with resumable upload for that exact approved video. The narrow upload scope supports this feature without requesting youtube.force-ssl or general account administration. The current setup keeps uploads and publishing disabled and has made zero upload attempts. Draft preparation, connection checks and analytics do not upload anything.

### yt-analytics.readonly

The authenticated dashboard displays the connected LexMom channel's aggregate reports for the last twenty-eight days. reports.query requests views, estimatedMinutesWatched, likes, comments and subscribersGained. This is read-only channel performance reporting with no monetary reports, audience targeting, personal profiles or data used for AI training. Reports are refreshed by the read-only AWS monitor; failed reads do not invent metrics.

## Additional submission information

LexMom Social Media Agent is an authenticated company workspace for designated LexMom operators managing the company's existing channel. The Google Cloud application and YouTube channel may have different administering accounts; channel access is granted by its actual owner. The callback checks exact-channel identity before persisting credentials. Offline access supports the AWS monitor after the owner closes Chrome. No Gmail, advertising, financial, deletion or broader account scope is requested. Public privacy disclosures describe storage, revocation and removal. Publishing is currently off, and there have been zero upload or publication attempts. We request review for the documented scopes and actual use case; please advise if this limited company-owned-channel use falls under an exception to review.

## Required demonstration — pending owner-authorized recording/upload

Use an English screen recording of the real application. Show the app-specific public homepage/privacy notice; a signed-in operator opening Connect YouTube; the existing owner selecting the LexMom channel; the actual Google consent screen and requested scopes; the returned connected channel and real read-only analytics; a rendered video preview; visibility choices; exact-draft approval and scheduling controls; and the account-control/removal explanation. Show the configured OAuth client identifier as Google requires while excluding client secrets, tokens, authorization codes, passwords, other accounts and unrelated private information. Keep all identifiers out of repository source and logs.

Record the actual state honestly. Current uploads are disabled, so a disabled upload control is not proof of a successful upload. Do not manufacture provider success or use an ordinary campaign image/video as a verification walkthrough. If Google requires a live write demonstration, obtain explicit permission for a bounded private test and retain its real receipt; preserve campaign publishing as disabled. Google's instructions require the verification walkthrough itself to be uploaded as Unlisted and its actual URL supplied to the form. The current user instruction forbids publishing/uploading, so that upload needs a specific exception before execution. An unlisted link is viewable by anyone who receives it.

Google's review team controls approval and timing. Do not promise instant approval or remove warnings through a bypass. No review credential/password should be pasted into the form; use an owner-approved reviewer-access process if requested.

## Production checks and removal operations

Visibility is approval-bound and defaults Private. Private/unlisted processing does not create a public posted date. The upload transport rejects untrusted destinations, verifies the exact channel and never retries ambiguous writes. Publishing, paid generation, email sending and campaigns remain disabled; read-only monitoring remains active.

Disconnect is explicit and must not be exercised on the live channel during setup. It revokes the current grant and removes its live API cache/managed receipt values while preserving authored media, duplicate guards and YouTube videos. A confirmed invalid_grant also removes live authorized data; configuration/transient/quota errors preserve the grant. Support deletion requests include retained operational copies; inspect exact social backup paths, remove only the requesting channel's authorized data within seven days, preserve unrelated settings/user-authored work and record a private receipt without token values.

## Official references

- https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification
- https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- https://developers.google.com/youtube/terms/developer-policies
- https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps
