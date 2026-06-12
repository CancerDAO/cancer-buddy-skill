# Anchor Token Contract `[[src:...]]`

The synthesis worker MUST emit a `[[src:...]]` anchor for every factual statement it writes into narrative artifacts (`case_text.md`, the patient-facing summary section), and an equivalent path string into `source_refs[]` for every fact written into structured JSON.

This is the contract that lets every downstream agent (vMTB pathologist / geneticist / oncologist; MTB-lite; trial-match eligibility filter) trace any fact back to a verifiable source.

There are two anchor kinds:

1. **File anchor** — points to a redacted MD sidecar that lives next to its image inside a clinical-domain subdirectory (`01_…14_`, see `bucket-taxonomy.md`). This is the normal case for anything OCR'd from a record.
2. **Conversation anchor** — points to a fact captured during a `conversation-incremental` (段C) chat turn, where the source is the dialogue itself rather than a file.

## 1. Syntax

```
[[src:<bucket-relative-path>]]
[[src:<bucket-relative-path>#<fragment>]]
[[src:conversation:<ISO8601>]]
```

### 1a. File anchor

- `<bucket-relative-path>` is a path to a `.md` sidecar **relative to `<patient_dir>`**, beginning with one of the clinical-domain prefixes (`01_…` … `14_…`; infra `raw/`/`99_` are never anchored), e.g. `04_诊断与分期/病理报告/2024-03-15_病理报告_x.md`.
- The legacy `ocr/` prefix is **deprecated and rejected** — the central `ocr/` directory no longer exists; MD sidecars live only inside their bucket alongside the image they were extracted from.
- The historical `02_脱敏病历/` prefix is likewise retired in favor of bucket-relative paths.
- `<fragment>` is optional. Two forms accepted:
  - **Line range**: `#L<start>` or `#L<start>-L<end>` — points to verbatim lines in the markdown file.
  - **Section anchor**: `#<slug>` where `<slug>` matches `[A-Za-z0-9_-]+` — points to a `## <Heading>` in the file (slug = lowercase, spaces → `-`).
- Paths are case-sensitive and use `/` separators (never `\`).
- No whitespace allowed inside the anchor.

### 1b. Conversation anchor

- Form: `[[src:conversation:<ISO8601>]]` where `<ISO8601>` is the timestamp of the chat turn the fact was confirmed in, e.g. `[[src:conversation:2026-06-07T14:32:05Z]]`.
- Emitted only by the `conversation-incremental` run mode (段C), and only for facts the user has explicitly confirmed via the diff card. Unconfirmed candidates are never written to formal fields and never carry an anchor.
- A conversation anchor has **no path and no `#fragment`** — the dialogue turn is the source. The underlying note is archived under the fact's CORRESPONDING clinical-domain `conversation_notes/` subdir (e.g. a lab value → `07_检验/conversation_notes/`), falling back to `14_患者自管补充/conversation_notes/` only when the fact fits no clinical domain, with a `patient_curated` tag, but that file is the archive, not the citation target.

## 2. Coverage rule

Every **factual sentence** in narrative output must carry at least one anchor. Examples:

```
- 主要诊断: 乙状结肠癌 (cT4N1M1) [[src:04_诊断与分期/病理报告/2019-04-09_病理报告_中山六院.md#L4-L8]]
- KRAS G12C 突变 (VAF 0.32) [[src:06_分子与组学/NGS报告/2024-03-15_NGS_华大基因.md#L22-L29]]
- 患者口述近一周乏力加重,ECOG 由 1 升至 2 [[src:conversation:2026-06-07T14:32:05Z]]
```

Pure narrative transitions, summary recaps, or headers without factual content do not need anchors. Examples of sentences that do NOT need an anchor:

- "以下按时间顺序整理本次入院记录:"  (transition)
- "## 2. 分子病理"  (section header)
- "暂未发现 BRAF / NRAS / HER2 异常 — 见 missing_items.json"  (forward reference to another file)

## 3. Path validity

Validity is checked per anchor kind.

**File anchors** — before writing a file with file anchors, the synthesis worker MUST:

1. Resolve every file anchor's bucket-relative path to an absolute filesystem path (`<patient_dir>/<bucket-relative-path>`).
2. Verify the target `.md` sidecar exists inside its bucket. If it does not, the entire write is rejected and the missing path is logged into `readiness.json.warnings` as `"anchor_dangling: <path>"`. A path still using the deprecated `ocr/` prefix is treated as dangling.
3. (Optional but recommended) For `#L<a>-L<b>` fragments, verify `<a>` and `<b>` are within the target file's line count; clamp or reject if out of range.

**Conversation anchors** — no filesystem path to resolve. Validity = (a) the `<ISO8601>` timestamp parses as a valid date-time, and (b) the fact was user-confirmed in 段C (unconfirmed candidates must not be written). Conversation anchors are never reported as `anchor_dangling`.

## 4. Structured-JSON form

In `patient_summary.json`, `timeline.json`, `molecular.json`, `treatment_lines.json`, `labs.json`, `comorbidities.json`, `missing_items.json`:

- Anchors live in `source_refs: [...]` arrays.
- Each entry is the **path-only** (file anchor) or **`conversation:<ISO8601>`** (conversation anchor) string, with no surrounding `[[src:` / `]]`.
- For file anchors the fragment is preserved: `"04_诊断与分期/病理报告/2024-03-15_病理报告_x.md#L22-L29"` is valid.
- For conversation anchors: `"conversation:2026-06-07T14:32:05Z"` is valid.

Schemas in [`*.schema.json`](README.md) enforce this via the regex:

```
^(([0-9]{2}_[^\s/]+(/[^\s/]+)*\.md(#L\d+(-L\d+)?|#[A-Za-z0-9_-]+)?)|(conversation:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?))$
```

The first alternative matches a bucket-relative `.md` path (leading `NN_` bucket segment, optional `#fragment`); the second matches a `conversation:<ISO8601>` reference. The legacy `^(ocr/|02_脱敏病历/)…` pattern is retired.

## 5. Why this matters

- **Downstream trust** — vMTB pathologist refuses to cite a fact without an anchor, eliminating fabrication.
- **Patient verifiability** — every fact in the patient-facing summary card can be inspected by clicking through to the redacted bucket sidecar (file anchor) or the confirmed chat turn (conversation anchor).
- **Audit trail** — when a regulator or treating physician asks "where did this molecular result come from", the chain is in the file itself.

Failure to honor this contract is a P0 bug — surfaced as a `🔴 red` flag in `review_flags.md` with `category: anchor_coverage_gap`.
