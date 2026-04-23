#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/validate-profile-schema.sh"

tmpdir="$(mktemp -d)"
trap "rm -rf $tmpdir" EXIT

pass=0
fail=0
run_case() {
  local label="$1"; shift
  local expect="$1"; shift  # "pass" or "fail"
  if bash "$SCRIPT" "$@" >/dev/null 2>&1; then
    got=pass
  else
    got=fail
  fi
  if [[ "$got" == "$expect" ]]; then
    pass=$((pass+1))
  else
    echo "FAIL: $label — expected $expect, got $got" >&2
    fail=$((fail+1))
  fi
}

# case 1: missing directory
run_case "missing dir" fail "$tmpdir/nonexistent"

# case 2: missing profile.json
mkdir -p "$tmpdir/c2"
run_case "no profile.json" fail "$tmpdir/c2"

# case 3: invalid JSON
mkdir -p "$tmpdir/c3"
echo "not json" > "$tmpdir/c3/profile.json"
run_case "invalid json" fail "$tmpdir/c3"

# case 4: missing required field
mkdir -p "$tmpdir/c4"
cat > "$tmpdir/c4/profile.json" <<'JSON'
{"schema_version": "1.0.0"}
JSON
run_case "missing required fields" fail "$tmpdir/c4"

# case 5: invalid ECOG enum
mkdir -p "$tmpdir/c5"
cat > "$tmpdir/c5/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"basics":{"ecog":7}}
JSON
run_case "invalid ecog" fail "$tmpdir/c5"

# case 6: invalid readiness grade
mkdir -p "$tmpdir/c6"
cat > "$tmpdir/c6/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
echo '{"schema_version":"1","grade":"Z"}' > "$tmpdir/c6/readiness.json"
run_case "invalid readiness grade" fail "$tmpdir/c6"

# case 7: valid minimal profile
mkdir -p "$tmpdir/c7"
cat > "$tmpdir/c7/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
run_case "valid minimal" pass "$tmpdir/c7"

# case 8: valid with v3 optional fields
mkdir -p "$tmpdir/c8"
cat > "$tmpdir/c8/profile.json" <<'JSON'
{
  "schema_version":"1.0.0","patient_code":"PT-X",
  "diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},
  "disclosure_state":"partial",
  "acp_status":"discussed",
  "surveillance_schedule_anchor":"2025-08-30"
}
JSON
run_case "valid v3 fields" pass "$tmpdir/c8"

# case 9: invalid disclosure_state enum
mkdir -p "$tmpdir/c9"
cat > "$tmpdir/c9/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"disclosure_state":"sort-of"}
JSON
run_case "invalid disclosure_state" fail "$tmpdir/c9"

# case 10: treatment_history out of order
mkdir -p "$tmpdir/c10"
cat > "$tmpdir/c10/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},
 "treatment_history":[{"line":2,"regimen":"X","start":"2024-01-01"},{"line":1,"regimen":"Y","start":"2025-01-01"}]}
JSON
run_case "treatment_history out of order" fail "$tmpdir/c10"

if (( fail > 0 )); then
  echo "$fail/$((pass+fail)) test cases failed"
  exit 1
fi
echo "$pass/$pass test cases passed"
