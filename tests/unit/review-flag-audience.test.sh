#!/usr/bin/env bash
# tests/unit/review-flag-audience.test.sh — organize v3.
#   gate_review_flag_audience   every flag says who it is for; the four QC categories
#                               are pinned to internal_qc and cannot claim a clinician
#   gate_projection_coverage    every inventoried source is accounted for, and the
#                               summary agrees with its own rows
#
# Why audience is a hard gate: before it, visit-prep rendered every review flag as
# 「请医生确认」, so a decimal-point disagreement and a genuine cross-source
# contradiction looked identical to a family — and the real ones drowned.
#
# Why projection_coverage is a hard gate: "best effort" projection with no coverage
# number is indistinguishable from a complete one. A report can be fully transcribed,
# correctly filed, and contribute zero structured facts with nothing anywhere saying so.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

run_gate() {  # <gate_fn> <patient_dir>
  set +e
  out="$(python3 - "$ORG" "$1" "$2" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
getattr(v, sys.argv[2])(pathlib.Path(sys.argv[3]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# schema-validate readiness.json on its own, so a shape breach is visible as such.
# `warnings` is collected too: fix spec A13 routes a legacy file to a relaxed schema
# plus a WARN, and a test that only looked at `errors` could not tell "validated and
# clean" apart from "not validated at all".
schema_check() {  # <patient_dir>
  set +e
  sout="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, json, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
pd = pathlib.Path(sys.argv[2])
data = json.loads((pd / "readiness.json").read_text(encoding="utf-8"))
errs, warns = [], []
v.validate_doc_schema("readiness.json", data, "readiness.schema.json", errs, warns)
for w in warns:
    print("WARN " + w)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  src=$?
  set -e
}

# two inventory sources: one ordinary, one unreadable — the unreadable one is exactly
# what a coverage number would otherwise hide.
mk_inventory() {  # <dir>
  mkdir -p "$1/07_检验/血常规" "$1/15_未分类资料/肠道菌群检测" "$1/raw/incoming"
  : > "$1/07_检验/血常规/2026-03-15_血常规.md"
  : > "$1/15_未分类资料/肠道菌群检测/report.md"
  cat > "$1/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.pdf",
   "raw_path":"raw/incoming/upload-001.pdf","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab","text_layer_kind":"born_digital",
   "sidecar_path":"07_检验/血常规/2026-03-15_血常规.md","bucket_path":"07_检验/血常规",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"pdftotext","version":"24.04","raw_output_ref":null,"llm_role":"none"},
   "high_risk_review_status":"not_applicable","adapter":"pdf_pages","persist":true},
  {"file_id":"f2","source_id":"s2","original_path":"upload-002.pdf",
   "raw_path":"raw/incoming/upload-002.pdf","page_range":null,
   "kind":"novel","doc_kind":"novel:肠道菌群检测","clinical_class":"unknown",
   "novel_reason":"肠道菌群丰度报告，14 个固定域都没有对应类型","text_layer_kind":"absent",
   "sidecar_path":"15_未分类资料/肠道菌群检测/report.md","bucket_path":"15_未分类资料/肠道菌群检测",
   "modality":"text","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,"llm_role":"primary_transcription"},
   "high_risk_review_status":"needs_human_review","adapter":"pdf_pages","persist":true},
  {"file_id":"f3","source_id":"s3","original_path":"upload-003.jpg",
   "raw_path":"raw/incoming/upload-003.jpg","page_range":null,
   "kind":"unreadable","doc_kind":"未知","clinical_class":"unknown","text_layer_kind":"absent",
   "sidecar_path":"15_未分类资料/肠道菌群检测/report.md","bucket_path":"15_未分类资料/肠道菌群检测",
   "modality":"image","read_mode":"stub_unreadable",
   "extractor_provenance":{"engine":"none","version":null,"raw_output_ref":null,"llm_role":"none"},
   "high_risk_review_status":"not_applicable","adapter":"unsupported_stub","persist":true} ]}
EOF
}

# readiness.json builder: <dir> <flags-json> <coverage-json>
#
# schema_version is "3" (fix spec A13), and that is load-bearing for this whole file.
# A readiness.json declaring "2" is routed to the RELAXED v2 schema — which predates
# review_flags[].audience — so every negative arm below would have passed against a
# schema that was never asked the question. The legacy branch gets its own explicit
# arm in section A4 instead of being the silent default here.
mk_readiness() {
  cat > "$1/readiness.json" <<EOF
{ "patient_code":"PT-0FA1","schema_version":"3",
  "generated_at":"2026-09-16T00:00:00Z",
  "documentation_coverage":{"pathology_report":"present"},
  $3
  "review_flags":$2 }
EOF
}

FULL_COVERAGE='"projection_coverage":{
    "per_source":[
      {"source_id":"s1","unprojected_field_classes":[]},
      {"source_id":"s2","unprojected_field_classes":["microbiome_abundances"],
       "note":"no pinned slot for microbiome abundances"},
      {"source_id":"s3","unprojected_field_classes":["all"],"note":"unreadable"}],
    "summary":{"sources_total":3,"sources_fully_projected":1,
               "novel_sources":1,"unreadable_sources":1}},'

# ===========================================================================
# A. review_flags[].audience
# ===========================================================================
echo "=== A. review_flags[].audience ==="

d="$tmp/flags"
mk_inventory "$d"

# A1. NEGATIVE — flag with no audience at all
mk_readiness "$d" '[
  {"id":"rf1","category":"source_conflict","affected_field":"诊断日期",
   "current_source_values":[{"value":"2026-03-15","source_ref":"07_检验/血常规/2026-03-15_血常规.md"}],
   "issue":"两份来源日期不一致","resolution_status":"unresolved"} ]' "$FULL_COVERAGE"
run_gate gate_review_flag_audience "$d"
[ "$rc" -eq 1 ] && ok "review flag with no audience → exit 1" || no "unlabelled flag accepted, rc=$rc"
echo "$out" | grep -q 'no usable audience' && ok "…error names the missing audience" \
  || no "wrong reason: $out"
echo "$out" | grep -q 'rendered to the family as a doctor action' \
  && ok "…error states the failure it prevents (an unlabelled flag reaches the family as 「请医生确认」)" \
  || no "consequence not stated: $out"
schema_check "$d"
[ "$src" -eq 1 ] && ok "…and readiness.schema.json rejects it too (audience is required)" \
  || no "schema accepted a flag with no audience"

# A2. NEGATIVE — transcription_disagreement claiming a clinician
mk_readiness "$d" '[
  {"id":"rf2","category":"transcription_disagreement","audience":"clinician",
   "affected_field":"白细胞计数",
   "current_source_values":[{"value":"3.21","source_ref":"07_检验/血常规/2026-03-15_血常规.md"},
                            {"value":"3.24","source_ref":"07_检验/血常规/2026-03-15_血常规.md"}],
   "issue":"视觉读数与文本层不一致","resolution_status":"unresolved"} ]' "$FULL_COVERAGE"
run_gate gate_review_flag_audience "$d"
[ "$rc" -eq 1 ] && ok "transcription_disagreement + audience=clinician → exit 1" \
  || no "QC category claimed a clinician and was accepted, rc=$rc"
echo "$out" | grep -q 'must be internal_qc' && ok "…error pins the category to internal_qc" \
  || no "wrong reason: $out"
echo "$out" | grep -q 'not a clinical decision' \
  && ok "…error explains why (it describes how the archive was READ)" || no "rationale absent: $out"

# A2b. the other three pinned categories behave the same way
for cat in ocr_artifact untrusted_content_marker pii_semantic_deferred; do
  mk_readiness "$d" "[
    {\"id\":\"rf-$cat\",\"category\":\"$cat\",\"audience\":\"clinician\",
     \"affected_field\":\"x\",\"current_source_values\":[],
     \"issue\":\"y\",\"resolution_status\":\"unresolved\"} ]" "$FULL_COVERAGE"
  run_gate gate_review_flag_audience "$d"
  [ "$rc" -eq 1 ] && ok "$cat + audience=clinician → exit 1" \
    || no "$cat wrongly allowed to claim a clinician, rc=$rc"
done

# A3. POSITIVE — a genuine cross-source clinical question MAY claim a clinician,
#     and QC noise correctly labelled internal_qc passes.
mk_readiness "$d" '[
  {"id":"rf3","category":"source_conflict","audience":"clinician","affected_field":"诊断日期",
   "current_source_values":[{"value":"2026-03-15","source_ref":"07_检验/血常规/2026-03-15_血常规.md"},
                            {"value":"2026-03-18","source_ref":"07_检验/血常规/2026-03-15_血常规.md"}],
   "issue":"两份来源日期不一致，需要医生确认以哪份为准","resolution_status":"unresolved"},
  {"id":"rf4","category":"transcription_disagreement","audience":"internal_qc",
   "affected_field":"白细胞计数",
   "current_source_values":[{"value":"3.21","source_ref":"07_检验/血常规/2026-03-15_血常规.md"}],
   "issue":"视觉读数与文本层差 0.03","resolution_status":"unresolved"} ]' "$FULL_COVERAGE"
run_gate gate_review_flag_audience "$d"
[ "$rc" -eq 0 ] && ok "source_conflict/clinician + transcription_disagreement/internal_qc → exit 0" \
  || no "correctly-labelled flags blocked: $out"
schema_check "$d"
[ "$src" -eq 0 ] && ok "…and the same readiness.json is schema-valid" \
  || no "schema rejected the positive fixture: $sout"

# ===========================================================================
# A4. the v3 legacy branch is a GRACE PERIOD, not a hole (fix spec A13)
# ===========================================================================
echo "=== A4. legacy readiness (schema_version 2) ==="

# The same unlabelled flag that section A1 rejects is READ, not rejected, when the file
# declares the pre-audience schema — because in schema 2 `audience` did not exist and
# failing it would be failing a file for not predicting the future. What must not happen
# is that the leniency stays invisible: the read emits a WARN naming the migration
# script, so "no errors" cannot be mistaken for "checked and clean".
dlegacy="$tmp/legacy_readiness"
mk_inventory "$dlegacy"
cat > "$dlegacy/readiness.json" <<'EOF'
{ "patient_code":"PT-0FA1","schema_version":"2",
  "generated_at":"2026-09-16T00:00:00Z",
  "documentation_coverage":{"pathology_report":"present"},
  "review_flags":[
    {"id":"rf1","category":"source_conflict","affected_field":"诊断日期",
     "current_source_values":[{"value":"2026-03-15","source_ref":"07_检验/血常规/2026-03-15_血常规.md"}],
     "issue":"两份来源日期不一致","resolution_status":"unresolved"}] }
EOF
schema_check "$dlegacy"
[ "$src" -eq 0 ] && ok "schema_version 2 + no audience → READ against the v2 shape, not failed" \
  || no "a legacy readiness.json was hard-failed instead of relaxed: $sout"
echo "$sout" | grep -q 'legacy_schema' \
  && ok "…and the relaxation is announced as a WARN, never silent" \
  || no "the legacy read produced no WARN: $sout"
echo "$sout" | grep -q 'migrate_v3_to_v4.py' \
  && ok "…the WARN names scripts/migrate_v3_to_v4.py (leniency is a grace period)" \
  || no "the WARN does not point at the migration: $sout"
echo "$sout" | grep -q 'audience' \
  && ok "…and says out loud that unlabelled flags are NOT being caught" \
  || no "the WARN does not say what is going unchecked: $sout"

# and the SAME file declaring "3" is failed — the escape hatch cannot be claimed by a
# current archive just by leaving the flag unlabelled
python3 - "$dlegacy/readiness.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["schema_version"] = "3"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF
schema_check "$dlegacy"
[ "$src" -eq 1 ] && ok "the same unlabelled flag declared schema_version 3 → schema violation" \
  || no "a v3 file bought the legacy relaxation, src=$src"

# ===========================================================================
# B. projection_coverage
# ===========================================================================
echo "=== B. projection_coverage ==="

GOOD_FLAGS='[
  {"id":"rf3","category":"source_conflict","audience":"clinician","affected_field":"诊断日期",
   "current_source_values":[],"issue":"两份来源日期不一致","resolution_status":"unresolved"} ]'

# B1. POSITIVE — every source accounted for, summary agrees with the rows
mk_readiness "$d" "$GOOD_FLAGS" "$FULL_COVERAGE"
run_gate gate_projection_coverage "$d"
[ "$rc" -eq 0 ] && ok "complete projection_coverage → exit 0" || no "valid coverage blocked: $out"

# B2. NEGATIVE — a source_id is missing from per_source
mk_readiness "$d" "$GOOD_FLAGS" '"projection_coverage":{
    "per_source":[
      {"source_id":"s1","unprojected_field_classes":[]},
      {"source_id":"s2","unprojected_field_classes":["microbiome_abundances"]}],
    "summary":{"sources_total":2,"sources_fully_projected":1,
               "novel_sources":1,"unreadable_sources":1}},'
run_gate gate_projection_coverage "$d"
[ "$rc" -eq 1 ] && ok "projection_coverage omitting an inventoried source → exit 1" \
  || no "missing source_id accepted, rc=$rc"
echo "$out" | grep -q 'omits source s3' && ok "…error names the omitted source (the unreadable one)" \
  || no "omitted source not named: $out"
echo "$out" | grep -q 'ESPECIALLY novel and unreadable' \
  && ok "…error says which sources a coverage number would otherwise hide" \
  || no "rationale absent: $out"

# B3. NEGATIVE — the summary disagrees with its own rows
mk_readiness "$d" "$GOOD_FLAGS" '"projection_coverage":{
    "per_source":[
      {"source_id":"s1","unprojected_field_classes":[]},
      {"source_id":"s2","unprojected_field_classes":["microbiome_abundances"]},
      {"source_id":"s3","unprojected_field_classes":["all"]}],
    "summary":{"sources_total":3,"sources_fully_projected":3,
               "novel_sources":1,"unreadable_sources":1}},'
run_gate gate_projection_coverage "$d"
[ "$rc" -eq 1 ] && ok "summary.sources_fully_projected disagreeing with the rows → exit 1" \
  || no "self-contradicting summary accepted, rc=$rc"
echo "$out" | grep -q 'sources_fully_projected is 3 but the data says 1' \
  && ok "…error prints both the claimed and the real count" || no "counts not printed: $out"
echo "$out" | grep -q 'worse than no summary' \
  && ok "…error states why a wrong summary is worse than none" || no "rationale absent: $out"

# B3b. novel/unreadable counts are checked against the inventory, not self-reported
mk_readiness "$d" "$GOOD_FLAGS" '"projection_coverage":{
    "per_source":[
      {"source_id":"s1","unprojected_field_classes":[]},
      {"source_id":"s2","unprojected_field_classes":["microbiome_abundances"]},
      {"source_id":"s3","unprojected_field_classes":["all"]}],
    "summary":{"sources_total":3,"sources_fully_projected":1,
               "novel_sources":0,"unreadable_sources":0}},'
run_gate gate_projection_coverage "$d"
[ "$rc" -eq 1 ] && ok "novel/unreadable counts zeroed out → exit 1" \
  || no "self-reported novel/unreadable counts were trusted, rc=$rc"
echo "$out" | grep -q 'unreadable_sources is 0 but the data says 1' \
  && ok "…error catches the zeroed unreadable count" || no "unreadable count not checked: $out"

# B4. NEGATIVE — projection_coverage absent entirely
mk_readiness "$d" "$GOOD_FLAGS" ''
run_gate gate_projection_coverage "$d"
[ "$rc" -eq 1 ] && ok "projection_coverage missing → exit 1" || no "absent coverage accepted, rc=$rc"
echo "$out" | grep -q 'indistinguishable from a complete one' \
  && ok "…error states why absence cannot be silent" || no "rationale absent: $out"

# B5. NEGATIVE — a coverage row for a source that is not in the inventory
mk_readiness "$d" "$GOOD_FLAGS" '"projection_coverage":{
    "per_source":[
      {"source_id":"s1","unprojected_field_classes":[]},
      {"source_id":"s2","unprojected_field_classes":["microbiome_abundances"]},
      {"source_id":"s3","unprojected_field_classes":["all"]},
      {"source_id":"s9","unprojected_field_classes":[]}],
    "summary":{"sources_total":4,"sources_fully_projected":2,
               "novel_sources":1,"unreadable_sources":1}},'
run_gate gate_projection_coverage "$d"
[ "$rc" -eq 1 ] && ok "coverage row for an uninventoried source → exit 1" \
  || no "phantom coverage row accepted, rc=$rc"
echo "$out" | grep -q 'which has no row in source_inventory.json' \
  && ok "…error names the phantom source" || no "phantom source not named: $out"

# ---------------------------------------------------------------------------
echo
echo "== review-flag-audience: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
