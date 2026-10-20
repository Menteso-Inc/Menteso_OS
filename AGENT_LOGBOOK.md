# Menteso Agent Operations Logbook

Last updated: 2026-10-20 (Asia/Calcutta)


This is the operating register for Menteso agents. Credentials are never stored
in this document. Every agent must use its own mailbox identity, secret boundary,
runtime, data directory, and deployment process.

## Safety rules

1. Never reuse one agent's Gmail token by changing only the mailbox address.
2. Never put credentials in Git, this logbook, application status JSON, or email.
3. Back up an agent before deployment and change only that agent's files/service.
4. Test with internal recipients before enabling external delivery.
5. Invoice Reminder Agent stays in test mode until Shweta approves it.
6. PCT remains local; SEO, Accountant, and reminder workloads assigned to AWS stay on AWS.
7. A failure or deployment of one agent must not restart unrelated agents.

## Agent register

### Invoice Request Agent

- Purpose: Receive internal invoice requests, retrieve Zoho details, select the
  approved Wave business, generate/reuse/correct an invoice, update Zoho, and
  reply to the requesting employee with the PDF.
- Mailbox: `invoicerequest@menteso.com`
- Audience: Internal `@menteso.com` employees only.
- Runtime: AWS EC2, `/home/menteso_os/agents/accountant_agent`.
- Trigger: Gmail push plus systemd path activation.
- Service: `accountant-agent.service`; watcher: `accountant-agent.path`.
- Data: `/home/menteso_os/data/accountant_agent`.
- External client delivery: Disabled.
- Current status: Live; 67 automated tests passing as of 2026-08-27.

### Invoice Reminder Agent

- Purpose: Continue weekly collection follow-ups for overdue invoices when no
  Wave flow exists or after Wave's configured reminders have finished. While a
  Wave reminder is pending, Wave owns the invoice and the agent waits.
- Wave business: **Menteso, Inc. only**.
- Mailbox: `accounts@menteso.com` only.
- Audience: External clients after approval; internal test recipient is Shweta.
- Runtime: AWS EC2 under the Accountant Agent repository,
  `/home/menteso_os/agents/accountant_agent/overdue_reminder_agent`.
- State: `/home/menteso_os/data/accountant_agent/overdue-reminder-status.json`.
- Google Cloud project: `Invoice Reminder Agent`.
- OAuth client: `Invoice Reminder Agent AWS` (Desktop application).
- Credential boundary: dedicated OAuth client and refresh token in a dedicated
  AWS secret; must not use Invoice Request credentials.
- Delivery mode: **single_live** in production. Multiple-invoice delivery remains locked.
- Approved design: personal Accounts Team wording; HTML `Pay now` buttons;
  original Wave PDF for one invoice; consolidated statement for multiple invoices;
  weekly cadence; per-customer and global pause controls.
- Approval authority: Shweta; administrative visibility for Shweta, Sajan, and Azam.
- OAuth secret: `invoice-reminder-agent/gmail` in `us-east-2`; required keys and
  mailbox identity were validated on 2026-08-31. EC2 reads it through the
  restricted `MentesoOSInvoiceReminderRole` instance role.
- Current setup task: verify Gmail `users.getProfile`, verify one delivered
  internal test header, and connect replies.

### PCT Agent

- Purpose: PCT-related processing and worksheet/output workflows.
- Runtime: Local Menteso server only.
- AWS state: Disabled; its local availability controls its status on `os.menteso.com`.
- Isolation: Must not be restarted or moved as part of Accountant/Reminder changes.

### SEO Agent

- Purpose: SEO workspaces and their approved sub-agents for Menteso properties.
- Runtime: AWS EC2 under `/home/menteso_os`; isolated from Invoice Reminder changes.
- Workspaces include Patent Drawing Experts, IP Docketers, and Menteso.
- PatentZoom SEO was removed from the active SEO-agent scope as previously directed.
- Isolation: Its container/runtime, credentials, state, and schedules must not be
  changed during Accountant/Reminder deployments.

## Lexmom research build — local development, 2026-10-07

- Display name: **Lexmom Sub Manager**, preserving module identity `lexmom_marketing_agent`.
- First specialist: `prospect_research_agent`, reusable sourced firm/contact research.
- Scope: Solo, small, and mid-size firms across configurable countries; Lexmom Manage profile initially.
- Trigger: On demand; no recurring schedule installed.
- State: ignored `runtime-data/prospect_research_agent/<run_id>/` artifacts/checkpoints/receipts and per-agent private learning.
- Validation: Isolated source, workflow, runtime, manager, and browser-layout checks. Real manager/specialist handoff verified with temporary synthetic data.
- Live status: Dedicated Hunter key **Lexmom Sub Manager** provisioned locally on 7 October and authenticated using the account endpoint; Free plan and 50 remaining credits confirmed. Local LLM/search credentials and conservative call-cost reservations remain unconfigured. Research workload execution has not been tested live.
- External marketing: Email outreach, ads, calls, and other later specialists remain disabled.
- Deployment: No AWS/production deployment or changes to unrelated agent runtimes.

## 2026-10-07 — Lexmom production rollout requested; authentication blocked

- Approval: User requested deployment and a live production run of the existing research specialist.
- AWS preflight: CLI reported an expired login session. Started `aws login`; browser sign-in is pending. No remote command succeeded and no server files or services changed.
- Browser control: Provider navigation and browser inventory timed out; dedicated LLM/search provisioning could not proceed.
- Local preparation: Added dedicated provider credential selection in `shared/llm.py`, template slots and regression tests; a blank declared dedicated key cannot fall back to a shared credential. Updated the specialist setup guide.
- Pilot profile: `agents/prospect_research_agent/live_pilot.json`, live mode, target five firms, ten candidates, three searches, fifteen model calls, three verification calls, five-minute deadline, and $1 reservation ceiling. No country restriction; initial search queries cover US, India, and UK.
- Validation: Existing 91 tests passed before this change; the changed runtime suite then passed all 25 tests, including two additional credential-isolation tests. Pilot schema and whitespace checks passed.
- Remaining: Renew AWS login, provision dedicated model/search access, configure conservative provider reservations, inspect the actual server deployment, back up the target, deploy only Lexmom, and evaluate the live pilot.
- Deployment/backup/rollback: No production mutation or backup created. No rollback required on AWS. Local additions remain uncommitted.
- External behavior: No outreach, advertisements, calls, or provider research workloads executed.

## Dashboard register

- `server.menteso.com`: infrastructure/server status and authorized remote access.
- `os.menteso.com`: agent status and operational controls.
- Accountant Agent view contains two switches:
  - Invoice Request Agent
  - Invoice Reminder Agent
- Invoice Reminder view shows customer, email, invoice numbers, invoice count,
  total due, oldest due date, workflow status, and pause/resume controls.

## Change history

### 2026-08-27

- Deployed WLF-branded invoice header while preserving the Wave invoice body.
- Added inbox-only processing, self-sent-message protection, and safe OpenAI outage handling.
- Added Zoho attachment content deduplication; identical PDFs are not reattached.
- Built Invoice Reminder test workflow for Menteso, Inc. overdue invoices.
- Added single-invoice PDF and multi-invoice statement attachments.
- Added weekly scheduling logic and customer/global pause controls.
- Added personal HTML reminders with payment buttons.
- Added Invoice Request / Invoice Reminder dashboard switch and reminder table.
- Confirmed the previous AWS Gmail identity still belongs to Invoice Request;
  prohibited its use for reminder delivery.
- Created dedicated Google project/client externally: `Invoice Reminder Agent` /
  `Invoice Reminder Agent AWS`; OAuth authorization is pending.

## Required deployment record

For every future change, append:

- Date/time
- Agent
- Requested change
- Files/services modified
- Backup location
- Tests performed and results
- Deployment result
- Rollback instructions
- Person approving external behavior

### 2026-09-02 15:22 IST — Invoice Reminder ownership and dashboard

- Requested change: Let the agent own overdue invoices when Wave has no reminder
  flow, hand ownership back while Wave reminders are pending, resume after Wave
  finishes, and stop when an invoice is no longer overdue.
- Files/services modified: Invoice Reminder Agent, Accountant dashboard adapter,
  and the `os.menteso.com` reminder dashboard UI.
- Backup: `/home/menteso_os/backups/overdue-dashboard-20260902T095146Z`.
- Tests: 77 Accountant service tests passed; JavaScript syntax and Python compile
  checks passed; production read-only scan reconciled 70 overdue invoices.
- Deployment: Commit `1641e0b`; `menteso-os` container rebuilt healthy; hourly
  reminder timer remains active. Live scan showed 3 Wave-owned, 65 agent-owned,
  2 missing-email invoices, and 20,083.03 USD agent-owned collection value.
- Rollback: Restore the four production files from the backup directory, rebuild
  only the `menteso-os` container, and leave unrelated agents untouched.
- External behavior approval: Requested directly by the user in the deployment conversation.

### 2026-09-02 — Agent-attributed collections metric

- Requested change: Replace agent-owned outstanding value with payments actually
  received after an agent reminder.
- Files/services modified: Invoice Reminder activity monitor, Accountant dashboard
  adapter, and the consolidated `os.menteso.com` collections card.
- Tests: 77 Accountant service tests passed; JavaScript syntax and Python compile checks passed.
- Attribution rule: A Wave payment counts once when its creation timestamp is later
  than that invoice's first recorded live agent reminder.
- External behavior: No change to recipients, cadence, or delivery permissions.

### 2026-09-07 11:06 IST — Reminder notifications and outbound pause

- User requested removal of accounts@menteso.com from client-reply and payment notification recipients, and a pause pending schedule redesign.
- Changed services/accountant_agent/overdue_reminder_agent/agent.py and production overdue_reminder_agent/agent.py: activity notifications now go only to Sajan, Shweta and Azam.
- Set production overdue-reminder-status.json global paused=true. Hourly timer retained so activity monitoring continues; both live reminder senders use the global pause guard.
- Backup: /home/menteso_os/backups/reminder-notifications-pause-20260907T053617Z (agent.py and state).
- Validation: 20 reminder tests passed in production; syntax parsed before write; verified persisted pause and recipient list. No email was sent for testing.
- Deployment: production source patched in place; next scheduled process loads it, no service restart required.
- Rollback: restore agent.py from backup to revert recipients. Resume only after the user approves the revised schedule by setting global paused=false; do not restore old state over newer payment/reply history.
- External behavior approval: user requested notification recipient reduction and outbound pause in this conversation.

### 2026-09-07 11:20 IST — Fixed Monday reminder schedule

- User requested all 62 agent-owned invoices in the first batch at 20:00 IST on 7 September, then every Monday at 20:00 IST.
- Live read-only Wave scan: 62 invoices / 51 customers; 5 eligible customers covering 6 invoices already paused. Existing customer pauses retained pending the user's answer; 56 invoices / 46 customers currently sendable.
- Replaced rolling seven-day eligibility with anchored weekly slots when weekly_schedule is configured; initial batch resets old due dates, same-slot duplicates are skipped, subsequent dates do not drift with batch duration. Sends are allowed only during the first hour of the Monday slot.
- Weekly timer: Monday 14:30 UTC, no random delay, one-second accuracy, no missed-run catch-up. First three occurrences verified: 7, 14 and 21 September 2026 at 20:00 IST.
- Separate hourly timer retains reply/payment monitoring and reconciliation. Shared flock serializes the two scheduled workers. Weekly worker checks activity and payments before singles and consolidated multi-invoice reminders, with previous 25/10 limits removed.
- Global pause released under the new schedule. Customer pauses and original send/payment history preserved. No client reminders sent during deployment.
- Files: overdue_reminder_agent/{agent.py,schedule.py,scheduled_run.py}, tests/test_reminder_calendar.py, infra/invoice-reminder-{single,monitor}.{service,timer}; production state weekly_schedule and next_follow_up fields.
- Backup: /home/menteso_os/backups/reminder-weekly-20260907T054823Z/original.
- Validation: 24 reminder/calendar tests passed on staged production code; systemd unit validation passed; timers enabled and next occurrences verified.
- Rollback: first globally pause reminders and stop both reminder timers; restore agent.py and original single service/timer from backup, disable monitor timer, reload systemd. Remove weekly_schedule without overwriting newer payment/reply history. Resume sending only on user instruction.
- External behavior approval: user explicitly requested Monday 20:00 IST sends beginning today.

### 2026-09-07 — PCT AI contact verification

- User requested AI reasoning for OCR mistakes, reuse of the SEO OpenAI API key, and configurable wanted/unwanted data rules.
- Added OpenAI Responses image verification with strict structured fields, document page evidence, role/domain/fax filtering, ambiguity review and local PDF/audit retention. Shared OPENAI_API_KEY is reused; key was not copied or printed.
- Integrated both sequential and parallel extraction. Applicant-name cache is bypassed; verification cache is scoped to PDF content, model, metadata and rules. Legacy progress cannot bypass verification. Reports retain 13 original columns and add verification/review/evidence columns.
- Added contact_rules.json for instructions and teaching examples, plus AI_VERIFICATION.md and PCT environment placeholders. User-specific include/exclude rules are still pending. Current defaults allow applicant, agent/attorney, inventor; exclude office contacts and fax; multiple contact owners require review.
- Backup: C:/Users/Administrator.MENTESO/pct-ai-backup-20260907-115313 (original agent.py, pipeline.py, pdf_extractor.py).
- Validation: 16 automated tests passed; Python compilation and diff whitespace checks passed. Synthetic image-only PDF live check was attempted, but OpenAI returned HTTP 429, code credit_balance_exhausted. Secure comparison confirmed AWS SEO and local PCT share the same key. No successful live AI extraction is claimed and no bulk scrape was launched.
- Added preflight API check to stop before scraping on unavailable credit/configuration. No raw OCR fallback is silently accepted while AI mode is enabled.
- Files installed at C:/sites/Menteso_OS/agents/pct_agent and mirrored to Menteso_OS_publish/agents/pct_agent; unrelated live services were not restarted.
- Rollback: restore the three original Python files from the backup; PCT_AI_VERIFY_ENABLED=false explicitly returns extraction to legacy OCR mode if desired. Preserve generated reports and audit evidence.
- Outstanding: restore OpenAI credit; run live synthetic and representative PDF accuracy checks; apply user's exact data-selection examples before production-scale use.

### 2026-09-07 ? Match Aneeq PCT sheet columns

- User requested exact column parity with Downloads/PCT Data(Aneeq).xlsx. Both worked and not-found report generators now use its 12 exact headings and order, including Agent Name and Priorty Date. Removed Date, Deadline and extra AI audit columns. Researcher and priority_date values map to K/L when provided; missing values remain blank. AI evidence remains in local audit files.
- Backup: C:/Users/Administrator.MENTESO/pct-sheet-backup-20260907-155948. Files: pct_agent/agent.py, test_ai_verifier.py, AI_VERIFICATION.md; live and publish copies synchronized.
- Validation: 16 tests passed; generated both report types and compared all headings and column counts directly against the supplied workbook. Existing historical reports not rewritten.
- Rollback: restore the three files from this backup.

### 2026-09-07 — PCT contact ownership and source-field preservation

- User clarified that WIPO already supplies applicant/patent fields and employees enrich agent contacts; requested prevention of mixed applicant/agent names, emails and phones.
- Updated visual extraction schema to carry contact block, owner, role, source section and entity type on every field. Current policy selects agent/attorney/representative contacts; applicant/inventor substitution is prohibited. Question about the older document's alternative selection rule was left open; latest explicit agent-enrichment clarification used as default.
- Select only one contact block; reject mixed owners/roles, names inconsistent with selected owner, ambiguous agent sections and multiple contact blocks. Missing fields stay blank. Country comes from the selected source contact country, normalized with pycountry, never the application-number/phone prefix. Cat values match Aneeq: Slf, Corp, Ind; classification uncertainty stays blank. No Info only for a completed review finding no usable agent contact; Repeated/Uns not guessed.
- Input reader maps source columns by explicit heading, supports WIPO and Aneeq headers, refuses missing required applicant/title/application/publication headers, and preserves source Applicant plus researcher/priority-date metadata. Report retains exactly Aneeq's 12 columns. Agent Name can only use identified agent-role metadata.
- Added four synthetic teaching examples, updated cache revision to invalidate prior extraction policy results, and included page-limit setting in the revision.
- Backup: C:/Users/Administrator.MENTESO/pct-contact-ownership-backup-20260907-172453. Changed PCT agent.py, pipeline.py, ai_verifier.py, contact_rules.json, tests, AI_VERIFICATION.md; added pycountry and explicit pydantic requirements. Live local files mirrored into publish checkout without overwriting unrelated changes.
- Validation: 32 tests passed, including both result builders and exact 12-column output mapping, source-field preservation, country/category and negative mixed-contact cases. Successfully read Aneeq's 489 rows and an archived WIPO XLS with 4,999 patent rows. Compilation and whitespace checks passed.
- Live OpenAI preflight still fails: HTTP 429 credit_balance_exhausted. No successful live extraction or accuracy claim; no bulk scrape launched. Restore credit and validate representative source PDFs before production-scale work.
- Rollback: restore backed-up PCT files and reverse only the two added dependency declarations if desired; preserve audit evidence and existing output sheets. No Invoice Reminder/PCT database changes or unrelated service restarts.

### 2026-09-07 - Git handoff and corrected PCT requirement

- User requested pushing all session work for a teammate to pull and continue.
- Correction superseding the previous PCT policy entry: extracted email and phone cannot automatically be assumed to belong to the agent. The current agent-only policy remains unfinished and must be revised with ownership evidence, selection examples, report mapping and tests. Agent Name must still identify an actual agent.
- Updated CODEX_HANDOFF.md and PCT AI_VERIFICATION.md to distinguish implemented behavior from the corrected requirement and record the OpenAI credit blocker. No successful live AI validation is claimed.
- Publishing source, tests, configuration templates and operational notes only. Secrets, production customer state, reference workbooks, source PDFs, generated reports and backups remain outside the public repository.
- This is a source handoff; no service restart or bulk PCT run is part of the push. Prior deployment and rollback records remain above.
- Handoff validation: 32 PCT tests and 24 reminder/calendar tests passed locally after installing missing test dependencies; staged whitespace checks and credential-pattern checks passed. Only the prepared publish checkout is committed; unrelated historical local-server changes remain untouched.

### 2026-10-08 - Preserve deployed PCT pipeline for teammate deployments

- Requested change: ensure a teammate's deployment does not overwrite the local PCT improvements or previously collected results.
- Source handoff: `pct-deployment-handoff-20261008`, prepared from current `origin/main`, preserving upstream Accountant/dashboard changes. Includes the deployed single-browser overlap, bounded parallel PDF verification, durable checkpoints/resume, atomic Excel writes/control-character fix, and dashboard ETA/reconnection changes.
- Files: PCT agent, verifier scheduling, browser failure reporting, overlap/parallel/resume modules and tests; focused dashboard changes; configuration examples/routing metadata; validation, handoff, keeper and dashboard patch scripts; this logbook and `CODEX_HANDOFF.md`. Added refusal guards to the legacy deploy script and its GitHub workflow before Git/service operations when the PCT keeper task exists.
- Tests: 100 PCT regression tests passed in an isolated checkout; JavaScript syntax and real dashboard reconnect function checks passed. Read-only local preflight reported no active agent runs during preparation.
- Deployment result: source preservation only; no production files, settings or services changed by this handoff. Local PCT and AWS frontend changes were already deployed during the October 7-8 work. Publishing a feature branch does not update `main`; teammates must merge it before deploying.
- Private backups: `C:\ProgramData\Menteso\pct-pipeline-handoff-20261007` and `C:\ProgramData\Menteso\pct-parallel-handoff-20261008`. Collected data, original sheets, PDFs, runtime memory and secrets remain outside Git.
- Rollback: restore only the target source/configuration after an idle check and any required validated handoff; preserve newer runtime data. Do not run the legacy PM2 deploy script or force-reset the local PCT checkout as part of unrelated AWS deployments.
- External behavior approval: user requested source/deployment protection. No external email, bulk run, merge to `main` or service restart was performed as part of preparing this handoff.


### 2026-10-07 - Lexmom isolated AWS deployment and live pilot

- User authorized AWS deployment and reuse of existing AWS LLM/search credentials; the Hunter key remains dedicated to Lexmom Sub Manager. Credential values were not printed or downloaded from AWS.
- Installed the manager and Prospect Research and Qualification specialist under /home/menteso_os/agents/lexmom_sub_manager with a dedicated environment, private state and on-demand lexmom-research.service. No timer or outreach agent was enabled. The public dashboard is not yet connected to this worker.
- OpenAI workload and Hunter account authentication passed. SerpAPI authenticated but has zero searches left, so live pilots used explicitly supplied firm URLs; automatic discovery remains unvalidated.
- Fixed CrewAI writable storage, supplied detail-URL preservation, source HTTP 403 classification, model input token accounting, and exact source-citation instructions. All 78 scoped server tests passed.
- Five-firm pilot: five researched, zero qualified. Final focused run 3a9e6b09fb3c42dd9b4459e69f389438: one researched, zero qualified, no contacts, no email verification. Accepted firm name, five attorneys and practice evidence; missing/unsupported country evidence kept the record in needs_research. Structural checks passed, but business result is partial.
- Final focused run took 13.208 seconds with four page requests and one model call; $0.01 was reserved against a $0.25 ceiling, not measured billing. Current input remains this focused profile. Historical results and learning were preserved.
- Verified process exit zero and normal inactive oneshot status. Existing shared Menteso container remains healthy with unchanged 2026-10-05 start time; unrelated agents were not restarted.
- Outstanding: search quota, representative grounded qualification, real email verification, and dashboard integration. Production readiness is not claimed. See docs/lexmom_sub_manager/DEPLOYMENT.md for operations and rollback.


### 2026-10-07 - Lexmom dashboard connected and verified-contact demo

- Connected the isolated AWS worker to the authenticated public dashboard, renamed the visible agent to Lexmom Sub Manager, and enabled profile editing, live status, cancellation, grounded results and manifest-checked JSON downloads. The original registry/package ID is retained for compatibility.
- Added a separate loopback dashboard service/tunnel and narrowly routed Caddy paths. Existing authentication and unrelated agent APIs stay on the original server; no shared Menteso agent container restart occurred.
- Installed the user's new dedicated Dev Team SerpAPI Free key in Lexmom's ignored environments using encrypted transfer. It had 250 searches at provisioning. Other agents' search credentials are unchanged; no paid plan purchased.
- Hardened source/model budgets, exact source URLs, country normalization, literal published-inbox capture, official-site classification, transient search fallback, and recovery after required source evidence is rejected. Directory/news records cannot qualify as official firms. Email validity does not grant outreach permission or establish a buyer role.
- Validated 110 distinct automated tests locally across the scoped suites, including the final grounding recovery case; 92 specialist/runtime/dashboard tests passed on the server. Existing CrewAI deprecation warnings remain.
- Successful live supplied-site demo 2b83d6f7ac4b47a2924cf7e27a5c4daa: one real US firm, five attorneys, one published inbox returned valid by Hunter (provider date 2026-09-20). Took 27.785 seconds, three model calls, one verification and zero searches; $0.08 reserved, not measured spend. Verified UI result and downloaded/parsed the JSON artifact.
- Broad and targeted discovery tests did not establish reliable qualification yield: third-party/unrelated results and intermittent search timeout/503 errors remain acceptance limitations. All unsuccessful runs are preserved. Do not present the supplied-site demo as autonomous client acquisition or full production acceptance.
- Documentation: docs/lexmom_sub_manager/DEMO.md, demo_profile.json and DEPLOYMENT.md include demonstration scope, service operations, rollback and remaining acceptance criteria. No outreach, ads, calls, purchases or recurring research were enabled.

- Follow-up reliability finding: a repeat on GPT-4o-mini remained partial because of a bad country quote. Fixed provider temperature (explicit zero), tested its configuration, and switched the isolated deployment to GPT-4o with a $0.10/model-call reservation under the same $1 cap. Two subsequent live runs (3441f57193a34790b9d864f6566106bc and a01d4efd398d4210a8831fad17346c9b) each qualified the firm and returned the inbox valid on one extraction attempt, in 15.747 and 17.302 seconds. Both reserved $0.15; no measured billing claim. Final provider check: 245 SerpAPI free searches remaining. Historical partial results are retained. One-firm repeatability does not close the broad-discovery acceptance gap.


### 2026-10-07 - Saved prospect table and credit conservation

- User asked to preserve search credits for the full test and display records in a table. Replaced the Lexmom result cards with a semantic table containing row number, firm/website, country, attorney count, qualification, published email, verification/date and expandable evidence/contact details.
- Counts explicitly describe the current run: records, unique firms, qualified, needs research, distinct published emails and valid emails; excluded count remains in the table caption. A supplied-site/search-discovery label prevents presenting seeded tests as discovered prospects. Repeated runs are not accumulated as new leads.
- Added the saved provider balance (245 at the previous check) and a notice that reading/refreshing saved records consumes no search or verification credits. This UI-only update ran zero search/model/Hunter workloads and did not start the research worker.
- Deployed static assets only to the isolated dashboard, with source backups under releases/before-results-table-*. JavaScript syntax and diff checks passed. Verified the real saved row, counts, expandable facts and contact associations in the browser, and independent horizontal table scrolling at 390px. Existing services were not restarted.


### 2026-10-07 - Saved JSON targeting and compact Lexmom dashboard

- User requested removal of the long explanations and targeting form. Replaced them with a compact targeting summary, saved credit balance, Run/Stop/Refresh controls, results table and collapsed idle execution log.
- Added agents/lexmom_marketing_agent/research_profile.json as editable non-secret targeting configuration. Manager default runs and dashboard runs reload/validate it each time; the isolated HTTP endpoint accepts only empty run requests and rejects browser targeting overrides. Missing, malformed or non-live saved configuration blocks execution. Credentials and unit-cost settings remain in .env.
- Saved profile targets global solo/small/mid-size law firms for Lexmom Manage, with the existing provisional 1-50 attorney range and buyer roles. Removed the demo website from the default; max_queries is 1 to conserve credits. Other bounded worker limits remain; this change does not establish discovery quality or complete milestone one.
- 28 manager/dashboard checks passed locally, including fresh configuration reads, invalid config, rejected browser overrides, empty-request dispatch and form-free rendering. No research/provider workload was executed for this update.


### 2026-10-07 - Lexmom business overview and agent chips

- Split the workspace into Dashboard and Prospect Research chips. Dashboard has total spend, total revenue and distinct qualified lead counts; the research table stays in the specialist view. A single Run all agents control dispatches the existing manager and its one implemented specialist. No future agent is represented as executable.
- Added a read-only saved-run summary: deduplicates domains and child handoffs, excludes fixtures/unvalidated leads, includes failed-run reservations separately, flags incomplete history. Billed spend/revenue remain unknown until tracking is connected; reservations are never presented as actual spend.
- 31 offline checks passed, covering financial semantics, historical deduplication, tab navigation, research evidence, blocked execution and duplicate-click dispatch. No research or provider workloads started.

### 2026-10-09 - Preserve PCT handoff while updating Lexmom development

- Integrated draft PR #9 head `7f719b3f1b79` into the separate local branch `codex/lexmom-pct-sync-20261009`, preserving all Lexmom changes. Shared main and production were not changed.
- Resolved the logbook conflict with both histories retained. Combined dashboard passes PCT reconnection checks, syntax checks, 100 PCT tests and 116 Lexmom/shared tests in an isolated source-only copy.
- Recovery stash `6b9ad11dc657695f7188075f9d1ec89a50b6fa00` retained; original environment/runtime inventory unchanged. No live restart, provider calls, deployment or PCT AWS activation.
- Full record and cleanup exception: docs/lexmom_sub_manager/LOCAL_SYNC_20261009.md. Automatic approval review blocked removal of the 5.4 MB disposable verification copy; it remains isolated and inactive.

### 2026-10-09 - Repair Prospect Research discovery locally

- Added retained/ranked search metadata, bounded directory-to-website resolution, targeted follow-up pages under the existing page cap, recent compatible live-history skips, and candidate outcome/reason records exposed in the specialist results view. Partial grounded records survive budget/cancellation; earlier search candidates survive a later search failure.
- Added configurable 30-day reuse window and legacy-profile resume compatibility; preserved evidence/identity requirements, provider caps and PCT changes. Modified only Prospect Research, its JSON profile, focused Lexmom result rendering/tests and documentation.
- Validation: 131 scoped offline tests passed, including 15 new real-workflow simulations; the additional legacy resume and excluded-directory cache tests passed, along with the updated cancellation audit check (133 distinct tests verified). JavaScript syntax/PCT reconnection/whitespace checks passed. Existing CrewAI deprecation warnings remain.
- Deployment: none. No credits spent, no external research or messages, no live service restart, and no changes to PCT runtime or its deployment guards. No disposable deployment bundle was created. Prior cleanup exception remains recorded in LOCAL_SYNC_20261009.md.
- Details and reviewable first-live-test limits: docs/lexmom_sub_manager/DISCOVERY_REPAIR.md. Broad discovery acceptance remains pending a bounded live run after the handoff requirements are met.

### 2026-10-09 - Merge PCT handoff and deploy Lexmom discovery repairs

- User explicitly authorized reviewing and merging PR #9 if checks passed. Reviewed the exact verified head, found no merge-blocking issue and merged as `11f2ac0f6042a9cf0bc7f10bb56f332b2b10730f`. Local integration fast-forwarded with uncommitted Lexmom changes preserved. Automatic workflow failed on missing SSH secrets before any remote action; deployment guards remain intact.
- Activated seven scoped source/profile/UI files through the isolated AWS Lexmom runtime after staging verification. Preserved actual served PCT/custom dashboard features, environment, memory and saved state. Restarted only the Lexmom dashboard. Shared container retained its original start time and PCT stayed disabled on AWS.
- One bounded autonomous pilot: `fac05e76039c4c0d9b2733558385153a`, 45.665 seconds, five researched records, zero qualified leads, one search, nine model calls, zero verifications, $0.95 reservations (not measured billing). Search balance reconciled 245 -> 244. Structural checks passed; business acceptance failed.
- Fixed the observed institutional/directory filtering and repeated empty/blocked-source work; tightened saved query phrases. Three additional regressions plus modified permanent-403 expectation passed. Follow-up AWS suite: 136 tests, 135 passed and one browser-dependent skip; all 53 targeted local tests passed. Follow-up deployed without a second live workload; yield remains unproven. Browser visual QA awaits sign-in.
- Release/rollback/cleanup receipt: docs/lexmom_sub_manager/RELEASE_20261009.md and CLEANUP_20261009.json. Removed only exact disposable transfer/staging files; preserved rollback backups, runtime data, source, credentials and the earlier blocked-cleanup exception. No outbound marketing or recurring work enabled.

### 2026-10-09 - Migrate and pause n8n / WLF SDR

- Owner explicitly requested moving n8n/WLF SDR to Menteso OS, preserving keys for future Lexmom reuse, pausing API consumption, and adding both to os.menteso.com.
- Stopped all source n8n containers and disabled restart policies and the backup timer. Transferred a private 705 MB rollback archive, including logical/cold database backups and all mounted data, to Ohio. Restored 38 workflow records and 11 credentials; offline decryption and dotenv round-trip checks passed. No provider calls or workflow executions were used for verification.
- Destination services are created but stopped, with paused Compose profiles, restart disabled, and internal-only networking. Source Compose is also gated by paused profiles. Shared OpenAI keys remain valid; this prevents these workloads from making calls, not unrelated consumers.
- Added authenticated n8n Automation / WLF SDR dashboard entries and rejected execution endpoints. Twelve tests passed locally and on AWS; public auth and asset checks passed. Shared Menteso container, LinkedIn database and local PCT runtime were preserved. Browser visual QA requires sign-in.
- Details, rollback paths, credential handling and limitations: docs/lexmom_sub_manager/N8N_WLF_MIGRATION_20261009.md. No secret values were displayed or committed, and Lexmom's active provider configuration was not overwritten.
- Final checks: all six destination image IDs match the original source and are pinned by digest; all source/destination containers remain stopped. The old n8n URL returns a deliberate HTTP 503 pause message. Removed nine exact disposable local operation/deployment scripts (96,428 bytes); local free space measured 10,265,436,160 -> 10,265,550,848 bytes. Full receipt: N8N_WLF_CLEANUP_20261009.json; rollback backups and live restored data retained.

### 2026-10-09 - Validate and repair first Lexmom specialist

- Deployed evidence-follow-up, canonical redirect, business JSON-LD, publisher-contact, rate-limit, best-record and query-preservation repairs to the isolated Lexmom runtime. 148 local tests passed; AWS passed 147 and skipped one browser-dependent test. Shared container start time unchanged; PCT and n8n/WLF preserved.
- Three bounded independent discovery runs used three search credits (244 to 241), 11 model calls, no email verifications and $1.25 configured reservations, not measured billing. None produced a qualified firm. Latest run returned one excluded directory record; seven URLs were rejected and another directory blocked. Milestone one remains incomplete; dashboard retains Live pilot status.
- All three required dedicated provider keys are present and usable for the checks performed; no new key needed. Updated quota snapshot; preserved older Hunter verification timestamp. Worker idle, no schedule/outreach enabled.
- Verified the authenticated production table visually. Full run IDs, remaining acceptance work and cleanup evidence: docs/lexmom_sub_manager/RESEARCH_VALIDATION_20261009.md and RESEARCH_CLEANUP_20261009.json. Source remains uncommitted; rollback and private data preserved.
- Cleanup: AWS removed both verified staging directories (3,160,068 file bytes); free space 78,478,172,160 to 78,481,805,312. Automatic approval review blocked the nine-file local disposable-script cleanup; no deletion occurred, no bypass attempted. Exact retained paths are in the cleanup receipt.

### 2026-10-09 - Audit existing Lexmom Meta assets before Ads Manager implementation

- Read-only browser audit located Menteso-owned LexMom New, LexMom Facebook Page, @thelexmom Instagram, LexMom Group and LexMom Website Data. Production website HTML/JS matches this active Pixel; Meta confirms Pixel and CAPI activity. The older LexMom portfolio's inactive Pixel is a separate asset, not evidence that the production Pixel is wrong.
- Inspected legacy draft campaign/ad set/ad, Menteso Main's remote-paralegal campaign and draft ads, and the original shared account. The shared account's 18 campaigns returned no campaign-name match for Lex over Maximum dates; this does not rule out differently named Lexmom campaigns.
- Existing shared token failed OAuth validation; migrated WLF token works for its own limited scopes but lacks ads_read/ads_management and exposes no Lexmom Page. No usable Lexmom campaign-management token verified. No credential generation or access changes made.
- Saved discovered identifiers in a gitignored local audit .env with execution/publication disabled and credential fields blank. Recorded event counts, malformed historical event, app/access gaps and a concrete setup-only build proposal in docs/lexmom_sub_manager/META_EXISTING_ASSET_AUDIT_20261009.md. No implementation/deployment, new ad spend, campaign mutations, workflow restart or PCT changes. Build-plan approval remains required by AGENTS.md.

### 2026-10-09 - Meta readiness follow-up and developer suspension diagnosis

- Read-only checks confirmed LexMom New billing is configured in USD, no balance due, and Meta's displayed daily spending cap is $26.95. No payment/spend changes made. Audience and conversion settings remain incomplete; shared business is Unverified. Ad-account contact settings also show a pending email confirmation; no contact values copied to project files.
- Existing-app access redirects to a developer restriction. Official Account Status explicitly confirms developer-account suspension under Platform Term 7.e.i.2 and displays an August 19 appeal record; no specific offending app/activity or prior decision is visible. Do not treat this as only an OAuth scope issue or evade the restriction.
- At user request to resolve access, prepared a factual clarification/review appeal in the official form, preserved screenshot evidence and left the tab open. No submission or attachment upload occurred; explicit authorization requested before sending to Meta. No new keys obtained and no claim of production readiness.
- Updated META_EXISTING_ASSET_AUDIT_20261009.md. Existing assets, secrets, apps, production services, PCT and paused workflows preserved. No deployment or disposable build outputs created.

### 2026-10-09 - Submit authorized Meta developer appeal

- User explicitly approved sending the prepared appeal. Submitted once and confirmed Meta's submission dialog. Reload verified the new response persists as disabled/read-only fields.
- Account remains suspended under Platform Term 7.e.i.2; no case number or ETA displayed. No new attachments, permissions, credentials, campaigns, spend or service changes.
- Saved submission screenshot under private runtime-data/lexmom-ads-audit/developer-appeal-submitted.png and updated the existing Meta audit document. Kept the submitted record open for the user.

### 2026-10-13 - Verify current IIPLA / WLF Meta credential separation

- User requested checking AWS after reporting the environment mix-up fixed. Refreshed the existing Devteam AWS CLI session and performed read-only SSM inspection of current WLF production on IIPLA Main Server and isolated WLF staging.
- Running WLF web/API/jobs have no Meta app/client credential or token; their tracking identifiers differ from running IIPLA. Eleven production WLF env files and three isolated-staging env files passed the scoped credential/identifier checks. Production tracking is enabled; isolated-staging integration flags are off.
- WLF aggregate-only database checks in read-only transactions found zero Meta marketing connections/OAuth sessions/Facebook or Instagram social-account records. Production database Pixel matches its WLF runtime and differs from IIPLA. Raw credentials, identifiers and customer data were not returned.
- Two older server-level IIPLA credential backups remain outside the current WLF release roots and are not referenced by inspected Compose configurations. Preserved them; no historical use or blanket server-wide absence claimed. Separate IIPLA Staging Server 2 command failed, limiting coverage there.
- Saved findings, current-vs-historical distinctions and verification limits in docs/lexmom_sub_manager/META_REMEDIATION_CHECK_20261013.md. No production changes, restart, provider API workload, token rotation or additional Meta appeal. No deployment cleanup required because no deployment/build was created; private audit evidence retained.

### 2026-10-13 - Record research-to-email requirements and zero-spend build proposal

- Owner selected separate Manage/Launch campaigns, named contacts plus generic firm inboxes with distinct messages, and requested our recommended automated flow. Owner wants free operation and does not know of an existing domain mailbox; proposed meetlexmom.com@gmail.com remains unverified and is a Gmail address rather than a domain mailbox.
- Read-only DNS found no meetlexmom.com MX or SPF record, with DMARC present. SES checks found an existing verified lexmom.com production identity in us-east-1; no meetlexmom.com identity in the three inspected regions. Provider availability does not authorize researched cold outreach: current Gmail policy prohibits unsolicited commercial mail and AWS AUP prohibits unsolicited mass email.
- Saved concrete local repair/draft-only build plan and remaining sender/offer/live-channel prerequisites in docs/lexmom_sub_manager/EMAIL_PIPELINE_REQUIREMENTS_20261013.md. Proposed zero additional spend blocks paid inference/overages and pauses at free quota exhaustion; current OpenAI research is paid. Proposed cap is 10 total daily emails across both products, including one follow-up, with initial sample review and continuous supervised workers.
- No specialist code, sending, DNS/provider changes, paid API requests, recurring workers, deployment or service restart in this requirements pass. New-agent implementation awaits the explicit plan approval required by AGENTS.md. Documentation whitespace validation passed; no build/deployment leftovers created.

### 2026-10-13 - Define two-product lead qualification and requested mailbox integration

- Owner asked how Prospect Research should collect evidence and qualify companies/people for Manage, Launch or both, then supply grounded personalization. Owner selected hello@meetlexmom.com for sent mail, replies and demo notifications.
- Public browser checks rendered both product pages and the demo form, which already supports product choice, role, size, stated need and permission to contact about that request. No form submitted and no backend delivery claimed. Current agent schema has one product label/basic fit; independent product assessments and inbox integration remain proposed.
- Existing delegated GoDaddy Email & Office session showed an empty Users list; Add user reported no accounts. Closed the dialog without continuing. No mailbox created, purchase, credential entry, DNS change, send, code or production mutation.
- Added docs/lexmom_sub_manager/LEAD_QUALIFICATION_DESIGN_20261013.md and linked it from the requirements. It separates evidence-backed firm/product fit, contact readiness, sending eligibility and expressed intent; includes duplicate control, generic/named message variants, mailbox options and durable demo-event notification design. Documentation whitespace checks passed; no deployment leftovers created.

### 2026-10-13 - Implement and deploy two-product research pilot

- Owner explicitly approved implementing the existing Prospect Research pipeline for Manage and Launch. Added separate evidence-based assessments, primary-product routing, named/generic briefs and contact readiness/hold reasons. Versioned JSON profiles remain editable; public fit is not buying intent and sending stays disabled.
- Added transactional canonical inventory/query rotation, freshness and saved-candidate enrichment. The saved profile uses rules extraction, zero model calls and free-provider checks that stop on paid/unknown/exhausted plans. No new key required and no credential values displayed.
- Local suite: 170 passed. AWS staged suite: 169 passed and one Node/browser-dependent skip. JavaScript syntax, PCT reconnect and whitespace checks passed. Activated only scoped isolated Lexmom source and two actual served rendering functions, preserving unrelated/PCT custom JavaScript. Dashboard active, research idle; shared container retains its October 5 start time, PCT local/AWS-disabled and n8n/WLF paused.
- One independent free search: six firms, 15 published emails, zero fully qualified firms/research-ready contacts; zero model/verification requests. Saved-candidate enrichment spent no further search credits. Search allowance reconciled 241 to 240. Country/attorney-count/roles remain unresolved, so business acceptance is not passed and the dashboard stays Live pilot.
- Fixed deep-page brand extraction and caught New Jersey being mistaken for Jersey. Added regressions, withdrew ambiguous country evidence, retained original data snapshots and reconciled manager/status/inventory metadata. A metadata helper initially used system Python without Pydantic after source activation; recovered with the isolated virtualenv without another search or shared-service restart. Runtime .env unchanged; legitimate research memory retained.
- Mail checks: GoDaddy has no available mailbox accounts, available Zoho CRM session shows Mail plan setup rather than a configured tenant, and menteso.com MX routes Google. Actual mail administrator/plan still needed. Recommended existing-tenant domain alias if supported; SES is optional transactional transport rather than an Inbox/Sent mailbox. No email, DNS, purchase, OAuth grant, demo-backend deployment or continuous schedule enabled.
- Release/limitations: docs/lexmom_sub_manager/RELEASE_20261013.md; mailbox findings: MAILBOX_OPTIONS_20261013.md. Source remains uncommitted. AWS cleanup removed exact staging and two transfer fragments, 770,167 file bytes; measured free space 78,466,179,072 to 78,467,080,192 bytes. Rollback/evidence/live data preserved.
- Automatic approval review rejected local disposable-file removal with "blocked by policy" before execution. No bypass/retry deletion. Nineteen exact retained targets (280,517 file bytes) recorded in CLEANUP_20261013.json; measured local free space 12,760,743,936 bytes. No task preview process or managed worktree needed cleanup.

### 2026-10-13 - Audit all enabled SES regions for Lexmom

- Owner corrected the reply/demo destination to mail@lexmom.com and selected AWS SES for future hello@meetlexmom.com sending; explicitly requested SES inventory before setup. Read-only AWS account identity confirmed against known Menteso OS ownership; all 17 enabled regions checked.
- Found one unique lexmom.com domain registered and verified in us-east-1/us-west-2, DKIM SUCCESS, production sending enabled/healthy. Zero separately verified Lexmom email-address identities; meetlexmom.com absent. No Lexmom active receipt rules or matching named configuration sets found. SES does not enumerate conventional mailbox users.
- Fresh lexmom.com MX routes Google. meetlexmom.com still has no root MX/TXT and retains DMARC quarantine. North Virginia account sends last 24h: zero; Oregon: 259,003. Oregon legacy approximately 14-day aggregate shows 1,087,430 delivery attempts. Account-wide values cannot establish Lexmom sending totals; no workload was changed or paused.
- Saved SES_INVENTORY_20261013.md and updated mailbox options. AWS identifiers/diagnostics stay in private audit .env, compact report retained. No email, DNS, identity/resource creation, key/permission change, deployment, purchase or restart. No disposable deployment outputs; audit helpers/evidence preserved.

### 2026-10-13 - Configure Lexmom SES, verify one internal delivery and route demos

- Owner explicitly authorized hello@meetlexmom.com in SES, support@lexmom.com for replies/demo requests, campaigns disabled, and exactly one internal test. Created the dedicated North Virginia identity/configuration and published five DNS authentication records. Domain, DKIM and custom bounce MAIL FROM verified SUCCESS; TLS required, bounce/complaint suppression and private SNS/encrypted SQS/DLQ events configured.
- Added an EC2-assumable role with no static keys, scoped to the new identity/configuration and hello sender. After the approved test, all recipients remain limited to support, SES configuration sending false, runtime send false and campaigns false. Existing account-wide sending and transactional providers preserved.
- One internal email was accepted. Queue inspection first failed on a non-JSON AWS validation notice after acceptance; reconciliation reused the saved receipt without resending and confirmed SMTP Delivery. Inbox/Spam placement and support-to-office mailbox relationship remain unverified. Owner identifies mail@lexmom.com as the office mailbox; available connector/browser sessions initially lacked it.
- Implemented and deployed shared validated configuration, EC2-role-only session, read-only readiness and pure request builders. Six meaningful transport tests passed locally and in AWS staging; actual runtime role passed all 13 readiness checks. Eleven new env entries appended locally and remotely with existing entries preserved; .env.example/requirements updated. No campaign sender/worker, mailbox token, recurring timer or subscription was activated.
- Changed only the live website's demo-recipient env entry to support, retaining source/database/SMTP/sender. One gunicorn restart reloaded its systemd EnvironmentFile; websocket was preserved. Verified actual Django settings, both services active and demo OPTIONS response 200 with POST allowed. No booking or demo email was created. Access used temporary Instance Connect authorization and an existing trusted host key.
- Setup, limitations, rollback and evidence: docs/lexmom_sub_manager/SES_SETUP_20261013.md. Research usable-contact acceptance and Email Campaign/inbox integration remain open; SES setup is not whole-agent readiness. Source uncommitted; keys and collected data not uploaded.
- After owner connected the Lexmom Chrome profile, verified the test visibly in mail@lexmom.com's Inbox. Message details confirm To/Reply-To support, mailed-by the bounce subdomain, signed-by meetlexmom.com and TLS. Recorded the observation locally/remotely and preserved a screenshot. No additional email or reply sent; server-side Gmail synchronization remains pending.
- Deployment cleanup completed: preserved staging .env as configured.env, then removed only the verified AWS staging directory (14,110 file bytes); remote free space 78,414,184,448 to 78,414,217,216 bytes. Removed 20 inspected, inactive, regular local operation scripts (70,413 bytes) with native PowerShell LiteralPath operations; local free space 13,553,414,144 to 13,553,520,640 bytes. Preserved source, all env/credentials, screenshots, private receipts, live data, rollback, dependencies and earlier blocked-cleanup files. Exact receipt: SES_SETUP_CLEANUP_20261013.json. No preview process or managed worktree required cleanup.

### 2026-10-13 - Deploy paused Manage/Launch email campaigns and office mailbox sync

- Owner approved setup-only Email Campaign specialist, separate seven-day daily sequences, dedicated Gmail read/insert offline authorization, and exactly one combined internal review to Sajan. No prospect sending authorized. Created fourteen paused JSON drafts and fourteen distinct AI robotics images after the owner rejected plant imagery/typography. Official logo, purple/white/lavender palette, readable shorter headings and concept labels retained.
- Dedicated Internal Google OAuth app/client authorized mail@lexmom.com; exact identity and readonly/insert scopes verified. Client credentials/refresh token remain in protected local/AWS .env; no Gmail send/delete scope or static AWS keys. Gmail API works on AWS and locally; token retries bounded, history cursors commit after durable messages, expired history recovers, ambiguous archive insertion never repeats.
- Deployed isolated Email Campaign routes/UI/private SQLite and a supervised two-minute monitor. Five messages synchronized; one review in Sent. Imported fifteen existing research contacts with holds, no new search/verification/model calls. These remain unqualified/not enrolled. Sourced excerpt handoff corrected and covered by regression. Known-contact replies cancel pending sequences; demo/reply review tasks deduplicate and hold responses. No live reply/demo was fabricated and none received yet.
- Previous review send attempt had an unknown tool outcome. Two office-connector searches plus direct dedicated Gmail API confirmed no Sent match before issuing the authorized send. Gmail returned a SENT receipt; AWS and the live OS Sent view then confirmed exactly one review to sajan@menteso.com, Reply-To support@lexmom.com. No duplicate review sent. Some punctuation suffered replacement during Windows-to-connector transfer; source drafts/SES MIME remain UTF-8. Recipient Inbox/Spam placement not verified because Sajan's connector requires reauthentication.
- All campaign switches remain false, SES configuration sending false, original internal recipient restriction intact, no prospect actions queued and send endpoint refuses activation. Sender postal identity and future recipient/frequency/limit approval plus activation lifecycle remain separate prerequisites. No never-Spam promise or fabricated placement metrics.
- Pub/Sub API enabled; topic creation not confirmed, publisher/subscription/watch not connected. Office Chrome refused debugger control after multiple supported recoveries; alternate Dev Google session requires verification with no saved password. Owner traveling, so no repeated manual-click requests, password collection, broader token grant or workaround. Working poll monitor remains independent of console sessions. AWS CLI expired mid-verification; renewed existing Devteam login through the saved browser sign-in, with code transferred privately back to the original CLI process.
- 37 email/SES/dashboard tests passed locally and on AWS, JavaScript syntax/diff checks passed, standalone draft agent passed four self-tests. Live desktop validated drafts/artwork, exact one Sent review and connected mailbox; phone viewport 390×844 had no page overflow (email width 348), then viewport restored. Saved screenshots and marked live Email Campaign tab as deliverable.
- Restarted only isolated Lexmom adapter and owned email monitor. Preserved custom PCT code/UI/data/local keeper and AWS-disabled state; shared container retains October 5 start time, n8n/WLF paused. No Git commit/push/merge and no customer data or secrets uploaded.
- Removed exact owned private S3 archive/bucket and its temporary role read access. Removed checked, inactive AWS email-build-stage-20261013 (46,106,648 file bytes); free space 78,328,406,016 to 78,374,670,336. Preserved live secrets/database/artwork/source and rollback releases. Automatic approval review rejected local deletion with "blocked by policy" before execution; did not bypass or retry deletion. Seventeen disposable files retained (22,036,677 bytes), measured local free space 11,538,120,704. Exact receipt: EMAIL_AGENT_CLEANUP_20261013.json. No preview process/worktree required cleanup; minimal operation helpers retained for unfinished Pub/Sub work.
- Release/limits: docs/lexmom_sub_manager/EMAIL_AGENT_RELEASE_20261013.md; agent README documents deployment and activation boundaries. Pub/Sub remains explicitly unfinished, so this is a working paused-campaign/mailbox setup, not full bulk-campaign readiness.

### 2026-10-14 - Personalize paused Launch and Manage campaign copy

- Owner rejected generic drafts and supplied direct website/case-management subject examples. Rewrote all fourteen paused drafts in a shorter problem-led tone, with named/firm subject templates and separate firm-inbox messages. Examples: “John, want to see an AI website for your law firm?” and “John, still chasing case updates?” Source names only; dashboard John/Example Law samples are clearly examples, not leads.
- Added validated plain template fields, bounded name handling/header-injection rejection, escaped HTML and Unicode MIME regression. Kept unsupported website-absence/manual-tool claims as questions or conditional wording; no fabricated personalized preview. “We created this for you” requires a real preview and was not used. Source JSON remains editable.
- Version 2026-10-14.1 deployed only to isolated Lexmom source and the exact existing email JS block, preserving all surrounding/custom PCT JS. Forty tests passed locally and on AWS; standalone draft agent passed four self-tests. JavaScript/whitespace checks passed. Live authenticated UI verified both revised sequences, labeled personalization examples and zero campaign sends. Gmail monitor stays connected; shared container retains October 5 start time, no secret/DNS changes or unrelated restart.
- Application/SES campaign gates remain off; no prospect, internal test or replacement Sajan review email sent. UI distinguishes the earlier review from updated drafts. No new provider search/verification/inference or artwork generation. Source remains uncommitted; no Git push.
- No archive, remote stage or S3 transfer created; compact evidence and required rollback preserved. Automatic approval review rejected single task-local deployment-helper cleanup with “blocked by policy” before execution. No bypass/retry; exact retained path/bytes/free space in EMAIL_COPY_CLEANUP_20261014.json. Earlier blocked-cleanup targets untouched. Revision/limits: EMAIL_COPY_REVISION_20261014.md and email-copy-20261014.png.

### 2026-10-14 - Replace seven-day drafts with CEO five-email routes and send internal review

- Owner deferred product-event integration and explicitly declined messaging the active Lexmom task. Created Launch, Manage and both routes with introduction, three follow-ups and final feedback; fifteen paused drafts, suggested days 1/3/6/10/14. No product repo changes or prospect activation. Existing branded artwork reused; source JSON remains editable.
- Updated validation, prepared-only offsets, combined CTAs/images, general-inbox introduction wording, retired preview positions and UI. Installation cancels obsolete unsent actions while preserving accepted history. Full conversion-aware branching and supervised dispatch remain deferred; no production-readiness claim for that unfinished lifecycle.
- 59 checks passed locally and on isolated AWS; standalone four self-tests passed with fifteen previews and zero sends. Live backend verified connected mailbox, artwork availability, healthy dashboard/monitor, current review metadata and zero campaign sends. Isolated dashboard/email monitor restarted; surrounding PCT UI and shared container preserved with October 5 start time. No keys/data pushed, provider searches/verification/inference or public campaign sends.
- One authorized combined review sent through the Gmail connector from mail@lexmom.com to sajan@menteso.com, Reply-To support@lexmom.com. Exactly one current-subject Sent email reconciled, all fifteen draft subjects and Unicode verified, mailbox cache synced. Sajan's receiving folder is unverified because his connector needs reauthentication. SES and application campaign gates stayed disabled.
- Source, strategy and verification: docs/lexmom_sub_manager/EMAIL_FIVE_DRAFT_RELEASE_20261014.md; complete review HTML/text preserved. Historical draft archive, private send receipt and unfinished lifecycle prototype retained in ignored runtime-data. Task cleanup receipt records exact disposable paths and free-space measurements; older blocked-cleanup targets untouched.

### 2026-10-14 - Short, image-free templates and CEO Google Doc revision

- Owner requested all fifteen Launch/Manage/combined emails shortened and personalized without images, preserving paused campaigns. Revised bodies to 28–42 words with sourced firm-name substitution, named/general inbox subjects, distinct first-message firm-inbox bodies, bounded optional source sentence and safe missing-data fallbacks. Current version 20261014-text-v2. No fabricated recipient facts or personalized site previews.
- Removed imagery and logo from current HTML/plain-text presentation, dashboard and generated review copy. Historical assets/mail retained. Existing native Google Doc updated across all three tabs in the Lexmom office browser, preserving audience rules, strategy/checklists and tab names. All current subject/body variants and fifteen sections verified through browser export readback; no image/artwork references. Review placeholders are explicit; Doc retains private office access for the owner to share with the CEO.
- 61 email/engagement/SES/dashboard checks passed locally and on isolated AWS; standalone five self-tests passed with fifteen previews and zero sends. Live verification confirmed image-free drafts, connected mailbox, zero campaign sends, disabled application/SES gates and older Sajan review correctly marked historical. No replacement Sajan/CEO email sent; owner intends to forward the Doc themselves.
- Only isolated dashboard/email monitor restarted; exact email UI block changed while surrounding PCT code/shared container remained intact. Secrets, state, accepted history, required rollback, unrelated agents and deferred product integrations preserved. No searches, verification, inference, paid generation, new credentials or Git push. Source archived under ignored task directory; disposable operation helpers cleaned with exact paths/free space in EMAIL_TEXT_ONLY_CLEANUP_20261014.json. Prior blocked paths untouched. Evidence: EMAIL_TEXT_ONLY_RELEASE_20261014.md and GOOGLE_DOC_TEXT_ONLY_20261014.png.

### 2026-10-14 - Continue the conversation across five-email routes

- Owner relayed CEO feedback that follow-ups lacked prior-email context and useful continuity, and requested stronger subjects. Revised all fifteen short, image-free drafts; every follow-up recalls its immediate predecessor, adds an evaluation point and asks a focused question. Current version 20261014-conversation-v3. Source names/firm facts only; no invented reading, click, reply, preference or custom preview.
- Updated the existing native Google Doc's Launch, Manage and combined tabs while preserving audience/routing guidance and existing owner sharing. Saved browser exports verified every body, subject variant, step reference, added-value note and five sections per tab. Chrome disconnected after readback, so an additional screenshot was unavailable; no document edits remained outstanding.
- Added schema continuity metadata and an atomic prior-send guard. A follow-up requires a nonempty provider acceptance ID for its preceding message in the same recipient/product/version sequence. Prepared, queued, unknown or other-series messages cannot satisfy the recap. Delivery/read status is not inferred.
- 64 meaningful checks passed locally and on isolated AWS; standalone five self-tests passed with fifteen previews and zero sends. Live verification confirmed current drafts, twelve contextual follow-ups, connected mailbox, zero campaign sends and false application/SES gates. No internal, CEO or prospect email was sent.
- Deployed only six owned backend/test files, preserving rollback source and a private SQLite backup. Isolated Lexmom dashboard/email monitor restarted; static app/email scripts and shared container were verified unchanged. Product branching and demo/signup/payment integration remain deferred. No credential/DNS/PCT/workflow changes, paid provider activity or Git push. Exact disposable helper cleanup/free-space receipt: EMAIL_CONVERSATION_CLEANUP_20261014.json. Source, old-template archive, current review HTML/text, verification and release evidence remain preserved.

### 2026-10-14 - Verify office access and use full product names in email links

- Owner completed Google verification in the first setup tab. Confirmed the office Cloud session and existing dedicated reply topic; zero attached subscriptions, only inherited Owner role shown. Prepared a Gmail publisher form but never saved a permission grant. No duplicate OAuth client, billing activation, password change or mailbox watch. One obsolete verification tab closed; further cleanup met intermittent browser-control failures.
- Read-only AWS check verified live dedicated Gmail authorization and 120-second synchronization, with fifteen paused drafts and zero campaign sends. Instant Pub/Sub notifications remain unconnected; identifiers and setup evidence are protected in ignored runtime-data.
- Owner requested complete LexMom product names in Explore and Book a demo links. Version 20261014-conversation-v3.1 changes only CTA labels/version, with body/subject/URL/cadence/continuation metadata preserved. All 34 existing campaign checks passed. Deployed one JSON file atomically with an intervening-change guard, source rollback and consistent private SQLite backup; no service restart. Standalone five self-tests and live label/mailbox/zero-send checks passed.
- Updated all three existing native Google Doc tabs with scoped Find and Replace. Reconciled interrupted edits after office reconnection and refreshing the stale original tab. Saved export readback verified every full-name link, preserved destination, fifteen subject/body variants, audience guidance and version note. Verification: EMAIL_CTA_DOC_VERIFICATION_20261014.json; screenshot: GOOGLE_DOC_CTA_LABELS_20261014.png. Existing sharing, other agents, PCT, static scripts, credentials and campaign sending gates unchanged.
- All campaigns remain paused; zero emails sent. Source and old-label archive retained; exact current-task disposable cleanup and free-space measurements recorded in EMAIL_CTA_LABEL_CLEANUP_20261014.json. Pub/Sub setup remains pending; no claim of push readiness or full acquisition-lifecycle completion.


### 2026-10-15 - Social Media Posting local completion; provider/AWS access initially blocked

- Owner authorized finishing LinkedIn/YouTube connections and isolated AWS deployment, with no public posts, video uploads or active schedules. Added dedicated cookie/operator/destination-bound OAuth callbacks, Google PKCE, safe connection controls, separate identity/analytics status, token-expiry monitoring, destination-bound media approval, edit/pause controls, bounded serialized video rendering and ambiguous-write/duplicate-claim protection. Added dedicated read-only monitor units; neither is installed on AWS yet.
- Verified 78 broad Python checks, then all 27 final social checks after an additional rejected-consent persistence regression (79 distinct checks overall). JavaScript syntax and existing PCT reconnect checks passed. Isolated standalone run passed three automatic self-tests, prepared five private drafts and two real vertical MP4 previews, with zero provider credentials/calls and zero posts/uploads. Visual browser acceptance remains unverified.
- LinkedIn initially exposed only the unverified World Lawyers Forum app. Prepared an unsaved LexMom app form against the existing LexMom Page; no terms acceptance, app registration, Community Management request or token grant completed. Google Cloud account/project inventory was inspected, but no social project/client/consent was created. All secrets and identifiers remain protected; no raw values printed or committed.
- AWS CLI authentication expired before the remote preflight. Existing remote-login renewal expired without a console session. Owner requested Sajan Chrome, but Chrome control disappeared and continued to time out/report unavailable after the owner reported Connected. A fresh direct-Chrome opening also timed out. In-app browser recovered and displayed actual provider sign-in pages; owner requested existing direct Chrome instead. Closed duplicate in-app sign-ins and preview tabs; no repeated signup/consent was attempted.
- No AWS source/configuration, service, permission, DNS or data changed. No deployment or public-publishing readiness is claimed. Existing research/email/PCT and paused workloads preserved. No Git push or paid generation. Local source, private preview assets and compact evidence retained because live setup remains unfinished. No production cleanup gate was reached.
- Resume from docs/lexmom_sub_manager/SOCIAL_AGENT_SETUP_20261015.md and agents/social_media_posting_agent/README.md after working Chrome/AWS access is restored. Do not ask for setup/deployment approval again; obtain any tool-required action-time access/legal consent only at the concrete final grant.

### 2026-10-15 - Deploy social workspace and register dedicated integrations

- Direct Chrome and existing AWS CLI access recovered. Created the dedicated LexMom LinkedIn app, verified its existing Page association/business email, saved callback/privacy settings, and submitted the owned-Page Community Management Development Tier form after the owner's API/Marketing terms approvals. Submission is confirmed; LinkedIn business/product review remains pending. No other-company app was changed and no LinkedIn access token was granted.
- Created the dedicated Google social project/Web client, enabled YouTube Data/Analytics APIs, configured published homepage/privacy/terms URLs and exactly three YouTube scopes. With owner approval, switched its OAuth audience to In production; Google's separate app-verification requirement remains. An old client secret was exposed through a copy-button accessibility label; its replacement was saved privately and the owner disabled the old secret. Eight dedicated config values were encrypted into the AWS .env, then the temporary transfer private key was removed.
- Deployed only the isolated Lexmom runtime and monitor-only timer, keeping all publishing/upload/campaign/paid-generation gates false. Preserved the actual customized PCT JavaScript prefix, existing email/research data and non-social environment values. Shared container retains its October 5 start time. No publisher timer, public post, upload (including private/unlisted), campaign send, paid generation or Git push.
- Diagnosed real HTTP rendering failure as FFmpeg exit -9; a resource limit was suspected without claiming a proven kernel OOM. Bounded decoder/filter/encoder workers, made artwork/style renders reusable across draft revisions, preserved drafts on failure and added bounded safe diagnostics. Both Manage and Launch then rendered through the actual dashboard to revision 3. Browser metadata confirms twelve seconds, 1080x1920 and no playback errors. Fixed initial social-tab rendering from URL hash and added video artwork posters; fresh desktop UI shows five private drafts automatically. Thirty social checks passed locally and on AWS; previous broad/self-test evidence remains documented. No mobile visual acceptance claimed.
- YouTube owner Chrome is accessible as menteso.com@gmail.com and shows the existing @thelexmom channel. Its separate Menteso OS Login tab remains signed out despite reported completion; the supplied authenticated screenshot was from Sajan's profile. Explained the exact profile/tab distinction and left the owner login for handoff. No cookie transfer, authentication weakening or replacement channel. Persistent YouTube consent is pending, and neither provider is claimed API-connected.
- Final source hashes, protected-route checks, zero publication attempts, preserved environment and shared-container checks passed. Removed the exact inspected 22-file remote stage (363,179 file bytes), preserving runtime/media/state/env/rollback. Remote free space: 78,228,004,864 to 78,228,451,328 bytes. Automatic approval review rejected native PowerShell deletion of the one local 44,486-byte deployment archive before execution as blocked by policy; no retry/bypass. Receipt: docs/lexmom_sub_manager/SOCIAL_CLEANUP_20261015.json. Source, compact evidence, required rollback and previous blocked targets retained.

### 2026-10-15 - Deploy dormant publishing controls; owner login still pending

- Added local-time scheduling and a Publish due posts control to the social dashboard, through the same durable worker as the new minute-based publisher timer. Dispatch requires operator/origin authorization, rejects enable/credential overrides and fails before worker execution while publishing is disabled. The timer is installed disabled/inactive; its oneshot service is static/inactive. No approval, schedule, upload, public post or paid call was made.
- All 33 social tests passed locally and on isolated AWS, including disabled dispatch, unauthorized/override rejection and future-enabled dispatch to a mocked worker. The real disabled worker returned zero publications. An installer assertion incorrectly expected a oneshot service to be disabled rather than static, stopping before restart. A guarded resume verified current source and preserved customized PCT UI, accepted the correct inactive/static state and restarted only lexmom-dashboard.service. Environment hash and shared-container start time remain unchanged.
- Browser verified deployed controls, five drafts, zero approved and zero published. Screenshot: ignored runtime-data/lexmom-social-20261015/social-dashboard-publishing-controls.png. Version 022 and deployment hashes are retained in publishing-controls-verification.json, with required scoped rollback before-youtube-controls-20261015T090902Z. No new transfer archive or remote build stage was created by this inline patch; earlier blocked cleanup paths remain untouched.
- Rechecked the owner's requested Menteso Gmail profile and its exact OS login tab after reported completion; it still redirects to login. The existing authenticated OS session is in Sajan's different profile, whose Google chooser exposes only Sajan. No wrong Google account was authorized. Privately checked only existing OS admin configuration in Docker environment, mounted .env and the container's working-directory .env; no reusable password was found or changed. The exact owner-profile login remains marked for handoff. Persistent YouTube consent and LinkedIn review remain outstanding; neither provider is claimed API-connected.

### 2026-10-15 - Social connection chips, platform-filtered posts and dates

- Added LinkedIn/YouTube connection chips below Social Media Posting. Green requires configured authorization and a recent verified identity check; loading, missing tokens, stale checks and errors cannot appear connected. Current provider status remains not connected. Chips also select LinkedIn/YouTube rows; All posts restores the complete table.
- Replaced large content cards with a post table showing title, platform, product, Created/Posted and other real states, creation timestamp and first confirmed public-posting timestamp. View opens an accessible native modal side drawer with existing media, edits and review controls. New records save creation once; upload processing/uncertain outcomes do not count as posted. Legacy timestamps stay unknown, preserving all five saved row payloads.
- Thirty-five offline checks passed locally and on AWS, including immutable creation/confirmed-publication dates, legacy compatibility and existing render-failure preservation. JavaScript syntax and offline filter/status/date checks passed. Live Chrome verified five total posts, three LinkedIn, two YouTube, modal preview and focus return. At 320px, chips stay inside the page, only the table scrolls horizontally, and the drawer fits without horizontal overflow. Temporary viewport reset.
- Guarded UI release 023 followed by source/UI release 024 preserved the actual customized PCT JavaScript prefix and environment. Only lexmom-dashboard.service restarted for the timestamp backend. Shared container retains its October 5 start time; email/campaign/social flags false, publisher timer disabled/inactive, zero posting attempts and zero scheduled/published posts. Scoped rollback plus consistent private SQLite backup retained. No provider grant, upload, public post, active schedule, paid call or Git push. No new transfer archive or remote staging directory was created; old blocked cleanup targets untouched. Evidence: ignored connection-chips-verification.json, posts-table-verification.json and social-posts-table-live.png in runtime-data/lexmom-social-20261015.

### 2026-10-15 - Official persistent access, pending-review guard and rate-limit handling

- Owner reported LinkedIn's authorization failure, requested enduring connections and prohibited activities that risk account restrictions. Read the dedicated app's Products page: Community Management remains Review in progress. No completed token grant exists. Did not retry failing OAuth, submit another product/access request, change LinkedIn settings, scrape profiles, automate engagement/messages, publish or bypass review. Verified official LinkedIn renewal/product documentation rather than promising perpetual access.
- Added a product-approval gate in settings, API and OAuth. Pending review blocks before state creation/provider use; UI says Approval pending and disables authorization until actual provider approval. Corrected the future Community Management scope request to its documented organization-admin permission for Page-role/report reads. Existing token checks accept supported read/admin scope variants with exact Page-role verification. No broader account permission was granted in the browser.
- Added eligible LinkedIn refresh-token/expiry persistence and pre-expiry renewal. Replacement credentials must verify exact LexMom Page/scopes, preserve fixed refresh expiry and pass an intervening-account guard before atomic protected .env replacement. Existing credentials survive refresh failures. Transient retries wait six hours; denied refresh grants stop until reauthorization. Durable per-platform HTTP 429 cooldowns honor Retry-After without immediate retry. YouTube offline refresh remains independent. Chrome need not stay open after real grants are installed; provider expiry/revocation and eligibility still apply.
- All 46 social checks passed locally/on isolated AWS, covering pending review, scope requests, initial grant without refresh, successful rotation, fixed expiry, wrong-Page replacement rejection, concurrent credentials, restart-safe transient/denied backoff, rate limits and prior setup/publication protections. JavaScript checks confirmed pending status and that an unrelated edit error cannot falsely disconnect a verified API status. No live grant/refresh was claimed or tested. Added five optional defaults to local/AWS .env and the template while preserving every original environment value; secrets/identifiers never uploaded to Git.
- Released version 025 and scoped approval-message refinement 026. Source, five saved post payloads, environment, customized PCT JavaScript and shared container retained; only isolated dashboard restarted. Read-only monitor timer active, publisher timer disabled/inactive, zero publication attempts, no public schedule/upload/post, paid call or Git push. Scoped source/private .env/SQLite rollback and compact evidence retained; inline changes created no transfer archive or remote stage. Prior blocked cleanup targets untouched. Receipts: ignored persistent-access-verification.json and approval-message-verification.json under runtime-data/lexmom-social-20261015. YouTube owner consent and LinkedIn external approval remain outstanding.

### 2026-10-15 — YouTube owner authorization completed; publishing remains off

- The Menteso Gmail Chrome profile's OS login became available. Completed the approved official Google flow using menteso.com@gmail.com and the existing Lex Mom / @thelexmom channel, selecting exactly upload, channel-read and analytics-read scopes with offline access. mail@lexmom.com remains the dedicated Google Cloud app administrator, not the YouTube channel owner. Exact-channel verification passed before the refresh grant was saved privately on AWS.
- Two independent AWS worker instances successfully renewed access and verified the correct channel; analytics read succeeded. Read-only monitor active, publisher inactive, five unscheduled drafts and zero publication attempts/uploads; social publishing, paid generation, email sending and campaigns all remain false. Protected .env mode 0600. No session/cookie transfer, auth weakening, replacement channel, service restart or upload test. Evidence: ignored runtime-data/lexmom-social-20261015/youtube-connection-verification.json.
- Rechecked LinkedIn's dedicated Products page: Community Management API Development Tier still Review in progress. Approval must come from LinkedIn's API review team, then the existing Page administrator can grant OAuth access. No approval bypass or automated social interaction attempted. Google app verification remains separately incomplete; offline access is renewable, not guaranteed permanent.
- Corrected misleading connected-account help text and deployed static UI version 027 with source hash and environment guards, existing customized JavaScript prefix preserved and no service restart. JavaScript syntax check passed. Required source rollback retained; inline patch created no archive/stage and consumed atomic temporary files. Evidence: connected-message-verification.json. No Git commit/push.

### 2026-10-15 — Google branding verified; YouTube release 028 guarded deployment

- Google verified and published LexMom Social Media Agent branding. The live Console explicitly confirmed it is shown to users; screenshot retained privately as google-branding-verified-live.png. Sensitive data-access review remains unsubmitted: Google requires scope justification and an unlisted demonstration video. Prepared the exact three scope justifications and actual company-owned-channel use case in GOOGLE_SOCIAL_VERIFICATION_20261015.md. No fabricated public-user claim, video URL, upload receipt or provider approval. No additional scopes, credentials or audience changes.
- Added per-draft YouTube visibility with Private default and exact approval binding; private/unlisted processing receives Uploaded status without a public posted timestamp. Added explicit confirmed operator-only disconnect/revocation and live provider-data removal, concurrent-grant preservation, confirmed-invalid-grant cleanup and a shared finite worker lock. Authored drafts/media, unrelated settings, duplicate protection and YouTube-hosted videos survive removal. Public app-specific about/privacy disclosures expose no runtime data; all previous private routes remain authenticated. Live disconnect and upload paths were not executed.
- All 58 social tests passed locally and on AWS; JavaScript syntax and diff checks passed. Fixed a pre-existing test dependency on FFmpeg discovery by isolating executable lookup from mocked render invocations. Offline tests exercise visibility payloads, processing/privacy mismatches, authorization, revocation failures/races, data removal, wrong-client preservation and public/private route boundaries.
- Initial release guard stopped before any write because the live CSS is an owned inline block rather than a separate link. Inspected actual served asset wiring and corrected the exact-block replacement. Release 028 then preserved actual customized JavaScript/HTML, source hashes, unchanged environment/grant and every saved post payload. Only isolated dashboard restarted. Monitor timer restored active; publisher disabled/inactive; zero attempts/uploads; all four social/email enable gates false. Fresh independent AWS channel renewal and analytics checks passed. External public about/privacy HTTP 200 with CSP; private data HTTP 401. Required source/SQLite rollback and compact evidence retained. No Git commit/push, shared OS restart, PCT change or campaign action.
- Cloud/browser control repeatedly timed out after branding approval and after the administrator profile reconnected. Could not claim Console scope text/new disclosure URLs saved or final visual QA of release 028. Google-sensitive review submission, a real compliant demonstration recording/unlisted upload and final provider approval remain pending. Existing verified branding still uses prior general product links. Pending setup helpers, secrets, required rollback, media and receipts preserved. Automatic approval review rejected the native PowerShell deletion of three inspected task bytecode files before execution, stating only blocked by policy. No retry or alternative deletion attempted; those exact files remain. The cleanup receipt records paths, sizes, no removals and measured free space.

### 2026-10-15 — Browser recovered; local Google review video prepared

- Recovered direct control of mail@lexmom.com Chrome after the user showed the debugging banner. Saved the exact three-scope justification (985/1000 characters) and dedicated live about/privacy URLs in Google Cloud. The Console confirmed both saves. Re-verification of the revised homepage was blocked by missing Search Console ownership of os.menteso.com; Google instructs verifying ownership and waiting 24 hours before retrying. Previous branding remains the version shown to users. No false ownership assertion, review submission, DNS change, scope expansion, credential rotation or paid action.
- Actual service-account verification exposed a root-owned worker.lock created by the earlier root deployment check. Changed only that exact verified lock's owner to menteso_os and mode to 0600; the monitor service then finished successfully. Existing grant/environment preserved, zero publication attempts. Timer remained enabled; publisher remained disabled. Production checks must include the actual worker identity, not only a root-run adapter check.
- Deployed static release 029 with exact source/bundle/index hash guards and preserved customized JavaScript prefix. Six recovery cases passed: an older failed OAuth attempt is suppressed only after a later fresh verified account check; new failures, stale/missing authorization and failed refresh remain visible. Live browser confirmed the green YouTube chip and disappearance of the obsolete warning. No service restart, OAuth change or posting action.
- Captured the real owner-account/channel chooser flow, selected the existing Lex Mom Youtube channel and stopped at Google's unverified-app security warning for user handoff. No bypass, grant replacement or disruption of the working AWS connection. Captured actual read-only analytics, five drafts/two YouTube rows, rendered preview, Private-default visibility control and removal explanation. No draft approval, schedule, upload or disconnect.
- Produced and visually checked a captioned local edited review cut: artifacts/lexmom-google-verification-20261015/lexmom-google-verification-review.mp4 (119 seconds, 1920x1080, H.264, silent). Full decode passed without errors. Provenance manifest identifies actual captures and the missing selected-channel capture; warning/remaining consent and ownership blockers are disclosed. It is not an uninterrupted Google submission recording. No video or file uploaded; local preview opened in Codex. Verification remains pending owner warning review, remaining consent capture, domain ownership and an eventually authorized unlisted demonstration URL.
- Static patch used inline payloads and consumed atomic temporary files; no new disposable build stage or transfer archive was created. Required rollback, authored media, local video project/captures, credentials and compact evidence are retained. Previously blocked cleanup paths were not retried. No Git commit/push or changes to PCT, shared OS, n8n or WLF.

### 2026-10-15 — User deferred Google warning review

- User explicitly postponed the personal Google warning step and asked to remember the stopping point. Saved the exact resume order in GOOGLE_SOCIAL_VERIFICATION_20261015.md. No further provider or AWS actions taken. Working YouTube grant/read-only monitor remain intact; uploading, publication and campaigns stay disabled. Pending OAuth state may expire and must be restarted through the normal OS flow when resumed. No reminder or automatic continuation was created.

### 2026-10-16 — Resumed Google verification; domain-account access pending

- User resumed setup. Reopened the exact owner-profile OS login and, after the user requested help finding it, focused its existing maximized Chrome window. User signed in; authenticated social dashboard verified YouTube Connected, a 09:45 IST account check, five drafts, zero approved/published and disabled publishing. Read-only AWS terminal audit stopped at expired CLI authentication before submitting SSM; no service or credential mutation.
- Opened a fresh same-client/same-scope owner flow and selected the existing Lex Mom Youtube channel. Google displayed the unverified-app warning. User-reported permissions visibility did not match the actual page, so inspected the real screenshot, expanded Advanced only and left its final continuation action for the owner. User then asked why the warning appeared. Explained separate branding/sensitive-scope review and preserved the existing working grant; did not bypass the warning. Browser screencast attempt produced only partial frames with navigation/event truncation; these are not claimed as a continuous completed video.
- User connected mail@lexmom.com Chrome and completed Google's fresh password verification directly. Verified the actual app-admin Console; scope justification remains 985/1000 characters with exactly three scopes and no video URL. Privately compared the single dedicated Web client's identifier with the actual AWS-generated owner-flow URL: exact match. No password requested in chat or copied from another profile. Closed the task-created unrelated-account chooser. Scope settings, credentials, DNS and provider permissions remain unmodified.
- Both public app/about and privacy pages returned HTTP 200 with expected disclosure/privacy links and CSP. Root DNS already contains five Google verification records. Current official Google documentation requires DNS-level Domain-property ownership of the registrable menteso.com domain by an account associated with the dedicated project, so inspect existing ownership before adding DNS. Updated the durable verification checkpoint. No upload/publication/review submission, new deployment, source commit/push or changes to shared OS/PCT.
- Prepared the menteso.com Domain property in the correct Search Console account. Selected manual TXT verification rather than the offered Google-to-GoDaddy registrar delegation. Exact challenge saved in ignored task .env with a placeholder .env.example; private comparison confirmed it is not already in public DNS. Domain ownership remains unverified. Preserved Google pages for handoff; the opened domain portfolio in the available work profile redirects to sign-in. Asked the user to connect their actual GoDaddy/delegated account. A work-profile control call requested an extension update, while the correct Google-admin profile continued to work. No DNS/permission change or warning bypass; obtain action-time confirmation for the prepared single TXT/ownership operation after the real domain zone can be inspected.
- Added a narrow .gitignore rule for private LexMom Google-verification review media. Kept the review video/captures, partial recording provenance and all earlier required artifacts; no retry of previously blocked cleanup paths. Documentation and ignored evidence only, no new production deployment.


## 2026-10-16 — LexMom signatures, held contact collection and Azam internal preview

- Owner approved the Sherry sign-off on all fifteen templates. Native Google Doc tabs and isolated AWS previews now match version `20261016-signature-v3.2`; forty email/transport checks passed locally and on AWS. Only email tools/campaign JSON changed; shared OS, PCT, social publishing and product backends were preserved.
- Live research inventory increased from fifteen to eighty-four saved contacts, including thirty-seven source-associated names. Sixty-nine primary-source contacts were imported as held research, not qualified leads. Zero are currently send-ready. Four free SerpAPI searches were used (236 remain); no Hunter, verification or paid model call was made.
- User explicitly authorized five combined Launch + Manage internal previews to Azam, five minutes apart. They are not real lead enrollments. All five completed between 15:30 and 15:51 IST, at least five minutes apart. All five have matching Delivery events and Sent copies in the OS cache; four messages have recorded Open events. The bounded runner has exited successfully. Do not repeat or restart sends without reconciling `runtime-data/lexmom-email-live-20261016/internal-review/.env` and the protected remote test state.
- A fresh final read confirms the temporary per-recipient IAM grant was removed and dedicated SES sending is disabled; application prospect/campaign switches remain false throughout. Actual replies pause the remaining previews.
- Missing business postal identity, recipient basis, qualification/verification and the deferred production dispatch/conversion integration still block prospect campaigns. Mailbox polling and delivery/open/click events are configured; folder placement is unknown.
- Automatic approval review rejected deletion of six disposable Doc exports as blocked by policy. No deletion or workaround ran. Exact retained paths/free-space evidence are in `docs/lexmom_sub_manager/EMAIL_SIGNATURE_CLEANUP_20261016.json`.
- Detailed current evidence: `docs/lexmom_sub_manager/EMAIL_RELEASE_20261016.md`.

- Final tracking verification: combined-route CTA matching repaired and deployed; fifty-four tests passed on AWS. The business-address request is saved as an unsent draft in the office mailbox. Recipient Inbox/Spam placement remains unknown; no prospect campaigns were activated.

## 2026-10-16 — Qualified prospect batch and research pipeline repair

- Researched 64 firm domains using public primary websites and source-grounded extraction, with targeted published buyer-profile enrichment. No LinkedIn scraping, paid model operation or new SerpAPI search was used for this batch. Kept raw public sources and verification responses in the ignored `runtime-data/lexmom-qualified-leads-20261016/` directory.
- Deployed 53 unique research-ready email contacts across 12 firms: 45 named buyer-role contacts and eight general firm inboxes. Primary routing is 50 Manage and three Launch contacts; the Launch contacts belong to one newly established practice. Fit remains a hypothesis from published evidence, not confirmed interest. All 53 are New, with no recorded opens, clicks or replies.
- Repaired source-linked person/role/email association, current profile versus old testimonial titles, bounded legal-team roster counting, complete-address country evidence, multi-office locations and recent own-firm launch statements. Rejected bogus role headings as names and kept catch-all, invalid, stale verification and incomplete evidence held. Published roster counts are labelled as roster counts rather than payroll headcounts. Verification freshness remains seven days.
- The saved JSON profile targets 50 verified contacts with rules-only extraction, finite page/candidate/verification limits and free-allowance checks. A completed inventory goal now reuses freshly assessed saved results without provider operations. A regression test covers that credit safeguard.
- The live lead table defaults to Qualified & verified, with separate Research, Product and Activity filters. Details includes sourced name/role/email, location, roster/count basis, provider and verification date, individual product-fit reasons and supporting excerpts. Preserved all 84 earlier contacts while migrating the policy profile. The complete saved inventory is 355 unique emails, of which 302 remain held; they are not included in the 53 verified count.
- Validation: 144 research regression tests and 15 engagement tests passed in the isolated AWS service. The full manager/UI harness also passed locally (18 manager checks; 47 focused checks including refreshed primary-facts and engagement coverage). The first deployment rolled back before data import when the repository-wide manager harness expected absent monolithic server.py and unrelated social metadata. Kept that repository-only harness local; no production guard, shared server or unrelated metadata was changed to make it pass.
- Live server verification confirms all 53 detailed records, fresh valid Hunter results, connected activity storage, login-protected data routes, zero active dispatches and disabled campaign/send switches. No email was sent. Only the isolated LexMom dashboard service restarted; the shared menteso-os container's Oct 5 start time and PCT were preserved. Current free balances: 236 SerpAPI searches and four Hunter credits. Existing internal Azam previews were not repeated.
- Assisted research provenance, result artifacts, source snapshots, consistent SQLite backups and rollback releases are retained. Removed only the redundant 237,558-byte local transfer packet and 15 matching AWS transfer chunks (237,558 bytes). Exact paths and measured free space are recorded in `docs/lexmom_sub_manager/PROSPECT_RESEARCH_CLEANUP_20261016.json`. No previous blocked Doc export deletion was retried; no source/data/env/database, shared dependency or live runtime cleanup was performed.
- Browser visual verification remains pending: the connected Sajan tab returned to an empty OS login form after refresh, despite the user's report that a dashboard was visible in another window. Requested the window identity; server verification and deployment are complete. No credential reset, auth bypass or password extraction was attempted. No commit/push or public publishing was performed.

## 2026-10-20 — Git source and teammate handoff

- User requested pushing the accumulated agent pipeline so a teammate can continue. Prepared `codex/agent-pipeline-handoff-20261020` from the fetched current `origin/main` baseline, preserving all local source and the PCT handoff. No force reset, merge to main, workflow change or production restart is part of this handoff.
- Included manager/research/email/social source, shared utilities, dashboard assets, public branded artwork, deployment templates and historical documentation. Added a current source/runtime/configuration map and unfinished-work checklist in `docs/lexmom_sub_manager/TEAM_HANDOFF_20261020.md`; linked it from the root handoff, README and environment guide. Corrected stale manager/research documentation and made the test directory importable for standard unittest discovery.
- Publication audit checked pending text against known protected environment values and credential patterns. Reviewed three documentation/test URL literals as synthetic examples. Actual credentials, protected IDs, lead/mailbox databases, runtime memory/logs, private verification media and account/mailbox/lead screenshots stay outside Git. A narrow ignore rule preserves private screenshots locally while allowing authored public campaign artwork.
- Offline validation: 144 Prospect Research, 153 shared/email/social/runtime/dashboard, 18 manager and 100 PCT checks passed (415 total), plus JavaScript syntax and PCT reconnect checks. No provider workload, message, upload, live service restart or data migration was run for publication. The 16 October research/connection snapshots remain dated historical evidence and were not represented as fresh 20 October checks.

## 2026-10-20 — Directory-led Prospect Research source update

- User requested directory discovery before Apollo, including Justia, Avvo,
  FindLaw, Martindale-Hubbell and similar lawyer-profile platforms, following
  their access/use rules and avoiding access-block evasion.
- Added an editable 16-source catalogue, mixed directory/website search queries,
  unknown-source recognition, dated collection/storage/commercial-use reviews,
  live full-document terms fingerprint and robots checks, reviewed profile paths,
  conservative per-source page/delay limits and durable denial/rate-limit holds.
  The saved profile enables directory discovery within the same search/credit caps.
- Permitted-source profiles retain explicitly associated contacts and evidence
  separately from verified leads. One labelled firm website feeds the existing
  primary research/Launch/Manage qualification and verification pipeline. Added
  a collapsed directory-source status table and source/terms audit details.
- Current catalogue: Justia, Avvo and FindLaw are restricted for the proposed
  commercial collection under the checked published terms; the other 13 require
  review. No real directory is configured as permitted. An IP block is not the
  criterion for whether terms apply. There is no bulk all-lawyer dump, permission
  bypass, automatic approval of an unfamiliar site, proxy rotation or CAPTCHA solving.
- Added the `source_holds` table without modifying existing firm/contact data.
  Runtime holds remain private and survive process restarts; automatic retries
  cannot clear review holds or shorten another worker's pause. Existing cached
  inventory, target-count and seven-day verification rules remain intact.
- Offline validation: 171 research checks, 153 shared/email/social/runtime checks
  and 18 manager/dashboard checks passed (342 total), plus JavaScript syntax and
  PCT reconnect checks. Tests use synthetic permissions, mock HTTP/providers and
  temporary state. No research credits, live campaign or social action was used.
- Scope: source/UI/configuration/documentation only, on the existing handoff
  branch. No AWS deployment, service restart, production data migration or
  deployment cleanup was performed. Existing production secrets, data, active
  processes and disabled send/publish settings were not changed. A future isolated
  deployment must follow `CODEX_HANDOFF.md`; rollback restores source while
  preserving newer databases/holds. Details: `DIRECTORY_RESEARCH_20261020.md`.

## 2026-10-20 — US and Australia research priorities

Superseded by the worldwide-discovery clarification below.

- User clarified worldwide eligibility with US/Australia as the main commercial
  research focus, citing US product hosting. Added editable `priority_countries`
  separately from the existing `countries` eligibility allowlist. The saved
  profile keeps global eligibility and prefers the two named markets; it retains
  a global query lane and the same query/credit limits. No other market was added
  to the priority list or automatically excluded based on assumed hosting needs.
- Round-robin website/directory query generation covers both preferred markets
  in the first three-search plan before ordinary historical query rotation.
  An explicit country allowlist takes precedence. Changing a search preference
  does not invalidate or hide existing inventory or alter qualification rules.
- Validation: 174 research checks and 43 manager/runtime checks passed (217 total).
  No live search, verification credit operation, campaign, deployment or service
  change was performed. Hosting location is user-provided context, not a claim
  that every firm in a country accepts it or that other countries forbid it.

## 2026-10-20 — Clarification: worldwide lawyer discovery

- User clarified that US/Australia are examples and discovery should identify
  lawyers worldwide. Cleared saved `priority_countries` while preserving empty
  `countries` for global eligibility. Optional per-run country targeting remains
  available; no market is excluded because of assumed hosting requirements.
- Added international and solicitor/advocate directory search themes within the
  same rotating query/credit caps. Corrected current documentation and added an
  offline regression check that the saved search does not append either country.
- Existing source-permission holds, qualification, lead inventory, verification
  and disabled sending/publishing remain unchanged. No provider work, AWS deploy,
  service restart or production data change is part of this correction.
- Validation: 49 directory-source and manager/dashboard checks passed, including
  the worldwide saved-profile search regression; no live providers were contacted.

## 2026-10-20 — Dynamic source URL tests and bounded bulk imports

- User requested bulk extraction, different site layouts, remembered source
  progress and a left-side URL/API test card in Prospect Research. Added that
  card, a separate unverified-observation table and source Details drawer.
  Qualified inventory and sending remain separate and unchanged.
- Added reviewed per-path HTML/JSON reader recipes, container-scoped fields,
  explicit profile/next URLs, safe pagination queries and dedicated environment
  authentication for feeds. Unknown/incompatible layouts and unreviewed or
  restricted directories remain held. No real directory/feed was enabled.
- Source jobs add up to 50 observations per explicit batch, buffer unread rows,
  checkpoint progress, deduplicate and resume within existing source limits.
  Only a completed selected URL/feed scope gets UTC calendar-month reuse; a
  partial job never marks the whole site exhausted. Refresh/later-month tests
  mark new/changed/unchanged observations. No new recurring schedule was enabled.
- Both local and isolated AWS adapters register authenticated, operator-only,
  same-origin routes. Browser requests cannot alter policy, enter credentials,
  raise fixed test caps or trigger provider verification/search/model operations.
- AWS identity verification failed, with diagnostics retained privately. This
  is source/UI/documentation only: no production deployment, service restart,
  real source collection, lead migration, campaign or social publication occurred.
  No deployment cleanup applied; test fixtures use automatically cleaned private
  temporary directories. See `SOURCE_IMPORT_20261020.md` for exact limits and
  continuation/deployment instructions.
- Added transactional `source_requests` pacing for explicit source tests so
  changing URLs or restarting a batch cannot reset its source request interval.
  A pacing deadline retains partial work without creating a permanent denial.
- Validation: 201 research checks, 153 shared/email/social/runtime/dashboard
  checks and 18 manager/UI checks passed (372 total), plus JavaScript syntax
  and PCT reconnect checks. Reviewed the synthetic credential-URL rejection
  fixture during the pre-publication audit; no real environment values or
  private business records are included in this source change.
