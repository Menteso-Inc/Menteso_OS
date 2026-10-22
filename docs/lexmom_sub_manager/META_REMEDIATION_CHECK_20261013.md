# IIPLA / WLF Meta credential separation check

Checked: 13 October 2026 (Asia/Calcutta). Requested by the owner after reporting that the cross-product environment deployment mistake had been fixed.

## Result

**No IIPLA Meta app credentials or access token were found in the inspected current WLF runtime, WLF environment files or saved Meta connection records. WLF's configured tracking identifiers differ from the running IIPLA identifiers.** This verifies the inspected current configuration boundary, not the original enforcement cause, historical API usage, credential validity or Meta approval.

AWS access was verified as the existing Devteam IAM user. The expired local CLI session was refreshed through the existing authenticated console. No new IAM user/key or permission grant was created. Read-only SSM scripts inspected the running resources; no service was restarted or production configuration changed.

## Verified findings

| Check | Finding |
| --- | --- |
| WLF production location | Running on IIPLA Main Server, with its own WLF Docker project, release directories and uploads. The public worldlawyersforum.org Nginx virtual host routes to the WLF web/API listeners. |
| Running WLF services | Web blue, API blue, jobs and Redis running. Green web/API rollback containers stopped. |
| Production Meta app credentials | No nonempty Meta/Facebook app ID, client ID, app secret, client secret or access token in the inspected WLF container environments. No .env file found at the checked embedded application locations in web/API/jobs containers. |
| Production tracking | WLF Meta integration flag enabled; Pixel/Dataset fields present. In-memory comparisons confirmed none of those identifiers match the running IIPLA Pixel/Dataset values. Raw identifiers were not exported or printed. |
| Ownership guard | Running WLF containers report provider credentials verified and a WLF-prefixed credential set. This is a deployment attestation, not independent Meta-side asset-ownership validation. |
| WLF production environment files | Eleven files checked under the discovered WLF deploy/release roots. No nonempty Meta app credential fields and no tracking identifier matching running IIPLA were found. Three inspected saved environments enable WLF tracking. |
| Isolated WLF staging | Running web/API containers contain no Meta credentials or tracking identifiers; their Meta integration flags are false. Three environment files checked under its deploy root; none flagged. |
| WLF database | Aggregate-only queries found zero Meta marketing connections, zero Meta OAuth connection sessions, and zero Facebook/Instagram social-account records, including zero records holding encrypted credentials. Queries used a read-only transaction and a statement timeout. No customer records or credential values were retrieved. |
| Database tracking setting | One analytics-settings row has tracking enabled and a Pixel configured. On production it matches WLF's runtime Pixel and differs from the running IIPLA identifiers. The isolated staging process has no runtime Pixel and its integration flag is off; a database setting alone does not establish that it transmits events. |
| Tracking history | 2,915 CLIENT_REPORTED and 256 SKIPPED event-log records in the queried WLF database. These are application status counts, not proof of Meta receipt, successful server-side delivery or unique customers. No SENT status group appeared. |
| Public browser sample | One production homepage reload showed zero Facebook/Instagram network requests in the captured window. This is a limited browser sample; it does not override the configured integration flag or prove site-wide absence of tracking. Consent, browser controls and initialization paths were not changed. |

## Retained backups and qualifications

Two server-level files outside the discovered current WLF release roots still contain IIPLA Meta credentials matching the running IIPLA configuration:

- `/home/ubuntu/.env.pre-wlf-leftover-clean-20260818075808.bak`
- `/home/ubuntu/.env.pre-wlf-service-separation-20260818075209.bak`

Neither is referenced by the current inspected Docker Compose configuration. Their contents were compared in server memory and not copied or displayed. Their historical ownership/use and every possible script reference were not established. They were preserved; finding credentials in an IIPLA backup does not establish that the current WLF application loads them.

The historical August 19 redacted support attachment reported removal of seven copied fields from a WLF-owned obsolete backup. That is an earlier audit record; this check did not reconstruct or independently prove all historical deployment behavior.

An initial broad topology output hit SSM's 24,000-character response limit on the shared server. The relevant checks were repeated with compact output and scoped comparisons, which completed successfully. IIPLA Staging Server 2 returned a failed SSM command; its full environment was not audited. The conclusions above cover the current inspected WLF production and isolated WLF staging resources, not every AWS resource or backup archive.

Meta still showed the developer account suspended earlier on October 13. The saved October 9 appeal had no visible decision or timeline. This report does not claim restoration, guaranteed policy compliance or successful production Ads Manager API access.

## Evidence and follow-up

Private redacted results: `runtime-data/meta-remediation-audit-20261013/isolation-results.json`, `database-results.json` and `triage-compact.json`. AWS operational identifiers and SSM request metadata stay in gitignored .env files in that directory. No Meta credential value was copied locally. The audit scripts remain available for reproducibility; no deployment build was created.

For a future Meta support update, accurately state that current runtime checks found no cross-product app credential reuse and distinct tracking configuration. Do not say all WLF Meta integration is disabled: production tracking is now enabled. Do not claim the credential mistake is confirmed as the suspension cause or that historical unauthorized access has been ruled out. Meta must identify the offending app/activity and decide the account review.

No additional appeal, message, attachment upload, token generation, credential rotation, database mutation, DNS change, deployment or restart was performed by this audit. PCT, the Menteso OS agents and paused n8n/WLF SDR were not modified.
