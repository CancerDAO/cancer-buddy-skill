---
name: cancer-buddy-nutrition
description: "按癌种与治疗阶段（术前/化疗/放疗/免疫/康复）生成个体化饮食方案，并核查药物-食物相互作用（人参↔抗凝、西柚↔TKI 等）。Use when 患者或照护者问吃什么、忌口、补剂能不能吃、某药配某食物有没有冲突，或在新化疗周期/术后/免疫治疗起始等阶段切换时。Triggers on: 吃什么, 忌口, 化疗期饮食, 术后营养, 补剂, 保健品, 中药冲突, 中医饮食, 灵芝, 孢子粉, 人参, 蛋白粉."
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: nutrition oncology drug-food-interactions supplements diet caregiver
---

# cancer-buddy-nutrition

What the patient eats affects treatment tolerance, healing, and outcome. This skill generates evidence-based, culturally-aware meal plans tied to current treatment phase and comorbidities.

## When to use

- User asks about food / diet / forbidden foods / supplements.
- During transitions: new chemo cycle, post-op, immunotherapy start (some immune-related nutrition differences).
- User asks about specific supplements (灵芝 / 虫草 / 人参 / 蛋白粉).

## Preflight

Run [../../references/preflight.md](../../references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. Especially critical here: a 🔴 RED review_flag on `current_therapy` or `treatment_history[].name` makes the entire meal plan wrong (drug-food interaction table is keyed on actual drugs in use). Real failure case: when `current_therapy` was OCR'd as "瑞戈非尼 + 伊立替康" instead of the actual "雷替曲塞 + 信迪利单抗", the resulting nutrition plan included a TKI low-fat-breakfast medication-timing rule and a SN-38 delayed-diarrhea protocol — both clinically irrelevant, both confidently wrong. Block until human-resolved.

In addition:
- Require `patients/<patient_code>/profile.json` with `primary_cancer` and `current_therapy` populated; if missing, route back to organize.

## 证据契约

每一条向患者展示的 🔴 红色（必须避免）或 🟡 黄色（需谨慎）药物-食物/补剂相互作用，**必须**满足以下之一：

1. 通过 **web-access skill** 实时联网核实于权威源（FDA/NMPA 说明书、DrugBank、Lexicomp、UpToDate、PubMed 等），并随条目附上来源链接；或
2. 携带可追溯的内联引用（说明书条目、指南、文献 PMID）。

**禁止**仅凭训练记忆就把某条相互作用作为红色「必须避免」直接发给患者。

若当前离线、无法联网核实，或核实后仍不确定：**不得**标红，一律降级呈现为 🟡「需药师确认（未在线核实）」，并提示患者向主诊医生/药剂师确认。

充分确立的经典相互作用（如西柚↔TKI、华法林↔维 K 食物、奥沙利铂↔冷食）依然可用作示例，但向患者展示时**每条都必须带上来源引用**——「众所周知」不能替代引用。

## Workflow

1. Identify treatment phase from `profile.json.current_therapy` + `profile.json.treatment_history`. Phases: pre-op / post-op recovery / active chemo / active radio / active immuno / active targeted / maintenance / post-treatment survivorship.
2. Query [references/phase-based-plans.md](references/phase-based-plans.md) for the phase-appropriate nutrition rules (protein target, caloric target, hydration, foods to emphasize/avoid).
3. Cross-check patient's current medications against [references/drug-food-interactions.md](references/drug-food-interactions.md). Critical interactions (TKI ↔ 西柚汁, 华法林 ↔ 大量深色叶菜, 奥沙利铂 ↔ 冷食, 免疫抑制期 ↔ 生食) MUST be flagged.
4. Generate a 7-day menu per [references/china-dietary-templates.md](references/china-dietary-templates.md) — match to patient's regional preference (北方 / 南方 / 川湘 / 粤) if hinted in `profile.json.patient_location_hint`.
5. If user asks about a specific supplement, check [references/forbidden-supplement-claims.md](references/forbidden-supplement-claims.md). Respond with honest evidence assessment, not marketing claims.

## Output

Written under `patients/<patient_code>/reports/nutrition/`:
- `plan-YYYY-MM-DD.md` — current phase + 7-day menu + shopping list (if role=caregiver)
- `interactions-flagged.md` — drug-food interactions reviewed for this patient's current regimen
- `supplement-assessments.md` — evidence evaluation for each supplement the user has asked about

## Role behavior

- **Role = patient**: 7-day self-cook menu, portion sizes for one. "你早餐可以吃..."
  - *Disclosure*: disclosure_state=suppressed → normal; abstract drug names OK; cancer-type not surfaced.
- **Role = caregiver**: adds weekly shopping list, batch-prep plan, and "怎么让 Ta 吃得下" — because cancer-induced anorexia is the #1 reason menus fail. 2nd-person: "你这周可以给 X 准备的菜..."
- **Role = family**: refuse. Emit: `日常饮食安排由主照护者把握最灵活。如果你想帮忙，可以问 Ta 这周需要补什么食材，你去采购送上门。`

## Safety

- **Never recommend "anti-cancer foods"** without level A evidence. Foods with marketing claims (灵芝孢子粉、抗癌茶、虫草) → explicitly state "尚无可靠循证支持抗肿瘤疗效"。
- Drug-food interactions with clinical consequences (bleeding with warfarin + dark leafy greens, TKI AUC shifts with grapefruit) flagged in red **only when verified per the 证据契约**; unverifiable ones degrade to 🟡「需药师确认（未在线核实）」, never silent red-from-memory.
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
