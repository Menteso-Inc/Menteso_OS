# PCT source verification and contact selection

Updated 23 September 2026. Source applicant/title/application/publication fields are preserved. Reports retain exactly Aneeq's 12 columns, including Priorty Date.

## Verification

Each PDF receives two separate image readings through the shared OPENAI_API_KEY and PCT_AI_MODEL (default gpt-4o). The second request sees original pages in a different order, not the first answer. Email and phone agreement requires the same normalized value, role and page; a firm name versus its named attorney is retained as an owner-label review issue instead of discarding the contact. Email comparison is case-insensitive while the source spelling is preserved.

The two initial readings now run concurrently under the existing two-request limit. Their original/reversed-page identities are retained even if the second finishes first. The prompts, image resolution, page coverage, ownership policy, email comparisons, DNS checks, and conditional third/fourth readings are unchanged. Failure of either required reading still withholds unverified OCR.

A valid email can also be confirmed by one image reading plus exact local OCR. Relevant pages receive a second local OCR pass at 400% scale. A one- or two-character disagreement triggers a focused third reading of overlapping high-resolution page bands. If that focused read introduces a new spelling, a fourth independent crop reading must repeat it. Unresolved conflicts are withheld. Recognized `Display Name <email>` syntax is separated conservatively; arbitrary malformed addresses are never guessed. The full readings, optional crop readings, OCR candidates and original PDF remain in local audit files. This is source verification, not a mailbox-delivery guarantee.

Fax/Telefax labels exclude phone candidates even if AI mislabeled them. Evidence and syntax are checked per field. Incomplete address evidence, an unclear name or unrecognized country do not discard independently confirmed email/phone fields. Country is normalized from printed country evidence or a recognized country at the end of a confirmed address. It is never inferred from a phone or filing-office prefix.

PCT_EMAIL_DNS_CHECK=true checks domain mail routing, retries a transient resolver failure once, and withholds unconfirmed email addresses. MX/null-MX, nonexistent domains and implicit A/AAAA mail routing are distinguished. No email is sent and no SMTP mailbox probing is performed. A source-matching email and a routable domain do not prove mailbox existence or delivery.

Verification cache includes model, rules, verifier code, policy code, page limit, DNS setting, PDF and context. Accepted records expire after five minutes. Unverified legacy progress cannot bypass the current revision. An API failure never silently falls back to OCR. PCT_AI_VERIFY_ENABLED=false explicitly opts into legacy OCR only.

## Selection and names

Extract applicant and agent blocks independently. Never assume that a contact email/phone belongs to an agent. Preserve each field's role, owner and evidence in the audit. Agent Name is sourced independently from an actual agent block.

The process rule is implemented as follows: prefer a verified applicant email when applicant and agent contacts differ; if the applicant has no email, use the independently verified agent email block. When contacts are shared, compare addresses (same address selects applicant, different addresses select agent). If the address comparison is unavailable, retain only the identical shared email/phone and withhold owner-dependent fields. A matching email or phone with no conflicting shared value counts as shared contact information; an omitted optional phone is not a conflicting value.

For multiple contacts in one role, an explicit primary PCT block is deterministic: IV-1 precedes IV-2 additional agents, and the unique earliest applicant block precedes continuation applicants. When no primary block exists, a single independently verified email shared across ambiguous blocks may be retained while owner, category, country, name and unrelated phone values stay blank. Multiple distinct peer emails still require review.

Identical complete contacts printed under a primary agent firm and an additional attorney can use the primary source block without merging people. An actual contact-block Name takes precedence over a later signature. Missing agent names display Sir/Ma'am, with name_is_placeholder=true; that display text is never treated as a real person or a contact owner.

Cat uses source-supported Slf/Corp/Ind. The legal company suffix of an applicant can support Corp; a corporate suffix on an agent does not establish whether the business is a legal practice. Unresolved classification remains blank. No Info means neither reading found usable wanted contact information in the reviewed complete document; uncertainty stays in review evidence.

Repeated marks later duplicate patent IDs or matching verified contact tuples (same owner, role, email set and phone set) within one input/run. Every patent row is retained. Matching applicant name alone does not mean Repeated. Original category and repeated_of row remain in metadata. This operational interpretation was stated to the user; refine it if they clarify a different duplicate criterion.

## Local runtime and tests

The single-browser pipeline downloads ahead while one separate worker extracts and verifies PDFs. PDF rendering/OCR stay on one worker, and Playwright stays on its owning thread. `PCT_PIPELINE_PENDING_PDFS` defaults to two (one active plus one waiting). `PCT_PIPELINE_MIN_ROW_INTERVAL_SECONDS` defaults to ten seconds; failed lookups increase backoff and retry the same row once. Navigation, CAPTCHA, download, and unconfirmed document lookup failures are errors rather than claims that no contacts exist. Legacy fast-mode inputs cannot introduce extra browsers.

Every completed row is written to a local JSONL checkpoint before it is reported complete. A single writer updates the same two Excel files every 25 completed rows and at the end, using temporary files and atomic replacement. The exact 12 columns, styles, source fields, original row order, and repeated-contact policy are retained. Stopping accepts no new downloads and drains at most the bounded pending PDFs before saving partial output. A failed final workbook write is reported as partial, with the JSONL location, rather than successful completion.

An explicit `resume_path` accepts a local handoff from a gracefully stopped run. It verifies the original sheet hash, row count, source cells, unique original row numbers and contact-policy fingerprint before starting the browser. Existing completed results, including errors and their evidence, are retained; only unfinished row numbers are downloaded. Policy fingerprints normalize text line endings so an unchanged Windows checkout is compatible. `scripts/handoff_pct_run.py` captures a specifically identified run without killing the dashboard and refuses a handoff if saved rows are missing. A service restart must happen only after this capture succeeds and all local agents are idle.

The dashboard uses completion timestamps supplied by the running pipeline. Restored rows are excluded from throughput, refreshing does not create artificial speed samples, and the ETA recalibrates until five new completions exist. Public dashboard JavaScript is served by the AWS Lexmom adapter; `scripts/patch_pct_eta.py` applies only the timing change to that customized script, preserving its other features.

A stopped localhost proxy listener falls back to a direct connection for the default single browser. Saved proxy configuration and remote proxy settings are unchanged. PCT remains local; no other agent service is restarted.

Run:

    python -m pytest agents/pct_agent/test_ai_verifier.py agents/pct_agent/test_contact_ownership.py agents/pct_agent/test_accuracy_policy.py agents/pct_agent/test_overlap.py -q

The October 2026 overlap change was prepared and tested in an isolated checkout, then activated with an explicit controlled handoff. The running 4,241-row sheet retained all 218 completed rows and resumed at row 219. The restored JSON records and both checkpoint workbooks were compared with the stopped run: all results, cells and checked formatting matched. Offline replay of 100 saved original/second/focused readings, OCR candidates and DNS outcomes also produced identical contact results and workbook cells to the baseline code. The comparison checks header order, fonts, number formats, alignment and column widths. This checks scheduling/reporting regressions with fixed evidence; it is not a new live AI accuracy benchmark. A scaled timing simulation measured approximately 2.3x speedup using observed stage durations; actual WIPO/API throughput varies. `scripts/check_pct_pipeline.py` reproduces both offline checks without sending API requests or accessing WIPO.

72 focused regression tests pass. The original blind 100-row run returned 62 exact workbook email matches, two incorrect emails and 36 missing emails. A current deterministic replay of its saved independent evidence, followed by blind focused rereads only for unresolved character conflicts, produces 96 exact workbook matches. The four non-exact cases were manually checked against the PDFs: three workbook values are wrong or incomplete while the revised output is source-supported, and one PDF prints an unroutable `.co` address that is correctly withheld after DNS validation. No reference email was supplied to extraction or focused-reread requests. This combined replay is not a fresh end-to-end 100-download run and is not a guarantee on unseen filings.

The live credit check now succeeds; the earlier credit_balance_exhausted blocker is resolved as of this test. The source PDF artifacts and contact sheets remain local, excluded from Git. Teaching rules/examples are prompt configuration, not model fine-tuning. Keep real examples in an ignored local PCT_AI_RULES_FILE, never in this public repository.

API reference: https://developers.openai.com/api/docs/guides/images-vision

## Parallel PDF verification

`PCT_PDF_VERIFICATION_WORKERS=4` enables up to four spawned worker processes. Each
process executes the unchanged PDF extractor and verifier, including original
images, both independent readings, focused rereads, owner selection and DNS
checks. PDF objects never cross process boundaries. `PCT_PDF_API_CONCURRENCY`
is a shared semaphore across those processes, bounded to 2-8 active requests.
The browser remains on the coordinator with its existing lookup interval.

`PCT_PIPELINE_PENDING_PDFS=8` bounds downloaded/processing PDFs. Completed
results return to one coordinator, which durably journals each row before
publishing progress. Workbook creation sorts original row numbers, so parallel
completion cannot misalign source metadata or contacts. Stopping drains all
submitted PDFs; a handoff preserves all completed results, including errors,
and resumes only unfinished row numbers. Defaults retain one PDF worker.

`test_parallel_verifier.py` tests real Windows-spawn processes and the shared
request bound using offline responses, both image readings, independent row
evidence, worker failures, stop/drain/resume and ordered workbook output.
Actual throughput remains limited by document supply and API/CPU capacity.

Excel export removes only XML-prohibited non-printing control characters from
cell strings. Source rows, verified contacts and journal/evidence records stay
unchanged. This handles a pre-existing control character in a phone field that
otherwise prevented all subsequent workbook checkpoints from being written.
Tabs, carriage returns, newlines, visible characters, column order and formatting
are preserved. The regression suite includes this export failure and 100 tests.
