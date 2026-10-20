# URL source tests and bulk batches — 20 October 2026

The source test card and bounded reader are deployed on the isolated AWS Lexmom
service. See [initial deployment evidence](SOURCE_CARD_RELEASE_20261020.md) and
[the public-source repair and cleanup receipt](PUBLIC_SOURCE_RELEASE_20261020.md).
No real directory was enabled or downloaded. Campaign and social write switches
remain off.

## User flow

The Prospect Research workspace has a **Test a source** card on the left on
desktop, above the table on smaller screens. Submit a public website, directory
or reviewed JSON API URL. An ordinary readable website follows returned contact,
team, about and named profile links on the same site, without a site-specific
reader. Recognized directories still require current recorded use
rights and live source checks. A supported URL is not a claim that the source
allows bulk reuse or exposes its whole database.

The separate preview table shows source observations, names/emails when
published, firm/role, country, change status and a Details drawer with evidence,
original retrieval time, JSON path where applicable and source/website links.
It does not inflate the qualified lead table or enroll anyone in email campaigns.
Primary-firm research, separate Launch/Manage qualification and current email
verification are still required in the existing research workflow. This preview
does not automatically run that downstream workflow or spend its provider credits.

The card accepts different source domains rather than only the sixteen catalogue
seeds. A new directory, unknown API schema, blocked/JavaScript-only source or
unsupported query gets a held/setup-required result; it is not silently treated
as an empty successful download. Literal "any URL extracts all data" is not a
capability: private/internal addresses, credential URLs, nonstandard ports and
unreviewed navigation are blocked.

### Public-site repair and repository inspection

The public reader uses `lxml`, the parser also used by Scrapy's maintained HTML
link extractor. It recognizes semantic contact links, nested person/role cards,
mailto links and React's explicit streamed Suspense segments without executing
page scripts. A person's name and published role remain observations even without
an email address. Adjacent cards, generic inboxes and unrelated external emails
are not combined into a made-up person/company association. Hidden elements and
script text are excluded. These facts still do not establish product fit.

Public jobs retain checked/skipped-page evidence and use a parser revision in
their cache key, so old one-page results do not hide repaired extraction. They
allow at most 30 pages per test, 100 observations per page and the existing
50-observation/ten-page batches. Broken or robots-blocked linked pages are
recorded and skipped; seed failures and access denials stop the job. Source
pacing persists between batches. No search, model or email-verification calls
are made by this reader.

References actually inspected: [Scrapy link extraction source](https://github.com/scrapy/scrapy/blob/master/scrapy/linkextractors/lxmlhtml.py),
[Scrapy persistent jobs](https://docs.scrapy.org/en/latest/topics/jobs.html),
[Firecrawl crawler source](https://github.com/firecrawl/firecrawl/blob/main/apps/api/src/scraper/WebScraper/crawler.ts)
and [Firecrawl self-hosting](https://docs.firecrawl.dev/contributing/self-host).
Scrapy's bounded navigation, parsing, throttling and job persistence are useful
patterns. Our existing transport/checkpoint boundary is retained. Full Scrapy
and Firecrawl are not installed; no Firecrawl source is copied. Firecrawl's
TypeScript/multi-service runtime would add an unnecessary second crawler for
the two supplied sites, which expose usable public HTML. JavaScript-only apps
are not claimed to be supported by this change.

Avvo stays restricted under its website terms; the catalogue now points to the
website terms rather than suggesting its API terms alone govern HTML collection.
An extraction library does not change that source-access decision.

## What dynamic means

`DirectoryRule.collection` is the default reviewed reader. Optional
`collection_routes` select different readers by the longest matching path prefix,
so one site can have different index, profile and API layouts. Existing
`profile_path_prefixes` remain the independent access boundary, including any
explicitly reviewed listing/feed paths. Config changes never grant themselves
collection rights.

- HTML recipes specify record containers, field selectors, profile links and
  the next-page link. Supported selectors are bounded descendant combinations
  of tag, `#id` and `.class`; no JavaScript, arbitrary expressions or executable
  model-generated parsers. Values stay inside their record container. Duplicate
  email fields are withheld and multiple next destinations hold navigation.
- JSON recipes specify the record-array path, explicit lead-field mappings and
  a next-URL path. Extra payload fields are not exported. Dotted object paths are
  supported; arbitrary JSONPath/code and guessed array traversals are not.
  Missing array/next fields and incompatible response types hold the job instead
  of claiming that the database ended. An explicit empty array and null/empty
  next URL can end a reviewed JSON feed.
- Only explicitly returned profile/next links are followed. HTML path pagination
  and JSON next URLs are supported. Cursor-only APIs that do not return a usable
  URL, browser-only pagination, GraphQL/POST APIs and downloadable database/CSV
  files require an additional adapter; this change does not pretend to support them.
- Authenticated JSON feeds can name a dedicated
  `PROSPECT_RESEARCH_AGENT_SOURCE_*_KEY` or `*_TOKEN` environment variable.
  `Authorization: Bearer` or `X-API-Key` are supported only on the exact HTTPS
  homepage host. Credentials are never sent to robots/terms or another host.
  Add each actually configured variable to `.env.example`; never put a real key
  in a recipe, pasted URL, browser form, log or Git. No real feed key was configured.
- API queries are limited to reviewed pagination keys. Page/offset values are
  numeric; limit/page-size values cannot exceed 100. Queries are canonicalized
  so changing parameter order does not duplicate a saved scope. Arbitrary filter,
  signature or authentication query parameters require a separate reviewed adapter.

Example **synthetic layout**, not permission to enable a real provider:

```json
{
  "collection_routes": [
    {
      "path_prefix": "/lawyers",
      "reader": {
        "format": "html",
        "record_selector": "article.lawyer",
        "field_selectors": {"name": "h2", "email": "a.email", "role": ".role"},
        "next_selector": "a.next"
      }
    },
    {
      "path_prefix": "/api/lawyers",
      "reader": {
        "format": "json",
        "records_path": "data.people",
        "field_paths": {"name": "full_name", "email": "email", "firm": "company.name"},
        "next_path": "paging.next",
        "query_keys": ["page", "limit"]
      }
    }
  ]
}
```

The real source rule still needs the collection/storage/commercial-use review,
terms hash, dated permission reference and finite page/delay limits documented in
[directory research](DIRECTORY_RESEARCH_20261020.md). No recipes for held real
providers were guessed from their brands. No real catalogue source is permitted.

## Batch progress and monthly revisit behavior

One source job runs at a time. A page/API response can supply many records in a
single request; each batch adds at most 50 observations, with up to 100 records
per reviewed response. Remaining records are buffered, so continuing a 60-row
response reads its last ten rows without downloading it again. A completed page
is not revisited within a partial job. Duplicate email contacts are removed.
Name-only observations retain their source identity rather than merging common
names across unrelated profiles.

Each batch has a 120-second deadline, 15-second request timeouts, at most ten
content pages and twenty total HTTP requests including robots/terms/redirects.
The stricter reviewed per-source page cap and crawl delay still apply. Clicking
**Continue batch** is required to start another bounded batch. Five hundred
observations per test job is a hard ceiling; narrow the reviewed feed scope to
proceed further. No endless crawler or uncontrolled whole-database download runs.
An additive private `source_requests` table reserves request slots transactionally
across source-test URLs, explicit batches and worker restarts. Starting a new test
does not reset its source's pace. Waiting beyond a deadline leaves resumable work;
it does not manufacture a permanent source-denial hold.

Private JSON checkpoints contain the selected URL, rule/reader fingerprint,
visited pages, pending queue, unread buffer and observations. A completed scope
can be reused for the rest of its **UTC calendar month**, preserving original
retrieval times. Permission reviews and persisted holds are still checked and,
for permitted sources, the live terms are rechecked before cache reuse. Changed
rules/reader revisions invalidate that cache. A requested refresh or a later-month
test re-reads the selected scope and marks new, changed and unchanged records.
This is on-demand behavior, not a newly enabled monthly scheduler.

"Selected page only" never means site exhausted. "Reviewed URL feed exhausted"
only covers that configured URL, returned links, filters and navigation contract.
A partial/error/blocked run never sets a completion timestamp or month-long skip.
Pagination loops, off-host links and paths outside review are held. HTTP denial,
rate-limit and changed-terms holds persist in the existing private source store.

## Runtime boundary and validation

`source_formats.py`, `source_import.py` and `source_api.py` are deterministic tools
inside the existing Prospect Research specialist, not another created employee.
Routes live under `/api/agents/lexmom_marketing_agent/source-imports`; both local
and isolated AWS adapters register them. They require authenticated admin/operator
access, same-origin writes, bounded input and private no-store responses. Only
the server accepts/configures recipes and credentials. Browser requests cannot
raise budgets, start search/model/verification work, modify source permissions,
send emails or publish social posts.

State is under the existing private research directory's `source-imports/`.
Keep it, the source-hold database and existing private data/environment during
deployment. Source jobs are single-worker; process locking serializes collection
across adapters sharing the same state. Do not delete checkpoints or release
source holds just to clear a stopped status.

Offline fixtures exercise different HTML layouts, same-site layout routing, JSON
pagination, 50-row buffers, monthly reuse/refresh, changes/deduplication, source
limits, dangerous navigation, source denials, dedicated credential boundaries and
HTTP authorization. No real source/API operation or research-provider credit was
used. Provider-specific feed fees are not inferred to be zero merely because
SerpAPI, Hunter and model operations are absent.

An initial AWS identity failure delayed deployment. After the authorized Devteam
session was renewed, the source card was deployed and verified in the authenticated
public dashboard. Only `lexmom-dashboard.service` was restarted. Two selected-page
smoke tests returned zero and one unverified observations, respectively; no search,
verification or model operations were used. The four original prospect tables and
the environment file passed before/after hash checks. Task-owned transfer/staging
files were removed after verification; rollback and business state were retained.
The saved normal-research profile and complete manager source were not replaced.
See `SOURCE_CARD_RELEASE_20261020.md` for the precise deployment boundary.
