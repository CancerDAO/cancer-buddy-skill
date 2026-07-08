#!/usr/bin/env bash
# Unit tests for the CB-P0-1 bucket-taxonomy enforcement gate + CB-P0-2 NGS
# completeness floor in validate_structured_outputs.py.
#   - gate_bucket_taxonomy: pinned NN_ domain + typed sub-bucket slugs (bucket_taxonomy.json)
#   - gate_ngs_completeness: NGS source present but molecular.json arrays empty → WARN
# Uses synthetic fixtures reproducing patient 023's real classifier drift
# (deterministic, no LLM) so the assertions are stable.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap "rm -rf $tmp" EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

# helper: run gate_bucket_taxonomy directly, print each collected error on a line
run_bucket_gate() {
  python3 - "$ORG" "$1" <<'PY'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_bucket_taxonomy(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
PY
}

# helper: run gate_ngs_completeness directly, print each collected warning
run_ngs_floor() {
  python3 - "$ORG" "$1" <<'PY'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
warns = []
v.gate_ngs_completeness(pathlib.Path(sys.argv[2]), warns)
for w in warns:
    print(w)
PY
}

# ===========================================================================
# 1. DRIFT fixture — reproduce patient 023's echoed source-folder names.
#    Every one of these 4 dirs must be named as a violation.
# ===========================================================================
d="$tmp/drift"
mkdir -p "$d/06_分子与组学/基因检测" \
         "$d/11_不良反应" \
         "$d/13_其他专科检查" \
         "$d/04_诊断与分期/影像报告" \
         "$d/raw" "$d/ocr"   # infra dirs must NOT trip the gate
: > "$d/06_分子与组学/基因检测/x.md"
: > "$d/04_诊断与分期/影像报告/y.md"

out="$(run_bucket_gate "$d")"
echo "----- drift fixture gate output -----"
echo "$out"
echo "-------------------------------------"

# sub-bucket drift under a valid domain
echo "$out" | grep -q '06_分子与组学/基因检测' && ok || no "should flag 06_分子与组学/基因检测 (should be NGS报告)"
echo "$out" | grep -q '04_诊断与分期/影像报告' && ok || no "should flag 04_诊断与分期/影像报告 (imaging → 05_影像)"
# top-level off-taxonomy domain slugs (echoed source-folder numbering)
echo "$out" | grep -q "top-level dir '11_不良反应'" && ok || no "should flag top-level 11_不良反应"
echo "$out" | grep -q "11_会诊与转诊" && ok || no "should name expected pinned 11_ slug (11_会诊与转诊)"
echo "$out" | grep -q "top-level dir '13_其他专科检查'" && ok || no "should flag top-level 13_其他专科检查"
echo "$out" | grep -q "13_行政与财务" && ok || no "should name expected pinned 13_ slug (13_行政与财务)"
# infra dirs raw/ ocr/ must NOT be flagged
echo "$out" | grep -Eq "top-level dir '(raw|ocr)'" && no "infra raw/ocr must NOT be flagged" || ok
# there must be at least 4 violations collected
nviol="$(echo "$out" | grep -c 'bucket_taxonomy:')"
[ "$nviol" -ge 4 ] && ok || no "expected >=4 violations, got $nviol"

# full-script wiring: the drift dir must make the entrypoint exit nonzero AND
# print the bucket_taxonomy violations (proves gate is wired into main()).
if python3 "$VAL" "$d" >/dev/null 2>"$tmp/drift.err"; then
  no "full validate script should exit nonzero on drift fixture"
else ok; fi
grep -q 'bucket_taxonomy: 06_分子与组学/基因检测' "$tmp/drift.err" && ok || no "entrypoint should surface the bucket violation"

# ===========================================================================
# 2. CLEAN fixture — all pinned slugs → gate PASSES (0 violations).
# ===========================================================================
c="$tmp/clean"
mkdir -p "$c/06_分子与组学/NGS报告" \
         "$c/05_影像/CT" \
         "$c/03_病程与叙事文书/病程记录" \
         "$c/04_诊断与分期/其他" \
         "$c/99_无关文件/high_confidence" \
         "$c/14_患者自管补充/conversation_notes"
out="$(run_bucket_gate "$c")"
echo "----- clean fixture gate output -----"
echo "${out:-<none>}"
echo "-------------------------------------"
[ -z "$out" ] && ok || no "clean fixture should produce ZERO violations (got: $out)"

# 2b. CLEAN fixture, en-locale slugs → also PASSES
ce="$tmp/clean_en"
mkdir -p "$ce/06_molecular_omics/ngs" "$ce/05_imaging/CT" "$ce/03_clinical_notes/progress_notes"
out="$(run_bucket_gate "$ce")"
[ -z "$out" ] && ok || no "clean en-locale fixture should produce ZERO violations (got: $out)"

# ===========================================================================
# 3. NGS completeness floor — NGS source present but molecular.json PGx empty.
# ===========================================================================
n="$tmp/ngs_pgx_empty"
mkdir -p "$n/06_分子与组学/NGS报告"
: > "$n/06_分子与组学/NGS报告/2024-03-15_NGS报告.md"
cat > "$n/molecular.json" <<'EOF'
{ "patient_code":"PT-NGS01","schema_version":"1",
  "variants":[{"gene":"KRAS","variant":"p.G12C","vaf":0.31}],
  "germline":[{"gene":"BRCA2","variant":"c.5946delT","classification":"VUS"}],
  "pharmacogenomics":[] }
EOF
out="$(run_ngs_floor "$n")"
echo "----- ngs floor (PGx empty) output -----"
echo "$out"
echo "----------------------------------------"
echo "$out" | grep -q 'ngs_completeness' && ok || no "NGS floor should WARN when PGx empty"
echo "$out" | grep -q 'pharmacogenomics' && ok || no "NGS floor should name the empty pharmacogenomics field"

# floor is WARN-only: the full entrypoint must NOT fail solely on an empty PGx
# array (add the artifacts it needs so the OTHER gates pass, isolating the floor).
w="$tmp/ngs_warn_only"
mkdir -p "$w/06_分子与组学/NGS报告" "$w/raw/h"
: > "$w/06_分子与组学/NGS报告/rep.md"
: > "$w/raw/h/IMG.pdf"
cat > "$w/molecular.json" <<'EOF'
{ "patient_code":"PT-NGS02","schema_version":"1",
  "variants":[{"gene":"EGFR","variant":"p.L858R"}], "germline":[], "pharmacogenomics":[] }
EOF
cat > "$w/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v1","patient_dir":"patients/PT-NGS02","files":[
  {"source_id":"s1","raw_path":"raw/h/IMG.pdf","sidecar_path":"06_分子与组学/NGS报告/rep.md","bucket_path":"06_分子与组学/NGS报告"} ]}
EOF
python3 "$VAL" "$w" >/dev/null 2>"$tmp/warn.err" && rc=0 || rc=$?
# it may still exit 1 for other reasons, but the NGS floor line must be a WARN, not an ERROR
grep -q 'WARN: ngs_completeness' "$tmp/warn.err" && ok || no "NGS floor must print as WARN in entrypoint"
grep -q 'ERROR: ngs_completeness' "$tmp/warn.err" && no "NGS floor must NOT be an ERROR (would false-block)" || ok

# negative: molecular.json fully populated → floor silent
f="$tmp/ngs_full"
mkdir -p "$f/06_分子与组学/NGS报告"
: > "$f/06_分子与组学/NGS报告/rep.md"
cat > "$f/molecular.json" <<'EOF'
{ "patient_code":"PT-NGS03","schema_version":"1",
  "variants":[{"gene":"KRAS"}], "germline":[{"gene":"TP53"}],
  "pharmacogenomics":[{"gene":"DPYD","result":"正常代谢"}] }
EOF
out="$(run_ngs_floor "$f")"
[ -z "$out" ] && ok || no "fully-populated molecular.json should NOT trip the floor (got: $out)"

# negative: NO NGS source → floor silent even with empty molecular.json
g="$tmp/no_ngs"
mkdir -p "$g/07_检验/血常规"
cat > "$g/molecular.json" <<'EOF'
{ "patient_code":"PT-NGS04","schema_version":"1","variants":[],"germline":[],"pharmacogenomics":[] }
EOF
out="$(run_ngs_floor "$g")"
[ -z "$out" ] && ok || no "no NGS source → floor must stay silent (got: $out)"

# ---------------------------------------------------------------------------
echo "bucket-taxonomy-gate: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
