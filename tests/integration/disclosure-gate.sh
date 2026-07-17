#!/usr/bin/env bash
# Ensure disclosure controls protect viewer authorization without suppressing a
# capable patient's explicit request for their own information.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
errs=0

for name in organize vault education nutrition second-opinion disclosure find-care visit-prep; do
  file="$ROOT/skills/cancer-buddy-$name/SKILL.md"
  if [[ ! -f "$file" ]]; then
    echo "FAIL: cancer-buddy-$name missing" >&2; errs=$((errs+1)); continue
  fi
  grep -q 'disclosure-behavior\.md' "$file" || {
    echo "FAIL: cancer-buddy-$name does not cite disclosure-behavior.md" >&2; errs=$((errs+1));
  }
done

POLICY="$ROOT/references/disclosure-behavior.md"
grep -qiE 'explicit.*request|明确.*(请求|要求)' "$POLICY" || {
  echo "FAIL: shared policy lacks explicit-patient-request rule" >&2; errs=$((errs+1));
}
grep -qiE 'authorized|授权' "$POLICY" || {
  echo "FAIL: shared policy lacks viewer-authorization rule" >&2; errs=$((errs+1));
}
grep -qiE 'family.*(cannot|must not|不得|不能).*override|家属.*(不得|不能).*覆盖' "$POLICY" || {
  echo "FAIL: shared policy does not prevent family override" >&2; errs=$((errs+1));
}

if (( errs )); then
  echo "$errs disclosure-gate violation(s)" >&2
  exit 1
fi
echo "disclosure gate intact: patient request + viewer authorization"
