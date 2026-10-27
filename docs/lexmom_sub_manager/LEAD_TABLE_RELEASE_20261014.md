# Contact table and engagement release — 2026-10-14

Deployed and verified on the isolated AWS Lexmom service at os.menteso.com.

- One table, one row per unique email; total/Hot/Warm metrics and activity filters.
- Contact name/email/firm together; full email addresses remain readable. Run
  details/downloads and execution logs are collapsed rather than repeated tables.
- Live inventory: 15 email contacts, 0 Hot, 0 Warm. All still need research; these
  counts do not represent 15 qualified buyers. Campaign emails sent: 0.
- Open is weak evidence. A matching product CTA click makes Warm. A confirmed
  positive reply makes Hot. Duplicate events and likely bots do not inflate heat;
  suppression takes precedence. Reply arrival time survives synchronization.
- Added operator-only confirmation from a known lead's actual incoming reply,
  accessible in Email Campaign → Inbox & replies. This never sends a message.
- Dedicated SES OPEN/CLICK event types verified; existing SNS destination and
  delivery events preserved. SES sending and campaign switches remain disabled.
- 66 focused local tests passed; 54 isolated AWS tests passed. No live campaign
  was sent for engagement testing. Desktop 1366×900 and mobile 390×844 inspected;
  Warm filter showed the correct empty state and All restored 15 contacts.
- Shared container start time and PCT app.js code preserved. Only the isolated
  dashboard was restarted; mailbox monitoring was restored. No research run or
  new search/verification/paid-generation call was started.
- Required rollback releases and SQLite backup retained on AWS. New Social Media
  code and research extraction repairs remain separate local work.

Screenshots: `lead-table-20261014.png`, `lead-table-mobile-20261014.png`.
The lifecycle document and JSON are proposals, not a deployed lifecycle engine.
