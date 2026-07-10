# 病情简要总结 HTML 生成 prompt（段 D）

Phase2 结构化整理完成、Profile Card 之后自动触发。读结构化文本脱敏 JSON → **只产出一份 `case_summary_data.json` 数据对象** → 跑确定性模板引擎 `scripts/render_html_template.py` 填模板 → 跑 `scripts/validate_case_summary_html.py` 过"形"不变量 → 不过则不出文件 → 落 `<patient_dir>/病情简要总结.html`。上传原件逐字保存在 `raw/`,永不像素打码;对**归档数据**的唯一**内容级**脱敏是 sidecar 文本遮蔽(raw/ 文件名另由 Phase1 去标识),而本 段D 患者向 HTML 另在**输出侧**把患者标识粗粒度化(**保留精确年龄**供临床试验匹配,但不出真名/生日 DOB/出生地/职业)——见下文 §患者标识。

## 红线（违反即非法输出，哪怕临床内容全对）

- 你**只产 `case_summary_data.json`**：各字段值 + 病情概要叙事串 + lesion/molecular/治疗线/path 数组 + **`trend_charts[]`（关键趋势 hero，总数 2–4 张或 `[]`，选取见下方分层规则）** + **`lab_trends[]`（实验室指标趋势行，取代旧 `labs[]` 平铺网格）** + **`caveats[]` 数据说明数组**（见下"Call parameters"）+ i18n locale 串表（含 `sec_stage` / `sec_caveats` / `sec_trend` / `delta_title` / `delta_vs` / `delta_none` / `trend_none`）+ 各空段 fallback 文案。
- **趋势的坐标不是你算的**：`trend_charts[]` 每张图 / `lab_trends[]` 每行里你只填**逐字取自 `longitudinal_observations.json` / `labs.json` 的 `series[]`（`{t,v}`）** + 选定指标 + 一句 `interpretation`；SVG 坐标（`svg_points` / `svg_area_d` / `dots[]` / `marker_x` / `direction`）由 `scripts/compute_sparklines.py` 逐图确定性注入，**你绝不手算像素、绝不编造任何 series 数值**（造点会被 compute_sparklines 的反造假门 exit 3 拦下）。
- **`version_delta`（自上次总结的变化）不是你产的**：由 `scripts/compute_version_delta.py` 对比上一版快照生成，你**不要**在 `case_summary_data.json` 里写它。
- 你**绝不手写、拼接、改写任何 HTML / CSS / DOM**。HTML 由 `render_html_template.py` 从 `case-summary.template.html` 确定性生成，你不碰模板、不碰标签、不碰 class、不碰样式。
- **任何自定义 HTML / CSS / DOM 结构都是非法输出**——哪怕临床内容完全正确。模板是唯一真相源；防过拟合靠"引擎零医学逻辑 + 数据驱动 0..N"。
- 渲染完后，引擎会自检"去 HTML 注释后无残留 `{{...}}`"。残留即报错（exit 1），说明 `case_summary_data.json` 漏了 key——补数据，不要去改模板。
- 渲染完还要过 `scripts/validate_case_summary_html.py`（形不变量：style 块逐字节一致、无越界 class、无 PII、骨架齐、provenance 对得上）。**renderer 或 validator 任一 exit≠0，就不交付这份 HTML**（fail-closed，见"输出"§4）。validator 只查形、与具体病人无关，**绝不断言某化验/某 section 内容存在**。

## Call parameters（来自编排器 SKILL.md Step 12）

除 `patient_dir` 外，编排器可能追加两个列表参数，二者都**只影响患者向 HTML，不改结构化 JSON**：

- **`unfaithful_values`**（Phase 2.5 忠实度检查的 CRITICAL `not_faithful` 列表，元素 `{file, json_path, value}`，可能为 `[]`）：对列表里的**每一个**值，你在组装 `case_summary_data.json` 时**必须把对应字段置 `null`（→ 模板渲染 `资料缺失`），并且绝不在病情概要叙事里复述该值**。坏值仍留在结构化 JSON 里（已被 flag，待用户更正）——你只负责让患者向 HTML 不显示它。`.case_summary_data.json` 由你创建，所以"丢弃"发生在你这一步，不存在"渲染前再 null"的时机。
  - **数组元素要素感知（硬约束，否则整份 HTML fail-closed）**：若被丢弃的值属于某数组元素（`lab_trends[].current_value` / `molecular_rows[].molecular_value` / `treatment_lines[].*`），**只把该 value 字段置 `null`，保留整个元素并渲成"资料缺失"行——绝不删除整个数组元素**；并且**务必把同元素里所有会进入 `class` 属性的兄弟字段显式置为空字符串 `""`（不是省略、不是 `null`）**：`lab_trends[].status_class`、`treatment_lines[].line_marker_class` / `line_badge_class` 等。原因：省略/`null` 会触发引擎 `__default__` 回退，把"资料缺失"注入 `class="status-badge 资料缺失"`，`validate_case_summary_html.py` 报越界 class（exit 1）→ 整份病情简要总结 fail-closed 不交付。若某趋势值被判 unfaithful，**同时把该点从 `series[]` 移除**（不能画一个未忠实的点）。
- **`adjudications`**（Step 3c 对 load-bearing `cross_doc_contradiction` 的来源优先级裁决列表，元素含被裁决字段 + 胜出来源类，可能为 `[]`）：对每一条，你在 `caveats[]` 里追加一个 `{ "caveat_text": "<本 locale 渲染的 (来源存在差异，已按X裁决)，X=胜出来源类>" }`。脚手架文案按 locale 渲染，临床实体 verbatim，**绝不把该 note 内联进任何 verbatim 临床值串**（那会破坏照抄规则）；它只作为"数据说明"脚注另起一段。无裁决则不追加。同时把 `i18n.sec_caveats` 填成该 locale 的"数据说明"串。
- **`lab_trend_caveats`**（US-006 化验/肿瘤标志物**趋势** OCR 提示列表，可能为 `[]`）：对每一条，你在 `caveats[]` 里追加一个 `{ "caveat_text": "<本 locale 渲染的 (数值来自照片 OCR，请以检验原件核对)>" }`。**这是该提示的唯一落点**——`数据说明` 脚注负责它，**不要**再把它内联进 `病情概要`、`关键趋势 interpretation` 或 `当前治疗路径`（趋势本身现在只在 hero + 实验室行呈现，叙事不陈述趋势，故叙事里也无需该提示）。无趋势提示则不追加。
- 三个来源（`unfaithful_values` 丢弃 / `adjudications` 裁决 / `lab_trend_caveats` OCR 趋势）共同决定 `caveats[]`：全空 → `caveats: []` → 模板"数据说明"脚注整段不显示。

## locale（i18n）— 先读再填

先读 `profile.json.locale`（organize 已在 Phase2 写入）。整张 HTML 的**脚手架按该 locale 出**，**临床实体一律 verbatim**（药名/基因/变异/TNM/数值单位/VAF 记法照抄，禁止翻译 —— 误译=医疗风险，见 [`../../../references/i18n.md`](../../../references/i18n.md) §4）。

- **药名规范化：去研发代号、全文一致（硬约束）**：患者向输出一律用药物的**标准通用名 / 中文药名**，**绝不用研发 / 开发代号**（如 `AMG510`→`索托拉西布`、`MRTX849`→`阿达格拉西布`；`TAS-102` 若为其上市名则原样保留）。同一药物在文档多处出现（`treatment_markers[].label`、`line_regimen`、叙事 `病情概要`）时，**必须全文使用同一种名称形式**，不得一处代号一处通用名。这是把代号**去术语化**到标准名（**同一药物、不改是哪个药**），**不是翻译**——与"药名 verbatim / 禁误译"规则兼容：不改 WHICH drug，只在"代号 vs 标准名"之间取标准名并保持全文一致。

模板顶部有一张 **i18n 字符串表注释块**（section 标题 / 免责声明 / 字段标签 / "待主诊医生补充"占位 / 性别值 / ECOG 推断注 / "待启动" 等）。你把这些串填进 `case_summary_data.json` 的 `i18n` 对象（key→该 locale 的串），引擎再替换模板里的 `{{i18n.<key>}}`：

1. 按 `profile.json.locale` 选该 locale 的列，把每个 `i18n.<key>` 填成表里对应字符串；`html_lang` 填该 locale 的 `<html lang>` 值。
2. locale 不在表中（如 `fr`/`es`）→ 按 `en` 列语义在目标语言生成等义脚手架字符串（同义同语气），临床术语保持原文，**不要硬编码单语言串**。
3. 字段值里凡映射到固定脚手架的（性别 M→`i18n.val_male`/F→`i18n.val_female`、缺字段→`i18n.val_pending`、ECOG inferred 注→`i18n.val_ecog_inferred`、待启动→`i18n.val_to_start`）一律取自该 i18n 串，不在数据里写死中文。
4. 你不动 CSS / DOM；引擎按模板 1:1 渲染，只替换 `{{占位符}}` / 展开 `<!-- LOOP -->` / 判定 `<!-- RENDER_IF -->`。

## 输入

只读以下脱敏产物，**绝不读原图、绝不读含明文 PII 的旁车**：

- `profile.json`
- `patient_summary.json`
- `molecular.json`
- `labs.json`
- `treatment_lines.json`
- `timeline.json`
- `longitudinal_observations.json`（**若存在** —— 关键趋势 hero + 实验室趋势行的**多时间点 series 来源**；每个 `observations[]` 元素带 `{metric, value, unit, timestamp}`。按 metric 分组、按 timestamp 升序即得一条 series）
- `case_text.md`（仅取影像段，用于病灶分布）
- 模板（**只读，不改**）：`references/templates/case-summary.template.html`
- 数据契约（你的产物结构）：`references/schemas/case_summary_data.schema.json`

## 数据来源映射表（§3）

下表第 2 列是 `case_summary_data.json` 里的 **JSON key**（标量字段 / 数组），不是你要手写的 HTML。引擎拿这些 key 去填同名 `{{占位符}}` / 展开 `<!-- LOOP key -->`。

| 模板 section | JSON key | 来源 | 处理方式 |
|---|---|---|---|
| header 一句话病情 | `one_line_condition` | profile.json（summary.stage + summary.histology + 关键分子 + 当前线状态 / 或直接 summary.one_line_condition） | 字段拼接：`<stage> <histology> · <driver> · <当前治疗状态>` |
| header 报告日期 | `report_date` | 当日日期 | `YYYY-MM-DD` |
| 诊断与分期 | `stage` | `profile.summary.stage`（旧 flat profile → 顶层 `profile.stage`） | **逐字照抄**分期串；多层/待定/两院差异原样保留，不重新合成、不归一为单一干净 TNM（接 organize P0-2 verbatim 口径）；缺失 → `null`（模板渲染 `资料缺失`） |
| 患者标识 性别 | `sex` | `patient_summary.json.demographics.sex` | M→`i18n.val_male` / F→`i18n.val_female` 串值（走字符串表，不写死） |
| 患者标识 年龄 | `age` | `patient_summary.json.demographics.age` | **精确年龄**：照实渲染（如 `63` / `63 岁`，单位按 locale）——临床试验匹配需要精确年龄；仅遮 DOB/生日，**不再降十年段** |
| 患者标识 身高体重 BMI | `height_weight_bmi` | `patient_summary.json.demographics.height_cm` / `weight_kg` | `165 cm / 68 kg / 25.0`，BMI 自算（单位/数值 verbatim） |
| 患者标识 ECOG | `ecog` | demographics.ecog（+ ecog_inferred） | inferred 时在数值后追加 `i18n.val_ecog_inferred` 串值 |
| 病情概要 | `case_summary_narrative` | **subagent 生成** ← patient_summary.json + timeline.json | 见下"叙事段" |
| 关键趋势 | `trend_charts[]`（0..N 张；每张 `metric`/`unit`/`series[]`/`treatment_markers[]`/`interpretation`） | longitudinal_observations.json（选真正驱动决策的趋势指标）+ treatment_lines.json（marker 日期）| 见下"关键趋势"；**张数由你按临床判断定**；无有意义趋势 → `[]`（模板占位不删段） |
| 实验室指标 | `lab_trends[]`（`lab_name`/`series[]`/`current_value`/`unit`/`status_class`/`status_label`）+ `labs_period` | longitudinal_observations.json（series）+ labs.json（当前值/状态）| 见下"实验室指标趋势行"；0 个给 `[]` |
| 主要病灶分布 | `lesions[]`（`lesion_site` / `lesion_detail`） | profile.json 影像字段 / case_text.md 影像段 | 每解剖部位一个数组元素；0 个就给 `[]`，引擎自动占位 |
| 核心分子检测 | `molecular_rows[]`（`molecular_label` / `molecular_value`） | molecular.json | 每维度一个元素；0 个给 `[]` |
| 治疗史 timeline | `treatment_lines[]`（见 §"治疗史"字段） | treatment_lines.json / timeline.json | 已用/进行中=红框，待启动=pending 黄框；0 个给 `[]` |
| 当前治疗路径 | `path_items[]`（`path_label` / `path_content`） | treatment_lines.json 当前线 + profile.json | 逐条标签 + 内容；0 个给 `[]` |
| footer | `report_date` | 当日日期 | 同 header |

**数量全来自 data**：有几个 lesion/molecular/lab/治疗线/path 就给几个元素（0..N），引擎按数组长度渲。空数组（`[]`）→引擎走该段的 `RENDER_IF_NOT` 占位（"资料缺失"），section 永不删。

## 字段段填充（直接映射，不交 subagent）

除"病情概要"叙事段外，所有 section 都是结构化 JSON → 占位符的直接映射，不做语义改写、不增删临床事实。

### header
- `{{one_line_condition}}`：有 `profile.json.summary.one_line_condition` 时**逐字照抄**该预计算值（与 AGENTS.md 用的同一个值）；仅当它为 null 时，再从 `profile.json.summary.stage` + `profile.json.summary.histology` + 主驱动变异（molecular.variants[0]）+ current_status 简述重新拼接。current_status 简述取自 `patient_summary.json.current_status`，或 `profile.json.latest_status`——注意 `current_status` 不在 profile.json 里。临床实体 verbatim，连接词按 locale。例（zh）：`IV 期胰腺导管腺癌 · KRAS G12D · 一线 FOLFIRINOX 后 · 二线桥接治疗前`。
- 免责声明走 `{{i18n.disclaimer}}`（按 locale 出，文案语义固定，不增删内容）。

### 患者标识（脱敏硬约束）
- 性别填 `i18n.val_male`/`i18n.val_female` 串值；年龄**照实输出精确年龄**（`demographics.age`，如 `63` / `63 岁`，单位按 locale）——临床试验匹配需要精确年龄，**不再降十年段**；但**仍绝不输出出生日期/生日（DOB）**，只给整数年龄。
- 绝不输出真名、真实出生日期（DOB）、住院号、城市、国籍、**出生地/籍贯、职业/工作单位**——这些与临床决策无关且属可识别信息，一律不出现在患者标识或任何字段里。BMI = `weight_kg / (height_cm/100)^2`，保留一位小数（数值/单位 verbatim）。

### 诊断与分期（`stage` — verbatim，禁重新合成）
- `stage` **逐字照抄** `profile.summary.stage`；**旧 flat profile** 无 `summary` 时取顶层 `profile.stage`。
- 分期串可能是**多层 / 待定 / 两院差异**（如"初诊 pT3N2M0（ⅢB期）；术后复发再分期 rT3N3M0（ⅢC期）；某病灶待定"）——**原样保留全部层次与差异**，**绝不**归一/重新合成成单一"干净" TNM（这正是 organize 的 **P0-2 verbatim-only 分期**口径，改写=医疗风险）。
- 分期本身**不做** LLM 判断、不补插、不推断缺失层；只照抄结构化字段里已写明的字符。
- 缺失（`profile.summary.stage` 与 `profile.stage` 均无）→ `stage=null`，模板走 `RENDER_IF_NOT stage` 渲染 `i18n.val_pending`（`资料缺失`），段不删。
- 该段是分期的**主段**；`header 一句话`里 `one_line_condition` 仍可带 `<分期>` 做一眼定位，但完整/多层分期只在本段落地，两者信息层级不同，不算重复。

### 主要病灶分布
- 遍历 profile.json 影像字段（原发灶 / 各转移部位 / 淋巴结）；若影像结构化字段缺，交 subagent 从 `case_text.md` 影像段抽取病灶清单（仅抽取，不增补医学判断）。
- 每个解剖部位渲染一行 `<tr><td>部位</td><td>描述</td></tr>`。

### 核心分子检测
- 驱动突变行：molecular.variants（gene + variant + vaf + tissue）。
- 免疫表型行：msi_mmr + PD-L1（ihc）+ TMB。
- DDR 与其他行：剩余 variants（BRCA / CHEK2 / VUS 等）。
- 组织病理行：ihc / 病理描述字段。
- 字段照抄，VAF/突变记法不改字符。
- **IHC 记法（硬约束，否则信息错乱）**：免疫组化每个 marker 的判读结果一律按病理报告标准记法 `marker（value）` 渲染，把结果用括号包住（locale=zh 用全角 `（）`，其它 locale 用半角 `(...)`）——`molecular.json` 里 `{"marker":"HER2","value":"0"}` → `HER2（0）`，绝不渲成 `HER2 0`（裸值会与相邻 marker 串读乱，如 `EGFR 2+ HER2 0` 分不清）。整行示例：`EGFR（2+）；HER2（0）；Ki-67（约5%+）；MLH1（+）；panTRK（-）`。括号内的判读值 verbatim 照抄，分隔用本 locale 的分号。

### 关键趋势 — `trend_charts[]`（hero 图，总数 2–4 张，或 `[]`；选取见下方分层规则）

**哪些指标够格进 hero「关键趋势」——分层选取（不是纯自由判断）**：

先读 `references/cancer-trend-markers.md`（按 `profile.json` 癌种取行），按优先级选：

- **Tier 1（默认 hero，只要 ≥2 时间点）**：该癌种表里的 primary 疗效监测标志物；`longitudinal_observations.json`/`labs.json` 有该 marker ≥2 时间点 → 必选一张 hero。同癌种 primary 有 2 个（如生殖细胞 AFP+β-hCG、肝癌 AFP+PIVKA-II）→ 可放 **≤2 张 Tier1**。
- **Tier 2（患者特异）**：本病程中真正驱动决策的动态指标（LDH 升示负荷、胆红素爬升逼近某药禁用门、血象逼迫减量等），临床判断挑。
- **降级**：平稳 / 非疗效相关 / 单点 → **不进 hero**，落下面「实验室指标」`lab_trends[]` sparkline 行。
- **门槛**：≥2（最好 ≥3）时间点；能跨一次治疗切换（`treatment_markers` 对齐）的优先。
- **克制 / 总量**：hero **总数 2–4 张**，按决策权重排（Tier1 在前）；没有任何有意义可趋势化指标 → `[]`（模板占位不删段）。
- **无标志物 fallback**：癌种表标 `—` 或查不到该癌种 → **不硬凑 hero**；有 Tier2 就放，否则 `[]`。
- **先验服从个案**：病历显示该癌种规范标志物一直阴性/不分泌（如 Lewis 阴性者 CA19-9 不升）→ 据实不选，并在 `interpretation`/`数据说明` 说明。**读 caveat 列**：若某癌种的 marker 依组织学/亚型而定（如甲状腺分化型用 Tg、髓样癌用降钙素+CEA），按患者**实际组织学**选对应 marker，别把 co-primary 两个都画；caveat 标注的适用限制（如乳腺 CA15-3 不推荐单独监测、Lewis 阴性者 CA19-9 不升）须体现在该图 interpretation。
- **反滥用**：癌种表是优先级提示，**不是"必须画"**——marker 时间点不足即不画，**禁为满足 Tier1 编造 series 点**（compute_sparklines exit 3 会拦）。

每张图对象：

- **`metric`/`unit`**：指标名 + 单位，verbatim。**单位字形安全**：含上标的单位（如 `×10⁹/L`）在图表里一律写 **ASCII 安全记法 `×10^9/L`**（或 SI `G/L`），**绝不**用裸上标 unicode（`⁹`）——图表字体常把它渲成豆腐块（如"WBC ×10⌷/L"）。这不改数值、不改是哪个单位，只把上标 `^n` 化。
- **`series[]`**：该指标按 `timestamp` 升序的 `{"t": ISO 日期, "v": 数值}` 列表（≥1 点，1 点也可只画一个点），**`v` 逐字取自 `longitudinal_observations.json`，绝不改写、绝不补插值、绝不编造点**。
- **`treatment_markers[]`**：把与该指标时间跨度相关的治疗线**起始日期**（`treatment_lines.json` 的 `started_at`）作为 `{"t": ISO 日期, "label": "<短线名/方案>"}` 传入——"指标↔治疗方案对应关系"，compute_sparklines 对齐到同一时间轴。只挑 1–3 个关键切换点，label 要短。
- **`interpretation`**：**一句** locale 大白话，只陈述该图趋势方向（如"CEA 整体下降，提示治疗反应较好"），**不复述具体数值**（点值在图上）、**不追加 OCR/患者自述来源提示**（进 `数据说明`）、**不给新数字/治疗建议/预后**。
- **对肿标：只陈述该指标的趋势方向；不得给任何标志物贴'最敏感/最特异/最可靠/金标准'等诊断性能标签（那是 MTB 层的解读，不在本层）。**
- `svg_points`/`svg_area_d`/`dots`/`direction`/`marker_x`/`idx`/`marker_date` 由 compute_sparklines 逐图注入，你别碰。

### 实验室指标趋势行 — `lab_trends[]`（取代旧平铺网格）
每个关键化验/标志物一行：名称 + sparkline（迷你趋势）+ 当前值 + 状态徽章。

- **⚠️ 必须非空（硬约束）**：只要 `labs.json` 有任何 panel 或 `longitudinal_observations.json` 有任何数值指标，`lab_trends` **就必须非空**——至少覆盖所有肿瘤标志物 + 有异常/趋势的血常规/生化项。**只有患者确实一份化验都没有时才允许 `[]`**。若你把它落成空而 `labs.json` 有 panels，编排层的 `backfill_lab_trends.py` 会从 panels 兜底自动补齐（name/series/current_value/status 全取自结构化数据）——但那是保底，不是你偷懒的借口：你应主动按病情选行、给出更贴切的顺序。
- **选行**：挑临床关注的 analyte（肿瘤标志物优先、异常项、有多时间点趋势的项），每项一个 `lab_trends[]` 元素。
- **按病情语境选行（"选得准，不是放得全"）**：这是一页纸，**继续 curate，不要把每一条异常值都倒进来**。但**选择要被这个病人的临床语境偏置**——优先保留对**这个**病人是"看点/须盯项"的化验：
  - **贴合当前方案的毒性谱**：含铂/伊立替康方案 → 肾功能 Cr + 血常规（CBC）；肝毒性方案 → 肝功能（ALT/AST/胆红素）；抗血管生成 → 尿蛋白/血压相关项。
  - **贴合已记录的既往 AE / 合并症**：有骨髓抑制史 → WBC/PLT/中性粒；有肾功能不全/心脏基础病 → 对应监测项。
  - **可丢**：与当前临床图景无关的轻度异常（偶发、非决策相关、无趋势）可以不放。
  - **原则**：**语境关键的化验绝不被静默丢掉**（该病人正盯的项必须在），无关噪声该丢就丢。不是"覆盖全部异常"，是"选中该盯的那几项"。
- **`series[]`**：该 analyte 按时间升序的 `{t,v}`，**逐字取自 `longitudinal_observations.json`（无纵向点则取 `labs.json` 的单点）**；不改写、不编造。单时间点合法（不画线，只显当前值+徽章）。
- **`current_value`**：**只填数值本身**（如 `2.1` / `<2.00`），单位放 `unit`。**不要**写成描述性从句（`× ULN`、`患者自述`、`较峰值回落`、趋势方向等一律**不进** `current_value`——那些进 `数据说明` 或不写）。原因：`current_value` 会进「实验室指标」当前值列，也是「自上次变化」delta 的对比字段；塞进一整句会让 delta 条变成一大段，密度崩掉。
- **`status_class`**（进 CSS class，缺/未知一律显式 `""`，禁省略/`null`）：`normal`（正常）/`low`（偏低）/`high`（偏高）/`abnormal`（异常，一般 <3× 参考上限）/`severe`（严重，≥3× 或危急值）。判定用 `labs.json` 的 `value`+`reference_range`，缺 range 时用 `flag`（H→high、L→low、HH→severe、LL→severe/low 视情、异常无方向→abnormal）。
- **`status_label`**：该 locale 的状态词（正常/偏低/偏高/异常/严重）。
- sparkline 坐标（`svg_points`/`direction`）由 compute_sparklines 注入。**趋势行里的每个 series 点也受 compute_sparklines 反造假门约束**——凡画出来的点必须在 `longitudinal_observations.json`/`labs.json` 里能查到同 (metric,value)。

### 治疗史 timeline
- 遍历 treatment_lines.lines（按 line 升序）。
- 已结束或进行中的线：`{{line_marker_class}}` 留空（红框）。徽章两字段各有明确规则（**硬约束**，两个都要填，不能只填其一）：
  - `{{line_badge_text}}` = 该线的**最佳缓解 / 缓解类别**，**逐字取自来源**（`treatment_lines.json.best_response`，或该记录 / timeline **明确写出**的缓解词：`PD` / `SD` / `PR` / `CR` / `CC0` / `维持中` / `肿标↑` / `肿标↓` / `术前桥接` / `新辅助` 等）。**CC0、SD、维持中 是有据可查的事实、不是推断——来源写明就必须填，绝不留 `null`。** 仅当来源对该线**根本没有记录任何缓解**时才置 `null`（→ 渲染 `资料缺失`，此时才是正确的）。
    - **疗效红线（P0，见 `../../../references/safety-guardrails.md`）**：`best_response` 若为 `null`（来源没逐字写响应类别），这里就是 `null`——**绝不**自己把影像的描述性发现（"病灶缩小/减轻"）转写成 `PR`/`SD` 填进徽章；也**绝不**在徽章或叙述里加 RECIST 定义式注解（如"部分缓解，病灶缩小超过 30%"——那个 30% 是**定义**不是这个患者的实测）。判疗效是医生的事。
  - `{{line_badge_class}}` = 仅当缓解为**进展（`PD` / 进展）**时填 `pd`（红）；其余任何缓解（`SD`/`PR`/`CR`/`CC0`/`维持中`/`肿标↓`/`术前桥接`…）一律填**空字符串 `""`**（中性基座 `.tl-badge` 样式，**不红**，避免给一条稳定 / 有反应的线过度报警）。（对应模板可用 class：`.tl-badge.pd` 红 / `.tl-badge.pending` 黄 / 基座中性。）
- `ended_at` 为 null 且未启动（待启动）：`{{line_marker_class}}`=`pending`（黄框），`{{line_badge_class}}`=`pending`，`{{line_date_range}}`=`{{i18n.val_to_start}}`。
- `{{line_label}}`（**硬约束，违反即临床不准确、整份 fail**）：**用治疗意图渲染，绝不自动编序数**。取 `treatment_lines.json` 每条线的 `intent` 字段，按 locale 映射为临床意图标签：`neoadjuvant`→新辅助、`adjuvant`→术后辅助、`perioperative`→围手术期、`palliative`→姑息治疗、`maintenance`→维持治疗、`definitive`→根治、`consolidation`→巩固（`intent` 取值即 `treatment_lines.schema.json` 的 7 项 enum，无 `radical` 这一项——根治意图统一记 `definitive`）。**严禁从 `line` 整数推导 `一线`/`二线`/`三线`… 这类裸序数标签**（validator 会对 ≥2 条裸序数 `^[一二三四五六七八九十]+线$` 直接 FAIL）——围手术期 / 新辅助治疗本身已是一线，再把手术、新辅助、后续晚期线编号成"一线/二线/…/十二线"临床不准确。`intent` 缺失时用中性时段标签（按 locale 的"第 N 段治疗"/"Phase N"），按 `started_at` 先后排，不臆断线序；仅当病历**逐字写明**了线序（如"姑息一线"）才 verbatim 照抄该原文，不另行推算。
- `{{line_regimen}}`=regimen 照抄（临床实体 verbatim）；`{{line_note}}`=best_response + reason_for_change + 影像转归（取自 timeline 对应区间，照抄不增补；连接词按 locale）。
- 口述/未经机构确认的信息要在 note 按 locale 注明等义于"待治疗机构出具/待主诊医生确认"。

### 当前治疗路径
- treatment_lines 中当前线 + profile 计划字段，逐条渲染。每条：`<span class="label">标签：</span>内容`，条间 `<br>`，末条不加 `<br>`。
- 标签如"当前较可能的路径：""桥接：""备选试验路径："。仅复述病历/计划已载明内容，不新增推荐方案。

## 信息密度与去重（硬约束 —— 每段各司其职，绝不互相复述）

这份总结是**一页纸**，同一事实**只在它的"主段"出现一次**。真实回归里出现过 CEA 趋势重复 5 次、OCR 提示重复 5 次、诊断/方案各重复 3 次——密度低、读起来累。规则：

- **诊断+分期**：主段 = header 一句话 (`one_line_condition`) + 患者标识。`病情概要`可**极简带过**诊断名，**不重抄** TNM/组织学细节（那些在分子/病灶段）。
  - **`one_line_condition` 必须是一行 headline（≤ ~35 字）**：`<分期> <组织学> · <驱动> · <当前治疗状态>`，例"IV 期胃腺癌 · 印戒细胞癌 · 免疫维持中"。**绝不写成一整段临床叙事**、**绝不塞标志物趋势/数值**（CEA 550→50 那种进「关键趋势」图，不进标题）、**绝不与`病情概要`重复整句**。头部是一眼的定位，`病情概要`才是 3–4 句展开——两者信息层级不同，不是同一句话写两遍。
- **化验/标志物趋势**：主段 = `关键趋势` hero + `实验室指标` 行。`病情概要`**不复述任何具体数值或升降序列**（不写"CEA 由 X 升到 Y"——hero 已画）；`当前治疗路径`也不复述标志物数值。
- **治疗方案/剂量**：主段 = `治疗史` timeline。`病情概要`只说"已用 N 线、当前 X 线治疗中"级别的**概括**，**不逐字抄 regimen/剂量/放疗剂量**；`当前治疗路径`只说方向，不再抄一遍完整方案。
- **数据来源/OCR/患者自述提示**：**唯一主段 = `数据说明` (`caveats[]`)**。**不要**把 OCR/患者自述提示再内联进 `病情概要`、`关键趋势 interpretation`、`当前治疗路径`。（这条覆盖下文旧的"叙事里陈述趋势就追加 OCR 提示"——现在趋势不在叙事里陈述，故也不在叙事里加提示。）
- **缺项提示**（如未做 NGS）：主段 = 对应结构段的占位（`核心分子检测`）。`当前治疗路径`的"待补充"只列**下一步该补的动作**，不重列已在别处显示的缺项。

## 叙事段（病情概要）— 交 subagent / LLM 生成

`{{case_summary_narrative}}` 是唯一需要语义生成的段落。交 subagent 处理，prompt 要点：

- 输入：patient_summary.json + timeline.json（脱敏后）**＋ 必须把 `unfaithful_values` 传给该 subagent**（patient_summary/timeline 里仍带着未忠实值，叙事 subagent 默认看不到 Phase 2.5 的判定）。
- **输出语言按 `profile.json.locale`**（叙事是脚手架 → output in `<locale>`；临床实体 verbatim per i18n.md §4）。
- **短**：**3–4 句、≤120 字**的定向导览，只回答"这是谁、什么病、走到治疗旅程的哪一步"。**不是**逐段复述——它是让读者快速进入状态的开场，细节交给下面各结构段。
- 结构：诊断名（一句带过）→ 已用/当前治疗线的**概括**（不抄方案/数值）→ 当前处境与下一步方向（不抄标志物数值、不抄 OCR 提示）。
- 硬约束：只复述 JSON 已有事实，**禁止新增任何医学判断、预后、治疗建议**；禁止出现真名/生日（DOB）/医院全称/**出生地/籍贯/职业/工作单位/家庭住址**（机构粗粒度化，按 locale 出，如"某北美学术癌症中心""a North American academic cancer center"；精确年龄可保留）；JSON 缺关键字段时该句省略，不编造；药名/基因/变异/TNM/数值单位一律原文不译。
- **忠实度硬约束（US-003）**：`unfaithful_values` 列出的任何值（含被它污染的 stage/标志物/剂量）**绝不出现在叙事里**——当作缺失跳过该句，不复述、不改写。
- **OCR 趋势提示（US-006）归属 `数据说明`，不进叙事**：叙事**不陈述**具体化验/标志物趋势（那是 hero + 实验室行的职责），因此**不在叙事里追加** OCR 提示；`lab_trend_caveats` 只汇入 `caveats[]`（见"信息密度与去重"）。
- 不写硬编码模板句拼接 keyword list，交 subagent 按上述要点自然生成。

## 缺字段处理（fallback 文案进 data，不进模板）

引擎对**标量占位符**有 fallback 机制：某 `{{key}}` 对应的 data 值为 `null`/`""`/缺失时，引擎按顺序取 `fallbacks[key]` → `fallbacks.__default__` → `""`。所以你把"资料缺失"类文案放进 `case_summary_data.json` 的 `fallbacks` 对象（key = 占位符名，value = 该 locale 的占位文案，如 zh `"资料缺失"`），并务必给 `fallbacks.__default__`（兜底，如该 locale 的 `i18n.val_pending`）。**不捏造、不推断填充**真实临床值。

- 标量缺字段（如 `ecog`/`labs_period`/`one_line_condition` 为 null）→ 引擎自动落该 key 的 fallback 或 `__default__`，section 结构照常渲染。
- 整段数组无数据（如无 molecular.json）→ 给 `[]`，引擎走该段 `RENDER_IF_NOT` 占位行（"资料缺失"），section 标题与骨架保留、不删。
- 所有空段都靠模板里的 `RENDER_IF_NOT` 占位或标量 fallback 兜住，**永远不留空表 / 不删 section**——validator 查"形"的骨架对任何病人都成立。

## 输出（先 JSON，后跑引擎，再过 validator；不过则不出文件）

`<patient_dir>` 是上游（SKILL.md / INSTALL.md）按**单一解析规则** `$CANCER_BUDDY_PATIENTS_DIR → $VMTB_PATIENT_DATA_ROOT → $HOME/CancerDAO/patients` 解析出来、再作为 call parameter 传给你的绝对路径。你**直接用这个 `patient_dir`**，自己**绝不重新发明输出根**、不另解析环境变量。

1. 把渲染数据对象写到 **`<patient_dir>/.case_summary_data.json`**（**点开头的隐藏文件** —— 它只是喂给模板引擎的渲染中间产物，不是患者向产物，不应出现在目录顶层可见清单里；渲染成功后保留作 re-render/debug 即可），结构遵 `references/schemas/case_summary_data.schema.json`（i18n 串表 + fallbacks + 各标量 + `trend_charts` + `lab_trends`/lesions/molecular_rows/treatment_lines/path_items 数组；`version_delta` 与所有 SVG 坐标字段留给下一步的确定性脚本注入，你不写）。

1.5. **确定性富化（两个零医学逻辑脚本，按序在 render 之前跑）**：

   ```
   # (a) 保底 —— lab_trends 空则从 labs.json 的 panels 自动补齐(已有则 no-op)
   python3 scripts/backfill_lab_trends.py --data <patient_dir>/.case_summary_data.json --labs <patient_dir>/labs.json --profile <patient_dir>/profile.json

   # (b) 自上次总结的变化 —— 对比上一版快照(若有);首版无快照 → version_delta:null
   prev=$(ls -1 <patient_dir>/case_summary_versions/case_summary_data_*.json 2>/dev/null | sort | tail -1)
   if [ -n "$prev" ]; then
     python3 scripts/compute_version_delta.py --data <patient_dir>/.case_summary_data.json --prev "$prev"
   else
     python3 scripts/compute_version_delta.py --data <patient_dir>/.case_summary_data.json
   fi

   # (c) 注入 SVG 趋势坐标 + 反造假门(每个画出的点必须在纵向库/labs 里查得到,否则 exit 3 拦停)
   long=""; [ -f <patient_dir>/longitudinal_observations.json ] && long="--longitudinal <patient_dir>/longitudinal_observations.json"
   python3 scripts/compute_sparklines.py --data <patient_dir>/.case_summary_data.json $long --labs <patient_dir>/labs.json
   ```

   compute_sparklines exit 3 = 你的 `series[]` 里有 `longitudinal_observations.json`/`labs.json` 查不到的点（造假/改写）→ **不要绕过**，回去把该点改成 verbatim 原值或删除，再重跑。

2. 跑确定性模板引擎填模板、落 HTML：

   ```
   python3 scripts/render_html_template.py \
     --template references/templates/case-summary.template.html \
     --data <patient_dir>/.case_summary_data.json \
     --out <patient_dir>/病情简要总结.html
   ```

   HTML 文件名固定中文，下游按固定名取，不随 locale 改名。引擎 exit 0 = 无残留 `{{...}}`；exit 1 = data 漏 key（补 `case_summary_data.json`，**不要去改模板**）。

   > **dated 快照是 orchestrator/host 文件级步骤,不在本 data-only producer 范围内**：每次(重)渲染后，编排层（SKILL.md Step 12 / `organize-contract.md` 步骤 4）须把 `病情简要总结.html` 复制一份不可变快照到 `case_summary_versions/病情简要总结_<date>.html`（同日重渲后缀 `_2`/`_3`），**并把富化后的 `.case_summary_data.json` 同样快照到 `case_summary_versions/case_summary_data_<date>.json`**（下一版 `compute_version_delta` 的对比基准就靠它）。re-render 永不销毁患者已分享的旧版本。本 producer 只产 data JSON + 跑富化/渲染/校验，不做 `cp`（data-only 子代理无文件级快照职责）——见 `organize-contract.md` 步骤 4。

3. 跑"形"不变量校验器（模板固定、与病人无关的骨架检查 —— style 块逐字节一致、无越界 CSS class、无残留 `{{...}}`、无 PII（DOB/邮箱/身份证/电话——**精确年龄允许**，临床试验匹配需要）、骨架 section 齐、provenance template_sha256 与本次模板一致）：

   ```
   python3 scripts/validate_case_summary_html.py \
     --html <patient_dir>/病情简要总结.html \
     --template references/templates/case-summary.template.html
   ```

   validator **只查形、不查具体临床内容**（绝不断言"必须有某化验 / 某 `.lab-grid`" —— 无化验的病人合法地没有这些）。exit 0 = 形不变量成立；exit 1 = 形被破坏（手写过 HTML / 漏渲染 / 泄 PII / 越界 class）。

4. **fail-closed：renderer 或 validator 任一非 0，就不交付 `病情简要总结.html`** —— 删掉/不落这份 HTML，回报失败原因（哪个 exit、哪条 error），不要把一份形不合规或带残留/PII 的 HTML 留在 `patient_dir`。修 `case_summary_data.json` 后重跑 2→3，直到两步都 exit 0 才算产出成功。

- 你不写、不改 HTML/CSS/排版；模板逐像素由引擎保持，class/样式/结构由模板单方决定。**禁止手写 HTML**——唯一合法产出路径是「写 data JSON → 引擎渲染 → validator 放行」。
- 脱敏不改临床字符：遮的只能是 PII，VAF/剂量/数值/突变记法原样保留；临床实体禁译（i18n.md §4）。

## 返回契约（你交回编排器的东西 —— 不是 HTML，是一个 template_sha 或一个失败）

你**在自己这个子代理的上下文里跑完整条管线**（写 data JSON → `backfill_lab_trends.py` → `compute_version_delta.py` → `compute_sparklines.py` → `render_html_template.py` → `validate_case_summary_html.py`），然后**只返回一个 JSON 对象**，两种形态之一：

- **成功**：`{"status":"ok","template_sha":"<validate_case_summary_html.py 回显的 64 位十六进制 template_sha>","html_path":"<patient_dir>/病情简要总结.html"}`。`template_sha` 是"HTML 确实由模板渲染、没被手写"的**唯一证明**——validator exit 0 才拿得到它。
- **失败**：`{"status":"failed","stage":"<render|validate|sparkline_antifab|...>","exit_code":<n>,"reason":"<哪条 error>"}`，**并且不留下**那份不合规 HTML（fail-closed，见"输出"§4）。

**绝不**把 HTML 正文、或"我生成了一份总结"这类自然语言当作返回值——编排器靠 `template_sha` 判定你有没有真的走模板。**没有 template_sha 就是没完成**，编排器会据此重派你，而不是接受一份手写产物。这条契约是整个流程对上下文压缩最关键的一环：把"必须走模板"的机制锁在你这个干净上下文里，编排器只需检查你回没回 `template_sha`。
