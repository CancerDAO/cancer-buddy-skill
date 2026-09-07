# Cancer Buddy Organize Contract

This contract separates source preservation, extraction, organization, and patient-facing rendering. It
does not authorize clinical interpretation.

## Pipeline

1. **Ingest**: retain authorized originals, hash bytes, create immutable source IDs, classify modality.
2. **Extract**: deterministic OCR/parser first where available; LLM-assisted layout/semantics second;
   independent verification for high-risk fields.
3. **Synthesize**: write schema v2 with provenance layer and verification status; preserve conflicts.
4. **Confirm archive actions**: confirmation allows a patient-reported note or explicit deletion; it does
   not establish clinical truth.
5. **Faithfulness gate**: verify every patient-visible value against source spans.
6. **Render**: deterministic templates only; no treatment path, response, stage, ECOG, severity, or
   prognosis inference.
7. **Validate/export**: schema, anchors, hashes, PII, conflict preservation, and share-policy gates.

## Clinical truth invariants

- `source_reported`, `patient_reported`, `caregiver_reported`, and `system_normalized` never overwrite
  each other.
- Source strings remain available. Validated normalization and translation are additive.
- Stage, ECOG, response, treatment line, laboratory values, molecular results, and clinician plan are
  copied only from attributable sources.
- Conflicts remain `disputed`; patient confirmation cannot clear them.
- Existing-document inventories do not recommend tests.
- Longitudinal observations are not response trajectories.
- Missing/failed extraction yields null and review flags, never a plausible value.

## Graphic-dominant waveform reports

`waveform_report` is an extensible extraction type for records whose clinical source is a written report
around a waveform (for example ECG or EEG). The waveform itself is not text and this contract does not
authorize machine interpretation of it.

- A valid waveform-report sidecar declares `doc_kind: waveform_report` and
  `waveform_interpretation: not_performed`, transcribes the visible written area verbatim, and states that
  the graphical trace requires clinician/specialist interpretation.
- The text-area completeness gate replaces a text-volume heuristic for this type. A readable written area
  is usable evidence even when the page body is almost entirely grid or trace; it must not be classified
  as `insufficient_text` or `evidence_unavailable` solely for that reason.
- Only a clinician-written conclusion may flow into a timeline or comorbidity record as `source_reported`.
  Machine parameters remain verbatim source text; neither they nor the trace may be converted into a new
  diagnosis.
- The original remains referenced through the protected `raw_path` in the phase-0 manifest and
  `source_inventory.json`. It is access-controlled and never an export/anchor target.

## HEIC derived-raster lifecycle

The HEIC/HEIF requirement introduced in PR #32 is a host-facing extraction contract: Phase 0 materializes
`.staging/rasters/<source_id>/page1.jpg` (and subsequent pages when applicable) before any high-risk
second read. The raster is a protected derivative for Phase-1/Step-2 and dispute review, never a second
clinical source, export target, or `[[src:...]]` anchor. The original `raw_path` remains the durable source
reference. A missing HEIC raster for a high-risk source is a coverage failure requiring `needs_human_review`,
not a `no_raster` exemption.

## Irreversible actions

No file is deleted on silence or model confidence. Quarantine and preview first; delete only after explicit,
item-specific confirmation and append an irreversible audit event. Corrections and superseded clinical
records remain versioned with immutable anchors.

## Canonical meaning

“Canonical file” means the current storage/contract location, not that its clinical content is correct.
Clinical validity is represented separately by source, provenance layer, verification status, and dispute
state.

## Output set

The patient directory contains the source inventory, raw vault, clinical-domain sidecars, schema-v2 JSON,
timeline, neutral record summary, review flags, document gaps, update log, and deterministic HTML. All
artifacts share one patient directory; `patient_code` is a locator, not authentication.

## Artifact profiles

Sidecar weight scales with who consumes it. Two profiles exist; a host declares one and
records it in each sidecar (`profile:` header).

- **platform** (default): full sidecars — per-field confidence/review-status tables, pixel
  source spans, `pii_regions` files — consumed by deterministic platform post-processing.
- **lite** (personal/single-machine hosts, e.g. the Kimi binding): those platform-consumed
  fields are dropped; nothing else is.

**Red lines — mandatory in every profile, never trimmed:** manifest-assigned `source_id`
(IDs are deterministic bookkeeping, never model-invented), original hash + `raw/` retention,
a verbatim report-type declaration (or explicit `unknown` — never inferred), verbatim
transcription with uncertainty marks (`[unreadable]`/`[uncertain: …]`), PII masking, and
all three executable gates below. A profile trims output weight, never fidelity or gates.

## Executable gates (deterministic, host-mandatory)

Prose guarantees in this contract have failed in production when a host skipped or re-implemented them
(2026-08-05: batch naming shuffle; unverified archive values presented as fact on conflict cards). Three
invariants are therefore shipped as deterministic scripts in `scripts/gates/` — stdlib-only, zero LLM —
and every host MUST run them at the stated points. Conformance fixtures live in `tests/conformance/`
(`run_conformance.sh` must be green before deploying any host integration).

1. **Name↔content consistency (G1, `gate_name_content.py`)** — before persisting bucket files: the
   report-type segment of every bucket filename must match that sidecar's own report-type declaration
   (normalized substring or alias-group intersection, `references/report-type-aliases.json`). Violations
   must not persist under the claimed name (rename or file as pending-classification). Generic container
   declarations (`laboratory_report` etc.) are no claim → `unknown`, flagged not blocked.
2. **Candidate value–source binding (G2, `gate_candidate_binding.py`)** — before any reconcile card is
   shown: `old_value` must locate verbatim in the target sidecar AND carry no `needs_human_review` mark;
   `new_value` must locate verbatim in an independent second read of the new upload (produced separately
   from the round-1 judgment call). Failures render as "value pending verification" with the source
   image attached — never as a confident either/or choice.
3. **Same-test dedup (G3, `gate_same_test.py`)** — a conflict candidate whose accession visible-tail
   overlap (≥3 digits; redaction shapes vary, never assume fixed width) AND both sampled-at/reported-at
   timestamps match the target is the same test on two carriers: `same_test_duplicate`, no conflict card.
   A value mismatch there is an internal read discrepancy — trigger re-read, do not ask the patient.

## Host responsibilities

The host authenticates actors, enforces consent/authorization and revocation, handles concurrent writes,
encrypts storage/transport, manages retention, and prevents the skill from overriding platform safety.
Runtime bindings may differ in mechanism but must satisfy these invariants — including executing the
deterministic gates above at their stated pipeline points; skipping a gate is a contract violation.
