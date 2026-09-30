---
name: cancer-buddy-visit-prep
description: 抗癌搭子·就诊准备——根据患者档案生成一页就诊准备包：医生 30 秒速览、要问的问题、要带的东西、上次以来的变化。触发词：看病前准备、就诊准备、复诊、要问医生什么、问题清单、带什么去医院、准备包、MDT 前准备。English: visit prep, prepare for appointment, questions for my doctor, what to bring, follow-up visit. Requires the cancer-buddy skill.
---

# 就诊准备包

帮患者和家属带着一页纸去看病：医生 30 秒能看懂的病情速览，按类分好的问题，要带的东西，复诊时"上次以来的变化"。只组装和整理，不解读、不建议。

## 先问一句

这次是哪种就诊：`first`（初诊/换医院）、`followup`（复诊）、`decision_discussion`（要讨论治疗决定）。用户说不清就按档案推断并在包里写明。

## 读什么

按 [archive.md](../cancer-buddy/references/archive.md) 找到档案，读 `profile`、`patient_summary`、`acute_findings`、`molecular`、`treatment_lines`、`labs`、`timeline`、`missing_items`、`readiness`。复诊时对比 `case_summary_versions/` 里最近的快照。

## 产出

1. 写 `<patient_dir>/.work/visit_prep.json`：

```json
{
  "visit_type": "followup",
  "snapshot": ["一句一条的病情速览，照抄原文，带日期"],
  "questions": [
    {"group": "请医生确认", "items": [{"text": "…", "why": "…", "source_ref": "…md#L3-L5"}]},
    {"group": "是否补入已有资料", "items": []},
    {"group": "接下来的安排", "items": []},
    {"group": "想了解的一般问题", "items": []}
  ],
  "bring_list": ["…"],
  "changes_since_last": ["…（仅复诊）"]
}
```

   字段以 `skills/cancer-buddy/scripts/cblib/render.py` 的文档说明为准；本文写作时该文件尚未完成，以上形状来自 SPEC §7。

2. 运行 `python3 "<cancer-buddy 目录>/scripts/cb.py" render visit-prep <patient_dir> <patient_dir>/.work/visit_prep.json`，得到 `就诊准备包.html`。不要手写 HTML。
3. 给用户：文件路径 + 三五句要点（最先说急性发现，若有）。

## 怎么写问题

- **请医生确认**：只放真的看不清（`review_flags` 里 `kind: legibility`）或真的有冲突（`kind: conflict` / `disputed`）的字段，写明各个读法和出处。表格没对齐的 `candidate_value`、读数的小差异不放进来。没有就留空，不凑数。
- **是否补入已有资料**：来自 `missing_items`，写成"如果手里有 X 报告/第 2 页，可以带上或补进档案"，不写"需要做某检查"。
- **接下来的安排**：一般性的问法，如"下次复查大概什么时候、查什么？"
- **想了解的一般问题**：把用户自己的担心改写成中立的问题。"该换哪个方案"写成"目前还有哪些治疗选择，各自要考虑什么？"
- 每个问题附一句 `why`（为什么值得问），有出处就带 `source_ref`。

## 边界

- 分期、线次、疗效照抄原文，不重算、不判断。
- 单位不同的化验值并列列出，不算差值。
- 患者要看自己的诊断和分期，就照原文给。
- 急性发现放在速览最前面。

## 语气

对照护者：问题清单写成"可以替 Ta 问"，bring_list 里加上照护者自己需要记的事（下次时间、联系电话）。

规则：[guardrails](../cancer-buddy/references/guardrails.md) · [引用](../cancer-buddy/references/citations.md)
