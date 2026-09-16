# Structured Output Schemas (Draft 2020-12)

These JSON Schemas define the structured outputs `cancer-buddy-organize` produces alongside `profile.json`. They are the contract that downstream consumers (vMTB, MTB-lite, trial-match, patient data export) rely on.

| File | Schema | What it carries |
|---|---|---|
| `patient_summary.json` | [patient_summary.schema.json](patient_summary.schema.json) | Demographics + diagnosis + current_status — single rollup |
| `timeline.json` | [timeline.schema.json](timeline.schema.json) | Chronological clinical events |
| `molecular.json` | [molecular.schema.json](molecular.schema.json) | NGS variants + IHC + MSI/MMR + TMB |
| `treatment_lines.json` | [treatment_lines.schema.json](treatment_lines.schema.json) | Chronological treatment episodes; line labels only when documented |
| `labs.json` | [labs.schema.json](labs.schema.json) | Lab panels with serial values |
| `comorbidities.json` | [comorbidities.schema.json](comorbidities.schema.json) | Conditions + long-term meds + allergies |
| `missing_items.json` | [missing_items.schema.json](missing_items.schema.json) | Existing-document inventory gaps; never a test recommendation |
| `source_inventory.json` | [source_inventory.schema.json](source_inventory.schema.json) | Native/deterministic extraction provenance, independent high-risk-field reread status, sidecar path, and protected `raw_path` |
| `readiness.json` | [readiness.schema.json](readiness.schema.json) | Documentation coverage plus source/faithfulness flags; never a clinical readiness score |
| `longitudinal_observations.json` | [longitudinal_observations.schema.json](longitudinal_observations.schema.json) | Neutral longitudinal observations; not a response trajectory |
| `extracted_fields.json` | [extracted_fields.schema.json](extracted_fields.schema.json) | Open key-values projected from novel/unmapped material; each entry carries its own `open_ref`, **not** an anchor |
| `update_log.json` | [update_log.schema.json](update_log.schema.json) | Append-only run history: run_mode, added sources, `pii_semantic` state, faithfulness method |
| `gap_asks.json` | [gap_asks.schema.json](gap_asks.schema.json) | What was asked of the patient for a missing document, and how it ended |
| `raw/_provenance/<run>/human_sample_plan.json` | [human_sample_plan.schema.json](human_sample_plan.schema.json) | The ASK half of the human spot-check — written by a script |
| `raw/_provenance/<run>/human_sample_result.json` | [human_sample_result.schema.json](human_sample_result.schema.json) | The ANSWER half — written by a person; `verdict ∈ match \| mismatch \| unreadable` |

## Anchor token contract

Every factual field carries source reference(s) and, where defined, a provenance layer and verification/dispute status. A conversation anchor supports only a patient/caregiver-reported statement; confirmation does not make it clinician/source truth. Each anchor is a bucket-relative path or `conversation:<ISO8601>`:

```
<NN_bucket>/<…>/<file>.md[#L<start>-L<end>]
<NN_bucket>/<…>/<file>.md[#section-anchor]
conversation:<ISO8601>
```

File-anchor paths MUST begin with an **anchored** clinical-domain bucket prefix (`01_…` … `14_`, scheme_version 4) — the open bucket `15_未分类资料/`, the infrastructure vault `raw/` (including `raw/transcript/`, `raw/_cache/`, `raw/_provenance/`) and the quarantine `99_无关文件/` are never anchor targets, and the legacy `02_脱敏病历/` prefix is **retired**, and the transient central `ocr/` staging dir (live during a run, drained + deleted by 段 2; it MUST NOT exist in a completed archive) is **not a valid anchor prefix** in final artifacts. Sidecars now live next to their image inside the clinical-domain bucket subdirectory. The full contract (regex included) is in [anchor-contract.md](anchor-contract.md).

In narrative artifacts (`case_text.md`, the human-readable patient summary), the same anchors appear in `[[src:...]]` syntax — see [anchor-contract.md](anchor-contract.md).

## New and changed fields (`scheme_version 4`)

### `extracted_fields.schema.json` (new)

```
{ schema_version: "1",
  entries: [ { source_id, page, doc_kind, clinical_class, label, value, unit?,
               source_reported_text?,
               open_ref: { source_id, page, bbox: [x0,y0,x1,y1] },
               open_verification_status: unverified|settled|needs_human_review,
               reread_channel? } ] }
```

- The state field is **`open_verification_status`** (`unverified | settled | needs_human_review`),
  deliberately **not** named `verification_status` — the structured-JSON `verification_status` is
  `unverified | clinician_verified | disputed`, and one name carrying two different enums is how
  "has this been checked?" ends up answered differently on two surfaces. This is the one place the
  literal `settled` survives; a high-risk field that passed its second read is recorded as
  `high_risk_fields[].status: passed_independent_reread`, never as "settled".
- `label` is copied **verbatim** from the source. The only constraints are length **≤ 120**,
  no control characters (including zero-width), and non-empty — it is **not** put through the `15_`
  slug whitelist, which exists to make a `mkdir` safe and would silently rewrite ordinary assay names
  like `WBC (10^9/L)` or `c.2573T>G`.
- `bbox` is normalized 0–1 with origin top-left, anchored to the **`raw/` page**, never to a Markdown
  line number.
- A `clinical_class: lab` entry MUST carry `unit`; a `lab` or `molecular` entry MUST carry
  `source_reported_text` (the verbatim source string).
- **`open_ref` is not an anchor.** It exists precisely so open fields cannot be cited as confirmed
  facts. This file is **not** a legal source store for charts or core-completeness; see
  [anchor-contract.md](anchor-contract.md) §1c.

### `source_inventory.schema.json` (`files[]`, `additionalProperties: false`)

| field | type | required |
|---|---|---|
| `kind` | enum `known \| novel \| unreadable` | yes |
| `doc_kind` | string — a known type name or `novel:<slug>` | no |
| `clinical_class` | enum `molecular \| lab \| imaging \| pathology \| narrative \| admin \| unknown` | yes |
| `text_layer_kind` | enum `born_digital \| embedded_ocr \| absent \| not_applicable` | no |
| `novel_reason` | string, ≥8 chars | yes when `kind: novel` |
| `reread_channel` | enum `text_layer \| barcode \| deterministic_ocr \| alternate_vision_model \| human \| none` | no |

| `transcript_path` | string, MUST start with `raw/transcript/` | yes for any transcribed source |
| `transcribe_model_id` | string — the model id that produced the 段 1 primary read | yes |
| `high_risk_fields` | array of `{label, status, reread_channel, reread_model_id?, readings[]}` | yes when the source has any high-risk field |

(The `transcript_path` row used to sit *below* a paragraph of prose, which broke the Markdown table
in two and hid the last rows from every renderer. The table is one table.)

**`high_risk_fields[]` is per-field; the row-level fields are derived summaries.**

- `high_risk_fields[].status` ∈ `passed_independent_reread | needs_human_review | not_applicable`.
- `high_risk_review_status` (row level) = `needs_human_review` if any entry is; else
  `passed_independent_reread` if all are; else `not_applicable` when `high_risk_fields[]` is empty.
  There is no separate "pending" state.
- `reread_channel` (row level) is the **dominant channel** summary; the per-field truth is
  `high_risk_fields[].reread_channel`.
- `passed_independent_reread` is valid **only** when `reread_channel != none` **and** that channel is
  independent (a different model, a different modality, or a human — never the same model re-reading
  the same image). "No independent channel was available" maps to `needs_human_review` with
  `reread_channel: none` — **never** `human`, which asserts a spot-check verdict.
- `reread_channel: alternate_vision_model` requires `reread_model_id`, and it MUST differ from the
  row's `transcribe_model_id`.
- `reread_channel: text_layer` requires `text_layer_kind: born_digital` (schema `allOf` + gate) — an
  `embedded_ocr` text layer is a scanner's OCR output, a comparison channel, not a deterministic one.
- `reread_channel: human` requires a matching verdict in
  `raw/_provenance/<run_id>/human_sample_result.json` — at the **row** level too, not only
  per field. A row-level `human` summary with no verdict anywhere for that source is the
  cheapest unverifiable claim in the structure, and it is an ERROR.
- `high_risk_fields[].readings[].channel` ∈
  `transcribe | text_layer | barcode | deterministic_ocr | alternate_vision_model | human`.
  The first read is spelled **`transcribe`** — not `first_read`, not `model_vision_primary`.
  `none` is deliberately **not** in this enum: "no second read happened" is the *absence* of a
  second `readings[]` entry, never a reading whose channel is nothing.
- **The set of `high_risk_fields[]` is not the run's to choose.** `scripts/_high_risk.py` is the
  single authority (shared with `plan_second_read.py`); the validator recomputes the high-risk
  label set from each source's own page frontmatter and requires `high_risk_fields[]` to **cover**
  it. Declaring *more* is always legal; declaring fewer — including the total case
  `high_risk_fields: []` on a page whose frontmatter prints 住院号 / WBC / 剂量 — is an ERROR.
  Over-inclusion costs one extra recorded second read; under-inclusion is an archive certifying
  its own exemption.

### `legacy_transcript_unavailable` (migration-only escape hatch)

| field | type | required |
|---|---|---|
| `legacy_transcript_unavailable` | boolean | no — and only `scripts/migrate_v3_to_v4.py` may write it |

A scheme-3 row whose characters a model read (`read_mode: model_vision_primary` /
`model_vision_assist`) predates per-page transcripts, so it cannot produce a `transcript_path`:
the file was never written and re-reading the pages would be a new run, not a migration. This flag relaxes
**four** requirements for exactly that row, all of which are the same requirement seen from
different angles — *produce evidence drawn from a page that no longer exists anywhere*:

| relaxed | what it would otherwise demand | why it cannot be met |
|---|---|---|
| `transcript_path` (schema `allOf` + `gate_transcripts`) | a file under `raw/transcript/` | it was never written; v3 kept no per-page transcript |
| `gate_high_risk_denominator` | a `high_risk_fields[]` entry per recomputed high-risk label | a second read would have to re-open pages that are no longer transcribed |
| `gate_faithfulness` | a `faithfulness-*.json` span per high-risk label | there is no page image and no transcript to draw a bbox on |
| `gate_human_sample` | a spot-check plan + verdicts | nobody can sample a field with no page behind it |

`migrate_v3_to_v4.py` writes `high_risk_fields: []`, `high_risk_review_status: "not_applicable"`
and `reread_channel: "none"` on such a row, which is what those three gates then see and skip.

The price is **moved, never waived**. `gate_projection_coverage` counts the row in
`summary.unreadable_sources`, and the archive must carry a `review_flag` with
`category: coverage_gap` / `audience: internal_qc`. Since C3 that gate also ERRORs when
`readiness.json` is **missing or unparseable** while such rows exist — otherwise the four
exemptions above could be collected in total silence, which is the one outcome the flag must never
buy. It must never appear on a row a v4 run produced; there it would mean a transcript the run
simply declined to write.

`read_mode` (top level) gains `model_vision_primary`; `extractor_provenance.llm_role` gains
`primary_transcription`.

**`scheme_version` is `enum: [3, 4]` and it must be DECLARED.** A writer emits `4`; a reader must
still accept an explicit `3`, which selects the legacy branch (the validator WARNs and points at
`scripts/migrate_v3_to_v4.py` rather than failing an archive written before v4). **Absent is not
`3`.** Treating silence as legacy meant every v4-only gate — open-domain filing, the
`clinical_class` floors, per-field second-read independence, the human spot-check, faithfulness
coverage, projection coverage, review-flag audience, field provenance, the high-risk denominator —
could be switched off by deleting one key, which is the cheapest bypass a gate can have. An
omitted `scheme_version` is now an ERROR that names both legal answers.

A **half-migrated** archive (`scheme_version: 4` over rows with no `kind` / `clinical_class`) gets
its own ERROR naming `scripts/migrate_v3_to_v4.py <patient_dir> --force`, rather than a dozen
unrelated-looking schema violations.

`readiness.json`'s own `schema_version` is bumped to `"3"`. `"2"` is read leniently and WARNed
**only inside an archive that declares `scheme_version: 3`**. A `scheme_version: 4` inventory over a
`schema_version: "2"` readiness is an **ERROR** (C12), not a warning, and the file gets no lenient
read: schema 2 is precisely the shape with no `review_flags[].audience`, no `category` enum and no
`projection_coverage` — the fields `gate_review_flag_audience` and `gate_projection_coverage` read.
Relaxing it left a *current* archive's review surface unchecked, so QC noise could still reach a
family as 「请医生确认」. The remedy is named in the error: `migrate_v3_to_v4.py <dir> --force`.

### Two version keys, on purpose — and `readiness.json` has only one

| file | version key | values |
|---|---|---|
| `source_inventory.json` | `scheme_version` (integer) | `3` (legacy, WARN) / `4` (current) |
| `readiness.json` | `schema_version` (string) | `"2"` (legacy — WARN under `scheme_version: 3`, **ERROR** under `4`) / `"3"` (current) |

`update_log.schema.json`'s `runs` carries **`minItems: 1`**. An empty `runs[]` reproduces exactly
the bypass that deleting the file used to be: no deferred PII pass to find, no `run_mode` for
`export_share.py` to anchor its retro-check on, nothing for a later incremental run to
short-circuit against. `pii_semantic` is `required` on every run for the same reason — an unset key
was cheaper than an honest `"deferred"`, and `export_share.py` reads an unset key as clean.

`readiness.json` deliberately does **not** carry `scheme_version`, and its schema is
`additionalProperties: false`, so adding one is a validation error rather than a harmless
annotation. The two keys answer different questions: `scheme_version` is the **bucket-taxonomy**
generation the archive was filed under (which directories are legal, whether `15_` exists at all),
while `schema_version` is the shape of **this one document**. A file that declared both would be
asserting something about the taxonomy from a surface that does not file anything, and the two
would drift the first time one of them bumped alone. The archive's taxonomy generation is read from
the inventory, once, by `archive_is_legacy_v3()`.

### `read_mode` values nothing currently writes

`read_mode` (`source_inventory.json`, `update_log.json.runs[].added_sources[]`) carries three
enum values that no shipped code path emits today. They are **reserved, not dead**, and they are
kept because the alternative — mislabelling a future deterministic adapter as `deterministic_ocr`
or, worse, as `model_vision_primary` — would put non-visual extraction under the wrong
independence rules:

| value | reserved for | why it is not `deterministic_ocr` |
|---|---|---|
| `table_parser` | a structured-table extractor reading cells from a born-digital PDF/XLSX grid (no rasterization, no glyph recognition) | it never looks at pixels, so its output is an *independent channel* against a vision read rather than a second opinion on the same image |
| `barcode_parser` | a 1D/2D symbology decode (检验号 / 标本号 barcodes) with an error-correcting checksum | a checksum-verified decode is stronger evidence than any OCR run, and `reread_channel: barcode` already depends on the distinction |
| `hybrid_verified` | a unit whose characters are the **agreed** output of two independent extractors, recorded as agreeing | it is a *conclusion about two channels*, not a channel; labelling it `deterministic_ocr` would hide that two things were compared |

A future adapter that emits one of these must still obey the high-risk rule: the value describes
where the characters came from, never that they were verified.

### `readiness.schema.json`

| field | type | required |
|---|---|---|
| `review_flags[].audience` | enum `clinician \| internal_qc` | yes |
| `review_flags[].category` | enum `transcription_disagreement \| ocr_artifact \| untrusted_content_marker \| pii_semantic_deferred \| source_conflict \| source_faithfulness \| coverage_gap \| other` | yes |
| `projection_coverage` | `{ per_source: [{source_id, unprojected_field_classes: [string]}], summary: {sources_total, sources_fully_projected, novel_sources, unreadable_sources} }` | — |

`projection_coverage` quantifies "field classes that exist in the full text but were not projected
into a known slot". An empty `unprojected_field_classes` array means fully projected; an **absent**
entry for a source is a bug, not the same thing.

## Validation

The synthesis worker validates each JSON it writes against its schema before saving. If validation fails, the file is NOT written and the error is surfaced into `readiness.json.warnings`.

A minimal validator is shipped in `scripts/validate_structured_outputs.py` (consumes `jsonschema>=4.18`).

### Gates that read `raw/transcript/` alongside the schemas

Three gates share the verbatim vault and ask the three different questions it can be wrong in.
They run consecutively, in this order, because each later one measures something the earlier one
must already have established:

| gate | assertion | verdict |
|---|---|---|
| `gate_transcripts` | every row declaring a `transcript_path` has that file; the masked sidecar carries no unmasked PII shape; nothing outside `raw/` references the vault | ERROR |
| `gate_page_completeness` (C5) | for each source, every page `pages.json` records with `kind != "unreadable"` has a `raw/transcript/<sid>/page-NNN.md`; **missing page numbers are listed** | ERROR — WARN when `pages.json` is absent but transcripts exist |
| `gate_sidecar_transcript_consistency` (C6) | every bucket-sidecar `fields[].value` is findable in that page's transcript `fields[].value` | ERROR |

**Why `gate_page_completeness` exists.** Every other gate iterates over what EXISTS, so the
cheapest way to pass all of them at once was never to cheat on a page — it was to lose one. A
five-page report yielding four transcripts has four clean pages, four verified spans and a field
provenance record that reconciles perfectly; the fifth page is simply not in any denominator.
`pages.json` is the only surface written *before* the transcription pass, by a deterministic script
that counted the pages in the file, so it is the one honest statement of how many pages the
document has. Pages already marked `kind: unreadable` are exempt **by name**: a declared gap is a
disclosure, an absent page is not. `native_text` sources (no per-page transcript by contract) and
`legacy_transcript_unavailable` rows are out of scope.

**Why `gate_sidecar_transcript_consistency` exists.** The sidecar is *derived* from the transcript
and the only legal difference between them is masking. `gate_field_provenance` reads the transcript
when one exists and so never compares the two surfaces; `gate_transcripts` checks the sidecar for
unmasked PII, which is the opposite direction. A sidecar carrying `9.99` where the transcript says
`3.21` therefore passed every gate — and since every consumer downstream reads the sidecar and
nothing else, that is the number a clinician eventually sees. Matching is: normalized equality →
numeric-token equality → whole-word containment either way (so `"3.21"` matches `"3.21 10^9/L"` but
`"3.2"` does **not** match inside `"3.21"`). A value containing `[PII_MASKED]` is skipped — masking
is the one transformation that legitimately destroys the original — as is any value shorter than
two characters, which is inside almost any string and therefore proves nothing either way.

The validator is also an archive form gate. A final archive includes
`source_inventory.json`; every content unit points to a source-attributed sidecar and a protected original.
Archive completeness is judged as **every source having `raw/` bytes + a masked MD + an inventory row**
— not as "all known slots filled".
This structural check does not prove clinical correctness, authorization, anonymity, or minimum-necessary
sharing. Source-faithfulness and PII semantic review remain separate required gates.
