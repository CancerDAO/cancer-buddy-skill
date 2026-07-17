---
name: cancer-buddy-nutrition
description: "Provide symptom-directed nutrition education, food-safety guidance, and pharmacist/dietitian routing for people affected by cancer. Use for questions about eating, treatment-related nutrition symptoms, food/drug interactions, supplements, and culturally familiar meal ideas. Never prescribe nutrient targets or infer interactions from model memory."
---

# cancer-buddy-nutrition

Provide low-risk nutrition support and help the user prepare for a registered dietitian, oncology pharmacist,
or treating-team discussion. Do not generate a clinical nutrition prescription.

## Entry

1. Resolve role, authorization, locale, and provenance under the root contracts.
2. Identify the user's actual question and urgent symptoms. Persistent vomiting/diarrhea, inability to keep
   fluids down, rapid weight loss, dehydration, swallowing obstruction, suspected immune toxicity, or other
   severe/rapidly worsening symptoms route promptly to the treating team/emergency care.
3. Use only non-disputed source fields. Patient/caregiver reports remain separate.

## Workflow

- Use `phase-based-plans.md` as a symptom/setting framework. Do not auto-prescribe protein, calories,
  fluid, salt, sugar, fiber, fasting or supplements from treatment phase, albumin, ANC, or model judgment.
- Use `drug-food-interactions.md` for every medication/food/supplement question. Verify the exact drug,
  formulation and current regulator label plus an authoritative interaction resource at answer time. If
  unverified, fail closed and route to an oncology pharmacist.
- Use `forbidden-supplement-claims.md` for products/diets. Do not provide generic dose, timing, safe-use,
  anticancer or recurrence-prevention claims.
- Use `china-dietary-templates.md` for replaceable culturally familiar meal ideas after asking preferences,
  symptoms, allergies, budget and comorbidities. Portions/targets come only from an individualized plan.

## Output

Write optional patient-owned notes under `reports/nutrition/`:

- symptom-friendly food ideas and questions for the dietitian;
- medication/supplement inventory with source and verification status;
- interaction items with direct label/source URL, version/date and pharmacist-review status;
- supplement evidence/uncertainty summary.

Do not label output as a prescribed 7-day plan unless a registered dietitian supplied the targets and the
artifact clearly attributes them.

## Localization

Preserve source drug/product terms. Add validated normalized names and patient-language explanations beside
them; do not overwrite the source. Localize all scaffold and warnings.

## Safety

- Never tell a patient to start, stop, delay, retime or change a prescription medicine.
- Never claim a food, herb, vitamin, supplement or diet treats cancer or prevents recurrence without a
  current, directly applicable primary guideline claim.
- General food safety focuses on safe temperatures, hand hygiene, adequate cooking and cross-contamination;
  do not automatically impose a restrictive “neutropenic diet.”
- Suspected immune-related diarrhea is not routine chemotherapy diarrhea; escalate promptly.

## Role behavior

- **Role = patient**：提供症状导向的一般营养教育，并使用患者本人授权资料。
- **Role = caregiver**：在有效授权内帮助备餐和整理问题；观察记为 `caregiver_reported`。
- **Role = family**：无授权时只提供一般食品安全和支持建议，不查看患者记录。

## Disclosure

不得从饮食建议暗示或泄露患者未授权的诊断/分期。患者明确要求自己的信息时，家属 suppression 偏好不能覆盖；能力或代理争议转临床团队。

## References

- [phase-based-plans.md](references/phase-based-plans.md)
- [drug-food-interactions.md](references/drug-food-interactions.md)
- [china-dietary-templates.md](references/china-dietary-templates.md)
- [forbidden-supplement-claims.md](references/forbidden-supplement-claims.md)
- [../../references/clinical-content-governance.md](../../references/clinical-content-governance.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/i18n.md](../../references/i18n.md)
- [../../references/disclosure-behavior.md](../../references/disclosure-behavior.md)
