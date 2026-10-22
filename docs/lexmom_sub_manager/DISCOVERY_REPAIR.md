# Prospect discovery repair — 9 October 2026

Status: deployed after PR #9 was reviewed and merged on 9 October. The first bounded live test used one search credit and returned zero qualified firms; follow-up fixes address observed triage/retry gaps. See `RELEASE_20261009.md` for exact evidence and current acceptance limits. Simulated successful results are not real leads.

## Repaired workflow

1. Read the saved research profile and recent completed research for the same targeting criteria.
2. Search within the existing query limit. Retain bounded title, snippet, query, position, source URL and collection time. Reject unsafe URLs without storing their query credentials.
3. Rank the whole result page before applying the candidate allowance. Flag unrelated results, excluded domains, duplicate domains and recently researched firms. Keep decisions for deferred candidates as well.
4. For supported public directory profiles, read their published website links. Follow a single unambiguous labelled website destination; multiple destinations or missing links remain unresolved. This is not an Apollo integration or bulk directory collector. Destination ownership still has to pass official-firm qualification.
5. Read the candidate's first page. Request team/attorney pages for missing size and contact/office pages for missing country or email. All follow-up pages share the same three-content-page allowance; failed pages also use it. A failed page can fall through to another published link if allowance remains. No additional model call occurs solely because missing facts remain when there is no new page, except an explicitly diagnosed extraction/grounding retry.
6. Validate extracted facts against literal page evidence. Keep unknown size/country/contact identity unresolved. A partial team list is not evidence of total firm size. A qualified firm is not proven buying intent.
7. Verify published emails within the verification allowance. Save qualified, excluded, unfinished, failed, duplicate and previously known outcomes and reasons in `data.candidates`. Partial grounded records survive cancellation or budget exhaustion. Earlier search candidates survive a later source-provider error.
8. Show saved decisions inside the Prospect Research results under a collapsed Discovery decisions table. The business overview stays compact.

## Reuse policy

`research_freshness_days` defaults to 30 in the JSON profile. Set it to 0 for a deliberate fresh research run. Reuse checks completed, schema-valid, self-tested live artifacts with matching product, countries, segments, buyer roles and size criteria. Query words and per-run cost limits do not invalidate recent fit research. Fixture records, third-party directory/news records, failed validation, unresolved firms and expired records are not treated as reusable completed research. Bad saved artifacts produce a warning and do not fabricate a known lead.

A known firm is skipped before website, extraction and verification requests; its earlier run ID remains in the decision record. It does not count as a new qualified firm toward the current run's target. This is a read-only history scan, not a CRM or an outreach permission system.

## Offline verification

- The existing combined Lexmom, runtime, source, workflow and dashboard suite plus 15 new discovery tests passed (131 tests).
- Two additional regressions passed: legacy-profile resume compatibility and ignoring old excluded directory listings in the firm cache. The existing cancellation/resume check also passed with a new no-duplicate-audit assertion (133 distinct tests verified overall).
- End-to-end simulations use the real source tools, public URL/robots rules, run budgets, qualification, persistence and mocked provider/HTTP responses. They exercise ranking, team/contact follow-up, email verification, directory resolution, ambiguity, history expiry/profile changes, duplicate skips, corrupt history, provider failures and partial preservation.
- JavaScript syntax, PCT reconnection checks and whitespace checks passed. PCT code, deployment guards, secrets and live data were not changed.
- No live SerpAPI, Hunter or LLM research calls were made. Live performance and discovery yield remain unproven.

## First live test boundaries

Keep the existing saved profile: no supplied seed websites; global solo/small/mid-size law firms, 1–50 attorneys. Maximum 1 new search request, 10 candidates, 3 content pages per firm, 15 model calls, 3 verification requests, 300 seconds and $1 conservative cost reservations. These are simultaneous upper bounds; the first exhausted bound stops further work. The desired 5 qualified firms is a target, not a guaranteed result. Archive polling does not create another configured query, and provider accounting must still be reconciled separately.

Before production deployment, follow CODEX_HANDOFF.md: incorporate reviewed/merged PR #9, preserve the actual customized public JavaScript and PCT reconnection/ETA fixes, keep PCT local and disabled on AWS, and use only the isolated Lexmom deployment. Check live service state and retain rollback assets. After deployment, assess a bounded independent search run separately from these offline checks; do not label milestone one complete from simulated data.
