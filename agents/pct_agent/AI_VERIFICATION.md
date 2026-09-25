# PCT source verification and contact selection

Updated 23 September 2026. Source applicant/title/application/publication fields are preserved. Reports retain exactly Aneeq's 12 columns, including Priorty Date.

## Verification

Each PDF receives two separate image readings through the shared OPENAI_API_KEY and PCT_AI_MODEL (default gpt-4o). The second request sees original pages in a different order, not the first answer. Email and phone agreement requires the same normalized value, role and page; a firm name versus its named attorney is retained as an owner-label review issue instead of discarding the contact. Email comparison is case-insensitive while the source spelling is preserved.

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

A stopped localhost proxy listener falls back to a direct connection for the default single browser. Saved proxy configuration and remote proxy settings are unchanged. PCT remains local; no other agent service is restarted.

Run:

    python -m pytest agents/pct_agent/test_ai_verifier.py agents/pct_agent/test_contact_ownership.py agents/pct_agent/test_accuracy_policy.py -q

72 focused regression tests pass. The original blind 100-row run returned 62 exact workbook email matches, two incorrect emails and 36 missing emails. A current deterministic replay of its saved independent evidence, followed by blind focused rereads only for unresolved character conflicts, produces 96 exact workbook matches. The four non-exact cases were manually checked against the PDFs: three workbook values are wrong or incomplete while the revised output is source-supported, and one PDF prints an unroutable `.co` address that is correctly withheld after DNS validation. No reference email was supplied to extraction or focused-reread requests. This combined replay is not a fresh end-to-end 100-download run and is not a guarantee on unseen filings.

The live credit check now succeeds; the earlier credit_balance_exhausted blocker is resolved as of this test. The source PDF artifacts and contact sheets remain local, excluded from Git. Teaching rules/examples are prompt configuration, not model fine-tuning. Keep real examples in an ignored local PCT_AI_RULES_FILE, never in this public repository.

API reference: https://developers.openai.com/api/docs/guides/images-vision
