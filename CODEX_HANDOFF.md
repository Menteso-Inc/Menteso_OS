# Codex Handoff

Read `AGENTS.md`, `AGENT_LOGBOOK.md`, and `ENVIRONMENT_SETUP.md` completely before changing code.

## Repository layout

- `agents/pct_agent`: PCT agent (local-server runtime).
- `agents/patentzoom_seo_agent`: AWS SEO agent and approved workspaces.
- `agents/accountant_agent`: Menteso OS dashboard adapter for Accountant Agent.
- `services/accountant_agent`: deployable Invoice Request and Invoice Reminder services.
- `server.py`, `static/`: `os.menteso.com` backend and frontend.

## Current PCT state - 8 October 2026

The local PCT worker has completed a live run with the updated pipeline. The
older September credit blocker and agent-only-selection description are
historical; do not restore that old implementation during a deployment.
`agents/pct_agent/AI_VERIFICATION.md` describes the current contact policy.

- One browser downloads PDFs while up to four processes extract and verify
  downloaded documents. Both independent image readings and the existing
  focused rereads, owner checks and DNS policy remain in place.
- One coordinator saves durable JSONL checkpoints and writes the two Excel
  outputs in original row order. Resume validates the input and policy before
  reusing completed results. Excel export strips only prohibited non-printing
  XML controls; raw evidence and journal values remain unchanged.
- Preserve source Applicant and patent fields and the exact 12 headings,
  including `Agent Name` and `Priorty Date`. Selected contact ownership remains
  separate from the agent-name field; do not assume they are the same person.
- The dashboard reconnects after a dropped log stream and uses backend
  completion timestamps for ETA, excluding restored rows from speed samples.
- Tests check scheduling and data preservation, not perfect source accuracy.
  Failed downloads, withheld emails, contact-selection gaps and occasional
  character errors remain candidates for future work. Do not weaken the
  verification policy or change collected results during an unrelated deploy.
- Reference workbooks, generated sheets, PDFs and audit records remain local,
  outside this public repository.

Invoice Reminder OAuth and live scheduling have already been configured under
the user's authorization. Monday reminders run at 20:00 IST, starting September
7, 2026, with separate hourly reply/payment monitoring. Activity notifications
exclude the accounts mailbox. Existing customer pauses remain operational
state outside Git; the explicitly requested individual resume was applied.
Keep development email disabled and do not overwrite production state on pull.

## Teammate deployment handoff

The `pct-deployment-handoff-20261008` branch preserves the local October PCT
changes on top of the current `main`, including existing Accountant and other
dashboard changes. Merge this branch/PR into the shared deployment branch
before deploying. A branch push alone does not update `main` or production.
An existing teammate feature branch must incorporate the merged changes before
its deployment; resolve conflicts by preserving both sets of features.

**Automatic deployment:** `.github/workflows/deploy-main.yml` runs on pushes
to `main` and targets the local Windows checkout. This handoff adds a guard
before its remote Git operations, and another guard in `scripts/deploy.ps1`:
both refuse the legacy PM2 deployment when the `Menteso PCT Dashboard Keeper`
scheduled task exists. On this server the workflow is expected to fail with
that explicit refusal after a merge. Use a reviewed deployment for the actual
target service; do not remove the guard just to make the workflow green. An
older workflow already executing is not retroactively protected, so check
the Actions queue before merging. Neither guard blocks arbitrary manual file
replacement; the data and active-run instructions below still apply.

Do not deploy an older checkout, force-reset the local server, or replace its
directory with an archive from an older branch. The existing
`scripts/deploy.ps1 -ForceReset` resets to `origin/main`; that loses these fixes
until they have been merged. The script also assumes a PM2 dashboard runtime,
whereas the local PCT service currently uses the keeper described below. Do
not use that script to manage the current local PCT service without reviewing
and adapting the deployment procedure.

### Runtime boundaries and settings

- PCT runs in `C:\sites\Menteso_OS`, listening on local port 8010. The public
  PCT routes reach it through the AWS reverse-SSH listener on port 29010.
  `.menteso/app.json` records this routing; preserve the actual gateway and
  tunnel configuration as well. The former 28998 route is not the PCT route.
- Keep `MENTESO_DISABLED_AGENTS=pct_agent` on the AWS container, as in
  `compose.aws.yml`. An AWS deployment must not enable another PCT worker or
  route PCT requests to that disabled copy.
- The Windows scheduled task `Menteso PCT Dashboard Keeper` runs
  `scripts/keep-pct-dashboard.ps1`. The reverse tunnel is maintained separately
  by `C:\ProgramData\Menteso\start-aws-tunnel.ps1`. Neither should be stopped
  during an unrelated agent deployment. Machine tasks, keys and live gateway
  configuration are operational state, not installed by a Git pull.
- Keep the existing local `.env`. Current parallel settings are shown below;
  `.env.example` intentionally defaults to one PDF worker for new environments.
  Do not replace a live `.env` with the example or commit any secret values.

```dotenv
PCT_PDF_VERIFICATION_WORKERS=4
PCT_PDF_API_CONCURRENCY=8
PCT_PIPELINE_PENDING_PDFS=8
PCT_PIPELINE_MIN_ROW_INTERVAL_SECONDS=10
PCT_AI_VERIFY_ENABLED=true
PCT_EMAIL_DNS_CHECK=true
```

### Public dashboard

The public dashboard JavaScript is served through the AWS Lexmom adapter and
may contain additional features beyond this repository's `static/app.js`.
Do not replace that customized file wholesale with an older repository copy.
Preserve both its custom features and the PCT ETA/reconnection changes.
The focused patchers `scripts/patch_pct_eta.py` and
`scripts/patch_pct_reconnect.py` can apply these PCT changes to a staging copy
of the actual served JavaScript. They reject an unexpected source layout;
inspect such a failure instead of forcing a replacement. Check the resulting
file with `node --check` and `scripts/check_pct_reconnect.cjs` before deploying
that asset. Verify the actual public asset after deployment, not only the
repository file.

### Data and active-run protection

Before a planned local PCT deployment, run this read-only check using the local
server's existing virtual environment:

```powershell
.\.venv\Scripts\python.exe scripts/check_pct_activation.py --live-root C:\sites\Menteso_OS
```

Any nonzero exit means do not restart or overwrite the local service. If a run
is active, wait for completion. Only for a separately authorized interruption,
use `scripts/handoff_pct_run.py` with the exact run ID and a private backup
directory; it deliberately requests a graceful stop, drains submitted PDFs and
validates saved rows. It is not a read-only inspection tool. Do not restart
until the handoff succeeds, and resume with its original input and
`resume_path`, never by starting that sheet again at row 1.

Back up the target code/configuration and preserve `uploads/`, `outputs/`,
`logs/`, `.env`, runtime state, source PDFs, AI evidence and JSONL checkpoints.
Do not run `git clean -fdx` or restore an old backup over newer collected data.
Source-control operations and this branch's push do not back up those files.
Existing private deployment backups are at
`C:\ProgramData\Menteso\pct-pipeline-handoff-20261007` and
`C:\ProgramData\Menteso\pct-parallel-handoff-20261008`.

### Verification

Run offline in an isolated checkout with dependencies installed, without
copying a production `.env`:

```powershell
python -m pytest agents/pct_agent/test_ai_verifier.py agents/pct_agent/test_contact_ownership.py agents/pct_agent/test_accuracy_policy.py agents/pct_agent/test_overlap.py agents/pct_agent/test_parallel_verifier.py -q
node --check static/app.js
node scripts/check_pct_reconnect.cjs static/app.js
```

The prepared handoff passed 100 Python tests and the dashboard checks on
8 October. The legacy deployment guard is also checked against the actual
keeper task, with refusal before any deployment action. No production service
was restarted by preparing this handoff.
After an authorized deployment, compare public/local run status and verify
report headers, source-row alignment and saved-row counts. Roll back only the
target code/configuration from a compatible backup, retaining newer data; an
older policy may refuse a newer resume file, so check compatibility first.

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
