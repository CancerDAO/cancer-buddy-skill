#!/usr/bin/env bash
# Shared helpers for tests/eval/lint/* — sourced, not run directly.
# Convention mirrors tests/unit/ + tests/integration/: pure shell, no deps,
# exit code reflects pass/fail; one fail-line per violation on stderr.

# REPO_ROOT resolves to the repo top from any lint/ script.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[1]}")/../../.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
REFS_DIR="$REPO_ROOT/references"

# Patient-visible companion sub-skills (8). The meta router `cancer-buddy`
# and the bundled `web-access` plumbing skill are handled separately where
# relevant — they are NOT in this list because they emit no clinical scaffold.
PATIENT_VISIBLE_SKILLS=(
  cancer-buddy-organize
  cancer-buddy-mind
  cancer-buddy-caregiver
  cancer-buddy-disclosure
  cancer-buddy-education
  cancer-buddy-nutrition
  cancer-buddy-find-care
  cancer-buddy-second-opinion
  cancer-buddy-vault
)

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
