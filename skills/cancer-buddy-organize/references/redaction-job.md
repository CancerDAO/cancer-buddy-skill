# 段B — 持久化前 LLM-region source redaction job

> 段A 已把下游文字边界收敛到脱敏 MD/JSON/HTML；段B 负责把要持久化的源文件本体也脱敏。PII 判断和坐标/结构定位来自 Phase 1/2 的 LLM manifest，脚本只做确定性打码、替换和状态推进。最终 archive/persist 必须等待段B commit 通过。

## 角色与脚本

| 脚本 | 角色 |
|---|---|
| `scripts/run_redaction_job.py prepare <patient_dir>` | 读取 `redaction_manifest_v2`，按 LLM 提供的 bbox/quad/XML/cell/line/payload locator 生成 redacted candidate，写 `redacted_pending_qa`。不覆盖桶文件，不删除明文原件。 |
| LLM QA worker | 只看 redacted preview/payload，输出 `llm_redaction_qa.json`：file id、pass/fail、类别、reason code。不得回写或打印明文 PII。 |
| `scripts/run_redaction_job.py commit <patient_dir> --qa-report <qa.json>` | 只有 `coverage_passed:true && llm_qa_passed:true` 才替换 bucket + `10_原始文件/` mirror，并用脱敏版覆盖明文原件。 |

## Manifest / Status 契约

- 输入 `redaction_manifest.json`: schema `redaction_manifest_v2`。每个文件包含 `source_id`, `source_kind`, `bucket_path`, `mirror_path`, `redacted_candidate_path`, `redacted_payload_path`, `adapter_frame`, `regions[]`。`regions[]` 只允许类别与 locator，禁止明文 PII。
- 输出 `redaction_status.json`: schema `redaction_status_v2`。状态为 `pending`, `redacted_pending_qa`, `done`, `failed`, `blocked`，并记录 `coverage_passed`, `llm_qa_passed`, `qa_report_id`, `qa_passed`, `original_deleted`。
- 同步 `source_redaction_status.json`: source-level hard gate。所有 `persist:true && redaction_required:true` 源文件必须 `done + coverage_passed + llm_qa_passed + qa_passed + original_deleted` 才能离开本地工作区。

## 支持格式

- Image/HEIC: 将源文件规范化为 canonical raster 后，按 `normalized_bbox` / `normalized_quad` / `pixel_bbox` 画黑框；HEIC 可转为可浏览 JPG/PNG candidate。
- PDF: 固定 DPI 渲染页图，按页坐标打码，再用 `reportlab` 重建 rasterized redacted PDF；页数必须一致。
- DOCX: 按 `xml_path` locator 替换 `word/*.xml` 的文本节点/run/cell；可定位正文、表格、页眉页脚、批注/脚注。不可定位则 `blocked`，除非 manifest 提供 redacted payload。
- XLSX: 按 sheet/cell locator 替换单元格，清理被标记的批注和文档属性。
- CSV/TXT/HTML/MD: 按 line/span locator 或 redacted payload 输出 redacted copy。
- Archive: 不持久化原 archive；只从 redacted children 或 redacted payload 重建 archive。
- Unknown binary: `blocked_unsupported`，不得进入最终包。

## 运行约定

```bash
python3 skills/cancer-buddy-organize/scripts/run_redaction_job.py prepare <patient_dir>
# LLM QA writes <patient_dir>/llm_redaction_qa.json
python3 skills/cancer-buddy-organize/scripts/run_redaction_job.py commit \
  <patient_dir> \
  --qa-report <patient_dir>/llm_redaction_qa.json
```

也可以显式指定 manifest:

```bash
python3 skills/cancer-buddy-organize/scripts/run_redaction_job.py prepare \
  --manifest <path/to/redaction_manifest.json>
```

退出码: `0` = 无 failed/blocked；`1` = 至少一个 failed/blocked；`2` = 调用错误 / manifest 或 QA report 不可读。

## Coverage Gate

`prepare` 必须证明每个 manifest region 被处理：

- locator 类型合法，坐标裁剪后仍有面积；
- candidate 可打开；
- `candidate_sha256 != original_sha256`，除非该文件 `regions: []` 且 `redaction_required:false`；
- `redacted_candidate_path` 在工作区内；
- status 写为 `redacted_pending_qa`，`original_deleted:false`。

`commit` 必须再次确认：

- coverage 已通过；
- QA report 中该 file id 为 pass；
- candidate 仍存在且 hash 与 status 记录一致；
- bucket path 和 mirror path 都在 patient_dir 内；
- 替换完成后没有明文原件路径残留在最终 package 清单中。

## LLM QA Gate

LLM QA 是删原件的唯一语义前置。QA worker 复核 redacted 图片/PDF 页面预览、DOCX/XLSX/text redacted payload，只输出：

```json
{
  "schema": "llm_redaction_qa_v1",
  "report_id": "qa-20260609T000000Z",
  "files": [
    {"id": "f001", "pass": true, "categories_checked": ["patient_name"], "reason": null}
  ]
}
```

QA report 不得包含原始姓名、证件号、住院号、电话、地址、出生日期等明文值。`pass:false` 或缺失条目都会阻止 commit。

## 提交语义

1. `prepare` 只写 candidate，不覆盖原件。
2. QA pass 后，`commit` 使用 `os.replace` 原子替换 bucket copy。
3. 同步覆盖 `10_原始文件/` mirror，使 audit mirror 自身也脱敏。
4. 标 `status:"done"`, `coverage_passed:true`, `llm_qa_passed:true`, `qa_passed:true`, `original_deleted:true`。
5. QA fail / candidate 缺失 / IO 错误 → 保留原件，标 `failed` 或 `blocked`，不得持久化。

## 不变量

- 段B 不做 OCR、不做新的 PII 判断、不产任何下游临床文字。
- 明文源文件只允许短暂停留在本地 staging；最终 package 只能包含脱敏 MD/JSON/HTML 和 QA 通过后的 redacted source copy。
- 删除明文原件不可逆，只能在 coverage + LLM QA 双通过后发生。
- 脱敏只遮/替换 PII，不改临床实体、药名、剂量、分期、突变、检验值和临床事件日期。
- `validate_structured_outputs.py` 是 archive/persist 总门；任何 `pending/failed/blocked`、`qa_passed:false/null`、`original_deleted:false/null` 都必须阻止最终包。
