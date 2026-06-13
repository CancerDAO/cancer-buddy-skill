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
  # Capture the body strictly between `## Role behavior` and the next `## ` header
  # (flag-based, so it stops at any following header incl. `## References`).
  body=$(awk '/^## Role behavior/{f=1; next} f && /^## /{f=0} f{print}' "$skill_md")
  for role in patient caregiver family; do
    # Spacing- and case-tolerant: matches `role=patient`, `Role = patient`, `active_role = patient`.
    if ! echo "$body" | grep -qiE "role[[:space:]]*=[[:space:]]*$role|active_role[[:space:]]*=[[:space:]]*$role"; then
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
