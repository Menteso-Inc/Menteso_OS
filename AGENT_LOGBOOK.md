# Menteso Agent Operations Logbook

Last updated: 2026-08-27 (Asia/Calcutta)

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
