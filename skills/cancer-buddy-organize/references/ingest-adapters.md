# Typed ingest adapters (段 0)

Adapters run in **段 0**, before any model call. They convert supported formats into
source-preserving page packages. They do not interpret treatment effect or clinical significance.

## What an adapter produces

For every page (or record) of every source, an adapter emits:

1. **A rendered page** — `pdftoppm` at the contract default `-r 150` for PDFs; the original
   file for photos (no re-encode); nothing for non-visual modalities.
2. **A text layer** — that page's character layer (`pdftotext`, docx payload, cell values, or a
   format-specific decoder's output).
3. **A `text_layer_kind` verdict** — the classification that decides which 段 1 rule applies:

   | value | how it is decided |
   |---|---|
   | `born_digital` | `pdftotext` returns non-empty text **and** font information is present on the page |
   | `embedded_ocr` | a text layer exists but the page is essentially one full-page image (scanner OCR output) |
   | `absent` | no text layer |
   | `not_applicable` | non-visual modality decoded by a deterministic tool (see below) |

4. **An optional deterministic OCR appendix** — `tesseract` or equivalent, stored under
   `raw/adapter_views/…/ocr_appendix`. It is a **three-state additive signal, never truth and never
   a veto**: 0 bytes or garbage = no signal (emits no flag); parseable and in numeric conflict on a
   high-risk field = triggers a second read; parseable and agreeing = confidence bonus.
5. **A cache key** — `sha256(page image) + prompt_version + model_id`. A hit skips the model call
   entirely and reuses `raw/_cache/transcripts/<key>.md`.

Adapters also detect orientation (`needs_rotation`), blank pages, and duplicate pages
(perceptual hash) so 段 1 does not pay for pages with no content.

## Required metadata

Every adapter records source ID/hash, adapter/version, modality, `text_layer_kind`, extraction time,
raw location, transcript location, sidecar location, source row/page/span, transformation log, and
verification status.

## Non-visual modalities (the LLM never decodes binary)

DICOM, VCF/BAM/FASTQ, wearable exports and proprietary formats are **not images and not paper**.
A validated format-specific tool decodes them here, in 段 0, and the decoded result becomes the
`text_layer` handed to 段 1 with `text_layer_kind: not_applicable`.

The `modality` values in the first column are the **closed set** recorded on every inventory row
and asserted in the 段 1 sidecar frontmatter (`bucket-taxonomy.md` §2) — an adapter never invents a
new one:

| `modality` | meaning |
|---|---|
| `text` | native prose or transcribed document |
| `image` | imaging / scan |
| `structured` | tabular numeric report |
| `omics_raw` | parseable omics payload (VCF / annotated TSV / matrix) |
| `timeseries` | longitudinal stream (wearable export, glucose log, PRO diary) |
| `binary_other` | unsupported / opaque binary (BAM / FASTQ / raw DICOM / proprietary) |

| modality | what 段 0 decodes | what it never does |
|---|---|---|
| DICOM | headers/metadata and structured reports (device, series, acquisition time, slice thickness, position, report text) | never interprets pixels; no imaging diagnosis |
| VCF / annotated TSV | header + records: chromosome, position, REF/ALT, HGVS, VAF, FILTER, depth, reference build | never "fixes" a look-alike variant |
| BAM / FASTQ / CRAM | nothing — records existence, hash, size, and a pointer to the companion report | never samples reads to "summarize" |
| wearable / timeseries | metric, value, unit, timestamp, device → observation series | never derives a response trajectory |
| unsupported proprietary | a PARTIAL/BLOCKED stub stating what could and could not be read | never guesses |

**An LLM must not pretend to decode binary data**, must not claim a visual read on a
`not_applicable` source, and must not emit a `bbox` for one (its span carries
`text_layer_offset` only). Full per-modality routing is in [`domain-pack.md`](domain-pack.md) §3.

Second reads on non-visual modalities are deterministic: the adapter output *is* the deterministic
layer, so `reread_channel: text_layer` and the comparison is a script, costing zero model calls. If
the adapter cannot read the field, that field's `high_risk_fields[].status` becomes
`needs_human_review` (the row-level `high_risk_review_status` is derived from the per-field entries)
— never "let the model fill it in".

The `reread_channel: text_layer` precondition is `text_layer_kind ∈ {born_digital, not_applicable}`.
The gate exists to exclude **`embedded_ocr`**, whose text layer is a scanner's own OCR output — using
it as the second channel means one OCR vouching for another. A `not_applicable` layer comes from a
validated format-specific decoder and is at least as independent as a born-digital character layer,
so excluding it would push every VCF variant and every DICOM header field into the human-review
queue for no safety gain.

## Molecular/omics

Preserve exact gene/variant notation, VAF representation, sample/site/date, assay, tumor-only vs paired,
quality/LOD, tumor purity, report version and source classification. Never correct a look-alike variant,
infer germline status, merge MSI with MMR, assign actionability, or connect a result to a drug.

**These invariants hang on `clinical_class: molecular`, not on the destination bucket.** Path-based
claiming was the hole: a new sequencing vendor's panel filed into `15_未分类资料/<slug>/` used to slip
past `_has_ngs_source`, leaving `molecular.json` empty with zero warnings while a downstream board
convened on an empty record. A source declared `clinical_class: molecular` triggers the molecular
completeness gate **wherever it is filed**, and must carry the sibling source-shape keys; missing
them is an ERROR, not a WARN.

## Laboratory/timeseries/PRO/wearable

Preserve each raw value, unit, method/device, timestamp, report-specific reference range and source. Keep
patient-reported and device/clinical observations separate. Unit conversion requires deterministic tested
code and retains the raw value/formula. The output is a neutral observation series, not a treatment-response
trajectory.

**Likewise keyed on `clinical_class: lab`, not on the bucket.** An open-archive lab source is still
subject to the lab gate and to the **sibling source-shape keys** that every row must carry —
`kind`, `doc_kind`, `clinical_class`, `text_layer_kind`, `modality`, `raw_path`, `transcript_path`
(`novel_reason` in addition when `kind: novel`). Open key-values in `extracted_fields.json` carrying
`clinical_class: lab` must carry `unit` and `source_reported_text`.

(Earlier drafts said "the seven source-shape keys" without listing them, which is how a row shipped
missing `modality` while every reader assumed some other seven. The list above is the list; if it and
`schemas/source_inventory.schema.json` disagree, the schema wins and this line is the drift bug.)

## Unsupported or partial formats

Never silently sample or drop. Produce a BLOCKED/PARTIAL stub describing what could and could not be
read, route high-risk fields to human review, and write the inventory row with `kind: unreadable`.
An `unreadable` source must not be counted as covered by any patient-facing surface; it appears in
`readiness.json.projection_coverage.summary.unreadable_sources`.

PII minimization and export rules apply to all sidecars; masked text is not guaranteed anonymous.
The verbatim `raw/transcript/` layer is under the same access control as `raw/` and is excluded from
every export.
