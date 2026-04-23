#!/usr/bin/env bash
# Assert cancer-buddy-comfort has the 10 hard safety rules explicitly.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$REPO_ROOT/skills/cancer-buddy-comfort/SKILL.md"
GUARDRAILS="$REPO_ROOT/references/safety-guardrails.md"
errs=0

[[ -f "$SKILL" ]] || { echo "FAIL: comfort SKILL.md missing"; exit 1; }

grep -qi 'C-SSRS' "$SKILL" || { echo "FAIL: comfort missing C-SSRS screening rule"; errs=$((errs+1)); }
grep -qi 'never advocate\|never recommend.*stop\|never recommend.*continue' "$SKILL" || { echo "FAIL: comfort missing 'never advocate' rule"; errs=$((errs+1)); }
grep -q '换一种照顾目标' "$SKILL" || { echo "FAIL: comfort missing hospice reframing"; errs=$((errs+1)); }
grep -q '安乐死' "$SKILL" || grep -q 'euthanasia' "$SKILL" || { echo "FAIL: comfort missing euthanasia legal note"; errs=$((errs+1)); }
grep -qi 'WHO.*阶梯\|opiophobia\|阿片' "$SKILL" || { echo "FAIL: comfort missing opiophobia correction"; errs=$((errs+1)); }
grep -q 'Temel\|NEJM 2010' "$SKILL" || { echo "FAIL: comfort missing mandatory Temel footer"; errs=$((errs+1)); }
grep -q 'cancer-buddy-mind\|crisis' "$SKILL" || { echo "FAIL: comfort does not route to mind for crisis"; errs=$((errs+1)); }
grep -q 'Palliative\|缓和' "$GUARDRAILS" || { echo "FAIL: safety-guardrails missing palliative rules"; errs=$((errs+1)); }

if (( errs > 0 )); then
  echo "$errs comfort safety violation(s)" >&2; exit 1
fi
echo "comfort safety rules intact"
