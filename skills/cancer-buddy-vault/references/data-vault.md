# Patient Data Vault Governance

This reference defines minimum product behavior; it is not a legal opinion or a complete security design.
Apply the current law, deployment jurisdiction, actor, data type, purpose, recipient, and transfer method.

## 1. Data classification

Treat identifiable health records, genomics, pathology, images, treatment history, disclosure preferences,
and family relationships as highly sensitive. A pseudonym, hashed identifier, masked text, or removed name
does not guarantee anonymity or prevent re-identification. Never promise “impossible to re-identify.”

Keep these layers distinct:

- raw originals: encrypted, access-controlled, immutable/versioned;
- derived sidecars: provenance-linked and minimized;
- patient-facing artifacts: minimum necessary content;
- analytics/research exports: separately authorized, assessed, and de-identified to the applicable standard.

## 2. Access and authorization

- Authenticate the actor; `patient_code` and `role.json` are not credentials.
- Enforce least privilege, purpose limitation, time-bounded caregiver authorization, and revocation.
- Log read, export, share, correction, deletion, and authorization events in a tamper-evident audit trail.
- Do not assume a spouse, adult child, or “primary caregiver” has access authority.
- Concurrent edits require conflict handling; do not use silent last-write-wins for clinical or permission data.

## 3. Integrity and provenance

- Preserve source files and cryptographic hashes according to the retention policy.
- Store `source_reported`, `patient_reported`, `caregiver_reported`, and `system_normalized` separately.
- Corrections create a new version; they do not erase the original or remap its anchor.
- Conflicting clinical values remain `disputed` until an amended source or authorized clinician attestation.
- Test backup restoration, key rotation, access revocation, and audit-log completeness.

## 4. Retention and deletion

Define retention by data class, purpose, consent/legal basis, clinical need, contract, and law. Do not claim
that PIPL requires every access log to be kept for three years. PIPL Article 56 specifies at least three
years for personal-information protection impact-assessment reports and processing records; other
records may have different requirements.

No uploaded file is deleted on model confidence or user silence. Show an item-specific preview and obtain
explicit confirmation for irreversible deletion, subject to legal/clinical retention obligations. Record
the action and outcome.

## 5. Incident response

Maintain detection, containment, investigation, evidence preservation, risk assessment, notification,
recovery, and post-incident review procedures. Do not encode a universal “72-hour PIPL notification”
rule. PIPL Article 57 requires immediate remedial measures and notification to the responsible authority
and individuals, subject to its stated conditions; other jurisdictions may impose different clocks.

## 6. Cross-border and human genetic resources

Do not state that all genomic data must remain in China. Before any transfer or remote access, determine:

- controller/processor and domestic/foreign recipient status;
- purpose, legal basis, consent, data minimization, and PIPL cross-border mechanism;
- whether the information is human genetic resource information under the current HGR rules;
- whether international cooperation approval/filing, prior report, backup, or security review applies;
- cybersecurity, data-security, export-control, ethics, and institutional requirements.

The 2023 HGR implementing rules distinguish human gene/genome information from general clinical,
imaging, protein, and metabolite data and apply different routes by activity and recipient. Route every
real transfer to qualified privacy/HGR counsel and the participating institutions; fail closed until the
required determination is documented.

## 7. Patient-facing promises

Allowed: describe actual encryption, access control, retention, deletion, sharing, and incident processes
that the deployed host has implemented and verified.

Forbidden: “fully anonymous,” “cannot be re-identified,” “never leaves China,” “always deleted,” “HIPAA/
PIPL compliant,” or a breach deadline unless deployment-specific evidence and current legal review support
the exact claim.

## 8. Official sources

- PRC Personal Information Protection Law:
  https://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html
- PRC Regulation on the Administration of Human Genetic Resources:
  https://www.nhc.gov.cn/bgt/gwywj2/201906/7f057bf005b44d87894e6764e73d557a.shtml
- MOST 2023 Implementing Rules:
  https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/bmgz/202306/t20230601_186416.html

Last legal-source check: 2026-07-17. Re-verify at use time.
