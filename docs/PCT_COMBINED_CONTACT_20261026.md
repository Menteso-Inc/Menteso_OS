# Experimental combined contact verification

`PCT_OLLAMA_COMBINED_CONTACTS=true` changes the first visual read of an
explicitly labelled contact block. It is false by default and has not yet
qualified for production. Keep the existing two-worker scheduling profile.

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

These fixes are isolated from the frozen off/on timing runs. Qualify them with
scoped regressions and fresh original-PDF rechecks after the paired test ends.
Keep the original comparison immutable and record repaired rows/revision and
repair time separately in any composite final report. Do not label that report
as a full new 200-row run under the repair revision.
