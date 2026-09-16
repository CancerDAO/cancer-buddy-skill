#!/usr/bin/env bash
# tests/unit/numeric-integrity.test.sh — gate_numeric_integrity (labs.json).
#
# The one numeric check that needs no clinical knowledge at all: the normalized
# `value` must still be findable in the source-reported `raw_value` it was derived
# from. Nothing here compares a value with a threshold, calculates an abnormal flag,
# or decides whether a number is plausible for a human — those are clinical
# judgements this gate is forbidden to make. It only asserts that normalization did
# not invent a number.
#
# Why it earns its place: the single recorded accuracy data point from a real run was
# a page of phantom characters and a misread date. A dropped decimal point
# ("12.4" → "124") or a swapped digit survives every schema, every anchor check and
# every PII scan, because the JSON stays perfectly well-formed. Keeping raw_value
# beside value is only worth the disk space if something actually compares them.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

gate() {  # <patient_dir>
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_numeric_integrity(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# one labs.json value row with everything the source-shape floor requires, so the
# ONLY thing under test is the numeric relationship.
labs() {  # <dir> <value-json> <raw_value-json> <unit-json>
  local d="$1"
  mkdir -p "$d"
  cat > "$d/labs.json" <<EOF
{ "patient_code":"PT-0E11","schema_version":"2","panels":[
  {"analyte":"癌胚抗原 CEA","values":[
    {"date":"2026-03-15","value":$2,"raw_value":$3,"unit":$4,
     "reference_range":"0.00-5.00","report_flag":null,"critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "source_refs":["07_检验/肿瘤标志物/2026-03-15_CEA.md"]}]} ]}
EOF
}

# ===========================================================================
# A. NEGATIVE — normalization invented a number
# ===========================================================================
echo "=== A. value not findable in its own raw_value ==="

d="$tmp/dropped_point"
labs "$d" '11.2' '"112"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 1 ] && ok "value 11.2 vs raw_value \"112\" → exit 1" \
  || no "invented number accepted, rc=$rc"
echo "$out" | grep -q 'numeric_integrity' && ok "…flagged by gate_numeric_integrity" \
  || no "wrong gate reported it: $out"
echo "$out" | grep -q 'does not appear in its own source-reported raw_value' \
  && ok "…error states the relationship that broke" || no "wrong reason: $out"
echo "$out" | grep -q 'must not introduce a number the source never printed' \
  && ok "…error states the rule (keep the source value; conversions are an additive layer)" \
  || no "rule not stated: $out"

# the mirror case: a swapped digit
d="$tmp/swapped_digit"
labs "$d" '25.8' '"25.3"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 1 ] && ok "swapped digit (25.8 vs \"25.3\") → exit 1" || no "swapped digit accepted, rc=$rc"

# ===========================================================================
# B. NEGATIVE — a blank unit defeats the rule it pretends to satisfy
# ===========================================================================
echo "=== B. unit present but blank ==="

d="$tmp/blank_unit"
labs "$d" '25.3' '"25.3"' '""'
gate "$d"
[ "$rc" -eq 1 ] && ok "unit: \"\" → exit 1" || no "blank unit accepted, rc=$rc"
echo "$out" | grep -q 'unit is present but blank' && ok "…error names the blank unit" \
  || no "wrong reason: $out"
echo "$out" | grep -q 'use null when the report prints no unit' \
  && ok "…error states the correct encoding for 'the report prints no unit'" \
  || no "remedy not stated: $out"

# whitespace-only is the same defect
d="$tmp/space_unit"
labs "$d" '25.3' '"25.3"' '"   "'
gate "$d"
[ "$rc" -eq 1 ] && ok "unit: \"   \" (whitespace only) → exit 1" || no "whitespace unit accepted, rc=$rc"

# POSITIVE — null unit is legal and visible
d="$tmp/null_unit"
labs "$d" '25.3' '"25.3"' 'null'
gate "$d"
[ "$rc" -eq 0 ] && ok "unit: null → exit 0 (absence is recorded, not faked)" \
  || no "null unit wrongly blocked: $out"

# ===========================================================================
# C. NEGATIVE — an impossible numeric token
# ===========================================================================
echo "=== C. '1.2.3' is a transcription artifact in every locale ==="

d="$tmp/impossible"
labs "$d" '1.2' '"1.2.3"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 1 ] && ok "raw_value \"1.2.3\" → exit 1" || no "impossible token accepted, rc=$rc"
echo "$out" | grep -q 'impossible numeric token' && ok "…error names the token" \
  || no "wrong reason: $out"
echo "$out" | grep -q 'decimal-point/phantom-glyph failure mode' \
  && ok "…error names the failure mode it is catching" || no "failure mode not named: $out"

# ===========================================================================
# D. POSITIVE — legitimate source formatting is not a mismatch
# ===========================================================================
echo "=== D. positives ==="

d="$tmp/plain"
labs "$d" '25.3' '"25.3"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 0 ] && ok "value 25.3 / raw_value \"25.3\" → exit 0" || no "clean row blocked: $out"

d="$tmp/with_text"
labs "$d" '25.3' '"CEA 25.3 ng/mL (参考 0-5)"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 0 ] && ok "value found inside a verbatim source string → exit 0" \
  || no "verbatim source string treated as a mismatch: $out"

d="$tmp/thousands"
labs "$d" '12500' '"12,500"' '"/uL"'
gate "$d"
[ "$rc" -eq 0 ] && ok "thousands separator in raw_value → exit 0" \
  || no "thousands separator treated as a mismatch: $out"

d="$tmp/fullwidth"
labs "$d" '3.21' '"３.２１"' '"10^9/L"'
gate "$d"
[ "$rc" -eq 0 ] && ok "full-width digits in raw_value → exit 0" \
  || no "full-width digits treated as a mismatch: $out"

# a non-numeric normalized value is not comparable and must not be forced to be
d="$tmp/qualitative"
labs "$d" '"阴性"' '"阴性"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 0 ] && ok "qualitative value (阴性) → exit 0 (not comparable, not failed)" \
  || no "qualitative value wrongly blocked: $out"

# raw_value that carries no number at all is likewise nothing to compare
d="$tmp/no_number"
labs "$d" '0' '"未检出"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 0 ] && ok "raw_value \"未检出\" → exit 0 (no number to compare)" \
  || no "number-free raw_value wrongly blocked: $out"

# ===========================================================================
# E. the gate makes NO clinical judgement
# ===========================================================================
echo "=== E. no medical judgement ==="

# a value far outside its own printed reference range is NOT this gate's business
d="$tmp/out_of_range"
labs "$d" '250.0' '"250.0"' '"ng/ml"'
gate "$d"
[ "$rc" -eq 0 ] && ok "a value far above its reference range is NOT flagged (no threshold comparison)" \
  || no "the gate made a clinical judgement: $out"

# and it must not invent a report_flag
echo "$out" | grep -qiE 'abnormal|偏高|critical' \
  && no "the gate emitted an abnormality judgement" \
  || ok "…and no abnormality/severity language appears anywhere in its output"

# ===========================================================================
# F. wiring — gate_numeric_integrity subsumes the source-shape floor
# ===========================================================================
echo "=== F. wiring ==="

d="$tmp/shape_missing"
mkdir -p "$d"
cat > "$d/labs.json" <<'EOF'
{ "patient_code":"PT-0E11","schema_version":"2","panels":[
  {"analyte":"癌胚抗原 CEA","values":[{"date":"2026-03-15","value":25.3}]} ]}
EOF
gate "$d"
[ "$rc" -eq 1 ] && ok "gate_numeric_integrity also runs the source-shape floor → exit 1" \
  || no "source-shape floor is no longer reached from gate_numeric_integrity, rc=$rc"
echo "$out" | grep -q 'lab_source_shape' && ok "…and reports it under its own name" \
  || no "source-shape violation not reported: $out"

# ---------------------------------------------------------------------------
echo
echo "== numeric-integrity: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
