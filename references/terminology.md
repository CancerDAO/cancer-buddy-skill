# Terminology Guide

Every medical term surfaced to patients appears as: **the source term verbatim + validated normalized term when available + a plain-language explanation in the patient's locale.** Resolve locale per `references/i18n.md`.

## Format rule

```
<source term, verbatim> [normalized: <validated term>] (<gloss in profile.json.locale>)
```

- `zh` locale gloss:
  - 腺癌 (由腺体细胞长出来的癌，肺癌里最常见的一种)
  - 铂类化疗 (含顺铂或卡铂的化疗方案)
  - ORR, objective response rate (吃药后肿瘤明显缩小的患者比例)
- `en` locale gloss:
  - adenocarcinoma (a cancer arising from gland-forming cells; the most common type of lung cancer)
  - platinum-based chemotherapy (a chemo regimen containing cisplatin or carboplatin)
  - ORR, objective response rate (the share of patients whose tumor shrinks meaningfully on treatment)
- For any other locale (`fr` / `es` / `de` / …): keep the source term verbatim and write the one-line gloss in that locale.

When the source term and the locale already match (e.g. an English term for an `en` patient), the parenthetical is just the plain-language explanation; no second-language rendering is added.

## Vocabulary coverage

Every sub-skill output that surfaces the following categories must apply the format on first use:
- Diagnoses and histology
- Drug names (generic + brand)
- Mechanism-of-action terms (EGFR TKI, PD-1 inhibitor, etc.)
- Tumor response criteria (RECIST, iRECIST, CR, PR, SD, PD)
- Lab value abbreviations first time they appear
- Clinical trial phase terms (Phase I/II/III, expansion cohort)

After first use, the plain-language form in the locale is fine. The verbatim term does not need to repeat its gloss.

## Generating the gloss

The gloss is a short, locale-appropriate explanation — produce it via the sub-skill prompt instruction ("explain this term in one plain-language sentence in `<locale>`"), not a hardcoded per-language dictionary. The only fixed mapping in this skill family is the bucket-name table (`references/i18n.md` §6); term glosses are generated, not table-lookup.

## Forbidden phrases

Never use in patient-facing output (render the locale equivalent of these intents):
- "推荐" / "I recommend" (use "匹配" / "可以考虑讨论" / "an option to discuss")
  - **Exemption — faithfully relaying someone else's OWN recommendation, with attribution**: a treating clinician's (e.g. "医生推荐 A，但决定是你的" / "the doctor recommended A — the decision is yours"), OR a cited current guideline/label's for a *class* of patients (e.g. "指南推荐… / NCCN recommends…"): allowed. The ban is on *the AI* recommending; faithfully reporting — with attribution — what the treating doctor recommended, or what a current sourced guideline itself states, is reporting, not the AI giving a recommendation. (This is why the disclosure family-scripts legitimately use 医生推荐, and why a sourced guideline relay may say 指南推荐.) It stays reporting only while general and non-individualized — turning it into "you should take A" is the AI recommending, and forbidden.
- "应该" / "you should" (use "可以" / "一种选项是" / "one option is")
- Do not ban "治愈" / "cure" categorically. Use it only when a source clinician or current disease-specific evidence supports curative intent; otherwise describe the actual aim (cure, control, symptom relief, or uncertainty) without false reassurance.
- "最后希望" / "last hope" (emotionally loaded, not informative)
- "奇迹" / "miracle" (false expectation)

## Tone markers

- Warm but direct. Honest but hopeful.
- No marketing of CancerDAO, cancer-buddy, or any specific hospital.
- Never reference Sid Sijbrandij, GitLab, or "founder mode" in patient-facing text — these are internal design references only.
