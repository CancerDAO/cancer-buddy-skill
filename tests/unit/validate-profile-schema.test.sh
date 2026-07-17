#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/validate-profile-schema.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0

run_case() {
  local label="$1" expected="$2" dir="$3" got
  if bash "$SCRIPT" "$dir" >/dev/null 2>&1; then got=pass; else got=fail; fi
  if [[ "$got" == "$expected" ]]; then pass=$((pass+1)); else
    echo "FAIL: $label expected=$expected got=$got" >&2; fail=$((fail+1));
  fi
}

mkdir "$tmp/no_profile"
run_case "missing profile" fail "$tmp/no_profile"

mkdir "$tmp/minimal"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1","summary":{}}' > "$tmp/minimal/profile.json"
run_case "missing diagnosis fields remain valid unknowns" pass "$tmp/minimal"

mkdir "$tmp/bad_code"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"patient-name","summary":{}}' > "$tmp/bad_code/profile.json"
run_case "patient code must be random-style locator" fail "$tmp/bad_code"

mkdir "$tmp/ecog5"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A2","summary":{},"latest_status":{"ecog":5}}' > "$tmp/ecog5/profile.json"
run_case "clinician ECOG 5 allowed" pass "$tmp/ecog5"

mkdir "$tmp/ecog_bool"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A3","summary":{},"latest_status":{"ecog":true}}' > "$tmp/ecog_bool/profile.json"
run_case "boolean ECOG rejected" fail "$tmp/ecog_bool"

mkdir "$tmp/old_readiness"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A4","summary":{}}' > "$tmp/old_readiness/profile.json"
echo '{"schema_version":"1","grade":"B","review_flags":[]}' > "$tmp/old_readiness/readiness.json"
run_case "A-F readiness retired" fail "$tmp/old_readiness"

mkdir "$tmp/readiness_ok"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A5","summary":{}}' > "$tmp/readiness_ok/profile.json"
cat > "$tmp/readiness_ok/readiness.json" <<'JSON'
{"patient_code":"PT-A5","schema_version":"2","documentation_coverage":{"pathology_documents":"not_in_archive"},"review_flags":[{"id":"RF-1","category":"cross_source_conflict","affected_field":"diagnosis.stage","current_source_values":[{"value":"III","source_ref":"04_diagnosis_staging/a.md"},{"value":"IV","source_ref":"04_diagnosis_staging/b.md"}],"issue":"different source strings","resolution_status":"unresolved"}]}
JSON
run_case "source-preserving readiness v2" pass "$tmp/readiness_ok"

mkdir "$tmp/model_value"
cp "$tmp/readiness_ok/profile.json" "$tmp/model_value/profile.json"
cat > "$tmp/model_value/readiness.json" <<'JSON'
{"patient_code":"PT-A5","schema_version":"2","documentation_coverage":{},"review_flags":[{"id":"RF-1","category":"cross_source_conflict","affected_field":"diagnosis.stage","current_source_values":[],"issue":"x","resolution_status":"unresolved","suggested_value":"IV"}]}
JSON
run_case "model-proposed clinical replacement rejected" fail "$tmp/model_value"

mkdir "$tmp/user_override"
cp "$tmp/readiness_ok/profile.json" "$tmp/user_override/profile.json"
cat > "$tmp/user_override/readiness.json" <<'JSON'
{"patient_code":"PT-A5","schema_version":"2","documentation_coverage":{},"review_flags":[{"id":"RF-1","category":"cross_source_conflict","affected_field":"diagnosis.stage","current_source_values":[],"issue":"x","resolution_status":"unresolved","user_confirmed":true}]}
JSON
run_case "patient override of source conflict rejected" fail "$tmp/user_override"

mkdir "$tmp/bad_coverage"
cp "$tmp/readiness_ok/profile.json" "$tmp/bad_coverage/profile.json"
echo '{"schema_version":"2","documentation_coverage":{"molecular":0.8},"review_flags":[]}' > "$tmp/bad_coverage/readiness.json"
run_case "numeric coverage score rejected" fail "$tmp/bad_coverage"

echo "validate-profile-schema: pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
