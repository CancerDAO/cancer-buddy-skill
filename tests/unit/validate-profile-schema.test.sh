#!/usr/bin/env bash
# Unit tests for scripts/validate-profile-schema.sh.
# Profile fixtures use the cancer_buddy_profile_v3 (nested) shape — schema doc:
# references/patient-profile-schema.md. The legacy flat shape (schema_version +
# top-level diagnosis) must now be REJECTED (case 10) so a regression back to it
# is caught.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/validate-profile-schema.sh"

tmpdir="$(mktemp -d)"
trap "rm -rf $tmpdir" EXIT

# minimal valid v3 profile, reused by readiness/role cases that don't test profile
V3_MIN='{"schema":"cancer_buddy_profile_v3","patient_code":"PT-X","summary":{"primary":"lung","histology":"adeno","stage":"IV"}}'

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

# case 4: missing required fields (schema present, summary + patient_code missing)
mkdir -p "$tmpdir/c4"
cat > "$tmpdir/c4/profile.json" <<'JSON'
{"schema": "cancer_buddy_profile_v3"}
JSON
run_case "missing required fields" fail "$tmpdir/c4"

# case 5: invalid ECOG enum (ECOG lives under latest_status in v3)
mkdir -p "$tmpdir/c5"
cat > "$tmpdir/c5/profile.json" <<'JSON'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-X","summary":{"primary":"lung","histology":"adeno","stage":"IV"},"latest_status":{"ecog":7}}
JSON
run_case "invalid latest_status.ecog" fail "$tmpdir/c5"

# case 6: invalid readiness grade (profile is valid v3)
mkdir -p "$tmpdir/c6"
echo "$V3_MIN" > "$tmpdir/c6/profile.json"
echo '{"schema_version":"1","grade":"Z"}' > "$tmpdir/c6/readiness.json"
run_case "invalid readiness grade" fail "$tmpdir/c6"

# case 7: valid minimal v3 profile
mkdir -p "$tmpdir/c7"
echo "$V3_MIN" > "$tmpdir/c7/profile.json"
run_case "valid minimal v3" pass "$tmpdir/c7"

# case 8: valid v3 with optional fields (alias / locale / latest_status / disclosure_state / anthropometrics)
mkdir -p "$tmpdir/c8"
cat > "$tmpdir/c8/profile.json" <<'JSON'
{
  "schema":"cancer_buddy_profile_v3","patient_code":"PT-48C5070065","alias":"48C507_CRC_2022","locale":"zh",
  "summary":{"primary":"乙状结肠恶性肿瘤","histology":"中分化腺癌","stage":"ypT4aN2aM1 IV期"},
  "latest_status":{"regimen":"FOLFOX","response":"NE","ecog":1,"as_of":"2024-07-05"},
  "anthropometrics":{"height_cm":170,"weight_kg":80,"bmi":27.7},
  "disclosure_state":"partial"
}
JSON
run_case "valid v3 optional fields" pass "$tmpdir/c8"

# case 9: invalid disclosure_state enum
mkdir -p "$tmpdir/c9"
cat > "$tmpdir/c9/profile.json" <<'JSON'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-X","summary":{"primary":"lung","histology":"adeno","stage":"IV"},"disclosure_state":"sort-of"}
JSON
run_case "invalid disclosure_state" fail "$tmpdir/c9"

# case 10: legacy flat profile must be REJECTED (regression guard against reverting to flat shape)
mkdir -p "$tmpdir/c10"
cat > "$tmpdir/c10/profile.json" <<'JSON'
{"schema_version":"1.0.0","patient_code":"PT-X","diagnosis":{"primary_site":"lung","histology":"adeno","stage":"IV"}}
JSON
run_case "legacy flat shape rejected" fail "$tmpdir/c10"

# case 11: valid readiness with empty review_flags
mkdir -p "$tmpdir/c11"
echo "$V3_MIN" > "$tmpdir/c11/profile.json"
cat > "$tmpdir/c11/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[]}
JSON
run_case "empty review_flags" pass "$tmpdir/c11"

# case 12: valid readiness with one well-formed review_flag
mkdir -p "$tmpdir/c12"
echo "$V3_MIN" > "$tmpdir/c12/profile.json"
cat > "$tmpdir/c12/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"format_violation","field_path":"stage",
   "current_value":"rpT4aN2aM1","issue":"non-AJCC prefix","source_evidence":["04_诊断与分期/诊断证明/x.md"],
   "suggested_action":"rewrite to p","user_confirmed":false}
]}
JSON
run_case "well-formed review_flag" pass "$tmpdir/c12"

# case 13: invalid review_flag severity
mkdir -p "$tmpdir/c13"
echo "$V3_MIN" > "$tmpdir/c13/profile.json"
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
echo "$V3_MIN" > "$tmpdir/c14/profile.json"
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
echo "$V3_MIN" > "$tmpdir/c15/profile.json"
cat > "$tmpdir/c15/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"format_violation"}
]}
JSON
run_case "review_flag missing keys" fail "$tmpdir/c15"

# case 16: review_flags must be array, not object
mkdir -p "$tmpdir/c16"
echo "$V3_MIN" > "$tmpdir/c16/profile.json"
cat > "$tmpdir/c16/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":{"foo":"bar"}}
JSON
run_case "review_flags wrong type" fail "$tmpdir/c16"

# case 17: review_flag user_confirmed must be bool
mkdir -p "$tmpdir/c17"
echo "$V3_MIN" > "$tmpdir/c17/profile.json"
cat > "$tmpdir/c17/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-001","severity":"red","category":"format_violation","field_path":"stage",
   "current_value":"x","issue":"x","source_evidence":["x"],
   "suggested_action":"x","user_confirmed":"no"}
]}
JSON
run_case "user_confirmed wrong type" fail "$tmpdir/c17"

# case 18: v3 profile missing summary.stage must be REJECTED (the real v3 regression the guard must catch)
mkdir -p "$tmpdir/c18"
cat > "$tmpdir/c18/profile.json" <<'JSON'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-X","summary":{"primary":"lung","histology":"adeno"}}
JSON
run_case "v3 missing summary.stage" fail "$tmpdir/c18"

# case 19: review_flag with a newly-rostered category (filename_content_mismatch) must PASS
mkdir -p "$tmpdir/c19"
echo "$V3_MIN" > "$tmpdir/c19/profile.json"
cat > "$tmpdir/c19/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-009","severity":"red","category":"filename_content_mismatch","field_path":"file_3",
   "current_value":"肿瘤标志物","issue":"sidecar is a 生化 panel","source_evidence":["07_检验/x.md"],
   "suggested_action":"correct doc_type","user_confirmed":false}
]}
JSON
run_case "review_flag filename_content_mismatch (9-roster)" pass "$tmpdir/c19"

# case 20: wrong schema literal must be REJECTED
mkdir -p "$tmpdir/c20"
cat > "$tmpdir/c20/profile.json" <<'JSON'
{"schema":"cancer_buddy_profile_v2","patient_code":"PT-X","summary":{"primary":"lung","histology":"adeno","stage":"IV"}}
JSON
run_case "wrong schema literal" fail "$tmpdir/c20"

# case 21: review_flag with cross_patient_name_collision (P0, newly-rostered) must PASS
mkdir -p "$tmpdir/c21"
echo "$V3_MIN" > "$tmpdir/c21/profile.json"
cat > "$tmpdir/c21/readiness.json" <<'JSON'
{"schema_version":"1","grade":"B","review_flags":[
  {"id":"RF-006","severity":"red","category":"cross_patient_name_collision","field_path":"demographics.name",
   "current_value":"张三","issue":"name+DOB year match PT-Y","source_evidence":["01_身份与基础信息/x.md"],
   "suggested_action":"确认是否同一病人","user_confirmed":false}
]}
JSON
run_case "review_flag cross_patient_name_collision (9-roster)" pass "$tmpdir/c21"

if (( fail > 0 )); then
  echo "$fail/$((pass+fail)) test cases failed"
  exit 1
fi
echo "$pass/$pass test cases passed"
