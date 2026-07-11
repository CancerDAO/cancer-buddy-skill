# Runtime Binding — Claude Code(参考实现 / reference binding)

> Claude Code 是交互式参考实现。它用 `Agent` 扇出、in-agent `Read`、本地 adapter 命令和 inline 确认卡来满足 `organize-contract.md`。这些是机制,不是契约;契约要求所有 host 都满足同一行为不变量。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | Claude Code 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | `Agent` 并行扇出 Phase1 LLM ingestion,单 `Agent` 做 Phase2 reduce |
| LLM 输入源 | sidecar 正文由 LLM 输出,纯 OCR/parser 不是临床正文或 PII 判断来源 | worker 内 `Read` 读取图片/渲染页/文件 payload,由模型写文本脱敏 MD(原件逐字存 `raw/`,不做图像打码) |
| 格式适配 | 只把源文件转成 LLM-readable input | `sips` 转 HEIC,可用工具渲染 PDF/展开 DOCX/表格 payload;adapter 只做 provenance |
| 确认门 | 未确认不写正式字段/不可逆删除 | inline diff card 同会话往返 |
| 存储 | canonical 输出集 | agent 写本地 `patient_dir`;原始件逐字保存进 `raw/` vault |

## 1. 编排

- SKILL.md Step 2 按目录/文件数切片;Step 3 并发 Phase1 LLM Markdown Ingestion Workers;Step 4 continuation loop;Step 5 单 Phase2 worker reduce。
- Phase1 只写 `<patient_dir>/ocr/` text-masked MD sidecars + `<patient_dir>/raw/` 逐字保存的原始件 vault。它不写 INDEX/timeline/profile 等全局产物。
- 切片大小是 Claude Code 图像上下文预算,不是契约。其它 host 可顺序运行。

## 2. LLM 输入源

- sidecar 正文必须由 Claude/driver LLM 读取 adapted input 后写出(文本脱敏 MD: inline `[PII_MASKED]` + `## PII` trailer)。
- 图片/扫描件: `Read` 视觉。PDF/DOCX/表格/文本: 可先转成模型可读输入,但最终 Markdown 正文、PII 判断 (inline `[PII_MASKED]` + `## PII` trailer)、表格转写仍由 LLM 输出。
- 纯 OCR/parser 字符流不能直接写 sidecar 临床正文,也不能替代 LLM 做 PII 判断。它们只能做格式适配或机械文件处理。
- sidecar 头部字段集: SOURCE / READ_MODE / ADAPTER / ADAPTER_PROVENANCE / CONFIDENCE / FILE_ID (stable source_id, rename-survivable) / optional MODALITY / ORIGINAL。

## 3. 格式适配

- HEIC/HEIF: `sips` 生成临时 JPG/PNG 给 `Read`;原始 HEIC 仍逐字保存到 `raw/`,sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件,临时图只写入 `ADAPTER_PROVENANCE`。
- PDF: 可渲染页或准备文件上下文给 LLM。渲染页不是证据源。
- DOCX/表格/文本: 可展开为 LLM-readable payload。payload 不是临床正文来源。
- 不支持/损坏文件: Phase1 产 stub sidecar + `[INGESTION_BLOCKED]`,不能静默跳过。

## 4. 确认门

- Claude Code 用 inline review_summary/review_flags/profile card/段E disposition 让用户当场确认。
- 沉默/推迟/随便/关闭 = no-confirm。关键字段矛盾必须并列展示,不静默覆盖。
- 任何相关性类别都不自动删除用户文件:no-confirm ⇒ 不归档、源文件原位置保留;仅 agent 自建临时副本在核实源仍在后可清理;删除用户文件需逐项显式确认(confirm-gate)。

## 5. 存储

- Phase2 写 canonical `patient_dir`: 14 clinical domains, co-located text-masked MD, `source_inventory.json`(每条 content unit 带 `raw_path` deep-link + `file_id` + `page_range`), structured JSON, HTML 等。
- `raw/` keeps every uploaded original's BYTES verbatim (never byte-altered, never pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by Phase 1 (identity token stripped; if the whole basename is the identity, fall back to <source_id>.<ext>) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared surface. The verbatim original filename is preserved ONLY in raw/_FILENAME_MAPPING.md (inside raw/, excluded from export, never a delivered/scanned surface).
- `病情简要总结.html` 在文本脱敏 MD/JSON 后生成。
- sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件(de-identified filename)。

## 6. 不变量

- Acceptance gate = run validate_structured_outputs.py; its currently-implemented check set is authoritative. It runs: structured JSON schema + anchors; PII rescan **Layer 2** (deterministic shape floor — id/phone/email/path/account/deny-list) of sidecars AND delivered surfaces; gate_numeric_integrity (flag↔reference_range + dropped-abnormal); source_inventory completeness (every content unit has a de-identified raw_path + text-masked sidecar); case-summary HTML shape. The run must also complete Phase 2.5 extraction-faithfulness (no unresolved CRITICAL) AND the **PII Layer-1 semantic agent scan** (references/pii-rescan-prompt.md, dispatched by the orchestrator — catches label/semantic categories the shape floor can't), and any shareable copy must go through export_share.py (excludes raw/, gated by this script).
- The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) + the synthesized surfaces (case_text.md / profile.json / …) are scanned by the **two-layer PII gate** — Layer 1 semantic agent scan (pii-rescan-prompt.md, generalizes to name/birthplace/occupation/…) + Layer 2 pii_rescan.py shape floor. De-identification therefore covers the sidecar body AND every delivered/synthesized surface。(Phase2/段D 不读明文原文件。)
- 临床实体 verbatim,不翻译/规范化/平滑。
- `source_inventory.json` 覆盖每个输入源,每条 content unit 带 `raw_path` + 文本脱敏 sidecar。
- LLM 可生成 MD/JSON/HTML 前置数据 (含 sidecar 正文 inline `[PII_MASKED]` + `## PII` trailer);确定性 HTML 渲染、PII rescan 由脚本执行。
