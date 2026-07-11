# Owner-reviewed text fast path (段C)

This is a fast branch of `run_mode: conversation_incremental`, not a separate organize mode. Use it only when the health-vault owner has reviewed the exact short text and explicitly approved writing it.

## Inputs

- `patient_dir`: existing canonical patient directory
- `conversation_turn`: approved UTF-8 text, 1–20,000 characters
- `turn_timestamp`: ISO-8601 timestamp used by the existing `conversation:<timestamp>` anchor
- `actor_role`: `patient` or `caregiver`
- `owner_reviewed: true`
- `source_label`: optional contributor/link label

Reject a missing patient directory or empty text. Never fall back to file ingestion, full organize, or upload reconciliation.

## Privacy and execution

1. Apply the same local, open-ended PII masking and two-layer rescan required by `conversation-incremental-prompt.md` Step 4a. Raw text must not be sent to a cloud model or written to a downstream-readable surface.
2. Make at most one semantic call, using only the PII-masked text plus the minimum existing structured context needed to classify it.
3. Authentication failures (`invalid refresh_token`, HTTP 401/403, login required) fail immediately with no retry. Rate limits return to the caller; do not sleep or retry internally.
4. A parse, validation, or PII-gate failure writes nothing and returns the submission to the caller as pending.

## Writes

- Archive the masked note under the matching locale-aware clinical domain, using the existing stable `NN_` routing rules. Routine home vitals, symptom diaries, PROs, adherence, and activity normally belong to `10_` follow-up/monitoring; undirected diary context falls back to `14_` patient supplement. This remains LLM domain judgment, never a keyword table.
- Tag the note `patient_curated`, `confidence: low`, and `owner_reviewed: true`; cite `[[src:conversation:<turn_timestamp>]]`.
- Append explicit dated vital/symptom/PRO/adherence/activity points to `longitudinal_observations.json` using its existing schema. Never infer a missing date, unit, value, diagnosis, or cause.
- Append one `update_log.json` entry with `run_mode: conversation_incremental`, `fast_path: owner_reviewed_text`, source label, anchor, and changed paths.
- Do not overwrite record-sourced facts. Do not rewrite profile, timeline, or other structured files unless this exact confirmed observation has an existing schema-defined append target.

Do **not** run OCR, rasterization, file classification, Phase 1, Phase 2 full synthesis, readiness regeneration, upload reconciliation, whole-vault reconciliation, or case-summary generation.

## Result

Return pure JSON:

```json
{
  "role": "conversation_incremental_worker",
  "fast_path": "owner_reviewed_text",
  "ok": true,
  "conversation_anchor": "conversation:2026-07-11T10:00:00Z",
  "observations_written": 1,
  "changed_paths": ["10_followup_monitoring/conversation_notes/2026-07-11.md", "longitudinal_observations.json", "update_log.json"]
}
```

Paths are locale-aware examples, not hard-coded names.
