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

grep -q '"schema_version": { "const": "2" }' "$READY" || fail "readiness schema is not v2"
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
grep -qiE '不是.*唯一字符真值|不得.*唯一字符真值|not.*sole character' "$ORG/references/organizer-prompt-phase1-ocr.md" \
  || fail "Phase 1 does not prohibit LLM-only character truth"
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
