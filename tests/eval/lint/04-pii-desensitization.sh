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
# What this CANNOT prove: that a real image was actually pixel-redacted with
# zero residual PII. That requires running redact_ocr.py on fixtures (an
# integration test with the OCR venv) and/or LLM-judge on a sidecar sample
# (scenarios/cancer-buddy-organize.md).
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

# B. redaction hand-off is backed by real artifacts.
[[ -f "$ORG/references/schemas/redaction_manifest.schema.json" ]] \
  || fail "organize: redaction_manifest.schema.json missing (hand-off contract)"
[[ -f "$ORG/scripts/redact_ocr.py" ]] \
  || fail "organize: scripts/redact_ocr.py missing (PaddleOCR pixel-redactor)"
[[ -f "$ORG/scripts/run_redaction_job.py" ]] \
  || fail "organize: scripts/run_redaction_job.py missing (batch redaction job)"

# C. QA-gated irreversible-delete carve-out in shared guardrails.
[[ -f "$SG" ]] || fail "safety-guardrails.md not found"
if [[ -f "$SG" ]]; then
  grep -qiE 'qa_passed|QA gate|QA 门' "$SG" \
    || fail "safety-guardrails.md: QA-gated redaction-then-delete carve-out absent"
fi

# D. vault de-identification on share.
[[ -f "$VAULT" ]] || fail "cancer-buddy-vault/SKILL.md not found"
if [[ -f "$VAULT" ]]; then
  grep -qiE 'de-identif|anonymiz|PII strip|strip.*PII|脱敏|去标识' "$VAULT" \
    || fail "vault: no de-identification/PII-stripping on share"
fi

summarize "pii-desensitization"
