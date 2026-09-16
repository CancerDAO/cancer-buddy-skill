# Anchor Token Contract `[[src:...]]`

The synthesis worker MUST emit a `[[src:...]]` anchor for every factual statement it writes into narrative artifacts (`case_text.md`, the patient-facing summary section), and an equivalent path string into `source_refs[]` for every fact written into structured JSON.

This is the contract that lets every downstream agent (vMTB pathologist / geneticist / oncologist; MTB-lite; trial-match eligibility filter) trace any fact back to a verifiable source.

There are two anchor kinds:

1. **File anchor** — points to a masked MD sidecar that lives next to its image inside an **anchored clinical-domain** subdirectory (`01_…14_`, see `bucket-taxonomy.md`). This is the normal case for anything transcribed from a record.
2. **Conversation anchor** — points to a fact captured during a `conversation-incremental` (对话增量模式) chat turn, where the source is the dialogue itself rather than a file.

## 1. Syntax

```
[[src:<bucket-relative-path>]]
[[src:<bucket-relative-path>#<fragment>]]
[[src:conversation:<ISO8601>]]
```

### 1a. File anchor

- `<bucket-relative-path>` is a path to a `.md` sidecar **relative to `<patient_dir>`**, beginning with one of the **anchored** clinical-domain prefixes (`01_…` … `14_…`), e.g. `04_诊断与分期/病理报告/2024-03-15_病理报告_x.md`. **`15_未分类资料/` is NOT anchorable**, and neither are the infrastructure locations `raw/` (including `raw/transcript/`, `raw/_cache/`, `raw/_provenance/`) or `99_无关文件/` — see §1c.
- The legacy `ocr/` prefix is **deprecated and rejected** — the central `ocr/` staging dir is a live transient dir during a run and is deleted by 段 2 (so it no longer exists at anchor-write time); final MD sidecars live only inside their bucket alongside the image they were extracted from.
- The historical `02_脱敏病历/` prefix is likewise retired in favor of bucket-relative paths.
- `<fragment>` is optional. Two forms accepted:
  - **Line range**: `#L<start>` or `#L<start>-L<end>` — points to verbatim lines in the markdown file.
  - **Section anchor**: `#<slug>` where `<slug>` matches `[A-Za-z0-9_-]+` — points to a `## <Heading>` in the file (slug = lowercase, spaces → `-`).
- Paths are case-sensitive and use `/` separators (never `\`).
- No whitespace allowed inside the anchor.

### 1b. Conversation anchor

- Form: `[[src:conversation:<ISO8601>]]` where `<ISO8601>` is the timestamp of the chat turn the patient/caregiver statement was confirmed for archiving.
- **A conversation source never gets a `source_inventory.json` row.** It has no uploaded bytes, no `raw/` original, no page, no character layer, no `bbox` and no `transcript_path` — an inventory row asserts a binding to `raw/` bytes that does not exist, and minting one hollows out the "every source has `raw/` bytes + a masked MD + an inventory row" definition of done. The conversation anchor **is** the whole provenance record (see `conversation-incremental-prompt.md`).
- Emitted only for `patient_reported` or `caregiver_reported` facts. Confirmation does not promote the statement to `source_reported` or `clinician_verified`.
- A conversation anchor has **no path and no `#fragment`** — the dialogue turn is the source. The underlying note is archived under the fact's CORRESPONDING clinical-domain `conversation_notes/` subdir (e.g. a lab value → `07_检验/conversation_notes/`), falling back to `14_患者自管补充/conversation_notes/` only when the fact fits no clinical domain, with a `patient_curated` tag, but that file is the archive, not the citation target.

### 1c. `15_未分类资料/` is NOT an anchor target — use `open_ref` instead

`scheme_version 4` adds a 15th visible bucket, `15_未分类资料/<slug>/`, for material whose document
type the taxonomy does not know (`bucket-taxonomy.md` §1.1c). **It does not extend the anchor
namespace.** Anchors remain restricted to `01_…14_`:

- a `[[src:15_…]]` token in narrative output is **invalid** and the write is rejected;
- a `"15_…"` entry in any `source_refs[]` / `source_ref` is **invalid** and fails the acceptance gate;
- the regex in §4 does not change — it matches a two-digit bucket prefix, and the gate additionally
  asserts the prefix is in `01…14`. (The historical looseness where the regex admitted any two
  digits is a drift bug; `15_` must be rejected explicitly, not by accident of the regex.)

A fact whose only source is a `15_` document is referenced through **`extracted_fields.json`'s own
reference format**, which is deliberately *not* an anchor:

```json
"open_ref": { "source_id": "s007", "page": 3, "bbox": [0.12, 0.44, 0.58, 0.47] }
```

`open_ref` points at the **`raw/` page** (normalized 0–1 `bbox`, origin top-left), not at a bucket
path, precisely so that it cannot be mistaken for — or silently promoted into — a citable clinical
anchor.

**Consequences (all three hold together):**

1. **Open fields do not enter any confirmed-fact surface.** They are absent from
   `patient_summary.json`, from the confirmed values of the patient-facing summary, and from the
   anchored factual sentences of `case_text.md`.
2. **`extracted_fields.json` is not a legal source store** for charts or core-completeness. The
   rendering stage draws known slots only; an open field never becomes a trend line and never
   satisfies a core-completeness requirement.
3. **`15_` is still read.** Non-anchorable does not mean invisible: the material is transcribed,
   masked, filed, inventoried, and surfaced through `projection_coverage`; consumers decide whether
   to read it from the row's `clinical_class`, never from its path.

Rationale: making `15_` citable would ripple through `anchor-contract`, every downstream bucket
enumeration (vmtb, visit-prep), and the export policy in one step, for a bucket whose contents have
by definition not been validated against a known schema. Keeping the open archive and the citation
namespace separate is the cheaper and safer first stage; it can be revisited once novel-material
frequency data exists.

## 2. Coverage rule

Every **factual sentence** in narrative output must carry at least one anchor. Examples:

```
- 主要诊断: 乙状结肠癌 (cT4N1M1) [[src:04_诊断与分期/病理报告/2019-04-09_病理报告_示例医院.md#L4-L8]]
- KRAS G12C 突变 (VAF 0.32) [[src:06_分子与组学/NGS报告/2024-03-15_NGS_华大基因.md#L22-L29]]
- 患者口述近一周乏力加重，活动时间减少 [[src:conversation:2026-06-07T14:32:05Z]]（不得转成 ECOG 分数）
```

Pure narrative transitions, summary recaps, or headers without factual content do not need anchors. Examples of sentences that do NOT need an anchor:

- "以下按时间顺序整理本次入院记录:"  (transition)
- "## 2. 分子病理"  (section header)
- "暂未发现 BRAF / NRAS / HER2 异常 — 见 missing_items.json"  (forward reference to another file)

## 3. Path validity

Validity is checked per anchor kind.

**File anchors** — before writing a file with file anchors, the synthesis worker MUST:

1. Resolve every file anchor's bucket-relative path to an absolute filesystem path (`<patient_dir>/<bucket-relative-path>`).
2. Verify the target `.md` sidecar exists inside its bucket **and that the bucket prefix is in `01_…14_`**. If it does not exist, the entire write is rejected and the missing path is logged into `readiness.json.warnings` as `"anchor_dangling: <path>"`. A path using the deprecated `ocr/` prefix is treated as dangling; a path using the `15_` prefix is rejected as **not anchorable** (`anchor_not_anchorable: <path>`), which is a different error from dangling — the file may well exist.
3. (Optional but recommended) For `#L<a>-L<b>` fragments, verify `<a>` and `<b>` are within the target file's line count; clamp or reject if out of range.

**Conversation anchors** — no filesystem path to resolve. Validity also requires an explicit provenance layer and actor. They can support patient/caregiver-reported fields only, not clinician/source clinical truth.

## 4. Structured-JSON form

In `patient_summary.json`, `timeline.json`, `molecular.json`, `treatment_lines.json`, `labs.json`, `comorbidities.json`, `missing_items.json`:

- Anchors live in `source_refs: [...]` arrays.

> **`longitudinal_observations.json` exception**: this file carries a **singular** `source_ref: "<anchor>"` string per `observations[]` entry (not a plural `source_refs[]` array). The anchor string itself follows the same regex below; only the field name/cardinality differs. The acceptance gate (`validate_structured_outputs.py` `collect_source_refs`) validates both the plural `source_refs[]` and the singular `source_ref` forms.
- Each entry is the **path-only** (file anchor) or **`conversation:<ISO8601>`** (conversation anchor) string, with no surrounding `[[src:` / `]]`.
- For file anchors the fragment is preserved: `"04_诊断与分期/病理报告/2024-03-15_病理报告_x.md#L22-L29"` is valid.
- For conversation anchors: `"conversation:2026-06-07T14:32:05Z"` is valid.

Schemas in [`*.schema.json`](README.md) enforce this via the regex:

```
^(([0-9]{2}_[^\s/]+(/[^\s/]+)*\.md(#L\d+(-L\d+)?|#[A-Za-z0-9_-]+)?)|(conversation:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?))$
```

The first alternative matches a bucket-relative `.md` path (leading `NN_` bucket segment, optional `#fragment`); the second matches a `conversation:<ISO8601>` reference. The legacy `^(ocr/|02_脱敏病历/)…` pattern is retired.

> **The regex is necessary but not sufficient.** `[0-9]{2}_` syntactically admits `15_`, `99_` and any
> other two-digit prefix. The acceptance gate MUST additionally assert the prefix is one of
> `01`–`14`; `15_` (open archive), `99_` (quarantine) and `raw/` (vault) are rejected at that check,
> not by the regex. Do not relax the gate on the grounds that "the regex allows it".

## 5. Why this matters

- **Downstream trust** — vMTB pathologist refuses to cite a fact without an anchor, eliminating fabrication.
- **Patient verifiability** — every fact in the patient-facing summary card can be inspected by clicking through to the redacted bucket sidecar (file anchor) or the confirmed chat turn (conversation anchor).
- **Audit trail** — when a regulator or treating physician asks "where did this molecular result come from", the chain is in the file itself.

Failure to honor this contract is a P0 bug — surfaced as a `🔴 red` flag in `review_flags.md` with
`category: coverage_gap` (the `readiness.schema.json` enum has no `anchor_coverage_gap` member; the
anchor detail goes in the flag's message, not in a category value the schema rejects) and
`audience: internal_qc`.

## 6. `current_source_values[].source_ref` — a deliberately looser reference

`profile.json`'s `current_source_values[]` is a *first-read convenience projection*, not a citation
surface, so its `source_ref` accepts **three** forms and is validated more loosely than a
`source_refs[]` entry:

```
source_ref := <anchor>                 # a normal file or conversation anchor (§1)
            | "source:<source_id>"     # source-level attribution when no single span carries the value
            | null                     # value is present but its provenance is not resolvable to either
```

- `"source:<source_id>"` exists for values that are true of a whole source rather than of one span
  (a report-level assay name, a document-level collection date). Requiring a `bbox`-resolvable
  anchor there used to force producers to invent a span, which is worse than admitting the
  granularity.
- `null` is legal and means "unresolved", not "no source". It is a visible gap, not a silent one.
- **The looseness stops here.** `source_refs[]` in the structured JSON set, and every `[[src:…]]` in
  narrative output, still take anchors only — `"source:<source_id>"` and `null` are **invalid** there.
- The `15_` prohibition applies to all three forms: `"source:<source_id>"` is allowed for a `15_`
  source only because it carries no bucket path; it still does not make the value citable and still
  does not admit it to a confirmed-fact surface.

## 7. Anchor checks extend to markdown artifacts

The `15_`-is-not-anchorable check is **not** limited to structured JSON. The acceptance gate scans
`timeline.md`, `case_text.md`, `review_summary.md` and `INDEX.md` for `[[src:15_…]]` tokens and
reports each one as an **ERROR** (`anchor_not_anchorable`). A narrative artifact is exactly where an
un-citable open-archive path would do the most damage, because a human reader sees a working-looking
citation.

The complementary containment check is deliberately **narrow**: only `source_refs[]` / `source_ref`
entries and chart data-source references may not point at `extracted_fields.json`. Prose that merely
*mentions* `extracted_fields.json` (this document does, repeatedly) is not a violation.
