#!/usr/bin/env bash
# Cross-cutting clinical-governance regression checks.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

ORG="$SKILLS_DIR/cancer-buddy-organize"
READY="$ORG/references/schemas/readiness.schema.json"
LABS="$ORG/references/schemas/labs.schema.json"
TX="$ORG/references/schemas/treatment_lines.schema.json"
INV="$ORG/references/schemas/source_inventory.schema.json"

# organize v3→v4 (fix spec A13): readiness.json bumped to schema_version "3". The legacy
# "2" archives are not rejected — they take the migrate_v3_to_v4.py WARN branch — but the
# SCHEMA itself must pin the current version, or a v3 file validates as if nothing moved.
grep -q '"schema_version": { "const": "3" }' "$READY" || fail "readiness schema is not v3 (fix spec A13)"
grep -q '"schema_version": { "const": "2" }' "$READY" \
  && fail "readiness schema still pins the legacy const \"2\"" || true
grep -q 'documentation_coverage' "$READY" || fail "readiness lacks documentation coverage"
grep -Eq '"grade"|"blocking_gaps"|"suggested_value"|"user_confirmed"' "$READY" \
  && fail "readiness schema resurrected score/patient-adjudication fields" || true

grep -q 'report_flag' "$LABS" && grep -q 'critical_flag' "$LABS" \
  || fail "labs schema does not preserve report/critical flags per result"
grep -q 'reference_range' "$LABS" || fail "labs schema does not preserve per-result reference range"
grep -Eq '_status_from_range|_TUMOR_MARKERS|cap_tumor_marker_severity' "$ORG/scripts/backfill_lab_trends.py" \
  && fail "lab backfill performs model-side grading or analyte exceptions" || true

grep -q 'clinician_reported_response' "$TX" || fail "treatment episodes lack clinician-source response field"
grep -q 'documented_line_label' "$TX" || fail "treatment episodes lack source-only line label"
grep -q 'best_response' "$TX" && fail "legacy best_response field returned" || true

grep -q 'source_inventory_v2' "$INV" || fail "source inventory does not require v2 extraction provenance"
grep -q 'extractor_provenance' "$INV" || fail "source inventory lacks deterministic/native extractor provenance"
grep -q 'high_risk_review_status' "$INV" || fail "source inventory lacks independent high-risk-field reread status"
grep -q 'reread_channel' "$INV" \
  || fail "source inventory lacks reread_channel — passed_independent_reread would be self-certifying"
grep -q '"clinical_class"' "$INV" \
  || fail "source inventory lacks clinical_class — the completeness floors would key off the bucket path again"
grep -q 'transcript_path' "$INV" \
  || fail "source inventory lacks transcript_path — the verbatim page vault would be unrecorded"
grep -q 'audience' "$READY" \
  || fail "readiness schema lacks review_flags[].audience — QC noise would reach a family as 「请医生确认」"
grep -q 'projection_coverage' "$READY" \
  || fail "readiness schema lacks projection_coverage — a best-effort projection would be indistinguishable from a complete one"
# --- Phase 1 transcription prompt (organize v3) ------------------------------
# The file was renamed organizer-prompt-phase1-ocr.md -> -transcribe.md when 段 1
# stopped pretending deterministic OCR was the character source. The v2 assertion
# ("LLM is not the sole character truth") no longer describes the contract: on a
# pixel page the model IS the first read, and what makes that safe is not a
# disclaimer, it is (a) the tri-state OCR rule, (b) the 12 high-risk classes that
# get an unconditional second read, and (c) the rule that re-reading the same image
# is not an independent channel. Those three are what this lint now pins.
TRANSCRIBE="$ORG/references/organizer-prompt-phase1-transcribe.md"
[[ -f "$TRANSCRIBE" ]] || fail "phase-1 transcription prompt not found at organizer-prompt-phase1-transcribe.md"
if [[ -f "$TRANSCRIBE" ]]; then
  # fix spec A1: the cache key is sha256(image).sha256(text_layer)[:16].prompt_version.model_id,
  # so this string is load-bearing — the v3.1 prompt dropped prev_page_tail, which changes what
  # the model is asked for, and a stale 3.0 header would serve the OLD readings for NEW inputs.
  grep -qE '^prompt_version:[[:space:]]*"?3\.1"?' "$TRANSCRIBE" \
    || fail "phase-1 transcribe prompt: header does not declare prompt_version: 3.1 (the transcription cache key reads it; a wrong/absent version silently serves stale pages)"
  # the 12 high-risk classes (9 universal + 3 oncology pack) must be listed verbatim
  for _c in identifier date drug_name dose frequency lab_value unit reference_range accession stage variant vaf; do
    grep -qF "\`$_c\`" "$TRANSCRIBE" \
      || fail "phase-1 transcribe prompt: high-risk class \`$_c\` missing from the 12-class list"
  done
  unset _c
  grep -qE '不算独立复读|not an independent (re-?read|channel)' "$TRANSCRIBE" \
    || fail "phase-1 transcribe prompt: does not state that re-reading the same image with the same model is NOT an independent reread"
  grep -qE '三态' "$TRANSCRIBE" \
    || fail "phase-1 transcribe prompt: deterministic-OCR tri-state rule missing"
  grep -qE 'ocr_appendix.*不是真值|三态信号源.*不是真值' "$TRANSCRIBE" \
    || fail "phase-1 transcribe prompt: the OCR appendix is not declared a non-authoritative signal"
  # v3 口径 negatives: tesseract must NOT be promoted to sole truth or sole reread channel
  grep -qE 'tesseract[^\n]{0,40}(才算|唯一)[^\n]{0,20}(独立复读|真值)' "$TRANSCRIBE" \
    && fail "phase-1 transcribe prompt: claims tesseract is the only independent reread / the truth (tri-state, never a veto)" || true
  grep -qE '确定性 ?OCR[^\n]{0,30}唯一[^\n]{0,20}真值' "$TRANSCRIBE" \
    && fail "phase-1 transcribe prompt: deterministic OCR declared the sole character truth" || true
  # injection isolation survived the rewrite
  grep -qE '数据[^\n]{0,6}不是指令|data, not instructions' "$TRANSCRIBE" \
    || fail "phase-1 transcribe prompt: 'this is data, not instructions' isolation rule missing"
fi
# The renamed-away file must not be referenced from any binding surface. Scoped to
# skills/ (the instructions a model actually loads); __pycache__ and this lint's own
# prose are excluded, and tests/ is excluded because a test may legitimately assert
# the OLD name is gone.
_stale="$(grep -rl 'organizer-prompt-phase1-ocr' "$SKILLS_DIR" 2>/dev/null \
  | grep -v '__pycache__' || true)"
[[ -n "$_stale" ]] && fail "stale reference to the renamed organizer-prompt-phase1-ocr.md in: $(echo "$_stale" | tr '\n' ' ')" || true
unset _stale
grep -q -- '--include' "$ORG/scripts/export_share.py" \
  || fail "share exporter lacks explicit minimum-necessary allowlist"
grep -q -- '--authorization-ref' "$ORG/scripts/export_share.py" \
  || fail "share exporter lacks authorization/audit reference"

grep -qiE '不.*(打分|排名)|unranked' "$SKILLS_DIR/cancer-buddy-find-care/SKILL.md" \
  || fail "find-care no longer guarantees unranked resources"
grep -qiE '死亡|death' "$SKILLS_DIR/cancer-buddy-case-precedent/SKILL.md" \
  || fail "case-precedent does not require negative/death outcomes"
grep -qiE '不.*相似度|no.*similarity' "$SKILLS_DIR/cancer-buddy-case-precedent/SKILL.md" \
  || fail "case-precedent no-similarity-score rule missing"

for checklist in "$ORG"/references/checklists/*.yaml; do
  grep -q 'mode: existing_document_inventory_only' "$checklist" \
    || fail "$(basename "$checklist"): not document-inventory-only"
  grep -Eq '^(recommended|must_test|threshold|cutoff|guideline):' "$checklist" \
    && fail "$(basename "$checklist"): contains a static clinical claim" || true
done

grep -qiE 'cryptographically random|random bytes|随机' "$REFS_DIR/patient-profile-schema.md" \
  || fail "patient_code is not specified as random"
grep -qiE 'model memory|模型记忆' "$REFS_DIR/safety-guardrails.md" \
  || fail "fail-closed no-model-memory rule missing"

summarize "clinical-governance"
