#!/usr/bin/env bash
# Dimension 4 — PII desensitization is mandatory (organize + vault).
#
# Static, mostly automatable. organize is the single ingest point for raw
# records, so the text-masking contract has to be visible in its SKILL.md.
# Uploaded originals are kept verbatim in raw/ (never pixel-redacted, never
# deleted); the only desensitization is the sidecar TEXT masking — that is what
# this dimension guards.
#
# Static assertions:
#   A. organize/SKILL.md states the text-masked-MD-sidecar invariant: the MD
#      sidecar is the downstream-only read source and carries no plaintext PII;
#      text masking masks PII only, never clinical characters (anti-anchoring).
#   B. source_inventory schema carries the raw_path deep-link to the verbatim
#      original in raw/, and the image/source-redaction status subsystem
#      (redaction_manifest / source_redaction_status / run_redaction_job) does
#      NOT re-enter the skill (originals are never pixel-redacted).
#   C. vault declares PII stripping / de-identification on share.
#
# What this CANNOT prove: that a sidecar was semantically fully masked. That
# requires a residue rescan on fixtures and/or an LLM judge
# (scenarios/cancer-buddy-organize.md). pii_rescan.py is the deterministic
# residue gate on the text sidecars.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

ORG="$SKILLS_DIR/cancer-buddy-organize"
ORG_MD="$ORG/SKILL.md"
VAULT="$SKILLS_DIR/cancer-buddy-vault/SKILL.md"

# A. text-masked sidecar invariant + anti-anchoring (no plaintext PII in the sidecar).
[[ -f "$ORG_MD" ]] || fail "cancer-buddy-organize/SKILL.md not found"
if [[ -f "$ORG_MD" ]]; then
  grep -qiE '脱敏|desensitiz|text.?mask|文本脱敏|text masking' "$ORG_MD" \
    || fail "organize: no text-masking/desensitization language"
  grep -qiE 'no plaintext PII|无.*plaintext PII|不.*携带.*PII|downstream-only read source|下游.*读.*源' "$ORG_MD" \
    || fail "organize: does not state MD sidecar is the no-plaintext-PII downstream read source"
  grep -qiE 'anti-anchoring|never alters clinical|never alter.*clinical|不.*改.*临床字符|masks PII only|只.*PII' "$ORG_MD" \
    || fail "organize: does not state text masking masks PII only (anti-anchoring, clinical chars intact)"
fi

# B. source_inventory deep-links to the verbatim raw/ original; the source-redaction
#    subsystem must NOT re-enter the skill (originals are kept verbatim, never pixel-redacted).
grep -q 'raw_path' "$ORG/references/schemas/source_inventory.schema.json" \
  || fail "organize: source_inventory schema missing raw_path deep-link to the verbatim original"
for gone in \
  "$ORG/references/schemas/redaction_manifest.schema.json" \
  "$ORG/references/schemas/redaction_status.schema.json" \
  "$ORG/references/schemas/source_redaction_status.schema.json" \
  "$ORG/scripts/run_redaction_job.py" \
  "$ORG/references/redaction-job.md"; do
  [[ -e "$gone" ]] && fail "organize: removed source-redaction artifact re-appeared: $gone"
done

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

# C. vault de-identification on share.
[[ -f "$VAULT" ]] || fail "cancer-buddy-vault/SKILL.md not found"
if [[ -f "$VAULT" ]]; then
  grep -qiE 'de-identif|anonymiz|PII strip|strip.*PII|脱敏|去标识' "$VAULT" \
    || fail "vault: no de-identification/PII-stripping on share"
fi

summarize "pii-desensitization"
