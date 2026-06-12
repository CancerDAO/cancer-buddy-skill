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

## 3. 格式适配

- HEIC/HEIF: `sips` 生成临时 JPG/PNG 给 `Read`;原始 HEIC 仍逐字保存到 `raw/`,sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件,临时图只写入 `ADAPTER_PROVENANCE`。
- PDF: 可渲染页或准备文件上下文给 LLM。渲染页不是证据源。
- DOCX/表格/文本: 可展开为 LLM-readable payload。payload 不是临床正文来源。
- 不支持/损坏文件: Phase1 产 stub sidecar + `[INGESTION_BLOCKED]`,不能静默跳过。

## 4. 确认门

- Claude Code 用 inline review_summary/review_flags/profile card/段E disposition 让用户当场确认。
- 沉默/推迟/随便/关闭 = no-confirm。关键字段矛盾必须并列展示,不静默覆盖。
- 高置信非医疗文件 no-confirm 可删除;borderline 永不自动删除。

## 5. 存储

- Phase2 写 canonical `patient_dir`: 14 clinical domains, co-located text-masked MD, `source_inventory.json`(每条 content unit 带 `raw_path` deep-link + `file_id` + `page_range`), structured JSON, HTML 等。
- `raw/` 是每个上传原件的逐字 vault,按上传原样保存,永不像素脱敏、永不删除。
- `病情简要总结.html` 在文本脱敏 MD/JSON 后生成。
- sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件。

## 6. 不变量

- sidecar(文本脱敏 MD)是下游唯一读取源;Phase2/段D 不读明文原文件。
- 临床实体 verbatim,不翻译/规范化/平滑。
- `source_inventory.json` 覆盖每个输入源,每条 content unit 带 `raw_path` + 文本脱敏 sidecar。
- LLM 可生成 MD/JSON/HTML 前置数据 (含 sidecar 正文 inline `[PII_MASKED]` + `## PII` trailer);确定性 HTML 渲染、PII rescan 由脚本执行。
