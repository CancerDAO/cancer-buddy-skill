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

### 2.1 时变字段不是冲突（先判这一条，再判 §2）

**冲突 = 同一时点的两个来源说了不相容的话。不同时点说了不同的话，是时间演变，不是冲突。**

先按下表判字段类别，**时变字段跨不同来源日期取值不同一律不标 `disputed`**：

| 类别 | 字段 | 跨来源取值不同时 |
|---|---|---|
| **时变** | `demographics.age`、`demographics.height_cm`、`demographics.weight_kg`、`demographics.ecog`、`current_status.*`、labs 面板值、生命体征 | 正常演变。各值带自己的 `_as_of` 并列保存，快照字段取 `_as_of` 最新者，**不标 disputed** |
| **时不变** | `demographics.sex`、`diagnosis.primary/histology/icd10/diagnosed_at`、`birth_year`、既往治疗线的历史事实、已出具的分子结果 | 走 §2，标 `disputed` |

时变字段仍要标 `disputed` 的三种情形（**只有这三种**）：

1. **同一 `as_of` 日期**内两个来源给出不同值；
2. **与时间跨度矛盾**：年龄倒退（2023 年报告 60 岁、2026 年报告 55 岁），或增量远超时间跨度；
3. 值本身可疑（超范围、OCR 明显误读）→ 走忠实度 flag，不是冲突。

**年龄自洽判据**：两条观测 `(a₁, t₁)`、`(a₂, t₂)`，`t₁ < t₂`，年跨度 `Δ = (t₂ − t₁)/365.25`。自洽条件为 `a₂ − a₁ ∈ [⌊Δ⌋ − 1, ⌈Δ⌉ + 1]`。**±1 的容差不可收紧**——它吸收的是生日是否已过、周岁/虚岁口径、以及报告写的是就诊时年龄这三种正常来源差异；收紧就会把正常增龄重新误判成冲突。仅当落在该区间外才按情形 2 标 `disputed`。

体重/身高/ECOG 同理：只对比同 `_as_of` 的值；不同日期的差异是状态变化，写进 `longitudinal_observations.json`（`obs_type: vital` / `clinician_function_score`），不进冲突队列。

### 2.2 年龄字段怎么写

- 每个说了年龄的来源，各写一条 `age_observations[]`：`{value（原文年龄，不重算）, as_of（该来源的报告/采集日期）, source_ref}`；来源明说周岁/虚岁才填 `age_basis`，没说就是 `unspecified`。
- `age` = `age_observations` 中 `as_of` 最新的那条的 `value`，`age_as_of` = 该条的 `as_of`。**`age` 是快照不是现龄，永远不要把它推算到今天。**
- 来源没给报告日期 → 该条年龄进 `age_observations` 但 `as_of` 无法确定时，不写这条，改记 review flag（无锚年龄不可用）。
- **`birth_year` 只在能被来源钉死时才写**，两条路径：
  1. 来源含完整出生日期 → 取年份写入，**其余部分不落盘**（DOB 是准标识项，见 `pii-rescan-prompt.md`）；
  2. 仅有年龄快照 → 单条快照 `(a, t)` 只能推出 `{year(t)−a−1, year(t)−a}` 两个候选，**禁止直接相减得出一个年份**；只有 ≥2 条不同月份的快照交集唯一时才写。
  - 交集不唯一或无法确定 → `birth_year: null`。宁可没有，也不要伪精度。
- `birth_year` 的 `provenance_layer` 是 `system_normalized`，永不覆盖来源原文年龄。

## 3. 禁止推断

- 不把 TNM 映射到其他分期系统；
- 不从功能描述生成 ECOG；
- 不从影像/标志物生成 CR/PR/SD/PD、进展或疗效；
- 不把维持、巩固、围手术期自动算成新线；
- 不把患者确认当临床核实；
- 不按通用阈值生成器官限制、严重度或治疗资格。

## 3b. 桶内命名铁律（G1 一致性门的前置）

- 桶内文件名的**报告类型段必须逐字取自该 sidecar 自己的报告类型声明**（`报告类型/document_title/document_type/report_type` 字段原文，或其所属别名组的规范名，别名组见 `report-type-aliases.json`）。绝不从"同日常见检验组套"、相邻文件或任何 sidecar 之外的来源推断名字——批量命名串位（内容是肿瘤标志物的 sidecar 被命名"凝血功能筛查"）正是这样发生的。
- sidecar 没有可用的报告类型声明（缺失或仅有 `laboratory_report` 之类泛型容器词）→ 该文件**不得**冠以具体报告类型名，落待归类（pending-classification）路径。
- 逐 sidecar 输出命名 echo 映射表 `naming_echo.json`：`{"entries":[{"source_id":"...","report_type_verbatim":"<sidecar 原文>","chosen_path":"<桶内相对路径>"}]}`。这是自证产物：宿主在落盘前用 `scripts/gates/gate_name_content.py`（确定性，零 LLM）逐行核验文件名↔sidecar 一致性，violation 不得以当前名落盘。

## 4. 结构化产物

按 `schemas/` v2 写 `patient_summary.json`、`timeline.json`、`treatment_lines.json`（治疗事件）、`labs.json`、`molecular.json`、`comorbidities.json`、`longitudinal_observations.json` 和兼容文件名 `missing_items.json`。

所有 worker 使用同一来源引用合同：结构化 JSON 的 `source_refs[]`（以及
`longitudinal_observations.json` 的单数 `source_ref`）只写安全的 `01_…14_` 桶内相对
sidecar 路径；JSON 可以引用整个文件，也可以保留 `#L…`/`#section` fragment。正式
Markdown 的每条事实必须写 `[[src:<相对路径>#<fragment>]]`，文件引用不得只有 path。
禁止绝对路径、反斜线、`.`/`..`、`raw/`、`ocr/`、`99_…` 和不存在的目标；详见
`schemas/anchor-contract.md`，最终由 `validate_structured_outputs.py` 机械校验。

`source_inventory.json` 必须使用 `source_inventory_v2`，逐 content unit 记录受保护的 `raw_path`、sidecar、读取方式、抽取器名称/版本/原始输出引用、LLM 的受限角色和高风险字段独立复读状态。缺少这些字段不得降级成无来源清单。

`missing_items.json` 只输出现有文档档案缺口。checklist 的癌种 slug 不确定时用 unknown，不做 closest-fit。

## 5. 覆盖状态

`readiness.json` 只记录 `documentation_coverage` 和来源/忠实度 flags，不给 A–F 临床 readiness 分数。资料不完整不阻止一般教育；只限制受影响的个体化内容。

## 6. 产物验证

运行 JSON schema、来源锚点、hash、PII、字段分层和冲突不可覆盖检查。验证失败则不生成患者摘要；错误进入 review queue，不让模型自行修正临床值。
