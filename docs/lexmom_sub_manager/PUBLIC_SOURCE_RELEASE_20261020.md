# Public source extraction repair — 20 October 2026

Source commit `caf01cfc4d330e280af7997b499b51f8102a31e4` is deployed on the
isolated Lexmom AWS runtime. The source test now follows public contact, team,
about and named profile links without a site-specific recipe. It retains
published names/roles without requiring an email and handles explicit React
streamed HTML. Checked/skipped pages are exposed in the preview. Existing
verification, qualification and campaign eligibility are not inferred from
these observations.

The repository inspection and reader boundaries are documented in
[source imports](SOURCE_IMPORT_20261020.md). The repair uses lxml, also used by
Scrapy's link extractor. Full Scrapy and Firecrawl services were not installed,
and no Firecrawl source was copied. The isolated environment received the
tested lxml 6.1.1 wheel with no dependency upgrades; the repository requirement
is explicit for fresh installations. No new API key is required.

## Deployment and verification

Only the changed source reader, catalogue note, two test files and scoped
dashboard assets were installed. The actual customized live JavaScript was
patched by matching its prior research-workspace region. Shared OS/PCT changes
were preserved. Only `lexmom-dashboard.service` was restarted. Source jobs were
idle before installation; research and public social publishing were inactive.

- All **214 research tests passed in AWS staging** before runtime replacement.
  Thirty-nine focused parser/import tests and 113 related Lexmom tests passed
  locally. The actual static patch passed JavaScript syntax and PCT reconnect
  checks; public served JavaScript/CSS hashes matched the deployed release.
- Anonymous source API requests returned 401. Existing role, same-origin and
  private-response checks passed in offline API tests.
- Direct AWS source jobs completed against the two supplied company websites:

| Source | Pages read | Source records | Distinct names within source | Published emails |
| --- | ---: | ---: | ---: | ---: |
| IIPLA | 7 | 40 | 39 | 1 |
| World Lawyers Forum | 5 | 14 | 14 | 0 |

Names can overlap between sources; these totals are not verified or qualified
lead counts. The completed IIPLA scope was reused without another download.
Both jobs used zero SerpAPI searches, verification calls and model calls. The
Avvo test remained held under its website terms, with zero pages/records and no
attempted access bypass. The catalogue explanation now references website terms
rather than only API restrictions.

- The four original prospect tables (`firms`, `observations`, `queries`,
  `reservations`) matched their consistent pre-deployment backup by full-row
  hashes. All private source observations/checkpoints were retained. The
  environment hash and shared container start time remained unchanged.
- Campaign and social write flags stayed off. No campaign, internal preview,
  social post, credential rotation or account-access change was performed.
- The authenticated browser showed the updated source-card description. Later
  clicks and screenshots timed out in Chrome, including a fresh tab, so final
  table/drawer visual verification remains pending. Server source jobs and
  deployed asset hashes were verified independently; no screenshot is claimed.

The release keeps its `before/` source/static backups, `prospects-before.sqlite3`,
`before.json`, `receipt.json`, `verification.json`, `tests.log`, `dependency.log`
and `cleanup.json` under the protected AWS release directory. Rollback restores
code/assets, not older business data. Keep the new dependency if rolling back
only this reader; it is isolated from the shared OS runtime.

## Cleanup

Only inspected task-owned disposable copies were removed. No preview process
was started for this repair, and no service was stopped for cleanup. Symlinks,
protected data files and containment were checked before deletion. Runtime
state, collected pages/observations, all environment files, source, helper
scripts and rollback releases were preserved.

AWS release root:
`/home/menteso_os/agents/lexmom_sub_manager/releases/20261020-public-source-discovery`.

| Removed child | Files | File bytes |
| --- | ---: | ---: |
| `stage` | 94 | 1,285,999 |
| `transfer-source.tar.gz` | 1 | 23,209,123 |

AWS measured available space: **78,024,011,776 → 78,048,747,520 bytes**.

Local task root:
`C:\Users\hp\Desktop\Menteso\Menteso_OS\runtime-data\source-flexibility-20261020`.
Native PowerShell LiteralPath operations removed these exact children:

| Removed child | File bytes |
| --- | ---: |
| `live-app.js` | 276,755 |
| `live-style.css` | 95,015 |
| `patched-app.js` | 277,243 |
| `patched-style.css` | 95,297 |
| `deploy.sh` | 8,064 |
| `firecrawl-crawler-reference.ts` | 40,239 |
| `__pycache__` (one disposable diagnostic bytecode file) | 3,961 |

Local measured available space: **23,001,874,432 → 23,002,681,344 bytes**.
Detailed inspection/removal receipts remain private. No live contacts, raw source
responses, screenshots, secrets or cloud account identifiers were committed.
