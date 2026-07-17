---
name: cancer-buddy-education
description: "Generate a patient-friendly education handbook (Markdown with Mermaid diagrams) from the patient profile + organize's structured JSONs (and an MTB report when one is available — not required). Includes quick reference card, my-health-summary in plain language, drug sheets with side-effect management, daily living guide, follow-up schedule, cost/insurance navigation, FAQ. Absorbs mechanism diagrams, cancer-type modules, and phase-organized FAQ from vmtb-patient-education. Also provides **conditional / severity education** — general 'if the pathology shows X, generally the management is Y' scenario-mapping for questions like 严不严重 / 能治好吗 / 是不是晚期 / 预后 / 会不会复发 / 要不要化疗, framed as '一般而言 / 如果…通常… / 最终以病理 + 主诊医生为准' — never a personal verdict, stage, prognosis number, or treatment decision. **Guideline-level questions** (NCCN/CSCO/ESMO 指南建议 / 标准治疗 / 一线二线方案 / 我这类一般用什么药) are answered by a **real-source lookup at answer time** — the user's own legitimately-held current guideline file if present (read verbatim, cite version/page), otherwise a live web lookup — **never from model memory** — and returned as general conditional guidance with numbered source citations — see `references/guideline-lookup.md`. Triggers on 宣教手册, 给我爸妈看的版本, patient handbook, 患者教育, 严不严重, 能治好吗, 是不是晚期, 预后, 会不会复发, 要不要化疗, 指南建议, 标准治疗, NCCN, CSCO."
---

# cancer-buddy-education

Turn clinical output into something the patient (and their family) can actually use day to day.

## When to use

- Patient has at least `profile.json` + organize's structured JSONs. An MTB report (`mtb-full` from `vmtb-skill`, or `mtb-lite` from the private pro-skill) **enriches** the handbook but is **not required** — education works from organize's outputs alone.
- Patient says: 宣教手册 / 给我爸妈看的版本 / 我爸妈看不懂报告 / patient handbook.
- **Conditional / severity education (不生成整本手册，行内条件式解释)**: patient asks 严不严重 / 能治好吗 / 是不是晚期 / 预后 / 会不会复发 / 要不要化疗 — give the general "如果病理是 X，一般怎么处理、大致怎么走" scenario map, drawing cancer-type depth from [`references/cancer-type-modules.md`](references/cancer-type-modules.md). **This follows the router's 条件式教育 pattern + guardrails verbatim** (see `../cancer-buddy/SKILL.md` 「条件式教育」 and `../../references/safety-guardrails.md` → *Conditional education is allowed*): 一般而言 / 如果…通常… framing, **never** a personal stage/prognosis/verdict/number or a treatment decision, respect `disclosure_state`, always close with "你具体落在哪一支，病理 + 主诊医生定" + a doctor-question list.
  - **两种子问法（判定见 [`references/guideline-lookup.md`](references/guideline-lookup.md)）**：
    - **(a) 严重度/预后**（严不严重 / 能治好吗 / 是不是晚期 / 还能活多久 / 会不会复发）＝疾病生物学一般规律 → 模型通识 + `cancer-type-modules.md` 框架（现状不变）。
    - **(b) 指南级**（NCCN/CSCO/ESMO 指南建议 / 标准治疗 / 一线二线方案 / 我这类一般用什么药 / 最新获批）＝版本敏感的外部目录事实 → **走 `references/guideline-lookup.md` 的 web-access 实时检索子路径，禁 LLM 凭记忆合成**，用联网锚编号引用（见 `../cancer-buddy/SKILL.md` 「来源引用」）。边界模糊时倾向 (b)。**(b) 仍是一般性条件图、不是个人换线判决。**

## Locale

Read [../../references/i18n.md](../../references/i18n.md). The whole handbook is a patient-visible template artifact, so before rendering anything:

1. If the caller / host supplies `locale` (the user's explicit product UI language), use it first and write/update `profile.json.locale` when profile state is available.
2. Otherwise read `patients/<pid>/profile.json` → `locale`. If present, use it — do not re-detect (education runs after organize, so a `locale` is almost always already persisted).
3. If absent (no profile, or `locale` is null), detect from the **primary patient-facing language of the records**, tie-breaking to the language the user is asking in (the `record-consuming generative sub-skills` row in `../../references/i18n.md` §2), then write it back to `profile.json.locale` (BCP-47, e.g. `en` / `zh` / `fr`).
4. Render every patient-visible scaffold string in that `locale` — handbook section titles, quick-reference-card labels, my-health-summary prose, drug-sheet headings, daily-living / follow-up / cost-navigation copy, FAQ question+answer prose, mechanism-diagram explanations, the family 亲友简报, ER-criteria wording, and the mandatory footer. The handbook is generated prose + templates, so this is a prompt instruction: **"Output all scaffold/narrative prose in `<locale>`; keep clinical entities verbatim per `references/i18n.md` §4."** Template-style references (`cancer-type-modules.md` 6-subsection headings, `expanded-faq.md` phase headings) carry their own per-locale heading table — follow it.
5. Keep every clinical entity verbatim regardless of `locale` — drug names (osimertinib / 奥希替尼 as the source used them, Tagrisso), genes/variants (EGFR L858R, KRAS G12C, ALK fusion), TNM/stage (cT3N2M0, IIIA), response codes (RECIST PR, MSI-H), all numbers + units (CEA 12.4 ng/mL, 80 mg qd, fever > 38.5°C), biomarker labels (PD-L1 TPS 40%). Never translate, transliterate, or normalize them — mistranslating a clinical entity is a P0 medical-safety bug. An optional locale-appropriate gloss may be added *beside* the verbatim term in parentheses (per `terminology.md`), never replacing it.
6. Honor an explicit user language override ("给我爸妈出英文版" / "answer me in English") → update `profile.json.locale` and follow it going forward.

## Preflight

Run [../../references/preflight.md](../../references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. The handbook propagates upstream extracted facts (diagnosis, summary.stage, summary.current_regimen, drivers from molecular.json, treatment lines from treatment_lines.json) directly to the patient/caregiver as authoritative-sounding educational content; an unconfirmed 🔴 RED review_flag on any of those fields makes the resulting handbook misleading. Block until resolved.

## Inputs

- `patients/<pid>/profile.json` + organize's structured JSONs (`patient_summary.json` / `molecular.json` / `treatment_lines.json` / `comorbidities.json`) — the always-available base.
- MTB report (optional enrichment): prefer `patients/<pid>/reports/mtb-full/` (vmtb-skill) if it exists, else `patients/<pid>/reports/mtb-lite/` (pro-skill). Absent is fine — fall back to the structured JSONs above.
- Treatment timeline, comorbidities, current medications.

## Output

Written under `patients/<pid>/reports/education/`:
- `<pid>_<date>_患者教育手册.md` — main handbook
- `quick-reference-card.md` — one-pager with emergency info and key contacts
- `drug-sheets/<drug>.md` — per-drug handout (mechanism, dose, side effects, when to call the doctor)

## Workflow

See [references/handbook-template.md](references/handbook-template.md) for the full template. Main steps:

1. Read the MTB report if one exists (full preferred, lite fallback); otherwise read organize's structured JSONs (`patient_summary.json` / `molecular.json` / `treatment_lines.json`) directly as the source of treatment facts.
2. Extract: treatment plan, drug list, monitoring schedule, comorbidity interactions.
3. Select relevant handbook chapters based on patient's condition (skip chemotherapy chapter if immunotherapy only, include diabetes chapter if comorbid T2DM, etc.).
   - **Mechanism diagrams**: pull relevant diagrams from `references/mechanism-diagrams.md` based on patient's `summary.current_regimen` type (chemo / targeted / immuno / radio).
   - **Cancer-type module**: include the patient's primary cancer section from `references/cancer-type-modules.md`.
   - **FAQ**: pull phase-relevant questions from `references/expanded-faq.md` based on current therapy phase (newly-diagnosed / active-treatment / survivorship).
4. Render in Markdown — all scaffold/narrative prose in `profile.json.locale`, clinical entities verbatim (§Locale) — with:
   - Cover page (name, patient_code, date, physician contact)
   - Quick reference card (emergency phone, ER criteria — fever > 38.5°C, new bleeding, etc.)
   - My Health Summary (1 page, plain language)
   - Per-drug sheets (what it does, how to take, side-effect watchlist)
   - Daily living guide (nutrition placeholder → full version in v2 nutrition skill, exercise, sleep, work)
   - Follow-up schedule (from the treatment plan + `timeline.json`; a richer monitoring calendar comes from the private pro-skill `cancer-buddy-manage` when it is available)
   - Cost and insurance navigation (general guidance only; detailed drug-access / 同情用药 / 跨境 pathways are handled by the private pro-skill `cancer-buddy-access` when available — not part of this public companion)
   - FAQ (common patient questions grouped by disease stage)
5. Embed Mermaid diagrams: disease-mechanism flow, treatment-decision tree.

## Tone

- Warm, direct, practical. Talk like a friend with medical knowledge — in the patient's `locale`.
- Every medical term keeps its verbatim clinical form + a locale-appropriate plain-language gloss beside it (see `terminology.md` — locale-aware, not fixed bilingual).
- Section-end prompt, rendered in `locale` (zh: "你家里有人能帮你执行这一段吗？不行的话，搭子可以帮你安排提醒。"; render the same meaning in the patient's locale otherwise) — invite the patient to flag if no one at home can help execute this section, offering to set reminders.

## Safety

Apply `safety-guardrails.md` rules:
- **Mandatory footer** on every handbook, quick-reference card, and drug sheet, rendered in `locale` (zh: `本手册为信息参考，任何治疗调整必须与主诊医生确认。` — render the same disclaimer meaning in the patient's locale otherwise). The footer must be present in every locale; it is scaffold copy, not a clinical entity.
- **No medical recommendations** — explain what drugs / tests / side-effects are, never instruct the patient to change dose, stop a drug, or skip a visit without clinician sign-off.
- **Guideline-level claims come from real sources, not memory** — any "指南/NCCN/CSCO 一般怎么治 / 标准治疗是什么" content follows `references/guideline-lookup.md`: **local authoritative guideline file first (the user's own current NCCN/CSCO/ESMO copy, read verbatim + cite version/page), else live web lookup**, always verbatim grounding + numbered citation + retraction-checked. Licensing boundary = whether output is redistributed to third parties (a user reading their own copy may quote it; a central platform redistributing NCCN tables is the constrained case), not whether a local file was read. When neither local nor live lookup is reachable, a model-knowledge fallback is allowed **only** if explicitly labeled `⚠️ 未经实时核实 · 基于模型知识`, carries **no citation number**, and urges verification (guideline-lookup.md 「优雅降级」). Model memory may never be presented as a sourced/current fact (`../../references/safety-guardrails.md` → no-silent-snapshot). This is a general conditional map, never a personal treatment/换线 verdict.
- **ER criteria are absolute** — the *thresholds* are clinical entities and stay verbatim in every locale (fever > 38.5°C, new bleeding, severe dyspnea, altered mental status); the surrounding call-to-action is scaffold, rendered in `locale` (zh: `立即就医，不要等门诊`).

## Role behavior

- **Role = patient**: patient self-study handbook. 1st-person, includes my-health-summary, drug sheets, daily living guide.
  - *Disclosure*: disclosure_state=suppressed → refuse patient handbook; offer general health content only.
- **Role = caregiver**: caregiver operator manual. Same structure but reframed: "你陪 Ta 做化疗当天需要准备…", "Ta 的化疗药清单 + 你该留意的红旗症状", "如果你是一个人陪诊的话…". Add a `## 你的自我照顾` chapter (1 page).
- **Role = family**: 2-page 亲友简报. Disease name + plain-language explanation, current treatment phase, one-sentence prognosis, "你能帮上的三件事", "请不要做的三件事"（不问"还有多久"、不提新的偏方、不比较其他癌友）.

## References

- [handbook-template.md](references/handbook-template.md) — full template
- [guideline-lookup.md](references/guideline-lookup.md) — 条件式教育 (b) 指南级子路径：web-access 实时检索 + 源面优先级 + 逐字接地 + 联网锚引用
- [mechanism-diagrams.md](references/mechanism-diagrams.md) — disease mechanism Mermaid diagrams (absorbed from vmtb-patient-education)
- [cancer-type-modules.md](references/cancer-type-modules.md) — per-cancer-type patient modules
- [expanded-faq.md](references/expanded-faq.md) — FAQ organized by treatment phase
- [../../references/i18n.md](../../references/i18n.md) — shared locale layer (host `locale` first, otherwise profile locale / detection fallback / persist / verbatim-clinical)
- [../../references/terminology.md](../../references/terminology.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
