---
name: cancer-buddy-nutrition
description: "Individualized nutrition plans by cancer type and treatment phase (pre-op / chemo / radio / immuno / recovery). Checks drug-food interactions (ginseng↔anticoagulants, grapefruit↔TKIs, etc). Role-aware: patient-mode gives self-cook menus; caregiver-mode adds shopping lists and a week's prep plan; refuses other-family routing. Triggers on: 吃什么, 忌口, 化疗期饮食, 术后营养, 补剂, 中医饮食, 灵芝, 人参, 蛋白粉."
---

# cancer-buddy-nutrition

What the patient eats affects treatment tolerance, healing, and outcome. This skill generates evidence-based, culturally-aware meal plans tied to current treatment phase and comorbidities.

## When to use

- User asks about food / diet / forbidden foods / supplements.
- During transitions: new chemo cycle, post-op, immunotherapy start (some immune-related nutrition differences).
- User asks about specific supplements (灵芝 / 虫草 / 人参 / 蛋白粉).

## Locale

Per `../../references/i18n.md`: read `profile.json.locale` first (this skill always runs after organize, so a value should normally be present); if absent (or no profile yet), detect it from the **primary patient-facing language of the records**, tie-breaking to the **language the user is conversing in**, and write it back to `profile.json.locale` (BCP-47, e.g. `zh` / `en` / `fr`). Reuse the persisted value on every later turn so the whole journey speaks one language. An explicit user override ("answer me in English" / "用中文") always wins and is written back.

Render **every patient/caregiver-visible output in that locale** — the 7-day menu, shopping list, batch-prep plan, interactions-flagged report, supplement assessments, the family-role refusal copy, and any routing/disclaimer prose. **Keep clinical entities verbatim** (drug names, genes/variants, TNM/stage, numbers + units, scale standard names — e.g. `osimertinib`, `奥沙利铂`, `ANC < 1.0`, `EGFR L858R`) per `i18n.md` §4 — mistranslating one is a P0 safety bug. The reference files below carry their scaffold in `zh`; treat them as the **source string table** and render the localized equivalent at output time (§5 of `i18n.md`). For the generative pieces (7-day menu prose, supplement honesty replies, interaction findings) the prompt instruction is: *output all scaffold/narrative prose in `<locale>`; keep every clinical entity verbatim.*

## Preflight

Run [../../references/preflight.md](../../references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. Especially critical here: a 🔴 RED review_flag on `current_therapy` or `treatment_history[].name` makes the entire meal plan wrong (drug-food interaction table is keyed on actual drugs in use). Real failure case: when `current_therapy` was OCR'd as "瑞戈非尼 + 伊立替康" instead of the actual "雷替曲塞 + 信迪利单抗", the resulting nutrition plan included a TKI low-fat-breakfast medication-timing rule and a SN-38 delayed-diarrhea protocol — both clinically irrelevant, both confidently wrong. Block until human-resolved.

In addition:
- Require `patients/<patient_code>/profile.json` with `primary_cancer` and `current_therapy` populated; if missing, route back to organize.

## Workflow

1. Identify treatment phase from `profile.json.current_therapy` + `profile.json.treatment_history`. Phases: pre-op / post-op recovery / active chemo / active radio / active immuno / active targeted / maintenance / post-treatment survivorship.
2. Query [references/phase-based-plans.md](references/phase-based-plans.md) for the phase-appropriate nutrition rules (protein target, caloric target, hydration, foods to emphasize/avoid).
3. Cross-check patient's current medications against [references/drug-food-interactions.md](references/drug-food-interactions.md). Critical interactions (TKI ↔ 西柚汁, 华法林 ↔ 大量深色叶菜, 奥沙利铂 ↔ 冷食, 免疫抑制期 ↔ 生食) MUST be flagged.
4. Generate a 7-day menu per [references/china-dietary-templates.md](references/china-dietary-templates.md) — match to patient's regional preference (北方 / 南方 / 川湘 / 粤) if hinted in `profile.json.patient_location_hint`. Render the menu scaffold (meal labels, section titles, prep notes) in `profile.json.locale`; the `zh` templates are the source string table. For a non-`zh` locale, adapt to dishes the patient can actually source/cook in that culinary context rather than transliterating Chinese dish names, while honoring the same per-phase nutrition rules.
5. If user asks about a specific supplement, check [references/forbidden-supplement-claims.md](references/forbidden-supplement-claims.md). Respond with an honest evidence assessment (not marketing claims), written in `profile.json.locale`; keep drug/supplement standard names verbatim.

## Output

Written under `patients/<patient_code>/reports/nutrition/` (filenames are stable ASCII keys; the date in `plan-YYYY-MM-DD.md` follows ISO regardless of locale, but in-document date prose follows the locale's date format). All document **content** is rendered in `profile.json.locale`; clinical entities stay verbatim.
- `plan-YYYY-MM-DD.md` — current phase + 7-day menu + shopping list (if role=caregiver)
- `interactions-flagged.md` — drug-food interactions reviewed for this patient's current regimen
- `supplement-assessments.md` — evidence evaluation for each supplement the user has asked about

## Role behavior

- **Role = patient**: 7-day self-cook menu, portion sizes for one. "你早餐可以吃..."
  - *Disclosure*: disclosure_state=suppressed → normal; abstract drug names OK; cancer-type not surfaced.
- **Role = caregiver**: adds weekly shopping list, batch-prep plan, and "怎么让 Ta 吃得下" — because cancer-induced anorexia is the #1 reason menus fail. 2nd-person: "你这周可以给 X 准备的菜..."
- **Role = family**: refuse. Emit the localized equivalent (`profile.json.locale`) of: `日常饮食安排由主照护者把握最灵活。如果你想帮忙，可以问 Ta 这周需要补什么食材，你去采购送上门。`

## Safety

- **Never recommend "anti-cancer foods"** without level A evidence. Foods with marketing claims (灵芝孢子粉、抗癌茶、虫草) → explicitly state, in `profile.json.locale`, the equivalent of "尚无可靠循证支持抗肿瘤疗效" (keep the supplement's standard name verbatim).
- Drug-food interactions with clinical consequences (bleeding with warfarin + dark leafy greens, TKI AUC shifts with grapefruit) ALWAYS flagged in red.
- For immunocompromised phases (chemo nadir, post-transplant, high-dose steroids), emphasize food safety (avoid raw, undercooked, unpasteurized) not calorie micromanagement.
- Recognize that many patients lose 10-20% body weight during treatment — calorie goals are often "eat what you can keep down", not ideal macro ratios.
- Never tell a patient to stop an evidence-based therapy in favor of a diet (e.g., Gerson protocol).

## References

- [phase-based-plans.md](references/phase-based-plans.md) — per-phase nutrition rules
- [drug-food-interactions.md](references/drug-food-interactions.md) — common oncology drug + food combinations to watch
- [china-dietary-templates.md](references/china-dietary-templates.md) — 北方/南方/川湘/粤 modular templates
- [forbidden-supplement-claims.md](references/forbidden-supplement-claims.md) — evidence assessment of supplements patients commonly ask about
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/roles.md](../../references/roles.md)
