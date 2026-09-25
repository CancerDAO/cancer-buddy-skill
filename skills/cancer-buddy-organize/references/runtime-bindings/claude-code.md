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

- SKILL.md Step 2 按目录/文件数切片；Step 3 并发 Phase 1 来源保真 ingestion workers（原生/确定性抽取优先，LLM 仅辅助）；Step 4 continuation 与存活监测；Step 5 单 Phase 2 worker reduce。
- worker 标识由编排者生成并写进 Call parameters：Phase 1 `p1-<slice_id>-<n>`，单文件重派 `p1-<source_id>-<n>`，stub worker `p1stub-<source_id>`，旧档案摘录 `p1digest-<n>`，Phase 2（含 `faithfulness_patch` / `relevance_disposition` 模式）`p2-<n>`，Phase 2.5 `p25-<n>`，段C `c-<n>`。每次派发、终止、重派都记入 `dispatch_log`，并向 `<patient_dir>/raw/_dispatch_log.jsonl` 追加一行 JSON（`{at, event: dispatch|kill|redispatch, worker_id, phase, files}`；上下文被压缩后它仍在盘上），交给 Phase 2 写进 `update_log.json`。
- **存活监测**：后台 subagent 运行期间，每隔几分钟检查一次产物（Phase 1 看 `ls -lt <patient_dir>/ocr` 的新文件与修改时间；Phase 2 看 `<patient_dir>` 下 `.rename_plan.json` 与各 JSON 的修改时间），并在宿主能看到工具调用记录时统计连续只读调用次数。**10 分钟无新产物写入，或连续 30 次只读工具调用** → 终止该 subagent → Phase 1：已写出完整 sidecar 的文件保留（`in_progress_timeout_risk` stub 不算完整），其余每个文件派一个单文件 worker；worker 自己返回 `timed_out: true` 时，对其 `timeout_risk_files` 同样处理；Phase 2：同一提示词重派一次 → 仍超时则 Phase 1 派 stub worker 写 `[INGESTION_BLOCKED: timeout]`、Phase 2 停下向用户报告。编排者任何时候都不自己写 sidecar 或结构化 JSON，也不用脚本代写；它的写入只限 SKILL.md 不变量 3 的白名单。
- Phase1 写 `<patient_dir>/ocr/` 的来源保真 sidecars、抽取 provenance 和
  `<patient_dir>/raw/` 中的受控原件。它不写 INDEX/timeline/profile 等全局产物。
- 切片大小是 Claude Code 图像上下文预算,不是契约。其它 host 可顺序运行。

## 2. 来源保真抽取

- 图片/扫描件优先运行适用的确定性 OCR/表格/条码工具；born-digital 文件优先读取其原生
  文本/表格层。保存引擎、版本、原始输出、source span 和文件 hash。
- LLM 可重建版面、提出候选纠错、做语义标注和 PII 语义复扫，但 `raw_text` 与
  `proposed_text` 分层保存，不能让 LLM 输出成为唯一字符真值。
- 药名、剂量、频次、日期、实验室值/单位/参考范围、分期、变异/VAF 等高风险字段执行第二次
  读取；不一致写 `[OCR_UNCERTAIN:U-nnn]` 与 `## 不确定字段` 条目，不得进入 settled-fact surface。
- **Claude Code 可用的读取通道**：born-digital PDF → `pdftotext -layout`（`text_layer`）；DOCX/表格 →
  原生段落与单元格（`text_layer` / `table_parser`）；扫描件与照片 → **默认确定性通道是
  `tesseract <图片> <输出前缀> -l chi_sim+eng tsv`**（`deterministic_ocr:tesseract`；TSV 自带逐词坐标与置信度，
  原样存到 `raw/_extract/<source_id>.tesseract.tsv`，检验表可据坐标按行配对）。本 skill 不附带其他 OCR
  脚本；宿主另有确定性引擎（如 macOS Apple Vision）时可按 `deterministic_ocr:<engine>` 命名使用，同样须保存
  逐行坐标与置信度，不能只取首选文本。宿主没有安装 tesseract 且没有其他确定性引擎时，主通道只能是
  `llm_vision`（phase1 §4 C），并在返回 JSON 标注。Claude 用 `Read` 看图属于 `llm_vision`：可以做第二次
  读取，但 `INDEPENDENT_REREAD` 永远是 `false`。两个 OCR 引擎同属一类，也不构成独立复读；真正独立的
  组合是“原生文本层 + OCR”或“确定性通道 + 人工”。
- PII 同时使用语义复扫与确定性 shape 兜底；任何一层不可用时，共享/交付门 fail closed。
- sidecar 头部恰好 12 个键，按序：SOURCE / FILE_ID（稳定的 source_id）/ EXTRACTOR（worker 标识）/ PRIMARY_CHANNEL / SECOND_READ_CHANNEL / INDEPENDENT_REREAD / READ_MODE / ADAPTER / CONFIDENCE / SHA256 / PAGE_LABEL / MODALITY（定义见 `organizer-prompt-phase1-ocr.md` §3；头部块不做 PII 扫描，出现其他键即校验错误）。原件路径与适配器临时文件不进头部，由 Phase 2 写进 `source_inventory.json`。

## 3. 格式适配

- HEIC/HEIF: `sips` 生成临时 JPG/PNG 供 OCR 与 `Read`；原始 HEIC 仍逐字保存到 `raw/`，`source_inventory.json.raw_path` 指向 `raw/` 下的逐字原件，临时图只记在 `adapter_provenance`。
- PDF: born-digital 文本层或 OCR 输出保留为字符来源；渲染页可供版面复核。
- DOCX/表格/文本: 原生文本/单元格是字符来源，LLM-readable payload 是辅助视图。
- 不支持/损坏文件: Phase1 产 stub sidecar + `[INGESTION_BLOCKED: <原因>]`，不能静默跳过；`.DS_Store`、`__MACOSX/`、空文件、重复 sha256 记入 `skipped_inputs`。

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
- `source_inventory.json.raw_path` 指向 `raw/` 下的逐字原件（de-identified filename）；旧档案摘录行的 `raw_path` 为 null。

## 6. 不变量

- Acceptance gate = run `validate_structured_outputs.py` after `write_organize_meta.py` (SKILL.md Step 17; audits and
  downstream checks add `--readonly`). It checks schemas, anchors, source-shape integrity, sidecar headers,
  inventory completeness, deterministic PII shapes, and HTML form. It does not decide whether a value is
  clinically normal or important. The run also requires Phase 2.5 source-faithfulness review and the PII
  semantic scan. A share action additionally requires viewer authentication, explicit scope/purpose/recipient/
  expiry, data minimization, and an export that excludes `raw/`.
- The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) + the synthesized surfaces (case_text.md / profile.json / …) are scanned by the **two-layer PII gate** — Layer 1 semantic agent scan (pii-rescan-prompt.md, generalizes to name/birthplace/occupation/…) + Layer 2 pii_rescan.py shape floor. De-identification therefore covers the sidecar body AND every delivered/synthesized surface。(Phase2/段D 不读明文原文件。)
- 来源临床字符串保持不变；翻译/规范化只能作为带标签的派生字段，不能覆盖来源。
- `source_inventory.json` 覆盖每个输入源,每条 content unit 带 `raw_path` + 文本脱敏 sidecar。
- LLM 可生成带来源跨度的候选结构、叙述和 HTML 前置数据，但不得覆盖 native/OCR 原始字符层；确定性 HTML 渲染和 PII shape rescan 由脚本执行。
