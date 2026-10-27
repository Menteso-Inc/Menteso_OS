# Source test card deployment — 20 October 2026

The **Test a source** card is live under Lexmom Sub Manager → Prospect Research
at `https://os.menteso.com/`. It reads the selected public page or a configured,
reviewed feed and displays separate unverified observations with an evidence
drawer. It does not claim that one page covers an entire website or promote
observations into qualified leads automatically.

## Release boundary

Runtime source commit: `1869d1c3ad2b4b67b45f7f1907fa47c9904bae9a`.
Release directory: `/home/menteso_os/agents/lexmom_sub_manager/releases/20261020-source-test-card`.

Installed eleven runtime source files: research `agent.py`, `directory_sources.json`,
`directory_sources.py`, `discovery.py`, `models.py`, `source_api.py`,
`source_formats.py`, `source_import.py`, `tests.py`, `tools.py`, and
`shared/prospect_store.py`. Added source-route registration to the existing
customized isolated adapter. Patched only the research-workspace region/binder
in live JavaScript, appended source-card CSS and updated static cache versions
in the actual live HTML. Existing PCT and unrelated dashboard customizations
were preserved. An initial static hash mismatch stopped the installer before
any live writes; it was resolved by inspecting the actual isolated HTML and
using that as the baseline.

Only `lexmom-dashboard.service` was restarted. The shared `menteso-os` container
start time was unchanged. Research was inactive; the social publisher timer
remained inactive. The normal-research profile, complete manager module,
environment, private state, provider grants and shared deployment workflows were
not replaced. No real catalogue source was enabled. This release does not assert
that all directory-discovery manager/default-profile changes are deployed.

## Verification

- All 201 research checks passed in AWS staging. The scoped actual-live JavaScript
  passed syntax, manager UI and PCT reconnect checks locally.
- Public served JavaScript/CSS hashes matched the installed release. Anonymous
  source API requests returned 401.
- Authenticated browser tests covered two selected public pages: zero observations
  on one page, one published contact on the other. The evidence drawer opened and
  closed correctly. Both jobs completed only their selected-page scope.
- Source observations remained `not_checked` and ineligible for outreach. Both
  jobs used zero search queries, email verifications and model calls. No campaign
  email or social content was sent or published.
- The original `firms`, `observations`, `queries` and `reservations` SQLite tables
  matched the consistent pre-deployment backup by full-row SHA-256 comparisons.
  The environment file hash was unchanged. New source-import state was preserved.
- The dashboard showed 355 saved contacts: 52 qualified/verified and 303 held.
  Readiness changes with verification freshness; these are existing records,
  not leads produced by the two source tests.

The current 50-observation batch and 500-observation test ceilings, reviewed
navigation, access restrictions and source-specific pacing still apply. API and
directory sources require the appropriate reviewed reader/access configuration.

## Cleanup receipt

After verification, exact disposable paths were rechecked for containment,
symlinks, protected files and byte counts before removal. No service or preview
process was stopped for cleanup.

AWS paths removed:

| Exact path | Files | File bytes |
| --- | ---: | ---: |
| `/home/menteso_os/agents/lexmom_sub_manager/releases/20261020-source-test-card/stage` | 94 | 1,607,660 |
| `/home/menteso_os/agents/lexmom_sub_manager/releases/20261020-source-test-card/transfer-source.tar.gz` | 1 | 23,197,205 |

AWS measured available space: **78,047,141,888 → 78,072,193,024 bytes**.
The `before/` source/static backups, `prospects-before.sqlite3`, `before.json`,
`receipt.json`, `verification.json`, `tests.log`, `cleanup.json`, live app/state,
environment and dependencies remain preserved.

Local root: `C:\Users\hp\Desktop\Menteso\Menteso_OS\runtime-data\source-card-deploy-20261020`.
Each exact child listed below was removed using native PowerShell `LiteralPath`
operations after containment, reparse-point, size and exclusive-open checks:

| Child path | File bytes |
| --- | ---: |
| `live-app.js` | 263,166 |
| `live-style.css` | 80,964 |
| `live-index.html` | 10,347 |
| `patched-app.js` | 271,923 |
| `patched-style.css` | 82,476 |
| `patched-index.html` | 10,354 |
| `deploy.sh` | 10,445 |

Local measured available space: **15,885,516,800 → 15,886,262,272 bytes**.
These were duplicate download/build/transfer artifacts; required deployed and
rollback assets remain on AWS and repository source remains in Git. Private
helpers, compact evidence, the review screenshot, source jobs and all environment
files were retained. No broader cache, shared dependencies or unrelated task
directory was cleaned. Private detailed receipts are retained locally; no live
contact records, screenshots, credentials or account/instance identifiers are
included in this repository note.
