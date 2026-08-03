---
name: cancer-buddy-second-opinion
description: "从患者已整理资料生成来源可追溯的二次意见资料包、记录索引和问题清单。仅转录与组织，不推断诊断、分期、ECOG、疗效、进展或治疗选择；跨境联系和材料要求必须实时核验。Triggers on 第二意见, second opinion, 海外会诊, 病例摘要, 会诊资料包."
---

# cancer-buddy-second-opinion

生成给另一医疗团队复核的资料包，不替任何一方作临床判断。

## Preconditions

- 仅患者本人或经验证、限用途授权的照护者可以制作和发送资料包。
- 开始前确认目标机构、临床问题、所需语言、拟分享资料范围和患者同意。
- 不以 A–F “readiness” 分数阻断。若关键字段缺失或冲突，在相应字段标 `not_available` / `disputed`，并列为给审阅医生的问题。
- 未解决的来源忠实度问题只阻止受影响字段被当作事实；其余资料仍可打包。

## Source fidelity

- `diagnosis`、`stage`、`ECOG`、影像反应、病理和分子结论只能标注为报告医生/机构所述，并附日期与来源。
- 不从症状推 ECOG，不从影像描述推 RECIST/进展，不从治疗时间推治疗线，不生成“最佳疗效”。
- 患者自述与医疗记录分层保存；冲突并列，不由模型选择“正确版本”。
- 保留原文；需要翻译时并列原文与译文，并记录译者/工具、日期和复核状态。剂量、单位、基因、变异和注册号必须逐项核对。

## Workflow

1. 读取最少必要的脱敏来源和 provenance；不读取任务无关资料。
2. 按 [case-summary-template.md](references/case-summary-template.md) 生成 1–2 页来源型摘要。
3. 生成 records index：文件日期、机构、类型、原始文件名、来源定位、翻译状态。
4. 按 [cover-letter-template.md](references/cover-letter-template.md) 生成问题导向的转诊信，不暗示接收方必须同意或执行任何方案。
5. 若涉及跨境，按 [cross-border-shipping.md](references/cross-border-shipping.md) 先联系目标机构确认接收方式。病理玻片/蜡块、影像介质、海关、费用、隐私和退回方式均以机构与承运方当前书面要求为准。
6. 输出发送前核对表，由患者/授权代表确认收件方、资料范围和联系方式后再发送。skill 不自动外发。

## Live verification

目标机构名单只作发现线索，见 [top-centers.md](references/top-centers.md)。每次都从目标机构官方网站实时核验：项目是否开放、适用地区、所需材料、语言、费用、门户/电话/地址和病理材料政策。无法核验时标 `unconfirmed` 并停止给出可执行地址；不得从静态文档或模型记忆补写。

## Outputs

写入 `patients/<patient_code>/reports/second-opinion/<target>/`：

- `case-summary.md`
- `records-index.md`
- `cover-letter.md`
- `questions-for-reviewer.md`
- `shipping-instructions.md`（如适用）
- `send-checklist.md`

所有条目带生成日期、来源、版本和未核实项。资料包声明其为记录摘要，不是诊断或治疗建议。

## Safety

不承诺第二意见会提供新方案，不评价机构优劣，不以病例摘要替代原始报告。出现急性危险症状时先按 `../../references/safety-guardrails.md` 路由就医。数据处理遵循 `../cancer-buddy-vault/references/data-vault.md` 和 `../../references/roles.md`。

## Role behavior

- **Role = patient**：在认证和明确同意后生成自己的资料包，并在发送前逐项确认。
- **Role = caregiver**：仅在有效、限用途授权范围内操作；不能自行扩大分享范围。
- **Role = family**：无授权时只提供二次意见流程说明，不读取或打包患者资料。

## Disclosure

资料包的 viewer 和接收方必须获授权。能作决定的患者明确要求自己的资料时，家属 suppression 偏好不能阻止；能力/代理争议时暂停外发并转机构流程。


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

- [case-summary-template.md](references/case-summary-template.md)
- [cover-letter-template.md](references/cover-letter-template.md)
- [cross-border-shipping.md](references/cross-border-shipping.md)
- [top-centers.md](references/top-centers.md)
- [clinical-content-governance.md](../../references/clinical-content-governance.md)
- [i18n.md](../../references/i18n.md)
- [disclosure-behavior.md](../../references/disclosure-behavior.md)
- [../../references/citation-format.md](../../references/citation-format.md)
- [../../references/evidence-trust-tiers.md](../../references/evidence-trust-tiers.md)
- [../../references/reference-library.md](../../references/reference-library.md)
