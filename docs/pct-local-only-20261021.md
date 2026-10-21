# PCT cloud dependency removal — staged, not activated

The owner requested removal of GPT-4o from PCT and connection of local Qwen to
CAPTCHA handling. Automatic CAPTCHA solving was declined. The allowed removal
portion is implemented here: PDF verification uses local Ollama; CAPTCHA handling
requires operator confirmation. This is not a Qwen CAPTCHA integration.

## Changes

- The PDF verifier defaults to Ollama and rejects every other provider before
  making a request, even if a shared OpenAI key exists. Removed OpenAI HTTP
  transport, key lookup and GPT-4o defaults. Both independent PDF readings,
  contact rules, original images, evidence checks and sheet formatting remain.
- CAPTCHA orchestration only offers manual confirmation. Old environment values
  such as `vision,manual` cannot restore a paid call. Retired vision and audio
  adapter entry points return failure without any network operation.
- Updated the sample configuration to local PDF inference and manual challenges.
  No shared OpenAI credentials are deleted; other agents may still need them.
- Updated offline transport/concurrency tests to cover the local provider. Added
  explicit checks for rejected cloud configuration, stale CAPTCHA settings,
  retired entry points and absence of OpenAI endpoints/key access in PCT runtime.

## Validation and activation boundary

157 offline PCT tests passed in 32.59 seconds. No inference request was sent by
these tests. The active private 100-row worker and production service were not
stopped or changed. The source changes are in the isolated integration worktree.
They cannot remove calls from a Python process that already imported older code.

Because the owner previously requested no interruption, an explicit question was
sent asking whether to checkpoint, drain in-flight work, restart and resume. Do
not treat elapsed time or this document as restart approval. Do not mark this
change active until the approved deployment and fresh runtime checks succeed.

The existing private test has a separate performance failure: both Qwen calls
for row 4 timed out after approximately 1,800 seconds each. At 15:47 IST ten rows
had recorded errors and none had a successful extraction. Removing GPT-4o does
not resolve these local-model timeouts or establish any accuracy percentage.

## Safe activation after authorization

1. Confirm run identity on port 8011 and all other local agents idle. Save current
   status and hashes of source inputs, journals, PDFs, reports and live config.
2. Use the normal stop endpoint for this identified private run. Wait for the
   verifier queue to drain and durable outputs to finish. Do not kill it while
   an in-flight result is unsaved. If draining is slow, report the wait.
3. Validate a resume handoff against the exact cleaned input, source row identity
   and existing policy fingerprint. Preserve original error rows and all files.
4. Back up the exact live PCT files before a guarded copy of these tested source
   changes and the previously staged telemetry/manual-confirmation fixes.
   Set `PCT_AI_PROVIDER=ollama` and `CAPTCHA_SOLVER_TIERS=manual`; remove only the
   obsolete PCT-specific cloud model/key settings. Preserve shared credentials.
5. Adapt the one-shot private test launcher to accept this validated resume,
   retain the original run/timing artifacts, and keep completion email disabled.
   Restart only the required idle services through their existing keepers.
6. Verify the resumed row set, provider, manual CAPTCHA setting and dashboard
   status before claiming activation. Do not trigger extra test/model jobs
   while another worker is using the CPU. Retry missing/error rows separately
   after the main pass, with original outcomes retained in the comparison.

Source deployment, restart and resume have not been performed by this change.
