---
name: cancer-buddy-case-precedent
description: "检索 PubMed、Europe PMC 等来源中的病例报告，完整呈现病例差异、治疗经过和全部结局，作为不可推广的研究线索。无相似度分数或排序，不生成治疗方向、适用性、获益概率或患者预后。Triggers on 相似病例, 病例报告, case report, 真实病例, 文献先例."
---

# cancer-buddy-case-precedent

用病例报告回答“文献中记录过什么”，不能回答“患者应该做什么”。

## Clinical boundary

- 个案报告是高度选择性、不可推广的证据；不能证明有效性、安全性、因果关系或患者适用性。
- 不计算或展示综合相似度，不按“最像”排序，不把相同基因或癌种当作可比性的充分条件。
- 不汇总有效率、生存率、获益概率或患者预后。
- 不输出“治疗方向”“值得尝试”“可复制路径”或获取某药/操作的行动建议。
- 死亡、严重不良事件、无效、进展和失访必须与阳性结局同等显著；患者版也不得隐藏。

## Inputs

只读取检索问题所需的最少病历字段，并保存其来源层级。临床确认字段与患者自述分开；缺失或冲突记为 `unknown` / `disputed`，不由模型裁决。无需具备完整档案即可进行一般疾病检索。

## Workflow

1. 把用户问题改写为中性的研究问题，例如“该组织学和变异组合有哪些已发表病例报告？”
2. 按 [retrieval-sources.md](references/retrieval-sources.md) 实时检索。限定文献类型，去重，检查撤稿/更正，并记录检索日期、数据库和完整检索式。
3. 按 [case-extraction-schema.md](references/case-extraction-schema.md) 逐病例抽取。一个论文有多个患者时逐个分开；摘要没有的信息标 `not_reported`。
4. 按 [similarity-axes.md](references/similarity-axes.md) 展示 `same | different | unknown | not_comparable`。这是差异表，不是匹配或推荐工具。
5. 按 [output-template.md](references/output-template.md) 输出，病例按发表年份或 PMID 等中性顺序排列。

## Required output

每个病例必须同时展示：

- PMID/DOI/题名/年份与是否有全文；
- 原文报告的人口学、诊断、病理、分子、治疗意图和治疗经过；
- 疗效评估方法、时间点、毒性、进展、死亡、失访及随访长度；
- 与当前检索条件的相同、不同、未知和不可比较项；
- 抽取局限、撤稿/更正状态和来源定位。

开头和结尾都需说明：病例报告存在发表偏倚，不能用于预测本人结局或选择治疗。完整偏倚说明见 [bias-disclosure.md](references/bias-disclosure.md)。

## Locale and safety

保留文献原文和经验证的翻译/规范化字段。药名、基因、变异、剂量、单位等不得被无痕改写；译文与原文并列。用户若询问个体治疗，转为帮助其整理要问主诊团队的问题，不从病例生成方案。

本 skill 不另设自伤/自杀处置路径；宿主平台继续执行其通用安全能力。其他急症按 `../../references/safety-guardrails.md` 处理。

## Role behavior

- **Role = patient**：可用自己的授权资料定义检索问题。
- **Role = caregiver**：仅在有效授权范围内使用患者资料；否则做一般疾病检索。
- **Role = family**：无授权时只能做一般检索，不能加载患者档案。

## Disclosure

明确要求自己信息的患者可获得来源型结果。对其他 viewer，只使用其获授权内容；病例报告不能被用来绕过披露权限或暗示患者预后。


## Charting an indicator the user asked about

When the user asks about a **specific named lab value or observation** (CEA, 白蛋白, 体重…),
check `longitudinal_observations.json` / `labs.json` for that analyte BEFORE answering in prose:

- **≥2 comparable points** → answer in text **and attach a chart**:
  `python3 ../cancer-buddy-charts/scripts/render_chart.py --chart trend --from-longitudinal <patient_dir>/longitudinal_observations.json --metric <analyte> --out-html <patient_dir>/charts/<analyte>_趋势.html`
- **fewer than 2, or not comparable** → answer in text and say in one line why there is no chart

Volunteering a chart covers only the analyte the user named. A general question
("我的化验单怎么样") does not auto-chart — list which indicators form a series and let them pick.
When the user explicitly asks for several ("都画出来"), chart them all; there is no cap.

**Answer the question, do not wall it off.** What the indicator is, what it generally reflects,
why reference ranges differ between hospitals, what guidelines generally say about follow-up
intervals — all answerable (verify a current primary source at answer time and cite it; route to
`cancer-buddy-education`). Only a verdict on **this person's numbers** — response, progression,
whether to change regimen or add imaging, prognosis — routes to the treating team, in a sentence
or two woven into the answer rather than a standing disclaimer block.

Keep implementation detail out of the reply: no script names, exit codes, rule numbers, or your
own verification steps.

## References

- [retrieval-sources.md](references/retrieval-sources.md)
- [case-extraction-schema.md](references/case-extraction-schema.md)
- [similarity-axes.md](references/similarity-axes.md)
- [bias-disclosure.md](references/bias-disclosure.md)
- [output-template.md](references/output-template.md)
- [clinical-content-governance.md](../../references/clinical-content-governance.md)
- [i18n.md](../../references/i18n.md)
- [safety-guardrails.md](../../references/safety-guardrails.md)
- [disclosure-behavior.md](../../references/disclosure-behavior.md)
- [../../references/citation-format.md](../../references/citation-format.md)
- [../../references/evidence-trust-tiers.md](../../references/evidence-trust-tiers.md)
- [../../references/reference-library.md](../../references/reference-library.md)
