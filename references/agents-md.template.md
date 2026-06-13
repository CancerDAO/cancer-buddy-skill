# 患者档案 · AGENTS.md

<!--
  本文件由 cancer-buddy-organize 自动生成（填充模板 references/agents-md.template.md，repo-root 共享契约，与 patient-profile-schema.md 并排，被 cancer-buddy 家族 + vmtb 共用）。
  它是 agent-facing 的**索引 / 召回指针**，不是数据本身，也不是给患者看的。
  只注入两个占位符，且都是从 profile.json **逐字复制**、不重新合成（占位符写法见下方正文）：
    patient_code        ← profile.json.patient_code
    one_line_condition  ← profile.json.summary.one_line_condition（临床实体 verbatim）
  静态部分（路由表 / 下钻规则 / 硬规则）所有患者共用，改动只改这个模板。
  说明语言为 skill 运行语言；模型可用任意语言阅读，注入字段保持 profile.json.locale 原文。
-->

> 回答任何病情问题前，先按下方路由表 `read` 对应文件，再作答。这是一个已整理好的患者档案目录。

## 患者身份
- patient_code: `{{patient_code}}`   ← 本目录锚定的唯一患者
- 一句话病情: {{one_line_condition}}
- 档案根目录: 本文件所在目录
- 就绪度: 见 `readiness.json`（score / grade / blocking_gaps）
- **全档索引**: `source_inventory.json`（每份原始材料 → sidecar_path → bucket_path 的总映射）；`INDEX.md`（人读清单：file_id / 桶 / 类型 / 日期 / 机构 / 置信 / MD / Raw原件 / 页码）

## 检索分两层，逐层升级

**第 1 层 · 已消化层（顶层 JSON / 总结）—— 默认先查这里，按路由表：**

| 患者问的 | 先读 | 取哪个字段 |
|---|---|---|
| 得的是什么 / 分期 / 组织学 | `patient_summary.json` | diagnosis{primary, histology, stage, metastasis_sites} |
| 现在的方案 / 疗效 / ECOG | `profile.json` | latest_status{regimen, response, ecog, as_of} |
| 治疗史 / 几线 / 换过什么 | `treatment_lines.json` | lines[]{line, regimen, best_response, reason_for_change} |
| 基因 / 突变 / IHC / MSI / TMB | `molecular.json` | variants[] / ihc[] / msi_mmr / tmb |
| 化验值 / 某指标趋势 | `labs.json` + `longitudinal_observations.json` | panels[].values[] / observations[] |
| 什么时候做了什么 / 时间线 | `timeline.md`（机读用 `timeline.json`） | events[]{date, category, title} |
| 合并症 / 长期用药 / 过敏 | `comorbidities.json` | conditions[] / medications[] / allergies[] |
| 还缺什么检查 / 该补什么 | `missing_items.json` | missing[]{item, priority, reason} |
| 给个整体小结 | `病情简要总结.html` / `case_text.md` | 全文 |

**第 2 层 · 颗粒层（子文件夹 sidecar 原文）—— 出现以下任一情况，必须下钻二次确认：**
- 顶层 JSON / 总结**找不到**患者问的那条信息；
- 顶层信息**模糊、笼统，或与患者描述对不上**；
- 患者**明确质疑或要看原始依据**；
- 多个文件之间**互相矛盾**（需交叉核对原件）。

下钻方法（沿索引走，不要瞎翻目录）：
1. 取顶层字段里的 `source_refs[]` 锚点（形如 `06_分子与组学/ngs_report.md#L20-L34`）→ 直接 `read` 那个 sidecar 的对应行段；
2. 若该字段无 source_refs，或要查全某个域，打开 `source_inventory.json`，按 `bucket_path` 过滤出该域所有 `sidecar_path`，逐个 `read`；
3. 14 个域目录：`01_身份与基础信息` / `02_既往史与家族史` / `03_病程与叙事文书` / `04_诊断与分期` / `05_影像` / `06_分子与组学` / `07_检验` / `08_治疗` / `09_手术与操作` / `10_随访与监测` / `11_会诊与转诊` / `12_心理社会与支持` / `13_行政与财务` / `14_患者自管补充`。

> 下钻取到的内容仍要**逐字引用 + 附 source_refs 锚点**。两层都查不到，才判定"档案中无此信息"。

## 硬规则（不可违反）

1. **逐字引用 + 溯源呈现**：临床事实（分期 / 剂量 / 分子标记 / 检验值）必须取自档案原文，事实后带来源。优先用行内角标 + 末尾脚注呈现（完整格式见 cancer-buddy `SKILL.md`「来源引用」节）；角标指向的锚点**复用该事实底层 JSON 的 `source_refs[]`，不另造一套**。脚注 label 的日期 / 类型 / 机构从 `INDEX.md` 对应行取；会话锚（患者口述）写 `日期·患者口述` 且无文件路径；`INDEX.md` 查不到机构就省略，**绝不编造机构名**。
2. **禁止编造 / 禁止 LLM 合成证据**：两层检索都没有的，就说"档案里没有这条，需要补充"，**绝不推测或自行生成临床事实**。
3. **永不读取** `raw/`（未脱敏原件保险库）和 `99_无关文件/`（无关文件）—— 它们不是合法锚点目标。只读已脱敏的结构化层与 bucket sidecar。
4. **不做诊疗决策**：可以整理、解释患者自己的档案，不给治疗建议、不替代医生。需要临床判断时引导去主诊医生 + 专业流程（mtb-lite / vmtb / trial-match 等）。
5. 数据已脱敏（PII 已替换为 `[PII_MASKED]`）；不要尝试还原任何个人信息。
