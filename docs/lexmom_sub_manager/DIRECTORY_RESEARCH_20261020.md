# Lawyer-directory research — 20 October 2026

The user requested directory-led discovery before Apollo. The saved research
profile now enables `discover_directories`. This update is source/tested code;
it has not been deployed to AWS. No live collection run, provider credit
operation, email, upload or change to unrelated services is part of this work.

The user's final clarification is worldwide lawyer discovery. The saved profile
uses `countries: []` and `priority_countries: []`; US/Australia were examples, not
a fixed targeting list. International directory queries and solicitor/advocate
terminology supplement the existing sources. Optional explicit country targeting
is available for future runs. Inventory/qualification keys are preserved. US
product hosting is user-provided context; assess each firm's requirements without
inferring acceptance, consent or residency compliance from its country.

## Pipeline

1. Interleave general directory and site-targeted queries with the existing
   firm-website queries. Query reservation/rotation, country targeting, free
   allowance checks and the existing three-search saved limit remain in force.
2. Recognize the 16 configured sources and identify unfamiliar directories from
   explicit directory/claim-profile signals. Unknown sources remain review
   candidates; they are not silently added to the permitted source list.
3. Check recorded collection, storage and commercial-research rights before
   fetching any directory profile. Public visibility and a working HTTP response
   are not permission. A robots allow rule is a technical condition, not a data
   licence. An IP denial is a stop signal, not the first point at which terms apply.
4. For a source with an applicable recorded permission, check that its review is
   current, re-fetch its reviewed terms document and compare the full bounded
   visible-text SHA-256. Changed/unreadable terms hold collection. Respect live
   robots rules, delays, reviewed profile paths and per-source page caps.
5. Read only bounded profiles returned by discovery or explicitly supplied.
   Save explicitly associated names, roles and published emails with source
   excerpts/timestamps in `data.directory_profiles`. Never infer missing emails.
   Directory operator/footer contacts and ambiguous associations are withheld.
6. Follow one unambiguous, explicitly labelled official firm website. Apply the
   existing primary-source identity/location/attorney-count checks, separate
   Launch/Manage assessments, contact affiliation, deduplication and fresh email
   verification. A missing website does not prove no website exists: keep that
   profile unresolved. A directory listing does not prove product need or interest.
7. Keep directory observations separate from qualified/verified lead totals.
   The dashboard has one collapsed source-status table and source/terms details
   in discovery decisions. Existing lead counts and Details drawer remain intact.

## Editable catalogue and source status

`agents/prospect_research_agent/directory_sources.json` contains the search
themes, known source hosts, notes, reviewed terms and limits. It contains no
credentials or customer data. The catalogue currently recognizes Justia, Avvo,
FindLaw, Martindale-Hubbell, Lawyers.com, Nolo, LawInfo, Abogado, HG.org,
Lawzana, Justdial, LawRato, The Lawyers Global, Super Lawyers, The Legal 500
and Chambers and Partners. Recognition does not assert a current data licence.

As checked on 20 October:

- [Justia's terms](https://www.justia.com/terms-of-service/) restrict commercial
  copying/exploitation. The configured state is `restricted` for this use.
- [Avvo's published API terms](https://www.avvo.com/support/api_terms_of_use)
  prohibit bulk access, retained copies and direct-marketing lists. Standard
  API access is not a suitable grant for this workflow; state is `restricted`.
- [FindLaw's terms](https://www.findlaw.com/company/findlaw-terms-of-service.html)
  incorporate [Internet Brands' terms](https://www.internetbrands.com/ibterms),
  whose collection/aggregation restrictions need an applicable written exception;
  the configured state is `restricted`.
- The remaining sources are `review_required`. Their current permitted terms
  and any applicable separate agreement have not been established. **No real
  source is configured as permitted by this change.**

An operator may set `permitted` only when the actual use is covered. The schema
requires dated review, affirmative collection/storage/commercial-purpose rights,
a non-secret permission reference, reviewed policy URL/hash, bounded profile-path
prefixes and conservative limits. A public policy that expressly permits the use
can be the reference; an extra paid licence is not assumed universally necessary.
Do not put private signed agreements or credential/account IDs into this public
JSON. Record protected evidence privately and use a non-secret descriptive
reference here. A browser account or advertising subscription is not itself such
evidence. API-only licences need their own API adapter; the HTML reader does not
infer that an API grant permits website collection.

`reviewed_terms_sha256` uses `terms_digest()` on the full visible UTF-8 terms
document parsed by `_PublicHTML` (its joined `parts`, not the 60k business excerpt).
The default review lifetime is 30 days, at most 90. Changing collection paths,
rights or terms requires a corresponding review; the worker does not grant itself
permission or rewrite the catalogue.

## Denials and recovery

The existing safe transport keeps DNS/IP validation, pinned TLS, no proxy use,
bounded bodies, same-site redirects, deadlines and cancellation. Directory
redirects also stay inside reviewed profile paths. No CAPTCHA solving, proxy/IP
rotation or login bypass is added.

- HTTP 401/403/451 or a human/browser challenge: stop that source, persist an
  operator-review hold and continue other eligible sources.
- HTTP 429: persist a pause of at least 24 hours and at least the supplied
  `Retry-After`. An extreme value requires review instead of an early retry.
- Changed/unreadable terms: persist a review hold; no profile is fetched.
- Robots denial or a page/cost/time ceiling: stop that operation. A fresh or
  recorded permission never overrides robots or remaining run budgets.

Holds are an additive `source_holds` table in the existing private
`prospects.sqlite3`, independent of campaign/profile selection and retained across
restarts. No existing firm/contact rows are removed or requalified by migration.
After resolving the actual cause, an operator can call
`ProspectStore.release_source_hold(host)` in the authorized environment. Automatic
research retries never release these review holds. Do not replace live databases
with a development copy or delete holds just to get a green status.

## Validation and deployment

Offline tests use explicit synthetic permissions and simulated HTTP responses;
they do not imply real directory approval. They cover permitted profile-to-firm
research, held/unknown sources, changing/expired terms, robots, access denial,
challenges, rate limits, persistent holds, path/redirect controls, contact evidence,
budget sharing, source rendering and existing research/email/social behavior.

Deploy only the reviewed Lexmom source/UI patch using the isolated runtime
procedure in `TEAM_HANDOFF_20261020.md`. Preserve live state/environment and the
custom public static asset/PCT changes. Existing tables are extended on open;
rollback can restore source files while preserving the newer database, including
the unused extra table. Do not restart the shared OS, local PCT or unrelated
agents. Keep campaign sending and social publishing disabled.
