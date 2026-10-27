# Lexmom AWS deployment

Current release: see `RELEASE_20261009.md` for the merged PCT handoff, isolated
discovery update, one-credit live test and follow-up. Discovery is deployed but
representative qualification yield is still unproven. Earlier October 7 records
below are historical checkpoints; the saved JSON profile now caps runs at one
search and remains the source of targeting configuration.

Updated 7 October 2026. This deployment is isolated from the existing Menteso OS container and its embedded SEO scheduler.

## Installed runtime

- Root: `/home/menteso_os/agents/lexmom_sub_manager`.
- Source: `app/`; dependencies: `.venv/`; credentials: root `.env` (mode 0600).
- Agent: Lexmom Sub Manager delegates to Prospect Research and Qualification.
- Unit: `lexmom-research.service`, an on-demand systemd oneshot running as `menteso_os`. No recurring timer or outbound marketing specialist is enabled.
- Input: `pilot.json`. It must use live mode. Output summary: `state/status.json`.
- Full records, evidence, checkpoints, and completion receipts: `state/runtime-data/prospect_research_agent/<run_id>/`.
- Private learning: each agent's `app/agents/<name>/memory.json`. Preserve these files during upgrades.
- Source backups and resolved dependency versions: `releases/`.
- The authenticated public `os.menteso.com` dashboard now invokes this isolated worker and displays Lexmom Sub Manager. Live progress, cancellation, evidence and JSON exports are connected.

## Credentials and limits

The user authorized reuse of the existing AWS OpenAI and SerpAPI credentials on 7 October. Only these selected credentials were copied within AWS into Lexmom's prefixed `.env` slots. Existing provider credentials were not copied to the development PC. The newly created Hunter key remains dedicated to Lexmom; its transfer to AWS used public-key encryption without putting the cleartext value in SSM commands or output.

OpenAI workload authentication passed. Hunter account authentication passed from AWS with the expected account and Free plan. The user subsequently created a dedicated Dev Team SerpAPI Free account; its key is installed in Lexmom only, with 250 searches available at provisioning. The exhausted shared key remains unchanged for other agents. Live discovery now returns results, but broad queries have returned directories and encountered timeouts/503 errors. Supplied-site qualification and broad discovery acceptance are distinct checks.

Pilot limits: five target firms, ten candidate ceiling, three searches, fifteen model calls, three verification requests, five-minute deadline, and $1 reservation ceiling. The second sample uses 20,000 input tokens and 3,000 output tokens per model call. Current configured reservations are $0.10/model call, $0.05/search, and $0.05/verification request. The deployed extraction model is GPT-4o at temperature zero; earlier runs used GPT-4o-mini at its default provider temperature. These are conservative allowances, not measured invoices; available free credits can make actual provider charges zero.

## Operations

Start an authorized run on the server:

```text
sudo systemctl start lexmom-research.service
sudo systemctl show lexmom-research.service -p Result -p ExecMainStatus
sudo systemctl stop lexmom-research.service
```

Read `state/status.json` for business status. `partial` may exit successfully but does not mean the lead target was met. A oneshot is inactive after completing; that is expected. A failed process must not be represented as a healthy or successful research batch. SIGTERM requests cancellation and preserves completed checkpoints; forced shutdown remains possible after the stop timeout.

Before replacing code, stop only this unit, back up the affected source files and unit into a new release directory, run the scoped tests, and validate the systemd unit. Preserve `.env`, state, and memory. Run `systemctl daemon-reload` only when changing the unit; never restart the shared Menteso container as part of this isolated worker's deployment.

For rollback, stop this unit, restore only the changed code and unit from the relevant `releases/before-*` backup, and reload systemd. Preserve newer records and credentials. The original deployment created a new directory and service; it did not replace an existing agent runtime. Leaving this on-demand unit stopped disables execution without deleting evidence.

## Live acceptance

Initial live attempts exposed and led to fixes for CrewAI storage permissions, discarded supplied detail URLs, website HTTP 403 errors being treated as provider authentication failures, and overly restrictive byte-based OpenAI input checks. These failures remain recorded in private run history. Completion of a live pilot and evidence review is recorded in the operations logbook; passing structural self-tests alone does not establish prospect quality or production acceptance.

### Latest verified result â€” 7 October 2026

The isolated server passed 78 scoped automated tests. The five-firm batch completed with five records requiring more research and zero qualified leads. The final focused run (`3a9e6b09fb3c42dd9b4459e69f389438`) completed with one researched firm, zero qualified leads, and zero contacts or email verifications. Renier Hotopp Law Offices had accepted evidence for its name, five attorneys, practice areas, and organization type; country evidence was missing or rejected, so it correctly remained `needs_research`.

The focused run used four page requests and one model call in 13.208 seconds, reserving $0.01 against a $0.25 ceiling (not measured billing). Its manager and specialist structural checks passed. Systemd reported process success and exit code zero; the business result remains `partial`. The service is now inactive, as expected after a oneshot run. The shared Menteso container remains healthy with its original 5 October start time.

The current `pilot.json` remains the focused one-firm profile: target one, candidate ceiling three, four model calls, three verification requests, and a five-minute deadline. Earlier five-firm profiles remain under `releases/`. No recurring runs are enabled.

At this earlier checkpoint, search quota, qualification, email verification and dashboard integration were outstanding. See the current acceptance record below; historical failures are retained.

## Dashboard operations and rollback

`lexmom-dashboard.service` runs the isolated adapter on loopback port 8030. `lexmom-dashboard-tunnel.service` forwards the gateway loopback port 28999 to it. Both are enabled on boot. The research worker remains on-demand.

Caddy sends only `/`, `/static/app.js`, `/static/style.css`, `/api/agents`, and the Lexmom API prefix to this adapter. Authentication and unrelated agent APIs still use the existing server on 8010 through the original tunnel. Each private adapter request checks the existing session; writes require admin/operator plus the exact dashboard origin. Artifact paths are manifest-checked. Sudo permission is limited to starting/stopping the one research service.

Code changes to the adapter require restarting only `lexmom-dashboard.service`. Worker code loads on its next run. Do not restart the shared `menteso-os` container or original tunnel.

Gateway configuration: `/etc/caddy/apps/os.menteso.com.caddy`. Pre-routing backup: `/etc/caddy/apps/os.menteso.com.caddy.lexmom-backup-20261007T073327Z`. To roll back routing, restore that file, validate Caddy configuration, then gracefully reload Caddy. The old dashboard placeholder will return; this does not delete research records. Stop/disable only the new dashboard/tunnel services if retiring the adapter.

Source backup: `releases/before-dashboard-20261007T072912Z`. Preserve credentials, memory and all state during rollback. Current source also exists in this workspace; credentials are excluded.

## Current live acceptance - 7 October 2026

The public dashboard successfully started and displayed supplied-site run `2b83d6f7ac4b47a2924cf7e27a5c4daa`: one researched, one qualified, one published general inbox. Hunter returned `valid`, with provider verification date `2026-09-20`; no new verification date or person/role association was invented. Evidence supports RENIER HOTOPP LAW, United States, five attorneys and a legal practice. The JSON artifact was downloaded through the authenticated UI and parsed successfully.

This run took 27.785 seconds, four page requests, three model calls and one verification request; zero searches because the site was supplied. It reserved $0.08 against a $1 ceiling, not measured billing. Two rejected name quotes triggered changed extraction strategies; the successful third extraction supplied a literal supported name. All four specialist output checks and the manager handoff checks passed. Earlier failures remain in history.

Validation: 110 distinct automated tests passed across the local suites after the added grounding-recovery case; the final 92-test specialist/runtime/dashboard suite also passed on AWS. Coverage includes SSRF and redirect restrictions, source grounding, directory exclusion, quotas, retries, cancellation/resume, secret redaction, manager handoffs, authenticated routes and exports. CrewAI emits upstream deprecation warnings.

This is a deployed on-demand research pilot with a real verified-contact demo. Representative discovery yield, high-volume reliability and customer acquisition are not established by this one-firm result. Broad searches returned third-party sites and encountered provider timeouts/503 responses; bounded async polling and a budget-counted synchronous fallback now preserve explicit failures. A targeted site search also returned unrelated results and no qualified firms. A paid search plan is not the only remaining acceptance requirement.

### Model reliability adjustment

A repeat of the mini-model demo returned a partial result (`98e84f52a1334733a711511659635411`), with an unsupported country quote. This prevents treating the earlier success as repeatability evidence. The provider client now explicitly sets temperature zero, with a regression assertion. AWS was switched to GPT-4o and a $0.10 per-call reservation, retaining the $1 run cap. At the 20,000 input / 3,000 output token limits, the published $2.50/$10 per-million-token rates imply a maximum $0.08 text-token allowance before headroom; this is reservation sizing, not a usage invoice. Source checked 7 October 2026: https://developers.openai.com/api/docs/models/gpt-4o.


### Final deployed-model acceptance

With GPT-4o at temperature zero, two consecutive supplied-site runs passed on their first extraction attempt: `3441f57193a34790b9d864f6566106bc` (15.747 seconds) and `a01d4efd398d4210a8831fad17346c9b` (17.302 seconds). Each produced one qualified firm and one Hunter-valid published inbox, used one model call and one verification, and reserved $0.15. The final manager receipt completed in 17.556 seconds with all six manager and four specialist checks passing. These are repeat runs of one firm, not two newly acquired leads or representative market validation.

Provider snapshot at 2026-10-07 08:04:58 UTC: dedicated SerpAPI Free account authenticated, 245 searches remaining; OpenAI workload verified; Hunter live verification valid with its preserved 2026-09-20 date. Snapshot values can change with later account usage. The shared Menteso container remains healthy and retains its original 2026-10-05T10:47:43.70323391Z start time. The research worker completed and is inactive normally; the dashboard and its tunnel remain running.
