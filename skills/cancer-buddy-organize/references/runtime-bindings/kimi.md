# Runtime binding — Kimi (personal single-machine, lite artifact profile)

Kimi CLI has subagent fan-out but tight background-task wall clocks, and a
personal machine has no deterministic post-processing platform consuming heavy
sidecar fields. This binding keeps every contract invariant while cutting the
per-page cost from ~5 LLM calls to ~1.3. It uses the **lite artifact profile**
(`organize-contract.md` §Artifact profiles) — red-line fields are all kept.

Division of labor (fixed): judgment stays in prompts (transcription,
classification, naming); verification and bookkeeping stay in scripts
(transcode, hashes, IDs, gates, coverage).

## Phase 0 — deterministic preparation (no LLM)

Run `scripts/phase0_prepare.sh <patient_dir> <input_dir>...` once, before any
model call. It transcodes HEIC/PDF to readable rasters, hashes originals into
`raw/`, and **pre-assigns every `source_id` (`SRC-<sha256 12-hex>`) in
`phase0_manifest.json`**. Workers receive IDs; they never invent them — this
removes the cross-slice ID drift observed in live runs (`s001…` vs
`SRC-<hash>` from sibling workers). Files no tool can convert get an
`[INGESTION_BLOCKED]` stub entry in the manifest, never silently skipped.

## Phase 1 — vision transcription, small slices, embedded card

- Slice size: **6–8 sources per worker** — half of the host's background-task
  timeout budget, so a slice finishes or fails fast; never size a slice so that
  a timeout-and-resume becomes the expected path (resume repays cold start).
- Worker prompt = `kimi-phase1-worker-card.md` **inlined verbatim** plus the
  slice's manifest rows. Workers read no other reference files — the card is
  self-contained. (Live run paid the full-reference cold start 7 times.)
- Each source: read the raster(s) directly with model vision and write one
  **lite sidecar** per the card. No per-field confidence tables, no pixel
  source spans — but `report_type`, verbatim transcription, uncertainty
  marks, PII masking and the manifest `source_id` are mandatory (red lines).
- Workers write sidecars incrementally (one file, one write) so a timeout
  loses at most one source; resume = re-dispatch the unwritten remainder
  listed by a deterministic `ls` diff against the manifest.

## Targeted second read (replaces blanket dual-read)

After Phase 1, run `scripts/highrisk_page_filter.py <patient_dir>` (stdlib,
deterministic). It lists sidecars containing drug names/doses, stage strings,
lab values or identifiers. Only those sources (~30–40% in practice) get one
extra vision read comparing the sidecar against the raster; mismatches become
`needs_human_review` on the affected line. Values that pass may be recorded in
`high_risk_review.json` (same format G2 consumes).

## Phase 2 — split: per-source classification, then one synthesis pass

1. **Classification/naming is per-source** (one small call per sidecar:
   sidecar text + bucket taxonomy → `{bucket_path}`; filename type segment
   must be verbatim from the sidecar's own report-type declaration). Per-source
   calls are structurally immune to the batch name-shuffle failure class.
   Run `gate_name_content.py` (G1) after moves; violations are re-filed as
   pending-classification, never persisted under a wrong name.
2. **Synthesis is one pass** over the already-bucketed tree: timeline,
   structured JSON, INDEX, summaries — cross-document work only; it renames
   nothing.

## Gates (not negotiable in any profile)

G1 after classification; G2/G3 before any reconcile card
(`scripts/gates/*.py`, stdlib — run them with the host `python3`). The lite
profile trims sidecar weight, never the gates.

## Confirmation, locale, authorization

Same as the contract: destructive actions and clinical-field changes require
explicit per-item confirmation; locale follows host → `profile.json.locale` →
record language; source clinical strings are never replaced by translation.
