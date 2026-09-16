#!/usr/bin/env bash
# Dimension 4 — PII desensitization is mandatory (organize + vault).
#
# Static, mostly automatable. organize is the single ingest point for raw
# records, so the text-masking contract has to be visible in its SKILL.md.
# Original integrity, PII masking, contextual minimization, and authorization are
# separate controls. No clean scan is treated as proof of anonymity.
#
# Static assertions:
#   A. organize/SKILL.md states the masked-MD-sidecar invariant: the masked MD
#      sidecar is the downstream-only read source and carries no plaintext PII;
#      masking masks PII only, never clinical characters (anti-anchoring).
#      organize v3→v4 renamed the vocabulary — 「文本脱敏 / text masking」 became
#      「masked sidecar / masking」 once raw/transcript/ became the verbatim vault
#      and the bucket copy became the derived masked one — so each assertion below
#      accepts the old and the new wording. What must not be relaxed is the CLAIM:
#      dropping any one of the three sentences is what this lint exists to catch.
#   B. source_inventory carries a protected raw_path and extraction provenance.
#   C. sharing requires authentication, scoped confirmation, minimization and
#      residual-risk language; it never promises anonymity.
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
  grep -qiE '脱敏|desensitiz|text.?mask|文本脱敏|text masking|masked sidecar|masked `?\.?md`? sidecar|masked MD' "$ORG_MD" \
    || fail "organize: no masking/desensitization language"
  grep -qiE 'no plaintext PII|无.*plaintext PII|不.*携带.*PII|downstream-only read source|下游.*读.*源|only legal full-text surface downstream|ONLY readable text surface' "$ORG_MD" \
    || fail "organize: does not state the masked MD sidecar is the no-plaintext-PII downstream read source"
  grep -qiE 'anti-anchoring|never alters clinical|never alter.*clinical|不.*改.*临床字符|masks PII only|只.*PII' "$ORG_MD" \
    || fail "organize: does not state text masking masks PII only (anti-anchoring, clinical chars intact)"
fi

# B. source inventory deep-link is protected and source extraction is auditable.
grep -q 'raw_path' "$ORG/references/schemas/source_inventory.schema.json" \
  || fail "organize: source_inventory schema missing protected raw_path"
grep -q 'extractor_provenance' "$ORG/references/schemas/source_inventory.schema.json" \
  || fail "organize: source_inventory schema missing extraction provenance"
for gone in \
  "$ORG/references/schemas/redaction_manifest.schema.json" \
  "$ORG/references/schemas/redaction_status.schema.json" \
  "$ORG/references/schemas/source_redaction_status.schema.json" \
  "$ORG/scripts/run_redaction_job.py" \
  "$ORG/references/redaction-job.md"; do
  [[ -e "$gone" ]] && fail "organize: removed source-redaction artifact re-appeared: $gone"
done

# C. vault sharing authorization, minimization, and residual-risk boundary.
[[ -f "$VAULT" ]] || fail "cancer-buddy-vault/SKILL.md not found"
if [[ -f "$VAULT" ]]; then
  grep -qiE 'de-identif|anonymiz|PII strip|strip.*PII|脱敏|去标识' "$VAULT" \
    || fail "vault: no de-identification/PII-stripping on share"
  grep -qiE 'recipient|接收方' "$VAULT" && grep -qiE 'scope|范围' "$VAULT" \
    || fail "vault: share confirmation lacks recipient/scope"
  grep -qiE '再识别|re-identif|不.*匿名|not.*anonymous' "$VAULT" \
    || fail "vault: residual re-identification risk boundary missing"
fi

summarize "pii-desensitization"
