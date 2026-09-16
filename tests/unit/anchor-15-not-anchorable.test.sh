#!/usr/bin/env bash
# tests/unit/anchor-15-not-anchorable.test.sh — organize v3, decision Q7.
#
# Domain 15 is an OPEN archive: its sub-bucket slug is model-written from untrusted
# source text and its contents are by definition material no pinned schema
# anticipated. So it is NOT an anchor target. A formal output (labs / timeline /
# molecular / …) may never rest a fact on a `15_…` path; open readings carry their
# own pointer instead — extracted_fields.json `open_ref = {source_id, page, bbox}` —
# which anchors to the raw page image rather than to a directory a model named.
#
# The failure this prevents is quiet: a `15_…/report.md` file EXISTS on disk, so a
# plain "does the anchor resolve?" check passes and the open material silently
# becomes a cited clinical fact.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# validate_anchors over one structured file; stdout = errors, exit 1 when any.
anchors() {  # <patient_dir> <fname>
  set +e
  out="$(python3 - "$ORG" "$1" "$2" <<'PYEOF'
import sys, json, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
pd = pathlib.Path(sys.argv[2])
data = json.loads((pd / sys.argv[3]).read_text(encoding="utf-8"))
errs = []
v.validate_anchors(pd, data, sys.argv[3], errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

labs_json() {  # <patient_dir> <anchor>
  cat > "$1/labs.json" <<EOF
{ "patient_code":"PT-A15","schema_version":"2","panels":[
  {"analyte":"白细胞计数","values":[
    {"date":"2026-03-15","value":3.21,"raw_value":"3.21","unit":"10^9/L",
     "reference_range":"3.50-9.50","report_flag":"L","critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "source_refs":["$2"]}]} ]}
EOF
}

# ===========================================================================
# NEGATIVE — a formal output citing the open archive
# ===========================================================================
echo "=== A. negative: labs.json source_refs → 15_ ==="

d="$tmp/open_ref_needed"
mkdir -p "$d/15_未分类资料/肠道菌群检测"
# the file genuinely EXISTS — existence is exactly what makes this failure quiet
cat > "$d/15_未分类资料/肠道菌群检测/report.md" <<'EOF'
SOURCE: novel | CONFIDENCE: medium
| 项目 | 结果 |
| 白细胞计数 | 3.21 |
EOF
labs_json "$d" "15_未分类资料/肠道菌群检测/report.md"

anchors "$d" labs.json
[ "$rc" -eq 1 ] && ok "labs.json anchoring into 15_ → exit 1" || no "15_ anchor must fail, got rc=$rc"
echo "$out" | grep -q 'open_ref' \
  && ok "…error names extracted_fields.open_ref as the correct mechanism" \
  || no "error does not mention open_ref: $out"
echo "$out" | grep -q 'not anchorable' \
  && ok "…error states 15_ is not anchorable" || no "error does not say 'not anchorable': $out"
if echo "$out" | grep -q 'dangling'; then
  no "15_ rejection was reported as a dangling anchor — the file exists; the point is that it is not citable"
else
  ok "…it is a policy failure, not a 'dangling anchor' report"
fi

# en-locale open domain is the same domain
d2="$tmp/open_en"
mkdir -p "$d2/15_unclassified/gut-microbiome"
: > "$d2/15_unclassified/gut-microbiome/report.md"
labs_json "$d2" "15_unclassified/gut-microbiome/report.md"
anchors "$d2" labs.json
[ "$rc" -eq 1 ] && ok "en-locale 15_unclassified anchor also rejected" \
  || no "15_unclassified anchor was accepted, got rc=$rc"

# a 15_ anchor with a #fragment must not slip past the prefix check
d3="$tmp/open_frag"
mkdir -p "$d3/15_未分类资料/肠道菌群检测"
: > "$d3/15_未分类资料/肠道菌群检测/report.md"
labs_json "$d3" "15_未分类资料/肠道菌群检测/report.md#L12-L18"
anchors "$d3" labs.json
[ "$rc" -eq 1 ] && ok "15_ anchor carrying a #Lnn fragment also rejected" \
  || no "fragment form slipped past the open-domain check, rc=$rc"

# the rule is about the FORMAL surface, so it must hold for any structured file
d4="$tmp/open_timeline"
mkdir -p "$d4/15_未分类资料/肠道菌群检测"
: > "$d4/15_未分类资料/肠道菌群检测/report.md"
cat > "$d4/timeline.json" <<'EOF'
{ "patient_code":"PT-A15","schema_version":"1","events":[
  {"date":"2026-03-15","event":"报告","source_refs":["15_未分类资料/肠道菌群检测/report.md"]} ]}
EOF
anchors "$d4" timeline.json
[ "$rc" -eq 1 ] && ok "timeline.json anchoring into 15_ → exit 1 (rule is per-surface, not per-file)" \
  || no "timeline.json 15_ anchor accepted, rc=$rc"

# ===========================================================================
# POSITIVE — a pinned clinical domain is anchorable exactly as before
# ===========================================================================
echo "=== B. positive: labs.json source_refs → 07_检验 ==="

c="$tmp/pinned_ok"
mkdir -p "$c/07_检验/血常规"
cat > "$c/07_检验/血常规/2026-03-15_血常规.md" <<'EOF'
SOURCE: lab | CONFIDENCE: high
| 项目 | 结果 | 参考 |
| 白细胞计数 | 3.21 | 3.50-9.50 |
EOF
labs_json "$c" "07_检验/血常规/2026-03-15_血常规.md"
anchors "$c" labs.json
[ "$rc" -eq 0 ] && ok "07_检验 anchor accepted → exit 0" || no "pinned anchor rejected: $out"
[ -z "$out" ] && ok "…with zero errors" || no "pinned anchor produced errors: $out"

# 14_ (the last CLOSED domain) is still anchorable — the rule is 15_-specific,
# not "high-numbered domains are suspect".
c2="$tmp/pinned_14"
mkdir -p "$c2/14_患者自管补充/日记"
: > "$c2/14_患者自管补充/日记/2026-03-15.md"
labs_json "$c2" "14_患者自管补充/日记/2026-03-15.md"
anchors "$c2" labs.json
[ "$rc" -eq 0 ] && ok "14_患者自管补充 anchor still accepted (only 15_ is closed off)" \
  || no "14_ anchor wrongly rejected: $out"

# a MISSING pinned target must still fail, and for the dangling reason
c3="$tmp/pinned_missing"
mkdir -p "$c3/07_检验/血常规"
labs_json "$c3" "07_检验/血常规/nope.md"
anchors "$c3" labs.json
[ "$rc" -eq 1 ] && ok "missing pinned target still fails" || no "dangling pinned anchor accepted"
echo "$out" | grep -q 'dangling anchor' && ok "…reported as a dangling anchor, not as a 15_ policy breach" \
  || no "dangling anchor reported with the wrong reason: $out"

# ===========================================================================
# C. wiring — the entrypoint, not just the helper
# ===========================================================================
echo "=== C. entrypoint wiring ==="
set +e
python3 "$VAL" "$d" >/dev/null 2>"$tmp/entry.err"
rc=$?
set -e
[ "$rc" -ne 0 ] && ok "full validate script exits nonzero on the 15_-anchored fixture" \
  || no "entrypoint accepted a 15_ anchor"
grep -q 'open_ref' "$tmp/entry.err" && ok "entrypoint surfaces the open_ref guidance" \
  || no "entrypoint did not surface the 15_ anchor error"

# ---------------------------------------------------------------------------
echo
echo "== anchor-15-not-anchorable: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
