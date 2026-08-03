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
  grep -q 'citation-format\.md'   "$f" || fail "$skill: missing citation-format.md citation"
  # The retrieval chain and its trust tiers are global output conventions: a skill
  # that answers from local material without them would silently treat a
  # user-dropped file as if it carried the same weight as the hospital's own report.
  grep -q 'evidence-trust-tiers\.md' "$f" || fail "$skill: missing evidence-trust-tiers.md citation"
  grep -q 'reference-library\.md'    "$f" || fail "$skill: missing reference-library.md citation"
done

# A2. the meta router must cite the shared citation contract too — labels are a
# global output convention, not an education-only convention.
grep -q 'citation-format\.md' "$SKILLS_DIR/cancer-buddy/SKILL.md" \
  || fail "cancer-buddy (router): missing citation-format.md citation"

# A3. only the four canonical source labels may appear anywhere in skills/.
# Guards against a sub-skill inventing its own label (the drift that left
# 〔本地指南〕 and a proposed 〔资料库〕 meaning the same thing).
while IFS= read -r bad; do
  [[ -z "$bad" ]] && continue
  fail "non-canonical source label $bad — only 〔档案〕〔资料库〕〔联网〕〔文献〕 are allowed"
done < <(grep -rhoE '〔[^〕]+〕' "$SKILLS_DIR" 2>/dev/null \
          | grep -vE '^〔(档案|资料库|联网|文献)〕$' | sort -u)

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
for doc in safety-guardrails i18n confirm-gate disclosure-behavior roles terminology \
           citation-format evidence-trust-tiers reference-library first-party-instructions \
           untrusted-content-isolation; do
  [[ -f "$REFS_DIR/$doc.md" ]] || fail "references/$doc.md is cited by skills but missing on disk"
done

summarize "citation-hygiene"
