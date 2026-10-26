# Experimental combined contact verification

`PCT_OLLAMA_COMBINED_CONTACTS=true` changes the first visual read of an
explicitly labelled contact block. It is false by default and has not yet
qualified for production. Keep the existing two-worker scheduling profile.

Full-document OCR, role/field mapping, whole-field OCR agreement shortcuts,
contact selection, recipient/signature checks, DNS checks and output formatting
remain in place. A block with at least two unresolved fields combines their
original image crops into one labelled panel for a single Qwen request. Pure
white margins may be trimmed; pixels are not scaled and faint ink is retained.
OCR strings, reference-sheet answers and previous extracted values are not
supplied to the model. Each panel stays within one verified source role/block.

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
