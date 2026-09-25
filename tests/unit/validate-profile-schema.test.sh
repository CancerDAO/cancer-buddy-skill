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

# ---- readiness v2.1 + profile.demographics (schemas/README.md version policy / O-08). A readiness "2" archive
# (above) stays valid with a WARN; readiness "2.1" archives must carry the new fields.
# demographics carry provenance_layer + source_refs (references/schemas/README.md) and each PS text is bound
# to the source line it cites — mk21 writes that synthetic source file into every case.
DEMO='"demographics":{"sex":null,"age":60,"age_as_of":"2030-01-10","performance_status_verbatim":[{"text":"PS=1","as_of":"2030-01-10","scale_label":"PS","source_ref":"03_clinical_notes/outpatient_notes/a.md#L3"}],"provenance_layer":"source_reported","source_refs":["03_clinical_notes/outpatient_notes/a.md#L3"]}'
R21_FLAG='{"id":"RF-1","category":"cross_source_conflict","affected_field":"diagnosis.stage","current_source_values":[],"issue":"x","resolution_status":"unresolved","severity":"red","kind":"conflict"}'
# latest_status is required on a current archive (patient-profile-schema.md): {regimen: null, …} when nothing is
# ongoing — every current-archive case below carries it unless the case is about it
LS_NONE='"latest_status":{"regimen":null,"response":null,"ecog":null,"as_of":null,"status_basis":null,"source_refs":[]}'
R21_TOP='"patient_code":"PT-A6","schema_version":"2.1","documentation_coverage":{},"latest_source_date":"2030-01-15","days_since_latest":5,"as_of_run_date":"2030-01-20"'

mk21() {  # name, profile-json, readiness-json
  mkdir "$tmp/$1"; echo "$2" > "$tmp/$1/profile.json"; echo "$3" > "$tmp/$1/readiness.json"
  mkdir -p "$tmp/$1/03_clinical_notes/outpatient_notes"
  printf 'SOURCE: raw/s001.jpg\n\n一般状况：PS=1。\n' > "$tmp/$1/03_clinical_notes/outpatient_notes/a.md"
}
mk21 r21_ok "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" "{$R21_TOP,\"review_flags\":[$R21_FLAG]}"
run_case "readiness 2.1 + profile demographics" pass "$tmp/r21_ok"
mk21 r21_noflagsev "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" \
  "{$R21_TOP,\"review_flags\":[$(echo "$R21_FLAG" | sed 's/,"severity":"red"//')]}"
run_case "readiness 2.1 flag without severity rejected" fail "$tmp/r21_noflagsev"
mk21 r21_badkind "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" \
  "{$R21_TOP,\"review_flags\":[$(echo "$R21_FLAG" | sed 's/"kind":"conflict"/"kind":"strikethrough"/')]}"
run_case "readiness flag kind outside enum rejected" fail "$tmp/r21_badkind"
mk21 r21_norecency "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" \
  "{\"patient_code\":\"PT-A6\",\"schema_version\":\"2.1\",\"documentation_coverage\":{},\"review_flags\":[]}"
run_case "readiness 2.1 without recency fields rejected" fail "$tmp/r21_norecency"
mk21 r21_stale "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" \
  "{$(echo "$R21_TOP" | sed 's/"days_since_latest":5/"days_since_latest":27/'),\"review_flags\":[]}"
run_case "27 days without a day-count warning rejected" fail "$tmp/r21_stale"
mk21 r21_stale_warned "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" \
  "{$(echo "$R21_TOP" | sed 's/"days_since_latest":5/"days_since_latest":27/'),\"warnings\":[\"资料距本次整理已 27 天\"],\"review_flags\":[]}"
run_case "27 days with the day-count warning accepted" pass "$tmp/r21_stale_warned"
mk21 r3 "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" \
  "{\"patient_code\":\"PT-A6\",\"schema_version\":\"3\",\"documentation_coverage\":{},\"review_flags\":[]}"
run_case "unknown readiness version rejected" fail "$tmp/r3"
mk21 r21_nols "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "current archive without latest_status rejected (required; absent is not 'nothing ongoing')" fail "$tmp/r21_nols"
nols_out="$(bash "$SCRIPT" "$tmp/r21_nols" 2>&1 || true)"
if grep -q "ERROR: latest_status missing" <<<"$nols_out"; then
  pass=$((pass+1)); else echo "FAIL: a current archive without latest_status must print ERROR: latest_status missing" >&2; fail=$((fail+1)); fi
mk21 r21_lsnull "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},\"latest_status\":null,$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "current archive with latest_status null rejected (write {regimen: null, …})" fail "$tmp/r21_lsnull"
min_out="$(bash "$SCRIPT" "$tmp/minimal" 2>&1 || true)"
if grep -q "WARN: latest_status missing" <<<"$min_out"; then
  pass=$((pass+1)); else echo "FAIL: a legacy archive without latest_status must only WARN" >&2; fail=$((fail+1)); fi
mk21 r21_nodemo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A6","summary":{}}' "{$R21_TOP,\"review_flags\":[]}"
run_case "current archive without profile.demographics rejected" fail "$tmp/r21_nodemo"
mk21 r21_age_noasof "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/"age_as_of":"2030-01-10"/"age_as_of":null/')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "age without age_as_of rejected" fail "$tmp/r21_age_noasof"
mk21 r21_ps_scale "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/"scale_label":"PS"/"scale_label":"ECOG-from-PS"/')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "converted PS scale label rejected" fail "$tmp/r21_ps_scale"
mk21 r21_mismatch "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
echo '{"demographics":{"sex":null,"age":61,"age_as_of":"2030-01-10","performance_status_verbatim":[]}}' > "$tmp/r21_mismatch/patient_summary.json"
run_case "profile demographics ≠ patient_summary rejected" fail "$tmp/r21_mismatch"
mk21 r21_ps_text "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/"text":"PS=1"/"text":"PS=0"/')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "PS text that is not on the cited source line rejected" fail "$tmp/r21_ps_text"
mk21 r21_noprov "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/,"provenance_layer":"source_reported"//')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "demographics without provenance_layer rejected" fail "$tmp/r21_noprov"
mk21 r21_norefs "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/"source_refs":\["03_clinical_notes\/outpatient_notes\/a.md#L3"\]/"source_refs":[]/')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "filled demographics with empty source_refs rejected" fail "$tmp/r21_norefs"
# profile.latest_status {regimen, as_of} (phase2 §5.7; read by SMTB as the current-status row)
LS_OK='"latest_status":{"regimen":"示例方案B","response":null,"ecog":null,"as_of":"2030-01-10","source_refs":["03_clinical_notes/outpatient_notes/a.md#L3"]}'
mk21 r21_ls_ok "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_OK,$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "latest_status regimen + ISO as_of accepted" pass "$tmp/r21_ls_ok"
mk21 r21_ls_month "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"as_of":"2030-01-10"/"as_of":"2030年1月"/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "latest_status.as_of not YYYY-MM-DD rejected" fail "$tmp/r21_ls_month"
mk21 r21_ls_nodate "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"as_of":"2030-01-10"/"as_of":null/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "latest_status regimen without as_of rejected" fail "$tmp/r21_ls_nodate"
mk21 r21_ls_list "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"regimen":"示例方案B"/"regimen":["示例方案B"]/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "latest_status.regimen as a list rejected" fail "$tmp/r21_ls_list"
# B7: latest_status.status_basis (optional) says what the snapshot rests on; B3: as_of may be null
# only for an undated family/patient statement (status_basis patient_reported)
mk21 r21_ls_basis "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"as_of":"2030-01-10"/"as_of":"2030-01-10","status_basis":"order_or_indication_only"/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "latest_status.status_basis from the episode enum accepted" pass "$tmp/r21_ls_basis"
mk21 r21_ls_badbasis "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"as_of":"2030-01-10"/"as_of":"2030-01-10","status_basis":"imaging_request"/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "latest_status.status_basis outside the enum rejected" fail "$tmp/r21_ls_badbasis"
mk21 r21_ls_undated "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"as_of":"2030-01-10"/"as_of":null,"status_basis":"patient_reported"/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "undated self-report: regimen + null as_of + status_basis patient_reported accepted" pass "$tmp/r21_ls_undated"
mk21 r21_ls_undated_clin "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$(echo "$LS_OK" | sed 's/"as_of":"2030-01-10"/"as_of":null,"status_basis":"clinician_note_current"/'),$DEMO}" "{$R21_TOP,\"review_flags\":[]}"
run_case "regimen + null as_of with a clinician-note basis rejected" fail "$tmp/r21_ls_undated_clin"
# D8: PS items may carry provenance_layer (optional; a digest statement is prior_archive)
mk21 r21_ps_prov "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/"scale_label":"PS",/"scale_label":"PS","provenance_layer":"prior_archive",/')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "PS item provenance_layer prior_archive accepted" pass "$tmp/r21_ps_prov"
mk21 r21_ps_badprov "{\"schema\":\"cancer_buddy_profile_v3\",\"patient_code\":\"PT-A6\",\"summary\":{},$LS_NONE,$(echo "$DEMO" | sed 's/"scale_label":"PS",/"scale_label":"PS","provenance_layer":"old_archive",/')}" "{$R21_TOP,\"review_flags\":[]}"
run_case "PS item provenance_layer outside the enum rejected" fail "$tmp/r21_ps_badprov"
mkdir "$tmp/ls_legacy"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A7","summary":{},"latest_status":{"regimen":"示例方案B","as_of":"2030年1月"}}' > "$tmp/ls_legacy/profile.json"
run_case "legacy archive: odd latest_status.as_of only WARNs" pass "$tmp/ls_legacy"
# organize_meta.json marks the archive current exactly like validate_structured_outputs:
# a readiness "2" archive WITH organize_meta.json must carry profile.demographics.
mk21 meta_current '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A6","summary":{}}' \
  '{"patient_code":"PT-A6","schema_version":"2","documentation_coverage":{},"review_flags":[]}'
run_case "readiness 2 without organize_meta.json: missing demographics only WARNs" pass "$tmp/meta_current"
echo '{"skill":"cancer-buddy-organize"}' > "$tmp/meta_current/organize_meta.json"
run_case "organize_meta.json ⇒ current: missing demographics rejected" fail "$tmp/meta_current"
meta_out="$(bash "$SCRIPT" "$tmp/meta_current" 2>&1 || true)"
if grep -q "ERROR: profile.demographics missing" <<<"$meta_out"; then
  pass=$((pass+1)); else echo "FAIL: organize_meta.json must make the missing demographics an ERROR" >&2; fail=$((fail+1)); fi
if grep -q "ERROR: mixed-version archive: readiness.schema_version '2'" <<<"$meta_out"; then
  pass=$((pass+1)); else echo "FAIL: readiness 2 + organize_meta.json must be a mixed-version ERROR" >&2; fail=$((fail+1)); fi
if bash "$SCRIPT" "$tmp/readiness_ok" 2>&1 >/dev/null | grep -q "WARN: readiness.schema_version '2' is legacy"; then
  pass=$((pass+1)); else echo "FAIL: legacy readiness 2 must print a WARN" >&2; fail=$((fail+1)); fi

echo "validate-profile-schema: pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
