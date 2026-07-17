# Phase 2：来源分层综合

Phase 2 将已复核 sidecar 组织成 schema v2。它不诊断、不重新分期、不判断疗效、不推断 ECOG、不计算治疗线、不决定检查适应证。

## 1. 来源层

每个临床事实必须标：

- `source_reported`: 正式报告/医嘱/临床记录原文；
- `patient_reported` / `caregiver_reported`: 对话或自填；
- `system_normalized`: 验证后的附加标准化字段，永不覆盖原文；
- `verification_status`: `unverified|clinician_verified|disputed`。

## 2. 冲突

不同来源冲突时并列保留，不按“病理优先/最新优先/用户选择”自动裁决。只有正式更正文件或授权临床人员签认才能解决。所有旧值和锚点保持不可变。

## 3. 禁止推断

- 不把 TNM 映射到其他分期系统；
- 不从功能描述生成 ECOG；
- 不从影像/标志物生成 CR/PR/SD/PD、进展或疗效；
- 不把维持、巩固、围手术期自动算成新线；
- 不把患者确认当临床核实；
- 不按通用阈值生成器官限制、严重度或治疗资格。

## 4. 结构化产物

按 `schemas/` v2 写 `patient_summary.json`、`timeline.json`、`treatment_lines.json`（治疗事件）、`labs.json`、`molecular.json`、`comorbidities.json`、`longitudinal_observations.json` 和兼容文件名 `missing_items.json`。

`source_inventory.json` 必须使用 `source_inventory_v2`，逐 content unit 记录受保护的 `raw_path`、sidecar、读取方式、抽取器名称/版本/原始输出引用、LLM 的受限角色和高风险字段独立复读状态。缺少这些字段不得降级成无来源清单。

`missing_items.json` 只输出现有文档档案缺口。checklist 的癌种 slug 不确定时用 unknown，不做 closest-fit。

## 5. 覆盖状态

`readiness.json` 只记录 `documentation_coverage` 和来源/忠实度 flags，不给 A–F 临床 readiness 分数。资料不完整不阻止一般教育；只限制受影响的个体化内容。

## 6. 产物验证

运行 JSON schema、来源锚点、hash、PII、字段分层和冲突不可覆盖检查。验证失败则不生成患者摘要；错误进入 review queue，不让模型自行修正临床值。
