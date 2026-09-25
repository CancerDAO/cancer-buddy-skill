# Structured Output Schemas (Draft 2020-12)

These JSON Schemas define the structured outputs `cancer-buddy-organize` produces alongside `profile.json`. They are the contract that downstream consumers (vMTB, MTB-lite, trial-match, patient data export) rely on.

| File | Schema | What it carries |
|---|---|---|
| `patient_summary.json` | [patient_summary.schema.json](patient_summary.schema.json) | Demographics + diagnosis + current_status — single rollup |
| `timeline.json` | [timeline.schema.json](timeline.schema.json) | Chronological clinical events |
| `molecular.json` | [molecular.schema.json](molecular.schema.json) | NGS variants + IHC + MSI/MMR + TMB |
| `treatment_lines.json` | [treatment_lines.schema.json](treatment_lines.schema.json) | Chronological treatment episodes; line labels only when documented |
| `labs.json` | [labs.schema.json](labs.schema.json) | Lab panels with serial values |
| `comorbidities.json` | [comorbidities.schema.json](comorbidities.schema.json) | Conditions + medication orders/records with administration setting + allergies |
| `missing_items.json` | [missing_items.schema.json](missing_items.schema.json) | Existing-document inventory gaps; never a test recommendation |
| `source_inventory.json` | [source_inventory.schema.json](source_inventory.schema.json) | Native/deterministic extraction provenance, independent high-risk-field reread status, sidecar path, and protected `raw_path` |
| `readiness.json` | [readiness.schema.json](readiness.schema.json) | Documentation coverage plus source/faithfulness flags; never a clinical readiness score |
| `longitudinal_observations.json` | [longitudinal_observations.schema.json](longitudinal_observations.schema.json) | Neutral longitudinal observations; not a response trajectory |
| `acute_findings.json` | [acute_findings.schema.json](acute_findings.schema.json) | Acute / incidental findings the source itself reports (always written — on a legacy Phase-2-only pass too, where `timeline_event_id` may be null; `findings: []` when none; not a current-contract marker); each one ↔ one timeline `acute_finding` event on a current archive; acuity from the fixed class table, never model triage |
| `update_log.json` | [update_log.schema.json](update_log.schema.json) | Run ledger: workers (sidecar `EXTRACTOR` must be one of them), input sha256, added/removed, degradations. Entries are closed: the retired orchestrator-written `relevance[]` / `case_summary_stale` are rejected — 段E decisions are a Phase 2 worker's `run_mode: relevance_disposition` entry; a conversation-only entry writes `workers: []`, `inputs: []` |
| `organize_meta.json` | [organize_meta.schema.json](organize_meta.schema.json) | Which organize build produced the archive (version / commit / fingerprint); read by SMTB |
| `gap_asks.json` | [gap_asks.schema.json](gap_asks.schema.json) | Conditional ask-once ledger of invitations to add an existing document; written only by `scripts/record_gap_ask.py`; never a clinical priority |

## Versions and legacy archives

| File | Current | Legacy read (WARN, not FAIL) | What the current version adds |
|---|---|---|---|
| `readiness.json` | `2.1` | `2` | review_flags `severity` (red/yellow/info — an extraction / archive-integrity uncertainty grade, **not** clinical severity) + `kind` (legibility / artifact / document_intent / conflict / completeness / other), optional `cross_doc_supported` / `uncertain_ids`, optional `current_source_values[].channel`; top-level `latest_source_date` / `days_since_latest` / `as_of_run_date` (the local run date; update_log `at` is UTC, ±1 day tolerated) |
| `patient_summary.json` | `2.2` | `2`, `2.1` | `demographics.performance_status_verbatim[]` (verbatim, never converted between scales; optional per-item `provenance_layer` — `prior_archive` for a digest statement, history only) |
| `timeline.json` | `2.1` | `2` | `conflict_group`, `acute_finding_id`, category `acute_finding` |
| `labs.json` | `2.1` | `2` | `pairing_method` (+ `candidate_value` / `pairing_confidence` / `pairing_note`); a `linear_position` or `llm_row_read` row keeps `value: null`, and only those two methods may carry a `candidate_value` |
| `comorbidities.json` | `2.1` | `2` | medication `administration_setting` + `setting_basis` (+ optional `order_role`, `medication_id`); `inpatient` / `long_term` are reserved values the current rules never assign |
| `treatment_lines.json` | `2.1` | `2` | episode `status` + `status_basis` (+ `status_basis_text`, `status_as_of`, `line_number`, `medication_refs`; optional `cycle_label_verbatim` — every cycle of one regimen is one episode — and `status_as_of_precision: undated_self_report`, the only form in which an `ongoing` episode has `status_as_of: null`) |
| `missing_items.json` | `2.1` | `2` | gap `severity`; gap_type `missing_pages` with `group_key` / `pages_present` / `pages_missing` / `page_total` |
| `molecular.json` | `2.1` | `2` | `hla_typing[]` (`locus` = bare letters `A` / `DRB1`; `allele: null` only with a verbatim `zygosity`; optional `report_date` = the typing report's own date) |
| `source_inventory.json` | `source_inventory_v2.1` | `source_inventory_v2` | per-file `sha256` / `size_bytes` / `page_count` / `page_label` / `source_kind` (`prior_archive_digest` → `digest_of`, null `raw_path`) / `second_read_channel` (pinned channel categories, open OCR engine name) / `independent_reread`, `extractor_provenance.worker_id`; top-level `skipped_inputs[]`. The sidecar's 12-key header is the row's own copy: `validate_structured_outputs.py` binds FILE_ID ↔ `source_id`, READ_MODE / ADAPTER / MODALITY / PAGE_LABEL / SECOND_READ_CHANNEL / INDEPENDENT_REREAD / SHA256 / EXTRACTOR ↔ the row, and checks the key order and the rule-derived CONFIDENCE. `read_mode` `model_vision_primary` (a pixel page: the model's whole-page transcription is the body, a deterministic engine reads it a second time) and the optional `second_read_summary` `{engine, spans_total, agree, no_signal, conflict, declared}` copied from `scripts/second_read_align.py`; `independent_reread` is true when the second channel is a non-`llm_vision` category AND the engine read at least one high-risk span (an engine read is independent of the model; the model re-reading its own image is not). Enum value and optional field added without a version bump |

The schemas pin the **current** version, so a worker validating its own output must write the current shape. An archive is **current** as soon as it carries any current-contract marker — `organize_meta.json`, `readiness.json` ≥ 2.1, a structured file at its current version, an `update_log.json` entry with `workers[]`, a sidecar header naming `EXTRACTOR` (`validate_structured_outputs.py --generation` lists them); `acute_findings.json` is not a marker. In a wholly **legacy** archive, `validate_structured_outputs.py` reads a legacy version against an in-memory relaxed copy (`LEGACY_SCHEMA_VERSIONS`: version const swapped, only the later-added fields dropped from `required`; closed shapes, types and enums still apply) and reports a WARN, and the v2.1 gates (acute findings, sidecar headers, page completeness, recency, prior-archive usage, update_log …) WARN. In a **current** archive those gates FAIL, and a structured file still at a legacy version is a *mixed-version archive* ERROR validated against the strict schema — a run cannot write `"2"` to skip the v2.1 required fields, so every structured file of a run that produces a current archive is written at the current version. Sidecars an update-type run did not touch (not in any `workers[].files`, no `full` / `legacy_upgrade` run in the ledger) are reported once as carried-over (WARN) instead of being held to the new header. Bringing a legacy archive to the current contract is `run_mode: legacy_upgrade` — every original re-transcribed by Phase 1, then Phase 2; a Phase-2-only rewrite keeps the legacy version numbers (and writes no `organize_meta.json`), so it stays a legacy archive read with WARNs. `provenance_layer` gained `prior_archive` in all seven schemas that carry it (adding an enum value does not bump a version).

## Anchor token contract

Every factual field carries source reference(s) and, where defined, a provenance layer and verification/dispute status. A conversation anchor supports only a patient/caregiver-reported statement; confirmation does not make it clinician/source truth. Each anchor is a bucket-relative path or `conversation:<ISO8601>`:

```
<NN_bucket>/<…>/<file>.md[#L<start>-L<end>]
<NN_bucket>/<…>/<file>.md[#section-anchor]
conversation:<ISO8601>
```

File-anchor paths MUST begin with an `NN_` clinical-domain bucket prefix (`01_…` … `14_`, scheme_version 3) — the infrastructure vault `raw/` and quarantine `99_无关文件/` are never anchor targets, and the legacy `02_脱敏病历/` prefix is **retired**, and the transient central `ocr/` staging dir (live during a run, drained + deleted by Phase-2) is **not a valid anchor prefix** in final artifacts. Sidecars now live next to their image inside the clinical-domain bucket subdirectory. The full contract (regex included) is in [anchor-contract.md](anchor-contract.md).

In narrative artifacts (`case_text.md`, the human-readable patient summary), the same anchors appear in `[[src:...]]` syntax — see [anchor-contract.md](anchor-contract.md).

## Validation

The synthesis worker validates each JSON it writes against its schema before saving. If validation fails, the file is NOT written and the error is surfaced into `readiness.json.warnings`.

A minimal validator is shipped in `scripts/validate_structured_outputs.py` (consumes `jsonschema>=4.18`).

The validator is also an archive form gate. A final archive includes
`source_inventory.json`; every content unit points to a source-attributed sidecar and a protected original.
This structural check does not prove clinical correctness, authorization, anonymity, or minimum-necessary
sharing. Source-faithfulness and PII semantic review remain separate required gates.
