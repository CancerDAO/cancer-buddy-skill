# Runtime Binding — Claude Code(参考实现 / reference binding)

> Claude Code 是交互式参考实现。它用 `Agent` 扇出、in-agent `Read`、本地 adapter 命令和 inline 确认卡来满足 `organize-contract.md`。这些是机制,不是契约;契约要求所有 host 都满足同一行为不变量。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | Claude Code 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | `Agent` 并行扇出 Phase1 LLM ingestion,单 `Agent` 做 Phase2 reduce |
| 抽取输入源 | 确定性抽取保留原始字符层；LLM 只做版面/候选纠错/语义辅助 | OCR/parser 输出、引擎版本和 source span 均保留；高风险字段独立复读，LLM 改动不得覆盖原始层 |
| 格式适配 | 只把源文件转成 LLM-readable input | `sips` 转 HEIC,可用工具渲染 PDF/展开 DOCX/表格 payload;adapter 只做 provenance |
| 确认门 | 未确认不写正式字段/不可逆删除 | inline diff card 同会话往返 |
| 存储 | canonical 输出集 | agent 写本地 `patient_dir`;原始件逐字保存进 `raw/` vault |

## 1. 编排

- SKILL.md Step 2 按目录/文件数切片；Step 3 并发 Phase 1 来源保真 ingestion workers（原生/确定性抽取优先，LLM 仅辅助）；Step 4 continuation loop；Step 5 单 Phase 2 worker reduce。
- Phase1 写 `<patient_dir>/ocr/` 的来源保真 sidecars、抽取 provenance 和
  `<patient_dir>/raw/` 中的受控原件。它不写 INDEX/timeline/profile 等全局产物。
- 切片大小是 Claude Code 图像上下文预算,不是契约。其它 host 可顺序运行。

## 2. 来源保真抽取

- 图片/扫描件优先运行适用的确定性 OCR/表格/条码工具；born-digital 文件优先读取其原生
  文本/表格层。保存引擎、版本、原始输出、source span 和文件 hash。
- LLM 可重建版面、提出候选纠错、做语义标注和 PII 语义复扫，但 `raw_text` 与
  `proposed_text` 分层保存，不能让 LLM 输出成为唯一字符真值。
- 药名、剂量、频次、日期、实验室值/单位/参考范围、分期、变异/VAF 和标识字段执行第二次
  独立读取；不一致标 `needs_human_review`，不得进入 settled-fact surface。
- PII 同时使用语义复扫与确定性 shape 兜底；任何一层不可用时，共享/交付门 fail closed。
- sidecar 头部字段集: SOURCE / READ_MODE / ADAPTER / ADAPTER_PROVENANCE / CONFIDENCE / FILE_ID (stable source_id, rename-survivable) / optional MODALITY / ORIGINAL。

## 3. 格式适配

- HEIC/HEIF: `sips` 生成临时 JPG/PNG 给 `Read`;原始 HEIC 仍逐字保存到 `raw/`,sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件,临时图只写入 `ADAPTER_PROVENANCE`。
- PDF: born-digital 文本层或 OCR 输出保留为字符来源；渲染页可供版面复核。
- DOCX/表格/文本: 原生文本/单元格是字符来源，LLM-readable payload 是辅助视图。
- 不支持/损坏文件: Phase1 产 stub sidecar + `[INGESTION_BLOCKED]`,不能静默跳过。

## 4. 确认门

- Claude Code 用 inline review_summary/review_flags/profile card/段E disposition 让用户当场确认。
- 沉默/推迟/随便/关闭 = no-confirm。关键字段矛盾必须并列展示,不静默覆盖。
- 任何文件 no-confirm 都不删除；疑似非医疗文件隔离预览，逐项显式确认后才删除。

## 5. 存储

- Phase2 写 canonical `patient_dir`: 14 clinical domains, co-located text-masked MD, `source_inventory.json`(每条 content unit 带 `raw_path` deep-link + `file_id` + `page_range`), structured JSON, HTML 等。
- Organization preserves uploaded bytes in access-controlled `raw/` and uses a de-identified on-disk filename.
  It does not silently overwrite, transform, or delete the original. Retention/deletion is enforced by the
  host's authenticated policy, not by the organizer. The original upload name remains protected and is
  excluded from derived exports.
- `病情简要总结.html` 在文本脱敏 MD/JSON 后生成。
- sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件(de-identified filename)。

## 6. 不变量

- Acceptance gate = run `validate_structured_outputs.py`. It checks schemas, anchors, source-shape integrity,
  inventory completeness, deterministic PII shapes, and HTML form. It does not decide whether a value is
  clinically normal or important. The run also requires Phase 2.5 source-faithfulness review and the PII
  semantic scan. A share action additionally requires viewer authentication, explicit scope/purpose/recipient/
  expiry, data minimization, and an export that excludes `raw/`.
- The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) + the synthesized surfaces (case_text.md / profile.json / …) are scanned by the **two-layer PII gate** — Layer 1 semantic agent scan (pii-rescan-prompt.md, generalizes to name/birthplace/occupation/…) + Layer 2 pii_rescan.py shape floor. De-identification therefore covers the sidecar body AND every delivered/synthesized surface。(Phase2/段D 不读明文原文件。)
- 来源临床字符串保持不变；翻译/规范化只能作为带标签的派生字段，不能覆盖来源。
- `source_inventory.json` 覆盖每个输入源,每条 content unit 带 `raw_path` + 文本脱敏 sidecar。
- LLM 可生成带来源跨度的候选结构、叙述和 HTML 前置数据，但不得覆盖 native/OCR 原始字符层；确定性 HTML 渲染和 PII shape rescan 由脚本执行。
