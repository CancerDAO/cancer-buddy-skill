---
name: cancer-buddy-nutrition
description: "Provide practical oncology nutrition support: food safety, symptom-aware meals, shopping and preparation help, and cautious supplement education. Personalization requires a nutrition safety intake; drug-food and supplement interactions must be checked against a current official label or pharmacist rather than model memory. Triggers on: 吃什么, 忌口, 化疗期饮食, 术后营养, 补剂, 中医饮食, 灵芝, 人参, 蛋白粉."
---

# cancer-buddy-nutrition

Before nutrition advice or archive preflight, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md) and the suicide-safety rules in [`safety-guardrails.md`](../cancer-buddy/references/safety-guardrails.md). Inability to drink, persistent vomiting/diarrhea, treatment fever, confusion, or rapidly worsening symptoms need clinical assessment, not a meal plan.

This skill gives practical, culturally aware nutrition support during cancer care. It does not prescribe calories, protein, supplements, fasting, or a therapeutic diet.

## When to use

- User asks about food / diet / forbidden foods / supplements.
- During transitions: new chemo cycle, post-op, immunotherapy start (some immune-related nutrition differences).
- User asks about specific supplements (灵芝 / 虫草 / 人参 / 蛋白粉).

## Locale

Per `../cancer-buddy/references/i18n.md`: if the caller / host supplies `locale` (the user's explicit product UI language), use it first. Otherwise read `profile.json.locale` when a verified archive is already open (this skill normally runs after organize, so a value should be present); if absent (or no profile yet), detect it from the **language the user is conversing in** and use it for this session. Do **not** create or modify `profile.json` merely to save a language preference — organize is the canonical `profile.json.locale` writer. An explicit user override ("answer me in English" / "用中文") always wins for the current and later turns; persist it only via the canonical writer when an authorized profile is already open.

Render **every patient/caregiver-visible output in that locale** — the 7-day menu, shopping list, batch-prep plan, interactions-flagged report, supplement assessments, the family-role refusal copy, and any routing/disclaimer prose. **Keep clinical entities verbatim** (drug names, genes/variants, TNM/stage, numbers + units, scale standard names — e.g. `osimertinib`, `奥沙利铂`, `ANC < 1.0`, `EGFR L858R`) per `i18n.md` §4 — mistranslating one is a P0 safety bug. The reference files below carry their scaffold in `zh`; treat them as the **source string table** and render the localized equivalent at output time (§5 of `i18n.md`). For the generative pieces (7-day menu prose, supplement honesty replies, interaction findings) the prompt instruction is: *output all scaffold/narrative prose in `<locale>`; keep every clinical entity verbatim.*

## Preflight

Run [../cancer-buddy/references/preflight.md](../cancer-buddy/references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. Especially critical here: a 🔴 RED review_flag on `summary.current_regimen` or a line's drug name in `treatment_lines.json` makes the entire meal plan wrong (drug-food interaction table is keyed on actual drugs in use). Real failure case: when `summary.current_regimen` was OCR'd as "瑞戈非尼 + 伊立替康" instead of the actual "雷替曲塞 + 信迪利单抗", the resulting nutrition plan included a TKI low-fat-breakfast medication-timing rule and a SN-38 delayed-diarrhea protocol — both clinically irrelevant, both confidently wrong. Block until human-resolved.

In addition:
- A profile is optional for general food-safety and symptom-support information. Archive personalization requires verified access and confirmed `summary.current_regimen`; otherwise work only from facts the user supplies in the current conversation.
- **Don't gate every concrete answer behind the full intake.** Generally-safe, act-tonight suggestions (a few high-protein soft-food combos, ordinary safe food handling, small-frequent-meals) can be given first from what the user already said — then ask the intake to personalize. Withhold only the drug-timing/interaction, calorie/protein-target, and restriction-specific pieces until the relevant intake answer is in. See [references/phase-based-plans.md](references/phase-based-plans.md) → "Act-tonight defaults" and "When family push back on 忌口".
- Before a personalized menu, ask the **nutrition safety intake**, but **triage it**: the two load-bearing questions are (1) recent unintentional **weight change** and (2) **swallowing/chewing and how much they're actually eating/drinking**. Ask those two first. The rest are optional and can come later if relevant: vomiting/diarrhea/constipation; allergies; diabetes; kidney/liver/heart or fluid-restriction conditions; ostomy/short-bowel or major GI surgery; current treatment; all prescribed/OTC medicines, herbs and supplements; and any written restrictions from the clinical team. Say plainly, in the user's locale, the equivalent of **"答得动多少算多少，不用一次答全，先答得上的就行"** so the questions never read as a gate.
- If there is substantial weight loss, very poor intake, recurrent dehydration, tube/IV feeding, swallowing risk, complex GI surgery, severe organ dysfunction, or conflicting restrictions, **still hand the 2–3 generally-safe soft-food combos they can act on tonight** and recommend prompt assessment by the oncology team and an oncology dietitian — escalation is a reason to route to the team, not a reason to leave the patient with nothing to eat tonight. Hold back only targets, drug-timing and restriction-specific advice.

## Workflow

1. Establish the user's goal. Confirm urgent symptoms have already gone through the emergency gate. **Lead with 2–3 concrete, generally-safe high-protein soft-food combos they can act on tonight** (from [references/phase-based-plans.md](references/phase-based-plans.md) → "Act-tonight defaults"), **then** ask the triaged nutrition safety intake above (weight change + swallowing/intake first; "答得动多少算多少"). Don't make the meal help wait on the questionnaire.
2. Use [references/phase-based-plans.md](references/phase-based-plans.md) for **supportive options**, not fixed nutrient targets. Preserve the treatment team's written restrictions exactly.
3. For every medicine/herb/supplement question, follow [references/drug-food-interactions.md](references/drug-food-interactions.md): verify against a current official product label or an oncology pharmacist. Never infer “safe,” “no interaction,” a timing gap, or a dose from model memory.
4. Offer a flexible 1-day example first. Generate a 7-day menu from [references/china-dietary-templates.md](references/china-dietary-templates.md) only if the user wants it and the intake reveals no unresolved contraindication. State which preferences and restrictions were used. Do not attach numeric calorie/protein/fluid targets unless they were supplied by the treating team or oncology dietitian.
5. For supplements, use [references/forbidden-supplement-claims.md](references/forbidden-supplement-claims.md). Give evidence status and uncertainties; do not provide a dose, schedule, washout interval, product recommendation, or “safe amount.”

## Output

Written under `patients/<patient_code>/reports/nutrition/` (filenames are stable ASCII keys; the date in `plan-YYYY-MM-DD.md` follows ISO regardless of locale, but in-document date prose follows the locale's date format). All document **content** is rendered in `profile.json.locale`; clinical entities stay verbatim.
- `plan-YYYY-MM-DD.md` — current phase + 7-day menu + shopping list (if role=caregiver)
- `interactions-flagged.md` — source-backed checks, unresolved questions, label date/region, and pharmacist follow-up
- `supplement-assessments.md` — evidence evaluation for each supplement the user has asked about

## Role behavior

- **Role = patient**: give general food-safety and symptom-aware support; personalize only with verified archive access and after the nutrition safety intake.
- **Role = caregiver**: add shopping/prep support without assuming authority; archive personalization requires a verified scope.
- **Role = family**: provide general practical support (food delivery, shopping, asking preferences) without reading patient data or prescribing a menu.

*Disclosure* ([`disclosure-behavior.md`](../cancer-buddy/references/disclosure-behavior.md)): `disclosure_state` is a communication-planning hint, not access control. General food-safety support needs no diagnosis details; before a personalized plan, ask the authorized patient **how much cancer-type detail** to surface in the plan itself — a caregiver-set `suppressed` paces communication, it never blocks the patient's own plan.

## Safety

- **Never recommend "anti-cancer foods"** without level A evidence. Foods with marketing claims (灵芝孢子粉、抗癌茶、虫草) → explicitly state, in `profile.json.locale`, the equivalent of "尚无可靠循证支持抗肿瘤疗效" (keep the supplement's standard name verbatim).
- Never declare an interaction or lack of interaction from training memory. Record the exact current label/pharmacist source, jurisdiction, access date, and what remains unknown.
- Do not impose a “neutropenic diet” from an ANC number alone. Follow the treating team's instructions and emphasize ordinary safe food handling; transplant programs may have specific rules.
- Unintentional weight loss or poor intake is a reason to escalate, not a reason to invent a calorie/protein target.
- Never advise changing the dose/timing of a medicine, separating a supplement by a guessed number of hours, or stopping a medicine. Route those decisions to the prescribing team/pharmacist.
- Never tell a patient to stop an evidence-based therapy in favor of a diet (e.g., Gerson protocol).

## References

- [phase-based-plans.md](references/phase-based-plans.md) — per-phase nutrition rules
- [drug-food-interactions.md](references/drug-food-interactions.md) — common oncology drug + food combinations to watch
- [china-dietary-templates.md](references/china-dietary-templates.md) — 北方/南方/川湘/粤 modular templates
- [forbidden-supplement-claims.md](references/forbidden-supplement-claims.md) — evidence assessment of supplements patients commonly ask about
- [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md)
- [../cancer-buddy/references/roles.md](../cancer-buddy/references/roles.md)
