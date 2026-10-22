# Personalized email copy revision — 14 October 2026

Owner requested a more personal, catchy tone, using examples about a lawyer's website and manual case management. Rewrote both paused seven-day sequences with shorter questions, one useful idea and one clear next step. This is a copy hypothesis, not measured evidence of higher reply/conversion rates.

## First email examples

- Launch named contact: **John, want to see an AI website for your law firm?**
- Manage named contact: **John, still chasing case updates?**
- Launch firm inbox: **Example Law: want to see an AI website for your law firm?**
- Manage firm inbox: **Example Law: still chasing case updates?**

John and Example Law are explicitly labeled dashboard examples. Live rendering uses the sourced contact/firm identity. General firm inboxes receive their own message asking for the colleague responsible; named contacts receive a direct invitation. Without recipient context, the safe fallback contains no fabricated name.

Launch focuses on a practice brief, AI-drafted pages, intake and review. Manage focuses on scattered case context, next tasks, documents and financial views. Wording asks about potential friction instead of asserting that the firm has no website or uses old tools. The proposed “we created this for you” message remains conditional on a real recipient-specific website preview; none was generated or claimed here.

## Implementation and verification

- Version `2026-10-14.1`: 14 saved drafts, 14 named subject templates, 14 firm subject templates and separate firm-inbox bodies, all paused.
- Pydantic permits only plain approved subject fields and rejects attribute traversal/conversions/format directives. Rendering bounds names, rejects header controls, escapes HTML and preserves Unicode through MIME.
- Dashboard shows labeled subject examples. Earlier review to Sajan is marked as earlier/outdated; no replacement review or campaign email sent.
- 40 email/SES/dashboard tests passed locally and on AWS; standalone draft agent passed all four self-tests. JavaScript syntax and whitespace checks passed.
- Live authenticated dashboard verified both new product sequences, personalized subject examples, shorter copy and zero campaign sends. Screenshot: `email-copy-20261014.png`.
- Gmail monitoring remains connected. Replaced only scoped specialist source and the exact existing email JS fragment, preserving custom PCT/dashboard code. Shared container retained its October 5 start time; secrets, research/mailbox state and paused n8n/WLF preserved. No paid inference/search, new credential, DNS change, Git commit or push.

Temporary source transfer used the existing protected SSM transport, with no S3 bucket, remote staging directory or archive. Required rollback release and compact production evidence preserved. Automatic approval review rejected removal of the single task-local deployment helper before execution with “blocked by policy”; it remains untouched. Exact retained path and free-space measurement: `EMAIL_COPY_CLEANUP_20261014.json`. Earlier blocked-cleanup files were not retried.
