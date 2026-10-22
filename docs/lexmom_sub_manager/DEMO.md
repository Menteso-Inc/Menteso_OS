# Lexmom Sub Manager: live research demo

Open https://os.menteso.com, sign in with an operator/admin account, and select **Lexmom Sub Manager**. The first specialist is **Prospect Research and Qualification**.

## Verified demonstration result

On 7 October 2026, the deployed GPT-4o configuration completed two consecutive supplied-site runs in about 16 and 17 seconds. Both qualified the same US five-attorney firm and returned its published general inbox as Hunter-valid (provider verification date 20 September). Each used one model call and one verification, reserving $0.15 within the $1 ceiling. This establishes a repeatable one-firm demo, not broad discovery accuracy. The dedicated search account had 245 free searches left at the final check.

## Demonstration

1. The dashboard now uses the saved server `agents/lexmom_marketing_agent/research_profile.json`; there is no targeting form. Default targeting is global law firms, with one search request allowed per run to conserve credits.
2. For the historical supplied-site demonstration, edit the saved configuration's `seed_urls` to `["https://therhlawoffice.com/about/"]`, set `target_count` to 1 and `query_terms` to `[]`. The sample `demo_profile.json` remains available for the CLI. Clearly identify this as a supplied website, not a newly discovered prospect. Restore the production targeting configuration afterwards.
3. Click Run research only when ready to spend the configured allowance. Expand Execution log to see delegation and recovery. Closing the browser does not stop the worker; Stop research requests cancellation.
4. Review qualified/needs-research/excluded counts. Use the results table and expand View details to compare literal quotes, URLs and retrieval dates. Missing evidence must remain unresolved.
5. Read the email and verification columns, then expand View details for contact association and role evidence. A published general inbox is not a named decision maker. Hunter validity/catch-all/unknown status describes the mailbox, not consent, buying intent or conversion.
6. Download Sourced prospect records for the complete JSON evidence record. Results are real provider outputs; no mock fallback or manufactured leads is used.

For discovery mode, set empty `seed_urls` and the intended `query_terms` in the saved JSON. Search consumes the dedicated free account's quota. Broad queries can produce directories, news or blocked sites and may return zero qualified firms. The agent excludes known non-firm sources, classifies other sources, and preserves partial results.

## What to say to the CEO or investor

“This is our first deployed specialist. Lexmom Sub Manager delegates research, checks published firm facts, records evidence and verifies published email addresses. It enforces a budget and preserves failures so we can measure quality. The next investment decision is whether search coverage and cost per usable prospect justify more volume.”

Do not present a qualified firm as a paying customer, a verified email as consent, a one-firm demonstration as representative accuracy, or an estimated reservation as a measured invoice. This stage does not send outreach, run ads, make calls or process purchases.

## Decision before buying more search capacity

Review a manually audited sample across intended countries and sizes. Measure official-site discovery rate, grounded qualification rate, contact verification outcomes, failure/recovery rate, elapsed time and actual provider spend. Set an acceptable quality threshold before expansion. A larger SerpAPI allowance increases available search volume; it does not itself resolve extraction quality, inaccessible websites or customer conversion.

The current deployment is an on-demand live pilot. For unattended, high-volume operation, complete representative acceptance, add sustained operational monitoring/alerts and backup restore drills, and establish the later outreach workflow separately. See DEPLOYMENT.md for service operations and the current measured results.
