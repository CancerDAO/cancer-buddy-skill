# Runtime Binding — Claude Code(参考实现 / reference binding)

> Claude Code 是交互式参考实现。它用 `Agent` 扇出、in-agent `Read`、本地 adapter 命令和 inline 确认卡来满足 `organize-contract.md`。这些是机制,不是契约;契约要求所有 host 都满足同一行为不变量。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | Claude Code 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | `Agent` 并行扇出 Phase1 LLM ingestion,单 `Agent` 做 Phase2 reduce |
| LLM 输入源 | sidecar 正文由 LLM 输出,哑 OCR/parser 不是临床正文来源 | worker 内 `Read` 读取图片/渲染页/文件 payload,由模型写脱敏 MD |
| 格式适配 | 只把源文件转成 LLM-readable input | `sips` 转 HEIC,可用工具渲染 PDF/展开 DOCX/表格 payload;adapter 只做 provenance |
| 确认门 | 未确认不写正式字段/不可逆删除 | inline diff card 同会话往返 |
| 存储+本体脱敏 | canonical 输出集 + persist 前源文件脱敏 hard gate | agent 写本地 `patient_dir`;段B脚本/平台 worker 在 archive/persist 前完成 source redaction |

## 1. 编排

- SKILL.md Step 2 按目录/文件数切片;Step 3 并发 Phase1 LLM Markdown Ingestion Workers;Step 4 continuation loop;Step 5 单 Phase2 worker reduce。
- Phase1 只写 `<patient_dir>/ocr/` redacted MD sidecars + `10_原始文件/` staging mirror。它不写 INDEX/timeline/profile 等全局产物。
- 切片大小是 Claude Code 图像上下文预算,不是契约。其它 host 可顺序运行。

## 2. LLM 输入源

- sidecar 正文必须由 Claude/driver LLM 读取 adapted input 后写出。
- 图片/扫描件: `Read` 视觉。PDF/DOCX/表格/文本: 可先转成模型可读输入,但最终 Markdown 正文、PII 判断、表格转写仍由 LLM 输出。
- PaddleOCR/Tesseract/macOS Vision/PDF text extractors/DOCX XML parsers 不能直接写 sidecar 临床正文。它们只能做格式适配、source-file redaction 定位或 QA。

## 3. 格式适配

- HEIC/HEIF: `sips` 生成临时 JPG/PNG 给 `Read`;原始 HEIC 仍镜像到 `10_原始文件/`,sidecar `ORIGINAL` 指向原始镜像,临时图只写入 `ADAPTER_PROVENANCE`。
- PDF: 可渲染页或准备文件上下文给 LLM。渲染页不是证据源。
- DOCX/表格/文本: 可展开为 LLM-readable payload。payload 不是临床正文来源。
- 不支持/损坏文件: Phase1 产 stub sidecar + `[INGESTION_BLOCKED]`,不能静默跳过。

## 4. 确认门

- Claude Code 用 inline review_summary/review_flags/profile card/段E disposition 让用户当场确认。
- 沉默/推迟/随便/关闭 = no-confirm。关键字段矛盾必须并列展示,不静默覆盖。
- 高置信非医疗文件 no-confirm 可删除;borderline 永不自动删除。

## 5. 存储与持久化前脱敏

- Phase2 写 canonical `patient_dir`: 11 buckets, co-located redacted MD, `source_inventory.json`, structured JSON, `redaction_manifest.json`, `source_redaction_status.json`, HTML 等。
- `病情简要总结.html` 可在脱敏 MD/JSON 后生成,不等待源文件本体脱敏。
- 最终 archive/persist 必须等待 `source_redaction_status.json`:每个 `persist:true && redaction_required:true` 源文件都必须 `status=done`, `qa_passed=true`, `original_deleted=true`。
- 图片本体脱敏复用 `run_redaction_job.py`;PDF/DOCX/其它 redactor 缺失时必须 `blocked`,不得持久化明文。

## 6. 不变量

- sidecar 是下游唯一读取源;Phase2/段D 不读明文原文件。
- 临床实体 verbatim,不翻译/规范化/平滑。
- `source_inventory.json` / `source_redaction_status.json` 是 archive hard gate 的一部分。
- LLM 可生成 MD/JSON/HTML 前置数据;确定性 HTML 渲染、PII rescan、redaction QA 由脚本执行。
