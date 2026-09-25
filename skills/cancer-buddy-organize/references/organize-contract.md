# Cancer Buddy Organize Contract

This contract separates source preservation, extraction, organization, and patient-facing rendering. It
does not authorize clinical interpretation.

## Pipeline

1. **Ingest**: retain authorized originals, hash bytes (sha256, size, page count), create immutable source
   IDs, classify modality, and record every skipped input with a reason.
2. **Extract**: deterministic OCR/parser first where available; LLM-assisted layout/semantics second;
   independent verification for high-risk fields. Two reads are independent only when their channel
   classes differ and neither is `llm_vision` (a model looking at the image is never an independent
   reread). Uncertain fields carry engine readings and lexicon-constrained candidates; candidates are
   readings, never corrected values.
3. **Synthesize**: write the versioned schemas (`references/schemas/`: `2.1`, `patient_summary` `2.2`,
   `source_inventory_v2.1`, `acute_findings`/`update_log` `1`) with provenance layer and verification status;
   preserve conflicts.
4. **Confirm archive actions**: confirmation allows a patient-reported note or explicit deletion; it does
   not establish clinical truth.
5. **Faithfulness gate**: verify every patient-visible value against source spans.
6. **Render**: deterministic templates only; no treatment path, response, stage, ECOG, severity, or
   prognosis inference. The `severity` on a review flag grades extraction/archive-completeness
   uncertainty, not clinical severity; the `acuity` of an acute finding is a fixed class table applied to
   source wording, not triage. A new or changed emergent/urgent finding makes the summary re-render
   mandatory (never a question; non-interactive hosts and legacy archives too); until it happens a pinned
   stale notice stands in `review_summary.md` and `readiness.json.warnings[]`.
7. **Validate/export**: schema, anchors, hashes, PII, conflict preservation, and share-policy gates.

## Clinical truth invariants

- `source_reported`, `patient_reported`, `caregiver_reported`, `system_normalized`, and `prior_archive`
  never overwrite each other. `prior_archive` (an explicitly authorized digest of an earlier organized
  archive) supports history only, never current status or recommendations.
- Source strings remain available. Validated normalization and translation are additive; a quote that is a
  translation of a foreign-language report (`verbatim_is_translation`) is labelled as one wherever it is shown.
- Stage, ECOG, response, treatment line, laboratory values, molecular results, and clinician plan are
  copied only from attributable sources.
- Conflicts remain `disputed`; patient confirmation cannot clear them.
- Existing-document inventories do not recommend tests.
- Longitudinal observations are not response trajectories.
- Missing/failed extraction yields null and review flags, never a plausible value.
- Unconfirmed `document_intent` fields and `[OCR_UNCERTAIN:U-nnn]` fields are not premises for staging,
  pathology, or treatment reasoning.
- Writers are an allow-list (SKILL.md invariant 3). Phase 1 workers write sidecars and their own `raw/`
  files; Phase 2 and 段C workers write the structured JSON and `INDEX.md` / `case_text.md` / `timeline.md` /
  `review_*.md` (under `raw/` Phase 2 writes only `_SIDECAR_MAP.md` and moves legacy outputs into
  `_legacy_<ts>/`; a script's intermediate text is piped, never saved there), and 段C workers also write the conversation records `<bucket>/conversation_notes/*.md`; the 段D worker writes `.case_summary_data.json` and the HTML. The orchestrator dispatches,
  monitors liveness and redispatches, and writes under the patient directory only through fixed actions:
  `inventory_hash.py --mapping-out`, the `library/index.json` seed, appending dispatch events to
  `raw/_dispatch_log.jsonl`, `record_gap_ask.py`, `fill_agents_md.py`, `write_organize_meta.py`, the terminal
  `validate_structured_outputs.py` (it merges untrusted-content flags), the dated 段D snapshot copy and the
  Step 17 clean-up (stray `.DS_Store`, an empty `ocr/`, and an archive's temp `unpack_dir` — never `$src`, `raw/` or
  the user's input folder). Nothing else, however small.
- Bucket paths are checked against the pinned taxonomy before any directory is created.

## Irreversible actions

No file is deleted on silence or model confidence. Quarantine and preview first; delete only after explicit,
item-specific confirmation and append an irreversible audit event. Corrections and superseded clinical
records remain versioned with immutable anchors.

## Canonical meaning

“Canonical file” means the current storage/contract location, not that its clinical content is correct.
Clinical validity is represented separately by source, provenance layer, verification status, and dispute
state.

## Output set

The patient directory contains the source inventory, raw vault, clinical-domain sidecars, schema-versioned JSON
(including `acute_findings.json`, always written), timeline, neutral record summary, review flags, document
gaps (including missing pages), update log with worker and degradation records, `organize_meta.json`, and
deterministic HTML. All
artifacts share one patient directory; `patient_code` is a locator, not authentication.

## Host responsibilities

The host authenticates actors, enforces consent/authorization and revocation, handles concurrent writes,
encrypts storage/transport, manages retention, and prevents the skill from overriding platform safety.
Runtime bindings may differ in mechanism but must satisfy these invariants.
