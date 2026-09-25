# Runtime binding — headless Codex

This binding implements the same source-fidelity and authorization contract in a
single-process or platform-worker environment.

## Pipeline

For each uploaded source:

1. Create a stable `source_id`, hash the file, and store its bytes under an
   access-controlled, de-identified `raw/` filename. The organizer does not
   silently overwrite, transform, or delete it. Host retention policy controls
   later deletion or legal hold.
2. Prefer the file's native text/table layer when available. For scans, run an
   appropriate deterministic OCR/table/barcode extractor. Save engine, version,
   language, raw output, source spans, and adapter provenance.
3. Use Codex for layout reconstruction, candidate corrections, semantic labels,
   and PII semantic review. Preserve `raw_text` separately from any
   `proposed_text`; an LLM correction never overwrites the character source.
4. Reread dates, drug names, dose/frequency, laboratory values/units/reference
   intervals, stage strings, IHC markers, lymph-node stations, variants/VAF and
   institution names through a second channel. `codex exec -i` is an `llm_vision`
   read: it may serve as the second read, but the sidecar records
   `INDEPENDENT_REREAD: false`. Only a different channel class that is not
   `llm_vision` (native text layer vs. OCR, deterministic channel vs. human)
   counts as independent. Disagreement becomes an `[OCR_UNCERTAIN:U-nnn]` token
   plus a `## 不确定字段` entry with every channel's reading and lexicon-only
   candidates.
5. Write a source-attributed sidecar with the 12-key header of
   `organizer-prompt-phase1-ocr.md` §3. `EXTRACTOR` is the per-source call id
   (e.g. `p1-<source_id>-1`), never the engine name and never the host pipeline.
   Unreadable content is never guessed.

All sidecars must be complete before Phase 2 synthesis begins. Unsupported or
corrupt files receive an `[INGESTION_BLOCKED: <reason>]` stub rather than being
skipped.

**Liveness.** Each per-source call has a 10-minute budget without a new sidecar
write. A call that exceeds it, or returns `timed_out: true` with an
`in_progress_timeout_risk` stub, is killed and retried once as a fresh call with a
new id; if the retry also times out, a separate stub call writes
`[INGESTION_BLOCKED: timeout]` for that source and the run stops and reports.
The Phase 2 call gets one retry under the same rule and otherwise stops and
reports. Every attempt is recorded in the `dispatch_log` handed to Phase 2 and
lands in `update_log.json` (`workers[]`, `degradations[]`). The host pipeline
never writes a sidecar or a structured JSON file itself.

## Locale and source language

The host forwards the current BCP-47 product locale when known. Locale controls
scaffold and explanations, not the source layer. Source clinical strings remain
unchanged; translation or normalization is an additive labeled field.

## Confirmation and truth layers

Before the run starts, the host adds one confirm-as-product item: “是否已有比本次
更新的资料（最近的影像、化验或门诊记录）？” It does not block the run; a later
answer that supplies newer records triggers an incremental run diffed by sha256.

Headless confirmation is a product artifact:

1. Produce a diff with source/provenance and requested action.
2. The authenticated user confirms the administrative action in the UI.
3. Apply only the confirmed scoped change and append an audit event.

Patient confirmation can confirm what the patient reported; it cannot promote a
statement to `clinician_verified`, choose between conflicting clinician sources,
or create stage, ECOG, response, progression, or treatment-line truth. Silence
never authorizes deletion.

## Outputs and privacy gates

Phase 2 produces the canonical archive, source inventory, source-preserving JSON,
timeline, review flags, and derived HTML. PII review uses both an independent
semantic scan and deterministic shape checks. Failure or unavailability of either
layer blocks sharing.

`validate_structured_outputs.py` (run after `write_organize_meta.py`; any check that
is not the run's own terminal gate adds `--readonly`) checks schemas, anchors,
source-shape integrity, sidecar headers, inventory completeness, PII shapes, and HTML form. It does not decide whether a
clinical value is normal, severe, meaningful, or treatment-relevant. Phase 2.5
separately verifies that structured values can be reproduced from their sources.

The deterministic HTML path remains (`<skill_dir>` = the absolute path of `skills/cancer-buddy-organize`, the same value every worker receives):

```bash
python3 "<skill_dir>/scripts/stamp_case_summary_sources.py" <patient_dir>   # acute_findings_sha256 (段D step 3)
python3 "<skill_dir>/scripts/render_html_template.py" \
  --template "<skill_dir>/references/templates/case-summary.template.html" \
  --data <patient_dir>/.case_summary_data.json \
  --out <patient_dir>/病情简要总结.html

python3 "<skill_dir>/scripts/validate_case_summary_html.py" \
  --html <patient_dir>/病情简要总结.html \
  --template "<skill_dir>/references/templates/case-summary.template.html"
```

Any share action additionally requires host authentication, explicit confirmation
of recipient/scope/purpose/expiry, data minimization, residual-risk disclosure,
and an export that excludes `raw/`. A generated patient code or role file is not
authorization.
