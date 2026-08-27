# Codex Handoff

Read `AGENTS.md`, `AGENT_LOGBOOK.md`, and `ENVIRONMENT_SETUP.md` completely before changing code.

## Repository layout

- `agents/pct_agent`: PCT agent (local-server runtime).
- `agents/patentzoom_seo_agent`: AWS SEO agent and approved workspaces.
- `agents/accountant_agent`: Menteso OS dashboard adapter for Accountant Agent.
- `services/accountant_agent`: deployable Invoice Request and Invoice Reminder services.
- `server.py`, `static/`: `os.menteso.com` backend and frontend.

## Current priority

Complete isolated Gmail OAuth for the Invoice Reminder Agent:

- Google Cloud project: `Invoice Reminder Agent`
- OAuth client: `Invoice Reminder Agent AWS`
- Required mailbox: `accounts@menteso.com`
- Scope: `https://www.googleapis.com/auth/gmail.modify`
- Store credentials outside Git in a dedicated AWS Secrets Manager secret.
- Never reuse or modify the Invoice Request credentials.
- Keep reminder delivery in `test` mode until Shweta approves it.

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
