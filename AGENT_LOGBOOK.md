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
