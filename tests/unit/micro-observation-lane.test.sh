#!/usr/bin/env bash
# Guard the micro-observation fast lane + opt-in alias wiring.
#
# The lane exists so a single self-monitored reading (体温/血压/…) never pays the
# full organize pipeline. These checks assert the load-bearing properties that
# must not regress silently:
#   1. the lane exists and is routed to from the size triage;
#   2. de-identification is explicitly KEPT (speed must never be bought by
#      skipping masking);
#   3. full synthesis / 段D re-render are explicitly skipped, with the
#      freshness gate (case_summary_stale) as the deferral mechanism;
#   4. the Definition of Done carve-out exists (micro lane has a reduced
#      done-gate; full runs keep the full checklist);
#   5. no-archive micro input never silently builds a full archive;
#   6. the headless binding tells platform hosts to run it single-round;
#   7. alias is opt-in only: no auto-generated {cancer_code}_{year} alias.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SK="$ROOT/skills/cancer-buddy-organize/SKILL.md"
P2="$ROOT/skills/cancer-buddy-organize/references/organizer-prompt-phase2-synthesis.md"
HC="$ROOT/skills/cancer-buddy-organize/references/runtime-bindings/headless-codex.md"
CT="$ROOT/skills/cancer-buddy-organize/references/organize-contract.md"
META="$ROOT/skills/cancer-buddy/SKILL.md"
SCHEMA="$ROOT/skills/cancer-buddy/references/patient-profile-schema.md"

errs=0
fail() { echo "FAIL: $1" >&2; errs=$((errs+1)); }

# 1. lane + triage exist
grep -q 'run_mode: "micro_observation"' "$SK" \
  || fail "SKILL.md: micro_observation run mode missing"
grep -q 'Size triage' "$SK" \
  || fail "SKILL.md: size triage missing from When to use"

# 2. masking is explicitly kept in the lane
grep -q 'de-identification is NOT skipped' "$SK" \
  || fail "SKILL.md: micro lane no longer states that masking is kept"

# 3. heavy machinery explicitly skipped; deferral via freshness gate
grep -q '段D is never re-rendered here' "$SK" \
  || fail "SKILL.md: micro lane no longer defers 段D re-render"
grep -q 'case_summary_stale' "$SK" \
  || fail "SKILL.md: case_summary_stale freshness mechanism missing"

# 4. DoD carve-out
grep -q '降级 done-gate' "$SK" \
  || fail "SKILL.md: Definition of Done carve-out for light run modes missing"

# 5. no silent full archive for a single reading
grep -q 'do NOT silently build a full canonical archive' "$SK" \
  || fail "SKILL.md: no-archive micro input protection missing"

# 6. headless binding single-round lane
grep -q '微量观测快车道' "$HC" \
  || fail "headless-codex.md: micro lane section missing"
grep -q '单轮完成' "$HC" \
  || fail "headless-codex.md: single-round requirement missing"
grep -q 'micro_observation' "$CT" \
  || fail "organize-contract.md: reduced-product-set run-mode note missing"
grep -q '微量观测' "$META" \
  || fail "meta SKILL.md: router does not mention the micro lane"

# 7. alias is opt-in only
grep -q 'alias_opt_in' "$P2" \
  || fail "phase2 prompt: alias_opt_in parameter missing"
if grep -q '"alias": "<patient_id_short>' "$P2"; then
  fail "phase2 prompt: profile example auto-fills alias (must default null)"
fi
grep -q 'default \*\*`null`\*\* — never auto-generated' "$P2" \
  || fail "phase2 prompt: alias default-null rule missing"
grep -q '`alias` (optional, default `null`)' "$SCHEMA" \
  || fail "patient-profile-schema.md: alias still documented as required"
grep -q 'Display alias (opt-in only)' "$SK" \
  || fail "SKILL.md: alias section no longer opt-in"

if (( errs > 0 )); then
  echo "$errs micro-observation-lane violation(s)" >&2
  exit 1
fi
echo "micro-observation lane + opt-in alias wiring OK"
