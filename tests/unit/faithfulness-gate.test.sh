#!/usr/bin/env bash
# tests/unit/faithfulness-gate.test.sh — organize v3→v4 fix spec A20.
#
# 段 2.5 is the pass that goes back to the page raster and checks that the value the
# archive now carries is the value the document actually prints, with a span saying
# WHERE. Two failure modes made it optional in practice, and both were invisible.
#
# The first is silence. `faithfulness_method` was enum-checked only when it was
# present, so a run that skipped verification entirely validated more easily than one
# that did the work and wrote down which method it used. That is the shape where
# honesty costs and silence is free, and it always resolves the same way. So: at least
# one raw/_provenance/<run>/faithfulness-*.json per archive that declares any
# high-risk field, and the legal exemption for a born-digital source is a RECORDED
# `faithfulness_method: native_text_identity` (A35), never the absence of a record.
#
# The second is spans that are syntactically perfect and semantically empty. The
# validator never read a bbox, so `[0, 0, 1, 1]` — "it is somewhere on this page" —
# satisfied every high-risk field at zero cost, and a span could cite a page the
# document does not have. Hence the three geometric assertions, each of which is a
# different way of pointing at nothing:
#   * area < 1e-4 — too small to contain a legible value; the crop verified nothing;
#   * area > 0.5  — more than half the page is not a location;
#   * span.page != the record's own page, or page > page_total from pages.json —
#     the span is outside the thing it claims to be evidence about.
#
# And coverage is 100%, not a sample: every high_risk_fields[] entry in the inventory
# must be covered by some record. The fields marked high-risk are precisely the ones
# where one wrong character changes a dose, a date or a variant, which is why they are
# the set that gets verified unconditionally while everything else is sampled.
#
# What this gate deliberately does NOT do — and the boundary is asserted, because a
# gate trusted beyond its reach is worse than one that does not exist — is judge
# whether the cropped region actually shows the value. That is the reread's job and no
# script can stand in for it.
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

# An archive with two declared high-risk fields on a 2-page image source, and a
# pages.json that pins page_total — which is what makes "page 7" checkable at all.
# The fields are recorded needs_human_review / reread_channel none so this fixture
# exercises ONLY 段 2.5: the A5 independence rules have their own test file.
mk_archive() {  # <dir>
  local d="$1"
  mkdir -p "$d/raw/_provenance/run-001" "$d/07_检验"
  : > "$d/07_检验/a.md"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"u.pdf","raw_path":"raw/incoming/u.pdf",
   "page_range":null,"kind":"known","doc_kind":"化疗记录","clinical_class":"narrative",
   "text_layer_kind":"absent","sidecar_path":"07_检验/a.md","bucket_path":"07_检验",
   "modality":"image","read_mode":"model_vision_primary","transcribe_model_id":"host-vision-1",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"needs_human_review","reread_channel":"none",
   "high_risk_fields":[
     {"label":"白细胞计数","status":"needs_human_review","reread_channel":"none","readings":[]},
     {"label":"给药剂量","status":"needs_human_review","reread_channel":"none","readings":[]}],
   "adapter":"pdf_pages","persist":true} ]}
EOF
  cat > "$d/raw/_provenance/run-001/pages.json" <<'EOF'
{ "run_id":"run-001","pages":[
  {"source_id":"s1","page":1,"page_total":2,"image":"raw/pages/s1/page-001.png",
   "text_layer_kind":"absent","packet_path":"raw/_provenance/run-001/packets/s1-001.json"},
  {"source_id":"s1","page":2,"page_total":2,"image":"raw/pages/s1/page-002.png",
   "text_layer_kind":"absent","packet_path":"raw/_provenance/run-001/packets/s1-002.json"} ]}
EOF
}

report() {  # <dir> <checks json body> [faithfulness_method]
  cat > "$1/raw/_provenance/run-001/faithfulness-s1.json" <<EOF
{ "schema":"faithfulness_v1","run_id":"run-001","source_id":"s1",
  "faithfulness_method":"${3:-vision_second_read}","checks":[$2] }
EOF
}

OK_WBC='{"source_id":"s1","label":"白细胞计数","page":1,"span":{"page":1,"bbox":[0.10,0.20,0.34,0.24]},"verdict":"match"}'
OK_DOSE='{"source_id":"s1","label":"给药剂量","page":2,"span":{"page":2,"bbox":[0.11,0.51,0.38,0.56]},"verdict":"match"}'

# ===========================================================================
# A. NEGATIVE — 段 2.5 never ran
# ===========================================================================
echo "=== A. no faithfulness record at all ==="

d="$tmp/missing"; mk_archive "$d"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "no faithfulness-*.json anywhere, 2 high-risk fields declared → exit 1" \
  || no "a run that verified nothing passed, rc=$rc"
echo "$out" | grep -q 'no raw/_provenance/<run>/faithfulness-\*.json exists' \
  && ok "…error names the artifact that is missing and where it belongs" || no "wrong reason: $out"
echo "$out" | grep -q '段 2.5 is MANDATORY' \
  && ok "…error states that the段 is not optional" || no "mandatory-ness not stated: $out"
echo "$out" | grep -q 'native_text_identity' \
  && ok "…error names the ONE legal exemption (a recorded native_text_identity)" \
  || no "the exemption is not named: $out"
echo "$out" | grep -q 'must not be cheaper to pass' \
  && ok "…error states the incentive it exists to remove (silence being free)" \
  || no "incentive not stated: $out"

# ===========================================================================
# B. NEGATIVE — a record that covers only some of the high-risk set
# ===========================================================================
echo "=== B. partial coverage ==="

d="$tmp/partial"; mk_archive "$d"
report "$d" "$OK_WBC"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "2 high-risk fields, 1 covered → exit 1" \
  || no "sampling accepted where 100% is required, rc=$rc"
echo "$out" | grep -q "s1 field '给药剂量'" \
  && ok "…error names the uncovered field" || no "uncovered field not named: $out"
echo "$out" | grep -q '100% of high-risk fields' \
  && ok "…error states the coverage rule" || no "coverage rule not stated: $out"
echo "$out" | grep -q 'a single wrong character changes a dose' \
  && ok "…error states why this set in particular is unconditional" || no "rationale missing: $out"

# a record that covers a DIFFERENT field is not coverage either
d="$tmp/wrong_field"; mk_archive "$d"
report "$d" '{"source_id":"s1","label":"报告日期","page":1,"span":{"page":1,"bbox":[0.1,0.1,0.3,0.14]}}'
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "a record covering a field that is not in high_risk_fields[] → exit 1" \
  || no "coverage satisfied by an unrelated field, rc=$rc"

# ===========================================================================
# C. NEGATIVE — spans that point at nothing (one case each)
# ===========================================================================
echo "=== C. bbox geometry and page bounds ==="

d="$tmp/bbox_tiny"; mk_archive "$d"
report "$d" '{"source_id":"s1","label":"白细胞计数","page":1,"span":{"page":1,"bbox":[0.100,0.200,0.1005,0.2005]}},'"$OK_DOSE"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "bbox area BELOW 1e-4 → exit 1" || no "a sub-pixel span accepted, rc=$rc"
echo "$out" | grep -q 'below 1e-4 of the page' \
  && ok "…error states the floor" || no "floor not stated: $out"
echo "$out" | grep -q 'cannot contain the value it claims to locate' \
  && ok "…error states why a too-small box verifies nothing" || no "rationale missing: $out"

d="$tmp/bbox_full"; mk_archive "$d"
report "$d" '{"source_id":"s1","label":"白细胞计数","page":1,"span":{"page":1,"bbox":[0.0,0.0,1.0,1.0]}},'"$OK_DOSE"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "bbox area ABOVE 0.5 ([0,0,1,1]) → exit 1" || no "whole-page span accepted, rc=$rc"
echo "$out" | grep -q 'more than half the page' \
  && ok "…error states the ceiling" || no "ceiling not stated: $out"
echo "$out" | grep -q 'absence of a location' \
  && ok "…error states that 'somewhere on this page' is not a span" || no "rationale missing: $out"

d="$tmp/span_page"; mk_archive "$d"
report "$d" '{"source_id":"s1","label":"白细胞计数","page":1,"span":{"page":2,"bbox":[0.10,0.20,0.34,0.24]}},'"$OK_DOSE"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "span.page != the record's own page → exit 1" || no "inconsistent page accepted, rc=$rc"
echo "$out" | grep -q "span.page 2 != the record's own page 1" \
  && ok "…error quotes both page numbers" || no "pages not quoted: $out"

d="$tmp/oob"; mk_archive "$d"
report "$d" '{"source_id":"s1","label":"白细胞计数","page":7,"span":{"page":7,"bbox":[0.10,0.20,0.34,0.24]}},'"$OK_DOSE"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "page > page_total from pages.json → exit 1" || no "out-of-range page accepted, rc=$rc"
echo "$out" | grep -q 'has only 2 page(s) per pages.json' \
  && ok "…error cites pages.json as the authority on page_total" || no "authority not cited: $out"
echo "$out" | grep -q 'points outside the document' \
  && ok "…error states the span is outside the document" || no "conclusion not stated: $out"

# the method vocabulary stays closed: an unrecognised value silently reads as
# "some verification happened", which is exactly the claim that must never be vague
d="$tmp/bad_method"; mk_archive "$d"
report "$d" "$OK_WBC,$OK_DOSE" "manual_review"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "an off-enum faithfulness_method → exit 1" || no "invented method accepted, rc=$rc"
echo "$out" | grep -q "faithfulness_method 'manual_review' is not one of" \
  && ok "…error quotes the value and the closed vocabulary" || no "enum not quoted: $out"

# a corrupt record is reported as corrupt, not skipped into a silent pass
d="$tmp/corrupt"; mk_archive "$d"
printf '{ "checks": [' > "$d/raw/_provenance/run-001/faithfulness-s1.json"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 1 ] && ok "an unparseable faithfulness-*.json → exit 1" || no "a corrupt record passed, rc=$rc"
echo "$out" | grep -q 'not parseable' && ok "…error says the file could not be read" || no "wrong reason: $out"

# ===========================================================================
# D. POSITIVE — a complete, in-range report
# ===========================================================================
echo "=== D. the shape that should pass ==="

d="$tmp/complete"; mk_archive "$d"
report "$d" "$OK_WBC,$OK_DOSE"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 0 ] && ok "every high-risk field covered, every bbox in range, every page valid → exit 0" \
  || no "a complete report was blocked: $out"

# both ends of the legal band are INSIDE it: the comparisons are `< 1e-4` and `> 0.5`,
# so a span sitting ON a boundary is not quietly rejected by a strict inequality. (The
# bboxes are chosen to be exactly representable in binary floating point — a fixture
# whose area lands a few ULPs under the floor would be testing IEEE 754, not the gate.)
d="$tmp/boundary"; mk_archive "$d"
report "$d" \
  '{"source_id":"s1","label":"白细胞计数","page":1,"span":{"page":1,"bbox":[0.00,0.00,0.01,0.01]}},{"source_id":"s1","label":"给药剂量","page":2,"span":{"page":2,"bbox":[0.0,0.0,1.0,0.5]}}'
run_gate gate_faithfulness "$d"
[ "$rc" -eq 0 ] && ok "bbox areas of exactly 1e-4 and exactly 0.5 → exit 0 (the band is inclusive)" \
  || no "a boundary-value span was rejected: $out"

# the native_text exemption is a RECORD, not an absence (A35): a born-digital source
# whose characters were compared byte-for-byte declares its method and passes
d="$tmp/native"; mk_archive "$d"
report "$d" "$OK_WBC,$OK_DOSE" "native_text_identity"
run_gate gate_faithfulness "$d"
[ "$rc" -eq 0 ] && ok "faithfulness_method: native_text_identity → exit 0" \
  || no "the recorded native-text exemption was rejected: $out"

# an archive that declares NO high-risk field owes no record — the rule is scoped to
# the claim, not applied by reflex to every archive
d="$tmp/no_high_risk"; mk_archive "$d"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "source_inventory.json"
data = json.loads(p.read_text(encoding="utf-8"))
data["files"][0]["high_risk_fields"] = []
data["files"][0]["high_risk_review_status"] = "not_applicable"
p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
PYEOF
run_gate gate_faithfulness "$d"
[ "$rc" -eq 0 ] && ok "no high_risk_fields declared + no record → exit 0" \
  || no "a record demanded where nothing was claimed: $out"

# ===========================================================================
# E. the boundary this gate does NOT cross
# ===========================================================================
echo "=== E. scope ==="

# A span that is well-formed, in range, on the right page and points at the WRONG
# region still passes. That is not a hole, it is the division of labour: only the
# reread can say whether the crop shows the value, and a gate that pretended otherwise
# would be trusted for a judgement no script can make. The docstring must say so.
python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
doc = v.gate_faithfulness.__doc__ or ""
assert "does NOT do" in doc, "gate_faithfulness does not state its blind spot"
assert "no script can stand in for it" in doc, "the division of labour is not recorded"
assert v.FAITHFULNESS_METHODS == {
    "native_text_identity", "vision_second_read", "sampled_reread"
}, f"method vocabulary drifted: {sorted(v.FAITHFULNESS_METHODS)}"
print("scope + vocabulary pinned")
PYEOF
[ $? -eq 0 ] && ok "the gate records what it cannot check, and its method vocabulary is pinned" \
             || no "scope or vocabulary not pinned in code"

# ---------------------------------------------------------------------------
echo
echo "== faithfulness-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
