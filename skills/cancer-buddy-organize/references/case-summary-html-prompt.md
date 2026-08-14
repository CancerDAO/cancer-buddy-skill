# 病情资料摘要 HTML 数据生成合同（段 D）

本步骤只组织来源，不作临床判断。先生成唯一规范中间件 `.case_summary_data.json`，再由
`scripts/render_html_template.py` 确定性渲染，并运行现有 schema、来源锚点、PII 和 HTML
验证。验证失败则不交付。

## 只读输入

读取脱敏后的 `profile.json`、结构化 JSON、`case_text.md` 和模板。不得读取未授权明文 PII，
不得从原图重新解释临床内容。任何存在忠实度、OCR、身份或来源冲突的值在患者摘要中置
`null` 并列入 caveats；原始分层数据保留以供复核。

## 临床真值红线

- `stage`、诊断、方案、分子结果、实验室值只复制来源，并显示来源层级和验证状态。
- `response`、CR/PR/SD/PD 和 ECOG 只在医生来源明确写出时复制；不得从影像、症状或功能描述推断。
- 不生成“当前治疗路径”、治疗建议、器官限制、严重度或下一步检查。
- 不使用通用 `3×参考上限` 或任何跨检验项目阈值分级。只显示原报告 flag/危急值标记及其来源。
- 肿瘤标志物、实验室、症状、可穿戴和病灶描述趋势均为观察事实，不是疗效。
- 冲突不裁决胜者。并列显示来源并标 `disputed`，直到更正报告或授权临床人员签认。
- 患者确认只能创建 `patient_reported` 层，不能修正或覆盖来源层。

## 趋势

按 `cancer-trend-markers.md` 选择。每个点逐字来自结构化数据，保留 raw value、单位、日期、
方法和来源。`interpretation` 只能是中性的数值/日期描述；不解释原因或临床意义。
SVG 坐标仍由确定性脚本生成，模型不得造点或手算坐标。

## 数据映射

- 患者标识：只显示最小必要字段；`patient_code` 不是身份认证。
- 年龄/体重/身高：**必须连同其 `_as_of` 日期一起显示**（"52 岁（2024-03-11 报告）"），裸数字等于把旧快照当现况。`birth_year` 非空时可在旁边补一个明确标注"约"的现龄，不替换带日期的快照。跨年份的取值差异是时间演变，**不置 null、不进 caveats、不标 `disputed`**（见 `organizer-prompt-phase2-synthesis.md` §2.1）；只有同日期矛盾或与时间跨度冲突才按 §上文冲突规则处理。
- 诊断/分期：原文 + verification_status；缺失为 null，并在下述 `provenance[]` 记录来源。
- ECOG：clinician-reported only；否则显示患者功能描述，不转成分数。
- 病灶：逐份报告的描述与日期；不合成 progression/response。
- 分子：精确变异、方法、样本、日期、质量/限制；不连接药物。
- 治疗史：按事件和来源列出；不自动计算“线”，维持/巩固/围手术期保留原标签。
- 实验室：每个结果自己的单位、参考范围和报告 flag，并在 `provenance[]` 记录来源。
- caveats：缺失、来源冲突、OCR、单位/方法不兼容、患者自述与正式报告差异。

`.case_summary_data.json` 的 render 字段保持模板所需纯值；来源统一放在必需的
`provenance[]` side table，例如：
`{"field":"stage","provenance_layer":"source_reported","verification_status":"unverified","source_refs":["04_.../x.md#L12"]}`。
每个实际填入的 `one_line_condition/stage/sex/age/height_weight_bmi/ecog/`
`case_summary_narrative/labs_period`，以及每个病灶、分子、趋势、实验室和治疗数组条目，
都要有同名 field（数组使用 `lesions[0]` 等索引）的对应记录。JSON 引用遵守
统一 source-ref 合同，最终 validator 会机械检查路径、fragment 与目标存在；模板忽略该
side table，不会把内部路径显示给患者。

## i18n 与术语

按根目录 `i18n.md` 保留来源原文，同时允许验证后的标准化字段和患者语言解释。不能根据
研发代号猜通用名；只有权威来源完成映射时才添加 normalized name。

## 页脚

显示生成时间、工具版本、输入 hash、来源清单和：

> 本页是资料索引，不替代主诊医生的判断，不包含疗效、分期重判或治疗建议。冲突与缺失项需由原报告机构或主诊团队核对。
