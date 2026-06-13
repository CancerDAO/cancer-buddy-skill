# Structured Output Schemas (Draft 2020-12)

These JSON Schemas define the structured outputs `cancer-buddy-organize` produces alongside `profile.json`. They are the contract that downstream consumers (vMTB, MTB-lite, trial-match, patient data export) rely on.

| File | Schema | What it carries |
|---|---|---|
| `patient_summary.json` | [patient_summary.schema.json](patient_summary.schema.json) | Demographics + diagnosis + current_status — single rollup |
| `timeline.json` | [timeline.schema.json](timeline.schema.json) | Chronological clinical events |
| `molecular.json` | [molecular.schema.json](molecular.schema.json) | NGS variants + IHC + MSI/MMR + TMB |
| `treatment_lines.json` | [treatment_lines.schema.json](treatment_lines.schema.json) | Ordered lines of therapy |
| `labs.json` | [labs.schema.json](labs.schema.json) | Lab panels with serial values |
| `comorbidities.json` | [comorbidities.schema.json](comorbidities.schema.json) | Conditions + long-term meds + allergies |
| `missing_items.json` | [missing_items.schema.json](missing_items.schema.json) | Cancer-checklist diff |
| `source_inventory.json` | [source_inventory.schema.json](source_inventory.schema.json) | Per-content-unit LLM ingestion provenance, sidecar path, and the `raw_path` deep-link back to the verbatim original in `raw/` |
| `longitudinal_observations.json` | [longitudinal_observations.schema.json](longitudinal_observations.schema.json) | Longitudinal stream store (vital/lab/symptom/pro/adherence/activity) beside profile.json — the 单时间点→纵向曲线 trajectory; see bucket-taxonomy.md §3 |

## Anchor token contract

Every factual field that originates from a text-masked MD sidecar MUST carry a `source_refs[]` array — **except `longitudinal_observations.json`, where each `observations[]` entry carries a singular `source_ref` string** (same anchor grammar, different cardinality; see `anchor-contract.md` §4). Each entry is either a bucket-relative path (file anchor) or a `conversation:<ISO8601>` reference (段C conversation anchor), with an optional fragment:

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

The validator is also the archive hard gate. A final archive must include
`source_inventory.json`; every content unit must point to a text-masked MD sidecar
and carry a `raw_path` back to its verbatim original in `raw/`. Originals in `raw/`
are kept verbatim and are never pixel-redacted — the only desensitization of the archived data is the
sidecar text masking (re-scanned by `pii_rescan.py`).
