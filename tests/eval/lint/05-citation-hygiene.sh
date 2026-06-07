#!/usr/bin/env bash
# Cross-cutting — reference citation hygiene.
#
# Static, fully automatable. A safety rule only binds a sub-skill if that
# sub-skill actually cites it. This script enforces the citation graph the
# four dimensions above assume:
#   A. Every patient-visible companion SKILL.md cites safety-guardrails.md +
#      i18n.md (the two always-on shared contracts). [overlaps 01 by design —
#      this is the dimension-agnostic floor; keeping it here means the floor
#      holds even if 01's verbatim-specific check is later relaxed.]
#   B. Skills that persist patient data through a confirm/diff gate cite the
#      shared confirm-gate.md (no skill may invent its own irreversible-write
#      door — see relevance-gate.md / upload-reconciliation.md "fix it at the
#      shared gate"). Applicable set = skills that write profile/timeline
#      fields from un-vetted input: organize.
#   C. All referenced shared docs actually exist on disk (no dangling cite).
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

# A. floor: guardrails + i18n cited by every patient-visible skill.
for skill in "${PATIENT_VISIBLE_SKILLS[@]}"; do
  f="$SKILLS_DIR/$skill/SKILL.md"
  [[ -f "$f" ]] || { fail "$skill: SKILL.md not found"; continue; }
  grep -q 'safety-guardrails\.md' "$f" || fail "$skill: missing safety-guardrails.md citation"
  grep -q 'i18n\.md'              "$f" || fail "$skill: missing i18n.md citation"
done

# B. confirm-gate cited by the data-writing skill.
CONFIRM_GATE_SKILLS=( cancer-buddy-organize )
for skill in "${CONFIRM_GATE_SKILLS[@]}"; do
  f="$SKILLS_DIR/$skill/SKILL.md"
  [[ -f "$f" ]] || { fail "$skill: SKILL.md not found"; continue; }
  if ! grep -qiE 'confirm-gate|先确认|diff.?card|diff 卡' "$f"; then
    fail "$skill: writes patient data but does not cite the shared confirm-gate"
  fi
done

# C. no dangling shared-doc references.
for doc in safety-guardrails i18n confirm-gate disclosure-behavior roles terminology; do
  [[ -f "$REFS_DIR/$doc.md" ]] || fail "references/$doc.md is cited by skills but missing on disk"
done

summarize "citation-hygiene"
