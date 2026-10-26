# Combined contact verification: qualified local release

`PCT_OLLAMA_COMBINED_CONTACTS=true` changes the first visual read of an
explicitly labelled contact block. It remains false in the repository template;
the qualified local release enables it while keeping the existing two-worker
scheduling profile. Check the private activation receipt before assuming that
the running dashboard has loaded this release.

Full-document OCR, role/field mapping, whole-field OCR agreement shortcuts,
contact selection, recipient/signature checks, DNS checks and output formatting
remain in place. A block with at least two unresolved fields combines their
original image crops, in an explicit field order, in a single Qwen request. Pure
white margins may be trimmed; pixels are not scaled and faint ink is retained.
OCR strings, reference-sheet answers and previous extracted values are not
supplied to the model. Each request stays within one verified source role/block.
Fields remain separate images to avoid the extra vision area of a stitched
panel. Image indexes, original crop bounds and saved cropped images retain
field identity; disagreement still triggers an individual source check.

The compact response uses a string for each literal transcription and null for
an unclear field. This retains the legibility decision while reducing repeated
JSON keys/output tokens. Invalid types or missing/extra keys trigger fallback.

Each returned field must independently agree with its OCR source. A disputed
field follows the existing enlarged-crop and independent-reading rules.
Malformed responses, capacity failures or model errors fall back to individual
checks and retain the failed request's measured cost. The shared request is
recorded once; field traces reference it without double-counting its duration.
The mode and module are included in verification/resume fingerprints.

The first comparison uses the same saved original PDFs, model digest, worker
count, CPU-thread settings and scoring rules with the mode off/on. Freeze the
candidate before running; record both first-pass failures and all retries.
Use a small paired pilot before a full 200-row comparison. Fewer API requests
do not guarantee faster inference or unchanged accuracy. Do not activate a
candidate unless measured speed and preservation of correct fields support it.

Rollback checkpoint: `pct-before-combined-contact-20261026`, commit `5a45adc`.
Results and source PDFs stay private. No changes to CAPTCHA, live WIPO access,
cloud resources, model weights or production configuration are part of this
isolated implementation.

## Verified-data retention fixes under qualification

The matched 200-row test exposed two existing loss paths. An `unconfirmed`
DNS lookup discarded literal emails even after independent image/OCR agreement.
Domain routing is now annotated separately: an unknown lookup retains an
already verified source value and records `mailbox: not_tested`. Confirmed
`nxdomain` and `null_mx` outcomes retain their existing withholding policy.
This change does not infer deliverability, repair spelling or accept OCR alone.

The preferred-applicant rule could also discard a verified agent phone/name
when only the applicant email remained uncertain. Primary email selection
still stays unresolved in that case. Already verified agent email fields move
to the existing role/owner-labelled Additional Email column, while verified
phone/name fields remain and the row is marked `needs_review`. Each moved
email must have matching legible agent source-field evidence; absent evidence
keeps the existing closed failure path. Confirmed signer selections are
unchanged. Nothing is copied from human reference cells.

These fixes were isolated from the frozen off/on timing runs, then qualified
with scoped regressions and fresh original-PDF rechecks. Original comparisons
remain immutable. The final report records repaired rows/revision and repair
time separately; it is not a full new 200-row run under the repair revision.

## Measured result: 26 October 2026

The same 200-row input contained 176 identity-validated original PDFs and 24
unavailable sources. Both modes used two workers, two threads per model, the
same pinned Qwen model, reset model runners and identical synthetic warm-up.
Human answers were read only for scoring. No live WIPO navigation, CAPTCHA or
bibliography capture was included.

- Current pipeline: 8,546.953 seconds, 175 found/25 errors, 704 model requests.
- Combined first pass: 5,996.860 seconds, 173 found/27 errors, 414 model requests.
  Time fell 29.84%; the existing primary-selection rule caused two extra errors.
- Five fresh source rechecks under retention-fix revision `ea1f086` took
  237.218 seconds. The final composite has 175 found/25 errors: 24 missing PDFs
  and one unresolved Russian form. Total active time is 6,234.078 seconds
  (1h43m54s), 27.06% below the matched baseline, or 101.06 successful rows/hour.
  At 35.623 elapsed seconds/successful row, the 25–35-second target is close
  but not consistently established. This is batch throughput, not row latency.
- Email: 171/171 returned matches (100%), 171/176 available sources (97.16%),
  171/200 whole sample (85.5%). Baseline returned 169 matching primary emails.
  Two other verified agent emails were preserved as labelled Additional Email
  while their preferred applicant email remained unresolved.
- Names: 108/125 returned exact matches (86.4%); formatting/accent/order
  normalization gives 117/125 (93.6%). Exact available-source coverage is
  108/143 (75.52%). One additional person matches after accent normalization;
  no previously matching name was lost. Country: 170/172 returned (98.84%).
- Comparable email/name/country fields: 449/495 available-source references
  (90.71%), 449/561 whole-sample references (80.04%). Completely matching
  comparable rows: 135/200 (67.5%). Phone accuracy cannot be scored because
  the human phone column is empty. Category is a management label, excluded
  from the overall extraction metric; returned agreement is 161/171 (94.15%).
- All 347 scoped regressions passed. All 200 row identities/order, original
  input columns, 13 report columns/styles, role-labelled additional emails and
  workbook values passed. Every baseline primary/additional email, phone,
  country/category/role and matching reference field was preserved. Newly
  retained name/owner metadata was checked against original source images.

Results stay private in `Downloads/PCT_Combined_Contact_Test_26-October-2026`.
The `qualified-combined` report combines the complete first pass with five
fresh repairs; no full 200-row pass under the repair revision is claimed.
Human agreement is not a guarantee of complete or independently proven source
accuracy. Model weights, CAPTCHA adapter and AWS resources were not changed.

Local activation/backup receipts live in
`C:\ProgramData\Menteso\pct-combined-contact-release-20261026`. Activate only
after an all-agent idle check. Preserve existing reports, inputs, journals,
runtime state, teammate changes and every environment value except the new
combined-contact flag. Rollback checkpoint: `pct-before-combined-contact-20261026`.
