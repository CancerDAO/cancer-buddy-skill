#!/usr/bin/env bash
# For every sub-skill affected by disclosure (per references/disclosure-behavior.md),
# assert its SKILL.md (1) declares a disclosure behavior AND (2) that declaration is
# consistent with the disclosure-behavior.md matrix cell (not merely "the word
# Disclosure appears somewhere"). This is what disclosure-behavior.md §"When the
# matrix updates" promises the guard enforces.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
errs=0

# Companion-scope skills affected by disclosure (disclosure-behavior.md Matrix).
# Excluded: caregiver (N/A — patient never routes here); meta cancer-buddy (routing-only).
# Clinical skills live in cancer-buddy-pro-skill (private).
affected=(
  organize
  vault
  education
  mind
  nutrition
  second-opinion
  disclosure
  find-care
  visit-prep
)

# Behavior keyword(s) each skill's disclosure declaration MUST contain, matching its
# disclosure-behavior.md matrix cell. Keeps the guard consistent with the authority
# table, so a regression that silently flips a cell's behavior is caught.
# IMPORTANT: a keyword must be unique to the BEHAVIOR, never a substring of the trigger
# condition `disclosure_state=suppressed` (which every cell contains) or other scaffolding
# — otherwise the assertion is an always-pass. (organize uses `warn`, NOT `suppress`.)
behavior_re() {
  case "$1" in
    organize)        echo 'warn' ;;                        # warn entering breaks suppression
    vault)           echo 'redact|mask' ;;                 # redacted/masked view
    education)       echo 'refuse' ;;                       # refuse patient handbook
    mind)            echo 'continue' ;;                     # continue screening, generic framing
    nutrition)       echo 'cancer-type|abstract|normal' ;; # cancer-type not surfaced
    second-opinion)  echo 'refuse' ;;                       # refuse operator-only
    disclosure)      echo 'disclosure' ;;                   # main workflow (this IS the skill)
    find-care)       echo '晚期|进展后' ;;                  # avoid late-stage wording
    visit-prep)      echo '晚期|进展后' ;;                  # avoid late-stage wording
    *)               echo 'disclosure' ;;
  esac
}

for skill in "${affected[@]}"; do
  f="$REPO_ROOT/skills/cancer-buddy-$skill/SKILL.md"
  if [[ ! -f "$f" ]]; then
    echo "FAIL: cancer-buddy-$skill SKILL.md not found" >&2
    errs=$((errs+1))
    continue
  fi
  # 1) declares a disclosure behavior at all
  if ! grep -qi 'disclosure' "$f"; then
    echo "FAIL: cancer-buddy-$skill missing Disclosure declaration in SKILL.md" >&2
    errs=$((errs+1))
    continue
  fi
  # The disclosure skill IS the disclosure workflow (matrix cell = "main workflow"),
  # so there is no suppressed-patient behavior keyword to assert — presence suffices.
  [[ "$skill" == "disclosure" ]] && continue
  # 2) extract the ACTUAL disclosure-behavior cell — the inline `*Disclosure*:` /
  # `**Disclosure**` declaration line, or the body of a `## Disclosure` section — and
  # assert the matrix keyword appears INSIDE it. Scoping to the cell itself (not a fixed
  # line window) prevents an unrelated `refuse`/`晚期` elsewhere in the file (a preflight
  # role-gate, a Role-behavior family-refuse rule, an example query) from false-passing a
  # flipped cell.
  dcell="$(awk '
    /^#+ *Disclosure/ { sec=1; print; next }
    sec==1 && /^#+ / { sec=0 }
    sec==1 { print; next }
    /\*Disclosure\*:|\*\*Disclosure\*\*/ { print }
  ' "$f")"
  re="$(behavior_re "$skill")"
  if ! echo "$dcell" | grep -qiE "$re"; then
    echo "FAIL: cancer-buddy-$skill disclosure cell inconsistent with matrix (expected /$re/ in the Disclosure cell)" >&2
    errs=$((errs+1))
  fi
done

if (( errs > 0 )); then
  echo "$errs disclosure-gate violation(s)" >&2
  exit 1
fi
echo "disclosure gate intact (${#affected[@]} companions, matrix-consistent)"
