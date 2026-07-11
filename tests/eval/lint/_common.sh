#!/usr/bin/env bash
# Shared helpers for tests/eval/lint/* — sourced, not run directly.
# Convention mirrors tests/unit/ + tests/integration/: pure shell, no deps,
# exit code reflects pass/fail; one fail-line per violation on stderr.

# REPO_ROOT resolves to the repo top from any lint/ script.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[1]}")/../../.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
REFS_DIR="$SKILLS_DIR/cancer-buddy/references"

# Patient-visible companion sub-skills = every skills/cancer-buddy-*/ directory.
# Derived from disk (not a hand-maintained list) so the lints CANNOT silently drift
# behind a newly-added companion — the exact bug that left cancer-buddy-visit-prep
# unguarded. The meta router `cancer-buddy` and the bundled `web-access` plumbing
# skill do NOT match the `cancer-buddy-*` glob and are intentionally excluded — they
# emit no clinical scaffold.
PATIENT_VISIBLE_SKILLS=()
for _d in "$SKILLS_DIR"/cancer-buddy-*/; do
  [[ -d "$_d" ]] || continue
  PATIENT_VISIBLE_SKILLS+=("$(basename "$_d")")
done
unset _d

# fail <msg>  — record a violation line on stderr, bump the caller's $errs.
fail() {
  echo "FAIL: $1" >&2
  errs=$((errs+1))
}

# summarize <label>  — final line + exit code for a single lint script.
summarize() {
  local label="$1"
  if (( errs > 0 )); then
    echo "$errs $label violation(s)" >&2
    exit 1
  fi
  echo "$label OK"
}
