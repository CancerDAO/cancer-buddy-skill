# Typed ingest adapters

Adapters convert supported formats into source-preserving sidecars. They do not interpret treatment
effect or clinical significance.

## Required metadata

Every adapter records source ID/hash, adapter/version, modality, extraction time, raw location, sidecar
location, source row/page/span, transformation log, and verification status.

## Molecular/omics

Preserve exact gene/variant notation, VAF representation, sample/site/date, assay, tumor-only vs paired,
quality/LOD, tumor purity, report version and source classification. Never correct a look-alike variant,
infer germline status, merge MSI with MMR, assign actionability, or connect a result to a drug.

## Laboratory/timeseries/PRO/wearable

Preserve each raw value, unit, method/device, timestamp, report-specific reference range and source. Keep
patient-reported and device/clinical observations separate. Unit conversion requires deterministic tested
code and retains the raw value/formula. The output is a neutral observation series, not a treatment-response
trajectory.

## Unsupported or partial formats

Never silently sample or drop. Produce a BLOCKED/PARTIAL stub describing what could and could not be
read, and route high-risk fields to human review. Binary data (DICOM, BAM/FASTQ, proprietary exports)
requires a validated format-specific tool; an LLM must not pretend to decode it.

PII minimization and export rules apply to all sidecars; masked text is not guaranteed anonymous.
