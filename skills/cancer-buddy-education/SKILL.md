---
name: cancer-buddy-education
description: "Generate a patient-friendly education handbook (Markdown with Mermaid diagrams) from the MTB report and patient profile. Includes quick reference card, my-health-summary in plain language, drug sheets with side-effect management, daily living guide, follow-up schedule, cost/insurance navigation, FAQ. v1 basic version; v2 absorbs content from vmtb-skill's vmtb-patient-education. Triggers on 宣教手册, 给我爸妈看的版本, patient handbook, 患者教育."
---

# cancer-buddy-education

Turn clinical output into something the patient (and their family) can actually use day to day.

## When to use

- Patient has at least `profile.json` + one MTB report (lite or full).
- Patient says: 宣教手册 / 给我爸妈看的版本 / 我爸妈看不懂报告 / patient handbook.

## Inputs

- `patients/<pid>/profile.json`
- MTB report: prefer `patients/<pid>/reports/mtb-full/` if exists; fallback to `patients/<pid>/reports/mtb-lite/`.
- Treatment timeline, comorbidities, current medications.

## Output

Written under `patients/<pid>/reports/education/`:
- `<pid>_<date>_患者教育手册.md` — main handbook
- `quick-reference-card.md` — one-pager with emergency info and key contacts
- `drug-sheets/<drug>.md` — per-drug handout (mechanism, dose, side effects, when to call the doctor)

## Workflow

See [references/handbook-template.md](references/handbook-template.md) for the full template. Main steps:

1. Read MTB report (full preferred, lite fallback).
2. Extract: treatment plan, drug list, monitoring schedule, comorbidity interactions.
3. Select relevant handbook chapters based on patient's condition (skip chemotherapy chapter if immunotherapy only, include diabetes chapter if comorbid T2DM, etc.).
4. Render in Markdown with:
   - Cover page (name, patient_code, date, physician contact)
   - Quick reference card (emergency phone, ER criteria — fever > 38.5°C, new bleeding, etc.)
   - My Health Summary (1 page, plain language)
   - Per-drug sheets (what it does, how to take, side-effect watchlist)
   - Daily living guide (nutrition placeholder → full version in v2 nutrition skill, exercise, sleep, work)
   - Follow-up schedule (derived from cancer-buddy-manage monitoring calendar)
   - Cost and insurance navigation (reference: [../../cancer-buddy-access/references/access-pathways.md] for drug access + insurance section)
   - FAQ (common patient questions grouped by disease stage)
5. Embed Mermaid diagrams: disease-mechanism flow, treatment-decision tree.

## Tone

- Warm, direct, practical. Talk like a friend with medical knowledge.
- Every medical term bilingual + plain explanation (see `terminology.md`).
- Section-end: "你家里有人能帮你执行这一段吗？不行的话，搭子可以帮你安排提醒。"

## Safety

Apply `safety-guardrails.md` rules:
- **Mandatory footer** on every handbook, quick-reference card, and drug sheet: `本手册为信息参考，任何治疗调整必须与主诊医生确认。`
- **No medical recommendations** — explain what drugs / tests / side-effects are, never instruct the patient to change dose, stop a drug, or skip a visit without clinician sign-off.
- **ER criteria are absolute** — fever > 38.5°C, new bleeding, severe dyspnea, altered mental status → `立即就医，不要等门诊`.

## Role behavior

- **Role = patient**: patient self-study handbook. 1st-person, includes my-health-summary, drug sheets, daily living guide.
- **Role = caregiver**: caregiver operator manual. Same structure but reframed: "你陪 Ta 做化疗当天需要准备…", "Ta 的化疗药清单 + 你该留意的红旗症状", "如果你是一个人陪诊的话…". Add a `## 你的自我照顾` chapter (1 page).
- **Role = family**: 2-page 亲友简报. Disease name + plain-language explanation, current treatment phase, one-sentence prognosis, "你能帮上的三件事", "请不要做的三件事"（不问"还有多久"、不提新的偏方、不比较其他癌友）.

## References

- [handbook-template.md](references/handbook-template.md) — full template
- [../../references/terminology.md](../../references/terminology.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
