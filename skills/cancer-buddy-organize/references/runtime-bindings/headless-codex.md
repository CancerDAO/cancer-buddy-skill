# Runtime Binding — headless codex

> `cancer-buddy-organize` 在 headless Codex 单进程/平台 worker 上的绑定。目标是让平台用 Codex 驱动同一份 runtime-neutral 契约:LLM-first text-masked MD ingestion, Phase2 synthesis, 段D HTML;原始件逐字保存进 `raw/` vault。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | headless codex 填法 |
|---|---|---|
| 编排 | Phase2 前所有 sidecar 就绪 | 单进程顺序遍历 source inventory,逐源调用 Codex |
| LLM 输入源 | sidecar 正文 (含 inline `[PII_MASKED]` + `## PII` trailer) 由 LLM 输出;纯 OCR/parser 非正文或 PII 判断来源 | `codex exec -i <raster>` 视觉或 Codex file-context/payload prompt |
| 格式适配 | 只把源文件变成 LLM-readable input | `heif-convert`/ImageMagick/pdftoppm/document payload builder |
| 确认门 | 未确认不写正式字段/不可逆删除 | confirm-as-product JSON + 平台 UI + 第二轮回灌 |
| 存储 | canonical 输出集 | 沙箱内生成 patient_dir;原始件逐字保存进 `raw/` vault |

## 1. 编排

平台先生成 `source_inventory` 初稿和 `source_id ↔ 原名/路径` 映射,然后顺序处理每个 source:

```text
for src in source_inventory:
  source_id = stable_id(src)
  # raw/ keeps every uploaded original's BYTES verbatim (never byte-altered, never
  # pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by Phase 1
  # (identity token stripped; if the whole basename is the identity, fall back to
  # <source_id>.<ext>) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into
  # a scanned/shared surface. The verbatim original filename is preserved ONLY in
  # raw/_FILENAME_MAPPING.md (inside raw/, excluded from export, never a
  # delivered/scanned surface).
  copy original BYTES verbatim into patient_dir/raw/<de-identified-filename>
  append "<de-identified-filename> ← <verbatim-original-name>" to patient_dir/raw/_FILENAME_MAPPING.md
  seed stripped identity token into patient_dir/.identity_denylist.json
  adapter_input = adapt_for_llm(src)
  sidecar = codex_llm_ingest(source_id, adapter_input)
  write patient_dir/ocr/<source_id>.md            # text-masked MD sidecar (only desensitization of archived data)
run single Phase2 synthesis over all sidecars
```

Codex `-i` 喂的是匿名图像字节时,平台必须维护 `source_id ↔ 原名`。Phase2 通过这个映射写 canonical filename、`source_inventory.json` 和 anchors。

## 2. LLM 输入源

- 图片/扫描件: `codex exec -i <adapted-raster>` 让 Codex 视觉直接读,输出文本脱敏 MD。
- PDF/DOCX/spreadsheet/text:平台可构造 LLM-readable file context 或 payload,再让 Codex 输出文本脱敏 MD (inline `[PII_MASKED]` + `## PII` trailer)。
- 纯 OCR/parser 字符流不能直接写 sidecar 临床正文,也不能替代 Codex 做 PII 判断。它们只允许做 adapter 或机械文件处理。
- sidecar header 必须含 `SOURCE` / `READ_MODE` / `ADAPTER` / `ADAPTER_PROVENANCE` / `CONFIDENCE` / `FILE_ID` (stable source_id, rename-survivable) / optional `MODALITY` / `ORIGINAL`。`ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件,不是临时 adapter 文件。

## 3. 格式适配

- HEIC/HEIF: `heif-convert` 或 ImageMagick 转临时 JPG/PNG 给 Codex 视觉。
- Scanned PDF: `pdftoppm`/ImageMagick 渲染页给 Codex 视觉。
- Born-digital PDF/DOCX/spreadsheet/text:可展开成 LLM-readable payload。payload 只是输入适配,不是 sidecar 正文来源。原件仍逐字保存进 `raw/`。
- Archive:平台解包后递归创建 source entries。
- 不支持/损坏:Codex 生成 stub sidecar + `[INGESTION_BLOCKED]`;不得跳过。

## 4. 确认门

headless 没有 inline 往返,所以确认门产物化:

1. Codex 产待确认项 JSON,包括字段 diff、证据、风险级别、段E 处置项。
2. 平台 UI 展示并收集用户决定。
3. 平台将已确认决定回灌给 Codex;Codex 只写已确认字段/删除项,并写 `update_log.json` ledger。

未确认不写正式字段。高置信非医疗 no-confirm 可删除; borderline no-confirm 保留。

## 5. 存储

Phase2 产:

- 14 clinical domains + co-located text-masked MD
- `source_inventory.json`(每条 content unit 带 `raw_path` deep-link + `file_id` + `page_range`,无 redaction 字段)
- structured JSON / timeline / case_text / readiness / review outputs
- `病情简要总结.html` from text-masked JSON/MD

Storage model:

- `raw/` keeps every uploaded original's BYTES verbatim (never byte-altered, never pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by Phase 1 (identity token stripped; if the whole basename is the identity, fall back to `<source_id>.<ext>`) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared surface. The verbatim original filename is preserved ONLY in `raw/_FILENAME_MAPPING.md` (inside `raw/`, excluded from export, never a delivered/scanned surface)。每条 content unit 通过 `source_inventory.json.raw_path` deep-link 回到 `raw/`(多文档源带 `page_range`)。
- `病情简要总结.html` 从文本脱敏 JSON/MD 生成。
- The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) + the synthesized surfaces (case_text.md / profile.json / …) are scanned by the **two-layer PII gate** — Layer 1 semantic agent scan (`pii-rescan-prompt.md`, generalizes to name/birthplace/occupation/…) + Layer 2 `pii_rescan.py` shape floor (id/phone/email/path/account/deny-list). De-identification therefore covers the sidecar body AND every delivered/synthesized surface.
- Persist:text-masked bucket files、co-located text-masked MD、`raw/` 逐字原件、JSON/HTML/logs。

## 6. 段D HTML

Codex reads only text-masked JSON/MD and produces `case_summary_data.json` + narrative. Host runs:

```bash
python3 skills/cancer-buddy-organize/scripts/render_html_template.py \
  --template skills/cancer-buddy-organize/references/templates/case-summary.template.html \
  --data <patient_dir>/.case_summary_data.json \
  --out <patient_dir>/病情简要总结.html

python3 skills/cancer-buddy-organize/scripts/validate_case_summary_html.py \
  --html <patient_dir>/病情简要总结.html \
  --template skills/cancer-buddy-organize/references/templates/case-summary.template.html
```

Codex never hand-writes HTML.

## 7. 验收

- `validate_structured_outputs.py <patient_dir>` is the acceptance gate; **its currently-implemented check set is authoritative** (contract §5 invariant #8 — do not freeze a narrower enumeration here). As of this writing it runs: structured JSON schema + anchors; PII rescan **Layer 2** (deterministic shape floor — id/phone/email/path/account/deny-list) of text sidecars **and delivered surfaces** (INDEX.md / source_inventory.json / dotfiles / 病情简要总结.html); `gate_numeric_integrity` (flag↔reference_range + dropped-abnormal); source_inventory completeness (every content unit has a de-identified `raw_path` + text-masked sidecar); HTML shape. It does not check any source/image redaction state. Additionally the run must complete the **Phase 2.5 faithfulness check** (no unresolved CRITICAL) AND the **PII Layer-1 semantic agent scan** (`pii-rescan-prompt.md`, orchestrator-dispatched), and any shareable copy must go through `export_share.py` (excludes `raw/`, gated by this script).
- `source_inventory.json` must cover every input source, and every content unit must carry a `raw_path` deep-link into `raw/` plus a text-masked sidecar.
- Local OCR is never a sidecar text-source option in this binding.
