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

# case 11: valid readiness with empty review_flags
mkdir -p "$tmpdir/c11"
cat > "$tmpdir/c11/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c11/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[]}
JSON
run_case "empty review_flags" pass "$tmpdir/c11"

# case 12: valid readiness with one well-formed review_flag
mkdir -p "$tmpdir/c12"
cat > "$tmpdir/c12/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c12/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"format_violation","field_path":"stage",
   "current_value":"rpT4aN2aM1","issue":"non-AJCC prefix","source_evidence":["90_原始文件镜像/x.jpg"],
   "suggested_action":"rewrite to p","user_confirmed":false}
]}
JSON
run_case "well-formed review_flag" pass "$tmpdir/c12"

# case 13: invalid review_flag severity
mkdir -p "$tmpdir/c13"
cat > "$tmpdir/c13/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c13/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"critical","category":"format_violation","field_path":"stage",
   "current_value":"rpT4aN2aM1","issue":"non-AJCC prefix","source_evidence":["x"],
   "suggested_action":"rewrite","user_confirmed":false}
]}
JSON
run_case "invalid review_flag severity" fail "$tmpdir/c13"

# case 14: invalid review_flag category
mkdir -p "$tmpdir/c14"
cat > "$tmpdir/c14/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c14/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"typo","field_path":"stage",
   "current_value":"x","issue":"x","source_evidence":["x"],
   "suggested_action":"x","user_confirmed":false}
]}
JSON
run_case "invalid review_flag category" fail "$tmpdir/c14"

# case 15: review_flag missing required key
mkdir -p "$tmpdir/c15"
cat > "$tmpdir/c15/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c15/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"format_violation"}
]}
JSON
run_case "review_flag missing keys" fail "$tmpdir/c15"

# case 16: review_flags must be array, not object
mkdir -p "$tmpdir/c16"
cat > "$tmpdir/c16/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c16/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":{"foo":"bar"}}
JSON
run_case "review_flags wrong type" fail "$tmpdir/c16"

# case 17: review_flag user_confirmed must be bool
mkdir -p "$tmpdir/c17"
cat > "$tmpdir/c17/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
cat > "$tmpdir/c17/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"format_violation","field_path":"stage",
   "current_value":"x","issue":"x","source_evidence":["x"],
   "suggested_action":"x","user_confirmed":"no"}
]}
JSON
run_case "user_confirmed wrong type" fail "$tmpdir/c17"

if (( fail > 0 )); then
  echo "$fail/$((pass+fail)) test cases failed"
  exit 1
fi
echo "$pass/$pass test cases passed"
