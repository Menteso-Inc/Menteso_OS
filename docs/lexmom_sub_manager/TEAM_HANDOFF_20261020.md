# Agent pipeline handoff — 20 October 2026

This branch contains the accumulated Lexmom manager, research, email and social
source, dashboard integration, tests, deployment templates and historical release
notes. Existing Accountant, SEO and PCT source remains in the repository. Start
with this file and `CODEX_HANDOFF.md`; dated release notes are historical evidence,
not instructions to repeat their tests against live recipients.

## What is implemented

| Component | Source | Verified capability / remaining work |
| --- | --- | --- |
| Lexmom Sub Manager | `agents/lexmom_marketing_agent/` | Saved JSON targeting, research delegation, financial-summary semantics, inventory and activity views. Run all currently runs research; it does not activate email/social publishing. |
| Prospect Research | `agents/prospect_research_agent/` | Keyword/website discovery, bounded public-page extraction, evidence and buyer association, separate Launch/Manage fit, Hunter verification, cached inventory, checkpoints and automatic validation. JavaScript-only/blocked websites and missing evidence remain held. |
| Email Campaign | `agents/email_campaign_agent/` | Fifteen paused text drafts: five each for Launch, Manage and both; Gmail Sent/reply cache, SES events, durable reservations and suppression. Automated campaign dispatch, real product-conversion hooks and completed Pub/Sub watch remain unfinished. |
| Social Media Posting | `agents/social_media_posting_agent/` | Three LinkedIn drafts, two YouTube concepts, private media previews, platform filters, approval-bound destination/visibility, OAuth and read-only monitoring. Public publishing has not been acceptance-tested or authorized. |
| Meta Ads | `docs/lexmom_sub_manager/META_*.md` | Asset/restriction audits and proposal only. No completed Ads Manager specialist or confirmed production advertising grant. |
| n8n / WLF SDR | Migration notes and imported dashboard entries | Migrated operational state remains private on AWS. Workloads were paused; this checkout does not include their credentials, workflow database or private backup. |

## Last verified production checkpoint

The [source URL test card and bulk reader](SOURCE_IMPORT_20261020.md) are now live
on the isolated AWS Lexmom service. The authenticated public card, extraction and
Details drawer were verified on 20 October. It supports reviewed per-path HTML/JSON
recipes, bounded explicit pagination, 50-record batches, private checkpoints and
monthly completed-scope reuse. Imported observations stay outside qualified
inventory and campaigns. See [the release receipt](SOURCE_CARD_RELEASE_20261020.md)
for exact changed files, live checks and completed deployment cleanup.

The subsequent [responsive layout release](RESPONSIVE_LAYOUT_RELEASE_20261020.md)
is also live: full-width saved leads, contained tables, narrow-screen labeled
rows, wrapping filters and a shared mobile agent menu. Only three static files
were patched, with no service restart or environment/business-state change.
Final UI source is `bc104a7`; the research backend boundary remains as documented
in the source-card release. Sending/publishing remain disabled.

The related [directory-discovery update](DIRECTORY_RESEARCH_20261020.md) adds the
editable 16-source catalogue, bounded search/profile handling and durable holds.
Its reader/catalogue/backend dependencies were included in this scoped release;
the complete manager/default-profile changes were not deployed. The existing
normal-research JSON profile remains preserved. No real source is configured as
permitted for automated commercial collection. Recognized sources are not active
licensed integrations. Only the isolated dashboard service was restarted;
campaigns and social publishing remain off.

The 20 October browser check displayed 355 saved contacts: 52 qualified/verified
and 303 held. Hash comparison confirmed the four original prospect tables were
unchanged by deployment and source smoke tests. This is a freshness-dependent
snapshot, not a fixed target or proof of recipient permission.

The historical live research check on **16 October 2026** confirmed 53
research-ready contacts across 12 firms:
45 named buyer-role contacts and eight general firm inboxes. Primary routing was
50 Manage and three Launch contacts; the Launch contacts were from one practice.
There were 355 saved email contacts in total, including 302 held records. All 84
earlier contacts were preserved. These records and their evidence are private
runtime data and are deliberately absent from Git.

Qualification means sourced product relevance, not demonstrated interest or
permission to send. Verification freshness is seven days; viewing the inventory
recomputes readiness, so today's count can differ. Do not change a cached
verification's provider date or include held records to restore an old count.
The Oct 16 free balances were 236 SerpAPI searches and four Hunter credits;
recheck the actual account before new paid-provider work.

The saved `research_profile.json` requests both products, rules extraction,
free allowances only, zero model calls and a 50-contact inventory goal. It is
not a promise of 50 new contacts per click. A met and still-fresh goal reuses
saved results without new provider operations. The HTTP adapter applies tighter
run caps than the model's maximums: inspect `bounded_profile()` before changing
limits. The existing service template also has a separate process timeout.

The existing YouTube channel was connected on AWS using its owner account
`menteso.com@gmail.com`; `mail@lexmom.com` administers the Google Cloud app.
Sensitive-scope verification and revised domain ownership evidence were still
unfinished at the last checkpoint. LinkedIn Community Management product review
was pending, with no completed Page token grant. See
`GOOGLE_SOCIAL_VERIFICATION_20261015.md` before continuing either connection.
Do not rotate or replace working grants just because the browser signs out.

## Where the source runs

| Workload | Runtime boundary |
| --- | --- |
| Lexmom public workspace | `https://os.menteso.com/#lexmom/prospect_research_agent` and the Email Campaign / Social Media Posting tabs |
| Isolated Lexmom source | `/home/menteso_os/agents/lexmom_sub_manager/app` |
| Lexmom environment / dependencies | Parent `.env` and `.venv`; secrets remain on the authorized machine |
| Lexmom durable state / rollback | Parent `state/` and `releases/`; preserve existing symlinks, databases, authored media and agent memory |
| Lexmom HTTP service | `lexmom-dashboard.service`, loopback 8030, authenticated through the existing OS service |
| Research worker | `lexmom-research.service`, on demand |
| Mailbox / social reads | `lexmom-email-monitor.timer` and `lexmom-social-monitor.timer` |
| Public social writes | Publisher timer disabled/inactive at last verification; keep disabled |
| Shared OS / SEO | Existing `menteso-os` container; do not restart for an isolated Lexmom change |
| PCT | Local Windows keeper and reverse tunnel; keep AWS PCT disabled. Follow root `CODEX_HANDOFF.md`. |

The isolated adapter is `deploy/lexmom_dashboard.py`. The monolithic `server.py`
contains shared-server research/auth integration; it is not the isolated AWS
entry point. Deploy templates require an existing authorized OS/auth/gateway
installation; copying the unit files is not a complete fresh-server deployment.
Reconcile installed units, sudoers, gateway/tunnel routing and file ownership
before using a template.

The live dashboard includes scoped/inline changes and may differ from this
checkout. Back up and inspect its actual served JavaScript/HTML/styles before
patching. Preserve PCT ETA/reconnection and unrelated agent customizations;
do not replace the complete live static directory with an older checkout.

## Start development without production credentials

Fetch this branch in your own clone; do not reset an active server checkout:

```powershell
git fetch origin
git switch --track origin/codex/agent-pipeline-handoff-20261020
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Only copy the template if a local `.env` does not already exist. Keep sending,
publishing, paid generation and other automatic live actions disabled. The
template contains variable names/placeholders, not usable provider grants.
Request access to the appropriate protected AWS environment through the company;
do not put a secret, raw mailbox export, lead database or production backup in
a commit, PR, issue or chat. Never substitute another agent's mailbox token.

Offline checks used for this handoff:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s agents/prospect_research_agent -p test_*.py -t .
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py -t .
.\.venv\Scripts\python.exe -m unittest agents.lexmom_marketing_agent.test_placeholder
.\.venv\Scripts\python.exe -m pytest agents/pct_agent/test_ai_verifier.py agents/pct_agent/test_contact_ownership.py agents/pct_agent/test_accuracy_policy.py agents/pct_agent/test_overlap.py agents/pct_agent/test_parallel_verifier.py -q
node --check static/app.js
node --check static/lexmom-email.js
node --check static/lexmom-social.js
node scripts/check_pct_reconnect.cjs static/app.js
```

The manager repository harness reads root `server.py` and uses Node for UI
checks. Run that harness in the complete repository, not in the reduced isolated
runtime where monolithic `server.py` is absent. Research/engagement suites and
service-specific checks can run in the isolated runtime. Tests use temporary
data, fixtures and mocked providers; do not replace them with real sends.

## Next work for the teammate

1. Recheck current service/connection state and provider quotas before spending
   credits. The handoff does not assert today's live status from an old receipt.
2. The [public-source reader repair](PUBLIC_SOURCE_RELEASE_20261020.md) follows
   linked information pages and retains sourced people without email. Its two
   company-site smoke jobs are observations, not new qualified leads. Chrome
   controls timed out during the final visual check; that check remains pending.
   Improve independent Launch discovery; do not confuse multiple contacts at one
   firm with multiple companies. Preserve evidence, buyer association, freshness
   and domain/email deduplication.
3. Complete the email activation worker and five-step lifecycle against the real
   product event contract in `PRODUCT_EVENT_CONTRACT_20261014.md`. Coordinate
   with the active product team before editing their repositories. Missing
   consent/recipient basis, postal identity and conversion events remain holds.
4. Complete Google verification with the real owner-approved recording and
   official provider review. Keep the existing grant; do not bypass warnings or
   LinkedIn approval. No video upload is authorized by this handoff.
5. Before any later deployment, check active runs, back up only the changed
   service and take consistent database backups. Deploy the smallest compatible
   source patch, test it, and restart only its service. Retain newer runtime data
   on rollback and clean only inspected task-owned disposable build files.

Campaign sending and social publishing remain off. The completed five Azam
internal email previews from Oct 16 must not be replayed. The three LinkedIn
drafts were not confirmed mailed to Azam. A Git push does not send a review,
enable a schedule, install provider credentials or deploy an agent.
