# PCT contact verification

Work-in-progress handoff (2026-09-07): the user clarified that email and phone
cannot automatically be attributed to the agent. The agent-only policy
described below is the current implementation, but it requires correction.
Identify each contact field's actual owner and keep Agent Name independently
grounded in the agent section. Update selection rules and tests together before
considering this workflow complete. Live image validation is also pending
because the shared OpenAI account returned `credit_balance_exhausted`.

The extractor reads the original PDF images using OpenAI, then validates the
structured fields against the configured selection rules. It reuses
`OPENAI_API_KEY` from the existing root `.env`; `PCT_OPENAI_API_KEY` is an optional
override. Keys are never included in reports or evidence files.

`contact_rules.json` is the teaching configuration. Edit `include_roles`,
`exclude_roles`, `exclude_email_domains`, and `instructions` to specify wanted
contacts. Add reviewed examples with `observed`, `expected`, and `explanation`.
These rules/examples are supplied with every extraction; this is prompt-based
teaching, not model fine-tuning. Do not add production contact examples to a
public repository. Use an ignored local JSON file with `PCT_AI_RULES_FILE` when
teaching with real examples.

Current policy: preserve WIPO Applicant, Title, Publication No and Application
No as source data. Enrich the agent/attorney/representative contact only. Do not
substitute an applicant or inventor if no agent contact is available. This
was based on an interpretation the user subsequently corrected. The older process
document's ambiguous applicant-versus-agent fallback is not applied silently.

Every extracted field identifies its source block, owner, role, section heading,
page and evidence line. Phone, email and Agent Name must come from the same
block/owner. Separate agents are not merged, even if their company is the same.
Agent Name never takes a name from the WIPO Applicant column. Missing individual
fields remain blank. Country is read from the selected contact's country/address
and normalized through ISO country lookup, never from the application or phone
prefix. The selected entity type supplies Slf, Corp or Ind (matching Aneeq); uncertain
classification remains blank. No Info means no usable wanted contact was found
in the reviewed complete document. API errors and ambiguous contacts are review
cases, not No Info. Repeated and Uns are not guessed without defined rules.

Office contacts, fax, identifiers, form labels and unclear characters are
excluded. Four synthetic teaching examples cover applicant-versus-agent
separation, different agents, contact country and missing agent contacts.

Only visually legible fields with page references and supporting evidence are
exported. `verified` means the model read the value from the document; it is not
a guarantee that an address exists or that the model cannot make a mistake.
Review a labeled sample before a large production batch.

Both worked/not-found Excel reports use exactly the 12 column headings and order
from PCT Data(Aneeq).xlsx, including the spelling "Priorty Date". Verification
notes and evidence stay in local audit files, with no extra report columns.
Uncertain contacts and API failures are withheld from the worked report. The local `ai-evidence` directory
under `outputs/pct-work-sheets` stores the source PDF and verification JSON,
including raw OCR, extracted fields, rules and model. API responses use
`store=false`. The default reviews up to the first five pages; increase
`PCT_AI_MAX_PAGES` up to ten if needed. A negative result on a longer document is
marked for review rather than a definitive absence of contacts.

Verified results are cached only for identical PDF bytes, metadata, model and
rules. Applicant-name cache reuse is disabled while AI verification is enabled.
Old progress without the current verification revision is not trusted as
verified work. Existing spreadsheets are not automatically rewritten.

Run tests from the project root:

    .venv/Scripts/python.exe -m pytest agents/pct_agent/test_ai_verifier.py agents/pct_agent/test_contact_ownership.py -q

`PCT_AI_VERIFY_ENABLED=false` opts into legacy OCR-only extraction; it does not
provide verified contact-role metadata and is unsuitable for verified output.
No scraper scheduling or CAPTCHA behavior is changed by this feature.

API references:
- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/docs/guides/structured-outputs
