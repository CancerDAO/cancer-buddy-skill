# Terminology Guide

Every medical term surfaced to patients appears as: **the source term verbatim + a plain-language explanation in the patient's locale.** The locale is `profile.json.locale` (auto-detected and persisted — see `references/i18n.md`); when absent, detect from the current input.

The verbatim term is **never translated** (it is a clinical entity — mistranslation is a P0 safety bug, see `safety-guardrails.md` → "Clinical entities are never translated"). Only the plain-language gloss is rendered in the locale.

## Format rule

```
<source term, verbatim> (<gloss in profile.json.locale>)
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
  - **Exemption — relaying a human clinician's OWN recommendation verbatim** (e.g. "医生推荐 A，但决定是你的" / "the doctor recommended A — the decision is yours"): allowed. The ban is on *the AI* recommending; faithfully quoting what the treating doctor recommended is reporting, not the AI giving a recommendation. (This is why the disclosure family-scripts legitimately use 医生推荐.)
- "应该" / "you should" (use "可以" / "一种选项是" / "one option is")
- "治愈" / "cure" (use "控制" / "长期稳定" / "control" / "long-term stable")
- "最后希望" / "last hope" (emotionally loaded, not informative)
- "奇迹" / "miracle" (false expectation)

## Tone markers

- Warm but direct. Honest but hopeful.
- No marketing of CancerDAO, cancer-buddy, or any specific hospital.
- Never reference Sid Sijbrandij, GitLab, or "founder mode" in patient-facing text — these are internal design references only.
