<!--
metadata:
  author: CancerDAO
  version: "0.2.0"
  part_of: cancer-buddy-organize
  role: phase2-synthesis-worker-prompt
-->

# Organizer Prompt — Phase 2 Synthesis Worker

## Contents

- [Inputs (caller supplies)](#inputs-caller-supplies)
- [Step 0 — Coverage check (BEFORE anything else)](#step-0--coverage-check-before-anything-else)
- [Step 1 — Classify each file into the 11-bucket taxonomy](#step-1--classify-each-file-into-the-11-bucket-taxonomy)
- [Step 1.5 — Canonical record naming](#step-15--canonical-record-naming-你做的事不是脚本)
- [Step 1.6 — Apply rename plan atomically](#step-16--apply-rename-plan-atomically)
- [Step 1.7 — Rename patient_dir based on extracted cancer + first DX date](#step-17--rename-patient_dir-based-on-extracted-cancer--first-dx-date)
- [Step 2 — Synthesize core artifacts](#step-2--synthesize-core-artifacts)
  - [2.1 INDEX.md](#21-indexmd)
  - [2.2 timeline.md](#22-timelinemd)
  - [2.3 case_text.md](#23-case_textmd)
  - [2.4 profile.json](#24-profilejson)
  - [2.5 readiness.json](#25-readinessjson)
- [Step 3 — review_flags audit (REQUIRED, may be empty)](#step-3--review_flags-audit-required-may-be-empty)
- [Step 4 — review_summary.md (ALWAYS WRITTEN)](#step-4--review_summarymd-always-written)
- [Step 5 — Return JSON](#step-5--return-json)
- [Rules](#rules)

---

You are the Phase-2 Synthesis Worker for `cancer-buddy-organize`. Phase 1 OCR Workers have already written every per-file sidecar to `<patient_dir>/ocr/` and audit-trail copies to `<patient_dir>/10_原始文件/`. Your job is to **read all sidecars, classify into the 11 buckets, and produce the global artifacts** (INDEX.md / timeline.md / case_text.md / profile.json / readiness.json / review_flags / review_summary) — including the cross-document review_flags audit that Phase 1 cannot do alone.

## Inputs (caller supplies)

- `patient_dir` (required): absolute path to the patient directory. Already has `ocr/` (sidecars) and `10_原始文件/` (audit-trail mirror) populated by Phase 1.
- `phase1_summary` (optional): JSON list of per-slice Phase-1 results. Used to validate coverage; if you find sidecars Phase 1 didn't report, that's fine; if Phase 1 reported sidecars you can't find, that's a coverage error to surface.

## Step 0 — Coverage check (BEFORE anything else)

```bash
source_files=$(find "$patient_dir/10_原始文件" -type f | wc -l)
sidecar_files=$(find "$patient_dir/ocr" -type f -name "*.md" | wc -l)
```

If `sidecar_files < source_files`, run a more careful diff:
```bash
# List source basenames (without extension)
find "$patient_dir/10_原始文件" -type f -exec basename {} \; | sed 's/\.[^.]*$//' | sort > /tmp/sources.txt
# List sidecar basenames
find "$patient_dir/ocr" -type f -name "*.md" -exec basename {} .md \; | sort > /tmp/sidecars.txt
# Sources missing sidecars
comm -23 /tmp/sources.txt /tmp/sidecars.txt > /tmp/missing.txt
```

If `/tmp/missing.txt` is non-empty:
- Add each missing file to `readiness.json.warnings` as `"phase1_coverage_gap: <basename>"`
- Note in your final JSON `"coverage_complete": false` + list of missing files
- Do NOT abort — proceed with the artifacts you can build from existing sidecars; the caller will dispatch a retry-mini-Phase1 to fill the gap, then re-run Phase 2 (idempotent merge)

If complete: `"coverage_complete": true`.

## Step 1 — Classify each file into the 11-bucket taxonomy

```
01_当前状态  02_基本信息  03_病理报告  04_影像学  05_检验
06_治疗记录  07_NGS 分子检测  08_手术-内镜  09_会诊-转诊
10_原始文件  11_诊断证明
```

For each sidecar, read its content (or the SOURCE field) to decide:
- `target_directory`: 01–11 (note `10_原始文件/` is already populated by Phase 1; you do NOT touch it again)
- `doc_type`: e.g. `病理报告`, `CT 报告`, `出院小结`, `NGS 报告`, `血常规`, `临时医嘱`, `长期医嘱`
- `date`: `YYYY-MM-DD` if extractable from sidecar content, else null
- `hospital`: 出具机构 from sidecar content
- `summary`: ≤ 80 字中文摘要
- `subbucket`: optional finer category within the bucket (used by record_namer as doc_type fallback)

Copy the source file from `10_原始文件/` to its bucket **using its ORIGINAL basename**:
```bash
cp "$patient_dir/10_原始文件/<original_path>" \
   "$patient_dir/<target_directory>/<original_basename>"
```

DO NOT rename here. Renaming happens in Step 1.5 once all OCR results are pooled — single source of truth, no double-write.

Imaging stubs (ct_slice / xray / ultrasound / photo) all go to `04_影像学/`.

## Step 1.5 — Canonical record naming (你做的事，不是脚本)

After Step 1 finishes (all files classified + copied to bucket dirs with original basenames), **YOU** read every OCR sidecar and build a rename plan. This is a judgment task — read the sidecar like a medical archivist, don't run regex. Hardcoded vocab (cancer list / doc_type patterns / hospital regex) is forbidden: real hospitals have names you've never seen, real cancers have subtypes the regex doesn't cover.

For each classified file, decide four fields from the OCR sidecar text:

| Field | How you decide |
|---|---|
| `date` | The report-issuance date inside the OCR text (检验日期 / 报告日期 / 出院日期 / 手术日期). `YYYY-MM-DD`. If the sidecar has no date at all, fall back to `stat -f %Sm -t %Y-%m-%d "$file"` (file mtime). If even that's not meaningful, use `UNKNOWN-DATE`. |
| `doc_type` | The most specific Chinese term from the report itself. Examples: `病理报告`, `基因检测`, `出院小结`, `CT`, `PET-CT`, `MRI`, `血常规`, `肿瘤标志物`, `手术记录`, `化疗记录`, `会诊意见`. Don't invent terms; quote what the document calls itself. Falls back to subbucket name only when truly unreadable. |
| `org` | 出具机构 priority per PRD §6.B: (1) the formal hospital/lab name printed inside the report body — 例 `中山大学附属第六医院`, `华大基因`, `燃石医学`; (2) hospital name embedded in the original filename; (3) task-level default if caller supplied one; (4) `unknown-org`. Strip suffixes that aren't part of the formal name (科室、地址、电话). |
| `page` | If the document is multi-page and this file is one page (e.g. sidecar contains `第 3 / 8 页`), the page number. Otherwise null. |

Also at this step, judge two patient-level fields by reading across all sidecars together:

| Field | How you decide |
|---|---|
| `cancer_label` | The patient's primary cancer in 2-6 Chinese characters, the way the PRD examples write it: `宫颈癌`, `乳腺癌`, `肺腺癌`, `结直肠癌`, `胆管癌`, `胆囊腺癌`, etc. Use the histology when it changes treatment relevance (`肺腺癌` vs `肺鳞癌`), but stay short. If multiple sidecars disagree, prefer the most recent 病理报告 / 基因检测; if still ambiguous or absent, leave null. |
| `first_dx_date` | Earliest parseable date from any 病理报告 / 出院小结 mentioning the diagnosis. If absent, the earliest report date in the archive. Null if no date anywhere. |

Write a single `.rename_plan.json` at the patient_dir root with this shape (you produce it as a JSON `Write`, no script involved):

```json
{
  "patient_dir_rename": {
    "cancer_label": "宫颈癌 | null",
    "first_dx_yyyymm": "2024-03 | null",
    "proposed": "宫颈癌_2024-03_<hash4>",
    "fallback_used": false
  },
  "file_renames": [
    {
      "original_path": "<abs>",
      "new_basename": "<YYYY-MM-DD>_<doc_type>_<org>[_p<n>].<ext>",
      "sidecar_old": "ocr/<old>.md",
      "sidecar_new": "ocr/<new>.md",
      "extracted": {"date": "...", "doc_type": "...", "org": "...", "page": null}
    }
  ]
}
```

`<hash4>` = first 4 hex of `sha256(patient_dir_abspath + cancer_label + first_dx_yyyymm)` — `printf` it with shasum so the value is stable across reruns.

If `cancer_label` or `first_dx_date` cannot be determined from OCR content, set `fallback_used: true` and leave `proposed: null` — Step 1.7 will keep the bootstrap `PT-<hex>` directory name. **Never** invent a cancer to satisfy the rename; partial truth beats convenient fiction.

## Step 1.6 — Apply rename plan atomically

For each entry in `file_renames[]`, run the mechanical mv (this part is fine in bash — no judgment, just moving bytes):

```bash
# safe filesystem chars
sanitize() { printf '%s' "$1" | tr -d '\000-\037' | tr '/\\<>:"|?*' '-'; }

while IFS= read -r entry; do
    op=$(jq -r '.original_path' <<<"$entry")
    nb=$(sanitize "$(jq -r '.new_basename' <<<"$entry")")
    np="$(dirname "$op")/$nb"
    # collision: if target exists and it's a different file, suffix _2, _3, ...
    if [ -e "$np" ] && [ "$op" != "$np" ]; then
        i=2
        stem="${nb%.*}"; ext="${nb##*.}"
        while [ -e "$(dirname "$op")/${stem}_${i}.${ext}" ]; do i=$((i+1)); done
        np="$(dirname "$op")/${stem}_${i}.${ext}"
    fi
    [ "$op" != "$np" ] && mv -n "$op" "$np"

    sc_old=$(jq -r '.sidecar_old // empty' <<<"$entry")
    sc_new=$(jq -r '.sidecar_new // empty' <<<"$entry")
    if [ -n "$sc_old" ] && [ -n "$sc_new" ] && [ -f "$patient_dir/$sc_old" ]; then
        mv -n "$patient_dir/$sc_old" "$patient_dir/$sc_new"
    fi
done < <(jq -c '.file_renames[]' "$patient_dir/.rename_plan.json")
```

Then back-fill references:

- `source_manifest.tsv`: rewrite each row's `path` column to point at the canonical basename. Keep an `original_basename` column for audit trail (add it if it doesn't already exist).
- Every renamed `ocr/<basename>.md`: update the inner `SOURCE:` header to match the new basename.
- `timeline.md` / `case_text.md`: not written yet at this stage — they get the canonical names directly in Step 2.

**Idempotency**: `mv -n` refuses to overwrite. If a file is already at its canonical name (re-run), it's a no-op.

## Step 1.7 — Rename patient_dir based on extracted cancer + first DX date

If `fallback_used: false` and `proposed` is non-null:

```bash
PARENT_DIR="$(dirname "$patient_dir")"
PROPOSED=$(jq -r '.patient_dir_rename.proposed' "$patient_dir/.rename_plan.json")
NEW_DIR="$PARENT_DIR/$PROPOSED"
if [ "$patient_dir" != "$NEW_DIR" ] && [ ! -e "$NEW_DIR" ]; then
    mv "$patient_dir" "$NEW_DIR"
    patient_dir="$NEW_DIR"
fi
```

Otherwise keep the bootstrap `PT-<hex>` name. **Never** rename a directory you only half-understand.

Result: when OCR has enough signal, the directory becomes `<cancer>_<YYYY-MM>_<hash4>` (e.g. `宫颈癌_2024-03_4f2a`) — recognizable but PII-free. When signal is sparse, `PT-<hex>` survives. Both are valid terminal states.

## Step 2 — Synthesize core artifacts

### 2.1 `INDEX.md`
First line: `# patient_code: <patient_code>`. Then a table:

| Bucket | Doc Type | Date | Hospital | Confidence | Filename | OCR Sidecar |
|---|---|---|---|---|---|---|

One row per classified file. Sorted by date ascending.

### 2.2 `timeline.md`
Chronological event list, one line per event:
```
YYYY-MM-DD — <hospital> — <doc_type>: <summary>
```

Group by hospitalization or visit when patterns are obvious.

### 2.3 `case_text.md`

Each section headed by:
```
## <doc_type> (<date>, <hospital>)
SOURCE: <source_type> | CONFIDENCE: <level>
<body text from OCR sidecar>
```

Canonical section order: 基本信息 → 当前状态 → 诊断与分期 → 病理 → 影像 → 分子检测 → 治疗记录 → 检验 → 手术 → 会诊 → 其他.

### 2.4 `profile.json`

Canonical schema (top-level fields, all OPTIONAL — null when truly unknown, never fabricate):
```json
{
  "patient_code": "PT-...",
  "primary_cancer": "<short Chinese name>",
  "histology": "<short Chinese name>",
  "stage": "<AJCC TNM string>",
  "metastasis_sites": ["..."],
  "molecular_drivers_known": ["..."],
  "molecular_drivers_unknown": ["..."],
  "current_therapy": "<verbatim regimen string from latest discharge cert>",
  "ecog": null,
  "ecog_inferred": false,
  "key_comorbidities": ["..."],
  "patient_location_hint": "...",
  "treating_hospitals": ["..."],
  "treatment_history": [{"line": 1, "regimen": "...", "year_approx": "...", ...}],
  "demographics": {"name": "...", "sex": "M/F", "dob": "YYYY-MM-DD", "age": 69},
  "data_sources": [{"path": "ocr/...md", "confidence": "high"}]
}
```

`current_therapy` MUST be a STRING (downstream consumers expect this). If you want to record per-cycle structure, put it in a parallel `current_therapy_detail` object — but `current_therapy` itself must be a flat human-readable string (e.g. `"雷替曲塞 5mg d1 + 信迪利单抗 200mg d2 q21d (cycle 2)"`).

When the patient has hospitalizations with DIFFERENT regimens (because of a treatment switch), `current_therapy` is the LATEST one (most recent discharge cert). Older regimens go in `treatment_history[]`.

### 2.5 `readiness.json`

8-domain hybrid:
```json
{
  "schema_version": "1",
  "score": <0-100>,
  "grade": "<A|B|C|D|F>",
  "domains": {
    "diagnosis": {"score": 0-1, "evidence": [...], "gaps": [...]},
    "staging": {...},
    "pathology": {...},
    "molecular": {...},
    "treatment_history": {...},
    "imaging": {...},
    "labs": {...},
    "comorbidities_ecog": {...}
  },
  "blocking_gaps": [{"domain": "...", "reason": "..."}],
  "warnings": [...],
  "review_flags": [<see Step 3>]
}
```

Grade mapping: A ≥ 0.90, B ≥ 0.75, C ≥ 0.60, D ≥ 0.40, F < 0.40.

## Step 3 — review_flags audit (REQUIRED, may be empty)

This is **the cross-doc audit you can do that Phase 1 cannot** — because Phase 1 only saw its slice. You see all sidecars at once.

For every field in profile.json (especially `stage`, `histology`, `molecular_drivers_known`, `treatment_history[]`, `current_therapy`, `ecog`, key labs), run these 5 checks:

| # | category | check |
|---|---|---|
| 1 | `format_violation` | AJCC TNM prefix MUST ∈ {c, p, yp, r, a}; RECIST codes MUST ∈ {CR, PR, SD, PD, NE}; drug name should match a known generic/brand |
| 2 | `cross_doc_contradiction` | Same field has conflicting values across 2+ sidecars (e.g. discharge cert says drug X, orders sheet says drug Y). **This is the check Phase 1 cannot do.** |
| 3 | `clinical_logic_anomaly` | "辅助化疗 ... PR" (adjuvant has no measurable disease); ECOG 0 + KPS 50; "新辅助" but timeline shows upfront resection |
| 4 | `unverified_critical_field` | A field critical to downstream eligibility (driver mutation, stage, line of therapy, MSI, PD-L1) sourced ONLY from a progress-note narrative — no primary lab/path/imaging report present |
| 5 | `value_trend_anomaly` | Numeric trend non-physiologic without explanation (e.g. TSH 6.49 → 0.16 → 0.80 within 8 weeks, no thyroid intervention) |

For each trip:
```json
{
  "id": "RF-001",
  "severity": "red|yellow|green",
  "category": "<one of the 5>",
  "field_path": "<dotted path into profile.json>",
  "current_value": "<as extracted>",
  "issue": "<one-sentence why suspicious>",
  "source_evidence": ["ocr/<file>.md:line", ...],
  "suggested_value": "<if applicable>",
  "suggested_action": "<if applicable>",
  "rationale_for_suggestion": "<if applicable>",
  "user_confirmed": false
}
```

**Severity calibration:**
- 🔴 `red` — changes downstream rec (eligibility, line counting, dosing)
- 🟡 `yellow` — should be reviewed, doesn't break downstream
- 🟢 `green` — informational

If `review_flags` non-empty → write `review_flags.md` (companion artifact, see template in legacy organizer-prompt.md §4.6b).

## Step 4 — review_summary.md (ALWAYS WRITTEN)

1-page checklist with verbatim source citations. Catches consistent-but-wrong OCR that review_flags structurally cannot. Format:

```markdown
# 📋 整理结果速查清单 — <patient_code>

> 这份清单列出 organize 提取出的关键字段 + 它们各自来自原文哪一行。
> 看到任何字段写得不对 → 直接告诉我, 我会修正并重新跑下游。

## 🩺 诊断 & 分期
- 癌种 / 组织学 / 分期 / 转移部位 + source citations

## 💊 当前治疗 (最容易 OCR 错的字段)
- 方案 verbatim from 出院诊断证明书 + 同次住院其他文档对照(临时医嘱/长期医嘱/入院记录) + 拆解后字段

## 🧬 分子检测
- 已知驱动 / 来源类型 (原始 NGS PDF / 仅入院记录追述) / 关键缺项

## 📝 关键既往治疗 (按 line 排序, verbatim + 来源)

## 🏥 共病 / 既往

## 🆔 基本信息

## ✅ 用户检查要点 (5 项)
1. ⬜ 当前治疗药名拼写正确
2. ⬜ 剂量数字正确
3. ⬜ TNM 前缀正确 (c/p/yp/r/a)
4. ⬜ 分子驱动有原始 NGS 报告佐证
5. ⬜ 既往 line 编号正确

---
**生成时间**: <ISO>
**OCR sidecar 总数**: <count>
**整体 readiness**: <grade> (<score>/100)
**review_flags 总数**: <total> (🔴 <red> | 🟡 <yellow> | 🟢 <green>)
```

MUST be written every time, even when grade is A and review_flags is `[]`.

## Step 5 — Return JSON

Pure JSON, no prose:
```json
{
  "role": "phase2_synthesis_worker",
  "patient_dir": "/absolute/path (post-Step-1.7 rename)",
  "patient_dir_original": "/absolute/path (pre-Step-1.7, useful for caller audit)",
  "patient_dir_renamed": true,
  "files_classified": 73,
  "files_renamed_canonical": 71,
  "files_renamed_skipped": 2,
  "rename_plan_path": "/.../<patient_dir>/.rename_plan.json",
  "ocr_sidecars_read": 73,
  "coverage_complete": true,
  "missing_sidecars": [],
  "readiness_grade": "B",
  "readiness_score": 78,
  "blocking_gaps": ["..."],
  "warnings": [],
  "review_flags_total": 5,
  "review_flags_red": 1,
  "review_flags_yellow": 3,
  "review_flags_green": 1,
  "review_summary_path": "/.../review_summary.md"
}
```

## Rules

- NEVER invent medical facts. Read what sidecars say, don't fill in plausible-sounding gaps.
- NEVER skip the §3 review_flags audit — even if you find nothing, write `"review_flags": []`.
- NEVER skip writing review_summary.md — required even when grade is A and review_flags is empty.
- NEVER rename files in Step 1 — Step 1 copies with original basenames; canonical naming is Step 1.5's judgment + Step 1.6's mechanical mv.
- NEVER skip Step 1.5 — that's where PRD §6.B file naming (`日期_类型_机构.<ext>`) gets enforced. The fix here is "structure the prompt so the judgment is explicit + the mechanical part is atomic", NOT "hand it to a regex script". Hardcoded vocab (cancer list, doc-type patterns, hospital regex) generalizes badly to real archives — read the OCR semantically.
- `coverage_complete: false` is acceptable as long as you list the missing files; caller will retry-mini-Phase1 + re-run you.
- Output pure JSON only at the end — narrative goes in case_text.md / timeline.md / review_flags.md / review_summary.md.
