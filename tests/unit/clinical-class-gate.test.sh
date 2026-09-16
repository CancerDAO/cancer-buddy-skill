#!/usr/bin/env bash
# tests/unit/clinical-class-gate.test.sh — organize v3, gate_clinical_class_completeness.
#
# THE RULE: the molecular/lab completeness floors key off the inventory's own
# `clinical_class`, NOT off the bucket path. Open-world filing must not become the
# cheap door around the invariants closed-world filing enforces.
#
#   kind=novel + clinical_class=molecular  ⇒ molecular.json must exist AND be non-empty.
#       A novel gene panel is the exact case domain 15 was added for. If it can be
#       archived while molecular.json stays empty, the archive reads downstream as
#       "no molecular data exists" and every consumer inherits that lie.
#   clinical_class=lab                     ⇒ the numbers must have landed somewhere:
#       a labs.json value citing that source's sidecar, or a lab entry in
#       extracted_fields.json carrying unit + source_reported_text.
#   kind=unreadable                        ⇒ exempt (nothing could be lifted), but not
#       forgiven — gate_projection_coverage requires it to be declared there.
#
# Every case asserts the gate's exit code, not only its message.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

gate() {  # <patient_dir>  → $out (errors), $rc (0 clean / 1 blocked)
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_clinical_class_completeness(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# one inventory row, fully schema-shaped so the fixture is a real archive row
inv_row() {  # <kind> <clinical_class> <sidecar_path> [extra json]
  cat <<EOF
{"file_id":"f1","source_id":"s1","original_path":"upload-001.pdf",
 "raw_path":"raw/incoming/upload-001.pdf","page_range":null,
 "kind":"$1","doc_kind":"novel:肠道菌群检测","clinical_class":"$2",
 "novel_reason":"报告是肠道菌群丰度检测，14 个固定域都没有对应类型",
 "text_layer_kind":"absent","sidecar_path":"$3","bucket_path":"$(dirname "$3")",
 "modality":"text","read_mode":"model_vision_primary",
 "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                         "llm_role":"primary_transcription"},
 "high_risk_review_status":"needs_human_review","adapter":"pdf_pages","persist":true$4}
EOF
}

write_inv() {  # <patient_dir> <row-json>
  cat > "$1/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[ $2 ] }
EOF
}

# ===========================================================================
# A. novel + clinical_class=molecular → molecular.json floor
# ===========================================================================
echo "=== A. novel molecular source vs molecular.json ==="

# A1. molecular.json MISSING entirely
d="$tmp/mol_missing"
mkdir -p "$d/15_未分类资料/肠道菌群检测" "$d/raw/incoming"
: > "$d/15_未分类资料/肠道菌群检测/report.md"
write_inv "$d" "$(inv_row novel molecular '15_未分类资料/肠道菌群检测/report.md' '')"
gate "$d"
[ "$rc" -eq 1 ] && ok "novel molecular + no molecular.json → exit 1" \
  || no "missing molecular.json must block, got rc=$rc"
echo "$out" | grep -q 'clinical_class: s1' && ok "…error names the offending source_id" \
  || no "error does not name the source: $out"
echo "$out" | grep -q 'does not exist' && ok "…error says molecular.json does not exist" \
  || no "wrong reason: $out"

# A2. molecular.json present but every array empty — the quiet version of the same lie
cat > "$d/molecular.json" <<'EOF'
{ "patient_code":"PT-CC01","schema_version":"2","report_id":null,
  "variants":[], "germline":[], "pharmacogenomics":[] }
EOF
gate "$d"
[ "$rc" -eq 1 ] && ok "novel molecular + EMPTY molecular.json → exit 1" \
  || no "empty molecular.json must block, got rc=$rc"
echo "$out" | grep -q 'no variants, germline or pharmacogenomics' \
  && ok "…error names the three empty arrays" || no "wrong reason: $out"
echo "$out" | grep -q "reads downstream as" \
  && ok "…error states the downstream consequence" || no "consequence not stated: $out"

# A3. POSITIVE — molecular.json populated from the novel report's own table
cat > "$d/molecular.json" <<'EOF'
{ "patient_code":"PT-CC01","schema_version":"2","report_id":"NGS-2026-0315",
  "variants":[{"gene":"KRAS","variant":"p.G12C","source_refs":["15_x"]}],
  "germline":[], "pharmacogenomics":[] }
EOF
gate "$d"
[ "$rc" -eq 0 ] && ok "novel molecular + populated molecular.json → exit 0" \
  || no "populated molecular.json still blocked: $out"

# A4. the floor is keyed to clinical_class, NOT to the bucket path: the same row
#     filed under the pinned NGS bucket behaves identically.
d2="$tmp/mol_pinned_path"
mkdir -p "$d2/06_分子与组学/NGS报告" "$d2/raw/incoming"
: > "$d2/06_分子与组学/NGS报告/rep.md"
write_inv "$d2" "$(inv_row novel molecular '06_分子与组学/NGS报告/rep.md' '')"
gate "$d2"
[ "$rc" -eq 1 ] && ok "a novel molecular row in a PINNED bucket trips the same floor (path is irrelevant)" \
  || no "floor keyed off the path instead of clinical_class, rc=$rc"

# A5. kind=unreadable is exempt — nothing could be lifted from it
d3="$tmp/mol_unreadable"
mkdir -p "$d3/15_未分类资料/肠道菌群检测" "$d3/raw/incoming"
: > "$d3/15_未分类资料/肠道菌群检测/report.md"
write_inv "$d3" "$(inv_row unreadable molecular '15_未分类资料/肠道菌群检测/report.md' '')"
gate "$d3"
[ "$rc" -eq 0 ] && ok "kind=unreadable is exempt from the molecular floor" \
  || no "unreadable source wrongly tripped the molecular floor: $out"

# ===========================================================================
# B. clinical_class=lab → the values must have landed somewhere
# ===========================================================================
echo "=== B. lab source vs labs.json / extracted_fields.json ==="

mk_lab_fixture() {  # <dir>
  mkdir -p "$1/15_未分类资料/肠道菌群检测" "$1/raw/incoming"
  : > "$1/15_未分类资料/肠道菌群检测/report.md"
  write_inv "$1" "$(inv_row novel lab '15_未分类资料/肠道菌群检测/report.md' '')"
}

# B1. NEGATIVE — labs.json does not cite it and extracted_fields.json has no lab entry
d="$tmp/lab_lost"
mk_lab_fixture "$d"
cat > "$d/labs.json" <<'EOF'
{ "patient_code":"PT-CC02","schema_version":"2","panels":[] }
EOF
gate "$d"
[ "$rc" -eq 1 ] && ok "lab source with nowhere to land → exit 1" \
  || no "lost lab values must block, got rc=$rc"
echo "$out" | grep -q 'read and then lost' && ok "…error says the results were read and then lost" \
  || no "wrong reason: $out"
echo "$out" | grep -q 'source_reported_text' \
  && ok "…error names the two legal landing places and their floors" \
  || no "error does not describe the remedy: $out"

# B1b. no labs.json at all is the same failure
rm -f "$d/labs.json"
gate "$d"
[ "$rc" -eq 1 ] && ok "lab source + no labs.json at all → exit 1" \
  || no "absent labs.json must block a lab-class source, got rc=$rc"

# B2. POSITIVE — an extracted_fields lab entry with unit + source_reported_text
d="$tmp/lab_open_ok"
mk_lab_fixture "$d"
cat > "$d/extracted_fields.json" <<'EOF'
{ "schema_version":"1","patient_code":"PT-CC02","entries":[
  {"source_id":"s1","page":1,"doc_kind":"novel:肠道菌群检测","clinical_class":"lab",
   "label":"双歧杆菌属相对丰度","value":"4.7","unit":"%",
   "source_reported_text":"双歧杆菌属 4.7%（参考 2.0-8.0%）",
   "reference_range":"2.0-8.0%",
   "open_ref":{"source_id":"s1","page":1,"bbox":[0.12,0.33,0.47,0.36]},
   "verification_status":"unverified"} ]}
EOF
gate "$d"
[ "$rc" -eq 0 ] && ok "lab source projected into extracted_fields (unit + verbatim text) → exit 0" \
  || no "valid open lab projection still blocked: $out"

# B3. NEGATIVE — the same entry with the unit stripped. A unitless laboratory
#     number is uninterpretable; filing it openly must not be cheaper than filing
#     it in labs.json, so gate_extracted_fields must reject it.
d="$tmp/lab_open_nounit"
mk_lab_fixture "$d"
cat > "$d/extracted_fields.json" <<'EOF'
{ "schema_version":"1","patient_code":"PT-CC02","entries":[
  {"source_id":"s1","page":1,"doc_kind":"novel:肠道菌群检测","clinical_class":"lab",
   "label":"双歧杆菌属相对丰度","value":"4.7",
   "source_reported_text":"双歧杆菌属 4.7%（参考 2.0-8.0%）",
   "open_ref":{"source_id":"s1","page":1,"bbox":[0.12,0.33,0.47,0.36]},
   "verification_status":"unverified"} ]}
EOF
set +e
ef_out="$(python3 - "$ORG" "$d" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_extracted_fields(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
ef_rc=$?
set -e
[ "$ef_rc" -eq 1 ] && ok "open lab entry with NO unit → exit 1" \
  || no "unitless open lab entry accepted, rc=$ef_rc"
echo "$ef_out" | grep -q 'no unit' && ok "…error names the missing unit" \
  || no "missing-unit error not raised: $ef_out"
echo "$ef_out" | grep -q 'uninterpretable' \
  && ok "…error states why a unitless lab number is not a fact" || no "rationale absent: $ef_out"

# B4. POSITIVE — landing in labs.json instead, via a source_ref to the sidecar
d="$tmp/lab_labsjson_ok"
mkdir -p "$d/07_检验/血常规" "$d/raw/incoming"
: > "$d/07_检验/血常规/2026-03-15_血常规.md"
write_inv "$d" "$(inv_row known lab '07_检验/血常规/2026-03-15_血常规.md' '')"
cat > "$d/labs.json" <<'EOF'
{ "patient_code":"PT-CC03","schema_version":"2","panels":[
  {"analyte":"白细胞计数","values":[
    {"date":"2026-03-15","value":3.21,"raw_value":"3.21","unit":"10^9/L",
     "reference_range":"3.50-9.50","report_flag":"L","critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "source_refs":["07_检验/血常规/2026-03-15_血常规.md"]}]} ]}
EOF
gate "$d"
[ "$rc" -eq 0 ] && ok "lab source cited by labs.json → exit 0" \
  || no "labs.json landing still blocked: $out"

# B5. NEGATIVE — labs.json exists but cites a DIFFERENT sidecar. Coverage is
#     per-source; a populated labs.json is not a blanket receipt.
cat > "$d/labs.json" <<'EOF'
{ "patient_code":"PT-CC03","schema_version":"2","panels":[
  {"analyte":"白细胞计数","values":[
    {"date":"2026-03-15","value":3.21,"raw_value":"3.21","unit":"10^9/L",
     "reference_range":"3.50-9.50","report_flag":"L","critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "source_refs":["07_检验/血常规/SOMEONE_ELSE.md"]}]} ]}
EOF
gate "$d"
[ "$rc" -eq 1 ] && ok "labs.json citing a different sidecar does NOT cover this source" \
  || no "per-source coverage degraded into a blanket receipt, rc=$rc"

# B6. a non-lab, non-molecular class is untouched by these floors
d="$tmp/narrative_ok"
mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
: > "$d/03_病程与叙事文书/出院小结/2026-03-15.md"
write_inv "$d" "$(inv_row known narrative '03_病程与叙事文书/出院小结/2026-03-15.md' '')"
gate "$d"
[ "$rc" -eq 0 ] && ok "clinical_class=narrative trips neither floor" \
  || no "narrative source wrongly blocked: $out"

# ---------------------------------------------------------------------------
echo
echo "== clinical-class-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
