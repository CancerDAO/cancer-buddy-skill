# 病情简要总结 HTML 生成 prompt（段 D）

organize 完成、Profile Card 之后自动触发。读结构化脱敏 JSON → 1:1 填充金标准模板 → 落 `<patient_dir>/病情简要总结.html`。

## locale（i18n）— 先读再填

先读 `profile.json.locale`（organize 已在 Phase2 写入）。整张 HTML 的**脚手架按该 locale 出**，**临床实体一律 verbatim**（药名/基因/变异/TNM/数值单位/VAF 记法照抄，禁止翻译 —— 误译=医疗风险，见 [`../../../references/i18n.md`](../../../references/i18n.md) §4）。

模板顶部有一张 **i18n 字符串表注释块**（section 标题 / 免责声明 / 字段标签 / "待主治医师补充"占位 / 性别值 / 国籍值 / ECOG 推断注 / "待启动" 等）。填充时：

1. 按 `profile.json.locale` 选该 locale 的列，把每个 `{{i18n.<key>}}` 占位符替换成表里对应字符串；`<html lang>` 用 `{{i18n.html_lang}}`。
2. locale 不在表中（如 `fr`/`es`）→ 按 `en` 列语义在目标语言生成等义脚手架字符串（同义同语气），临床术语保持原文，**不要硬编码单语言串**。
3. 字段值里凡映射到固定脚手架的（性别 M→`{{i18n.val_male}}`/F→`{{i18n.val_female}}`、国籍→`{{i18n.val_nationality}}`、缺字段→`{{i18n.val_pending}}`、ECOG inferred 注→`{{i18n.val_ecog_inferred}}`、待启动→`{{i18n.val_to_start}}`）一律走字符串表，不再写死中文。
4. CSS / DOM 结构 1:1 不变，只换 `{{占位符}}` 与 LOOP 块。

## 输入

只读以下脱敏产物，**绝不读原图、绝不读含明文 PII 的旁车**：

- `profile.json`
- `patient_summary.json`
- `molecular.json`
- `labs.json`
- `treatment_lines.json`
- `timeline.json`
- `case_text.md`（仅取影像段，用于病灶分布）
- 模板：`references/templates/case-summary.template.html`

## 数据来源映射表（§3）

| 模板 section | 占位符 | 来源 | 处理方式 |
|---|---|---|---|
| header 一句话病情 | `{{one_line_condition}}` | profile.json（diagnosis/stage + 关键分子 + 当前线状态） | 字段拼接：`<stage> <histology> · <driver> · <当前治疗状态>` |
| header 报告日期 | `{{report_date}}` | 当日日期 | `YYYY-MM-DD` |
| 患者标识 性别 | `{{sex}}` | profile.json / patient_summary demographics.sex | M→`{{i18n.val_male}}` / F→`{{i18n.val_female}}`（走字符串表，不写死） |
| 患者标识 年龄 | `{{age_band}}` | demographics.age | **粗粒度**：归一到十年段，如 50+（绝不落真实年龄外的生日） |
| 患者标识 国籍 | `{{nationality}}` | patient_location_hint | 海外站统一渲染 `{{i18n.val_nationality}}`，不落具体国家/城市 |
| 患者标识 身高体重 BMI | `{{height_weight_bmi}}` | demographics.height_cm/weight_kg | `165 cm / 68 kg / 25.0`，BMI 自算（单位/数值 verbatim） |
| 患者标识 ECOG | `{{ecog}}` | demographics.ecog（+ ecog_inferred） | inferred 时在数值后追加 `{{i18n.val_ecog_inferred}}` |
| 病情概要 | `{{case_summary_narrative}}` | **subagent 生成** ← patient_summary.json + timeline.json | 见下"叙事段" |
| 主要病灶分布 | lesion LOOP | profile.json 影像字段 / case_text.md 影像段 | 字段段直接映射，每解剖部位一行 |
| 核心分子检测 | molecular LOOP | molecular.json | 字段段直接映射，每维度一行 |
| 关键实验室指标 | labs LOOP + `{{lab_class}}` | labs.json | ULN 倍数 → class，见下"实验室配色" |
| 治疗史 timeline | line LOOP | treatment_lines.json / timeline.json | 已用/进行中=红框，待启动=pending 黄框 |
| 当前治疗路径 | path LOOP | treatment_lines.json 当前线 + profile.json | 逐条标签 + 内容 |
| footer | `{{report_date}}` | 当日日期 | 同 header |

## 字段段填充（直接映射，不交 subagent）

除"病情概要"叙事段外，所有 section 都是结构化 JSON → 占位符的直接映射，不做语义改写、不增删临床事实。

### header
- `{{one_line_condition}}`：拼 diagnosis.stage + diagnosis.histology + 主驱动变异（molecular.variants[0]）+ current_status 简述。临床实体 verbatim，连接词按 locale。例（zh）：`IV 期胰腺导管腺癌 · KRAS G12D · 一线 FOLFIRINOX 后 · 二线桥接治疗前`。
- 免责声明走 `{{i18n.disclaimer}}`（按 locale 出，文案语义固定，不增删内容）。

### 患者标识（粗粒度脱敏，硬约束）
- 性别走 `{{i18n.val_male}}`/`{{i18n.val_female}}`；年龄**只输出十年段**（`age // 10 * 10` 后加 `+`，如 53→`50+`）；国籍走 `{{i18n.val_nationality}}`。
- 绝不输出真名、真实出生日期、住院号、城市。BMI = `weight_kg / (height_cm/100)^2`，保留一位小数（数值/单位 verbatim）。

### 主要病灶分布
- 遍历 profile.json 影像字段（原发灶 / 各转移部位 / 淋巴结）；若影像结构化字段缺，交 subagent 从 `case_text.md` 影像段抽取病灶清单（仅抽取，不增补医学判断）。
- 每个解剖部位渲染一行 `<tr><td>部位</td><td>描述</td></tr>`。

### 核心分子检测
- 驱动突变行：molecular.variants（gene + variant + vaf + tissue）。
- 免疫表型行：msi_mmr + PD-L1（ihc）+ TMB。
- DDR 与其他行：剩余 variants（BRCA / CHEK2 / VUS 等）。
- 组织病理行：ihc / 病理描述字段。
- 字段照抄，VAF/突变记法不改字符。

### 关键实验室指标（配色规则）
对 labs.json 每个 analyte 取最近一次值，按相对参考上限（ULN）倍数判 class：

- 正常范围内 → `{{lab_class}}` 留空（无 class）。
- 异常但 < 3× ULN → `abnormal`（浅红）。
- 严重（≥ 3× ULN，或临床显著严重缺乏/危急值）→ `severe`（深红）。
- 倍数从 labs.json 的 `value` 与 `reference_range` 计算；reference_range 缺失时用 `flag`（H/L→abnormal，HH/LL→severe）。
- `{{lab_value}}` 写实测值 + 单位 +（倍数/状态注），如 `1,240 U/mL（约 33× ULN）`。

### 治疗史 timeline
- 遍历 treatment_lines.lines（按 line 升序）。
- 已结束或进行中的线：`{{line_marker_class}}` 留空（红框），`{{line_badge_class}}`=`pd`。
- `ended_at` 为 null 且未启动（待启动）：`{{line_marker_class}}`=`pending`（黄框），`{{line_badge_class}}`=`pending`，`{{line_date_range}}`=`{{i18n.val_to_start}}`。
- `{{line_label}}`：一线/二线/三线 等序词按 locale 出（line 整数→该 locale 的序数表述）。
- `{{line_regimen}}`=regimen 照抄（临床实体 verbatim）；`{{line_note}}`=best_response + reason_for_change + 影像转归（取自 timeline 对应区间，照抄不增补；连接词按 locale）。
- 口述/未经机构确认的信息要在 note 按 locale 注明等义于"待治疗机构出具/待主治医师确认"。

### 当前治疗路径
- treatment_lines 中当前线 + profile 计划字段，逐条渲染。每条：`<span class="label">标签：</span>内容`，条间 `<br>`，末条不加 `<br>`。
- 标签如"当前较可能的路径：""桥接：""备选试验路径："。仅复述病历/计划已载明内容，不新增推荐方案。

## 叙事段（病情概要）— 交 subagent / LLM 生成

`{{case_summary_narrative}}` 是唯一需要语义生成的段落。交 subagent 处理，prompt 要点：

- 输入：patient_summary.json + timeline.json（脱敏后）。
- **输出语言按 `profile.json.locale`**（叙事是脚手架 → output in `<locale>`；临床实体 verbatim per i18n.md §4）。
- 输出 3–5 句客观叙事，结构：诊断名 + 确诊时间 → 已用治疗线及转归（影像/标志物变化）→ 当前处境与下一步计划（如待启动某线 / 申请某药）。
- 硬约束：只复述 JSON 已有事实，**禁止新增任何医学判断、预后、治疗建议**；禁止出现真名/生日/医院全称（机构粗粒度化，按 locale 出，如"某北美学术癌症中心""a North American academic cancer center"）；JSON 缺关键字段时该句省略，不编造；药名/基因/变异/TNM/数值单位一律原文不译。
- 不写硬编码模板句拼接 keyword list，交 subagent 按上述要点自然生成。

## 缺字段处理

- JSON 字段为 `null` 或对应 JSON 文件缺失 → 该占位符/该整段渲染 `{{i18n.val_pending}}`（按 locale 出，zh 即"待主治医师补充 / 资料缺失"），**不捏造、不推断填充**。
- 整个 section 无数据（如无 molecular.json）→ section 标题保留，表体渲染单行 `{{i18n.val_pending}}`。

## 输出

- 把填充后的 HTML 落到 `<patient_dir>/病情简要总结.html`（文件名固定中文，下游按固定名取；不随 locale 改名）。
- 模板 HTML/CSS/排版**逐像素保持与 `references/templates/case-summary.template.html` 一致**，只替换 `{{占位符}}`（含 `{{i18n.*}}` 脚手架串）与 LOOP 块，不改 class/样式/结构。
- 脱敏不改临床字符：遮的只能是 PII，VAF/剂量/数值/突变记法原样保留；临床实体禁译（i18n.md §4）。
