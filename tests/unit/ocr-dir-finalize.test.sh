#!/usr/bin/env bash
# tests/unit/ocr-dir-finalize.test.sh — organize v3, fix spec A29.
#
# ocr/ is staging, not content. 段 1 writes the MASKED page copies there, 段 2 moves each
# one into the bucket its document belongs to, and then deletes the directory. So a
# finished archive has no ocr/ at all — the absence of the directory IS the completion
# signal for that phase.
#
# A page left behind in staging is not clutter. It has no source_inventory row, so no
# gate reads it; it has no bucket path, so no [[src:...]] anchor can point at it; it is
# in no coverage number, so projection_coverage will not mention it. Meanwhile it sits in
# the archive as a masked medical sidecar, indistinguishable at a glance from filed
# content. That is the worst possible state: the archive LOOKS as though it holds the
# material and every mechanism designed to notice a gap reports clean. A run that dropped
# half its pages in ocr/_inbox/ and a run that filed all of them produce the same verdict
# unless this is checked, which is why it is an ERROR and why the error has to LIST the
# residue — "there is something in ocr/" is not actionable; the paths are.
#
# The empty-directory case is checked too, and deliberately: an empty ocr/ is the one
# state where "nothing was ever staged here" and "staging was never cleaned up" look
# identical from the outside. The contract resolves the ambiguity by removing the
# directory itself, so an empty ocr/ is a defect rather than a tidy result.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# run ONLY the staging gate, so nothing in this file can pass or fail for an unrelated
# reason. `out` holds the gate's errors, `rc` is 1 when it produced any.
gate() {  # <patient_dir>
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_ocr_staging_cleared(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
}

# A complete, schema-valid v4 archive — scheme_version 4, kind + clinical_class on the
# row, projection_coverage in readiness, a filled AGENTS.md. It exists so the POSITIVE
# arm can be the real end-to-end verdict (full validator, exit 0) rather than one gate
# in isolation: "a finished archive has no ocr/" is a claim about finished archives.
mk_archive() {  # <dir>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/upload-001.txt"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "kind":"known","doc_kind":"出院小结","clinical_class":"narrative",
   "text_layer_kind":"not_applicable",
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable",
   "adapter":"text_payload","persist":true} ]}
EOF
  cat > "$d/readiness.json" <<'EOF'
{"patient_code":"PT-A1B2","schema_version":"3",
 "documentation_coverage":{"pathology_report":"not_in_archive"},
 "projection_coverage":{
   "per_source":[{"source_id":"s1","unprojected_field_classes":[]}],
   "summary":{"sources_total":1,"sources_fully_projected":1,
              "novel_sources":0,"unreadable_sources":0}},
 "review_flags":[]}
EOF
  cat > "$d/profile.json" <<'EOF'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1B2",
 "summary":{"one_line_condition":"示例：结肠腺癌术后"}}
EOF
  # B7 — update_log.json is a required product, and this suite's positive arm is the
  # FULL validator verdict on a finished archive. A finished archive that cannot say
  # which run built it is not finished, so the fixture has to carry the run history or
  # the "no ocr/ residue" claim below would be riding on the wrong exit code.
  cat > "$d/update_log.json" <<'EOF'
{"schema_version":"1","patient_code":"PT-A1B2","runs":[
  {"run_id":"run-001","run_mode":"full","started_at":"2026-09-16T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],
   "pii_semantic":"clean","faithfulness_method":"native_text_identity"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

# ===========================================================================
# A. POSITIVE — a finished archive has no ocr/ at all
# ===========================================================================
echo "=== A. no ocr/ directory ==="

D="$tmp/clean"
mk_archive "$D"
[ ! -e "$D/ocr" ] && ok "the finished fixture has no ocr/ directory" || no "fixture ships an ocr/"

gate "$D"
[ "$rc" -eq 0 ] && ok "gate_ocr_staging_cleared: no ocr/ → no error" \
  || no "a finished archive was flagged: $out"

python3 "$VAL" "$D" >"$tmp/clean.out" 2>"$tmp/clean.err"; vrc=$?
[ "$vrc" -eq 0 ] && ok "the FULL validator exits 0 on the finished archive" \
  || no "full validator exited $vrc: $(grep '^ERROR' "$tmp/clean.err")"
grep -q 'ocr_staging' "$tmp/clean.err" \
  && no "a clean archive still produced an ocr_staging complaint" \
  || ok "…with no ocr_staging complaint anywhere in the output"

# ===========================================================================
# B. NEGATIVE — a leftover _inbox/ is an ERROR, and the residue is named
# ===========================================================================
echo "=== B. ocr/_inbox/ residue ==="

D="$tmp/inbox"
mk_archive "$D"
mkdir -p "$D/ocr/_inbox/s1"
printf -- '---\nsource_id: s1\npage: 1\n---\n# 全文\n白细胞计数 3.21\n' \
  > "$D/ocr/_inbox/s1/page-001.md"

gate "$D"
[ "$rc" -eq 1 ] && ok "a page left under ocr/_inbox/ → ERROR" \
  || no "leftover staging accepted, rc=$rc"
echo "$out" | grep -q 'ocr/_inbox/s1/page-001.md' \
  && ok "…and the error LISTS the residue by path (not just 'ocr/ is not empty')" \
  || no "the residue path is not in the message: $out"
echo "$out" | grep -q '1 file(s) remain' \
  && ok "…with the count, so an operator knows the size of the problem" \
  || no "no residue count: $out"
echo "$out" | grep -q 'no inventory row and no anchor' \
  && ok "…and states WHY it matters: no inventory row, no anchor, invisible to every gate" \
  || no "the consequence is not stated: $out"

python3 "$VAL" "$D" >/dev/null 2>"$tmp/inbox.err"; vrc=$?
[ "$vrc" -eq 1 ] && ok "the FULL validator exits 1 on the same archive" \
  || no "full validator exited $vrc with staging residue present"
grep -q '^ERROR: ocr_staging' "$tmp/inbox.err" \
  && ok "…reported as an ERROR (never a WARN that a run can ignore)" \
  || no "ocr_staging was not raised as an ERROR by the full validator"

# ===========================================================================
# C. NEGATIVE — ANY residue under ocr/, not just _inbox/
# ===========================================================================
echo "=== C. any residue at all ==="

D="$tmp/reports"
mk_archive "$D"
mkdir -p "$D/ocr/_reports"
printf 'run r1: 3 pages\n' > "$D/ocr/_reports/summary.txt"
gate "$D"
[ "$rc" -eq 1 ] && ok "a leftover ocr/_reports/ file → ERROR" || no "_reports/ residue accepted"
echo "$out" | grep -q 'ocr/_reports/summary.txt' \
  && ok "…listed by path as well" || no "_reports residue not listed: $out"

D="$tmp/loose"
mk_archive "$D"
mkdir -p "$D/ocr/s1"
printf -- '---\nsource_id: s1\n---\n# 全文\nx\n' > "$D/ocr/s1/page-002.md"
gate "$D"
[ "$rc" -eq 1 ] && ok "a masked page left directly under ocr/<sid>/ → ERROR" \
  || no "an unfiled masked page was accepted"
echo "$out" | grep -q 'ocr/s1/page-002.md' && ok "…listed by path" || no "not listed: $out"

# many files: the message stays readable but must still name some and say there are more
D="$tmp/many"
mk_archive "$D"
mkdir -p "$D/ocr/_inbox/s1"
for i in 1 2 3 4 5 6 7; do
  printf -- '---\nsource_id: s1\n---\n# 全文\nx\n' > "$D/ocr/_inbox/s1/page-00$i.md"
done
gate "$D"
[ "$rc" -eq 1 ] && ok "seven leftover pages → ERROR" || no "bulk residue accepted"
echo "$out" | grep -q '7 file(s) remain' \
  && ok "…the COUNT is the full 7, not the number of paths printed" \
  || no "the count is truncated along with the list: $out"
echo "$out" | grep -q '…' \
  && ok "…and the truncated list is marked, so nobody reads 5 paths as the whole problem" \
  || no "a truncated residue list is not marked as truncated: $out"

# ===========================================================================
# D. NEGATIVE — an EMPTY ocr/ is a defect too
# ===========================================================================
echo "=== D. the directory itself is the signal ==="

D="$tmp/empty"
mk_archive "$D"
mkdir -p "$D/ocr"
gate "$D"
[ "$rc" -eq 1 ] && ok "an empty ocr/ → ERROR (the completed state is that it is GONE)" \
  || no "an empty staging directory was accepted as finished"
echo "$out" | grep -q 'still exists (empty)' \
  && ok "…and the error distinguishes 'empty' from 'holds unfiled pages'" \
  || no "the empty case is not named: $out"
echo "$out" | grep -q "look identical" \
  && ok "…stating the ambiguity it exists to remove" || no "rationale absent: $out"

D="$tmp/empty_inbox"
mk_archive "$D"
mkdir -p "$D/ocr/_inbox"
gate "$D"
[ "$rc" -eq 1 ] && ok "an empty ocr/_inbox/ → ERROR as well" \
  || no "an empty _inbox was accepted"

# ===========================================================================
# E. scope — the rule is about ocr/, and only ocr/
# ===========================================================================
echo "=== E. scope ==="

# raw/ is the permanent vault, not staging: it must survive untouched
D="$tmp/raw_kept"
mk_archive "$D"
mkdir -p "$D/raw/transcript/s1" "$D/raw/_provenance/r1"
printf -- '---\nsource_id: s1\n---\n# 全文\nx\n' > "$D/raw/transcript/s1/page-001.md"
printf '{"pages": []}\n' > "$D/raw/_provenance/r1/transcribe-manifest.json"
gate "$D"
[ "$rc" -eq 0 ] \
  && ok "raw/transcript/ and raw/_provenance/ are NOT staging — they are never flagged" \
  || no "the staging gate reached into raw/: $out"

# a directory that merely starts with the letters ocr is a bucket name, not the staging dir
D="$tmp/lookalike"
mk_archive "$D"
mkdir -p "$D/03_病程与叙事文书/ocr_notes"
printf 'note\n' > "$D/03_病程与叙事文书/ocr_notes/x.md"
gate "$D"
[ "$rc" -eq 0 ] && ok "a nested directory merely NAMED ocr_notes is not staging residue" \
  || no "the gate matched on the name instead of the top-level staging path: $out"

# and the gate reads its directory name from the module constant, not from a copy here
python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
assert v.OCR_STAGING_DIR == "ocr", v.OCR_STAGING_DIR
PYEOF
[ $? -eq 0 ] && ok "OCR_STAGING_DIR is 'ocr' (this test and the gate agree on the path)" \
  || no "OCR_STAGING_DIR drifted away from 'ocr'"

# ---------------------------------------------------------------------------
echo
echo "== ocr-dir-finalize: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
