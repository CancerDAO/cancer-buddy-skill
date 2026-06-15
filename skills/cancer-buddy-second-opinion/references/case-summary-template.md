# Case Summary Template — 1-2 page

Format the case summary as follows. Keep it under 2 pages when PDF-converted. Reviewers triage quickly — front-load the specific question.

## Localization

Render the scaffold (section headers, field labels, formatting-rule prose) in **`reviewer_locale`** — the target reviewing center's language, derived in `SKILL.md` → Locale (NOT `profile.json.locale`). See [../../../references/i18n.md](../../../references/i18n.md).

- The structure below IS the `en` rendering (and the source-of-truth when a downstream concierge translates to `ja`). For any other `reviewer_locale`, treat the section headers / field labels / table column heads as a **`reviewer_locale → string table`**: localize the *keys* (e.g. "Question for Reviewer", "Diagnosis", "Best response", "Reason for discontinuation"), keep the section order and table shape 1:1.
- **Clinical entities stay verbatim regardless of `reviewer_locale`** — drug names (`osimertinib`), genes/variants (`EGFR L858R`), stage/TNM (`cT3N2M1a`, `IVA`), numbers + units (`80 mg QD`, `2.3 cm`, `VAF 42%`), biomarker labels (`PD-L1 TPS`, `TMB`, `MSS/MSI-H`). Never translate, transliterate, or normalize them — mistranslation is a P0 medical-safety bug.

The headers shown below are the `en` string-table values:

---

# Second Opinion Request — [Patient Initials], [Primary Diagnosis]

## Question for Reviewer

[One clear sentence. Examples:]
- "Is this patient a candidate for [specific trial] at your center, and if not, what alternative would you recommend?"
- "Do you agree with the proposed next-line regimen of [X + Y], or would you suggest a different approach?"
- "Is further molecular testing warranted before initiating [therapy]?"

## Patient

- Age / Sex: [age] / [M/F]
- Performance status: ECOG [0-4]
- Body weight: [xx kg]
- Key comorbidities: [list]
- Current medications: [list]

## Diagnosis

- Primary site: [e.g., Non-small cell lung cancer, adenocarcinoma]
- Date of diagnosis: [YYYY-MM]
- Initial stage: [e.g., cT3N2M1a, stage IVA per AJCC 8th]
- Current stage: [same or progressed to]

## Pathology

- [YYYY-MM hospital] biopsy: [histology summary, grade, margins if surgical]
- IHC highlights: [e.g., TTF-1 positive, Napsin-A positive, ALK IHC negative]

## Molecular profile

- [YYYY-MM, platform]: [key drivers and their allele frequencies]
- [e.g., EGFR L858R VAF 42%, TP53 co-mutation]
- TMB: [value if known]
- MSI: [MSS/MSI-H]
- PD-L1 TPS: [%]

## Treatment history

| Line | Regimen | Start | End | Best response | Reason for discontinuation |
|---|---|---|---|---|---|
| 1 | Osimertinib 80mg QD | 2023-12 | 2025-08 | PR (30% reduction) | Progression (brain) |
| 2 | [drug/regimen] | 2025-09 | ongoing | SD | — |

## Latest imaging

- [YYYY-MM-DD, modality, institution]: [key finding, in 2-3 sentences]
- Example: 2026-04-15, PET-CT, 上海某三甲: new 2.3cm lesion in right lower lobe; existing liver mets stable. Consistent with progression.

## Latest labs (relevant)

| Lab | Value | Date | Reference |
|---|---|---|---|
| ALT | 28 | 2026-04-18 | < 40 |
| Creatinine | 72 | 2026-04-18 | 50-110 |
| Hemoglobin | 118 | 2026-04-18 | 115-155 |

## Current status / question context

[2-4 sentences describing where the patient and team are today. What's been considered. Why the second opinion is sought.]

Example: "Patient has progressed on first-line osimertinib after 20 months. Primary oncologist has proposed [X]. Patient's family is considering cross-border referral given the complexity. Seeking your center's opinion on whether to continue osimertinib with local radiotherapy vs switch to platinum-doublet vs enroll in a trial targeting osimertinib resistance."

## Records enclosed

See `records-index.md`. Key items: [biopsy report, latest imaging CD, molecular panel, treatment summary from primary hospital].

## Primary oncologist contact

[Dr. Name], [Hospital], [email], [phone]. Speaks [English / Chinese].

## Patient / family contact

[Name], [WeChat / email / phone]. Prefers [language] for communication.

---

## Formatting rules

- Use the section headers above, localized to `reviewer_locale` (English values shown)
- Tables for any structured data (treatment history, labs)
- Dates always YYYY-MM-DD or YYYY-MM (date format follows `reviewer_locale` convention only if the center requires it; default ISO)
- Measurements in SI units (cm, kg, mL, mmol/L) — unit tokens are clinical entities, stay verbatim
- Drug names kept **verbatim in the source form** the record used (generic OR brand — never normalize brand→generic or vice versa; clinical entities stay verbatim per `../../../references/i18n.md` §4). Doses verbatim with units.
- Keep under 2 printed pages — use bullets, not prose, where possible
