# Runtime Binding — Claude Code(参考实现 / reference binding)

> Claude Code 是交互式参考实现。它用 `Agent` 扇出、in-agent `Read`、本地 adapter 命令和 inline 确认卡来满足 `organize-contract.md`。这些是机制,不是契约;契约要求所有 host 都满足同一行为不变量。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | Claude Code 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | `Agent` 并行扇出 Phase1 LLM ingestion,单 `Agent` 做 Phase2 reduce |
| 抽取输入源 | 像素页：模型整页转写 = 正文，确定性引擎第二读由脚本做三态对齐；born-digital：文本层 = 正文 | Claude `Read` 看正向副本转写；`second_read_align.py` 跑 Apple Vision / tesseract 并写 token 与复读表；引擎版本、原始输出、`body_sha256` 均保留 |
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

- **像素页**（照片、没有文本层的扫描页；`text_layer_kind.py` 判 `embedded_ocr` / `absent` 的 PDF 页）：字符真值是
  Claude 用 `Read` 看**正向副本**做的整页多模态转写（`PRIMARY_CHANNEL: llm_vision`，`READ_MODE: model_vision_primary`）。
  写正文前不运行 OCR、不看引擎输出。正文写完、遮蔽、落盘后，由 `second_read_align.py --apply` 运行确定性引擎做第二读
  并写 token、复读表与条目（phase1 §4 G、§5）。
- **born-digital 页**：`pdftotext -layout` 的文本层就是正文（`text_layer` / `native_text`），不跑 OCR；
  `second_read_align.py --apply … --text-layer` 只做同一性核对（`high_risk_review_status: not_applicable`）。
  文本层字形损坏的行（`text_layer_kind.py` 的 `glyph_anomaly_lines`）由 Claude 看渲染页补读一次，写 `## 文本层字形异常`。
- **本宿主的第二读引擎**（`run_ocr_engine.py` 的 `auto` 顺序）：macOS 有 `swiftc` 时是
  `deterministic_ocr:apple_vision`（skill 自带 `scripts/vision_ocr.swift`，首次使用时编译并按源码哈希缓存到
  `~/.cache/cancer-buddy-organize/`；可用 `CB_ORGANIZE_CACHE_DIR` 改位置）；否则 `deterministic_ocr:tesseract`
  （`chi_sim+eng`）；都没有时第二读为 `none`（每个高风险字段“无信号”，单通道读取，`INDEPENDENT_REREAD: false`）。
  Claude 用 `Read` 再看一遍图（含放大裁剪）属于 `llm_vision`：可以帮自己看清 `[不可读]` 处，但永远不是第二读、不是独立读。
  独立 = 模型主读 + 确定性引擎第二读且引擎至少读出一个高风险字段；born-digital 页的“原生文本层 + 区域引擎读”只用于
  文书意图（phase1 §6）。
- **方向**：看图与引擎读之前，`run_ocr_engine.py orient` 先按 EXIF 与引擎的文字基线方向写出正向副本
  （`raw/_extract/<…>.oriented.png`，旋转角度记进 `adapter_provenance`）；它只打印角度，不输出文字。
- 药名、剂量、频次、日期、实验室值/单位/参考范围、分期、变异/VAF 等高风险字段的分母由 `_high_risk_spans.py` 推出，
  worker 只能用 `declared.json` 补报；冲突写 `[OCR_UNCERTAIN:U-nnn]` 与 `## 不确定字段` 条目，不得进入 settled-fact surface；
  “无信号”不出 flag。
- PII 同时使用语义复扫与确定性 shape 兜底；任何一层不可用时，共享/交付门 fail closed。
- sidecar 头部恰好 12 个键，按序：SOURCE / FILE_ID（稳定的 source_id）/ EXTRACTOR（worker 标识）/ PRIMARY_CHANNEL / SECOND_READ_CHANNEL / INDEPENDENT_REREAD / READ_MODE / ADAPTER / CONFIDENCE / SHA256 / PAGE_LABEL / MODALITY（定义见 `organizer-prompt-phase1-ocr.md` §3；头部块不做 PII 扫描，出现其他键即校验错误）。原件路径与适配器临时文件不进头部，由 Phase 2 写进 `source_inventory.json`。

## 3. 格式适配

- HEIC/HEIF: `sips` 生成临时 JPG（放在 `raw/_extract/`），再由 `run_ocr_engine.py orient` 写正向副本供 `Read` 与引擎；原始 HEIC 仍逐字保存到 `raw/`，`source_inventory.json.raw_path` 指向 `raw/` 下的逐字原件，临时图只记在 `adapter_provenance`。
- PDF: `text_layer_kind.py` 逐页判类型；born-digital 页的文本层是字符来源；像素页 `pdftoppm -r 200` 渲染到 `raw/_extract/` 后转写。
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
