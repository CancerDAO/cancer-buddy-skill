# 域无关层与域知识层（domain-pack）

`cancer-buddy-organize` 的数据层是**疾病无关**的：同一套 14+1 桶、同一套转写 prompt、
同一套忠实度/PII 门，服务肿瘤、罕见病（firefly）、慢病和健康基线档案。
肿瘤特有的东西（TNM、VAF、NGS 报告完整性）不是内核的一部分，是**挂上去的一个 pack**。

这份文件定义这条切线在哪，以及新域怎么接进来而不用改感知层。

---

## 1. 两层的边界

### 1.1 域无关层（内核，永远生效）

| 面 | 内容 | 为什么域无关 |
|---|---|---|
| 分页转写 | `organizer-prompt-phase1-transcribe.md` 的输入/输出契约、像素页 vs born-digital 两条规则、`[章:]`/`[手写:]`/`[☑]`/`[圈:]` 标记 | 纸是什么纸，与病种无关 |
| 通道独立二读 | `organizer-prompt-second-read.md` 全文、`high-risk-fields.md` §1.1 通用 9 类 + §2 通道 + §3 人工抽查（`human_sample_plan.json` + `human_sample_result.json` 两份） | 读错一个剂量，任何科室都伤人 |
| 来源分层 | `source_reported` / `patient_reported` / `caregiver_reported` / `system_normalized` 互不覆盖；冲突 `disputed` | 证据学不是病种知识 |
| 归档骨架 | `bucket-taxonomy.md` §1.1 的 14 个**临床域**桶 + `15_未分类资料` 开放桶 + `raw/` + `99_` | 域名是「诊断/影像/检验/治疗」，不是「肺癌/乳腺癌」 |
| 忠实度与 PII | `organizer-prompt-phase2_5-faithfulness.md`、`pii-rescan-prompt.md` | 同上 |
| 结构化骨架 | `patient_summary` / `timeline` / `labs` / `comorbidities` / `longitudinal_observations` / `source_inventory` / `readiness` / `missing_items` | 通用临床骨架 |

**内核里不得硬编码任何病种词。** `肿瘤标志物` 是 `07_检验` 下的一个 pinned 子桶名，
`molecular.json` 是一个 schema 文件名——它们是**槽位**，不是内核对「癌症」的判断。

### 1.2 域知识层（pack，按需挂载）

一个 domain pack 是下面四样东西的**打包**，缺一不可自洽：

| 组成 | 落在哪 | 肿瘤 pack 的实例 |
|---|---|---|
| **taxonomy 增补** | `bucket_taxonomy.json` 的 pinned 子桶 | `06_分子与组学/{NGS报告,免疫组化,胚系检测,…}`、`07_检验/肿瘤标志物`、`08_治疗/{化疗,放疗,免疫治疗,靶向,内分泌,中医中药}` |
| **schemas 增补** | `references/schemas/*.json` | `molecular.schema.json`、`treatment_lines.schema.json`（line 标签只在有文档时写） |
| **checklists** | `references/checklists/<CANCER>.yaml` | 19 份癌种 existing-document inventory（`mode: existing_document_inventory_only`） |
| **高风险 pack** | `high-risk-fields.md` §1.2 | `stage` / `variant` / `vaf` / `response_wording` |

### 1.3 挂载与卸载规则

- **挂载是加法**：pack 只能往通用层上**增加**子桶、schema、checklist、高风险类。
  **不得**删减通用层的任何一项，不得放宽通用层的门。
- **未挂载 pack 时**，该域的字段照样被转写（全文永远完整），只是：
  - `doc_kind` 落到 `novel:<slug>`，
  - `clinical_class` 由段 1 按枚举给出（`molecular|lab|imaging|pathology|narrative|admin|unknown`），
  - sidecar 落 `15_未分类资料/<slug>/`，
  - 不跑该域专属的完整性门。
  **「没挂 pack」的正确表现是「进开放桶 + 声明类别」，不是「读不出来」也不是「丢掉」。**
- **一次运行可挂多个 pack**（肿瘤 + 慢病共存的患者很常见）。清单取并集，
  子桶取并集，冲突的 pinned slug 由 `bucket_taxonomy.json` 唯一裁决。
- **pack 不得影响临床红线**：任何 pack 都不能授权推断分期、ECOG、疗效、进展、治疗线、
  预后或检查适应证。pack 给的是**槽位和词表**，不是判断权。

### 1.4 判定归属的一句话

> 「换一个病种，这条规则还成立吗？」成立 → 内核；不成立 → pack。

按这条：`dose` 的 `0` 个数要复核 → 内核；HGVS `c.`/`p.` 串位要复核 → 肿瘤 pack；
`reference_range` 用报告自印区间 → 内核；`TNM 版次` 必填 → 肿瘤 pack。

---

## 2. 新增一个 pack 的步骤

1. **列桶**：在 `bucket_taxonomy.json` 对应 `NN_` 域下增 pinned 子桶（zh + en 两套 slug），
   同步 `bucket-taxonomy.md` §1.1/§1.1a 表格，bump `scheme_version`。
   **不新增顶层 `NN_` 域**——新域名几乎总能落进现有 14 个临床域；真落不进的进 `15_`。
2. **列 schema**：只在现有骨架装不下时才新增 `*.json`，并在 `schemas/README.md` 登记。
   能用 `longitudinal_observations` 表达的序列，不要新造文件。
3. **列 checklist**：`references/checklists/<KEY>.yaml`，`mode: existing_document_inventory_only`，
   只写「这类记录若已存在，问用户要不要加进来」，**永远不写「应该做什么检查」**。
   遵 root `clinical-content-governance.md`：适用性、一手源、版本、有效期、人工专科复核。
4. **列高风险类**：在 `high-risk-fields.md` §1.2 之后增一节，给出键、覆盖范围、典型误读。
   每一类都要能说出「读错了会怎样」。
5. **配负向测试**：新子桶的 slug 冲突、新高风险类漏二读、pack 未挂载时该类材料是否仍进
   `15_` 且带 `clinical_class` —— 三条至少各一个。

---

## 3. 非视觉模态：确定性适配器在段 0 完成解码

DICOM、VCF/BAM/FASTQ、可穿戴时序导出、专有厂商格式**不是图也不是纸**。
它们在**段 0**由确定性适配器处理，产物是 `text_layer`，然后才进入段 1。

### 3.1 铁律

> **LLM 不解码二进制。** 模型不得声称自己读了 DICOM 像素、BAM 记录或专有二进制块，
> 不得从文件名/大小/片段猜测内容。没有经过验证的格式专用工具，就产 BLOCKED/PARTIAL stub。

### 3.2 各模态的段 0 处理

| 模态 | 段 0 适配器做什么 | 交给段 1 的 `text_layer` | `text_layer_kind` |
|---|---|---|---|
| **DICOM** | 用 DICOM 库读**头/元数据与结构化报告（SR）**：设备、序列、采集时间、层厚、体位、报告文本。**不解读像素**，不做影像诊断 | 元数据表 + SR 文本 | `not_applicable` |
| **VCF / 注释 TSV** | 用 VCF 解析器读 header + 记录：染色体、位置、REF/ALT、HGVS、VAF、FILTER、深度、参考基因组版本 | 规范化表格文本 | `not_applicable` |
| **BAM / FASTQ / CRAM** | **不解码**。记录文件存在、hash、大小、配套报告指针 | BLOCKED stub 文本 | `not_applicable` |
| **可穿戴 / 时序导出** | 解析 CSV/JSON/厂商导出为观测序列：metric、value、unit、timestamp、device | 观测表文本（并直接喂 `longitudinal_observations.json`） | `not_applicable` |
| **表格 / 原生 docx / txt** | 读原生文本/单元格层 | 原生文本 | `born_digital` |
| **专有导出（不支持）** | 不猜，产 PARTIAL/BLOCKED stub，说明能读什么、不能读什么 | stub 文本 | `not_applicable` |

### 3.3 段 1 在非视觉模态上做什么

`text_layer_kind: not_applicable` 时段 1 **没有 `image`**，它只做：
版面整理（把适配器的表格文本排成可读 MD）+ 字段抽取 + `clinical_class` 判定。
它**不得**：宣称视觉读取、给 `bbox`（此时 span 只有 `text_layer_offset`）、
对二进制内容做任何推断。

高风险字段的二读在非视觉模态上通道是**确定的**：适配器输出即确定层，
`reread_channel: text_layer`，脚本直接比对，0 次模型调用。
适配器读不出该字段 → 该字段 `high_risk_fields[].status: needs_human_review`
（行级 `high_risk_review_status` 由它派生），不是「模型补一个」。

> **`reread_channel: text_layer` 的前置条件在非视觉模态上是 `text_layer_kind: not_applicable`，
> 不是 `born_digital`。** 那条 gate 要挡的是 `embedded_ocr`——扫描仪自带 OCR 的文本层是概率产物，
> 拿它当第二通道等于用一个 OCR 给另一个 OCR 背书。而 VCF 解析器、DICOM 头读取器的输出是
> **确定性工具**的产物，独立性比 born-digital 字符层只强不弱。
> 因此该 gate 的完整条件是 `text_layer_kind ∈ {born_digital, not_applicable}`；
> 只写 `born_digital` 会把每一个 VCF 变异都推进人工复核队列。
> （这与 A5 字面表述有出入，已在交付说明中标为待确认项。）

### 3.4 不得静默降级

不支持或部分可读的格式**永远**产 BLOCKED/PARTIAL stub + `kind: unreadable` 的 inventory 行，
并把高风险字段路由到人工。**不静默采样、不静默丢弃、不用「大概是……」填补。**
`kind: unreadable` 的源不得被任何患者向面当作「已覆盖」，必须出现在
`readiness.json.projection_coverage.summary.unreadable_sources`。

---

## 4. 域无关性回归（防漂移）

改动内核面时至少验这三条：

1. **无 pack 跑通**：不挂任何 pack 跑一份非肿瘤材料（如一份普通体检报告），
   全文完整、`15_` 落库、`clinical_class` 正确、门全绿。
2. **内核里无病种词**：内核文件里不出现具体癌种名；癌种只出现在 `checklists/` 与
   pack 章节。
3. **多 pack 并存**：同时挂肿瘤 + 慢病 pack，高风险清单取并集且无重复键，
   子桶 slug 无冲突。
