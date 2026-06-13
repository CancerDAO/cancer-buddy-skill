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
behavior_re() {
  case "$1" in
    organize)        echo 'suppress' ;;                    # warn entering breaks suppression
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
  # 2) declaration is consistent with the disclosure-behavior.md matrix cell.
  # Scope the keyword search to the disclosure DECLARATION region (each line that
  # mentions disclosure + the following 5 lines) so unrelated prose elsewhere in the
  # SKILL.md (e.g. a "晚期" example query) can't false-pass the consistency check.
  dscope="$(awk '/[Dd]isclosure/{c=6} c>0{print; c--}' "$f")"
  re="$(behavior_re "$skill")"
  if ! echo "$dscope" | grep -qiE "$re"; then
    echo "FAIL: cancer-buddy-$skill disclosure behavior inconsistent with matrix (expected /$re/ near a disclosure declaration)" >&2
    errs=$((errs+1))
  fi
done

if (( errs > 0 )); then
  echo "$errs disclosure-gate violation(s)" >&2
  exit 1
fi
echo "disclosure gate intact (${#affected[@]} companions, matrix-consistent)"
