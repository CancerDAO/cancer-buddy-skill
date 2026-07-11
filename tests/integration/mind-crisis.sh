#!/usr/bin/env bash
# Static integration contract for the mind crisis path. Runtime behavior is
# covered by the manual/LLM-judge scenarios in tests/eval/scenarios/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MIND_SKILL="$REPO_ROOT/skills/cancer-buddy-mind/SKILL.md"
CRISIS_REF="$REPO_ROOT/skills/cancer-buddy-mind/references/crisis-resources.md"
MEDICAL_GATE="$REPO_ROOT/skills/cancer-buddy/references/medical-emergency-gate.md"

errs=0
check() {
  local pattern="$1" file="$2" message="$3"
  grep -qiE "$pattern" "$file" || { echo "FAIL: $message" >&2; errs=$((errs+1)); }
}

check 'non-negotiable|non-overridable|不可覆盖|非覆盖' "$MIND_SKILL" \
  'mind SKILL.md missing non-negotiable suicide-safety rule'
check '已经做了什么|already (done|acted)|overdose|过量' "$MIND_SKILL" \
  'mind SKILL.md does not ask whether an act/overdose is underway'
check 'current intent|当前意图|现在.*意图' "$MIND_SKILL" \
  'mind SKILL.md does not assess current intent'
check 'specific plan|具体计划' "$MIND_SKILL" \
  'mind SKILL.md does not assess a specific plan'
check 'access.*means|means.*access|手段|药物/工具' "$MIND_SKILL" \
  'mind SKILL.md does not assess access to means'
check 'whether.*alone|是否独处|一个人' "$MIND_SKILL" \
  'mind SKILL.md does not ask whether the person is alone'
check 'declines? a hotline|拒绝热线|拒绝.*不要.*(结束|抛下)|do not abandon' "$MIND_SKILL" \
  'mind SKILL.md may abandon a person who declines a hotline'
check 'do not dump|不要.*(整张表|整页).*倾倒|1.?2.*(contact|个.*入口)' "$MIND_SKILL" \
  'mind SKILL.md does not limit the response to useful regional contacts'
check 'do not write.*by default|默认.*不(写|落盘|保存)|Never create a temporary.*crisis' "$MIND_SKILL" \
  'mind SKILL.md does not make crisis records opt-in'
check 'crisis-resources\.md' "$MIND_SKILL" \
  "mind SKILL.md doesn't reference crisis-resources.md"

check '12356' "$CRISIS_REF" 'mainland China psychological support number 12356 missing'
check '\*\*120\*\*|(^|[^0-9])120([^0-9]|$)' "$CRISIS_REF" \
  'mainland China emergency number 120 missing'
check '1.?2.*(入口|contact)|不要.*(整张表|整页).*倾倒|do not dump' "$CRISIS_REF" \
  'crisis reference does not prohibit a full hotline dump'
if grep -q '400-161-9995' "$CRISIS_REF"; then
  echo 'FAIL: retired/unverified 400-161-9995 must not be restored' >&2
  errs=$((errs+1))
fi

check '38\.0' "$MEDICAL_GATE" 'chemotherapy fever emergency threshold 38.0°C missing'
check 'chest pain|胸痛|胸部.*疼' "$MEDICAL_GATE" 'chest-pain emergency signal missing'
check 'before role|先于.*身份|role checks' "$MEDICAL_GATE" \
  'medical emergency gate is not ordered before role/routing'

if (( errs > 0 )); then
  echo "$errs mind-crisis violation(s)" >&2
  exit 1
fi
echo "mind crisis safety intact"
