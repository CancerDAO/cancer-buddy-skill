# 高风险字段清单与通道独立复读（high-risk-fields）

这是「哪些格子读错会伤人」的**唯一权威定义**。段 1 转写按它标 `high_risk[]`，
段 1.5 按它决定二读，段 2.5 按它决定 100% 复核面，validator 按它判
`high_risk_review_status`。其它文件与本文件不一致时，**本文件赢**。

> **关键词层的唯一权威实现是 `scripts/_high_risk.py::classify_label`。** 本文件定义
> *有哪些类、为什么它们危险*；把一个 label 判进哪一类的**词表**只存在于那一个 .py 文件里，
> `plan_second_read.py` 与 `validate_structured_outputs.py` 都 import 它，validator 用它做
> **分母对账**（遮蔽版 frontmatter 的 `fields[].label` 经它得到确定性集合 D，
> inventory 的 `high_risk_fields[]` 必须 ⊇ D）。**不要在任何别的脚本、prompt 或文档里
> 复制一份词表** —— 两份词表一旦漂移，分母就变成"谁先跑到"的结果。新增关键词改那一个文件。

来源：2026-07-17 临床参考审计 P0-7 —— 确定性 OCR + LLM 复核 + **数字双录 + 高风险字段人工抽查**。
感知层从「确定性 OCR 主读」换成「多模态转写主读」**不改变**这条要求；换的是通道来源，
不是要不要二读。

---

## 1. 两层清单

清单分**域无关的通用层**与**按域挂载的 pack**（分层理由见 `domain-pack.md`）。
一次运行的有效清单 = 通用层 ∪ 已挂载的所有 pack。

### 1.1 通用层（9 类，永远生效，任何疾病域、任何模态）

| 键 | 覆盖什么 | 典型误读 |
|---|---|---|
| `identifier` | 姓名、住院号、门诊号、病案号、就诊卡号、MRN、身份证号 | 形近字、号码位数缺一位 |
| `date` | 报告日期、采集日期、入/出院日期、给药日期、手术日期 | `07-15` vs `01-15`；年份错位；月日互换 |
| `drug_name` | 通用名、商品名、方案缩写 | 形近药名（顺铂/卡铂、他汀/替尼类后缀） |
| `dose` | 剂量数值（含单位换算前的原值） | **`0` 的个数**；小数点位；`mg` vs `mg/m²` |
| `frequency` | q3w / bid / qd / 每日一次 / 隔日 | `q3w` vs `q3d`；`bid` vs `tid` |
| `lab_value` | 任何检验/检查数值 | 小数点位移；相邻列串行；千分位 |
| `unit` | `10^9/L`、`g/L`、`ng/mL`、`U/L`、`mg/m²` | 上下标丢失；`μ` 与 `u`；量级差 1000 倍 |
| `reference_range` | 该次报告自己印的参考区间（**不是通用教科书区间**） | 上下限颠倒；把别行的区间串过来 |
| `accession` | 检验号、标本号、样本号、条码号、报告编号、病理号 | 末位字符；前缀字母/数字混淆 |

### 1.2 肿瘤 pack（4 类，随 oncology domain pack 挂载）

| 键 | 覆盖什么 | 典型误读 |
|---|---|---|
| `stage` | TNM 串、AJCC/FIGO 分期、分期版次（第几版） | `cT4N1M1` vs `cT4N1M0`；c/p/y 前缀丢失；版次缺失 |
| `variant` | 基因符号 + HGVS `c.` / `p.` 串、融合伙伴、拷贝数 | `c.` 与 `p.` **串位**；碱基形近（`T`/`I`）；氨基酸三字母/单字母混用 |
| `vaf` | 变异等位基因频率 | **`%` 与小数两种口径**（`32%` vs `0.32`）；有效位数 |
| `response_wording` | **疗效原文逐字串**：报告/病程里写出的 `CR`/`PR`/`SD`/`PD`、「完全缓解/部分缓解/疾病稳定/疾病进展」字样，**以及该次评效的日期**（评效日期、影像对比日期） | `PR` 与 `PD` 单字符之差；`SD` 与 `PD` 形近；把描述性发现（「病灶较前缩小」）当成一个响应码；评效日期错配到另一次复查 |

> **`response_wording` 只核"纸上写了什么"，不核"这个疗效对不对"。** 它进高风险清单不是因为
> 我们要判疗效——恰恰相反：疗效判定是主诊医生的事，本 skill 绝不自行推导（根 `safety-guardrails.md`
> P0 红线）。正因为这个值**只能照抄**、任何地方都不许重新合成，它一旦抄错就没有第二条纠正路径，
> 下游会把一个错的响应码当作"医生写的"。描述性发现（「较前缩小/增大/稳定」）**不是**
> `response_wording`，它保留为描述，不转成响应码，也不进这一类。

> 其它 pack（罕见病、慢病、儿科……）按同样方式增列，见 `domain-pack.md` §2。
> **新增 pack 只能往清单里加，不能从通用层里减。**

### 1.3 不在清单里 ≠ 可以随便读

未命中清单的字段仍要如实转写；它们只是不**无条件**触发二读。
它们在下列任一情况下同样进二读队列：段 1 自报 `uncertain`、跨通道出现 `discrepancy`、
确定性 OCR 与转写在数值上冲突。

**二读触发器 = 本清单 ∪ `uncertain[]` ∪ `discrepancy[]` ∪ OCR 数值级冲突。**

清单必须是**主项**而不是全靠自报：小数点、单位、HGVS 串位、VAF 口径、剂量里 `0` 的个数，
恰恰是模型读得很顺、却与「自报不确定」**反相关**的地方。只靠 `uncertain[]` 触发，
等于漏掉最危险的那一类。

---

## 2. 通道独立与优先级

### 2.1 什么算独立通道

三选一（详细定义与 prompt 见 `organizer-prompt-second-read.md` §0）：

1. **不同模型** —— `alternate_vision_model`（不同权重，不是同一模型换温度/换 prompt）；
2. **不同模态** —— `text_layer`（born-digital 字符层）/ `barcode`（条码解码）/
   `deterministic_ocr`（**可解析**的确定性 OCR 输出）；
3. **人工** —— `human`。

**同模型同图的裁剪复读只作 tie-break**，不得置 `passed_independent_reread`，
不得写进 `reread_channel`。**禁止多数投票。**

### 2.2 通道优先级（从便宜到贵，取第一个可用的）

| 顺位 | 条件 | 通道 | 成本 |
|---|---|---|---|
| 1 | 页是 `born_digital` | `text_layer` | 0 次模型调用（脚本比对） |
| 2 | 字段有条码/二维码承载（标本号、住院号、报告编号） | `barcode` | 0 次模型调用 |
| 3 | 确定性 OCR 附录**可解析**（非 0 字节、非乱码） | `deterministic_ocr` | 0 次模型调用 |
| 4 | host 有第二个视觉模型 | `alternate_vision_model` | 按页批量，一次核 N 个格子 |
| 5 | 以上都不可用 | `human` | 人工 |
| — | 都做不到 | `reread_channel: none` + `status: needs_human_review` | **不得默认放行** |

### 2.2a `reread_channel: none` 的确切含义

`none` = **「这一次运行里没有第二个通道可用」**，是一个关于**环境**的事实陈述。
它**不是**下面任何一种：

| 不是 | 正确写法 |
|---|---|
| 「二读跑了但读不出来」 | 通道照写，`high_risk_fields[].status: needs_human_review`（`legible: false`） |
| 「确定性 OCR 附录是空的/乱码」 | **无信号**：不出 flag、不进 `discrepancy[]`、**不算二读失败**，继续找下一顺位通道 |
| 「我们打算找人看，但还没看」 | 仍是 `none`。**不得写 `human`**——`human` 断言"人已核对过"，必须有 `human_sample_result.json` 里对应的 verdict 才成立 |
| 「这个字段本来就不用二读」 | `status: not_applicable`，不是 `none` |

`none` 永远伴随 `status: needs_human_review`，并进 `projection_coverage` 与 readiness。
**它不是一个可以被默认放行的中间态。**

### 2.3 确定性 OCR 的三态（永不 veto）

| OCR 输出 | 判定 | 动作 |
|---|---|---|
| 0 字节 / 乱码 / 明显无结构 | **无信号** | 不出 flag、不进 `discrepancy[]`、不算「二读失败」 |
| 可解析，且与转写在高风险字段上**数值级冲突** | **真信号** | 进 `discrepancy[]`，触发二读 |
| 可解析且一致 | 置信加成 | 可置 `reread_channel: deterministic_ocr` |

**OCR 从来不是 veto。** 把「工具失败」当成「两读不一致」，会让难页 flag 成灾，
并把质检噪音推到患者面前——这是本次改造要修掉的具体病灶，不是可讨论的偏好。
host 没装 OCR 工具**不是**跳过二读的理由，要用 §2.2 的其它通道顶上。

### 2.4 裁决与落库（**逐字段**，不是逐行）

二读结论落在 `source_inventory.json` 行的 **`high_risk_fields[]`** 上，**一个高风险字段一条**：

```yaml
high_risk_fields:
  - label: 白细胞计数                      # 逐字照抄段 1 的 label
    status: passed_independent_reread     # passed_independent_reread | needs_human_review | not_applicable
    reread_channel: text_layer            # text_layer|barcode|deterministic_ocr|alternate_vision_model|human|none
    reread_model_id: null                 # 仅 alternate_vision_model 时必填
    readings:
      - {channel: transcribe, value: "3.21"}       # 段 1 主读；channel 枚举见下
      - {channel: text_layer, value: "3.21"}       # 独立通道的第二读
```

**`readings[].channel` 的闭合取值**（schema、`ingest_transcripts.py`、本文件三处必须一致）：
`transcribe`（段 1 主读）| `text_layer` | `barcode` | `deterministic_ocr` |
`alternate_vision_model` | `human`。**没有 `first_read`**（旧名，已废；一律写 `transcribe`），
**也没有 `none`** —— `none` 是 `reread_channel` 的「无通道」取值，不是一条读数；
没有第二通道就只有一条 `readings[]`，不要造一条 `channel: none` 的空读数来凑数。

行级字段是**派生摘要**，不是独立真值：

| 行级字段 | 怎么来 |
|---|---|
| `high_risk_review_status` | 任一条 `needs_human_review` → 行级 `needs_human_review`；全部 `passed_independent_reread` → `passed_independent_reread`；`high_risk_fields[]` 为空 → `not_applicable` |
| `reread_channel` | **主通道**摘要（该行用得最多的那个通道）；逐字段的真值在 `high_risk_fields[].reread_channel` |
| `transcribe_model_id` | 段 1 主读该源所用模型 id（**新增，行级必填**） |

逐字段裁决表：

| 情况 | `high_risk_fields[].status` | 其它 |
|---|---|---|
| 两通道值相等 | `passed_independent_reread` | 写 `reread_channel`；`readings[]` 保留两条 |
| 两通道值不等 | `needs_human_review` | 两读**并列**写 sidecar + `review_flags[]`（`audience: internal_qc`，`category: transcription_disagreement`）；患者摘要该值 `null` |
| 二读读不出（`legible: false`） | `needs_human_review` | 不得回退成「保留第一读」 |
| 无可用通道 | `needs_human_review` | `reread_channel: none`；进 `projection_coverage` |
| 该字段不在清单里且无 trigger | `not_applicable` | 不占二读预算 |

**gate（validator 强制，逐条 ERROR）：**

1. `status == passed_independent_reread` ⇒ `reread_channel != none`；
2. `reread_channel == alternate_vision_model` ⇒ `reread_model_id` 必填**且 ≠ `transcribe_model_id``**
   （同一个模型换个名字写两遍不是独立通道）；
3. `reread_channel == text_layer` ⇒ 该源 `text_layer_kind ∈ {born_digital, not_applicable}`。
   这条门要挡的是 **`embedded_ocr`**——扫描仪自带 OCR 的文本层是概率产物，
   拿它当第二通道等于用一个 OCR 给另一个 OCR 背书。
   `not_applicable`（VCF / DICOM 头 / 时序导出，由确定性工具解码）**必须放行**：
   它的独立性比 born-digital 字符层只强不弱，排除它会把每一个变异、每一个 DICOM 头字段
   都推进人工队列，且换不到任何安全收益（见 `domain-pack.md` §3.3）；
4. `reread_channel == human` ⇒ `human_sample_result.json` 里有该 `(source_id, label)` 的 verdict。
   **没有 verdict 就不许写 `human`** —— 写 `human` 等于宣称"人看过了"。
   无通道时写 **`none`**，不写 `human`。

**未通过通道独立第二读或人工抽查的高风险字段，不进任何患者向已确认事实面。**
这是红线，不是 best-effort。

---

## 3. 人工抽查规则

模型之间互相核对解决不了系统性偏差（同类模型共享同一先验）。人工抽查是唯一
不依赖模型的验证点，**不可被任何自动化替代**。

- **抽多少**：每位患者 **≥3 个字段**，或全部高风险字段的 **5%**，**取较大者**。
  高风险字段总数 < 3 时，全查。
- **抽哪些**（分层，不是随机撒）：
  1. 至少 1 个 `dose` 或 `lab_value` + `unit`（量级错误伤害最大）；
  2. 至少 1 个 `date`（时间线的地基）；
  3. 有分子报告时，至少 1 个 `variant` 或 `vaf`；
  4. 剩余名额优先给 `unreadable_ratio` 最高的页与 `needs_rotation: true` 的页。
- **怎么比**：人直接看 `raw/` 里的原页（或原件），与结构化值逐字比对。
  **不看** sidecar MD——那是被验对象，拿它当标准就是自指。
- **记录拆两份文件**（都在 `raw/_provenance/<run_id>/` 下，**缺一不可**）：

  | 文件 | 谁写 | 内容 |
  |---|---|---|
  | `human_sample_plan.json` | **脚本** | `{run_id, sample: [{source_id, page, label, bbox, transcript_value}], rule}` —— 抽了哪些格子、为什么这么抽 |
  | `human_sample_result.json` | **人** | `{run_id, performed_by, performed_at, verdicts: [{source_id, page, label, verdict: match\|mismatch\|unreadable, note?}]}` |

  **拆两份是判据本身，不是格式偏好。** 一份文件时，"脚本写了抽样清单"和"人真的看了原件"在
  磁盘上长得一模一样——门只能验到"文件存在"，而文件是脚本自己写的，等于自证。
  拆开之后，`result` 里的 `performed_by` / `performed_at` / 每一条 `verdict` 只能由人产生，
  脚本无法伪造出一个合法的 `result`。

  抽样种子 = `sha256(patient_code + sorted(field keys))`，**不含 `run_id`**——
  同一份档案重跑抽到同一批格子，否则重跑就成了"多摇几次直到没人反对"。

- **门（`gate_human_sample`，新增）**：
  1. `human_sample_result.json` **存在**；
  2. 其 `verdicts[]` **覆盖 `plan` 的全部条目**（少一条即未完成，不是"抽样的抽样"）；
  3. `mismatch ≥ 2` → 整体 `needs_human_review`，validator 报 **ERROR「not deliverable」**。
- **失败处理**：抽查发现 1 处 `mismatch` → 该源全部高风险字段回段 1.5 重跑；
  ≥2 处 → 该次运行的感知层结论整体标记 `needs_human_review`，**不得交付**。
- **交付判据**：`human_sample_result.json` 不存在 = 整理未完成。
  Definition of Done 的一行，不是加分项。

---

## 4. 与其它文件的接口

| 文件 | 用本文件的什么 |
|---|---|
| `organizer-prompt-phase1-transcribe.md` §4 | 清单 → `high_risk[]` |
| `organizer-prompt-second-read.md` §0/§2 | 通道独立定义、裁决表 |
| `organizer-prompt-phase2_5-faithfulness.md` | 高风险 100% 复核面 |
| `schemas/source_inventory.schema.json` | `high_risk_fields[]`、派生的 `high_risk_review_status`、`reread_channel`、`transcribe_model_id` |
| `schemas/readiness.schema.json` | `review_flags[].category: transcription_disagreement` |
| `domain-pack.md` | pack 怎么挂载、通用层与域层怎么分 |
| `runtime-bindings/*.md` | host 用哪个通道顶第二读 |
