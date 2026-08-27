# Environment and Secret Setup

This repository is public. It contains variable names and placeholders only.
Never commit a live `.env`, OAuth JSON, refresh token, service-account key,
WordPress application password, SMTP password, API key, or AWS secret export.

## Configuration map

| Component | Development file | Production source |
|---|---|---|
| Menteso OS dashboard, PCT, SEO | repository-root `.env` | `/home/menteso_os/app/.env.aws` |
| Invoice Request Agent | `services/accountant_agent/.env` | AWS Secrets Manager: `invoice-request-agent/config` |
| Invoice Reminder Agent | dedicated untracked reminder environment | AWS Secrets Manager: `invoice-reminder-agent/gmail` |
| Agent state | local ignored runtime directories | `/home/menteso_os/data/*` |

The files above are deliberately ignored by Git. Do not copy production state
or secrets into the repository to make development easier.

## Home workstation setup

```powershell
git clone https://github.com/Menteso-Inc/Menteso_OS.git
cd Menteso_OS
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Fill only the variables needed by the agent you are developing. Leave automatic
publishing, external email, and other live actions disabled on a development PC.

## Menteso OS, PCT, and SEO

Location: repository-root `.env` created from `.env.example`.

Core dashboard variables:

```text
MENTESO_OS_ADMIN_USER
MENTESO_OS_ADMIN_PASSWORD
DASHBOARD_HOST
DASHBOARD_PORT
PUBLIC_BASE_URL
APP_BASE_URL
```

Shared LLM variables:

```text
OPENAI_API_KEY
OPENAI_MODEL
ANTHROPIC_API_KEY
ANTHROPIC_MODEL
CONTENT_LLM_PROVIDER
```

PCT variables are grouped under the `PCT_`, `CAPTCHA_`, `PACING_`, `TOR_`, and
`PROXY_` sections of `.env.example`. Keep these safe defaults at home:

```text
PCT_FAST_MODE=false
PCT_EMAIL_ENABLED=false
```

SEO variables are grouped by workspace:

```text
PATENT_DRAWING_EXPERTS_*
IP_DOCKETERS_*
MENTESO_*
```

WordPress, Google Search Console, Meta, LinkedIn, and social credentials remain
blank until that exact integration is being tested. Keep all `*_AUTO_PUBLISH`
and `*_SOCIAL_AUTO_POST` variables `false` during development.

## Invoice Request Agent

Location: `services/accountant_agent`.

```powershell
cd services\accountant_agent
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

Its `.env` documents the required groups:

```text
MAILBOX_ADDRESS=invoicerequest@menteso.com
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET / ZOHO_REFRESH_TOKEN
WAVE_API_TOKEN / WAVE_BUSINESS_ID / WAVE_INCOME_ACCOUNT_ID
OPENAI_API_KEY / OPENAI_MODEL
AWS_REGION / SECRETS_MANAGER_NAME / DDB_TABLE_NAME
PUBSUB_TOPIC / PUSH_AUDIENCE / PUSH_SA_EMAIL
```

Do not use these Gmail credentials for the Invoice Reminder Agent.

## Invoice Reminder Agent

Template: `services/accountant_agent/.env.reminder.example`.

This agent must use its own values:

```text
INVOICE_REMINDER_MODE=test
INVOICE_REMINDER_MAILBOX_ADDRESS=accounts@menteso.com
INVOICE_REMINDER_GOOGLE_CLIENT_ID
INVOICE_REMINDER_GOOGLE_CLIENT_SECRET
INVOICE_REMINDER_GOOGLE_REFRESH_TOKEN
INVOICE_REMINDER_GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.modify
INVOICE_REMINDER_AWS_SECRET_NAME=invoice-reminder-agent/gmail
INVOICE_REMINDER_TEST_RECIPIENT=shweta@menteso.com
INVOICE_REMINDER_FOLLOW_UP_DAYS=7
```

The Google project is `Invoice Reminder Agent`; the Desktop OAuth client is
`Invoice Reminder Agent AWS`. Confirm Gmail `users.getProfile` returns exactly
`accounts@menteso.com` before sending any test message.

Never put `accounts_oauth.json` or `credentials.json` inside the repository.
Store the production credential bundle directly in its dedicated AWS secret.

## Production locations

These locations are operational references, not files to copy into Git:

```text
/home/menteso_os/app                         Menteso OS/SEO AWS application
/home/menteso_os/agents/accountant_agent    Accountant services
/home/menteso_os/data/accountant_agent      Accountant runtime state
/home/menteso_os/AGENT_LOGBOOK.md           Deployed operations logbook
```

PCT remains on the local Menteso server. Do not deploy or enable its AWS copy.

## Before asking Codex to work

Tell Codex:

```text
Read AGENTS.md, AGENT_LOGBOOK.md, CODEX_HANDOFF.md, and ENVIRONMENT_SETUP.md.
Never print secrets. Never reuse one agent's mailbox credentials for another.
Keep live email and publishing disabled unless I explicitly approve them.
Run tests and change only the target agent/service.
```

## Missing-key troubleshooting

1. Identify the target agent and its environment file from the table above.
2. Compare the file with its `.env.example`; do not guess a value.
3. Confirm the variable is loaded without printing it (report only `SET/MISSING`).
4. For AWS, confirm the correct secret name and region before changing anything.
5. Verify mailbox identity with the provider API before sending mail.
6. Never solve a missing key by copying credentials from another agent.
