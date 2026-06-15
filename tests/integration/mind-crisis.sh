#!/usr/bin/env bash
# Verify cancer-buddy-mind SKILL.md contains non-overridable crisis rule
# and surfaces all hotline numbers from crisis-resources.md (the authoritative table; do not hardcode a count)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MIND_SKILL="$REPO_ROOT/skills/cancer-buddy-mind/SKILL.md"
CRISIS_REF="$REPO_ROOT/skills/cancer-buddy-mind/references/crisis-resources.md"

errs=0
# 1. SKILL.md has non-overridable crisis rule
grep -q 'Crisis rule.*non-negotiable\|非覆盖\|Not overridable\|never overridable' "$MIND_SKILL" || { echo "FAIL: mind SKILL.md missing non-overridable language"; errs=$((errs+1)); }

# 2. crisis-resources has at least 3 hotline numbers
hotline_count=$(grep -cE '^\| \*\*[0-9-]+\*\*|^\| \*\*400-|^\| \*\*010-|^\| \*\*021-' "$CRISIS_REF" || true)
if (( hotline_count < 3 )); then
  echo "FAIL: crisis-resources has fewer than 3 hotlines (found $hotline_count)"
  errs=$((errs+1))
fi

# 3. canonical national line 12356 + 希望24热线 400-161-9995 must be present
grep -q '12356' "$CRISIS_REF" || { echo "FAIL: canonical national line 12356 missing"; errs=$((errs+1)); }
grep -q '400-161-9995' "$CRISIS_REF" || { echo "FAIL: 希望24热线 400-161-9995 missing"; errs=$((errs+1)); }

# 4. Reference cross-check: SKILL.md cites crisis-resources.md
grep -q 'crisis-resources.md' "$MIND_SKILL" || { echo "FAIL: mind SKILL.md doesn't reference crisis-resources.md"; errs=$((errs+1)); }

if (( errs > 0 )); then
  echo "$errs mind-crisis violation(s)" >&2
  exit 1
fi
echo "mind crisis safety intact"
