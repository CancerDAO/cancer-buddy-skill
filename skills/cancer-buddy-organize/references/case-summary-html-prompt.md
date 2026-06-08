# 病情简要总结 HTML 生成 prompt（段 D）

organize 完成、Profile Card 之后自动触发。读结构化脱敏 JSON → **只产出一份 `case_summary_data.json` 数据对象** → 跑确定性模板引擎 `scripts/render_html_template.py` 填模板 → 跑 `scripts/validate_case_summary_html.py` 过"形"不变量 → 不过则不出文件 → 落 `<patient_dir>/病情简要总结.html`。

## 红线（违反即非法输出，哪怕临床内容全对）

- 你**只产 `case_summary_data.json`**：各字段值 + 病情概要叙事串 + lesion/molecular/labs/治疗线/path 数组 + i18n locale 串表 + 各空段 fallback 文案。
- 你**绝不手写、拼接、改写任何 HTML / CSS / DOM**。HTML 由 `render_html_template.py` 从 `case-summary.template.html` 确定性生成，你不碰模板、不碰标签、不碰 class、不碰样式。
- **任何自定义 HTML / CSS / DOM 结构都是非法输出**——哪怕临床内容完全正确。模板是唯一真相源；防过拟合靠"引擎零医学逻辑 + 数据驱动 0..N"。
- 渲染完后，引擎会自检"去 HTML 注释后无残留 `{{...}}`"。残留即报错（exit 1），说明 `case_summary_data.json` 漏了 key——补数据，不要去改模板。
- 渲染完还要过 `scripts/validate_case_summary_html.py`（形不变量：style 块逐字节一致、无越界 class、无 PII、骨架齐、provenance 对得上）。**renderer 或 validator 任一 exit≠0，就不交付这份 HTML**（fail-closed，见"输出"§4）。validator 只查形、与具体病人无关，**绝不断言某化验/某 section 内容存在**。

## locale（i18n）— 先读再填

先读 `profile.json.locale`（organize 已在 Phase2 写入）。整张 HTML 的**脚手架按该 locale 出**，**临床实体一律 verbatim**（药名/基因/变异/TNM/数值单位/VAF 记法照抄，禁止翻译 —— 误译=医疗风险，见 [`../../../references/i18n.md`](../../../references/i18n.md) §4）。

模板顶部有一张 **i18n 字符串表注释块**（section 标题 / 免责声明 / 字段标签 / "待主治医师补充"占位 / 性别值 / 国籍值 / ECOG 推断注 / "待启动" 等）。你把这些串填进 `case_summary_data.json` 的 `i18n` 对象（key→该 locale 的串），引擎再替换模板里的 `{{i18n.<key>}}`：

1. 按 `profile.json.locale` 选该 locale 的列，把每个 `i18n.<key>` 填成表里对应字符串；`html_lang` 填该 locale 的 `<html lang>` 值。
2. locale 不在表中（如 `fr`/`es`）→ 按 `en` 列语义在目标语言生成等义脚手架字符串（同义同语气），临床术语保持原文，**不要硬编码单语言串**。
3. 字段值里凡映射到固定脚手架的（性别 M→`i18n.val_male`/F→`i18n.val_female`、国籍→`i18n.val_nationality`、缺字段→`i18n.val_pending`、ECOG inferred 注→`i18n.val_ecog_inferred`、待启动→`i18n.val_to_start`）一律取自该 i18n 串，不在数据里写死中文。
4. 你不动 CSS / DOM；引擎按模板 1:1 渲染，只替换 `{{占位符}}` / 展开 `<!-- LOOP -->` / 判定 `<!-- RENDER_IF -->`。

## 输入

只读以下脱敏产物，**绝不读原图、绝不读含明文 PII 的旁车**：

- `profile.json`
- `patient_summary.json`
- `molecular.json`
- `labs.json`
- `treatment_lines.json`
- `timeline.json`
- `case_text.md`（仅取影像段，用于病灶分布）
- 模板（**只读，不改**）：`references/templates/case-summary.template.html`
- 数据契约（你的产物结构）：`references/schemas/case_summary_data.schema.json`

## 数据来源映射表（§3）

下表第 2 列是 `case_summary_data.json` 里的 **JSON key**（标量字段 / 数组），不是你要手写的 HTML。引擎拿这些 key 去填同名 `{{占位符}}` / 展开 `<!-- LOOP key -->`。

| 模板 section | JSON key | 来源 | 处理方式 |
|---|---|---|---|
| header 一句话病情 | `one_line_condition` | profile.json（diagnosis/stage + 关键分子 + 当前线状态） | 字段拼接：`<stage> <histology> · <driver> · <当前治疗状态>` |
| header 报告日期 | `report_date` | 当日日期 | `YYYY-MM-DD` |
| 患者标识 性别 | `sex` | profile.json / patient_summary demographics.sex | M→`i18n.val_male` / F→`i18n.val_female` 串值（走字符串表，不写死） |
| 患者标识 年龄 | `age_band` | demographics.age | **粗粒度**：归一到十年段，如 60+（绝不落真实年龄/生日） |
| 患者标识 国籍 | `nationality` | patient_location_hint | 海外站统一填 `i18n.val_nationality` 串值，不落具体国家/城市 |
| 患者标识 身高体重 BMI | `height_weight_bmi` | demographics.height_cm/weight_kg | `165 cm / 68 kg / 25.0`，BMI 自算（单位/数值 verbatim） |
| 患者标识 ECOG | `ecog` | demographics.ecog（+ ecog_inferred） | inferred 时在数值后追加 `i18n.val_ecog_inferred` 串值 |
| 病情概要 | `case_summary_narrative` | **subagent 生成** ← patient_summary.json + timeline.json | 见下"叙事段" |
| 主要病灶分布 | `lesions[]`（`lesion_site` / `lesion_detail`） | profile.json 影像字段 / case_text.md 影像段 | 每解剖部位一个数组元素；0 个就给 `[]`，引擎自动占位 |
| 核心分子检测 | `molecular_rows[]`（`molecular_label` / `molecular_value`） | molecular.json | 每维度一个元素；0 个给 `[]` |
| 关键实验室指标 | `labs[]`（`lab_name` / `lab_value` / `lab_class`）+ `labs_period` | labs.json | ULN 倍数 → `lab_class`，见下"实验室配色"；0 个给 `[]` |
| 治疗史 timeline | `treatment_lines[]`（见 §"治疗史"字段） | treatment_lines.json / timeline.json | 已用/进行中=红框，待启动=pending 黄框；0 个给 `[]` |
| 当前治疗路径 | `path_items[]`（`path_label` / `path_content`） | treatment_lines.json 当前线 + profile.json | 逐条标签 + 内容；0 个给 `[]` |
| footer | `report_date` | 当日日期 | 同 header |

**数量全来自 data**：有几个 lesion/molecular/lab/治疗线/path 就给几个元素（0..N），引擎按数组长度渲。空数组（`[]`）→引擎走该段的 `RENDER_IF_NOT` 占位（"资料缺失"），section 永不删。

## 字段段填充（直接映射，不交 subagent）

除"病情概要"叙事段外，所有 section 都是结构化 JSON → 占位符的直接映射，不做语义改写、不增删临床事实。

### header
- `{{one_line_condition}}`：拼 diagnosis.stage + diagnosis.histology + 主驱动变异（molecular.variants[0]）+ current_status 简述。临床实体 verbatim，连接词按 locale。例（zh）：`IV 期胰腺导管腺癌 · KRAS G12D · 一线 FOLFIRINOX 后 · 二线桥接治疗前`。
- 免责声明走 `{{i18n.disclaimer}}`（按 locale 出，文案语义固定，不增删内容）。

### 患者标识（粗粒度脱敏，硬约束）
- 性别填 `i18n.val_male`/`i18n.val_female` 串值；年龄**只输出十年段**（`age // 10 * 10` 后加 `+`，如 63→`60+`，53→`50+`）——精确年龄一律降到粗粒度 band，绝不落真实年龄/生日；国籍填 `i18n.val_nationality` 串值。
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

## 缺字段处理（fallback 文案进 data，不进模板）

引擎对**标量占位符**有 fallback 机制：某 `{{key}}` 对应的 data 值为 `null`/`""`/缺失时，引擎按顺序取 `fallbacks[key]` → `fallbacks.__default__` → `""`。所以你把"资料缺失"类文案放进 `case_summary_data.json` 的 `fallbacks` 对象（key = 占位符名，value = 该 locale 的占位文案，如 zh `"资料缺失"`），并务必给 `fallbacks.__default__`（兜底，如该 locale 的 `i18n.val_pending`）。**不捏造、不推断填充**真实临床值。

- 标量缺字段（如 `ecog`/`labs_period`/`one_line_condition` 为 null）→ 引擎自动落该 key 的 fallback 或 `__default__`，section 结构照常渲染。
- 整段数组无数据（如无 molecular.json）→ 给 `[]`，引擎走该段 `RENDER_IF_NOT` 占位行（"资料缺失"），section 标题与骨架保留、不删。
- 所有空段都靠模板里的 `RENDER_IF_NOT` 占位或标量 fallback 兜住，**永远不留空表 / 不删 section**——validator 查"形"的骨架对任何病人都成立。

## 输出（先 JSON，后跑引擎，再过 validator；不过则不出文件）

`<patient_dir>` 是上游（SKILL.md / INSTALL.md）按**单一解析规则** `$CANCER_BUDDY_PATIENTS_DIR → $VMTB_PATIENT_DATA_ROOT → $HOME/CancerDAO/patients` 解析出来、再作为 call parameter 传给你的绝对路径。你**直接用这个 `patient_dir`**，自己**绝不重新发明输出根**、不另解析环境变量。

1. 把 `case_summary_data.json` 写到 `<patient_dir>/case_summary_data.json`，结构遵 `references/schemas/case_summary_data.schema.json`（i18n 串表 + fallbacks + 各标量 + lesions/molecular_rows/labs/treatment_lines/path_items 数组）。

2. 跑确定性模板引擎填模板、落 HTML：

   ```
   python3 scripts/render_html_template.py \
     --template references/templates/case-summary.template.html \
     --data <patient_dir>/case_summary_data.json \
     --out <patient_dir>/病情简要总结.html
   ```

   HTML 文件名固定中文，下游按固定名取，不随 locale 改名。引擎 exit 0 = 无残留 `{{...}}`；exit 1 = data 漏 key（补 `case_summary_data.json`，**不要去改模板**）。

3. 跑"形"不变量校验器（模板固定、与病人无关的骨架检查 —— style 块逐字节一致、无越界 CSS class、无残留 `{{...}}`、无 PII / 无精确年龄、骨架 section 齐、provenance template_sha256 与本次模板一致）：

   ```
   python3 scripts/validate_case_summary_html.py \
     --html <patient_dir>/病情简要总结.html \
     --template references/templates/case-summary.template.html
   ```

   validator **只查形、不查具体临床内容**（绝不断言"必须有某化验 / 某 `.lab-grid`" —— 无化验的病人合法地没有这些）。exit 0 = 形不变量成立；exit 1 = 形被破坏（手写过 HTML / 漏渲染 / 泄 PII / 越界 class）。

4. **fail-closed：renderer 或 validator 任一非 0，就不交付 `病情简要总结.html`** —— 删掉/不落这份 HTML，回报失败原因（哪个 exit、哪条 error），不要把一份形不合规或带残留/PII 的 HTML 留在 `patient_dir`。修 `case_summary_data.json` 后重跑 2→3，直到两步都 exit 0 才算产出成功。

- 你不写、不改 HTML/CSS/排版；模板逐像素由引擎保持，class/样式/结构由模板单方决定。**禁止手写 HTML**——唯一合法产出路径是「写 data JSON → 引擎渲染 → validator 放行」。
- 脱敏不改临床字符：遮的只能是 PII，VAF/剂量/数值/突变记法原样保留；临床实体禁译（i18n.md §4）。
