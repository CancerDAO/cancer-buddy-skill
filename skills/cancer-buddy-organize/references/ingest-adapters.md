# Ingest Adapters — per-modality ingestion (`scheme_version: 3`)

> How a non-`text` source becomes a sidecar + structured output. Dispatch is by the `modality` tag
> (`bucket-taxonomy.md` §2), set during Phase 1. Every adapter is **LLM-driven** — no hardcoded
> keyword/column parsers. An adapter never invents data; unreadable → stub + `[INGESTION_BLOCKED]`,
> surfaced as a review flag, never silently dropped. PII masking rules (`phase1-ocr.md §2.4`) apply
> to every adapter's sidecar output exactly as for `text`.

## Dispatch table

| `modality` | source examples | sidecar body | structured target | bucket |
|---|---|---|---|---|
| `text` | discharge summary, pathology narrative | verbatim Markdown transcription | the 6 structured JSONs | clinical domain |
| `image` | CT series, IHC slide photo | ≤5-line vision stub (modality + body region + visible date) | — (imaging stub) | `05_影像` etc. |
| `structured` | CBC sheet, biochemistry panel | Markdown table, verbatim values+units | `labs.json` (+ trend → `longitudinal_observations.json`) | `07_检验` |
| `omics_raw` | VCF / annotated TSV / expression matrix | header + variant/feature summary table | `molecular.json` | `06_分子与组学` |
| `timeseries` | wearable export, glucose log, PRO diary | summary stub + sample rows | `longitudinal_observations.json` | `10_随访与监测` |
| `binary_other` | BAM / FASTQ / DICOM / proprietary | metadata-only stub + `[INGESTION_BLOCKED]` | — (archived raw) | matching clinical domain |

## 1. `omics_raw` adapter

Input: a parseable omics payload (VCF, MAF, annotated variant TSV, fusion report, expression/methylation
matrix). For oversized matrices the host supplies a head/tail + column header as the LLM-readable input
(`bucket-taxonomy.md` §2; the raw file is still filed + mirrored).

Sidecar (`06_分子与组学/<subtype>/<canonical>.md`):
1. Header per `phase1-ocr.md §2.3` plus `MODALITY: omics_raw` and an `ASSAY:` line (assay/panel/platform
   if stated, else `unknown`).
2. A verbatim **variant/feature table** — one row per called variant or top feature: `gene | HGVS (c./p.) |
   VAF/expr | consequence | zygosity | filter`. Values verbatim; never normalize a gene/HGVS string, never
   "correct" a variant to a look-alike (anti-anchoring, `phase1-ocr.md`). Unreadable cell →
   `[OCR_UNCERTAIN: verbatim | alt]`.
3. `## PII` trailer (sample IDs / names that appear in VCF headers are PII → mask).

Phase 2 lifts each row into `molecular.json` with a `source_ref` anchor back to this sidecar. Germline
calls go to the `胚系检测` subtype, somatic to `NGS报告`. **No clinical interpretation here** — that is
the geneticist/vMTB's job; the adapter is faithful transcription + structuring only.

## 2. `timeseries` adapter

Input: a tabular stream export (Apple Health / Huawei / device CSV, glucose/BP log, a PRO questionnaire
series). The raw export is filed into `10_随访与监测/{可穿戴导出|PRO自报|居家监测}` and mirrored.

Sidecar (`10_随访与监测/<subtype>/<canonical>.md`):
1. Header + `MODALITY: timeseries` + a `SERIES:` line (metric name(s) + date span + sample count, verbatim).
2. A **summary stub** (≤8 lines): which metrics, units, date range, sampling cadence, plus 3–5 sample rows
   verbatim. Do NOT transcribe thousands of rows into the sidecar — the series lives in JSON.
3. `## PII` trailer.

Phase 2 parses the full series into `longitudinal_observations.json`
(`schemas/longitudinal_observations.schema.json`), one entry per observation:
`{obs_type, metric, value, unit, timestamp, modality:"timeseries", source_ref:"10_随访与监测/...md#L.."}`.
`obs_type` ∈ {vital, lab, symptom, pro, adherence, activity}. PRO instrument scores (PHQ-9, distress
thermometer, ESAS) map to `obs_type:"pro"` with `metric` = the instrument name verbatim. Trended
`structured` labs (same analyte across dated panels) are ALSO appended here as `modality:"structured"` so
a trajectory exists, while the per-panel value still lives in `labs.json`.

This is the substrate for **单时间点 → 多时间点 → 纵向曲线 → 治疗反应轨迹** (`bucket-taxonomy.md` §3).

## 3. `binary_other` adapter

Input: opaque/oversized binary the LLM cannot read (BAM, FASTQ, DICOM stack, vendor blob). Do NOT fabricate
content. File the raw bytes into the matching clinical domain (`06_分子与组学` for sequence data,
`05_影像` for DICOM) + mirror. Sidecar = a metadata-only stub: format, file size, and any
externally-stated descriptors (assembly, sample, modality) + `[INGESTION_BLOCKED: <reason>]`, and a
`review_flag` so the gap is visible. The raw file remains available for an out-of-band specialist pass.

## Invariants (all adapters)

- **LLM-driven, never hardcoded parsers** (`feedback_default_prompt_over_script`): column→field, variant
  reading, instrument recognition are semantic judgments, not regex keyword lists.
- **Verbatim clinical fidelity** — adapters mask PII only; they never translate/normalize/round a gene,
  HGVS, dose, analyte value, unit, or timestamp.
- **No interpretation** — adapters transcribe + structure; clinical meaning is downstream (geneticist /
  oncologist / vMTB).
- **No silent drop / no sampling** — every source yields a sidecar (full table, stub, or BLOCKED stub);
  unreadable surfaces a flag.
- **Modality is recorded** in the sidecar header and `source_inventory.json.modality`; dispatch reads it.
