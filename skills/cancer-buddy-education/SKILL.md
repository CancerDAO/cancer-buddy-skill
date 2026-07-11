---
name: cancer-buddy-education
description: "Generate a patient-friendly education handbook (Markdown with Mermaid diagrams) from the patient profile + organize's structured JSONs (and an MTB report when one is available — not required). Includes quick reference card, my-health-summary in plain language, drug sheets with side-effect management, daily living guide, follow-up schedule, cost/insurance navigation, FAQ. Absorbs mechanism diagrams, cancer-type modules, and phase-organized FAQ from vmtb-patient-education. Also provides **conditional / severity education** — general 'if the pathology shows X, generally the management is Y' scenario-mapping for questions like 严不严重 / 能治好吗 / 是不是晚期 / 预后 / 会不会复发 / 要不要化疗, framed as '一般而言 / 如果…通常… / 最终以病理 + 主诊医生为准' — never a personal verdict, stage, prognosis number, or treatment decision. Triggers on 宣教手册, 给我爸妈看的版本, patient handbook, 患者教育, 严不严重, 能治好吗, 是不是晚期, 预后, 会不会复发, 要不要化疗."
---

# cancer-buddy-education

Before education or archive preflight, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md) and the suicide-safety rules in [`safety-guardrails.md`](../cancer-buddy/references/safety-guardrails.md). Education never delays urgent assessment.

Turn clinical output into something the patient (and their family) can actually use day to day.

## When to use

- Patient has at least `profile.json` + organize's structured JSONs. An MTB report (`mtb-full` from `vmtb-skill`, or `mtb-lite` from the private pro-skill) **enriches** the handbook but is **not required** — education works from organize's outputs alone.
- Patient says: 宣教手册 / 给我爸妈看的版本 / 我爸妈看不懂报告 / patient handbook.
- **Conditional / severity education (不生成整本手册，行内条件式解释)**: patient asks 严不严重 / 能治好吗 / 是不是晚期 / 预后 / 会不会复发 / 要不要化疗 — give the general "如果病理是 X，一般怎么处理、大致怎么走" scenario map, drawing cancer-type depth from [`references/cancer-type-modules.md`](references/cancer-type-modules.md). **This follows the router's 条件式教育 pattern + guardrails verbatim** (see `../cancer-buddy/SKILL.md` 「条件式教育」 and `../cancer-buddy/references/safety-guardrails.md` → *Conditional education is allowed*): 一般而言 / 如果…通常… framing, **never** a personal stage/prognosis/verdict/number or a treatment decision, respect `disclosure_state`, crisis-detection first, always close with "你具体落在哪一支，病理 + 主诊医生定" + a doctor-question list.
  - **报告逐词科普（患者只问某个吓人的词是什么意思时）**：先给一句**加粗的 TL;DR 安心话**压在最前（如"**两个词判不出你几期，别自己吓自己**"），让安心先落地，再展开逐词解释；解释**带一个轻量来源锚**（如"这是病理报告里的常规描述项 / 病理学的基础常识"；涉及分期分类时可点"T/N/M 分期分类来自 AJCC / NCCN 等通行标准"——是标准框架，不是某个编造的研究/数字），让"可溯源"落地而不编造具体研究。若给年轻患者"底子好更扛治疗"这类一般性安慰，**补一句不抵消的谨慎**（如"年轻确诊的某些癌种反而可能进展偏快，所以更要跟紧医生"），别让安慰被读成个人预后判决。若患者**只问词义**、没问预后，就**别主动铺"早期 vs 晚期"这类预后向条件地图**（那会把没问的担忧塞给 Ta，踩 R2 红线边缘）——把一般规律更明确地收成"带去问医生的问题"。**当你顺势提出"帮你把病历整理成清单/时间线"时，附一句 RL4 同意话**（如"这些只在你这台设备上、只这次用来帮你整理，你说删就删"）。

## Locale

Read [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md). The whole handbook is a patient-visible template artifact, so before rendering anything:

1. If the caller / host supplies `locale` (the user's explicit product UI language), use it first.
2. Otherwise read `patients/<pid>/profile.json` → `locale`. If present, use it — do not re-detect (education runs after organize, so a `locale` is almost always already persisted).
3. If absent (no profile, or `locale` is null), detect from the **primary patient-facing language of the records**, tie-breaking to the language the user is asking in (the `record-consuming generative sub-skills` row in `../cancer-buddy/references/i18n.md` §2), and use it for this session — do **not** create or modify `profile.json` merely to save a language preference (organize is the canonical writer).
4. Render every patient-visible scaffold string in that `locale` — handbook section titles, quick-reference-card labels, my-health-summary prose, drug-sheet headings, daily-living / follow-up / cost-navigation copy, FAQ question+answer prose, mechanism-diagram explanations, the family 亲友简报, ER-criteria wording, and the mandatory footer. The handbook is generated prose + templates, so this is a prompt instruction: **"Output all scaffold/narrative prose in `<locale>`; keep clinical entities verbatim per `../cancer-buddy/references/i18n.md` §4."** Template-style references (`cancer-type-modules.md` 6-subsection headings, `expanded-faq.md` phase headings) carry their own per-locale heading table — follow it.
5. Preserve the source form of clinical entities regardless of `locale`—drug names, genes/variants, TNM/stage, response codes, numbers + units, and biomarker labels. A verified normalized term or plain-language gloss may appear beside the source term with provenance; never silently replace it.
6. Honor an explicit user language override ("给我爸妈出英文版" / "answer me in English") for the current and later turns; persist it only via the canonical writer when an authorized profile is already open.

## Preflight

Run [../cancer-buddy/references/preflight.md](../cancer-buddy/references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. The handbook propagates upstream extracted facts (diagnosis, summary.stage, summary.current_regimen, drivers from molecular.json, treatment lines from treatment_lines.json) directly to the patient/caregiver as authoritative-sounding educational content; an unconfirmed 🔴 RED review_flag on any of those fields makes the resulting handbook misleading. Block until resolved.

## Inputs

- `patients/<pid>/profile.json` + organize's structured JSONs (`patient_summary.json` / `molecular.json` / `treatment_lines.json` / `comorbidities.json`) — the always-available base.
- MTB report (optional enrichment): prefer `patients/<pid>/reports/mtb-full/` (vmtb-skill) if it exists, else `patients/<pid>/reports/mtb-lite/` (pro-skill). Absent is fine — fall back to the structured JSONs above.
- Treatment timeline, comorbidities, current medications.

## Output

Written under `patients/<pid>/reports/education/`:
- `<pid>_<date>_患者教育手册.md` — main handbook
- `quick-reference-card.md` — one-pager with emergency info and key contacts
- `drug-sheets/<drug>.md` — per-drug handout based on a current official label; reproduce only the patient's documented prescribed dose/instructions, never generate one

## Workflow

See [references/handbook-template.md](references/handbook-template.md) for the full template. Main steps:

1. Read the MTB report if one exists (full preferred, lite fallback); otherwise read organize's structured JSONs (`patient_summary.json` / `molecular.json` / `treatment_lines.json`) directly as the source of treatment facts.
2. Extract documented treatment facts, drug list, monitoring schedule, and comorbidities. Mark absent or conflicting facts as unknown; do not complete them from model knowledge.
3. Select relevant handbook chapters based on patient's condition (skip chemotherapy chapter if immunotherapy only, include diabetes chapter if comorbid T2DM, etc.).
   - **Mechanism diagrams**: pull relevant diagrams from `references/mechanism-diagrams.md` based on patient's `summary.current_regimen` type (chemo / targeted / immuno / radio).
   - **Cancer-type module**: include the patient's primary cancer section from `references/cancer-type-modules.md`; treatment and follow-up statements require current authoritative sources and remain general education.
   - **FAQ**: pull phase-relevant questions from `references/expanded-faq.md` based on current therapy phase (newly-diagnosed / active-treatment / survivorship).
4. Render in Markdown — all scaffold/narrative prose in `profile.json.locale`, clinical entities verbatim (§Locale) — with:
   - Cover page (name, patient_code, date, physician contact)
   - Quick reference card (oncology contact, local emergency number, and the shared urgent-symptom gate; chemotherapy fever is `≥ 38.0°C` unless the treatment team supplied a lower threshold)
   - My Health Summary (1 page, plain language)
   - Per-drug sheets (what it is for, official-label food/handling points, side-effect watchlist, and when to call). “How to take” is copied only from the current label plus the patient's written prescription; conflicts go to the pharmacist/prescriber.
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
- Do not invent a treatment regimen, supportive-medication combination, dose, schedule, vaccine interval, surveillance cadence, fertility wait period, exercise target, or insurance/benefit estimate. Use the patient's written plan or a current authoritative source; otherwise turn it into a question for the treating team.
- Do not use model training knowledge as the evidence source for current treatment options or labels. Record the source URL/title, issuing body, version/date and access date for time-sensitive medical content.
- Use [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md) for urgent criteria. Do not invent a disease-specific threshold. For chemotherapy, `≥ 38.0°C` requires immediate oncology-team contact or emergency assessment unless that person's written oncology plan uses a lower threshold.

## Role behavior

- **Role = patient**: patient self-study handbook when archive access is authorized; ask how much diagnostic detail to include and offer general content without an archive.
- **Role = caregiver**: caregiver operator manual. Same structure but reframed: "你陪 Ta 做化疗当天需要准备…", "Ta 的化疗药清单 + 你该留意的红旗症状", "如果你是一个人陪诊的话…". Add a `## 你的自我照顾` chapter (1 page).
- **Role = family**: general 2-page support brief by default — and it must be a *usable education* brief, not just a communication/boundary template. Lead with a generic, plain-language condition explainer written as general education (「一般而言，XX 这类病通常是怎么回事、大致怎么治、家里能帮上什么」— 「一般而言 / 如果…通常…」framing, 最终以病理 + 主诊医生为准; never a personal stage/prognosis/verdict/number, and no fabricated study or statistic). Include patient-specific disease/treatment facts only within a verified scope and explicit share consent; never add a one-sentence prognosis. Any 费用 / 医保 line stays an explicit `[请按你家实际情况填写]` placeholder — do **not** pre-fill 「有医保在走，目前能应付」or any cost/coverage status as if it were fact. Deliver the usable brief first, close it with **one** clear next-step question (e.g. 「你们最想先帮上哪一件事？」), and **defer** the "要不要我再出一个方便微信转发的短版" offer until after that brief is out.

*Disclosure* ([`disclosure-behavior.md`](../cancer-buddy/references/disclosure-behavior.md)): `disclosure_state` plans communication pacing, it is not access control — ask the authorized patient **how much diagnostic detail** the handbook should include (layered and reversible) and preview the outline before generating; a caregiver-set `suppressed` never blocks the patient's own handbook.

## References

- [handbook-template.md](references/handbook-template.md) — full template
- [mechanism-diagrams.md](references/mechanism-diagrams.md) — disease mechanism Mermaid diagrams (absorbed from vmtb-patient-education)
- [cancer-type-modules.md](references/cancer-type-modules.md) — per-cancer-type patient modules
- [expanded-faq.md](references/expanded-faq.md) — FAQ organized by treatment phase
- [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md) — shared locale layer (host `locale` first, otherwise profile locale / detection fallback / persist / verbatim-clinical)
- [../cancer-buddy/references/terminology.md](../cancer-buddy/references/terminology.md)
- [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md)
