# Lexmom Sub Manager

The stable package/registry ID remains `lexmom_marketing_agent`. The approved
first-stage connector validates research profiles and explicitly runs
`prospect_research_agent`. The research dashboard shows sourced contacts,
unresolved evidence, failures, cancellations and exports. Separate Email Campaign
and Social Media Posting views expose drafts and read-only account activity.

Live use requires specialist credentials in `.env`. The current free-only rules
profile uses zero model calls and no cash reservation; the metered model path
requires configured provider cost estimates. Research is on demand; separate
mailbox/social monitors do not enable outreach, ads, uploads, public schedules,
sales conversations or customer success. Fixture mode is internal test input, never a
dashboard fallback. The specialist owns recovery of provider/extraction errors;
the manager checks the returned handoff and preserves its status and artifacts.

Manager learnings are private and contain outcome/validation metadata, not
prospect records. Latest handoff metadata is separate from learning memory;
the full dataset is reloaded from the specialist's manifest-checked artifact.

Run connector checks with `python -m unittest agents.lexmom_marketing_agent.test_placeholder`.


## Saved targeting configuration

Edit `research_profile.json` in this directory to change countries, firm segments, attorney-count boundaries, buyer roles, query terms, supplied websites and run limits. It contains non-secret configuration only; credentials and provider cost rates remain in `.env`.

Dashboard Run all agents sends an empty request. The server reloads and validates the JSON on every run, then saves the effective input in the run artifacts. Missing/invalid configuration blocks execution; there is no fallback to an old demo input. The Dashboard chip shows business metrics and Run/Stop/Refresh controls. The Prospect Research chip holds targeting and the results table. The execution log is collapsed while idle.

Current targeting: both Lexmom Manage and Launch, all countries, solo/small/mid-size law firms, 1-50 attorneys, owner/founder/partner/administrator/operations roles, no supplied seed. The core profile targets 50 verified contacts in saved inventory, with at most three queries, 50 candidates, twelve pages per firm, 50 verifications and a 900-second deadline. It uses rules extraction, free allowances only and zero model calls. The HTTP adapter applies tighter operating caps as described below. A met and still-fresh inventory goal reuses saved results without provider operations; it is not 50 new contacts per click.

The AWS file is `/home/menteso_os/agents/lexmom_sub_manager/app/agents/lexmom_marketing_agent/research_profile.json`. Editing the local copy requires deploying that file; editing the server copy takes effect on the next run without restarting a service. The adapter retains hard caps of 3 searches, 10 candidates, 5 target firms, 15 model calls, 3 verifications, 300 seconds and $1 per run. Increasing JSON values cannot bypass these caps. Explicit programmatic research profiles remain supported for tests and CLI workflows.


## Business overview and workflow chips

The overview reads preserved, completed Lexmom manager handoffs. It counts distinct qualified firm domains from validated live child results; repeated demos and fixture runs do not add leads. Incomplete artifact history is shown as unavailable, not a complete total. Cost reservations from live runs (including failures) are separate from actual billed spend. Spend and attributed revenue remain null until billing/payment tracking is connected; neither zero revenue nor ROI is inferred. No provider calls occur when opening or refreshing this view.

Run all agents currently executes Prospect Research; it does not activate email or social publishing. The three specialist views are available separately. The button has a client dispatch guard and the server rejects concurrent runs. Keyboard arrows/Home/End switch chips; the selected view is retained in the URL hash. The research table counts unique email contacts separately from firms, filters held/verified records and shows product fit, verification dates and sources in Details. Opens/clicks/replies are observed engagement rather than research qualification.

See [the current team handoff](../../docs/lexmom_sub_manager/TEAM_HANDOFF_20261020.md)
for the source/runtime map, last dated live checkpoint, test commands and pending
conversion/provider integration. Preserve the live environment, private data,
agent memory, authored media and rollback releases during updates.
