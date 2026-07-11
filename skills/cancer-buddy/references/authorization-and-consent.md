# Authorization and Consent

Conversation role controls tone. It is **not** identity proof, archive authorization, legal representation, or consent to share data.

## Two operating modes

### Stateless/general mode

Always available without a patient directory. Give general checklists, emotional support, questions for a clinician, and public resource discovery using only facts the current user supplies for this task. Do not reveal or infer facts from an archive.

### Authorized archive mode

Before reading, writing, exporting, or sharing `patients/<patient_code>/`, require a host-authenticated grant or a locally recorded grant that includes:

- an opaque `actor_id` and `data_subject_id`;
- relationship/authority basis (`self`, explicit patient authorization, verified legal representative);
- allowed scopes (`read`, `organize`, `write`, `export`, `share`, `cross_border`, `research_or_ai`);
- who granted it, when, expiry, and revocation status.

A self-declared `role=caregiver` or knowledge of `patient_code` is never enough. If the host cannot authenticate or verify a grant, stay in stateless mode and explain what authorization is needed. Do not invent an authentication mechanism.

## Identity hard-gate (demographic mismatch)

This is separate from the routine role/authorization ask above. When the **basic demographics in uploaded records (sex / age) clearly conflict with what the user says about the patient** — e.g. the records read 男 63 but the user calls the patient "我妈", or the age is off by a generation — **STOP and raise a hard identity-confirmation gate BEFORE presenting any full condition summary.**

- The reports may belong to two different people mixed together; showing one patient's sensitive records as another's is a serious harm.
- Name the specific mismatch plainly and ask the user to confirm whose records these are, e.g. `这份报告上写的是男性、63 岁，你说的是你妈妈——这两个对得上吗？会不会是两个人的报告混在一起了？`
- Do **not** proceed to a condition summary, diagnosis name, or source citations until the user resolves the conflict. If it stays unresolved, keep the archive closed and stay in stateless mode.
- This gate fires on the mismatch itself; it is not satisfied by role self-declaration or knowledge of `patient_code`.

## Consent boundaries

Obtain a separate, explicit confirmation immediately before each material operation:

- collecting/storing raw medical records;
- storing mental-health or suicide-related content;
- exporting or sharing, with recipient, purpose, exact fields/files, expiry, and revocation limits;
- cross-border transfer, with destination recipient/jurisdiction and transfer method;
- research, model training, or other AI use;
- irreversible deletion.

Consent to one purpose does not imply another. Silence is never consent. Minimize data and prefer a preview manifest before export/share.

## Children and adolescents

Medical records and information about a child under 14 are sensitive personal information under China's PIPL. Before persistent storage, export, sharing, research/AI use, or cross-border transfer, require a verified guardian/legal basis and age-appropriate assent when feasible. For ages 14–17, apply the host's jurisdictional minor-consent policy and seek the young person's assent. Emergency and suicide-safety support is never delayed for consent paperwork; persist nothing by default during the emergency.

## Disclosure state

`disclosure_state` is a communication-planning field, not an access-control list. It cannot authorize a caregiver, and it cannot be used to hide an authorized competent adult's own archive from them. If state or capacity is uncertain, label it `unknown` and offer communication support; do not let the model decide legal capacity or surrogate authority.

## Local CLI limitation

Local filesystem ownership is not proof of patient consent. A CLI skill can help create consent/grant records and enforce them, but cannot verify a person's legal identity. State this limitation rather than claiming HIPAA/PIPL compliance or secure access control.
