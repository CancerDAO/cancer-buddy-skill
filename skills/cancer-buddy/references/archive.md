# 怎么读患者档案（patient_dir）

所有 skill 读档案都按这里的方式。档案由 `cancer-buddy-organize` 建立和更新；其他 skill 只读（visit-prep、charts、vault 等只往约定的位置写自己的产物）。

## 1. 找到档案

1. 根目录：`$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`。
2. 根目录下每个 `PT-XXXXXXXXXX/` 是一位患者。`python3 "<cancer-buddy 目录>/scripts/cb.py" patients` 会列出全部档案（路径、alias、一句话病情、更新时间）。
   - 用户给了路径，或当前目录就是某个 `PT-*`，直接用。
   - 有多个 `PT-*`：按 `profile.json` 里的 `alias` 和一句话病情列出来，问用户是哪一位。不要猜。
   - 一个都没有：告诉用户还没有档案，问要不要先把病历整理一下（→ organize）。一般性问题不需要档案，照常回答。
3. `patient_code` 只是存放位置的编号，不证明身份，也不代表有权查看（见 [guardrails.md](guardrails.md) 第 6 节）。

## 2. 读取顺序

1. `profile.json` —— 一句话病情、最新状态、语言。
2. `readiness.json` —— 资料覆盖、资料时效、需要核对的字段。
3. `acute_findings.json` —— 有记录就**最先**告诉用户（见第 5 节）。
4. 和问题相关的**那一个** JSON（检验问题读 `labs.json`，治疗问题读 `treatment_lines.json`……）。
5. 需要引用原文时，才按 `source_refs` 读转写稿里对应的几行。

**不读 `raw/`**（原件，含真实身份信息），也不读 `99_无关文件/` 和 `.work/`。

## 3. 文件一览

| 文件 | 用途 |
|---|---|
| `profile.json` | 首读：身份定位、locale、一句话病情、最新状态 |
| `patient_summary.json` | 诊断、人口学、当前状态的权威汇总（含第二原发 `additional_primaries`） |
| `acute_findings.json` | 急性发现；`findings: []` 表示查过、没有 |
| `molecular.json` | 基因变异、胚系、药物基因组、免疫组化、MSI/MMR/TMB、HLA |
| `labs.json` | 检验值序列，带该次报告的单位、参考范围、原始标记 `report_flag` 和固定词 `flag_normalized`（high/low/normal/critical_high/critical_low/abnormal） |
| `imaging_findings.json` | 每份影像报告按部位逐条的所见原文（含“相仿/未变”的旧病灶和阴性部位）、检查日期、对比片 |
| `treatment_lines.json` | 治疗经过，一个方案的一个疗程一条，带 `status_basis` |
| `timeline.json` / `timeline.md` | 时间线 |
| `comorbidities.json` | 合并症、用药（含给药场景）、过敏 |
| `longitudinal_observations.json` | 有 ≥2 个可比点的时间序列（画图用） |
| `readiness.json` | 资料覆盖、复核提示、资料时效（不是临床评分） |
| `missing_items.json` | 已知缺的文书或缺页（不是检查建议） |
| `source_inventory.json` | 原件 ↔ 转写稿 ↔ 页数 ↔ 哈希 |
| `update_log.json` / `organize_meta.json` | 整理记录、版本和检查结果 |
| `transcription_log.md` | 每个转写任务派了哪些页、页图哈希、转写员说明（页图已删，可从原件重新渲染后比对） |
| `case_text.md` | 带锚点的病情叙事 |
| `review_summary.md` | 给患者看的一页抽检摘要 |
| `INDEX.md` / `AGENTS.md` | 文件清单 / 给 agent 的读取指引 |
| `病情简要总结.html`、`case_summary_versions/` | 一页纸总结及历次快照 |
| `library/index.json` | 患者专属资料库 |
| `share_log.json` | vault 导出记录（接收方、目的、到期、文件） |
| `gap_asks.json` | "要不要补某份资料"的询问记录（同一项最多问两次） |
| `01_…14_/<子类>/…md` | 转写稿（已遮蔽身份信息），抽屉见 [buckets.json](buckets.json)。front matter 的 `exam_date` 是检查/采样日，`doc_date` 是报告日；`evidence: secondary` 是人整理的二手材料，不当事实出处 |
| `15_其他资料/<类型>/…md` | 规则外的材料，全文照样入库 |
| `10_随访与监测/团队交代/` | 治疗团队的书面交代，检索时优先看 |
| `99_无关文件/` `raw/` `.work/` | 不读 |

## 4. 来源层、状态和看不清的字段

- 每条结构化记录有 `provenance_layer`（报告原文 / 患者自述 / 家属自述 / 系统规范化 / 旧档摘录）和 `verification_status`（未核实 / 医生确认 / 有冲突）。转述时说清是谁说的："报告上写着…" 和 "你家属提到…" 不混在一起。
- `disputed`：把各个取值和出处都列出来，不替用户选。
- 转写稿里的 `{?X|Y}` 表示看不清：字面读作 X，也可能是 Y；`{?X}` 表示读作 X 但不确定。对用户说"这里原件不清楚，读作 X（也可能是 Y），建议对照原件或问医生"。
- 转写稿和 JSON 里的 `[姓名]` `[出生日期]` `[医生]` `[病案号]` `[单号]` 是遮蔽后的占位，不要设法还原。
- `labs.json` 里 `value: null` 而有 `candidate_value` 的，是表格没对齐时的未核实读数，不当数值用。
- `readiness.json` 的 `review_flags[].severity`（red/yellow/info）指"这个字段能不能当确定事实用"，不是病情轻重。
- `days_since_latest` 超过 14 天时，提醒一句"最新资料是 X 日的，之后有没有新检查？"

## 5. 急性发现放在最前面

`acute_findings.json` 里 `acuity` 为 `emergent` / `urgent` 的记录，在回答任何问题之前先列出：报告原文 + 检查日期 + 出处，说"这是报告里写到的、需要尽快告知治疗团队的发现"。不解释原因，不判断严重程度，不给处理建议。`verbatim_is_translation` 为真的标"转述，非报告原句"。`advisory`（报告写的复查提示）和 `incidental` 不放进这一段，相关时再提。文件不存在表示"还没检查过"，不等于"没有"。

## 6. 锚点

- 叙事文本里的 `[[src:<相对路径>.md#L<起>-L<止>]]` 指向转写稿的行号；`[[src:conversation:<时间>]]` 指对话中用户提供的信息。
- 结构化 JSON 的 `source_refs: ["<相对路径>.md#L12-L14"]` 同理。行号从 1 起。
- 引用时按锚点读那几行，再按 [citations.md](citations.md) 写成 `〔档案〕文书名 + 日期`。

## 7. 老档案

v1 建的档案文件名和顶层结构相同，按同样方式读。个别 v1 独有文件（如 `review_flags.md`、`.case_summary_data.json`）可以参考，没有也不影响。想让老档案升级成 v2 格式，交给 organize。
