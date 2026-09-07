# Codex Handoff

Read `AGENTS.md`, `AGENT_LOGBOOK.md`, and `ENVIRONMENT_SETUP.md` completely before changing code.

## Repository layout

- `agents/pct_agent`: PCT agent (local-server runtime).
- `agents/patentzoom_seo_agent`: AWS SEO agent and approved workspaces.
- `agents/accountant_agent`: Menteso OS dashboard adapter for Accountant Agent.
- `services/accountant_agent`: deployable Invoice Request and Invoice Reminder services.
- `server.py`, `static/`: `os.menteso.com` backend and frontend.

## Current priority

Continue PCT contact selection on the local server. The current code is a work
in progress: the user rejected the assumption that extracted email and phone
always belong to the agent. The installed agent-only selection policy still
needs correction; its passing tests do not establish the intended workflow.

- Preserve Applicant and patent fields from the WIPO input.
- Identify the actual owner of each email and phone using document evidence.
- Agent Name must contain an actual agent name; do not assume that this person
  owns the selected email or phone. Preserve ownership evidence separately.
- Revise `ai_verifier.py`, `contact_rules.json`, report mapping and ownership
  tests together. Resolve the process document's ambiguous contact-selection
  cases with reviewed examples before treating the policy as complete.
- Keep exactly Aneeq's 12 output headings, including `Priorty Date`.
- OpenAI currently returns HTTP 429 `credit_balance_exhausted`. Restore credit
  through the account owner and validate representative PDFs before bulk use.
  No successful live AI extraction has been demonstrated.
- Reference files remain local: Downloads/PCT Process.docx and
  Downloads/PCT Data(Aneeq).xlsx. They are not committed to this public repo.

Invoice Reminder OAuth and live scheduling have already been configured under
the user's authorization. Monday reminders run at 20:00 IST, starting September
7, 2026, with separate hourly reply/payment monitoring. Activity notifications
exclude the accounts mailbox. Existing customer pauses remain operational
state outside Git; the explicitly requested individual resume was applied.
Keep development email disabled and do not overwrite production state on pull.

## Safety boundary

- Invoice Request: `invoicerequest@menteso.com`
- Invoice Reminder: `accounts@menteso.com`
- PCT remains local.
- SEO remains AWS-hosted.
- Never copy `.env`, OAuth JSON, refresh tokens, runtime state, customer data,
  Gmail content, invoices, logs, or backups into this repository.

## Verification before deployment

1. Run the relevant unit tests.
2. Confirm the target mailbox using Gmail `users.getProfile`.
3. Send only to an internal test recipient.
4. Verify the delivered `From` header.
5. Back up only the target service.
6. Deploy/restart only the target service; do not restart unrelated agents.
