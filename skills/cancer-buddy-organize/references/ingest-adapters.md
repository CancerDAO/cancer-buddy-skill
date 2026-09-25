# Typed ingest adapters

Adapters convert supported formats into source-preserving sidecars. They do not interpret treatment
effect or clinical significance.

## Required metadata

Every adapter records source ID/hash, adapter/version, modality, extraction time, raw location, sidecar
location, source row/page/span, transformation log, and verification status. Hash, byte size and page
count come from `scripts/inventory_hash.py`; the sidecar header is the 12-key block defined in
`organizer-prompt-phase1-ocr.md` §3 (worker id in `EXTRACTOR`, printed page label verbatim in
`PAGE_LABEL`). Inputs that are not content (`.DS_Store`, `__MACOSX/`, empty files, duplicate sha256,
unpacked archive containers) are listed in `source_inventory.json.skipped_inputs[]` with a reason.

## Molecular/omics

Preserve exact gene/variant notation, VAF representation, sample/site/date, assay, tumor-only vs paired,
quality/LOD, tumor purity, report version and source classification. Never correct a look-alike variant,
infer germline status, merge MSI with MMR, assign actionability, or connect a result to a drug.

## Laboratory tables

Bind item, result, unit, reference range and flag to the same printed row. Coordinates or a native/parsed
table come first; with linear text only, `scripts/pair_lab_columns.py` pairs per column (item count equal to
result count → position-paired `candidate_value`, never a confirmed `value`; unit / range / flag columns are
paired only when their own count equals the item count; item count ≠ result count → no pairing at all).
Details: `organizer-prompt-phase1-ocr.md` §7.

## Laboratory/timeseries/PRO/wearable

Preserve each raw value, unit, method/device, timestamp, report-specific reference range and source. Keep
patient-reported and device/clinical observations separate. Unit conversion requires deterministic tested
code and retains the raw value/formula. The output is a neutral observation series, not a treatment-response
trajectory.

## Unsupported or partial formats

Never silently sample or drop. Produce a BLOCKED/PARTIAL stub (`[INGESTION_BLOCKED: <reason>]`) describing
what could and could not be read, and route high-risk fields to human review. A file that is merely slow is
not skipped either: after a timed-out single-file retry, a stub worker writes `[INGESTION_BLOCKED: timeout]`. Binary data (DICOM, BAM/FASTQ, proprietary exports)
requires a validated format-specific tool; an LLM must not pretend to decode it.

PII minimization and export rules apply to all sidecars; masked text is not guaranteed anonymous.
