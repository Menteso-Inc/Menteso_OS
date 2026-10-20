# hello@meetlexmom.com: mailbox and demo integration options

Date: 13 October 2026. Current SES setup is verified; campaign sending remains disabled. The historical provider investigation below predates setup.

Latest owner selection: **support@lexmom.com** for replies/demo notifications and **AWS SES** for hello@meetlexmom.com. SES/DKIM/custom MAIL FROM are verified, one approved internal test has a confirmed SMTP delivery event and visible Gmail Inbox placement, and the live demo recipient is configured. See [the completed setup](SES_SETUP_20261013.md). The owner identifies **mail@lexmom.com** as the office mailbox; the test addressed to support arrived there. The underlying alias/forwarding mechanism and Gmail API synchronization remain unconfigured/uninspected. No normal hello mailbox or inbound MX was provisioned. [The 17-region inventory](SES_INVENTORY_20261013.md) is the before-setup snapshot.

## Findings before setup

- meetlexmom.com belongs to the owner's GoDaddy account. Email & Office reported no available email accounts; there is no verified existing mailbox there. DNS has no MX/SPF and has an existing DMARC quarantine policy.
- A fresh public DNS check shows menteso.com MX records pointing to Google's mail servers. This identifies the current inbound route; it does not prove the tenant plan, administrator, unused licences or whether a Zoho Mail subscription exists separately.
- The available Zoho session contains CRM. Opening Zoho Mail Admin Console in that session shows Email Setup and a plan-selection page under Accounts Team, not an existing configured organization/domain list. The owner has not supplied a different Zoho Mail admin account. CRM access alone cannot establish Mail hosting or domain entitlements.
- A subsequent audit of all 17 enabled AWS regions found verified lexmom.com domain identities in us-east-1 and us-west-2; zero separately verified Lexmom email addresses. meetlexmom.com is absent across those regions. Fresh lexmom.com MX points to Google's smtp.google.com. No SES mail was sent or actual mailbox licence verified.

## Recommended choice

First inspect the **actual existing company email organization**. Reusing an existing licensed user's alias can avoid another user subscription if the tenant permits it; a dedicated separate mailbox generally requires an available or additional user licence. An alias shares its user's Inbox/Sent, so it is not an independent account. Agent authorization must match the selected identity and approved mailbox scope.

Given the observed Google MX route, an existing Google Workspace tenant is a promising zero-additional-licence-cost route: add/verify the owned meetlexmom.com domain and configure hello as an alias of the selected existing user, with Lexmom labels and the authorized sender identity. The account's administrator must confirm the exact supported domain/alias combination and any existing mail routing first. This uses **Google Admin**, not Google Cloud Console. The agent must not rename an employee, change the primary Menteso domain, subscribe to a new plan or assume broad access to all company mail.

If the owner intends to use an existing **Zoho Mail** tenant, Zoho supports multiple domains under one organization. Verify its paid/free plan and domain limits before adding meetlexmom.com. Its free plan is limited to one domain in eligible data centers; an organization already using that free domain for menteso.com cannot be presumed to include a second domain. User aliases can share a mailbox where the plan/admin configuration allows; a separate hello mailbox can require another seat. The visible account currently does not demonstrate a reusable Mail subscription.

The owner subsequently selected SES for outgoing hello mail, with support@lexmom.com receiving replies/demo notifications. This supersedes the earlier mail@ recipient choice. Actual receiving-mailbox access and API authorization remain unverified; no provider was purchased. Do not claim that a CRM plan or an existing domain automatically includes a mailbox or usable agent API.

## Where AWS SES fits

SES is a sending/inbound-processing service. It does not provide POP/IMAP mailbox servers or a normal Inbox/Sent interface. Receiving through SES requires supported-region routing and additional storage/processing such as S3/SNS/Lambda, or a mailbox product such as WorkMail. That is a different integration from simply connecting Zoho/Gmail webmail.

Recommended optional arrangement: keep the domain's inbound MX at the chosen mailbox provider, and use SES for suitable transactional website notifications and demo acknowledgements. Configure a verified domain identity, aligned DKIM/SPF/DMARC and a suitable MAIL FROM subdomain for SES. Do not point the same domain's inbound routing at two unrelated providers or assume priority MX records partition incoming mail. Reply-To can point to the approved hello mailbox, or to the validated requester for an owner notification. SES sends do not automatically appear in Gmail/Zoho Sent; store receipts and explicitly archive/synchronize them if that visibility is required.

A personal @gmail.com identity can technically be verified as an individual SES email identity, but the owner cannot configure Gmail's domain authentication. It is unsuitable as our custom-domain production sender setup. Use the owned meetlexmom.com or an already authorized Lexmom identity. Existing verified lexmom.com does not verify the separate meetlexmom.com domain.

SES a-la-carte outbound pricing currently starts at $0.10 per 1,000 emails plus relevant data/optional-service charges. Free-tier eligibility was not checked; do not describe this old AWS account's SES as guaranteed free. AWS AUP prohibits unsolicited mass email, so use SES for eligible notifications rather than treating it as a workaround for cold-outreach provider requirements.

## Demo and dashboard work after mailbox selection

Persist the website demo request before queuing its owner notification. Include product choice, firm/contact details, the stated need, source/attribution and the permission given for that demo. Use an authenticated sender and validated requester Reply-To. Retry notification failure without losing or duplicating the stored lead. A preferred date/time is a request, not a booked appointment.

Connect authorized mailbox message/thread IDs to a Menteso OS conversation view, retaining Inbox/Sent visibility, receipts, replies and suppression. Scoped mailbox access and internal delivery/reply/unsubscribe tests must pass before any live email workflow. Demo-request contact permission is not consent to unrelated campaigns. No mailbox sync, demo-backend change or outbound specialist is enabled by the research deployment.

References: [Google Workspace domains](https://knowledge.workspace.google.com/admin/domains/add-a-user-alias-domain-or-secondary-domain), [Google email aliases](https://support.google.com/a/answer/33327?hl=en-sg), [Zoho domain hosting](https://www.zoho.com/mail/help/adminconsole/add-domains.html), [Zoho user aliases](https://www.zoho.com/mail/help/adminconsole/user-settings.html), [Zoho plans](https://www.zoho.com/mail/zohomail-pricing.html), [SES receiving restrictions](https://docs.aws.amazon.com/ses/latest/dg/receiving-email-concepts.html), [SES pricing](https://aws.amazon.com/ses/pricing/), [AWS AUP](https://aws.amazon.com/aup/).
