# Runtime Binding — headless codex

> `cancer-buddy-organize` 在 headless Codex 单进程/平台 worker 上的绑定。目标是让平台用 Codex 驱动同一份 runtime-neutral 契约:LLM-first redacted MD ingestion, Phase2 synthesis, 段D HTML, then pre-persist source-file redaction hard gate.

## 0. 绑定总览

| 接缝 | 契约要求(不变) | headless codex 填法 |
|---|---|---|
| 编排 | Phase2 前所有 sidecar 就绪 | 单进程顺序遍历 source inventory,逐源调用 Codex |
| LLM 输入源 | sidecar 正文由 LLM 输出;哑 OCR/parser 非正文来源 | `codex exec -i <raster>` 视觉或 Codex file-context/payload prompt |
| 格式适配 | 只把源文件变成 LLM-readable input | `heif-convert`/ImageMagick/pdftoppm/document payload builder |
| 确认门 | 未确认不写正式字段/不可逆删除 | confirm-as-product JSON + 平台 UI + 第二轮回灌 |
| 存储+本体脱敏 | canonical 输出集;persist 前源文件本体脱敏通过 | 沙箱内生成 patient_dir;source redaction 完成后仅 persist 脱敏文件/MD/JSON/HTML |

## 1. 编排

平台先生成 `source_inventory` 初稿和 `source_id ↔ 原名/路径` 映射,然后顺序处理每个 source:

```text
for src in source_inventory:
  source_id = stable_id(src)
  mirror original into patient_dir/10_原始文件/
  adapter_input = adapt_for_llm(src)
  sidecar = codex_llm_ingest(source_id, adapter_input)
  write patient_dir/ocr/<source_id>.md
run single Phase2 synthesis over all sidecars
```

Codex `-i` 喂的是匿名图像字节时,平台必须维护 `source_id ↔ 原名`。Phase2 通过这个映射写 canonical filename、`source_inventory.json` 和 anchors。

## 2. LLM 输入源

- 图片/扫描件: `codex exec -i <adapted-raster>` 让 Codex 视觉直接读,输出 redacted MD。
- PDF/DOCX/spreadsheet/text:平台可构造 LLM-readable file context 或 payload,再让 Codex 输出 redacted MD。
- PaddleOCR/Tesseract/macOS Vision/PDF text extractors/DOCX XML parsers 不能直接写 sidecar 临床正文。它们只允许做 adapter、source-file redaction 定位或 QA。
- sidecar header 必须含 `READ_MODE`, `ADAPTER`, `ADAPTER_PROVENANCE`, `ORIGINAL`。`ORIGINAL` 指向原始 staging mirror,不是临时 adapter 文件。

## 3. 格式适配

- HEIC/HEIF: `heif-convert` 或 ImageMagick 转临时 JPG/PNG 给 Codex 视觉。
- Scanned PDF: `pdftoppm`/ImageMagick 渲染页给 Codex 视觉。
- Born-digital PDF/DOCX/spreadsheet/text:可展开成 LLM-readable payload。payload 只是输入适配,不是 sidecar 正文来源。
- Archive:平台解包后递归创建 source entries。
- 不支持/损坏:Codex 生成 stub sidecar + `[INGESTION_BLOCKED]`;不得跳过。

## 4. 确认门

headless 没有 inline 往返,所以确认门产物化:

1. Codex 产待确认项 JSON,包括字段 diff、证据、风险级别、段E 处置项。
2. 平台 UI 展示并收集用户决定。
3. 平台将已确认决定回灌给 Codex;Codex 只写已确认字段/删除项,并写 `update_log.json` ledger。

未确认不写正式字段。高置信非医疗 no-confirm 可删除; borderline no-confirm 保留。

## 5. 存储+本体脱敏

Phase2 产:

- 11 buckets + co-located redacted MD
- `source_inventory.json`
- structured JSON / timeline / case_text / readiness / review outputs
- `redaction_manifest.json` for images
- `source_redaction_status.json` skeleton
- `病情简要总结.html` from redacted JSON/MD

Persist model:

- `病情简要总结.html` may be generated before source-file redaction finishes because it reads only redacted MD/JSON.
- Platform MUST NOT persist source files until `source_redaction_status.json` says every persisted source has `status=done`, `qa_passed=true`, `original_deleted=true`.
- Images use `run_redaction_job.py` from `redaction_manifest.json`, then sync image rows into `source_redaction_status.json`.
- PDF/DOCX/spreadsheet/text require reliable source-file redactors. If missing, write `blocked` with reason and do not persist the source file.
- Persist only: redacted bucket files, co-located redacted MD, JSON/HTML/logs/status. Plaintext originals never leave the sandbox/local workspace.

## 6. 段D HTML

Codex reads only redacted JSON/MD and produces `case_summary_data.json` + narrative. Host runs:

```bash
python3 skills/cancer-buddy-organize/scripts/render_html_template.py \
  --template skills/cancer-buddy-organize/references/templates/case-summary.template.html \
  --data <patient_dir>/case_summary_data.json \
  --out <patient_dir>/病情简要总结.html

python3 skills/cancer-buddy-organize/scripts/validate_case_summary_html.py \
  --html <patient_dir>/病情简要总结.html \
  --template skills/cancer-buddy-organize/references/templates/case-summary.template.html
```

Codex never hand-writes HTML.

## 7. 验收

- `validate_structured_outputs.py <patient_dir>` passes only when structured JSON/anchors/PII rescan/redaction manifest/source inventory/source redaction status/HTML shape pass.
- `source_redaction_status.blocked` is a valid intermediate state but not archive-ready.
- `source_inventory.json` must cover every input source.
- Local OCR is never a sidecar text-source option in this binding.
