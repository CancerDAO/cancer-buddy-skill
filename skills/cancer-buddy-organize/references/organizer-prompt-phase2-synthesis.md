# Phase 2：来源分层综合

Phase 2 将已复核 sidecar 组织成当前版本的 schema（v2.1 契约，版本号见 §5）。它不诊断、不重新分期、不判断疗效、不推断 ECOG、不计算治疗线、不决定检查适应证。

## 0. 你是谁、写什么

你是 Phase 2 worker，标识为 Call parameters 里的 `worker_id`。**档案里的结构化 JSON 只能由
Phase 2 worker 与 段C worker（对话增量，`conversation-incremental-prompt.md`）写**；编排者不会、也不得替你补写。你负责：分类与搬迁 sidecar、`source_inventory.json`、
`INDEX.md`、`timeline.md`、`case_text.md`、`profile.json`、`readiness.json`、`review_flags.md`、
`review_summary.md`、全部结构化 JSON（含 `acute_findings.json`）以及本次运行的 `update_log.json` 条目。
你不改 sidecar 正文（搬迁不改字），不渲染 HTML，不生成 `AGENTS.md`。`raw/` 是 Phase 1 与原件的区域，你在其中
只做两件事：写 §4.5 的 `raw/_SIDECAR_MAP.md`，以及 §4.0/§8 把旧产物移入 `raw/_legacy_<ts>/`；其余一律不写（需要
跑脚本的中间文本走管道，§5.1）。
**`<skill_dir>` 在运行期只读**：不得写、改、删其下任何文件（包括 `search_replace`、`sed -i`、`rm`、在其中新建脚本）；发现技能缺陷（脚本报错、规则互相矛盾）→ 停在该步，写进返回 JSON 的 `skill_defects`，不自己修。

**行号**：锚点 `#L<n>` 的行号按校验器的算法——Python `str.splitlines()`——计。sidecar 里有换页符（`\f`）等
特殊换行时，`cat -n` / `head` 的行号会比它少；这类文件（校验器报 `line_breaks: … form feeds` 的旧 sidecar）用
`python3 -c 'import sys;[print(i,l) for i,l in enumerate(open(sys.argv[1],encoding="utf-8").read().splitlines(),1)]' <sidecar>`
读行号。

**写盘节奏**：编排者在 **10 分钟无新文件写入或连续 30 次只读工具调用** 时终止你并重派。“只读调用”= 没有在
`<patient_dir>` 下写出或修改任何文件的工具调用（读文件、列目录、grep、只打印的脚本）；写文件、`mv`、追加
`.rename_plan.json`、运行会写文件的脚本都算写入。所以按 §4 逐个读 sidecar、每读一个就把它的计划条目追加进
`.rename_plan.json`；复核（§4.4）用一次 `head -n 30` 批量读多份并随即写回 `reviewed: true`；§5 每写完一个领域就
立即写出那份文件，不要把全部 sidecar 读完再统一动笔。本提示词自包含，不必先通读 skill 的其他文件；需要查规则时只查
被点名的那一节（如 `acute-findings.md`）。读本提示词与被点名的参考文件不计入“连续只读”次数（编排者按路径区分）。**不读 `<skill_dir>/scripts/*.py` 源码**（校验器在内）：只运行脚本、看它打印的结果；要查规则只查本提示词或被点名的那一节。

Call parameters：`skill_dir`（本 skill 目录的绝对路径——你的工作目录不是它：文中的 `scripts/…`、`references/…`、
`schemas/…` 都在它下面，运行脚本写 `python3 "<skill_dir>/scripts/<脚本>"`）、`worker_id`、`patient_dir`、
`phase1_summary`（各 Phase 1 worker 的返回 JSON）、
`dispatch_log`（编排者记录的派发/终止/重派事件；上下文压缩后以 `raw/_dispatch_log.jsonl` 为准，两者合并读）、`run_mode`（`full` | `legacy_upgrade`（§4.0）| `legacy_phase2_only`（§4.0：旧版档案上只重跑 Phase 2，不升级）| `incremental` |
`upload_reconciliation`（§12）| `faithfulness_patch`（§11）| `relevance_disposition`（§12）| `pii_remask`（§13））、`as_of_run_date`
（本次运行的**本地**日期 `YYYY-MM-DD`；本次 `update_log.json` 条目的 `at` 写 UTC 时间，所以两者的日期可能差一天，
校验器容许 ±1 天；不能改成最新资料日期来把天数归零）、`input_manifest`（`scripts/inventory_hash.py` 对本次输入
的结果）、`locale`、`prior_archive_authorized`（布尔）、`redispatch`（布尔：本 worker 是否为
超时后的重派，§4.0）、`user_decisions`（§12；上传对账时是用户对差异卡逐项的选择：你照选择执行，并在
本次 update_log 条目的 `note` 中逐项记录“选择 + 句柄 + 确认原话（遮蔽个人信息后）”）。

## 1. 来源层

每个临床事实必须标：

- `source_reported`: 正式报告/医嘱/临床记录原文；
- `patient_reported` / `caregiver_reported`: 对话或自填；
- `system_normalized`: 验证后的附加标准化字段，永不覆盖原文；
- `prior_archive`: 经用户明确授权引用的既往整理档案摘录（原件不在本次资料中），只能用于既往史（§5.9）；
- `verification_status`: `unverified|clinician_verified|disputed`。

## 2. 冲突

不同来源冲突时并列保留，不按“病理优先/最新优先/用户选择”自动裁决。只有正式更正文件或授权临床人员签认才能解决。所有旧值和锚点保持不可变。flag 的 `current_source_values[]` 必须列出**全部**互不相容的读法，每种一条，包括“某通道未读出此处”（`value: null`）。同一处的不同通道读数各写一条并带
`channel`（通道值同 phase1 §2，如 `{"value": "4L?", "source_ref": "…#L12", "channel": "deterministic_ocr:tesseract"}`），
否则几条读数引用同一行时分不清谁读的；来自不同文书的读法可以不写 `channel`。

**一条 flag 只针对一个受影响字段**（一个 `affected_field`，各自分级）：几个字段都不确定就各写一条；旧档案里
一条 flag 混了几个字段的（如“某站别 + 某日期”“某标志物 + 某单位”），重写时按字段拆开：拆出的 flag 接着现有最大编号
取新 `RF-nnn`，`issue` 写“拆自 RF-00x”。旧 flag 说明文字里**顺带**提到的字段（“另有未决项”），逐个按下面两条分流：
1. **高风险字段**（phase1 §2 清单：免疫组化标志物与判读、药名、日期、诊断名、淋巴结站别、分期、分子结果、剂量等）
   **只要能在某份 sidecar 里定位到**（找得到那一行），就**一律**单独成 flag，照 §6.1 分级——不论旧 flag 是正式列出
   还是顺带一提；
2. 只有**同时**满足“只是顺带提到”**且**“在任何 sidecar 里都定位不到对应字段”的，才不成 flag，写进
   `readiness.json.warnings[]`（写明来自哪条旧 flag）；非高风险字段能定位时按 §6.1 照常成 flag。
姓名、住院号、病理号这类已遮蔽的身份编号之间的不一致不写 flag（它们不是临床字段，也不能写出读数）。

### 2.1 时变字段不是冲突（先判这一条，再判 §2）

**冲突 = 同一时点的两个来源说了不相容的话。不同时点说了不同的话，是时间演变，不是冲突。**

先按下表判字段类别，**时变字段跨不同来源日期取值不同一律不标 `disputed`**：

| 类别 | 字段 | 跨来源取值不同时 |
|---|---|---|
| **时变** | `demographics.age`、`demographics.height_cm`、`demographics.weight_kg`、`demographics.ecog`、体能状态原文（PS/KPS 等）、`current_status.*`、labs 面板值、生命体征 | 正常演变。各值带自己的 `_as_of` 并列保存，快照字段取 `_as_of` 最新者，**不标 disputed** |
| **时不变** | `demographics.sex`、`diagnosis.primary/histology/icd10/diagnosed_at`、病灶部位与**侧别**（左/右）、`birth_year`、既往治疗线的历史事实、已出具的分子结果 | 走 §2，标 `disputed` |

时变字段仍要标 `disputed` 的三种情形（**只有这三种**）：

1. **同一 `as_of` 日期**内两个来源给出不同值；
2. **与时间跨度矛盾**：年龄倒退（2023 年报告 60 岁、2026 年报告 55 岁），或增量远超时间跨度；
3. 值本身可疑（超范围、OCR 明显误读）→ 走忠实度 flag，不是冲突。

同一页的两份打印件或照片，一份列出某项、另一份没有列出（如一份的合并症有第 3 条、另一份到第 2 条为止）：这是
“一处列出、一处未列出”，不是两种不相容的说法——两份都按原文保留，写 `kind: conflict`、`severity: yellow`
（§6.1“其他同时点不一致”），不写 red，也不补齐缺的一份。

**年龄自洽判据**：两条观测 `(a₁, t₁)`、`(a₂, t₂)`，`t₁ < t₂`，年跨度 `Δ = (t₂ − t₁)/365.25`。自洽条件为 `a₂ − a₁ ∈ [⌊Δ⌋ − 1, ⌈Δ⌉ + 1]`。**±1 的容差不可收紧**——它吸收的是生日是否已过、周岁/虚岁口径、以及报告写的是就诊时年龄这三种正常来源差异；收紧就会把正常增龄重新误判成冲突。仅当落在该区间外才按情形 2 标 `disputed`。

体重/身高/ECOG 同理：只对比同 `_as_of` 的值；不同日期的差异是状态变化，写进 `longitudinal_observations.json`（`obs_type: vital` / `clinician_function_score`），不进冲突队列。

### 2.2 年龄字段怎么写

- 每个说了年龄的**原件** sidecar，各写一条 `age_observations[]`：`{value（原文年龄，不重算）, as_of, source_ref, age_basis}`。
  同一页的重复照片（同日期、同文字）与 §2.3 同一口径：算一个出现处，写一条（引 `file_id` 较小的那份）。
  `as_of` 一律取该 sidecar 的文件名日期（即该文书的出具日期，§4.2；病理只印收到日期、影像分检查与报告日期的，同样取
  文件名日期），`age_basis` 总是写：来源明说周岁/虚岁照写，没说写 `unspecified`。对话或自述里的年龄不进
  `age_observations`（段C 只写时间线自述事件）。
- `age` = `age_observations` 中 `as_of` 最新的那条的 `value`，`age_as_of` = 该条的 `as_of`。**`age` 是快照不是现龄，永远不要把它推算到今天。**
- 来源没给报告日期 → 该条年龄进 `age_observations` 但 `as_of` 无法确定时，不写这条，改记 review flag（无锚年龄不可用）。
- **`birth_year` 只在能被来源钉死时才写**，两条路径：
  1. 来源含完整出生日期 → 取年份写入，**其余部分不落盘**（DOB 是准标识项，见 `pii-rescan-prompt.md`）。Phase 1 会把
     出生日期遮蔽成 `[PII_MASKED]`，所以这条路径通常用不上——sidecar 里看不到出生日期就走路径 2，不去 `raw/` 找；
  2. 仅有年龄快照 → 单条快照 `(a, t)` 只能推出 `{year(t)−a−1, year(t)−a}` 两个候选，**禁止直接相减得出一个年份**；只有 ≥2 条不同月份的快照交集唯一时才写。
  - 交集不唯一或无法确定 → `birth_year: null`。宁可没有，也不要伪精度。
- `birth_year` 的 `provenance_layer` 是 `system_normalized`，永不覆盖来源原文年龄。

### 2.3 体能状态逐字

- 医生书写的体能评分（“PS=2”“ECOG 2”“KPS 70分”“体力状况评分 2 分”）逐字写入
  `patient_summary.json.demographics.performance_status_verbatim[]` 与 `profile.json.demographics`
  同名数组：`{text（原文逐字）, as_of（该页日期）, scale_label, source_ref}`。每个出现处一条，
  不同日期都要写，不只写第一次；同一页的重复照片（同日期、同文字）算一个出现处，写一条（引 `file_id` 较小的那份）。
- `scale_label` 只按原文标签机械填写：`PS` | `ECOG` | `KPS` | `Zubrod` | `unlabeled`（原文有分值但
  没写量表名）。**不换算量表**：“PS=2”不写成 ECOG 2，“KPS 70分”不写成任何 ECOG 值。
- 条目可选 `provenance_layer`：本次原件的条目省略它（即沿用 demographics 块的来源层）；旧档案摘录（§5.9）里的体能陈述
  （如“ECOG 1”）只能作为 `provenance_layer: prior_archive` 的条目登记（`source_ref` 指摘录 sidecar 的行），
  它是既往记录，不是当前体能：`demographics.ecog`、`latest_status.ecog` 永不取它。摘录里的体能陈述不论原作者是谁都
  按这一条写；它的 `as_of` 取摘录所引旧档案 sidecar 的文件名日期（摘录行写了“旧档案 `…/2029-05-20_…md#L9`”就取
  2029-05-20），摘录没引到带日期的旧 sidecar 就写 null——不写摘录生成日期。
- `demographics.ecog` / `latest_status.ecog` 仍只收原文明写 “ECOG” 的临床来源；其余为 null。
- 有体能条目时同时逐日写 `longitudinal_observations.json`（`obs_type: clinician_function_score`，
  `metric` 用原文标签，如“PS（原文未注明量表）”）；没有就不写这份条件文件。只写本次原件的、`as_of` 为日期的条目：
  `as_of: null` 的条目（它的 `timestamp` 必填、无从填写）不写进时序，**`provenance_layer: prior_archive` 的条目一律
  不进当前时序**（它是既往记录，只留在 `performance_status_verbatim[]`）；这两种都不另写 warning。校验器核对时序里
  没有引旧档案摘录的条目。

### 2.4 患者自述与原件并列（`conflict_group`）

患者/照护者自述与原件对同一事实（诊断时间、转移部位、分期、方案、检验值）说法不一时，两条事件都写进
`timeline.json`，共享同一个 `conflict_group`（`CG-001` 起），`provenance_layer` 各自如实；
`timeline.md` 两行都注明组号并尽量相邻（按时间排序相隔较远时不强行挪动，在两行各写“见 CG-001”）；
`readiness.json` 加一条 `kind: conflict` 的 flag，`issue` 写明组号。**两份原件**对时不变的事实（诊断、组织学、
既往治疗史）说法不相容时，同样可以用 `conflict_group` 把两条事件并列，flag 按 §6.1 的原件冲突行分级。
自述中的数值（如“某标志物约 80”）只保留在 `patient_reported` 层，**不得**写进任何检验单对应的
`labs.json` 行，也不得用来补齐检验表。

### 2.5 同一对象的跨页用字对账

同一标本、同一日期、同一编号在多页出现时，把各页读法放进同一条 flag，引用全部 sidecar 行。“他页”只算：
同一份文书的另一页或另一张照片，或针对**同一标本**（同一标本号/同一次操作的同一种标本）的另一份报告。“同一份
文书”按检查/文书身份判定，与 `acute-findings.md` §2.2 同一个定义（同一模态、同一次检查或同一编号、同一机构，或
sidecar 写明几页同属一份）：旧档案里同一次检查的几页以不同日期命名，仍是同一份文书的另一页。医生在后来的
病历里照抄的报告结论、同一站别同日的另一种标本（如细胞学穿刺与组织活检）、另一份文书重复的同一句话都**不算**
他页清楚读数（`cross_doc_supported: none`），它们不是对同一对象的独立读取；
一页有 `[OCR_UNCERTAIN:U-nnn]`、另一页有清楚读数时，写 `cross_doc_supported`：拿清楚读数与不确定处
**每个通道的读数和每个候选**比较（读数里的 `?` 可匹配任一字符），等于其中任一个 → `supported`，与全部读数和
候选都不相容 → `contradicted`（§6.1 → `red`），引用写进 `refs`。**“清楚读数”按受影响的那个字段算，不按整行算**：
他页上**这个字段**（与本处 token 所覆盖的同一处文字）没有不确定 token、且至少一个通道读出了它，就是清楚读数——同一行
别处另有一个不确定字不影响它；他页这个字段本身也带 token，或各通道都没读出这一句，就不是清楚读数（`none`）。两页
各在不同字段上有一个不确定字时，可以互为对方那个字段的清楚读数。`kind: conflict` 的 flag 也可以写
`cross_doc_supported`（例如同一份报告的另一张照片与其中一方的读法相同），同样只是旁证。
这是旁证记录：不裁决、不把清楚页的读法抄进不确定页，结构化层不得出现“一处写成确定值、另一处写成
不确定”的不对称——两处都按各自原文写，并共享这条 flag。

## 3. 禁止推断

- 不把 TNM 映射到其他分期系统；
- 不从功能描述生成 ECOG；不把 PS/KPS 换算为 ECOG；
- 不从影像/标志物生成 CR/PR/SD/PD、进展或疗效；
- 不把维持、巩固、围手术期自动算成新线；不按记录条数或时间顺序计算线次；
- 不把患者确认当临床核实；
- 不按通用阈值生成器官限制、严重度或治疗资格。
- 急性发现登记（§5.5）是来源用词归档，按固定表取 `acuity`，不是严重度判断，不改变治疗，不替代主诊团队。

**不确定字段不得作为推理前提。** `kind: document_intent` 且 `resolution_status: unresolved` 的字段、
以及含 `[OCR_UNCERTAIN:U-nnn]` 的字段，不得作为分期、病理、治疗推理的前提：不据此写
`current_status`、诊断或分期的确定值，不据此构造“另一种分期/另一种诊断”的情景。文本型字段（标签、
站名、方案名、诊断原文）写“字面读数 + token”原样，让不确定性随记录流向下游；数值型字段（检验值、
剂量数值、VAF）写 `null`，原串放 `raw_value` 或说明字段；同时在 `readiness.json` 写 flag，列出各通道
读数并用 `uncertain_ids` 指向 sidecar 条目。sidecar 里的候选只可在 flag 的 `issue` 中作为“可能的
读法”提及，永远不进入结构化值位。

**一个 token 只遮住它覆盖的那一段**（按受影响的那个字段算，不按整行算，与 §2.5 同一口径）：同一行里别的字段两读一致，
就照常写确定值——“PR（部分缓解）”读得清、同一行的日期带 token，疗效照写，日期另记；不因同行别处有 token 就把整条记录或
别的字段连带置 null。`patient_summary.diagnosis` 的 `primary` / `histology` / `stage` 与 episode 的 `regimen` 带 token 时，
字段保留“字面 + 它自己的 token”，另写 `alt_readings[]`：每条 `{field, uncertain_id, source_ref, channel, text}`，放另一个
通道对同一段的读数（`channel` 取该条目 `readings[]` 的通道值）与词表 `high` 候选（`channel: "lexicon:<词表名>"`）。
`alt_readings` 永远只是读法：不升格为字段值，不参与 `one_line_condition`。校验器核对：`alt_readings` 所指字段不为 null、
带着该 token，`source_ref` 所指行上有该 token。

## 4. 归档：分类、写前桶计划与搬迁

### 4.0 开工前：旧档案升级与重派续做

- **旧档案升级**（`run_mode: legacy_upgrade`，编排者在本轮之前的旧版档案——没有 `schema_version: "1"` 的
  `update_log.json`——上首次运行时传入；它总是与 Phase 1 对本档案全部原件的重新转写一起进行）：
  在任何分类与搬迁之前，把旧产物整体移到 `<patient_dir>/raw/_legacy_<YYYYMMDDTHHMMSS>/`（`mv -n`，
  不删除；放在受控的 `raw/` 里，因为旧的 `INDEX.md`、`source_inventory.json`、`.rename_plan.json`、旧日志和
  旧 sidecar 头部可能带原上传文件名，移到根目录其他位置就脱离了 PII 复扫，而 `raw/` 不导出、以 `_` 开头的
  子目录也不会被 `inventory_hash.py` 当作原件）：全部 `01_`–`14_` 桶、`update_log.json`，以及 §5–§7 会重写的根目录产物（`INDEX.md`、`case_text.md`、
  `timeline.*`、`profile.json`、`patient_summary.json`、`readiness.json`、`review_*.md`、`source_inventory.json`、
  各结构化 JSON、`.rename_plan.json`、`.phase1_sources.json`）。**例外**：各桶中的 `conversation_notes/` 是段C 写入的对话记录、没有 `raw/` 原件，移走后
  立即按原相对路径搬回；`raw/`、`library/`、`99_无关文件/`、`case_summary_versions/`、`gap_asks.json`、
  `raw/_identity_denylist/` 与旧的根目录 `.identity_denylist.json` 不动。之后按全新运行处理本次 sidecar（它们由 Phase 1 从本档案 `raw/` 重新转写，
  头部是新契约），并从旧 `profile.json` 带回 `alias`（用户设定，永不重新生成），从旧 `timeline.json` 与
  `patient_summary.json` 带回以 `conversation:` 锚点登记的自述记录：内容与来源层照抄，**形状按当前 schema 规整**——
  补上 `conflict_group`、`acute_finding_id`（没有就 null），当前 schema 没有的键（如 `speaker_role`、`reported_at`、
  `source_ref`）并进 `detail` 一句（“陈述者：照护者”），不丢内容也不改层级；`event_id` 与本次新事件不重号。旧档案里的
  其他内容不作为本次来源。
- **旧版档案上的其他运行不升级版本**：`run_mode` 不是 `legacy_upgrade`、而档案仍是旧版（`readiness.json` 不是
  `2.1`，也没有 `organize_meta.json`）时——例如 `legacy_phase2_only`、`faithfulness_patch`——你
  改写的每份结构化文件都**保持它原来的版本号**，不要把任何一份升到当前版本：只升一部分会把整个档案切换成当前
  契约，其余没重写的旧文件与没有 12 键头部的旧 sidecar 就全部变成校验错误。同理，**不新建本契约的标记**：
  v1 形状（带 `workers[]`）的 `update_log.json` 条目与 `organize_meta.json` 是当前契约的标记，写出任何一个，校验器
  就按当前契约判整份档案（`validate_structured_outputs.py --generation <patient_dir>` 列出它看到的标记）。
  **`acute_findings.json` 例外，每次都写**：它是安全面、不是契约标记，旧版档案上只重跑 Phase 2 也照 §5.5 写出
  （`schema_version: "1"`，逐份报告登记）。旧版档案上每条发现的 `timeline_event_id` 写 null、不往旧 timeline 加
  `acute_finding` 事件（事件随 `legacy_upgrade` 补上）；校验器照样严格核对它的 schema、固定表、引文与日期，只有时间线
  链接在旧版档案上不要求。返回 JSON 照常报 `acute_findings_total` 与 `acute_findings_urgent`（§10），编排者据此在
  Step 7.5 先展示。旧日志也不转换（§8），所以必须写日志条目的
  运行（`relevance_disposition` 的删除与移回、上传对账）在旧版档案上不执行，返回给编排者先做升级。旧版档案
  要进入当前契约，只有 `legacy_upgrade` 一条路（Phase 1 全部重新转写 + 本提示词全量运行）。
  **旧版档案上只重跑 Phase 2（`run_mode: legacy_phase2_only`）时怎么做**（没有 Phase 1；编排者只在旧版档案、**没有新文件**、
  而用户暂不做一次性重新转写时选它，SKILL.md「Incremental and update runs」）：
  - §4.1 的头部检查、§4.3–§4.5 的分类与搬迁都不做：sidecar 原地不动、不改名（旧文件名里的机构名随锚点保留）；
    不把任何旧 sidecar 列进 `missing_sidecars`。不改 sidecar 正文（旧 sidecar 里的处理说明留到 `legacy_upgrade` 重新转写）。
    §4.6 的 `source_inventory.json` 与 §7 的 `INDEX.md` 不重写（没有搬迁，清单与索引照旧）；§5 各领域、§6 `readiness.json`、
    §7 的 `case_text.md`、`timeline.md`、`review_summary.md`、`review_flags.md` 照规则重写。
  - **旧档案摘录只凭校验器认得出的标记使用**：一份 sidecar 在 `既往档案摘录` 子桶里、或旧 `source_inventory.json` 行已是
    `source_kind: prior_archive_digest`、或头部写 `SOURCE: prior_archive_digest`（三者之一），它的事实才照 §5.9 标
    `provenance_layer: prior_archive`。没有这三种标记、只是内容看起来像旧档案摘录的 sidecar，你不能替它补标记（不移动、
    不改头部、不改清单行），它的事实也**不写进**任何结构化记录——既不标 `prior_archive`（校验器认不出，会报无摘录来源），
    也不标 `source_reported`（那会把摘录当成本次原件）；同一事实另有本次原件支持时只引原件。这里的“不写进”只约束你
    从这份 sidecar **新取**的事实；**旧结构化文件里已经有**、而本次只有这份未标记摘录支持的值（如只在旧 `molecular.json`
    与这份摘录里的突变）按下一条 `legacy_value_unsupported` 的规则**保留**——那条规则优先，任何旧值（分子结果尤其）都不因
    摘录未标记而静默消失：值与旧记录的 `source_refs` 照旧，写 `legacy_value_unsupported` flag，`current_source_values` 引这份
    摘录的那一行，`issue` 写“旧版结构化文件中的值，仅见于未标记的旧档案摘录，等 legacy_upgrade 核对”。校验器对引了未标记
    摘录的记录在旧版档案上报 WARN（有这条 flag 时说明它是保留的旧值），不据此删值。为这份 sidecar 写**一条**
    `category: prior_archive_digest_unrecognised`、`kind: other`、`severity: yellow` 的 flag（`affected_field` 写
    “旧档案摘录（未标记）”，`current_source_values` 引该 sidecar 首行），`warnings` 与返回 JSON 写明需要 `legacy_upgrade`
    （它会由摘录 worker 重写成带头部的摘录）。校验器核对：引了这种 flag 所指 sidecar 的结构化记录一律报出（旧版档案上
    是 WARN；保留的旧值应同时有上文的 `legacy_value_unsupported` flag）。
  - 结构化产物照 §5 重写，内容规则与当前契约相同（一个方案一个 episode——旧档案按周期拆开的 episode 合并；
    `treatment_lines.json` 的 `regimen`、`status_basis_text` 从 sidecar 逐字重取，不沿用旧文件里的转述或“患者自述：”之类前缀
    ——episode 自带 `provenance_layer`，前缀多余；`profile.json.summary.current_regimen` 不同，它照 §5.7 保留自述标记；
    timeline `detail` 只写来源内容，旧的方法说明移到 `readiness.json.warnings[]`），`generated_at` 更新为本次时间，版本号
    保持不变。`timeline.json` 照 §5.6 写（每个事件带 `conflict_group` 与 `acute_finding_id` 键——后者此时总是 null——旧版
    schema 也接受），不加 `acute_finding` 事件，所以影像/检验事件的 `detail` **必须**写出该报告登记的急性发现；
    `timeline.md` 同样不加急性发现行（`acute-findings.md` §7）。`longitudinal_observations.json` 照 §2.3 写，用它的当前版本号
    （这份条件文件只有一个版本，不是契约标记）。
  - 旧文件里有、sidecar 也支持、但放错了来源层的值（如自述用药在 `medications[]`、自述功能描述在
    `demographics.function_description`）：来源层规则优先——按 §5.2/§5.7 移到自述所属的位置（时间线自述事件、
    treatment episode），不写 `legacy_value_unsupported` flag，在 `warnings[]` 写一句移动了什么。
  - 旧结构化文件里有、本次 sidecar 找不到原文支持的值（如只在旧 JSON 里出现的性别），或只有未标记摘录支持的值（上一条）：
    **保留**，写一条
    `category: legacy_value_unsupported`、`kind: other`、`severity: yellow` 的 flag（§6.1），不删、不另编；它的
    `current_source_values` 写 `{value: 旧值, source_ref: 旧记录当时引用的 sidecar 行}`（旧记录没有行号就引那份 sidecar 的
    `#L1`；旧记录没引任何 sidecar 时，引该字段所属领域日期最新的一份 sidecar 的 `#L1`），`issue` 写“旧版结构化文件中的
    值，所引 sidecar 未见原文”（或“旧记录未引来源”）。
  - `readiness.json` 照 §6.2 写资料时效三字段与超期提示（旧版 schema 也接受）；`acute_findings.json` 照写（上文）。
  - 旧 flag 改为 `warnings[]` 说明（方法学说明、顺带提到且定位不到的字段，§2/§6.1）时，旧编号不能就此消失：该条
    warning 以旧编号开头（“RF-012（原 flag，改为说明）：…”）。
  - 旧版档案上的 flag 没有 sidecar 的 `layout` 记录：旧 flag 文字**或** sidecar 自己对该处的说明（如 Phase 1 说明“折痕
    压住该字”）写明是阴影、折痕、弯曲、划线之类版面观察时，按 `artifact` 分级（影响高风险字段为 yellow），两处都没写才按
    `legibility`；永不写 `document_intent`（它要两次独立读取）。**例外，优先于本条**：检验表的
    `category: lab_column_pairing` flag 一律按 §5.1 分级（有候选值：`legibility` / `yellow`；全部拒配：`artifact` / `red`），
    旧 sidecar 自己写了“列错位”之类的版面说明也不改它的 `kind`——这类说明逐字写进这条 flag 的 `issue`，不另写
    `artifact` flag（一个观察一条 flag）。本条只管旧 flag 里对**某个字段读数**的不确定。
  - 缺页（§5.8）：旧 sidecar 没有 `PAGE_LABEL`，`page_completeness.py` 把它们全列进 `unlabeled[]`、`gaps[]` 为空——这是
    “**无法检查**”，不是“没有缺页”。返回 JSON 写 `missing_pages_groups: null`、`page_continuity_checked: false`；
    `review_summary.md` 的缺页组一行写“旧版 sidecar 没有页码标注，缺页无法检查（`legacy_upgrade` 后检查）”。
  - 你登记或改动了 emergent/urgent 发现，而现有的 段D 渲染还没有写入它们时，照 §7 在 `review_summary.md` 与
    `readiness.json.warnings[]` 写过期提示（§9 的校验器核对）；重新渲染由编排者必做（SKILL.md Step 12），你不渲染。
- **重派续做**（`redispatch: true`）：上一个 Phase 2 worker 可能已部分完成。先读已有的
  `.rename_plan.json`：`md_dest` 已存在的条目视为已搬迁，不重新分类、不重复搬迁；`reviewed: true` 的条目不再复核；
  `ocr/` 中剩余的 sidecar 照常处理并追加计划条目；结构化产物按全部 sidecar 重新写出（覆盖半成品），同样每完成一个领域
  就写出一份。

### 4.1 覆盖检查（先做）

逐个 `source_id` 核对：`input_manifest` 与 `phase1_summary` 中的每个原件都应有 sidecar——在 `ocr/`
（多文书原件为 `ocr/<source_id>-<k>.md`），或（重派续做时）是 `.rename_plan.json` 中 `md_dest` 已存在的
条目——或在 `skipped_inputs` 中有理由。`raw/_FILENAME_MAPPING.md`、`raw/_SIDECAR_MAP.md`、`raw/_extract/`
等 `raw/_*` 审计与引擎输出不是原件，不计入。缺 sidecar 的原件写进返回 JSON 的 `missing_sidecars`，
`coverage_complete: false`；不中止，继续其余工作。

逐个检查 `ocr/` 中的 sidecar 头部：必须恰好是 phase1 提示词 §3 的 12 个键，`EXTRACTOR` 必须出现在
`phase1_summary`、`dispatch_log` 或 `raw/_dispatch_log.jsonl` 的 worker 标识中（被终止、没有返回的 worker 只在后两处）。桶内**所有** sidecar 都受同一契约约束，没有“旧版
不回溯”的例外（旧版档案走上面的旧档案升级）。不符合的 sidecar 不搬迁，留在 `ocr/`，写
`readiness.json.warnings` 一条（`sidecar_header_invalid: <source_id>`），并把该 `source_id` 同时列入
返回 JSON 的 `missing_sidecars`（`coverage_complete: false`），由编排者派 Phase 1 重新转写；你不修补它的
头部或正文。

### 4.2 相关性与分类（逐个 sidecar，大模型判断，不用关键词）

1. **相关性**：先按 `relevance-gate.md` 判断是否属于临床档案。明显无关或拿不准的文件移入
   `99_无关文件/`（高置信 `high_confidence/`、拿不准 `uncertain/`），不进入 14 个临床桶，并在
   `source_inventory.json.skipped_inputs` 记 `quarantined_irrelevant`——这一行的 `input_ref`、`sha256`、
   `size_bytes` 照抄 `input_manifest` 里该原件的条目（之后的运行由编排者在 Step 1 用 `inventory_hash.py --quarantined '<glob>'`
   直接得到同样的 `quarantined_irrelevant` 行；用户明确排除的输入用 `--exclude`，记 `user_excluded`）；拿不准的另写 flag。
2. **分类**：读 sidecar 内容决定 `bucket_path`（pinned 的 `NN_` 域 + 子桶，见 `bucket-taxonomy.md`
   §1.1/§1.1a 与 §1.3 易错项）。不照搬上传目录自己的编号或命名；影像报告一律进 `05_影像/<模态>`。
   旧档案摘录 sidecar（`SOURCE: prior_archive_digest`）固定进 `03_病程与叙事文书/既往档案摘录`
   （非中文 locale 为 `03_clinical_notes/prior-archive-digest`），其 inventory 行 `source_kind: prior_archive_digest`
   ——下游与校验器只凭这两处认出摘录，放在别处的摘录会让正确的 `prior_archive` 标注报错、错误的
   `source_reported` 标注漏检。只认头部 `SOURCE: prior_archive_digest`：内容看起来像旧档案摘录、但没有 phase1
   §3 头部的 sidecar 按 §4.1 当作头部不合规（交 Phase 1 摘录 worker 重写，旧版档案走 `legacy_upgrade`），不要
   凭内容把它归进摘录子桶，也不要把它的事实写成 `source_reported`。
3. **命名要素**：`doc_type`（文书自称，逐字）、`date`（出具日期；无则 `unknown-date`）、`hospital`
   （只取该文书正文逐字的机构名；看不清或没有写 `医院待核实`，并写 `kind: other` flag
   `unverified_critical_field`，不从文件名、相邻文件或上下文借用）。canonical 基名：
   `<YYYY-MM-DD>_<doc_type>_<hospital>`，文件名里不写“表格有问题”之类的说明。

### 4.3 写前桶计划（`.rename_plan.json`）与预检

每判断完一个 sidecar，立即把条目追加到 `<patient_dir>/.rename_plan.json`
（`{"schema": "phase2_rename_plan_v1", "patient_dir": "<PT-…，仅目录名>", "files": [...]}`；条目含
`id`（file_id，`f001` 起）、`source_id`、`ocr_sidecar_old`、`bucket_path`、`canonical`、`md_dest`、
`modality`、`page_range`、`persist: true`）。不写绝对路径、不写原上传文件名。

**任何 `mkdir` / `mv` 之前**，对计划中的每个 `bucket_path` 与 `md_dest` 运行
`scripts/check_bucket_path.py`（参数以 `--help` 为准）。被拒绝的路径：改到最合适的 pinned 子桶；
没有合适子桶时改到该域的 `其他`（`other`），写 `readiness.json.warnings` 一条
（`bucket_precheck_rejected: <原路径> → <新路径>`），并在返回 JSON 的 `bucket_precheck_rejections` 列出。
预检全部通过后才进入 §4.5。自造子桶（如“患者自述”“既往资料摘录”）一律会被拒绝。

### 4.4 复核计划（第二次读取，必做）

对每个计划条目重读 sidecar 前 30 行——一次命令批量读多份（如 `head -n 30 ocr/s001.md ocr/s002.md …`），每核完一批就在
`.rename_plan.json` 对应条目写 `reviewed: true`（这是写入，也让重派的 worker 从未核的条目接着做）：内容与
`doc_type` / `bucket_path` 明显不符 → 就地更正条目并写
`kind: other`、`severity: yellow` 的 `filename_content_mismatch` flag；拿不准 → 保留最佳判断并写
`severity: red` 的同类 flag。更正后的路径同样要重新预检。

### 4.5 搬迁

按计划把 `ocr/` 中的 sidecar **移动**到 `<patient_dir>/<md_dest>`（`mkdir -p` 目标桶，`mv -n` 不覆盖）。
canonical 基名相同的多个 sidecar 在基名后加 `_<file_id>`（如 `…_示例医院_f007.md`），**不要**用 `_2`、`_3`：
缺页检查（§5.8）按文件名里的机构段分组，只认识 `_<file_id>` / `_<source_id>` 这类句柄后缀，`_2` 会把同一
文书的几页拆成不同组、互报缺页。原件留在 `raw/`，不复制进桶。随后写 `raw/_SIDECAR_MAP.md`（去标识 raw 文件 →
sidecar → 桶；不写原上传名；**不改** Phase 1 的 `raw/_FILENAME_MAPPING.md`）。`ocr/` 清空后删除；
仍有剩余文件时保留 `ocr/`，逐个写 `ocr_drain_incomplete: <文件名>` 到 `readiness.json.warnings`。

### 4.6 `source_inventory.json`

使用 `"schema": "source_inventory_v2.1"`，每个 content unit 一行：`file_id`、`source_id`、`original_path`（去标识
句柄）、`raw_path`、`page_range`、`bucket_path`、`sidecar_path`、`modality`、`read_mode`、`adapter`、
`adapter_provenance`、`persist`，以及：

- `sha256`、`size_bytes`、`page_count`：取自 `input_manifest`；与 sidecar 头部 `SHA256` 不一致时写
  warning 并在返回 JSON 报告，不改任何一方；
- `page_label`：sidecar 头部 `PAGE_LABEL` 逐字（`null`，或旧写法 `none`，写 JSON null）；
- `source_kind`：`upload`，旧档案摘录为 `prior_archive_digest`（其 `raw_path`、`sha256`、`size_bytes` 为 null，
  `digest_of` 必填，取自 Phase 1 摘录 worker 的返回 JSON；它不进 `update_log.json` 的 `inputs[]`）；
- `extractor_provenance`：`engine`、`version`、`raw_output_ref`（指向 `raw/_extract/…`）、`llm_role`、
  `worker_id`（= sidecar 头部 `EXTRACTOR`）；
- `second_read_channel`、`independent_reread`：照抄 sidecar 头部（`independent_reread` 写 JSON 布尔）；
  `high_risk_review_status` 与 `second_read_summary` 照抄 Phase 1 返回 JSON 的 `second_read[]`（`second_read_align.py`
  的输出，phase1 §2.3、§4 G），`independent_reread: false` 时不得写 `passed_independent_reread`；
- **头部 ↔ 清单行逐项相同**（校验器逐项比对）：每行的 `source_id` / `read_mode` / `adapter` / `modality` /
  `page_label` / `second_read_channel` / `independent_reread` / `sha256` / `extractor_provenance.worker_id` 分别等于
  该 sidecar 头部的 `FILE_ID` / `READ_MODE` / `ADAPTER` / `MODALITY` / `PAGE_LABEL` / `SECOND_READ_CHANNEL` /
  `INDEPENDENT_REREAD` / `SHA256` / `EXTRACTOR`（头部 `PAGE_LABEL: null` ↔ JSON null）。唯一例外是旧档案摘录行：
  头部 `SHA256: none`，清单 `sha256: null`；
- 顶层 `skipped_inputs[]`：`{input_ref, reason, sha256, size_bytes}`，`reason` 取
  `ds_store|macosx|empty|duplicate_sha256|archive_container|user_excluded|quarantined_irrelevant`，
  `input_ref` 用 `scripts/inventory_hash.py` 给的去标识句柄（如 `skip-013`），不得是原上传名。

## 5. 结构化产物

按 `schemas/` 写 `patient_summary.json`、`timeline.json`、`treatment_lines.json`（治疗事件）、
`labs.json`、`molecular.json`、`comorbidities.json`、`acute_findings.json`、
`longitudinal_observations.json`（有时序数据时）和兼容文件名 `missing_items.json`。每个事实带
`source_refs`（指向 sidecar 的 `#L` 行锚点）、`provenance_layer`、`verification_status`。版本号一律
取 `schemas/*.schema.json` 中的常量，不要沿用旧档案里的版本号：获得新必填字段的结构化文件与
`readiness.json`（§6）为 `schema_version: "2.1"`，`patient_summary.json` 为 `"2.2"`，`source_inventory.json`
（§4.6）的版本键是 `schema`、值为 `"source_inventory_v2.1"`，`acute_findings.json` 与 `update_log.json`（§8）
为 `"1"`。档案一旦是当前契约（`readiness.json` 为 `2.1`，或已有 `organize_meta.json`），任何一份结构化文件
还停在旧版本号都是“混合版本档案”错误，校验器按新 schema 严格校验它。当前契约档案上，除条件文件
`longitudinal_observations.json` 外，上面每一份结构化文件与 `profile.json`、`readiness.json` **每次都写出**：
没有内容的领域写空数组，不省略文件（缺文件即校验错误）。所以当前契约档案上的**每次运行**
（含增量运行）都要检查所有结构化文件的版本号：内容没变、但版本号低于当前的文件也要按当前 schema 补齐新必填
字段后重写。旧版档案反过来：除 `legacy_upgrade` 外的运行一律保持原版本号（§4.0），不做部分升级。

### 5.1 检验（`labs.json`）

- 每个印出来的项目一个 panel，不合并（如总胆红素与直接胆红素分列）。
- 按 sidecar 的 `## 列配对` 记录填写：`bbox` / `table_parser` / `native_table` / `single_value` 配出的
  结果写 `value`；`linear_position` 与 `llm_row_read`（模型按行读表，phase1 §7 第 4 条）配出的只写
  `candidate_value`，**`value` 必须为 null**（schema：有 `candidate_value` 的行只能是这两种方法）；拒绝配对的
  `value` 与 `candidate_value` 都为 null，`pairing_method: none`。
- `pairing_method`、`pairing_confidence`（`high|medium|low|null`）、`pairing_note`（如“项目 8 / 数值 7，按规则
  全部拒配”）与 `raw_value`、`candidate_value`、`value` 逐项照抄 sidecar `## 列配对` 块里的 `pairs[]`（即
  `scripts/pair_lab_columns.py` 的输出；块的 `input` 键是脚本读的文件），按 `item` 对到 panel 的 `analyte`；
  `candidate_value` 是脚本给出的数字串原样（如 `"12.30"`，不转成数值、不去尾零）；`raw_value` 只放该格原串或
  null，**不写说明文字**，说明一律进 `pairing_note`。校验器在 `raw/` 在场时用脚本重算 `input`，并逐项核对
  labs.json 与块中的 `pairs[]`：与脚本输出不一致（换位、把候选改成 `bbox` 数值）即失败。结果串上印的 ↑/↓/H/L
  在 `pairs[].flag_glyph` 与 `pairing_note` 里，不写进 `report_flag`。
- 计数不等而置空的单位、参考范围、标记列写 null；`report_flag` 不由模型补写。
- **sidecar 没有 `## 列配对` 块**（旧版 sidecar，只在 `legacy_phase2_only` 时遇到——`legacy_upgrade` 会先由 Phase 1
  重新转写）：Phase 2 **不在 `raw/` 下写任何中间文件**（旧版档案可能根本没有 `raw/`），配对在内存里跑，用管道把表格
  文本交给同一个脚本：表格只有线性文字时，把该表在 sidecar 里的原文逐行（不改字）经标准输入交给
  `python3 "<skill_dir>/scripts/pair_lab_columns.py" --text -`；旧 sidecar 里的表已经是**按行的 Markdown 表**（每行
  “项目 | 结果 | 单位 | 参考范围”，`--text` 会拒绝它）时，逐格照抄成 `{"items": [...], "values": [...], "units": [...],
  "ranges": [...]}`（按表中行序、不改字、不补空格），经标准输入交给 `… pair_lab_columns.py --columns -`。按输出写候选
  （`pairing_method: linear_position`，`value: null`；脚本拒配就全部为 null、`pairing_method: none`），`pairing_note`
  写“旧版 sidecar，内存配对，无 raw/ 输入”——谁把这张表转写成行、行是否对齐都无从核实，所以只作候选。旧 sidecar 里
  由编排者或旧 worker 写的“不要配对”“列错位”之类注释不是本 skill 的规则，不据此跳过脚本；但 sidecar 里记录的这类
  版面观察要逐字写进下面那条 flag 的 `issue`，让核对的人看到转写者当时的疑虑。当前契约的 sidecar 没有这个块是
  Phase 1 的缺口：列进 `missing_sidecars` 交回 Phase 1 重写，不在 Phase 2 补。
- 位置配对或模型按行读出的候选值进 `readiness.json` flag（`category: lab_column_pairing`、`kind: legibility`、
  `severity: yellow`，“数值按位置配对，未核实”/“数值为模型按行读出，未核实”，`current_source_values` 引该 sidecar；
  旧 sidecar 写了“列错位”之类的版面说明时仍是这一分级，说明逐字进 `issue`——本条优先于 §4.0 旧 flag 的版面分级）；
  全部拒配写 `category: lab_column_pairing`、`kind: artifact`、`severity: red`（同样引该 sidecar）。校验器逐个 sidecar 检查这两种 flag。候选值不进入趋势、不进入段D 摘要。

### 5.2 用药（`comorbidities.json.medications`）

`medications[]` 只收**医嘱/用药清单条目**与**影像申请单指征里写的在用药**：每条医嘱/清单条目单独一行（相同药名
的多个条目不合并，顺序同原文）；申请单指征写“on X”“正在使用 X”时，X 写一行（`administration_setting: unknown`，
`use_status: active_reported`（见下方 `use_status`），`order_role` 按药物性质；同一天几张申请单都写了，每张各一行）。
患者/照护者自述的用药不写成 `medications[]` 行（自述来源层现行规则不产生用药行），只作为时间线自述事件。病历叙述里提到、没有对应医嘱行的药（如现病史写“按原方案继续第N周期”）
**不进** `medications[]`，抗肿瘤药只写进 treatment_lines 的 episode（§5.3）。每行写：

- `medication_id`：每行一个，`MED-001` 起顺序编号；`treatment_lines.json` 的 `medication_refs` 只列这些编号；

- `administration_setting`（必填），只有两条判定规则：
  1. 页面科室/病区为日间单元，且该条目途径为静脉或肌注，或带“配”/配伍标记 → `day_ward`。日间单元 = 科室/病区名里
     写明“日间”的给药单元：“日间病房”“日间治疗中心”“日间化疗”（含“某科日间化疗”这种挂在专科下的写法）、
     “day ward”“day-chemo unit”；只写专科名（如“肿瘤内科”）或“门诊”不算；
  2. 条目位于“出院带药”**标题**之下 → `discharge`（嘱托或备注里顺带提到带药的一句话不是标题，它下面的行仍是
     `unknown`）；
  3. 其余一律 `unknown`。`inpatient`、`long_term` 是保留值，现行规则不赋值。
- `setting_basis`：判定所依据的原文逐字（如“病区：日间治疗中心；用法：静滴”“出院带药”）；`administration_setting`
  不是 `unknown` 时必须非空，`unknown` 时为 null。按“；”分开的**每一段**都必须逐字出现在该行 `source_refs` 所引的某份
  来源里（校验器核对）——没有“出院带药”标题就不能写 `discharge`；
- `order_role`（可选，大模型按条目语义判断）：`antineoplastic|premedication|diluent|supportive|chronic|other|unknown`。
  判别：化疗、免疫、靶向、内分泌、抗体偶联药 → `antineoplastic`；冲管或作溶媒/载体的生理盐水、葡萄糖 →
  `diluent`；原文标明输注前给药或列在预处理栏的抗过敏、止吐、激素 → `premedication`；其余对症支持用药——护胃、保肝、
  止吐、止泻、抗过敏、皮疹外用药等，不论途径、是否“必要时”——→ `supportive`；长期基础病用药 → `chronic`；
  拿不准 → `unknown`；
- `use_status` 照旧只按来源用语：日间单次给药不等于 `active_confirmed`。影像申请单指征写“on X”“正在使用 X”的行
  **一律 `active_reported`**——医生文书说患者在用，但它不是给药记录：不写 `active_confirmed`（夸大），也不写
  `unknown`（丢掉了原文的“在用”）。

抗肿瘤药（含“赠药”）的用药行同时由 treatment_lines 的 episode 通过 `medication_refs` 链接（§5.3：同一方案的
各周期是**同一个** episode，各周期的用药行都列进它的 `medication_refs`），不产生线次。

### 5.3 治疗事件（`treatment_lines.json`）

**一个 episode = 一个方案的一段连续治疗。** 同一方案的多个周期（第1程、第2程、C3D1……）合并为**一个**
episode：`started_at` 取首程日期，`regimen` 逐字（取原文写法；“赠药”等供药说明不算换方案），各周期来源都进
`source_refs`；最近一次周期的原文写法（如“第4程”）写可选字段 `cycle_label_verbatim`。药物组成改变（换药、
加药、减药）才开新 episode。`documented_line_label` 只收原文带“线”字样的写法（“二线”“second-line”）；
“第N程”是周期，不写进 `documented_line_label`，也不写进 `line_number`。

每个 episode 必填 `status`、`status_basis`，只按来源用语登记，不推断：

| `status_basis` | 何时用 | 可得出的 `status` |
|---|---|---|
| `administration_record` | 给药记录/执行单写明本次给药 | `ongoing` |
| `clinician_note_current` | 当次就诊记录的现病史/诊疗计划写“继续/正在/目前方案/第 N 程/停药/更换” | `ongoing` 或 `stopped`（按原文） |
| `order_or_indication_only` | 只有处方/医嘱，或影像申请单指征写“on X”“restaging on X” | `ongoing` |
| `patient_reported` | 患者/家属的陈述（正在用、已停，或只是过去式叙述、没说停或换） | `ongoing` / `stopped` / `unknown`（按原文） |
| `dates_only` | 只有起止日期、没有状态用语 | `unknown` |
| `none` | 没有任何依据 | `unknown` |

- `status_basis_text`：依据原文逐字，必须出现在该 episode `source_refs` 所引的某份来源里（`conversation:` 锚点对应
  `conversation_notes/` 里的记录；校验器核对，只有省略号的引文不算）；`status_as_of`：依据来源的日期（`YYYY-MM-DD`）。
- schema 钉死的组合（违反即校验失败）：
  - `status: ongoing` ⇒ `status_basis` 不是 `none`，且 `status_as_of` 非 null——唯一例外见下方未注明日期的
    自述；
  - `status_basis: none` ⇒ `status: unknown`；
  - `status_basis` 为 `administration_record` / `clinician_note_current` / `order_or_indication_only` /
    `patient_reported` ⇒ `status_basis_text` 为非空原文。
- **只用当次记录，不用照抄的旧句**：在治判定取每份记录**当天**的现病史/诊疗计划段。门诊病历常把上一次的
  “本次按原方案行第N周期……”照抄进后来的病史（copy-forward）：它不是后来那个日期的在治依据，也不能据此把较早的
  周期判为该日仍在进行。多个来源时取日期最新的**当次**依据。
- 同一天的几页对周期序号说法不一（如一页写“第N程”、另一页写“第N+1程”）：**先剔除照抄句**——与更早一次记录逐字
  相同的句子是照抄，不算当天的说法；剔除后只剩一种写法时就用它（写 `cycle_label_verbatim`，不写冲突 flag）。剔除后
  仍有两种当天写法才写 `kind: conflict` flag 并列两种写法；两页都表明在治时 `status` 仍可为 `ongoing`，不写
  `cycle_label_verbatim`（两种写法都在 flag 里），`status_basis_text` 取不含周期序号的那段在治原文（没有这样的原文就取
  日期最新、`file_id` 最小的一页，并在 flag 的 `issue` 写明取了哪一句）。
- `status_basis_text` 有几个候选原句时：取日期最新的来源；同一天取 `file_id` 最小的那份；只写一句。
- 手术、单纯放疗不是药物方案的 episode：写进 timeline（`procedure` / `radiation`）；同步放化疗里的药物照常成 episode，
  放疗写在 timeline。自述里只到月份的起止日期（“2030年4月”）不能写进 `format: date` 的 `started_at` / `ended_at`：
  写 null，原文留在 `status_basis_text` 或 timeline 事件（`date_precision: month`），这时不能用 `dates_only`。
- 家属或本人陈述（`patient_reported`）的 `status_as_of` 取**这句话说出或交给我们的日期**：对话里说的取对话
  日期（`conversation:<ISO-8601>` 锚点的日期）；自述材料上写了日期取该日期。**自述材料没有落款日期**（如
  “这个方案现在还在用”）时：`status: ongoing`（或按原文 `stopped`）、`status_basis: patient_reported`、
  `status_as_of: null`，并写 `status_as_of_precision: "undated_self_report"`，`provenance_layer` 按说话的人写
  `patient_reported` / `caregiver_reported`（schema 钉死，写 `source_reported` 校验失败）——不借本次运行日期、文件名、
  相邻文件或治疗日期去补一个日期；这是 `ongoing` 允许 `status_as_of` 为 null 的唯一情形。未注明日期的自述说的是
  已停（`stopped`）或没说在用还是已停（`unknown`，如“经过4个周期治疗”这样的过去式叙述、原文没写停或换）时，同样
  写 `status_as_of: null` + `undated_self_report`；不是未注明日期的自述就不写 `status_as_of_precision`。累计次数
  （“已经做了4个周期”）不是某一周期的写法，不写 `cycle_label_verbatim`。“截止现在/到目前已经做了N个周期”同样是
  累计次数：“现在”锚定的是计数截止的时点，不是“还在继续”，按 `unknown` 写；只有原文另说了在用或继续（“现在还在用”
  “接下来继续做”）才是 `ongoing`。这时 `profile.json.latest_status.as_of`（§5.7）与
  `patient_summary.json.current_status.as_of` 同样写 null（`current_status.provenance_layer` 按陈述者写
  `patient_reported` / `caregiver_reported`）。
- `line_number` 只在来源明写线次（“二线”“second-line”）时填整数，其余为 null。
- 旧档案摘录中的既往治疗：`status` 只能是 `stopped`（摘录原文写明停用/结束）或 `unknown`，
  永不为 `ongoing`，`provenance_layer: prior_archive`。

### 5.4 分子（`molecular.json`）

照旧逐字记录报告、样本、方法、质量与结果；HLA 分型写入 `hla_typing[]`：
`{locus, allele, resolution, method, source_refs, provenance_layer, verification_status}`。`locus` 一律写裸位点
字母（`A`、`B`、`C`、`DRB1`…；报告写“HLA-A”也写 `A`），`allele` 逐字（如“A*02:01”），`resolution` 按等位基因
字段数机械填写（`1-field`…`4-field`），`method` 按原文，未写为 null；可选 `report_date` 写分型报告自己的日期
（文件名日期或报告上印的日期，`YYYY-MM-DD`；报告没写就 null 或不写，不从别的文书借——校验器核对）。报告只写了“杂合/纯合”、没有给出等位基因
时照样写一行：`allele: null`、`resolution: null`，另写 `zygosity`（逐字抄原文，如“杂合”“纯合”）；
这种行只说明做过分型，下游不拿它匹配 HLA 限制性试验。HLA 分型不是肿瘤体细胞检测，不与药物或试验连接。

### 5.5 急性与附带发现（`acute_findings.json`）

按 `acute-findings.md` 逐份报告登记：类别与默认 `acuity` 只用该文件的固定表，只允许三种来源用词
调整；`change_vs_prior` 只做逐字映射；每条发现在 `timeline.json` 有恰好一条 `category: "acute_finding"`
事件并双向链接（事件的 `acute_finding_id` = `finding_id`，发现的 `timeline_event_id` = 该事件 `event_id`）。
`source_ref` 带行号（`<sidecar>#L<n>` 或 `#L<n>-L<m>`），`verbatim_text` 按“……”切开后的每一段都必须
逐字出现在这几行上（校验器按行核对，只有省略号的引文不算）；调整 `acuity` 的 `acuity_basis_text` 与非 `not_stated`
的 `change_vs_prior.verbatim` 同样必须逐字出现在**这几行**上（调整用语在同一报告另一行时写 `acuity_basis_ref`），
且 `acuity_basis_text` 含 `acute-findings.md` §4.1 该调整的固定用词——“较前无显著变化”不能把血栓下调为 incidental。
`exam_date` / `report_date` 取自所引报告（文件名日期或报告上印的日期），不从别的文书借。**文件总是写**，没有发现时 `findings: []`；
旧版档案上只重跑 Phase 2 同样写（§4.0：`timeline_event_id` 为 null，不加时间线事件）。
影像报告里编号的诊断条目逐条读完再判断，不能只看第一条印象。

### 5.6 时间线（`timeline.json` / `timeline.md`）

事件字段照旧，另加：`conflict_group`（§2.4，没有则 null）、`acute_finding_id`（§5.5，没有则 null）——
这两个键**每个事件都写**，不适用时写 null，不省略；一个 `conflict_group` 至少有两个事件（只有一个事件的组
校验失败）。`category` 可取 `acute_finding`。影像事件的 `detail` 摘要不得遗漏报告编号诊断条目中的急性发现
（它们另有独立事件；`legacy_phase2_only` 时没有独立事件，`detail` 就是它们在时间线上唯一的位置，§4.0）。
`timeline.md` 每行以 `[[src:…]]` 锚点结尾。

### 5.7 人口学与 profile

- `patient_summary.json.demographics`：照 §2.1–§2.3 写 `sex`、`age`、`age_as_of`、
  `performance_status_verbatim` 等；它是权威来源，整块 `provenance_layer: source_reported`，所以只收原件里的值：
  患者/家属自述的功能描述、年龄、体重不写进这里，作为时间线自述事件（`provenance_layer: patient_reported` /
  `caregiver_reported`）保留。`function_description` 只收医生文书里对功能状态的原文（如“生活可自理，可下床活动”），
  必须逐字出现在 `demographics.source_refs` 所引的某份原件里（不是 `conversation:` 锚点、不是任何
  `conversation_notes/` 下的对话记录——包括领域桶里的，如 `03_病程与叙事文书/conversation_notes/`——、不是
  `14_患者自管补充/` 或 `SOURCE: patient_supplement` 的 sidecar；校验器核对）；没有这样的原文就写 null。
- `patient_summary.json.diagnosis`（判断在这里做，脚本只核对结果）：`primary` 按**来源阶梯**取第一个有写的来源，逐字照抄
  （不改写、不合并、不归一）：病理诊断 > 出院/门诊诊断 > 检查申请单或影像检查指征（“临床诊断：…”“检查目的：…”）>
  NGS 报告的“临床诊断”栏 > 自述（自述只进 `patient_reported` / `caregiver_reported` 层，不填 `primary`）；取自哪一级写进
  `diagnosis_basis`（`pathology` | `discharge_or_clinic_diagnosis` | `order_or_imaging_indication` | `ngs_clinical_diagnosis` |
  `patient_reported`）。两个原发、或不同来源说法不同，按 §2 并列保留并写 flag，不挑一个。`profile.json.summary.one_line_condition`
  **必须带上** `primary`（去掉 token 后的字面）；`primary` 为 null 时写“诊断资料缺失”（校验器核对）。sidecar 的
  `## 高风险字段复读` 表里两读一致的诊断或分期（“是”行），在任何结构化字段里都找不到时，在 `readiness.json.warnings[]` 写一句
  完整性提示（“<sidecar>#L<n> 的<分期/诊断>「…」未进入结构化字段”），校验器同样给 WARN。
- `profile.json.demographics`：`{sex, age, age_as_of, performance_status_verbatim[], provenance_layer, source_refs}`，
  从 `patient_summary.json` 原样复制，不另行抽取；年龄是准标识项，只作档案内部字段，导出时按
  最小必要原则处理。
- `profile.json.summary.current_regimen`：去掉下述来源标记前缀后等于 `latest_status.regimen`（没有在治 episode 时 null）。`summary` 整块只有
  一个 `provenance_layer`（通常是 `source_reported`，取决于诊断等字段），所以在治依据是自述（该 episode 的
  `provenance_layer` 为 `patient_reported` / `caregiver_reported`）时，`current_regimen` **保留**来源标记前缀：
  患者说的写“患者自述：<方案>”，家属/照护者说的写“家属自述：<方案>”——不能让自述方案以 `source_reported` 的面目
  出现；反过来，在治 episode 是原件时不加前缀。校验器核对三件事：去掉前缀后与 `latest_status.regimen` 相同（都为 null
  也算相同）、自述 episode 带对应前缀（按该 episode 自己的说话人，与 `summary` 块是哪一层无关）、原件 episode 不带前缀；
  只有前缀没有方案（如单独一个“患者自述：”）不是 null，报错。`treatment_lines.json` 与 `latest_status.regimen` 不加前缀
  （它们自带来源层）。`summary` 必写：缺失或写成 null 在当前契约档案上报错，校验器按 `current_regimen` 为 null 继续核对。
- `profile.json.latest_status`（必写；没有在治 episode 时写 `{"regimen": null, …}`，缺失、写成 null 或写成没有 `regimen`
  键的对象（`{}`）在当前契约档案上报错，校验器按 regimen null 继续核对）：`regimen` 取 `status: ongoing` 的 episode（没有则 null），`as_of` 为其
  `status_as_of`（未注明日期的自述为 null），`status_basis` 为该 episode 的 `status_basis` 原样（如
  `order_or_indication_only`、`patient_reported`；没有在治 episode 时 null）——只读 profile 的下游据此知道“在治”
  依据的是给药记录、医生当次记录、申请单指征还是家属陈述，不会把申请单指征当成给药记录；`ecog`、`response`
  只收医生原文。

### 5.8 文书缺口（`missing_items.json`）

- 现有档案缺口照旧只写“档案里没找到的既有文书”，不推荐检查。checklist 的癌种 slug 不确定时用
  unknown，不做 closest-fit。每条缺口都必填 `severity`：普通缺口（`not_in_archive` / `unknown` /
  `patient_declined_to_add`）写 `info`，`requested_by_clinician` 写 `yellow`，`missing_pages` 写 `red`。
  档案里的医生文书写明要做某项检查/复查（如门诊嘱托“复查血常规”），而档案里没有它的结果时，这条缺口是
  `requested_by_clinician`（`yellow`），`clinician_request_source_refs` 引那句嘱托；`not_in_archive` 只用于没有医生
  嘱托、按 checklist 列出的缺口——带 `clinician_request_source_refs` 的缺口不能写成 `not_in_archive`。这只记录医生
  已经写下的要求，不是本 skill 推荐检查。
- **缺页**：§4.5 搬迁完成、§4.6 写出 `source_inventory.json` 之后，运行
  `python3 "<skill_dir>/scripts/page_completeness.py" <patient_dir> --json`（它读桶内 sidecar 头部的 `PAGE_LABEL`，
  搬迁前运行会读不到）。脚本按“日期 + 桶内文书类型目录 + 文件名中的机构段 + 印刷总页数”分组检查页号
  连续性；把它输出的 `gaps[]` 逐条照抄进 `document_gaps[]`（`gap_type: missing_pages`、`severity: red`、
  `group_key`、`pages_present[]`、`pages_missing[]`、`page_total`、`document_category`（如
  “门诊病历（2030-01-05，共 4 页）”）、`reason_for_artifact`），不增删、不改页号；每组同时写一条
  `category: missing_pages`、`kind: completeness`、`severity: red` 的 readiness flag，`current_source_values` 引该组的
  一份 sidecar（校验器逐组核对）。同一页收到多份、其他页份数更少时，脚本也报为缺页（原因写明“可能是另一份同类
  文书缺页，也可能是重复拍摄”），同样照抄。脚本 `duplicates[]` 中的同页重复是重复件
  （`kind: other`、`severity: info`），不是缺页；`unlabeled[]`、`invalid[]`、`partially_labeled[]`（多页 sidecar
  里有页写 `null`）不产生任何缺口。
- 缺页只描述档案完整性，询问话术仍用 `gap-followup.md` 的模板。

### 5.9 旧档案摘录

只在 `prior_archive_authorized: true` 时出现。摘录 sidecar 中的事实：`provenance_layer: prior_archive`，
只写进既往史（timeline 的历史事件、既往治疗 episode、既往病理/分子/检验结果）；**不得**写进
`current_status`、`latest_status`、`summary.current_regimen`，不得支撑 `status: ongoing` 的 episode 或
`use_status: active*` 的用药行，不得作为急性发现，不得与本次原件合并成一个值（校验器对这些位置逐条检查）。
**一条记录只有一个来源层，所以摘录与原件不混在一条记录里**：带 `provenance_layer` 的块（如
`patient_summary.diagnosis`、`demographics`、`profile.summary`）是 `source_reported` 时，它的 `source_refs` 不引摘录；
只有摘录写了的字段（如组织学、诊断日期）在这个块里写 null，摘录的说法另写成 `prior_archive` 的时间线历史事件
（或既往 episode / 既往分子、检验结果行）。条目自带 `provenance_layer` 的列表（如 `performance_status_verbatim[]`）
可以在 `source_reported` 块里放一条 `prior_archive` 条目，但块的 `source_refs` 仍不引摘录。
`profile.summary.one_line_condition` 只由本次原件的事实拼成（它会被复制进 AGENTS.md），不含摘录里的基因、
诊断或治疗。校验器核对：引了摘录的记录必须是 `prior_archive`。
只引用摘录 sidecar 的记录一律 `provenance_layer: prior_archive`，`prior_archive` 记录也必须引用摘录 sidecar。与本次原件冲突时并列保留（§2）。旧会诊推荐、试验评分、旧线次编号不作为当前事实写入。
摘录 sidecar 必须在 `既往档案摘录` 子桶、inventory 行 `source_kind: prior_archive_digest`（§4.2）；没有 12 键头部的
旧摘录是旧版 sidecar，按 §4.1 交回 Phase 1 重写，不当作摘录使用。

## 6. `readiness.json`：覆盖状态、flag 分级与资料时效

`readiness.json` 记录 `documentation_coverage`、`warnings`、`review_flags`，以及资料时效三个字段；
不给 A–F 临床 readiness 分数。资料不完整不阻止一般教育；只限制受影响的个体化内容。

### 6.1 flag 分级

每条 flag 必填 `severity`（`red|yellow|info`）与 `kind`，可选 `cross_doc_supported`、`uncertain_ids`。
**`severity` 是抽取与档案完整性的不确定程度，不是临床严重度**；它只决定该字段能否当作已确认值使用。

| 情形 | `kind` | `severity` |
|---|---|---|
| 值类高风险字段两读冲突（`field_class` 为 date / number / unit / stage / drug_name / ihc_marker / ln_station / variant / regimen_connector / cycle_number） | `legibility` | `red` |
| 诊断文字两读冲突（`field_class: diagnosis_text`） | `legibility` | `yellow` |
| 以上任一，且他页清楚读数等于本处某个通道读数或候选（`cross_doc_supported.status: supported`） | `legibility` | 降一级（`red` → `yellow`，`yellow` → `info`） |
| 他页清楚读数与本处全部读数和候选都不相容（`cross_doc_supported.status: contradicted`） | `legibility` | `red` |
| 非高风险字段字迹不清；检验值按位置配对未核实 | `legibility` | `yellow` / `info` |
| 污迹、阴影、折痕、纸面弯曲（`layout: shadow_stain_fold`）、裁切、印章压字、疑似划线等版面异常，影响高风险字段 | `artifact` | `yellow` |
| 版面异常，未影响字段读取 | `artifact` | `info` |
| 检验表列计数不等，全部拒配 | `artifact` | `red` |
| 删除/更正意图经两次独立读取一致（sidecar `layout_intent` 非 null） | `document_intent` | 高风险字段 `red`，其余 `yellow` |
| 同一时点两个来源对高风险事实说法不相容 | `conflict` | `red` |
| 不同日期的两份原件对时不变字段（诊断、组织学、既往治疗史、已出具的分子结果）说法不相容 | `conflict` | `red` |
| 其他同时点不一致；患者自述与原件不一致（§2.4） | `conflict` | `yellow` |
| 缺页 | `completeness` | `red` |
| 资料最新日期距本次运行超过 14 天 | `completeness` | `yellow` |
| 报告写明的对照检查（“与某日片比较”）不在档案中 | `completeness` | `info` |
| 高风险字段（分期、免疫组化、方案等）只有患者/照护者自述，没有原件 | `other` | `yellow` |
| 疑似跨患者、忠实度复核不通过、锚点缺口 | `other` | `red` |
| 机构待核实、文件名与内容不符 | `other` | `yellow` |
| 外文报告只有中文转述、没有原句（`category: foreign_language_paraphrase`，每份这样的 sidecar 一条——影像、检验、HLA 等都算，不只是登记了发现的那份；`acute-findings.md` §2.4） | `other` | `yellow` |
| **仅旧版档案**：旧结构化文件里的值在本次 sidecar 中找不到原文支持（如只在旧 JSON 里的性别；`category: legacy_value_unsupported`）——值保留、不删、不另编，等 `legacy_upgrade` 或 Phase 2.5 核对 | `other` | `yellow` |
| **仅旧版档案**：内容像旧档案摘录、但没有任何摘录标记的 sidecar（`category: prior_archive_digest_unrecognised`，每份一条；不从它新取事实，旧结构化文件里已有、只有它支持的值照 `legacy_value_unsupported` 保留，§4.0） | `other` | `yellow` |
| 不可信内容标记（`UNTRUSTED-*`，由 `scan_untrusted_markers.py` 生成、校验器并入，§9） | `other` | 脚本定：最高命中为 high → `yellow`，其余 `info` |

- **分级只看字段类别与旁证，不投票**：sidecar 里的 `[OCR_UNCERTAIN:U-nnn]` 已经是 `second_read_align.py` 三态判定后的冲突
  （引擎读数过了置信度阈值、合乎语法、与转写不同）或 worker 补报的不可读/版面异常；照表分级，不按“多数通道一致”自行排除，
  只有他页清楚读数支持（§2.5）时降一级。非高风险字段字迹不清写 `yellow`，有他页清楚读数支持时写 `info`。
- **“无信号”不是 flag**：`## 高风险字段复读` 表里 `无信号` 的行（引擎没读出、置信度低、读数不合语法等）只说明这一处
  只有单通道读取：**不写 flag、不建条目**，也不因此把字段置 null。每份有“无信号”行的 sidecar 只在 `readiness.json.warnings[]`
  写一句：“<sidecar 相对路径>：N 个高风险字段中 M 个只有单通道读取”（N、M 取 `source_inventory.json` 该行
  `second_read_summary` 的 `spans_total` 与 `no_signal`），不逐字段展开。各通道一致读出、只是原文用字本身反常（错别字、少见写法）的，不是读取
  不确定：不建条目、不改字；在高风险字段上可写一条 `kind: other`、`severity: info` 的 flag（“原文用字如此”）。
- 报告写明、档案里没有的对照检查按**字段**计：同一份缺失的对照检查被两份报告引用，写一条 flag、引两份报告。
- **方法学与护栏说明不是 flag**：“不同检测方法的结果不直接比较”“某药只见于申请单、没有给药记录”“这条事实只见于
  旧档案摘录”之类的说明写进 `readiness.json.warnings[]`，不写成 review flag——flag 只记录某个字段的读取、冲突、
  来源与完整性问题。
- **先看版面，再看读数**：sidecar 不确定条目的 `layout` 不是 `none`（删除线、压字、裁切、印章、阴影/污迹/折痕）时，
  `kind` 只能是 `document_intent`（仅当 `layout_intent` 非 null，即有两次独立读取支持）或 `artifact`，
  即使各通道读数也不一致、某通道漏读了整行，也不归入 `legibility`；`severity` 按上表 `artifact` /
  `document_intent` 行取（影响高风险字段的 `artifact` 为 `yellow`）。`legibility` 只用于 `layout: none` 的条目。
- `document_intent` 只在 sidecar 条目的 `layout_intent` 有两次独立读取支持时使用；否则一律降为
  `artifact`，`issue` 写“版面异常，字面读作 X”，`current_source_values` 保留字面读数。机械条件（校验器
  照此检查）：flag 的 `current_source_values[].source_ref` 引用的**每一份** sidecar 头部都是
  `INDEPENDENT_REREAD: true`（inventory 行 `independent_reread` 也为 true）；flag 写了 `uncertain_ids`，且其中
  至少一条是 `layout_intent` 为 `deleted`/`amended`、`readings` 里有两个不同非 `llm_vision` 类别给出同一读数
  的条目。
- 引用了 sidecar 不确定条目的 flag 写 `uncertain_ids`（如 `["U-003"]`，配合该条 `source_ref` 定位）；每个
  id 必须是 flag 所引 sidecar（`current_source_values` 与 `cross_doc_supported.refs` 指向的文件）里真实存在的
  `[OCR_UNCERTAIN:U-nnn]` token。`cross_doc_supported.refs` 只写能解析到桶内 sidecar 的锚点
  （`<NN_桶>/…/<文件>.md#L<n>`），不写 `ocr/` 路径。
- `category` 仍写具体类别（如 `extraction_fidelity`、`cross_source_conflict`、`lab_column_pairing`、
  `missing_pages`、`source_recency`）；`kind` 与 `severity` 是统一的机读分级。
- 校验器机械核对的行：`kind: conflict` 的 flag 一边是患者/照护者自述（`conversation:` 锚点或任何 `conversation_notes/` 下的记录，或 `SOURCE: patient_supplement` /
  `14_患者自管补充/` 下的 sidecar）、另一边只有一份原件 ⇒ `yellow`；`cross_doc_supported.status: contradicted` ⇒ `red`；`category: missing_pages` ⇒
  `completeness` / `red`；`category: source_recency` ⇒ `completeness` / `yellow`；`legibility` flag 指向的条目
  `field_class` 是值类（上表第 1 行的十类）时，除非 `cross_doc_supported.status` 是 `supported`，一律 `red`；
  sidecar 里的**每个** `[OCR_UNCERTAIN:U-nnn]` 都有一条 flag 在 `uncertain_ids` 里列出它、并引用该 sidecar；
  **一条 flag 只写一个受影响字段**（`affected_field` 里不出现“、”“,”“;”）。

### 6.2 资料时效

§4.5 搬迁完成后运行 `python3 "<skill_dir>/scripts/source_freshness.py" <patient_dir> --as-of <as_of_run_date> --json`
（必须显式传 `--as-of`：不传时脚本会退回旧 `readiness.json` 或今天的日期）。它按桶内 sidecar 文件名的
报告日期计算，`14_患者自管补充`、`99_`、`conversation_notes`、旧档案摘录不参与，上传时间与文件修改时间
永不使用。把输出的 `latest_source_date`、`days_since_latest`、`as_of_run_date` 原样写入 `readiness.json`
顶层（校验器会重算并比对）。`as_of_run_date` 是**本次**运行的日期：校验器拿它与本次 `update_log.json` 条目的
`at`（最后一个 `inputs` 非空的条目）比对，不能沿用上一次运行的日期。`days_since_latest > 14`（恰好 14 天不算）时，
把脚本输出的 `warning` 文字原样写进 `readiness.json.warnings[]`（整句逐字，校验器按整句找），并加 §6.1 的
`category: source_recency`、`completeness`/`yellow` flag。这句话只有一种写法，就是脚本
`stale_warning()` 输出的：

```text
本档案最新一份资料的日期为 {latest}，距本次整理已 {days} 天；请确认此后是否有新的检查报告或病历，时效说明需写明这一天数。
```

（`{latest}` = `latest_source_date`，`{days}` = `days_since_latest`；即脚本的 `STALE_WARNING_TEMPLATE`。）
旧版档案上只重跑 Phase 2 时同样运行并写这三个字段（没有 v1 日志条目可比，`as_of_run_date` 就是本次运行的本地日期），
超期同样写这句提示与 flag；校验器在旧版档案上按 `as_of_run_date` 复算，不一致只报 WARN。

不要改写（校验器按“已 N 天”找这一行；编排者向用户转述、段D 写 caveat 时也用这同一句）。新鲜度提示只说明
资料时点，不暗示需要做新检查。

## 7. 人类可读面

- `INDEX.md`：首行 `# patient_code: <code>`；表头 `file_id | 桶 | 类型 | 日期 | 机构 | 置信 | MD | Raw原件 | 页码`，
  “页码”列写 `page_label`（没有写“—”）；机构列只写正文逐字机构名或 `医院待核实`。
- `case_text.md`：每个事实句带 `[[src:<bucket>/<file>.md#L<a>-L<b>]]` 锚点。
- `review_flags.md`：有 flag 时写。先写一句“以下分级表示整理时的读取与完整性不确定程度，不是病情
  严重程度”，再按 `red` → `yellow` → `info` 分组，组内按 `kind` 分小节（字迹不清 / 版面异常 /
  文书删改 / 来源不一致 / 缺页与资料时效 / 其他），每条写受影响字段、各来源读法和锚点。
- **段D 过期提示**（`legacy_phase2_only` 在内的每种运行）：`acute_findings.json` 有 emergent/urgent 发现，而现有的 段D
  渲染没有写入其中某些（`.case_summary_data.json` 的 `case_summary_narrative` 首句没有逐条写到它们的 `label` 与日期——
  首句不以“资料中有报告写到需要尽快告知治疗团队的发现：”开头时（包括旧写法“资料中有报告原文写到…”）全部都算没写入；
  `verbatim_is_translation: true` 的发现在首句里没标“中文转述”、或 caveats 里含它原句的那一条没写“中文转述，非报告原句：”、或写了“报告原文”等称原文的说法（按条核对，`case-summary-html-prompt.md`「急性/附带发现」），也算没写入；
  或只有 `病情简要总结.html`、没有 `.case_summary_data.json`，无从确认）时，你在 `review_summary.md` 开头（资料时效之前）与
  `readiness.json.warnings[]` 各写一条，都以下面这句**原样**开头，后接每条没写入的发现“<label>（<日期>）”，用“；”分隔：

  ```text
  本次登记了需要尽快告知治疗团队的发现，登记时现有的病情简要总结.html 还没有写入它们（该文件若未在本次之后重新生成，请以 acute_findings.json 为准）：
  ```

  这句话在重新渲染之后仍然属实，不必回头删除。重新渲染是编排者的必做步骤（SKILL.md Step 12），你不渲染、不改
  `.case_summary_data.json`；校验器在渲染过期时核对这两处提示（§9）。
- `review_summary.md`（总是写）：开头依次写资料时效（最新资料日期与天数）、缺页组、急性发现条数；
  随后是诊断与分期、当前治疗（含 `status` 与依据原文）、分子、检验、既往治疗、合并症与用药、基本
  信息、本次产出的结构化文件清单，每项带锚点；最后是请用户核对的要点（药名、剂量、分期前缀、分子
  是否有原始报告、检验数值与箭头是否与原件一致、缺页是否属实）。不写任何评分或等级。

## 8. `update_log.json`

`update_log.json` 只有 `update_log.schema.json` 规定的形状：`{"schema_version": "1", "patient_code": "<PT-…>"（可选）,
"entries": [...]}`，条目只含 `at`、`run_mode`、`workers`、`inputs`（这两个必填，可以是空列表）、`added`、`removed`、
`degradations`、`outputs`（可选）、`note`，**不得**再写 `ts`、`triggered_by`、`relevance`、`case_summary_stale`、
`added_files` 等旧字段（schema 是封闭的，多一个键就校验失败）。

- 文件不存在 → 新建 `{"schema_version": "1", "entries": []}`；
- 文件存在但 `schema_version` 不是 `"1"`（或没有 `entries`、条目是旧形状）→ 这是旧版档案的日志：
  `legacy_upgrade`（§4.0）时它已随旧产物移走，新建即可；当前契约档案里出现这种日志时把它 `mv -n` 到
  `raw/_legacy_<YYYYMMDDTHHMMSS>/update_log.json`，再新建。新旧两种形状不得混在一个文件里。
- 旧版档案上的其他运行（§4.0，不升级版本）：**不新建 v1 日志、也不移动旧日志**——新建 v1 日志会让下一次
  更新误以为档案已经升级、跳过 `legacy_upgrade`。在返回 JSON 的 `warnings` 写明本次改写了哪些文件，由编排者
  告诉用户这份档案仍需做一次 `legacy_upgrade`。

然后追加一条本次运行的条目——**只通过脚本追加**，不要手写或改动已有条目：把条目 JSON 经管道交给
`python3 "<skill_dir>/scripts/update_log_append.py" <patient_dir> --entry -`，它给新条目写 `prev_sha256`（上一条目的
规范 JSON 的 sha256），校验器逐条复算这条链：事后改过的旧条目（把 kill 改成 retried、删掉一条 degradation）会断链。
`dispatch_log` / `raw/_dispatch_log.jsonl` 里被 `kill` 的 worker 照实记 `status: killed`（或 `timeout`）并写 degradation，
Phase 1 被杀后的单文件重派照实列出（校验器拿派发日志逐条核对）。条目内容：

- `at`（UTC ISO 时间，如 `2030-01-20T01:30:00Z`；`as_of_run_date` 是本地日期，两者日期可以差一天，校验器
  容许 ±1 天）、`run_mode`（`legacy_upgrade` 与 `full` 一样表示全部 sidecar 由本契约的 worker 重新写出）；
- `workers[]`：`{worker_id, phase, slice_id, status, files[], prompt_file_sha256}`，来自 `dispatch_log`、`phase1_summary`
  与你自己（`phase` 取 `phase1|phase1_retry|stub|phase1_digest|phase2|phase2_5|pii_rescan`，`status` 取
  `done|timeout|killed|retried|blocked`；`prompt_file_sha256` 照抄该 worker 返回 JSON 里的值，没有就省略；你自己的是
  `shasum -a 256 "<skill_dir>/references/organizer-prompt-phase2-synthesis.md"` 的结果——校验器拿它与技能自带的提示词
  文件比对，不同说明这个 worker 读的不是原文）。`files` **只列这个 worker 被派到或亲手写出的来源**（`source_id`）：
  Phase 1 worker 列它切片里的 `source_id`，摘录 worker 列它写的摘录 sidecar 的 `source_id`，你自己（Phase 2
  综合 worker）不写 sidecar，列 `[]`——不要把档案里全部来源都列上，校验器用这个字段判断哪些 sidecar 是
  本契约的 worker 写的；
- `inputs[]`：`{source_id, sha256}`，本次运行后临床档案里的**全部**上传原件，即 `source_inventory.json.files[]`
  中每个非 null 的 `sha256`（增量运行时包括以前运行留下的原件）；进了 `skipped_inputs[]` 的输入（重复件、
  隔离到 `99_无关文件/` 的文件等）不列入；
- `added[]` / `removed[]`：与上一个 `inputs` 非空的条目按 sha256 比较得出的 `source_id`（`inputs: []` 的条目，
  如段C 对话条目，不算一次输入对账）；新建的日志（含旧档案升级）`added` 为全部；
- `degradations[]`：`{worker_id, reason, redispatched_as[]}`，来自 `dispatch_log`；`redispatched_as` 中的每个
  worker 也必须出现在 `workers[]`；`status` 为 `timeout` 或 `killed` 的 worker 必须有一条 degradation；Phase 1 worker
  超时后的重派是**逐文件**的单文件 worker（`files` 只有一个 `source_id`）或 stub worker（SKILL.md Step 4）；
- `outputs[]`（建议写）：本条目写出的每份结构化 JSON 的 `{file, sha256}`（`file` 为档案内相对路径）。之后
  有人在整理流程之外改了这些文件，校验器能据此发现；
- `note`：一句话说明本次运行（不写姓名、路径或原文件名）。

## 9. 产物验证

写完全部产物后运行 `python3 "<skill_dir>/scripts/validate_structured_outputs.py" <patient_dir>`（不带 `--final`；JSON schema、来源锚点、hash、
PII、字段分层、sidecar 头部、急性发现链接、缺页与时效等）。`readiness.json` 为 `2.1` 时档案已按当前契约
严格校验（`organize_meta.json` 由编排者收尾时再写）。此时可以留下的错误只有两类：`AGENTS.md missing`
（它在 Step 13 才生成），以及以 `ERROR: .case_summary_data.json` 开头的行（上一次 段D 渲染自己的问题，例如按旧契约
渲染、首句仍是“资料中有报告原文写到…”——盖戳只证明它读的是当前数据，不证明它按当前契约写成；这类行由 Step 12
重新渲染消除，你留下它，并在 §10 返回 `case_summary_rerender_required: true`；只有写着 “the pinned stale notice … is missing from …” 的那一行例外：它说的是你 §7 的过期提示没写全，补上后重跑）。上一次的 段D 渲染（`.case_summary_data.json`）不归你管：本次改了急性发现、而它的病情概要首句
没有写到新的 emergent/urgent 发现时，校验器要求 §7 的“段D 过期提示”同时出现在 `review_summary.md` 与
`readiness.json.warnings[]`（缺任一处即 ERROR，旧版档案同样），两处都在时只报 WARN（`段D stale`），重新渲染由编排者
做——不要为此改动 `.case_summary_data.json`。校验器需要 `jsonschema>=4.18`：它缺席时当前契约档案直接失败，不是“通过”。结构与绑定错误由你修正自己写的产物后重跑；验证失败（除上面可以留下的两类之外仍有错误）
则不生成患者摘要；涉及临床值的错误进入 review queue，不让模型自行修正临床值。你的这次运行（每种 `run_mode`，
`legacy_phase2_only` 在内）**不带 `--readonly`**——除 Step 17 终态门外，它是唯一不带 `--readonly` 的一次（SKILL.md
Step 17）——它会把
不可信内容 flag（`UNTRUSTED-*`）并进 `readiness.json`：**校验通过（只剩上面可以留下的两类）后再写（或重写）`review_flags.md`，并按合并后的
`readiness.json` 计算 §10 的 flag 计数**，编排者展示的 `review_flags.md` 才与 `readiness.json` 一致。

## 10. 返回 JSON

最后一条消息只输出 JSON：

```text
{
  "role": "phase2_worker", "worker_id": "p2-1", "run_mode": "full", "elapsed_s": 900, "timed_out": false,
  "patient_dir": "<绝对路径>", "files_classified": 21, "md_sidecars_relocated": 21,
  "coverage_complete": true, "missing_sidecars": [], "bucket_precheck_rejections": [],
  "disposition_refused": [],
  "documentation_coverage": {}, "document_gaps": 3, "missing_pages_groups": 1, "page_continuity_checked": true,
  "latest_source_date": "2030-01-05", "days_since_latest": 19,
  "acute_findings_total": 2, "acute_findings_urgent_or_emergent": 2,
  "acute_findings_urgent": [{"finding_id": "AF-001", "label": "…", "acuity": "urgent", "date": "2030-01-12",
                             "source_ref": "05_影像/CT/…md#L14", "verbatim_text": "…",
                             "verbatim_is_translation": false}],
  "case_summary_rerender_required": true,
  "warnings": [], "review_flags_total": 9, "review_flags_red": 2, "review_flags_yellow": 5,
  "review_flags_info": 2, "review_flags_by_kind": {"legibility": 4, "artifact": 1, "conflict": 2, "completeness": 2},
  "review_summary_path": "<…/review_summary.md>", "source_inventory_path": "<…/source_inventory.json>",
  "update_log_path": "<…/update_log.json>"
}
```

- `run_mode`：照抄 Call parameters，编排者据此知道这是哪种运行（旧版档案上只重跑 Phase 2 就是 `legacy_phase2_only`）。
- `acute_findings_urgent[]`：每条 emergent/urgent 发现，带 `verbatim_text` 与 `verbatim_is_translation`（`acute_findings.json`
  原样），编排者在 Step 7.5 直接逐条展示，不必再打开文件；`verbatim_is_translation: true` 的要标“中文转述，非报告原句”。
- `case_summary_rerender_required`：你写了 §7 的“段D 过期提示”时为 true，§9 的校验输出里有以 `ERROR: .case_summary_data.json` 开头的行时也为 true——编排者据此必做 Step 12 重新渲染，不再询问。
- `missing_pages_groups` / `page_continuity_checked`：页码无法检查（旧 sidecar 没有 `PAGE_LABEL`，§4.0）时分别为 null / false。

## 11. 忠实度修订模式（`run_mode: faithfulness_patch`）

Phase 2.5（`organizer-prompt-phase2_5-faithfulness.md`，worker `p25-<n>`）只报告、不写文件。它**每次**返回后，编排者
都以此模式派你一次，传入 `faithfulness_results` 与 Phase 2.5 的 `worker_id`——即使全部 `faithful`（这时你只写日志条目，
它是 Phase 2.5 跑过的唯一落盘痕迹，Step 17 的 `--final` 检查它）。你只做三件事，其余文件不动：

1. 按 Phase 2.5 的分级映射，为每条 `not_faithful` / `needs_human_review` / `disputed` 结果在 `readiness.json.review_flags[]`
   写 flag（`id`、`category`、`kind`、`severity`、`affected_field`、`current_source_values[]`、`issue`、
   `resolution_status: "unresolved"`），不写替换值；
2. `not_faithful` 的值若被拼进 `profile.json.summary.one_line_condition`，重新拼接该字符串并去掉这一成分（写“资料缺失”
   或省略）；`summary.stage` 等细分字段保持原样并由 flag 标注（段D 对这些值显示“待核对”，`case-summary-html-prompt.md`）；
3. 在 `update_log.json` **追加一条自己的条目**（§8 形状；不改以前的条目——日志只追加；经管道交给 `python3 "<skill_dir>/scripts/update_log_append.py" <patient_dir> --entry -` 追加（它写 `prev_sha256` 链接，§8；不要手写进文件））：`run_mode: faithfulness_patch`，
   `workers[]` = Phase 2.5 worker（`phase: phase2_5`，`files: []`）+ 你自己（`phase: phase2`，`files: []`），`inputs[]` 照抄
   上一个 `inputs` 非空的条目，`added` / `removed` 为空，`outputs[]` 写你改写过的文件的新 `sha256`（没改就不写），`note`
   写“核对 N 项，M 项不一致”（不写值）。

旧版档案（§4.0）上不写日志条目：只做第 1、2 步（版本号不动），在返回 JSON 的 `warnings` 写明本次没有落盘记录、档案仍需
`legacy_upgrade`。

## 12. 用户决定落盘模式（`run_mode: relevance_disposition` / `upload_reconciliation`）

段E（无关文件处置）与上传对账中，用户在对话里逐项作出的决定由编排者收集，作为 `user_decisions[]` 传给你：
`{item（99_无关文件/ 下的相对路径或去标识句柄）, action: delete|hold|restore|reclassify|replace|coexist|ignore,
target_bucket（reclassify 时）, supersedes（replace 时：被替换的旧 sidecar 路径）, confirmation_text（用户逐项确认的原话）,
actor_role}`。编排者不自己动这些文件，也不写 `update_log.json`。档案仍是旧版（没有带 `workers[]` 的
`schema_version: "1"` 的 `update_log.json`）时不执行任何决定（§4.0）：全部按 `hold` 处理、列入 `disposition_refused`，
并在返回 JSON 的 `warnings` 写明需要先做 `legacy_upgrade`。否则你只做：

1. `delete`：只对 `99_无关文件/` 中的项目执行，且仅当该项 `confirmation_text` 非空、点名了这一项时，删除
   该 sidecar 与其 `raw/` 原件；临床桶中的文件、没有逐项确认原话的项目一律按 `hold` 处理，并在返回 JSON
   的 `disposition_refused` 中列出。
2. `restore` / `reclassify`：把该项移回临床桶（`reclassify` 用 `target_bucket`，先经
   `python3 "<skill_dir>/scripts/check_bucket_path.py"` 预检），更新 `source_inventory.json`（移出 `skipped_inputs` 的
   `quarantined_irrelevant`，补 `files[]` 行），然后**对移回的来源做一次增量综合**：§4.6 的清单行、§5 的各领域（含 §5.5
   急性发现——移回的影像或检验报告里的发现必须登记，`findings: []` 不能再代表“查过、没有”）、§5.8 缺页、§6.2 资料时效，
   以及 §7 里受影响的人读面。只移文件不重算，终态门会因时效或缺页对不上而失败。
3. `replace`（上传对账“替换”）：**旧 sidecar 原地不动、锚点不改**（`upload-reconciliation.md`：原件与锚点不可移动、重映射
   或删除）。新上传照常入档；在旧 sidecar 的清单行写 `superseded_by: <新文件的 file_id>`，新文件对应的 timeline 事件写
   `supersedes_event_id` 指向旧事件；摘要类字段（`current_status`、`latest_status`、段D）改取新文件，旧值与旧事件保留。
   然后同第 2 条对新来源做增量综合。`coexist`：两份都留、不写关系；`ignore`：新上传按 `user_excluded` 记进
   `skipped_inputs`，不转写。
4. `hold`：不动文件。
5. 追加一条 `update_log.json` 条目（§8 形状，经管道交给 `python3 "<skill_dir>/scripts/update_log_append.py" <patient_dir> --entry -` 追加（它写 `prev_sha256` 链接，§8；不要手写进文件））：`run_mode` 为本次的 `relevance_disposition` 或 `upload_reconciliation`，
   `workers[]` 为你自己（`phase: phase2`，`files` 列你处置过的项目句柄）加上本次转写新上传的 Phase 1 worker，`inputs[]`
   照抄上一个 `inputs` 非空的条目、加上移回临床桶或新入档的原件（同时列进 `added[]`），`removed[]` 列已删除项的句柄，
   `note` 逐项写“动作 + 句柄 + 确认原话（遮蔽个人信息后）+ actor_role”。删除项在 `source_inventory.json.skipped_inputs[]`
   中的记录保留，作为审计。不写 §8 以外的字段。

## 13. 复扫遮蔽模式（`run_mode: pii_remask`）

SKILL.md Step 12.5 的语义 PII 复扫（`pii-rescan-prompt.md`，worker `pii-<n>`）在**合成面或交付面**（`profile.json`、
`patient_summary.json`、`case_text.md`、`timeline.md`、`review_*.md`、`INDEX.md`、`source_inventory.json`、
`acute_findings.json` 等）上有发现时，编排者以此模式重派你，传入 `pii_findings`（`{file, line, category}`，不含值）。
sidecar 正文上的发现不归你：编排者把那份原件重派给单文件 Phase 1 worker 重写。你只做：

1. 逐条回到该文件该行，按含义把个人信息遮蔽为 `[PII_MASKED]` 或删掉它所在的非临床短语，不动任何临床字符；
   `profile.json.summary.one_line_condition` 改了就在返回 JSON 写明（编排者据此重跑 Step 13）；
2. 跑形状层 `python3 "<skill_dir>/scripts/pii_rescan.py" <patient_dir>`，直到它干净；
3. 在 `update_log.json` 追加一条 §8 形状的条目（经管道交给 `python3 "<skill_dir>/scripts/update_log_append.py" <patient_dir> --entry -` 追加（它写 `prev_sha256` 链接，§8；不要手写进文件））：`run_mode: pii_remask`，`workers[]` 列你自己（`phase: phase2`）和
   派你之前的复扫 worker（`phase: pii_rescan`，`files: []`），`inputs[]` 照抄上一个 `inputs` 非空的条目，
   `outputs[]` 写你改过的文件的新 `sha256`，`note` 只写改了几处、哪几类（不写值）。
