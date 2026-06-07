#!/usr/bin/env bash
# tests/eval/run.sh — run every static lint in tests/eval/lint/ and summarize.
#
# This runs ONLY the static linters (exit code = pass/fail across all of them).
# It does NOT run the LLM-judge scenarios in tests/eval/scenarios/ — those are
# behavioral checks over live model output and need a judge harness wired up
# (see tests/eval/README.md → "Honest automation status"). When that harness
# lands, add a `scenarios` stage here behind a `--with-llm-judge` flag.
set -uo pipefail
LINT_DIR="$(cd "$(dirname "$0")/lint" && pwd)"

pass=0
fail=0
echo "== cancer-buddy companion safety eval — static lint =="
echo

for script in "$LINT_DIR"/[0-9]*.sh; do
  name="$(basename "$script")"
  if bash "$script"; then
    pass=$((pass+1))
  else
    echo "  ^ $name FAILED" >&2
    fail=$((fail+1))
  fi
  echo
done

echo "== summary: $pass lint group(s) passed, $fail failed =="
if (( fail > 0 )); then
  exit 1
fi
echo "all static safety lints green"
