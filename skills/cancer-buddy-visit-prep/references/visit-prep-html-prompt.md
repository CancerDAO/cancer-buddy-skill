# visit-prep — HTML assembly contract

只装配已有资料并生成“问医生的问题”。不解释结果、不作临床判断、不推荐或排序治疗。

## 1. Deterministic rendering

LLM 只写 `<patient_dir>/.visit_prep_data.json`，不得写或修改 HTML。随后运行：

```bash
python3 ../cancer-buddy-organize/scripts/render_html_template.py \
  --template references/templates/visit-prep.template.html \
  --data <patient_dir>/.visit_prep_data.json \
  --out <patient_dir>/就诊准备包.html
python3 scripts/validate_visit_prep_html.py <patient_dir>/就诊准备包.html
```

校验未通过即未完成。修 JSON 或模板后重渲染，不能手改产物。

## 2. Read-only inputs

从已脱敏档案按需读取：

- `patient_summary.json`：诊断、临床来源记录的分期/ECOG/当前状态；
- `molecular.json`：`reports[]`、`variants[]`、`ihc[]`、`msi_results[]`、`mmr_results[]`、`tmb_results[]`；
- `treatment_lines.json`：`episodes[]`；
- `labs.json`：`panels[].values[]`，每个结果自带单位、参考范围和报告标记；
- `timeline.json`：带来源层级的事件；
- `missing_items.json`：`document_gaps[]`，仅表示现有档案中缺少文件；
- `readiness.json`：documentation coverage 与未解决的来源/忠实度 flags（如存在）。

不得读取 `raw/`。缺失字段显示本地化的“资料缺失”，不得猜测。

## 3. Data shape

```json
{
  "i18n": {},
  "fallbacks": {"__default__": "资料缺失"},
  "one_line_condition": null,
  "visit_type_label": "复诊",
  "report_date": "YYYY-MM-DD",
  "is_followup": true,
  "snapshot_diagnosis": null,
  "snapshot_molecular": null,
  "snapshot_current_line": null,
  "snapshot_key_labs": null,
  "confirm_questions": [],
  "supplement_questions": [],
  "next_questions": [],
  "framework_questions": [],
  "bring_originals": [],
  "bring_for_questions": [],
  "change_symptoms": [],
  "change_lab_trends": [],
  "change_new_tests": []
}
```

所有数组项均为 `{"text":"..."}`；只写真实来源支持的条目，不为版面填充内容。

## 4. Direct mapping rules

- `one_line_condition` / `snapshot_diagnosis`：仅拼接 `patient_summary.diagnosis` 中有来源的原文；不重算分期。
- `snapshot_molecular`：逐项复制报告原文；不同报告或 MSI/MMR 冲突并列，不能合并裁决。
- `snapshot_current_line`：使用当前 `episode` 或 `patient_summary.current_status.regimen`。`sequence_index` 只代表时间顺序，不能转成一线/二线；`documented_line_label` 仅在原报告明确写出时使用。
- `snapshot_key_labs`：显示最近报告值、日期、单位、该次报告的参考范围及 `report_flag`/`critical_flag`。不自行判定高低或严重程度。
- ECOG、response、reason for change 只能在来源明确记载时复制，不能从活动能力、影像文本或时间线推断。

保留原始临床字符串；如为患者提供翻译，原文与译文并列并标明译文状态。

## 5. Questions only

将以下内容改写成给主诊医生的问题，不能先替医生回答：

- `confirm_questions`：每个未解决的来源冲突/忠实度 flag 一个问题，包含当前记录和来源；不提供模型建议值，不因患者确认而改写临床事实。
- `supplement_questions`：只问“是否需要把这份**已有文件**补入档案”；`document_gaps` 不能改写成“应补做某检查”。只有当医疗记录明确载有医生请求时，才可询问该请求的后续安排。
- `next_questions`：基于最近事件询问复查安排、症状处置和医生计划；不得把模型推断的“进展/换线”当事实。
- `framework_questions`：使用 [question-frameworks.md](question-frameworks.md) 的框架，个体化内容只来自有来源字段。

出现实验室报告的 critical flag、报告明确要求紧急处理，或用户描述急性危险症状时，先按 `../../../references/safety-guardrails.md` 的紧急路径处理，不等待就诊准备包。

## 6. Changes since last visit

仅复诊显示。按日期列出：

- 新增的来源报告症状；
- 同一 analyte 的两个报告值、各自单位/参考范围/标记；单位或方法不同则并列，不计算变化；
- 新收到的影像、病理、分子或化验报告。

只描述记录变化，不判断“好转/恶化/进展/应换药”。

## 7. Locale, provenance, privacy

遵循 `../../../references/i18n.md`、`../../../references/roles.md` 和 `../../../references/clinical-content-governance.md`。患者版可以翻译，但必须保留原文；所有数据项保留来源、日期、版本和 `source_reported | patient_reported | caregiver_reported | system_normalized` 层级。输出使用最小必要信息，不包含无关身份信息。
