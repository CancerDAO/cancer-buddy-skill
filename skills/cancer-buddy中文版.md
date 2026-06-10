organize

```
---
name: cancer-buddy-organize
description: "将患者的病历资料（PDF/图片/docx）整理到规范的 patients/<患者代码>/ 目录下，包含 profile.json、timeline.md、readiness.json、OCR侧车文件，以及 01_当前状态…11_诊断证明 等分类桶。当用户交给你一个病历文件夹，或说“病历整理”、“我有一堆报告，帮我整理报告”时使用。对于多住院档案（≥30 个文件）：采用扇出方式并行执行 Phase-1 OCR 工作器（每个源子目录一个），再通过 Phase-2 合成工作器进行规约，执行跨切片 review_flags 审计。对于小规模/扁平输入：采用单次传递。"
---

# cancer-buddy-organize

将原始病历转化为结构化数据，供其他子技能使用。

## 何时使用

- 用户提供文件夹路径或一组文件（PDF、JPG、PNG、DOCX、ZIP）。
- 用户问：病历整理 / 帮我整理这些报告 / 我有一堆检查单。
- 任何其他子技能检测到缺失 `profile.json` / `readiness.json`，并提示用户先运行 organize。

## 输入

- 文件夹路径，或单个 PDF/DOCX，或压缩包（zip/rar/7z/tar.gz）。

## 输出

写入 `patients/<患者代码>/` 目录下：

- `INDEX.md`（第一行：`# patient_code: <代码>`）
- `profile.json`（遵循 `../../references/patient-profile-schema.md`）
- `timeline.md`（人类可读的治疗时间线）
- `readiness.json` —— 覆盖度等级 + `review_flags[]`（MTB 就绪 + 可疑值审计）
- `review_flags.md` —— 自动生成的人类可读版 `readiness.json.review_flags[]`（仅当数组非空时写入）
- `review_summary.md` —— **始终写入**：一页检查清单，包含提取的关键字段及逐字源引用，供用户快速核对（可捕捉 review_flags 无法发现的“一致但错误”的 OCR 问题）
- `case_text.md`（整合的叙事文本）
- `01_当前状态/` … `11_诊断证明/`（原始文件分类桶）
- `ocr/`（带有 SOURCE/CONFIDENCE 头部的 OCR 侧车文件）

## 工作流

1. **解析输入** —— 与用户确认其提供的路径。对于压缩包，先解压到 `/tmp/cb-unpack-$$/`（支持 zip / rar / 7z / tar.gz / 单个 pdf-or-docx）。解压后的 **解析输入目录**（`$src`）是第 2 步规划的对象。

2. **规划切片（单次传递 vs 扇出）** —— 对 `$src` 进行 glob 获取直接子目录，统计文件数，决定切片边界。

   **每个 Phase-1 工作器最多处理 15 个图片文件。** Claude 在单个上下文中加载大量图片时有会话总图片预算限制。一个工作器试图在一次调度中 OCR 超过 25 个 HEIC 图片，会在处理到一半时触发“An image in the conversation exceeds the dimension limit for many-image requests”并终止，输出部分结果。（经验观察：24 张图片的切片在第 5/24 个侧车文件时失败。）

   切片规则：

   - **单次传递模式**：总文件数 ≤ 15 → 一个 Phase-1 工作器
   - **子目录扇出**：存在 ≥2 个子目录 **且** 每个子目录文件数 ≤ 15 → 每个子目录一个工作器
   - **子目录扇出 + 内部分割**：存在 ≥2 个子目录 **且** 任一子目录文件数 > 15 → 将每个超大子目录平分成两半或三份（如 `h1_part1`/`h1_part2`），每份一个工作器。典型场景：3 次住院共 73 张图片，每份 ~25 张 → 6 个工作器（每次住院拆成两半，每半 ~12-13 个文件）。
   - **扁平扇出**：无子目录，文件数 > 15 → 按 N 个文件一组分割（按字母顺序或任意顺序），切片命名为 `batch_a`/`batch_b` 等。

   各切片的工作器并行运行（单条消息，N 个并发的 Agent 工具调用）。工作器内部，文件顺序处理。

   确定 `patient_code`：调用者提供 或 自动生成 `PT-<hex>`（基于 `basename + mtime` 的哈希）。解析 `patient_data_root` 来源：`$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`。计算 `patient_dir = <patient_data_root>/<patient_code>`，并 `mkdir -p` 其 11 个桶 + `ocr/` + `10_原始文件/`。

3. **调度 Phase-1 OCR 工作器（并行）** —— 对每个切片，在一个 **单条消息中包含 N 个工具调用**（使它们并发执行，而非顺序执行）的方式调度一个 `general-purpose` 子代理。每个工作器获得：

   - `subagent_type: general-purpose`
   - `description: "Organize OCR slice <slice_id>"`
   - `prompt`：[`references/organizer-prompt-phase1-ocr.md`](references/organizer-prompt-phase1-ocr.md) 的完整内容，并在末尾附加以下 `## Call parameters`：
     - `slice_input_path: <切片源目录的绝对路径>`
     - `slice_id: <简短的逻辑标签 — 例如 h1, h2, batch_a>`
     - `patient_dir: <绝对路径 patient_dir>`
     - `original_subdir: <在 10_原始文件/ 下的相对路径，用于存放审计副本 — 通常是源子目录的 basename>`

   每个 Phase-1 工作器 **只写入** `<patient_dir>/ocr/`（侧车文件）和 `<patient_dir>/10_原始文件/<original_subdir>/`（审计镜像）。它们 **不碰** INDEX.md / timeline.md / profile.json 等 —— 那些是 Phase-2 的任务。工作器之间不共享上下文，因此从结构上强制执行了“防锚定”（每个工作器仅看到自己的切片，不会跨住院累积叙事）。

   每个工作器返回：`{slice_id, files_processed, sidecars_written, stub_sidecars, full_ocr_sidecars, ocr_uncertain_files, candidates_files, continuation_needed, continuation_resume_from}`。

4. **Phase-1 续跑循环** —— 对于每个返回 `continuation_needed: true` 的工作器，为该切片调度一个续跑工作器：

   > “恢复对 `<patient_code>` 的切片 `<slice_id>` 的 Phase-1 OCR。前一次调度处理到 `<continuation_resume_from>` 并停止。跳过所有侧车文件已存在于 `<patient_dir>/ocr/` 中的文件（这些文件的修改时间已低于源文件）；对 `<slice_input_path>` 中剩余的所有文件进行 OCR。返回相同的 JSON 契约；如果完成则设置 `continuation_needed: false`，如果上下文再次填满则设置 `true` 并给出下一个恢复点。”

   对每个切片循环，直到所有切片报告 `continuation_needed: false`。已完成且干净的切片无需重新调度；只有落后的需要续跑。这比重新调度整个 organize 更高效。

5. **调度 Phase-2 合成工作器** —— 在所有 Phase-1 工作器都报告 `continuation_needed: false` 后，调度 **一个** `general-purpose` 子代理进行合成：

   - `subagent_type: general-purpose`
   - `description: "Organize synthesis"`
   - `prompt`：[`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md) 的完整内容，并在末尾附加以下 `## Call parameters`：
     - `patient_dir: <绝对路径 patient_dir>`（当前的引导路径；Phase-2 可能在步骤 1.7 中重命名该目录）
     - `phase1_summary: <所有 Phase-1 工作器结果的 JSON 列表>`

   Phase-2 读取所有侧车文件（跨切片），使用 **原始 basename** 进行分类到 11 个桶（步骤 1），然后基于 OCR 文本本身判断每个文件的 `{date, doc_type, 机构, page}` 以及患者级别的 `{cancer_label, first_dx_date}`，并写入 `.rename_plan.json`（步骤 1.5 —— 语义判断，不使用硬编码词汇表），原子地重命名物理文件 + 侧车文件 + 回填 `source_manifest.tsv`（步骤 1.6 —— 机械化的 bash，原子操作并处理冲突后缀），并且当 OCR 能识别出癌症类型时，将 patient_dir 自身重命名为 `<cancer>_<YYYY-MM>_<hash4>`（步骤 1.7）。只有在完成规范命名之后，Phase-2 才构建 INDEX.md / timeline.md / case_text.md / profile.json / readiness.json，执行 §4.6 的 review_flags 审计，并写入 review_flags.md（若非空）和 review_summary.md（始终写入）。

   Phase-2 返回：`{role, patient_dir, patient_dir_original, patient_dir_renamed, files_classified, files_renamed_canonical, files_renamed_skipped, rename_plan_path, ocr_sidecars_read, coverage_complete, missing_sidecars, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path}`。`patient_dir` 字段是重命名后的路径；如果调用者仍持有引导时的 `PT-<hex>` 路径，应使用 `patient_dir`（而非原始路径）进行任何下游操作。

6. **覆盖度缺口重试** —— 如果 Phase-2 返回 `coverage_complete: false`，则调度一个重试性的 mini-Phase1 工作器，仅以缺失的文件作为输入，然后重新运行 Phase-2。循环直到 `coverage_complete: true`。大多数运行在 0 或 1 次重试内收敛。

7. **验证输出** —— 解析 Phase-2 返回的 JSON；确认 `profile.json` 存在且所需字段（`patient_code`, `primary_cancer`, `histology`, `stage`）已填充。如果有任何缺失或为 null，在路由到其他子技能之前向用户展示为阻塞项。

8. **等级 readiness** —— 从 Phase-2 返回的 JSON 中取 `readiness_grade` 和 `readiness_score`。如果等级为 F 或 D，向患者展示信息缺口清单 🔴🟡🟢（来源于 `blocking_gaps`）。

9. **展示 review_summary.md（强制，始终执行）** —— 读取 `review_summary_path` 处的文件，并将其完整内容展示给用户。这是 organize 后用户看到的 **第一项** 内容 —— 在 profile 卡片、review_flags 之前。它是一页检查清单，包含提取的关键字段及逐字源引用。

   为何这是第一展示内容：许多真实的 OCR 错误会产生 **内部一致但错误的值**（例如某次住院的 7 份文档都被 OCR 成同一个错误的药名）。`review_flags` 的 5 项检查无法检测到这种情况 —— 但人类阅读 `review_summary.md` 可以在 30 秒内发现一个错误字符。

   展示后，提示用户：“请核对上面 5 个检查要点。任何字段需要修正，直接告诉我哪个字段 + 正确值，我会更新 profile.json 并重新生成清单。”

10. **展示 review_flags（强制）** —— 如果 `review_flags_total > 0`，读取 `review_flags.md` 并在 `review_summary.md` 之后立即展示其内容。这是一个硬性门控，不是可选的润色：

    - **如果存在任何 🔴 红色标志**：告知用户“进入下游技能之前请先逐条确认或 override 这些 🔴 项 — 它们会直接影响 trial-match / mtb-lite / vmtb 的推荐”
    - **如果仅有 🟡/🟢 标志**：展示为“建议核对”，不阻塞下游路由
    - **如果 `review_flags_total: 0`**：仍然告知用户“所有提取字段已通过 5 项可疑值检查（格式/跨文档矛盾/临床逻辑/原始证据/数值趋势），无待确认项 — 但仍请核对上面的 review_summary.md 速查清单”
    - 用户对每个标志的解决（`accept_suggestion` / `keep_original` / `custom_value` / `defer`）将被记录回 `readiness.json.review_flags[i].user_confirmed = true` 以及一个 `resolution` 子对象。

11. **输出 profile 卡片** —— 使用 `terminology.md` 的格式规则（中英 + 通俗解释）向患者展示患者概要卡片（[references/profile-card.md](references/profile-card.md)）。卡片中的“🔍 待人工确认”部分来源于 `readiness.json.review_flags[]`。

    **下游门控**：只要有任何 🔴 红色 review_flag 未被确认，就 **不要** 将用户路由到任何下游子技能（mtb-lite / trial-match / vmtb / nutrition / education）。在此阶段一个错误的药名会污染所有下游报告。

## 为什么采用扇出 + 规约而不是单次传递

原始设计是一个子代理顺序处理每个输入文件。一个 73 张图片的档案耗时约 33 分钟。拆分为 Phase-1（每切片并行 OCR）+ Phase-2（跨切片合成 + 审计）带来三个好处：

1. **速度**：3 个并行的 Phase-1 工作器 + 1 个 Phase-2 完成时间约等于最慢切片的时间 + 合成传递时间 —— 实践中在多住院档案上快约 3 倍。
2. **防锚定更强**：每个 Phase-1 工作器只看到自己的切片（一次住院），因此模型可能锚定的叙事窗口更短。跨切片矛盾会在 Phase-2 的 §4.6 审计中被显式捕捉（该审计具有确定性的跨文档检查），而不是被单个代理的连续叙事所掩盖。
3. **更好的故障隔离**：如果一个切片的工作器遇到上下文耗尽，只有那个切片会重试（续跑循环）。已干净完成的切片不会被重新调度。

对于小规模输入（<30 个文件或没有子目录），保留单次传递 —— 并行开销不值得。

## patient_code 冲突

如果生成的 `patient_code`（例如 `PT-17CE02BC33`）在 patients 根目录下已存在，子代理会追加 `_2`、`_3` 等，并在摘要中告知分配的代码。

## 可配置的根目录

`patients/` 根目录按以下顺序解析：`$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`。导出其中任意一个即可覆盖。与 vmtb-skill 共享。

## 安全性

Organize 不做医疗建议。但仍然：

- 绝不捏造字段 —— 当源文件中某值确实无法读取时，子代理写入 `null`（JSON）或 `[OCR_UNCERTAIN]`（文本），并将其作为缺口展示。
- 下游子技能在读取 organize 生成的内容时会应用完整的 `safety-guardrails.md` 规则集；此处错误的数据会污染每一个下游报告。
- `10_原始文件/` 是审计追踪 —— 始终是每个源文件的字节级完全镜像。

## 下一步指导

成功执行 organize 后，根据用户的初始问题将患者路由到最相关的下一子技能：

- 新确诊、想了解 → `cancer-buddy-explore`（最大诊断层级）
- 有基因报告、寻求治疗指导 → `cancer-buddy-mtb-lite`
- 寻找临床试验 → `cancer-buddy-trial-match`

## 角色行为

权威矩阵见 `../../references/roles.md`。针对本技能：

- **角色 = 患者**：第一人称。“帮我整理我的病历” → 生成 profile.json / timeline.md / readiness.json。Profile 的 `data_sources[]` 中将患者列为来源。
  - *信息披露*：患者入口处 disclosure_state=suppressed → 警告 organize 很可能破坏抑制状态；仅在确认后继续。
- **角色 = 照护者**：第二人称。“帮你家人整理报告”。在首次为此 patient_code 执行 organize 时，主动询问是否在 `profile.json.caregivers[]` 中填入照护者的关系、姓名和联系方式偏好。语气更温暖，包含“整理这些很累吧，一步一步来”之类的体谅。
- **角色 = 家属**：拒绝。输出：`病历整理要靠主照护者操作（Ta 手里有原件）。要不要我帮你生成一份 2 页要点让 Ta 参考？` 不执行 organize。

## 参考资料

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) —— Phase-1 工作器提示：逐切片 OCR，并行安全，仅写入侧车文件
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) —— Phase-2 工作器提示：跨切片合成 + 步骤 1.5–1.7 规范命名（语义判断 + 原子 bash mv）+ review_flags 审计 + review_summary
- [profile-card.md](references/profile-card.md) —— 患者概要卡片展示模板
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) —— 与 vmtb-skill 共享的 schema 契约
- [../../references/preflight.md](../../references/preflight.md) —— 共享入口门控（角色 + 信息披露 + readiness 等级 + 步骤 2.5 review_flags 红色门控 + schema 有效性）
- [../../references/terminology.md](../../references/terminology.md) —— 中英 + 通俗解释格式
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md) —— 安全护栏
```

organizer-prompt-phase1-ocr.md

```

```

organizer-prompt-phase2-synthesis.md

```

```

 病例总结

````
# Patient Profile Card Template

## Patient Profile Card

```
═══════════════════════════════════════════════
  患者档案 | PATIENT PROFILE CARD
═══════════════════════════════════════════════

【基本信息 | BASICS】
  姓名/ID:        ___
  年龄/性别:       ___岁 / 男|女
  身高/体重/BSA:   ___cm / ___kg / ___m²
  ECOG评分:        ___
  合并症:          ___

【诊断 | DIAGNOSIS】
  癌种 Cancer Type:     ___
  病理分型 Histology:    ___
  分期 Stage:            ___ (TNM: T_N_M_)
  转移部位 Metastases:   ___
  确诊日期:              ___

【分子特征 | MOLECULAR FEATURES】
  驱动突变 Driver Mutations:
    - Gene: ___ | Variant: ___ | VAF: ___% | Actionability: ___
  免疫标志物 Immune Markers:
    - MSI/MMR:   ___ (MSS/MSI-H/dMMR)
    - PD-L1:     TPS ___% / CPS ___
    - TMB:       ___ mut/Mb
  其他关键变异:
    - ___

【治疗史 | TREATMENT HISTORY】
  Line 1: [方案] | [开始-结束] | 最佳疗效: CR/PR/SD/PD | 关键毒性: ___
  Line 2: [方案] | [开始-结束] | 最佳疗效: ___         | 关键毒性: ___
  Line N: ...
  当前治疗: ___ (第___周期, 末次___日)

【当前状态 | CURRENT STATUS】
  疾病状态:    进展/稳定/缓解
  关键指标趋势: ___
  主要症状:    ___
  器官功能限制: 肾___  肝___  骨髓___  心___

【信息缺口 | INFORMATION GAPS】
  (覆盖度 — 缺什么. 来源: readiness.json.blocking_gaps)
  🔴 关键缺失 (影响治疗决策):
    - ___
  🟡 建议补充 (提升精准度):
    - ___
  🟢 已充分:
    - ___

【待人工确认 | REVIEW FLAGS】
  (可信度 — 已提取但可疑. 来源: readiness.json.review_flags[])
  🔴 影响下游推荐 (进入 trial-match / mtb-lite 前必须确认):
    - [RF-NNN] field=___, 现写="___", 可疑点: ___
      建议: ___ ⬜ 接受 / ⬜ 保留原写 / ⬜ 自定义
  🟡 建议核对:
    - ___
  🟢 提示:
    - ___
═══════════════════════════════════════════════
```

## Display rules

- "信息缺口" 是覆盖度（缺什么），"待人工确认" 是可信度（写得对不对）—— 两个是不同失败模式，必须分开展示
- 当 `readiness.json.review_flags[]` 为空数组 → 显示 "✅ 所有提取字段已通过 5 项可疑值检查"
- 当存在 🔴 项 → 在 Card 末尾追加: "进入下游 skill 之前请先逐条确认 🔴 项, 它们会直接影响推荐结果"
- 用户的逐项决定 (accept_suggestion / keep_original / custom_value / defer) 写回 `review_flags[i].user_confirmed`
````

cancer-buddy-caregiver

```
---
name: cancer-buddy-caregiver
description: "为癌症旅程中的主要照护者（配偶/父母/成年子女）提供操作级支持。包括化疗陪护清单、家庭分工模板、Zarit 照护负担自测量表、如何与孩子沟通、哀伤准备。同时以简洁摘要模式为其他家庭成员提供服务。拒绝患者角色并引导重定向。触发词：家属, 陪护, 照护者, burnout, 我在照顾, 我爸/妈/爱人得癌症, 怎么陪诊, 我太累了。"
---

# cancer-buddy-caregiver

癌症治疗真正的操盘手往往是配偶或成年子女。本技能为他们提供临床医生很少给予的东西——实用的清单、分担负担的框架、照顾自己的许可，以及为艰难时刻所做的准备。

## 何时使用

- 用户在元技能中选择角色为 caregiver 或 family。
- 用户说：家属 / 陪护 / burnout / 我是照顾者 / 我太累了 / 怎么陪诊 / 我爸妈/爱人生病了。
- 任何子技能检测到照护者特定的痛苦并路由至此。

## 预检

按照 `../../references/preflight.md`：角色必须是 caregiver 或 family。如果是 patient → 拒绝 + 提供“给家人看的要点”2 页摘要。

## 工作流

确定照护者需要什么：

1. **首次使用** → 提供引导 + 基线 Zarit 筛查（见 [references/zarit-burden.md](references/zarit-burden.md)）。主动询问是否在 `profile.json.caregivers[]` 中填入其姓名、关系和联系方式。
2. **化疗/放疗/手术前一天** → [chemo-companion-checklist.md](references/chemo-companion-checklist.md)。
3. **希望分担负担** → [family-roles-template.md](references/family-roles-template.md)：谁负责跑医院，谁负责取药，谁负责情绪关怀，谁负责财务。输出可分享的家庭文档。
4. **孩子问发生了什么** → [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md)（适龄语言）。
5. **“我已经精疲力尽了”** → Zarit > 21 或明确的自杀意向陈述 → 路由到 `cancer-buddy-mind` 的 caregiver-distress 分支。不要让照护者只和你对话。
6. **为坏消息做准备** → 提供情感预承诺的温和框架，不显得病态：“你想不想花 10 分钟想一下，如果接下来复查不好，你希望 Ta 得到什么？你希望你自己怎么被对待？”

## 角色行为

- **角色 = 患者**：拒绝 + 提供本 caregiver 技能的 2 页摘要，让患者拿给其照护者看。不执行工作流。
- **角色 = 照护者**：主工作流。所有内容以第二人称对照护者说话；30% 权重放在自我关怀提示上。
- **角色 = 家属**：简洁版本。聚焦于“如何在不增加负担的情况下支持主要照护者”。跳过 Zarit 深挖；跳过化疗陪伴清单。

## 输出

写入 `patients/<patient_code>/reports/caregiver/` 下：

- `zarit-YYYY-MM-DD.md` — 纵向负担分数
- `chemo-prep-YYYY-MM-DD.md` — 每次陪护日的清单
- `family-roles.md` — 可编辑的分工文档
- `explaining-to-children.md`（如调用）

## 安全性

- 危机规则适用（来自 `safety-guardrails.md` 角色特定部分）：照护者有自杀陈述 → 转交给 `cancer-buddy-mind` 并执行完整危机协议。
- 绝不羞辱燃尽感。绝不说“你应该为 Ta 更强”。燃尽感是对非理性情境的理性反应。
- 绝不鼓励向患者隐瞒信息。

## 参考资料

- [chemo-companion-checklist.md](references/chemo-companion-checklist.md)
- [family-roles-template.md](references/family-roles-template.md)
- [zarit-burden.md](references/zarit-burden.md) — 22 项 Zarit 照护负担访谈量表（已验证）
- [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md)
- [../../references/roles.md](../../references/roles.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
```

disclosed

```
---
name: cancer-buddy-disclosure
description: "面向中国家庭情境的诊断披露协商。读写 profile.disclosure_state 及 disclosure_history[]。模拟分层披露（渐进式，非二元），提供分年龄段话术（年迈父母/配偶/子女/青少年患者），处理“患者突然问起”的场景，进行能力评估（痴呆症单独处理），明确何时联系医务社工或伦理委员会。角色感知：患者（反转情形——告诉家人），照护者（主要），家属（其他亲属决策）。安全规则：当患者具备知情能力且有知悉意愿时，绝不越权替代患者自主权；绝不鼓励永久欺骗；绝不羞辱家庭的初始隐瞒行为。触发词：要不要告诉，不想让 Ta 知道，Ta 不知道自己得癌，瞒着，告诉，知情同意，他爸妈不让说，披露，disclosure。"
---

# cancer-buddy-disclosure

中国家庭常常向患者隐瞒癌症诊断。出于爱，出于恐惧，出于习惯。本技能不评判这个起点——它帮助家庭将隐瞒→部分披露→完全披露作为一个过程而非一个事件来推进。“要么全说，要么全瞒”的二元选择是反模式。以分层披露、配合患者的知悉意愿进行节奏安排才是正确模式。

## 何时使用

- 照护者询问是否要告诉患者（“告不告诉我妈她得癌了？” / “他爸妈不让说”）
- 患者难以告诉家人（反转情形——年轻患者，年迈父母/配偶/子女）
- 其他家属得知诊断后，在尊重或打破隐瞒之间感到矛盾
- 患者主动问家人“我是不是癌症？” / “我是不是要死了？”
- 任何子技能检测到披露状态问题并路由至此（例如舒适/生存/探索在 `active_role = patient` 且状态为 `suppressed` 时受阻）
- 用户说：要不要告诉 / 不想让 Ta 知道 / Ta 不知道自己得癌 / 瞒着 / 告诉 / 知情同意 / 他爸妈不让说 / 披露 / disclosure

## 预检

- 角色解析（读取 `patients/<patient_code>/role.json`）
- 就绪等级 ≥ C（患者档案已有足够结构化数据可进行推理——至少要有诊断信息）
- Schema 有效性（`profile.json` 通过 `validate-profile-schema.sh`）
- 没有披露门控——这本身就是披露技能。无论当前 `disclosure_state` 为何，始终允许进入。

## 工作流

1. **明确当前状态。** 患者目前知道什么？家属想要什么？谁在问，为什么问？读取 `profile.disclosure_state` + `disclosure_history[]` 的末尾记录。解析当前活动角色。
2. **评估患者知情能力。** 若存在痴呆/谵妄/严重认知障碍 → 切换到 [references/capacity-and-surrogates.md](references/capacity-and-surrogates.md) 代理决策轨道。不要对有认知障碍的患者应用针对成人的披露逻辑。
3. **若知情能力完好**：
   - 询问患者是否想知悉。家属往往从未问过这个问题；许多中国患者的知悉意愿比成年子女以为的要强。
   - 应用 [references/layered-disclosure-model.md](references/layered-disclosure-model.md)——基础诊断 → 预后 → 治疗方案 → 姑息支持，每个层次按节奏推进。
   - 根据 [references/age-specific-disclosure.md](references/age-specific-disclosure.md) 和 [references/family-scripts.md](references/family-scripts.md) 生成适合年龄和关系的话术。
4. **写入 `profile.disclosure_state`**（`suppressed` / `partial` / `full` / `unknown`），并在每次状态转换后 **追加到 `disclosure_history[]`**：谁决定的、哪个层次、何时、为何。所有分层模型中的每一步都要记录。
5. **当患者主动问起时**（例如“我是不是癌症？”）：家属不需要立刻说谎，也不需要当即强制完全披露。使用 [references/when-patient-asks.md](references/when-patient-asks.md) 中的转场话术；如果患者在数日内同问 ≥3 次，将其视为知悉意愿信号，并开始一个披露层次的过渡。
6. **需要专业调解时**：家属内部意见不一，且患者有知情能力+知悉意愿 / 患者与代理人之间发生争议 / 痴呆症且家属观点冲突 / 涉及预嘱的法律问题。建议联系医务社工、安宁缓和医疗团队或医院伦理委员会（医务处/伦理委员会）。

## 输出

在 `patients/<patient_code>/reports/disclosure/` 下生成：

- `negotiation-notes.md` — 家庭内部讨论记录（谁有什么感受，隐瞒的动因是什么，已经尝试过什么方法）
- `family-scripts-drafted.md` — 为下一次披露时刻草拟的话术，根据说话者→听者的关系定制
- `decision-log.md` — 每次 `disclosure_state` 转换的记录，包含决策者、层次、时间、原因

同时写入 `profile.disclosure_state` 并追加到 `profile.disclosure_history[]`。绝不静默覆盖历史；每次转换都是带时间戳和理由的追加操作。

## 角色行为

- **角色 = 患者（反转情形）**：患者负责将自己的诊断告诉家人——例如年轻患者向年迈父母、配偶或子女告知病情。生成第一人称话术。患者决定分享什么；本技能帮助他们安排顺序、选择措辞。无披露门控——患者本人已知情。
- **角色 = 照护者（主工作流）**：照护者在决定是否、如何、何时告诉患者，并为此感到挣扎。承认隐瞒背后的爱与恐惧，但不支持无限期隐瞒。提供分层递进方案，使其不需要一次艰难的对话就能向前走。
- **角色 = 家属（其他亲属）**：其他亲属得知诊断后，不确定是尊重主要照护者的隐瞒安排还是打破它。尊重照护者的操作角色（他们日常协调照护），但如果患者有知情能力+知悉意愿，则重申患者自主权。当照护者与家属意见不合时，引导至专业调解，而不站队。

## 安全规则

1. **当患者有知情能力且想知悉时，绝不替代患者自主权。** 家属的意愿——无论出于多少爱——都不能凌驾。本技能展示分层选项，但绝不认可“然后我们就永远不告诉 Ta”。
2. **绝不鼓励永久欺骗。** 分层（暂时的、有节奏的）披露是可行的，常常也是人道的。一旦患者明确发出知悉意愿信号，永久隐瞒就不被支持。描述过渡：现在隐瞒 → 稍后部分披露 → 当患者自己的问题要求时再更完整披露。
3. **绝不羞辱家属的初始隐瞒行为。** 在中国家庭文化中，隐瞒往往是出于爱的起点；羞辱它会关闭对话。接纳家庭当前状态，帮助他们前进。
4. **痴呆/能力受损属于独立轨道。** 不要对有认知障碍的患者应用成人披露规则。转到 `capacity-and-surrogates.md`；决策变成代理人决策，遵循代理人层级，以最佳利益和已知既往意愿为标准。
5. **伦理委员会/社工**适用于以下情况：（a）家属内部意见不一，且患者有知情能力+知悉意愿；（b）痴呆症案例中患者-代理人冲突；（c）法律/预嘱问题超出家庭范围。明确建议 医务社工 / 医务处 / 伦理委员会 —— 不要在聊天中尝试调解临床伦理争议。

## 参考资料

- [right-to-know-china-law.md](references/right-to-know-china-law.md) — 执业医师法第22条，侵权责任法/民法典侵权编，患者知情权的实践现状
- [layered-disclosure-model.md](references/layered-disclosure-model.md) — 递进，而非二元
- [age-specific-disclosure.md](references/age-specific-disclosure.md) — 年迈父母/配偶/子女/青少年患者
- [family-scripts.md](references/family-scripts.md) — 5种关系配置的话术
- [when-patient-asks.md](references/when-patient-asks.md) — 家属如何处理患者的自发提问
- [capacity-and-surrogates.md](references/capacity-and-surrogates.md) — 痴呆症与代理决策轨道
- [../../references/preflight.md](../../references/preflight.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md) — 披露特定的规则
- [../../references/disclosure-behavior.md](../../references/disclosure-behavior.md)
```

宣传手册

```
---
name: cancer-buddy-education
description: "根据 MTB 报告和患者档案生成患者友好型教育手册（含 Mermaid 图表的 Markdown）。包含速查卡、通俗版健康摘要、带副作用管理的药物说明、日常生活指导、随访计划、费用/保险指引、常见问题。吸收机制图、癌种模块和按阶段整理的 FAQ（来自 vmtb-patient-education）。触发词：宣教手册，给我爸妈看的版本，patient handbook，患者教育。"
---

# cancer-buddy-education

将临床输出转化为患者（及其家人）日常真正能用的东西。

## 何时使用

- 患者至少拥有 `profile.json` + 一份 MTB 报告（精简版或完整版）。
- 患者说：宣教手册 / 给我爸妈看的版本 / 我爸妈看不懂报告 / patient handbook。

## 预检

执行 [../../references/preflight.md](../../references/preflight.md) —— 角色 + 披露状态 + 就绪等级 + **review_flags 红色门控（步骤 2.5）** + schema 有效性。手册会将上游提取的事实（诊断、分期、当前治疗、分子驱动因素、治疗史）以权威性教育内容的形式直接传播给患者/照护者；这些字段中任何一个未经确认的 🔴 红色 review_flag 都会使生成的手册产生误导。在问题解决之前保持阻塞。

## 输入

- `patients/<pid>/profile.json`
- MTB 报告：优先使用 `patients/<pid>/reports/mtb-full/` 中的报告；回退使用 `patients/<pid>/reports/mtb-lite/`。
- 治疗时间线、合并症、当前用药。

## 输出

写入 `patients/<pid>/reports/education/` 目录下：

- `<pid>_<date>_患者教育手册.md` —— 主手册
- `quick-reference-card.md` —— 包含紧急信息和关键联系人的一页纸
- `drug-sheets/<drug>.md` —— 每种药物的单页说明（机制、剂量、副作用、何时联系医生）

## 工作流

完整模板见 [references/handbook-template.md](references/handbook-template.md)。主要步骤：

1. 读取 MTB 报告（优先完整版，回退精简版）。
2. 提取：治疗计划、药物清单、监测计划、合并症相互作用。
3. 根据患者情况选择相关手册章节（如果只有免疫治疗则跳过化疗章节，如果合并 2 型糖尿病则包含糖尿病章节等）。
   - **机制图**：根据患者 `current_therapy` 类型（化疗/靶向/免疫/放疗）从 `references/mechanism-diagrams.md` 中拉取相关图示。
   - **癌种模块**：从 `references/cancer-type-modules.md` 中包含患者原发癌种的部分。
   - **常见问题**：根据当前治疗阶段（新确诊/积极治疗/康复期）从 `references/expanded-faq.md` 中拉取阶段相关的问题。
4. 使用 Markdown 渲染：
   - 封面页（姓名、patient_code、日期、医生联系方式）
   - 速查卡（紧急电话、急诊指征 —— 体温 > 38.5°C、新发出血等）
   - 我的健康摘要（1 页，通俗语言）
   - 每种药物的单页说明（作用、服用方法、副作用观察清单）
   - 日常生活指南（营养占位符 —— 完整版见 v2 营养技能、运动、睡眠、工作）
   - 随访计划（来自 cancer-buddy-manage 的监测日历）
   - 费用和保险指引（参考 [../../cancer-buddy-access/references/access-pathways.md] 的药物获取 + 保险部分）
   - 常见问题（按疾病阶段分组汇总的患者常见问题）
5. 嵌入 Mermaid 图表：疾病机制流程图、治疗决策树。

## 语气

- 温暖、直接、实用。像一位有医学知识的朋友在说话。
- 每个医学术语均为双语 + 通俗解释（见 `terminology.md`）。
- 章节末尾：“你家里有人能帮你执行这一段吗？不行的话，搭子可以帮你安排提醒。”

## 安全性

应用 `safety-guardrails.md` 规则：

- **每个手册、速查卡和药物单页上必须包含的页脚**：`本手册为信息参考，任何治疗调整必须与主诊医生确认。`
- **不作医疗建议** —— 解释药物/检测/副作用是什么，绝不要在没有医生许可的情况下指导患者改变剂量、停药或跳过复诊。
- **急诊指征是绝对的** —— 体温 > 38.5°C、新发出血、严重呼吸困难、意识状态改变 → `立即就医，不要等门诊`。

## 角色行为

- **角色 = 患者**：患者自学手册。第一人称，包含我的健康摘要、药物单页、日常生活指南。
  - *信息披露*：disclosure_state=suppressed → 拒绝提供患者手册；仅提供通用健康内容。
- **角色 = 照护者**：照护者操作手册。结构相同但重新组织为：“你陪 Ta 做化疗当天需要准备…”、“Ta 的化疗药清单 + 你该留意的红旗症状”、“如果你是一个人陪诊的话…”。增加 `## 你的自我照顾` 章节（1 页）。
- **角色 = 家属**：2 页亲友简报。疾病名称 + 通俗解释、当前治疗阶段、一句话预后、“你能帮上的三件事”、“请不要做的三件事”（不问“还有多久”、不提新的偏方、不与其他病友比较）。

## 参考资料

- [handbook-template.md](references/handbook-template.md) —— 完整模板
- [mechanism-diagrams.md](references/mechanism-diagrams.md) —— 疾病机制 Mermaid 图（来自 vmtb-patient-education）
- [cancer-type-modules.md](references/cancer-type-modules.md) —— 按癌种区分的患者模块
- [expanded-faq.md](references/expanded-faq.md) —— 按治疗阶段组织的常见问题
- [../../references/terminology.md](../../references/terminology.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
```

