# PCT live-test telemetry repair — 21 October 2026

The private 100-row Qwen test exposed three separate problems: status polling did
not retain CAPTCHA totals, failed solver attempts could emit a clearance event,
and a disappeared manual challenge form was treated as success without checking
the patent page. Early WIPO download failures also provided misleading ETA samples.

## Source changes

- `telemetry.py` maintains run-scoped absolute CAPTCHA counters, separate detected,
  failed and unconfirmed clearances, active PDF verification rows and successful
  completion timestamps. It never reads contact values or reference answers.
- Server status and browser events carry versioned snapshots. The frontend accepts
  newer snapshots, avoids SSE/poll double counting and resets totals for a new run.
- ETA waits for five successful rows, describes active verification or CAPTCHA
  waiting, and includes time since the most recent completion instead of freezing
  an optimistic estimate while a worker is delayed.
- Manual confirmation requires a visible patent page without an active challenge,
  both in the popup and in the worker after cookie transfer. Blank, closed, loading
  or forbidden pages are not successes. Exhausted attempts emit `captcha_failed`.
- The browser receives a short page-load allowance after manual confirmation so
  time spent waiting for the operator does not immediately exhaust navigation.

## Activation boundary

Only `static/app.js` and `static/index.html` were copied to the local live tree.
The private dashboard and production worker processes were **not restarted**.
The running worker retains its original Python code. The server reducer and
manual-confirmation changes are tested source for the next safe activation;
they are not claimed to be active in the current worker. No AWS assets changed.

For the already-running private test, a separate observer reads the original
timestamped event log and writes aggregate telemetry to the existing authenticated
output-download route. The frontend accepts it only for the matching run ID.
It does not operate a browser, call any model or modify extraction results.
The original human workbook, cleaned input and live environment hashes were
verified unchanged. No completion email is enabled in the private test.

Local rollback copies and HTTP/hash verification are in the test output folder's
`ui-backup-20261021` and `ui_deployment_receipt.json`. Restoring those two static
files rolls back this display change without stopping extraction.

## Findings and limits

At 14:45 IST the run had three recorded WIPO load-timeout errors, two downloaded
PDFs (rows 4 and 5), and Qwen still processing the first three-page verification
request. Its inference log advanced through image processing; it was not evidence
of a dead worker. No verified row or real-sample accuracy percentage was available.
CAPTCHA history contained twelve detections, eleven failures and one reported
manual clearance. Legacy clearance is labelled unconfirmed by the stronger rule.

The PDF verifier uses local Qwen3.5:4b. The separate CAPTCHA vision handler still
calls GPT-4o and received HTTP 429 with exhausted credits. This change does not
connect Qwen to CAPTCHA automation or alter the paid API configuration.

Local CPU inference is substantially slower than the throughput target. Both
independent readings, evidence coverage, contact policy, sheet columns and saved
row order remain unchanged. Regression checks are not proof of real-data accuracy.
The 100-row test and separate timing/comparison observer remain active; accuracy
must come from their completed results, with failures included in coverage.

## Validation

- 147 offline PCT tests passed, including extraction policy, Ollama contract,
  ownership, overlap, row preservation, telemetry and manual-confirmation cases.
- JavaScript syntax, dropped-stream/reconnect checks and telemetry checks passed.
- The private dashboard served the new JavaScript with its exact expected hash;
  authenticated telemetry was fetched while the same run remained running.
- A rendered browser visual check was not performed. Reloading the private test
  tab is needed to load the new static JavaScript; reloading does not stop its run.
