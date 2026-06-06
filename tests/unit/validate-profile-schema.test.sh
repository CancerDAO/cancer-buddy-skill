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
   "current_value":"rpT4aN2aM1","issue":"non-AJCC prefix","source_evidence":["10_原始文件/x.jpg"],
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

# --- null-tolerance cases (organize emits null for unknown optional fields) ---

# case 18: basics is null (whole object) — must not crash, treat as absent
mkdir -p "$tmpdir/c18"
cat > "$tmpdir/c18/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"basics":null}
JSON
run_case "basics null" pass "$tmpdir/c18"

# case 19: basics.sex null — unknown sex, not a violation
mkdir -p "$tmpdir/c19"
cat > "$tmpdir/c19/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"basics":{"sex":null,"ecog":null}}
JSON
run_case "sex+ecog null" pass "$tmpdir/c19"

# case 20: treatment_history with null start and null line — unknown, skipped
mkdir -p "$tmpdir/c20"
cat > "$tmpdir/c20/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},
 "treatment_history":[{"line":null,"regimen":"X","start":null}]}
JSON
run_case "treatment_history null start/line" pass "$tmpdir/c20"

# case 21: readiness.grade null — unknown grade, not a violation
mkdir -p "$tmpdir/c21"
cat > "$tmpdir/c21/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
echo '{"schema_version":"1","grade":null}' > "$tmpdir/c21/readiness.json"
run_case "readiness grade null" pass "$tmpdir/c21"

# case 22: review_flags null — no flags, treated as absent
mkdir -p "$tmpdir/c22"
cat > "$tmpdir/c22/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
echo '{"schema_version":"1","grade":"B","review_flags":null}' > "$tmpdir/c22/readiness.json"
run_case "review_flags null" pass "$tmpdir/c22"

# case 23: profile.json is a JSON array (non-object) — clean fail, no traceback
mkdir -p "$tmpdir/c23"
echo '[1,2,3]' > "$tmpdir/c23/profile.json"
run_case "profile.json non-object" fail "$tmpdir/c23"

# case 24: invalid sex value still rejected (guard didn't loosen the enum check)
mkdir -p "$tmpdir/c24"
cat > "$tmpdir/c24/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"basics":{"sex":"male"}}
JSON
run_case "invalid sex value" fail "$tmpdir/c24"

# --- required-field & type-soundness cases (null/wrong-type in REQUIRED positions = malformed) ---

# case 25: required field present-but-null (patient_code) — must fail (null == missing)
mkdir -p "$tmpdir/c25"
cat > "$tmpdir/c25/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":null,"diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
run_case "required field null" fail "$tmpdir/c25"

# case 26: diagnosis present-but-null — must fail (was silently passing)
mkdir -p "$tmpdir/c26"
cat > "$tmpdir/c26/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":null}
JSON
run_case "diagnosis null" fail "$tmpdir/c26"

# case 27: diagnosis is a non-object (string) — must fail (was silently passing)
mkdir -p "$tmpdir/c27"
cat > "$tmpdir/c27/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":"lung cancer"}
JSON
run_case "diagnosis non-object" fail "$tmpdir/c27"

# case 28: diagnosis sub-key present-but-null — must fail
mkdir -p "$tmpdir/c28"
cat > "$tmpdir/c28/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":null,"stage":"IV"}}
JSON
run_case "diagnosis sub-key null" fail "$tmpdir/c28"

# case 29: basics is a non-object truthy value (string containing 'ecog') — clean fail, no crash
mkdir -p "$tmpdir/c29"
cat > "$tmpdir/c29/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"basics":"ecogish"}
JSON
run_case "basics non-object string" fail "$tmpdir/c29"

# case 30: treatment_history is a non-array (string) — must fail (was silently skipped)
mkdir -p "$tmpdir/c30"
cat > "$tmpdir/c30/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},"treatment_history":"chemo"}
JSON
run_case "treatment_history non-array" fail "$tmpdir/c30"

# case 31: role.json is a non-object (array) — clean fail, no ugly traceback-via-except
mkdir -p "$tmpdir/c31"
cat > "$tmpdir/c31/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
echo '["patient"]' > "$tmpdir/c31/role.json"
run_case "role.json non-object" fail "$tmpdir/c31"

# case 32: fully-valid profile with optional nulls + valid role.json still passes (regression)
mkdir -p "$tmpdir/c32"
cat > "$tmpdir/c32/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"},
 "basics":{"sex":null,"ecog":null},"treatment_history":[{"line":1,"start":null,"regimen":"X"}],
 "disclosure_state":null,"acp_status":null}
JSON
echo '{"schema_version":"1","active_role":"patient"}' > "$tmpdir/c32/role.json"
run_case "valid with optional nulls + role" pass "$tmpdir/c32"

if (( fail > 0 )); then
  echo "$fail/$((pass+fail)) test cases failed"
  exit 1
fi
echo "$pass/$pass test cases passed"
