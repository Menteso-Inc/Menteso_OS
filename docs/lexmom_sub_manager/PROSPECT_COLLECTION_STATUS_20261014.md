# Prospect collection checkpoint — 14 October 2026

The requested target is at least 50 named law-firm contacts for Manage/Launch research. It has **not** been met as 50 qualified or send-ready leads.

## Actual collection and limits

- Hunter's free company discovery returned 100 company/domain hints without spending a SerpAPI search credit. Its classifications include associations, public bodies and outdated/misclassified businesses; they cannot establish a qualified law firm or an attorney count.
- Fourteen cached, filtered Hunter domain lookups returned **67 named contact candidates with 67 unique email addresses**. Empty lookups consumed no observed credit. Account reconciliation showed 10 free Hunter credits used, **39.5 remaining**, with no paid plan or model use.
- Primary-source checks inspected available firm websites/profile URLs through the existing robots/DNS/TLS/size/timeout guards. The current cached audit has **15 contacts with primary-source name/email association**, **0 fully qualified firms** and **0 research-ready contacts**. Missing country/count/role evidence, catch-all/undated or stale verification, and inaccessible sources remain holds. No provider claim was silently converted into primary evidence.
- This collection consumed **0 additional SerpAPI searches**, **0 Email Verifier calls**, **0 paid inference calls** and sent **0 emails**. The latest earlier free SerpAPI account read showed 240 searches remaining.
- Source data is private under `runtime-data/lexmom-leads-20261014/`: `provider_candidates.json`, `primary_records.json` and `primary-source-cache/`. It is ignored by Git. Do not expose the 67 candidates as 67 qualified leads or count generic inboxes as people.

## Prepared extraction repair

The local Prospect Research implementation now reads bounded published Person metadata, explicitly bounded team cards and single-person profile headers. Name/email identity is separate from a proven current buyer role. Generic and footer addresses remain unassigned to people; retired/former roles do not match current buyers. A profile can improve a previously unassigned root-page inbox. Named contacts take priority over unassigned inboxes in the bounded contact list. Repeated incidental firm facts no longer exhaust the evidence capacity before contact evidence is stored.

The free-credit guard now prefers Hunter's unified credit ledger over legacy verification counters. Missing, exhausted or invalid unified balances fail closed rather than using a misleading legacy allowance.

**128 Prospect Research tests passed** in the existing local project virtual environment, including new regressions for person/card/profile source grounding, assistant/footer separation, generic/third-party mailboxes, unknown/retired roles and the unified credit guard. An initial test invocation used the global Python runtime, which lacked declared research dependencies; the completed checks used the project's existing `.venv` without installing dependencies.

These repair files are **local and not yet deployed**. The AWS read-only check confirmed the isolated research service was idle, dashboard/monitor timer active, and the shared container retained its October 5 start time. No research deployment, container restart or production source mutation was performed in this checkpoint.

## Remaining work

Continue primary-source corroboration and discovery until there are at least 50 suitable named contacts, improve coverage of size/location and buyer-role facts without guessing, retain separate Manage/Launch assessments, deploy the tested isolated repair and show the verified inventory in the dashboard. A public profile without a proved current buyer role stays on hold. Verify only appropriate eligible addresses within preserved free allowances; keep all outreach disabled.

The owner subsequently requested a new Social Media Posting Agent. Its separate build plan is `SOCIAL_AGENT_PLAN_20261014.md`; creating that agent requires the new-agent plan approval mandated by AGENTS.md. This checkpoint preserves the unfinished 50-contact requirement rather than marking it complete.
