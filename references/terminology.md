# Terminology Guide

Every medical term surfaced to patients must appear as: Chinese + English + plain-language explanation.

## Format rule

```
<中文> (<English>) — <一句话通俗解释>
```

Example:
- 腺癌 (adenocarcinoma) — 由腺体细胞长出来的癌，肺癌里最常见的一种
- 铂类化疗 (platinum-based chemotherapy) — 含顺铂或卡铂的化疗方案
- 客观缓解率 (ORR, objective response rate) — 吃药后肿瘤明显缩小的患者比例

## Vocabulary coverage

Every sub-skill output that surfaces the following categories must follow this format on first use:
- Diagnoses and histology
- Drug names (generic + brand)
- Mechanism-of-action terms (EGFR TKI, PD-1 inhibitor, etc.)
- Tumor response criteria (RECIST, iRECIST, CR, PR, SD, PD)
- Lab value abbreviations first time they appear
- Clinical trial phase terms (Phase I/II/III, expansion cohort)

After first use, plain Chinese is fine. Bilingual terms do not need to repeat.

## Forbidden phrases

Never use in patient-facing output:
- "推荐" (use "匹配" / "可以考虑讨论")
- "应该" (use "可以" / "一种选项是")
- "治愈" (use "控制" / "长期稳定")
- "最后希望" (emotionally loaded, not informative)
- "奇迹" (false expectation)

## Tone markers

- Warm but direct. Honest but hopeful.
- No marketing of CancerDAO, cancer-buddy, or any specific hospital.
- Never reference Sid Sijbrandij, GitLab, or "founder mode" in patient-facing text — these are internal design references only.
