---
name: cancer-buddy-organize
description: "把患者的病历（PDF、照片、扫描件、Word、Excel、压缩包）整理成带出处的患者档案和一页病情简要总结。只记录报告写了什么，不推断诊断、分期、ECOG、疗效、线次或预后。Organize medical records into a source-traceable patient archive. Triggers on 病历整理, 整理报告, 帮我整理这些资料, 我有一堆检查单, 追加报告, organize medical records."
---

# 病历整理

把一堆病历变成一个档案：每页原文都转写成 Markdown，再汇总成结构化数据和一页《病情简要总结》。其他子 skill 都从这个档案里读。

红线和语气见 [guardrails](../cancer-buddy/references/guardrails.md)；档案格式见 [archive](../cancer-buddy/references/archive.md)。

## 怎么跑

所有命令：`python3 "<cancer-buddy 目录>/scripts/cb.py" organize …`（cancer-buddy 目录与本目录同级）。每个命令输出 JSON。

**进度只看 `next`。** 你不需要记住做到哪一步：任何时候（包括对话被压缩、子代理失败、会话中断之后）运行一次 `next`，照它说的做，做完再运行 `next`，直到它说 `review`。

1. **开始前问一句**：“除了这些，还有更新的检查或病历吗？有的话一起给我。”（非交互环境跳过）
2. **预处理**：`organize prepare <文件或文件夹…>`；已有档案加 `--patient <档案目录>`。新档案会自动建立。它会告诉你收录了几份、跳过了哪些（重复、空文件、打不开）。
3. **循环 `organize next <档案目录>`**，按 `stage` 做：
   宿主没有子代理工具时，你自己按顺序逐个执行任务文件，效果相同，只是慢一些。
   - `transcribe`：对 `tasks` 里的每个任务**并行**派一个子代理，提示词只写一句：“读取并严格执行 `<prompt_file>`”。全部返回后再 `next`。某个失败了不用管，`next` 会把没做完的页重新派出来。
   - `place`：运行 `organize place <档案目录>`。
   - `synthesize`：派一个子代理，提示词：“读取并严格执行 `<prompt_file>`”。
   - `finish`：运行 `organize finish <档案目录>`（检查、遮蔽身份信息、生成病情简要总结）。
   - `review`：进入第 4 步。
4. **给用户看结果**（`next` 返回的 `show` 里都有），按这个顺序：
   1. **急性发现**（有才说，放最前面）：逐条给报告原句、日期、哪份报告，说“这是报告里写到的、需要尽快告知治疗团队的发现”。标了转述的写明“转述，非报告原句”。不解释原因、不评轻重、不给处理建议。
   2. 一句话病情；资料覆盖了哪些方面；缺页；最新资料的日期（超过 14 天时，照 `warnings` 提醒“之后有没有新检查”）。
   3. `review_summary.md` 全文——请用户看看读得对不对。
   4. 需要核对的地方（`review_flags`，先 red 后 yellow）。说清楚：这是“这个字读得准不准”，不是病情轻重。
   5. `99_无关文件` 里的待确认项：逐项说是什么、为什么觉得无关，问用户留还是删；没回答就保留。
   6. 《病情简要总结.html》的路径：可以打印、可以转发给医生。
   7. 一句低压力的补料邀请（例如缺了病理报告），同一项最多问两次，用户说不用就不再问。

   `show.check_warnings` 里有“格式无法读取”或 `show.skipped_inputs` 里有“打不开”的，告诉用户哪几份没能读取（原件已保存），请他换个格式（如导出 PDF 或拍照）再给一次。重复的文件不用提。
   `show.unresolved_check_errors` 不为空时，如实说“档案里还有 n 处没对上，已标记”，不要反复重跑。

## 追加资料

新文件来了：`organize prepare <新文件> --patient <档案目录>`，然后同样循环 `next`。只有新文件需要看图转写；汇总会整体重跑（只读文字，很快）。

## 用户在对话里补充的信息

用户说“我上周开始吃 XX 药”“医生说下个月复查”：先把你要记下的内容给用户看一眼（“我会记为：患者自述……，对吗？”），用户确认后：

`organize note <档案目录> --layer patient_reported --bucket 08 --text "<确认后的原话>" [--date YYYY-MM-DD]`

家属说的用 `caregiver_reported`。它会作为自述记录单独存放，不会覆盖报告原文；然后 `next` 会要求重新汇总。

## 移动或删除

- 放错抽屉：`organize move <档案目录> <转写稿路径> <抽屉>`。
- 用户逐项确认删除无关文件：`organize discard <档案目录> <99_… 路径> --confirm "<用户原话>"`。原件始终保留在 `raw/`。

## 老档案（v1 建的）

直接 `organize prepare --patient <档案目录>`（不带新文件也行）：旧转写稿会移到 `raw/_legacy_<时间>/` 保留，原件重新按新方式转写一遍。先告诉用户这会花一些时间。

## 不要做

- 不要自己写档案里的 JSON、Markdown 或 HTML——转写和汇总交给子代理，HTML 由 `finish` 生成。
- 不要删除用户的输入文件夹或 `raw/` 里的任何东西。
- 整理过程中不要修改本 skill 的文件。
