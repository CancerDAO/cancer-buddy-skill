#!/usr/bin/env bash
# For every sub-skill SKILL.md, assert a `## Role behavior` section exists
# and names all three role tokens (patient, caregiver, family).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
errs=0

for skill_md in "$REPO_ROOT"/skills/cancer-buddy-*/SKILL.md; do
  name=$(basename "$(dirname "$skill_md")")
  # caregiver skill is itself the caregiver entrypoint — still needs the matrix
  if ! grep -q '^## Role behavior' "$skill_md"; then
    echo "FAIL: $name missing ## Role behavior" >&2
    errs=$((errs+1))
    continue
  fi
  body=$(awk '/^## Role behavior/,/^## [^R]/' "$skill_md")
  for role in patient caregiver family; do
    if ! echo "$body" | grep -q "Role = $role\|role = $role\|active_role = $role"; then
      echo "FAIL: $name Role behavior missing '$role' branch" >&2
      errs=$((errs+1))
    fi
  done
done

if (( errs > 0 )); then
  echo "$errs role-matrix violation(s)" >&2
  exit 1
fi
echo "role matrix intact across all sub-skills"
