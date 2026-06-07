#!/usr/bin/env bash
# Dimension 1 — Clinical entities are never translated (P0).
#
# Static, fully automatable. Two assertions:
#   A. Every patient-visible companion SKILL.md cites both the shared locale
#      contract (i18n.md) AND the verbatim-clinical safety rule
#      (safety-guardrails.md). A skill that localizes scaffold without citing
#      the verbatim policy can drift into translating drug/gene/stage strings.
#   B. No skill ships a hardcoded clinical-term translation/normalization map.
#      i18n.md §2.1/§5 are explicit: locale + entity verbatim are LLM judgment,
#      not a Python/JSON drug-name → drug-name lookup. A keyword translation
#      table IS the bug this dimension guards against.
#
# What this CANNOT prove: that a live generation actually kept "osimertinib"
# verbatim. That is a runtime-output property → tests/eval/scenarios/ +
# LLM-judge. This script only verifies the guardrail is wired into the docs.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

for skill in "${PATIENT_VISIBLE_SKILLS[@]}"; do
  f="$SKILLS_DIR/$skill/SKILL.md"
  [[ -f "$f" ]] || { fail "$skill: SKILL.md not found"; continue; }

  grep -q 'i18n\.md' "$f"             || fail "$skill: SKILL.md does not cite references/i18n.md"
  grep -q 'safety-guardrails\.md' "$f" || fail "$skill: SKILL.md does not cite references/safety-guardrails.md"

  # The verbatim-clinical promise must be stated, not merely linked.
  if ! grep -qiE 'verbatim|逐字|never translat|禁译|不翻译|不译' "$f"; then
    fail "$skill: SKILL.md does not state the verbatim / never-translate clinical-entity rule"
  fi
done

# B. No hardcoded clinical-entity translation table anywhere under skills/.
# Heuristic: a line mapping a known drug/gene to a *different-language* string,
# encoded as a code-level dict/list entry (": " or "=>" or "->" with quotes).
# The only allowed fixed map is the bucket-name table (i18n.md §6), which keys
# on NN_ prefixes and lives in references/i18n.md, not in skill code.
suspect=$(grep -rniE \
  '("|'\'')(osimertinib|奥希替尼|gefitinib|EGFR|KRAS|ALK|PD-L1)("|'\'')[[:space:]]*(:|=>|->)[[:space:]]*("|'\'')' \
  "$SKILLS_DIR" --include='*.py' --include='*.json' --include='*.js' 2>/dev/null \
  | grep -viE 'bucket|NN_|schema|0[0-9]_|1[01]_|99_' || true)
if [[ -n "$suspect" ]]; then
  while IFS= read -r line; do
    fail "hardcoded clinical-entity translation map suspected: $line"
  done <<< "$suspect"
fi

summarize "clinical-translation"
