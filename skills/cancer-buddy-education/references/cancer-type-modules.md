# 癌种模块 — handbook section template

> **Trust your oncology training data**, do NOT consult hardcoded per-cancer canned content here.

This file used to contain ~370 lines of canned per-cancer content (lung / breast / colorectal / liver / gastric / lymphoma / pancreatic / etc.) — disease overview, standard regimens, FAQs, daily-life tips, follow-up cadence, red flags, all pre-written.

Deleted because:

1. The model has comprehensive oncology training data — disease biology, NCCN/CSCO regimens, common patient FAQs, and red-flag symptoms are LLM knowledge, not project knowledge
2. Canned content is always behind the latest guidelines — when a new ADC like trastuzumab deruxtecan gets a new indication, or when CSCO updates BTK inhibitor lines, every canned module silently goes stale
3. Per-patient handbooks should be tailored to the specific patient's primary_site + stage + driver mutations + line of therapy, not pulled from a generic cancer-type module

What this file contains now is a **template scaffold** that the agent fills using its own training knowledge + the patient's actual profile.

> **指南级方案不在这里靠记忆答**。本静态框架只供**疾病生物学的一般描述**（疾病简介 / 一般随访节奏 / 红旗症状）。当患者问的是**指南级断言**——"NCCN/CSCO 标准治疗是什么 / 一线二线什么方案 / 我这类一般用什么药 / 最新获批"——那是版本敏感的外部目录事实，走 [`guideline-lookup.md`](guideline-lookup.md) 的 **web-access 实时检索**（禁 LLM 凭记忆合成、带编号引用），不要用本文件或训练记忆直接给方案。理由 2（canned 必然滞后）同样适用于"凭记忆报指南方案"。

## Locale

Render all section headings, prose, daily-life advice and red-flag wording in the locale resolved per `../../../references/i18n.md` (host `locale` first, otherwise `profile.json.locale`, otherwise detection fallback + persist). Keep clinical entities verbatim in every locale: cancer-subtype acronyms (NSCLC, SCLC, TNBC, MSI-H), drug names, genes/variants, TNM/stage, response codes, numbers + units. The 6 fixed subsection headings are scaffold — they have a stable key per row and a per-locale rendering (table below); this is the only allowed fixed string mapping in this file. Everything else is generated prose, written directly in `locale`.

### Subsection heading table (stable key → per-locale slug)

| Key (stable) | `zh` (existing) | `en` |
|---|---|---|
| `intro` | `### 疾病简介` | `### Disease overview` |
| `treatments` | `### 常见治疗方案概述` | `### Common treatment options` |
| `top5_questions` | `### 患者最常问的 5 个问题` | `### 5 questions patients ask most` |
| `daily_life` | `### 日常生活调整建议` | `### Daily-living adjustments` |
| `followup` | `### 随访节奏` | `### Follow-up cadence` |
| `red_flags` | `### 红旗警示` | `### Red-flag warnings` |

For a locale not in the table, render each heading from its stable-key meaning in the target language. The cancer-type section title (`## <癌种 + English>`) keeps the English/clinical name verbatim and localizes only any plain-language wrapper.

## Section structure (project convention — keep)

Every cancer-type section in the handbook MUST have these 6 subsections, in this order, each with the per-locale heading from the table above (shown here in `zh`):

```markdown
## <癌种中文 + English>

### 疾病简介
3-5 sentences. Disease biology + sub-classification (e.g. NSCLC vs SCLC, HR+ vs TNBC, MSS vs MSI-H). Use language a layperson can follow.

### 常见治疗方案概述
Bullet list by stage / molecular subtype. Mention the specific drug class but not exact dosing. Match the patient's ACTUAL situation more closely than a generic textbook list — if profile.json shows the patient is on 5L therapy, you don't need to explain 1L options at length.

### 患者最常问的 5 个问题
EXACTLY 5 questions, in patient voice (我 / 我家人 / 是不是, or the locale equivalent), each with a 2-4 sentence direct, non-condescending answer. Surface common misconceptions — patients ask "为什么我没吸烟也得肺癌" not "what is the etiology of NSCLC".

### 日常生活调整建议
Concrete daily life: diet (route to cancer-buddy-nutrition for specifics), exercise level, work, social activity, mental health touchpoints (suggest professional mental-health support where needed — cancer-buddy does not screen or intervene), sleep, sexual health, fertility (if pre-menopausal female or young male). Avoid one-size-fits-all generic advice.

### 随访节奏
Standard follow-up cadence for this disease + stage. Time intervals (every 3 months / 6 months) + what scans + what labs.

### 红旗警示
3-6 specific symptoms that warrant immediate medical attention (not a generic "fever > 38°C"). Disease-specific (e.g. for HCC: 黄疸、腹水增加、呕血; for lung cancer: 突发胸痛、大咯血、新发偏瘫).
```

End every cancer-type section with the **single mandatory footer defined in `SKILL.md` ("Mandatory footer")** — do not invent a per-section variant. Render it in `locale` (disclaimer meaning preserved in every locale; zh canonical):
```
本手册为信息参考，任何治疗调整必须与主诊医生确认。
```

## How to compose a section

When generating handbook for a specific patient:

1. Read the cancer type from `profile.json.summary.primary` (canonical). If absent, fall back to `patient_summary.json.diagnosis.primary` (the structured diagnosis source). (There is no `primary_diagnosis.site` field in any current or retired profile schema — do not look for it.) Determine the cancer type.
2. Use your oncology training to draft the 6 subsections matching the schema above. Length: 500-800 字 per cancer type.
3. **Tailor to the patient's actual stage + line + comorbidities** — do NOT recite a generic textbook overview. If the patient is stage IV on 5L therapy, the 治疗方案概述 should focus on late-line options, not "I-II 期手术为主".
4. **Use the patient's specific drugs verbatim** when discussing their regimen — pull from `profile.json.summary.current_regimen`. If the agent doesn't recognize the drug names from training data, do NOT make up a mechanism — write `[需向主诊医生确认 <drug> 的具体作用机制]`.
5. **Cross-reference the readiness audit**: if `readiness.json.review_flags` has any 🔴 unconfirmed flags on `summary.primary` / `summary.stage` / `summary.current_regimen` / drivers (`molecular.json`), the handbook MUST NOT BE WRITTEN — the preflight Step 2.5 gate should have already blocked. (Sanity check: if you reach this step with red flags unconfirmed, something upstream is broken.)

## Uncertainty escape hatch

When you encounter a cancer subtype, regimen, or molecular target that you don't have confident training data on (rare cancer / new approval / regional variant):

- Do NOT write generic-sounding placeholder content
- Write `[需要主诊医生补充: <topic>]` in that subsection
- Note the gap in the report footer's "本手册的局限" section

## Project convention (don't trust LLM — these are workflow rules)

- Length: ~500-800 字 (or the equivalent reading length in `locale`) per cancer type, readable in 5-8 minutes by a layperson
- Reading level: junior-high (zh: 初中文化), avoid medical Latinate jargon (zh: use 化疗 not 系统性细胞毒性药物治疗; apply the same plain-language principle in every locale) — but clinical entity names stay verbatim
- Footer: the **single mandatory footer defined in `SKILL.md`** (zh: `本手册为信息参考，任何治疗调整必须与主诊医生确认。`) rendered in `locale` — present on every section, no exceptions; do not invent a per-section variant
- Override on RED review_flag: must NOT proceed if upstream organize flagged summary.primary / summary.stage / summary.current_regimen / molecular driver (`molecular.json`) as 🔴 unconfirmed (preflight Step 2.5 enforces this; this is the second sanity check)
