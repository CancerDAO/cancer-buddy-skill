#!/usr/bin/env bash
# For every sub-skill affected by disclosure (per disclosure-behavior.md), assert its
# SKILL.md declares a Disclosure: note in the patient-role bullet.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
errs=0

# Sub-skills that must declare disclosure behavior
# (caregiver is N/A; meta-skill cancer-buddy is routing-only)
affected=(
  organize
  explore
  mtb-lite
  trial-match
  access
  manage
  vault
  education
  mind
  inflection
  nutrition
  second-opinion
  adherence
  survivorship
  comfort
  disclosure
)

for skill in "${affected[@]}"; do
  f="$REPO_ROOT/skills/cancer-buddy-$skill/SKILL.md"
  if [[ ! -f "$f" ]]; then
    # Skills not yet created (v3.0 runs before adherence/survivorship/comfort/disclosure ship)
    continue
  fi
  if ! grep -qi 'Disclosure' "$f"; then
    echo "FAIL: cancer-buddy-$skill missing Disclosure: note in Role behavior"
    errs=$((errs+1))
  fi
done

if (( errs > 0 )); then
  echo "$errs disclosure-gate violation(s)" >&2
  exit 1
fi
echo "disclosure gate declarations intact"
