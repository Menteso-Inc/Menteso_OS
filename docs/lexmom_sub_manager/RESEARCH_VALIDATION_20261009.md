# Prospect Research repair and live validation — 9 October 2026

**Status: deployed live pilot; independent discovery acceptance is still failing.**
No additional API key is currently required. Passing tests and the older
supplied-site demonstration do not prove reliable independent lead discovery.

## Deployed repairs

- Follow new published team/contact pages before retrying unsupported extraction quotes.
- Avoid repeated fetches after HTTP 429 or permanent source-access failures.
- Permit same-site www/apex redirects with DNS, TLS and robots checks intact.
- Read bounded business JSON-LD, including explicit addressCountry.
- Exclude publisher contacts from firm-contact results.
- Retain completed qualification over longer incomplete extractions.
- Preserve configured queries across extraction retries; reject mismatched provider queries.
- Classify additional known news/directories and simplify saved search phrases.

Targeting remains in `agents/lexmom_marketing_agent/research_profile.json`.
No outreach or recurring research schedule is enabled. Worker is idle.

## Validation and actual outcomes

Local combined suite: **148 passed**. AWS staging: **147 passed, one browser-dependent check skipped**.
Only the isolated Lexmom dashboard restarted. Shared container start time stayed
`2026-10-05T10:47:43.70323391Z`. PCT and paused n8n/WLF workloads were preserved.

| Live run | Searches | Model calls | Verifications | Qualified | Needs research | Excluded | Reserved USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `49117ae37ad54b2f9162fc02439bbbc7` | 1 | 9 | 0 | 0 | 4 | 2 | 0.95 |
| `5de2250931b1467eab2edb852d12a206` | 1 | 1 | 0 | 0 | 1 | 1 | 0.15 |
| `3830c79ee5964023ab440cdd487bd82f` | 1 | 1 | 0 | 0 | 0 | 1 | 0.15 |

Rows are separate run outcomes, not unique leads. Reservations are conservative
estimates, **not actual billing**. Search balance: 244 → **241**. No Hunter
verification credits used in these runs. The dashboard aggregate includes one
previously qualified supplied-site result, not new discovery success today.

The first run found genuine firms but lacked explicit country/headcount evidence;
one firm was too large. Later searches mostly returned directories or unsupported
URLs. The latest nine-result page had seven URLs rejected by the URL policy, one
directory index excluded, and one directory blocked by robots HTTP 403.
Rejected raw URLs were not retained, so the audit cannot establish whether all
seven rejections were necessary. The unofficial SerpAPI history-list endpoint
returned HTTP 403. No further search was purchased to investigate it.

Remaining work: preserve sanitized URL rejection diagnostics and search archive
IDs; assess benign public URL parameters; improve search diversity/query rotation;
then demonstrate independently discovered firms with sourced fit and verified
published contacts. Do not weaken source grounding to inflate qualification counts.

## Required keys

| Variable | Evidence |
| --- | --- |
| `PROSPECT_RESEARCH_AGENT_OPENAI_API_KEY` | Successful live gpt-4o extractions |
| `PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY` | Successful searches/account HTTP 200; 241 remaining |
| `PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY` | Account HTTP 200; 49.5 credits and 99 verifications remaining; earlier verification returned valid |

Keys remain in the private AWS `.env`. Hunter account readiness is distinct from
a fresh successful email verification. Provider state preserves the old verification
timestamp and records the newer account check separately. n8n/WLF credentials did
not replace the active Lexmom keys.

## Release and evidence

Runtime: `/home/menteso_os/agents/lexmom_sub_manager`.
Releases: `releases/completion-20261009/` and `releases/discovery-query-20261009/`.
Rollback `before/`, activation manifests, test logs, secrets and state remain.
Cleanup receipt: `RESEARCH_CLEANUP_20261009.json`. Previously blocked verification
copy cleanup was not retried. Local source changes remain uncommitted.

Authenticated visual inspection confirmed Lexmom Sub Manager, both tabs, the latest
partial results table, and n8n/WLF sidebar entries. Actual billing and revenue
attribution remain unconnected.
