# Cancer-type handbook module

This is a composition contract, not a store of clinical facts. Model memory is not an acceptable source for current regimens, indications, monitoring or follow-up schedules.

## Locale and source integrity

Render headings and explanations in the resolved locale. Keep cancer names, drug names, genes/variants, TNM/stage, response codes, numbers/units and source titles verbatim. Do not silently normalize an uncertain record.

For time-sensitive medical claims, use a current authoritative source appropriate to the user's jurisdiction: an official national guideline/public health body, regulator-approved label, recognized specialty-society guideline, or the treating center's written plan. Record issuing body, title, version/date, URL and access date. If current verification is unavailable, omit the option list and say what the treating clinician needs to confirm.

## Required section order

| Stable key | `zh` | `en` |
|---|---|---|
| `intro` | `### 疾病简介` | `### Disease overview` |
| `current_plan` | `### 我已知的治疗事实` | `### What is documented about my current care` |
| `questions` | `### 带去问医生的问题` | `### Questions for my clinical team` |
| `daily_life` | `### 日常生活支持` | `### Daily-living support` |
| `followup` | `### 复诊与监测计划` | `### Follow-up and monitoring plan` |
| `red_flags` | `### 紧急与尽快联系信号` | `### Urgent and prompt-contact signs` |

For other locales, translate the stable-key meaning. Clinical entities remain verbatim.

## Composition rules

### Disease overview

Explain only verified diagnosis, pathology and stage facts in plain language. Separate `documented`, `general explanation`, and `unknown`. Do not assign a stage, severity, prognosis or curability verdict.

### What is documented about current care

- Describe the purpose of the patient's documented treatment at a high level.
- Do not list alternative regimens or imply what should come next.
- A drug mechanism, indication, food instruction or common toxicity must cite a current official label or authoritative patient resource for that exact product/setting.
- Never generate a dose or schedule. Copy the written prescription only when provenance is clear; otherwise say “confirm with the prescribing team/pharmacist.”

### Questions for the clinical team

Generate five concise questions grounded in gaps or decisions visible in the record, such as treatment intent, what response will be measured, whom to call after hours, fertility needs, and which symptoms should trigger same-day contact. Questions are safer than filling gaps with generic oncology content.

### Daily-living support

Offer practical, non-prescriptive help with transport, work notes, symptom logs, meals, sleep and emotional support. Route individualized nutrition, mental-health and visit-preparation needs to their skills. Do not produce fixed exercise, sexual-health, infection or fertility rules without the treating team's plan.

### Follow-up and monitoring plan

Transcribe the patient's documented schedule. If absent, explain that cadence depends on cancer type, stage, treatment and local guideline, then prepare questions; do not invent “every 3 months” style intervals or scan/lab lists.

### Urgent and prompt-contact signs

Use the shared `medical-emergency-gate.md` for emergencies. Add treatment-specific warning signs only when supported by the current official label or the patient's written action plan. Never replace the shared chemotherapy fever threshold with a disease-specific guess.

End with the mandatory localized footer from `SKILL.md` and a compact source ledger. Do not write the module when critical diagnosis/regimen fields have unresolved red review flags.
