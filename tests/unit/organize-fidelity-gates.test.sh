#!/usr/bin/env bash
# Unit tests for the organize fidelity/safety hardening gates:
#   - pii_rescan.py delivered-surface scan + deny-list + path/filename PII (US-001/007/010)
#   - validate_structured_outputs.py gate_numeric_integrity (US-002)
# Uses synthetic fixtures (deterministic, no LLM) so the assertions are stable.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
PII="$ORG/scripts/pii_rescan.py"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap "rm -rf $tmp" EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

# ---------------------------------------------------------------------------
# 1. pii_rescan delivered-surface: name in filename + absolute path + email leak
# ---------------------------------------------------------------------------
d="$tmp/leaky"; mkdir -p "$d/raw/clinical"
# a raw upload whose basename carries a CJK personal name → seeds the deny-list
: > "$d/raw/clinical/王国洪-OncoFusion报告-220013897.pdf"
cat > "$d/INDEX.md" <<'EOF'
# patient_code: PT-TEST01
| f074 | NGS | raw/clinical/王国洪-OncoFusion报告-220013897.pdf | text |
EOF
cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v1","patient_dir":"/Users/alice/CancerDAO/patients/PT-TEST01",
  "files":[{"source_id":"f074","original_path":"/Users/alice/Library/CloudStorage/坚果云-452858265@qq.com/患者/王国洪-OncoFusion报告.pdf","raw_path":"raw/clinical/王国洪-OncoFusion报告-220013897.pdf"}] }
EOF
if python3 "$PII" "$d" >/dev/null 2>"$tmp/leaky.err"; then
  no "leaky delivered surface should exit 1"
else ok; fi
grep -q '王国洪' "$tmp/leaky.err" && ok || no "should flag 王国洪 in delivered surface"
grep -q 'identity_denylist' "$tmp/leaky.err" && ok || no "deny-list (from raw filename) should flag the name"
grep -q '452858265@qq.com' "$tmp/leaky.err" && ok || no "should flag uploader email"
grep -q 'local_user_path' "$tmp/leaky.err" && ok || no "should flag absolute /Users path"

# ---------------------------------------------------------------------------
# 2. pii_rescan delivered-surface CLEAN: relative paths, no name → exit 0
# ---------------------------------------------------------------------------
c="$tmp/clean"; mkdir -p "$c/raw/h1" "$c/07_检验"
: > "$c/raw/h1/IMG_0001.HEIC"
cat > "$c/INDEX.md" <<'EOF'
# patient_code: PT-TEST02
| f001 | lab | raw/h1/IMG_0001.HEIC | image |
EOF
cat > "$c/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v1","patient_dir":"patients/PT-TEST02",
  "files":[{"source_id":"f001","original_path":"raw/h1/IMG_0001.HEIC","raw_path":"raw/h1/IMG_0001.HEIC"}] }
EOF
# a clean sidecar body (no PII tokens) so the bucket scan also passes
cat > "$c/07_检验/2024-08-08_血常规.md" <<'EOF'
SOURCE: lab | CONFIDENCE: medium
ORIGINAL: raw/h1/IMG_0001.HEIC
| 项目 | 结果 | 参考 |
| 白细胞 | 5.2 | 3.5-9.5 |
EOF
if python3 "$PII" "$c" >/dev/null 2>"$tmp/clean.err"; then ok; else
  no "clean patient_dir should exit 0 (got residue: $(cat "$tmp/clean.err"))"; fi

# ---------------------------------------------------------------------------
# 3. pii_rescan body — SHAPE floor only (Layer 2). Label/semantic categories
#    (标本编号 specimen_id, 邮编 postal_code, 申请医生 signatory) are now owned by
#    Layer 1 (the semantic agent scan, references/pii-rescan-prompt.md) and are
#    covered by tests/eval/scenarios/cancer-buddy-organize.md — NOT asserted here.
#    The deterministic floor only owns pure shapes (here: a bare ≥11-digit serial).
# ---------------------------------------------------------------------------
s="$tmp/body"; mkdir -p "$s/07_检验"
cat > "$s/07_检验/2024-08-08_尿液分析.md" <<'EOF'
SOURCE: lab | CONFIDENCE: medium
ORIGINAL: raw/x/IMG_1.HEIC
标本编号：414　科室：内7-2病房
申请医生：刘俊宝
邮编：046204
检验号:
24080800634
EOF
python3 "$PII" "$s/07_检验/2024-08-08_尿液分析.md" >/dev/null 2>"$tmp/body.err" || true
grep -q 'numeric_id' "$tmp/body.err" && ok || no "shape floor should flag bare ≥11-digit 检验号 24080800634"
# negative: label-only lines (specimen_id/postal_code/signatory) must NOT fire the
# deterministic floor — they are Layer 1's job, asserting them here would resurrect
# the removed brittle label arms.
grep -Eq 'specimen_id|postal_code|signatory' "$tmp/body.err" && no "shape floor must NOT own label categories (moved to Layer 1)" || ok

# ---------------------------------------------------------------------------
# 4. numeric_integrity (a): out-of-range value with flag=null → block
# ---------------------------------------------------------------------------
mkdir -p "$tmp/num"
cat > "$tmp/num/labs.json" <<'EOF'
{ "patient_code":"PT-TEST03","schema_version":"1","panels":[
  {"analyte":"癌胚抗原 CEA","unit":"ng/ml","reference_range":"0.00-5.00","values":[
    {"date":"2024-09-05","value":25.3,"flag":null}]} ]}
EOF
out=$(python3 - "$ORG" "$tmp/num" <<'PY'
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import importlib, pathlib
v = importlib.import_module("validate_structured_outputs")
errs=[]; v.gate_numeric_integrity(pathlib.Path(sys.argv[2]), errs)
print(sum(1 for e in errs if "marked normal" in e))
PY
)
[ "$out" = "1" ] && ok || no "out-of-range value flag=null should block (got $out)"

# numeric_integrity (a) negative: in-range value flag=null → no block
cat > "$tmp/num/labs.json" <<'EOF'
{ "patient_code":"PT-TEST03","schema_version":"1","panels":[
  {"analyte":"癌胚抗原 CEA","unit":"ng/ml","reference_range":"0.00-5.00","values":[
    {"date":"2024-09-05","value":4.68,"flag":null}]} ]}
EOF
out=$(python3 - "$ORG" "$tmp/num" <<'PY'
import sys; sys.path.insert(0, sys.argv[1]+"/scripts")
import importlib, pathlib
v = importlib.import_module("validate_structured_outputs")
errs=[]; v.gate_numeric_integrity(pathlib.Path(sys.argv[2]), errs)
print(sum(1 for e in errs if "marked normal" in e))
PY
)
[ "$out" = "0" ] && ok || no "in-range value flag=null must NOT block (got $out)"

# ---------------------------------------------------------------------------
echo "organize-fidelity-gates: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
