#!/usr/bin/env bash
# Dimension 4 — PII desensitization is mandatory (organize + vault).
#
# Static, mostly automatable. organize is the single ingest point for raw
# records, so the desensitization contract has to be visible in its SKILL.md
# and backed by the actual redaction script + schemas it hands off to.
#
# Static assertions:
#   A. organize/SKILL.md states the desensitized-MD-sidecar invariant: the MD
#      sidecar is the downstream-only read source and carries no plaintext PII;
#      redaction masks PII only, never clinical characters (anti-anchoring).
#   B. The 段B redaction hand-off is real: redaction_manifest schema + the
#      redact/job scripts exist on disk (a documented-but-missing redactor is
#      a privacy hole).
#   C. The QA-gated delete carve-out (delete pre-redaction original only on
#      qa_passed) is stated in safety-guardrails.md — irreversible deletion
#      must be gated.
#   D. vault declares PII stripping / de-identification on share.
#
# What this CANNOT prove: that a real source file was semantically fully
# redacted. That requires running prepare + LLM QA + commit on fixtures and/or
# a judge on redacted previews/payloads (scenarios/cancer-buddy-organize.md).
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

ORG="$SKILLS_DIR/cancer-buddy-organize"
ORG_MD="$ORG/SKILL.md"
SG="$REFS_DIR/safety-guardrails.md"
VAULT="$SKILLS_DIR/cancer-buddy-vault/SKILL.md"

# A. desensitized sidecar invariant + anti-anchoring.
[[ -f "$ORG_MD" ]] || fail "cancer-buddy-organize/SKILL.md not found"
if [[ -f "$ORG_MD" ]]; then
  grep -qiE '脱敏|desensitiz|redact' "$ORG_MD" \
    || fail "organize: no desensitization/redaction language"
  grep -qiE 'no plaintext PII|无.*plaintext PII|不.*携带.*PII|downstream-only read source|下游.*读.*源' "$ORG_MD" \
    || fail "organize: does not state MD sidecar is the no-plaintext-PII downstream read source"
  grep -qiE 'anti-anchoring|never alters clinical|never alter.*clinical|不.*改.*临床字符|masks PII only|只.*PII' "$ORG_MD" \
    || fail "organize: does not state redaction masks PII only (anti-anchoring, clinical chars intact)"
fi

# B. redaction hand-off is backed by real artifacts and v2 schemas.
[[ -f "$ORG/references/schemas/redaction_manifest.schema.json" ]] \
  || fail "organize: redaction_manifest.schema.json missing (hand-off contract)"
[[ -f "$ORG/scripts/run_redaction_job.py" ]] \
  || fail "organize: scripts/run_redaction_job.py missing (batch redaction job)"
grep -q 'redaction_manifest_v2' "$ORG/references/schemas/redaction_manifest.schema.json" \
  || fail "organize: redaction_manifest schema is not v2"
grep -q 'redaction_status_v2' "$ORG/references/schemas/redaction_status.schema.json" \
  || fail "organize: redaction_status schema is not v2"
grep -q 'llm_region_image' "$ORG/references/schemas/source_inventory.schema.json" \
  || fail "organize: source_inventory schema missing llm_region strategies"
grep -q 'coverage_passed' "$ORG/references/schemas/source_redaction_status.schema.json" \
  || fail "organize: source_redaction_status schema missing v2 coverage gate fields"

# B2. old OCR redactor dependency must not re-enter active organize docs/scripts/tests.
old_redactor_pattern='Paddle''OCR|paddle''ocr|redact_''ocr|mtb-''ocr|OCR ''venv|paddle''ocr_''image'
grep -RInE "$old_redactor_pattern" \
  "$ORG" "$REPO_ROOT/tests/eval" >/tmp/cb-old-redactor-refs.raw.$$ || true
grep -vF "$0" /tmp/cb-old-redactor-refs.raw.$$ >/tmp/cb-old-redactor-refs.$$ || true
rm -f /tmp/cb-old-redactor-refs.raw.$$
if [[ -s /tmp/cb-old-redactor-refs.$$ ]]; then
  cat /tmp/cb-old-redactor-refs.$$ >&2
  rm -f /tmp/cb-old-redactor-refs.$$
  fail "organize: old OCR redactor dependency/reference present"
else
  rm -f /tmp/cb-old-redactor-refs.$$
fi

# C. QA-gated irreversible-delete carve-out in shared guardrails.
[[ -f "$SG" ]] || fail "safety-guardrails.md not found"
if [[ -f "$SG" ]]; then
  grep -qiE 'coverage_passed|llm_qa_passed|QA gate|QA 门' "$SG" \
    || fail "safety-guardrails.md: QA-gated redaction-then-delete carve-out absent"
fi

# D. vault de-identification on share.
[[ -f "$VAULT" ]] || fail "cancer-buddy-vault/SKILL.md not found"
if [[ -f "$VAULT" ]]; then
  grep -qiE 'de-identif|anonymiz|PII strip|strip.*PII|脱敏|去标识' "$VAULT" \
    || fail "vault: no de-identification/PII-stripping on share"
fi

summarize "pii-desensitization"
