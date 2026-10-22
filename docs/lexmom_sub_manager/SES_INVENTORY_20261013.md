# Lexmom SES inventory

Read-only check: 13 October 2026, 14:22 IST. The authenticated AWS account was confirmed against the known Menteso OS instance's owner. All 17 enabled regions were checked. No identity, DNS record, receipt rule, key, permission, mailbox or sending setting was changed; no email was sent.

The owner corrected the reply/demo destination to **mail@lexmom.com**, and selected SES for future outbound **hello@meetlexmom.com**. The screenshot shows a Google profile for mail@lexmom.com; this is user-provided identity evidence, not verification of a mailbox licence or Gmail API access. Fresh lexmom.com MX points to smtp.google.com, confirming Google inbound routing.

## What exists

| Setting | North Virginia: us-east-1 | Oregon: us-west-2 |
| --- | --- | --- |
| Lexmom identity | lexmom.com, domain | lexmom.com, domain |
| Domain verification / DKIM | SUCCESS / SUCCESS, signing enabled | SUCCESS / SUCCESS, signing enabled |
| Production access / account sending | Enabled / enabled | Enabled / enabled |
| Account enforcement | HEALTHY | HEALTHY |
| Custom MAIL FROM | noreply.lexmom.com, SUCCESS | Not configured on this identity |
| Configuration set on identity | None | None |
| Matching named Lexmom configuration sets | None found | None found |
| Active receipt rules addressed to Lexmom | None found | None found |
| Account sending quota per 24 hours | 50,000 | 917,600 |
| Account sends in preceding 24 hours | 0 | 259,003 |
| Account sending rate per second | 14 | 50 |

**Identity count: one unique domain, registered in two regions; zero separately verified Lexmom email-address identities.** Neither region has a meetlexmom.com identity, and no matching identity was found in the other 15 enabled regions. Subdomain and exact-address matching included both lexmom.com and meetlexmom.com. This is SES inventory, not a count of company mailboxes: domain verification permits eligible addresses under that domain to send without separately verifying each address, but does not create inboxes or enumerate their users.

Account-wide legacy SES statistics over the returned approximately 14-day window: North Virginia has zero delivery attempts, bounces, complaints or rejects. Oregon has 1,087,430 delivery attempts, 1,077 bounces, seven complaints and zero rejects. These totals include all senders in each account/region and **cannot be attributed to Lexmom** from this inventory. Quotas are AWS account limits, not approved Lexmom campaign budgets. No workload was paused, restarted or investigated beyond these aggregate queries.

## Requested sender status

hello@meetlexmom.com is **not configured for SES sending or direct receiving**. Fresh DNS has no root MX/TXT records and an existing DMARC quarantine record; the domain is hosted at GoDaddy nameservers. lexmom.com verification does not verify the separate meetlexmom.com domain.

For the selected architecture, configure a separate SES domain identity and aligned DKIM/MAIL FROM for meetlexmom.com, with Lexmom-specific event reporting. Use the approved mail@lexmom.com Reply-To/reply/demo destination. Menteso OS must persist outbound receipts and connect the authorized mailbox for replies; SES sends do not automatically appear in Gmail Sent. Direct mail addressed to hello additionally needs an inbound route: an existing-mail-provider alias/domain route or a separately designed SES receiving pipeline. An SES identity alone is not that route.

North Virginia is a candidate for the new setup because production sending is enabled and reported account traffic is zero. This is a configuration recommendation, not evidence of free-tier entitlement, email-delivery quality or authorization to send campaigns. Preserve existing identities and account settings, particularly Oregon's active shared traffic. No infrastructure requiring additional spend has been provisioned.

Private audit identifiers/raw diagnostics remain in runtime-data/lexmom-ses-audit-20261013/.env; compact non-credential report is retained alongside it. No deployment/build artifacts were created, so the standing post-deployment cleanup does not apply to these retained audit helpers/evidence.

References: [SES domain and email identities](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html), [regional identity configuration](https://docs.aws.amazon.com/ses/latest/dg/regions.html), [SES receiving and mailbox restrictions](https://docs.aws.amazon.com/ses/latest/dg/receiving-email-concepts.html).
