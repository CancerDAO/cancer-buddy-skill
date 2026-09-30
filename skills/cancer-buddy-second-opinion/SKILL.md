---
name: cancer-buddy-second-opinion
description: 抗癌搭子·第二意见——为找外院或海外专家看第二意见准备资料包：病例摘要、资料索引、给审阅医生的问题、寄送清单，以及病理切片怎么安全地借出和寄送。触发词：第二意见、再找一家看看、外院会诊、远程会诊、海外会诊、寄切片、借片、病理会诊、准备会诊资料。English: second opinion, external review, send pathology slides, consultation package. Requires the cancer-buddy skill.
---

# 第二意见资料包

帮用户把资料整理成外院医生拿到就能看的一包，并准备好想请对方回答的问题。只转录，不推断。

## 读什么

全部档案（按 [archive.md](../cancer-buddy/references/archive.md)）。先问：送给哪家机构/哪位医生、对方要什么语言、对方有没有资料清单要求。

## 产出

写到 `<patient_dir>/reports/second-opinion/<机构>/`：

- `case-summary.md`：病例摘要——诊断、病理、分子、分期、治疗经过、最近影像和检验、当前状态、急性发现（若有）。每条照抄原文并带出处和日期；看不清或有冲突的如实标出。
- `records-index.md`：随包资料的清单（文书、日期、页数、文件名）。
- `questions-for-reviewer.md`：请对方回答的问题，中立地写。"该换哪个方案"写成"基于这些资料，您认为目前有哪些治疗选择值得讨论，各自的考虑是什么？"
- `cover-letter.md`：简短的来函说明。
- `send-checklist.md`：寄送清单和步骤。

对方要英文或其他语言时，可以另出一份审阅语言版本；药名、基因、数值、TNM 保留原文，译文作为附加。

## 病理切片：先数字、后实物

1. 先问对方能否接受数字切片或已有报告。
2. 需要实物时，先请原医院病理科评估：借出后剩余组织是否还够日后检测。
3. 再按两家医院的要求办理借片和寄送，记录寄出和归还。

## 边界

- 摘要只转录档案，不补写、不总结疗效、不重算分期。
- 对方的资料要求、费用、流程当场联网核验，注明来源和日期。
- 不自动发送任何东西。实际要把文件交出去时，用 vault 做限目的的导出，并由用户本人发送。

## 语气

对家属：说清楚找第二意见是常见、正当的做法，不必担心得罪主诊医生；可以请主诊团队帮忙提供资料。

规则：[guardrails](../cancer-buddy/references/guardrails.md) · [引用](../cancer-buddy/references/citations.md)
