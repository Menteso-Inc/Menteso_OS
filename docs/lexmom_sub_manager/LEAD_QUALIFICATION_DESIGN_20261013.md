# Prospect Research: Manage and Launch qualification design

Date: 13 October 2026. Status: owner-approved two-product research extension implemented and deployed as a live pilot. The wider email, inbox, demo and continuous-worker flow below remains a design. See [release evidence and implementation limits](RELEASE_20261013.md), [research-to-email requirements](EMAIL_PIPELINE_REQUIREMENTS_20261013.md) and [mailbox findings](MAILBOX_OPTIONS_20261013.md).

## Product boundary and current checks

The owner wants one Prospect Research specialist to collect quality firms/people for Manage, Launch or both, with evidence suitable for personalized email. Qualification must be stored per product on one canonical firm record, with contacts underneath it. Do not create two unrelated copies of the same firm or simultaneously start conflicting sequences.

Public browser checks today rendered [Manage](https://lexmom.com/manage/) and [Launch](https://lexmom.com/launch/). Manage presents connected matter, task, document and financial workflows. Launch presents website creation and client intake. These are public product descriptions, not verification that every advertised capability works; approved product briefs must list demonstrated features and usable destinations before a sequence is enabled. Do not copy unverified customer counts, performance percentages, testimonials, instant-launch or case-acquisition promises into campaign messages.

The [Manage demo form](https://lexmom.com/manage/book-demo?source=website-navbar) renders product selection for Launch, Manage or both, role, firm size, preferred timing, a free-text need and permission to contact the requester about that demo. Its visible consultation link points to support@lexmom.com. No form was submitted; its backend routing and email delivery were not inspected. A rendered form is not proof that submissions reach a mailbox.

Baseline repository evidence before this extension: ResearchRequest accepted one `product` label, and FirmRecord had one product/basic fit status. The deployed extension now accepts `both`, stores independent product assessments and personalization briefs, and retains older-run compatibility. Its conservative rules extractor uses literal published facts, explicit needs and recent dated practice-launch statements. It does not implement visual website/intake auditing, authoritative no-website firm corroboration, first-party demo ingestion or a sending eligibility service. Those broader steps below remain planned.

## Collection pipeline

1. **Read the versioned product profiles.** The two profiles define supported country/language, firm segment, buyer roles, demonstrated features, meaningful need signals, exclusions and permitted sources. Existing global research scope and configurable solo/small/mid-size definitions remain; an enabled country's sending policy is separate.
2. **Generate bounded search batches.** Rotate country, practice area, firm stage and useful terms, retaining query history and source yield. Manage searches discover relevant operating firms and expansion/operations cues; Launch searches discover newly formed/repositioning firms and website/intake needs. These are candidate-finding terms, not proof of a problem. Search APIs can discover websites and public profiles; authorized directory data can provide additional candidates.
3. **Resolve identity.** Follow specific directory/profile listings to official firm websites or authoritative professional/business records. Confirm that a person is connected to the researched firm; avoid unrelated namesakes. Keep directories as discovery sources rather than qualified firms themselves. A new practice with no established site can qualify from corroborated authoritative identity/contact evidence; do not require an existing polished website to become a Launch prospect.
4. **Research bounded official pages.** Inspect home, team/about, practice, contact and intake information under the source/page/robots/network limits. Store the factual value, relevant excerpt, source URL, retrieval date and confidence. Count only clearly evidenced attorneys; generic employee count is not attorney count. Missing size/country/identity remains pending where required by the selected profile.
5. **Collect observed product signals.** For Launch, record a confirmed launch/rebrand announcement, a visibly unfinished site, or an observed missing consultation/intake route on inspected pages. Failure to find a site or temporary website failure is unknown, not proof that no website exists. An untested form is not labelled broken. For Manage, record firm/team/practice complexity, a relevant hiring/expansion announcement, or explicit requests concerning matters, tasks, documents or billing. Public size/hiring may support a hypothesis; it cannot prove spreadsheet use, missed deadlines, poor finances or dissatisfaction with another platform.
6. **Resolve contacts and verify published mailboxes.** Prefer sourced owners/founders/managing partners for Launch; owners/partners/operations for Manage, adjusting to the particular firm. Permit published generic inboxes using a firm-level message. Keep named email association, role match and technical verification separate. Refresh verification before any future send; unknown/catch-all/invalid status is held under the configured policy. Never invent a likely email pattern and present it as sourced.
7. **Deduplicate and assess both products.** Save the firm once, contacts once, evidence once, and two product-specific fit decisions. Reuse recent evidence where compatible; spend further credits only to resolve a relevant gap. Keep conflicting/expired evidence visible and queue it for refresh.
8. **Prepare the handoff.** Emit a primary product, optional secondary fit, supported message facts, a clearly labelled problem hypothesis, relevant approved capability, correct call to action, and explicit hold reasons. Email Campaign receives only records passing its current eligibility gate. Research does not send messages.

LinkedIn/social profiles and bulk-data providers are future/authorized inputs, not integrations proven by the present agent. Use approved APIs/exports or permitted public sources; an API record is a discovery hint requiring identity/freshness verification. No Apollo, LinkedIn automation or directory-access key is required to finish the current internet-search route.

Guardian Review: absence of a website is a valuable Launch hypothesis but cannot be inferred from one failed search. Requiring an existing official website for every candidate would incorrectly exclude new firms. Source corroboration resolves this without weakening identity checks. Exact firm size and internal workflow needs remain distinct evidence gaps.

## Qualification and priority

| Decision | Manage | Launch |
| --- | --- | --- |
| Base firm fit | Real legal practice in a supported market/segment, with enough evidence for the configured size rule | Same, including a corroborated new practice without a current website |
| Product relevance | Matter/work/team coordination use case; explicit need is strongest, while public operational complexity is a hypothesis | Website/intake launch or improvement use case; explicit launch/rebuild need is strongest, while observed website gaps are a hypothesis |
| Appropriate contact | Sourced owner, managing partner, operations contact or accepted generic firm inbox | Sourced founder, owner, partner or accepted generic firm inbox |
| Negative/unknown evidence | Out-of-profile organization, unsupported needs/market, contradiction or missing mandatory facts | Same; a complete site with working intake lowers Launch priority, but does not automatically prove the firm has no interest in a change |
| Primary message | One demonstrated workflow benefit tied to the relevant observed facts | One demonstrated website/intake benefit tied to the relevant observed facts |

Maintain four independent decisions:

- **Firm fit:** qualified / pending research / excluded under the profile's evidence rules.
- **Product fit, separately for Manage and Launch:** potential fit / confirmed need / no current fit / unknown, with reasons and supporting evidence. Potential fit must not be presented as intent.
- **Contact readiness:** sourced association and role where relevant, accepted generic inbox type, fresh verification and identity consistency.
- **Send eligibility:** appropriate selected provider and recipient/country basis, no suppression, no conflicting active sequence, approved content/destination and available limits. A high fit assessment cannot override a failed gate.

Recommended priority: an explicit relevant demo request or positive reply with a confirmed firm/contact comes first; sourced product need plus an appropriate verified contact comes next; a plausible use case with no expressed need is a lower-priority research-qualified prospect. Inbound requests still require identity/data checks and do not prove budget, authority, purchase timing or general marketing consent. A lead becomes sales-qualified only when the conversation confirms the relevant buying conditions. Ranking is a policy ordering, not a probability of purchase.

The route can be Manage only, Launch only, both or neither/unknown. For both, choose the primary product by the requester preference or strongest supported need, retaining the other for a relevant later conversation. If tied, prepare a neutral product-discovery message rather than choosing arbitrarily or sending two emails. Examples are illustrative:

- A newly announced solo practice seeking a website: Launch first; Manage remains potential/unknown until its operating need is known.
- An established eight-lawyer firm with a strong website requesting matter/billing coordination: Manage first; no current Launch need has been established.
- A new small firm requesting both a website and a matter workspace: both confirmed needs, with the prospect's immediate priority guiding the first message.

Guardian Review: generic inboxes cannot be personalized as named partners. Website appearance and firm size cannot establish buying intent or internal pain. Separate fit, confidence, readiness and actual interest so unknowns are retained and a ranking cannot authorize sending.

## Personalized-email contract and dashboard

The per-product handoff contains the firm/contact reference, approved product-brief version, fit status/reasons, source-backed personalization facts, hypothesis, verification state/time, contact basis, primary call to action and hold reasons. All provider IDs/secrets stay in private `.env`; lead and source business data stay in private runtime storage. Targeting and decision rules use versioned JSON without secrets.

A named-contact draft may mention the sourced role and a firm announcement, then ask whether a relevant workflow is a priority. A generic-inbox draft addresses the firm/team and asks who handles the relevant area. Neither draft claims to know that the firm loses cases, misses deadlines or uses spreadsheets without evidence. Use one primary problem, one demonstrated benefit and one action per email. Reuse approved product facts, not raw website text containing unverified claims or instructions.

The results table should show firm, contact/inbox type, country, evidenced attorney count, Manage fit/reason, Launch fit/reason, primary product, published email, verification/freshness, interest source, readiness/hold reason and source details. Discovery decisions are separate from usable-contact counts. Track qualified replies and product activation/payment later to evaluate whether the fit policy works; do not optimize only for records collected or emails sent.

## hello@meetlexmom.com and demo requests

The owner selected the intended address `hello@meetlexmom.com` and wants a mailbox containing sent mail, client replies and website demo notifications. This is not yet provisioned. October 13 DNS checks found no MX/SPF at meetlexmom.com; DMARC exists. Before configuration, inspect existing account/email products and recheck records to preserve current routing.

Read-only GoDaddy Email & Office check today used the existing delegated account session. The Users list was empty; selecting Add user displayed “Looks like you do not have any accounts.” The dialog was closed without continuing into a purchase/setup. No existing mailbox entitlement was available through this inspected account. This does not rule out another company's separate Microsoft/Google/Zoho email subscription.

Mailbox setup sequence:

1. GoDaddy showed no available email accounts in the inspected account. Check whether the company's separate email organization already includes an unused mailbox licence or a supported domain alias. Reusing an existing service may avoid another subscription, but availability and administrator authority must be verified.
2. If no service exists, choose a provider within the zero-additional-spend constraint. [Zoho's pricing page](https://www.zoho.com/mail/zohomail-pricing.html) lists free custom-domain mail in selected data centers, with no IMAP/POP/ActiveSync. It is a possible webmail/inbound option if the actual account qualifies; agent API/SMTP access and campaign suitability must be verified independently. Do not promise the free mailbox plan supports the complete agent. Google Workspace and Microsoft 365 are paid alternatives if later approved, not automatic purchases.
3. Verify domain ownership, provision `hello`, configure the selected provider's MX, SPF and DKIM while preserving a valid DMARC policy, and verify inbound/outbound authentication. Use [GoDaddy's existing Microsoft 365 setup procedure](https://www.godaddy.com/en-uk/help/create-my-microsoft-365-email-address-9137) only if that service/licence actually exists. Domain registration alone is not email hosting.
4. Give the owner provider webmail with Inbox and Sent, then connect scoped agent authorization where supported. Add an authenticated Menteso OS conversation view keyed to provider message/thread IDs. API sends must either save to the provider's Sent folder or be archived/reconciled explicitly; provider acceptance alone is not proof that the user can see a Sent item. Separate sent, delivered, replied, bounced and unsubscribed statuses.
5. Configure the Lexmom website backend to persist each demo request and product choice, then enqueue a notification to the private environment's configured `hello` recipient. Send the owner notification from an authenticated service identity with the requester's address as Reply-To, not as a spoofed From. The user-supplied address must be validated and cannot control arbitrary notification recipients or headers. Failure to email must not lose the stored request.
6. Ingest the demo request as a first-party lead with its own request ID, product/role/firm/need, campaign attribution if present and the exact contact permission. A permission to discuss a demo does not subscribe that person to unrelated marketing. Link an existing firm/contact when identity matches; suppress conflicting cold follow-ups. Provide a labelled owner notification and a tailored next-action/demonstration brief. Preferred timing is a request, not a booked appointment.
7. Test a controlled submission, mailbox receipt, requester acknowledgement if enabled, reply threading, duplicate event handling and notification retry. Never show success for email delivery merely because the form rendered or a backend accepted a record. Do not send tests or change production settings before the particular step is authorized.

The inbox and outbound campaign transport can be separate integrations if the provider requires it, with the same approved reply identity. Consumer Gmail prohibits unsolicited commercial email; [Zoho Mail usage policy](https://www.zoho.com/mail/help/usage-policy.html) treats the mailbox as normal business mail rather than a bulk sender. A free inbox does not resolve the researched cold-outreach provider prerequisite. No mailbox was created, email sent, provider credential generated, DNS changed or Lexmom backend deployed in this design pass.

Guardian Review: a demo request needs durable backend storage before notification, so an email outage cannot lose the lead. Sent-folder visibility and reply synchronization require explicit implementation/testing. Keep inbound demo requests, mailbox hosting and cold-campaign delivery as distinct readiness checks even when the owner uses one address.
