# Codex Handoff

Read `AGENTS.md`, `AGENT_LOGBOOK.md`, and `ENVIRONMENT_SETUP.md` completely before changing code.

## PCT combined contact release qualified - 26 October 2026

The qualified local profile adds `PCT_OLLAMA_COMBINED_CONTACTS=true` to the
existing two-worker profile below. It combines original field images from one
confirmed contact block in one Qwen request; independent acceptance checks and
individual fallback remain. Unknown DNS routing now annotates source-verified
emails without erasing them. An uncertain preferred-applicant email keeps the
primary email blank while preserving verified agent phone/name and explicitly
labelled Additional Email. No OCR-only promotion or ownership guessing.

Matched 200-row timing: 8,546.953 seconds before, 5,996.860 seconds combined
first pass. Five fresh source repairs took 237.218 seconds: final active time
6,234.078 seconds (27.06% less), 175 found/25 errors, 35.623 elapsed seconds per
successful row. The 24 unavailable source PDFs and one unresolved Russian form
remain. Email 171/171 returned matches, 171/200 whole sample; names 108/125
exact or 117/125 with formatting normalization. Overall exact comparable
email/name/country fields: 449/495 available, 449/561 whole sample. All baseline
matching fields and verified contacts were preserved; 347 regressions passed.

This is a saved-original-PDF comparison, excluding live WIPO/CAPTCHA/bibliography.
The final composite includes five fresh repairs, not a full 200-row run under
the final repair revision. Do not claim 100% complete extraction or attainment
of 500–1,000 rows/hour. Read `docs/PCT_COMBINED_CONTACT_20261026.md` for details.

Actual local activation is recorded separately in
`C:\ProgramData\Menteso\pct-combined-contact-release-20261026\verification.json`.
Check that receipt and the live environment/source before assuming deployment.
Rollback checkpoint `pct-before-combined-contact-20261026` is `5a45adc`.
Preserve Qwen document verification, GPT-4o CAPTCHA-only configuration, pinned
model digest, two worker endpoints, collected data and all teammate history.

## PCT two-worker release activated - 23 October 2026

Local activation completed from source `1ca7533`, preserving teammate history.
The idle dashboard reloaded to PID 2808; no active run was stopped. Both local
and public authenticated PCT status/config routes returned HTTP 200/idle.
Seventeen source files and 138 protected data files passed verification; all
unrelated environment values were retained. The second model listener 11435
(PID 10788) is now supervised by the SYSTEM startup task `Menteso PCT Ollama
Worker 2 Keeper`. Original model 11434/PID 7608 and the reverse tunnel remained
running. Temporary test server 11436 was unloaded and stopped. Reboot recovery
and live WIPO throughput are not tested. Private backup/receipts/rollback notes:
`C:\ProgramData\Menteso\pct-two-worker-release-20261023`.

The user's follow-up authorizes two stable row owners on one uploaded sheet.
Use round-robin ownership, one coordinator/writer and independent bounded
pending queues. Two local Ollama servers are required; a single Qwen35 server
still serializes requests. The activated local profile is two PDF workers, two
API slots, four pending PDFs, two threads per model and timeout scale 2, with
worker endpoints 127.0.0.1:11434 and 127.0.0.1:11435. Preserve the installed
model digest, local document provider and separate GPT-4o CAPTCHA configuration.
Keep PCT_OLLAMA_CYRILLIC_OCR_MODEL empty: the experimental Russian form mapping
did not qualify for deployment. This recorded local activation supersedes
earlier one-worker guidance; it does not change AWS compute.

The new 200-publication test retained 24 missing original PDFs. First pass:
172 found, 28 errors, 8561.656 seconds. Seven source-based rechecks recovered
three rows: 175 found, 25 errors, 8969.578 seconds active including rechecks.
Email agreement is 171/171 returned (100%), 171/176 available sources (97.16%),
171/200 whole sample (85.5%). Four emails were withheld for disagreeing source
readings. One Russian form remains unresolved. A further 458.969-second
experimental recheck recovered an email but mapped owner fields incorrectly;
its result is preserved separately and excluded from the qualified report.
Do not describe these results as 100% complete extraction or a speed-target win.

All 200 row IDs/owners, input columns, output order and report styles passed.
312 scoped regressions passed. Tests used original saved PDFs with fresh
OCR/Qwen, excluding live downloads, CAPTCHA and bibliography capture. Fair
queue scheduling was regression-tested and exercised in the seven-row recheck;
the full 200 were not rerun under the final repair revision. Human answers were
held separately. The two-worker profile still needs live throughput measurement.

## PCT combined release - 22 October 2026

The subsequent person/category change separates the report's greeting Name
from contact-owner and agent-name evidence. Preserve that separation: a person
may sign for a company without personally owning its generic mailbox. Names
come from verified applicant/agent identities or an owner-linked printed
signatory; never infer them from email strings or an arbitrary inventor.
Category is an assigned management label. Existing duplicate handling stays
separate; the reference workbook contains repeated emails without Repeated
labels, so an email alone is insufficient. Read the latest logbook for the
measured comparison and activation status before claiming this is deployed.

This release combines the teammate's `04bf7e9` research/responsive dashboard
changes with local Qwen source-region verification, OCR fallback, telemetry and
signing-agent selection. Preserve both histories when deploying. The public
AWS dashboard has additional customized code; patch its reviewed PCT changes
in scope, never replace the actual asset wholesale.

The original report columns A-L remain in order; column M is `Additional Email`,
with role/owner-labelled verified addresses. A source-confirmed signing agent
resolves competing agent contacts, without reversing applicant/agent priority.
Ambiguous signatures retain the previous policy. Do not substitute the signer
into the contact-block Name or infer email spelling from the reference workbook.

CPU production settings for this release: `PCT_AI_PROVIDER=ollama`,
`PCT_OLLAMA_MODEL=qwen3.5:4b`, `PCT_OLLAMA_DOCUMENT_MODE=source_regions`,
`PCT_OLLAMA_SECONDARY_OCR=true`, `PCT_OLLAMA_FIELD_OCR_GATE=true`; retain one PDF
worker, one API slot, two pending PDFs and the pinned installed model digest.
GPT-4o remains confined to the separate CAPTCHA adapter. The OCR name/phone
agreement shortcut never bypasses email vision verification. Optional Windows
OCR dependencies are kept in `C:\ProgramData\Menteso\pct-local-deps-20261022`
and loaded through the local virtual environment's scoped `.pth` file.

The 100-row development comparison retained 17 access failures and replayed
83 saved verified contact extractions. One changed document was independently
re-extracted from its original PDF in 64.94 seconds. Email agreement with the
human sheet is 81/83 returned rows (97.59%), or 81/100 including access failures.
This is not a fresh 100-row throughput or independently adjudicated accuracy
claim. Names/category remain weak; no 100% guarantee is established. Original
human/input sheets and historical outputs remain untouched. New policy hashes
invalidate old resume files; never force an incompatible resume fingerprint.

Release backups/receipts: `C:\ProgramData\Menteso\pct-combined-release-20261022`.
Read the current logbook receipt before assuming deployment finished. Preserve
all environment values except the explicitly scoped release settings, original
data, newer runtime state, machine tasks and the reverse tunnel on port 29010.

## PCT local Qwen activated - 21 October 2026

The `PCT_AI_PROVIDER=ollama` transport and synthetic teaching examples are
installed in the live Windows checkout. Its environment selects local
`qwen3.5:4b`, pinned to the installed digest, with one PDF worker, one API slot
and two pending PDFs. The repository template still defaults to OpenAI; preserve
the live environment during teammate deployments. Source is on
`pct-ollama-integration-20261021`; no GitHub push or merge is implied.
See `agents/pct_agent/AI_VERIFICATION.md` for provider settings and limitations.
The installed local model is Qwen3.5 4B, with no GPU acceleration detected.

The initial email-only trial matched three selected pages but averaged 169.4
seconds per page. Offline regression and saved-evidence replay are separate from
fresh model accuracy. After the earlier interrupted chat-related check, a new
real synthetic provider/schema/two-reading/report check passed in 194.33 seconds.
All 137 scoped regression tests passed; 100 saved-evidence results and checked
workbook values/formatting also matched the old pipeline. This does not establish
Qwen accuracy equivalence or the requested 500-1,000 rows/hour. Evaluate the
user's processed/unprocessed sheets in separate outputs against PDF-verified
labels; exact test filenames remain to be confirmed. No bulk extraction was
started. Do not restart an active PCT job or overwrite collected evidence.

The eight added examples teach transcription/ownership through prompts. They
are synthetic, contain no real sheet answers and do not change model weights.
Actual fine-tuning has not been performed. The SYSTEM startup task
`Menteso PCT Ollama Keeper` is installed/running, using explicit executable/model
paths with `scripts/keep-pct-ollama.ps1`. It preserves the existing loopback
listener and can start it after a desktop logout or reboot. Reboot recovery was
not tested. Pulling source alone does not install this machine task.

Only the idle local dashboard was reloaded; its keeper, model server, tunnel and
other agents were preserved. Sixty saved input/report/journal hashes matched.
Public authenticated PCT status/configuration returned HTTP 200 after restoring
SSH access for the office's changed public IP with one gateway /32 rule. No
AWS compute resources were added. Future office IP changes can break that
tunnel again; do not open SSH globally. The live route remains port 29010.

Private scoped backup, original environment, manifests and gateway-rule receipt:
`C:\ProgramData\Menteso\pct-ollama-activation-20261021`. Roll back only compatible
target source/configuration after a fresh idle check; retain all newer data.
Provider changes intentionally invalidate incompatible resume fingerprints.
CAPTCHA providers are separate and may still use paid services.

## Agent pipeline continuation — 20 October 2026

Read [the current team handoff](docs/lexmom_sub_manager/TEAM_HANDOFF_20261020.md)
for Lexmom's research, email and social packages, offline checks, isolated AWS
runtime and unfinished integrations. The branch contains development source;
private environment files, collected leads, mailbox data and live service state
are not in Git. Publishing and campaign sending remain disabled. Preserve all
PCT deployment protections and runtime boundaries below.

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

## 23 October 2026: parallel PCT experiment remains isolated

The rollback checkpoint `8021abd` is pushed as branch
`checkpoint/pct-before-parallel-20261023-095142` and annotated tag
`pct-before-parallel-20261023-095142`. Its tree matches live source `5ebad13`.
The private runtime backup and receipt are under
`C:\ProgramData\Menteso\pct-before-parallel-20261023-095142`.
Preserve newer runtime data when rolling source/configuration back.

Experimental source is on `pct-parallel-trial-20261023`, tested at `5cc65f0`.
It adds bounded independent PDF/model workers, isolated row evidence and
timing, retaining a single coordinator/writer. It is not enabled on production.
The 100-row original-PDF test extracted 83 rows, with 17 earlier source-access
failures. Total active processing plus two operational retries was 67m33s,
48.836 seconds per successful row; the 25-35-second target was not met.
Email agreement is 81/83 (97.59%), name 56/68 (82.35%), and comparable
email/name/country agreement 216/234 (92.31%). Live download/bibliography
timing and independent holdout accuracy were not measured. One name-parser
limitation remains. See `agents/pct_agent/AI_VERIFICATION.md` for definitions.

Do not turn on multiple model servers or change production worker settings
based only on the small pilots. The current CPU shares its capacity across
model copies; this is not threefold inference capacity. Production source and
environment stayed unchanged, and all 265 scoped regressions passed. The
test-only local dashboard uses port 8012; production remains on 8010/11434.

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
