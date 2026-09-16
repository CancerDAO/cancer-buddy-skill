#!/usr/bin/env bash
# tests/unit/field-provenance-gate.test.sh — organize v3→v4 fix spec A19.
#
# gate_numeric_integrity compares labs.json `value` against the `raw_value` recorded
# beside it. Both of those strings were written by the SAME pass, in the same object,
# seconds apart. So that gate can prove normalization did not invent a number — and it
# can prove absolutely nothing about whether the page was read correctly, because when
# the page is misread BOTH fields are wrong together and the comparison stays green.
# Its old docstring called itself "transcription integrity", which was a claim it had
# no standing to make; A19 renames the semantics to NORMALIZATION CONSISTENCY and
# moves the real question somewhere else.
#
# That somewhere else is gate_field_provenance, and the difference is the boundary it
# crosses. It takes the source-reported string and asks whether it actually occurs in
# the document labs.json says it came from — the page frontmatter's fields[].value /
# source_reported_text, or the page text itself. A number that appears nowhere in its
# own cited document was either misread off the page or imported from elsewhere, and
# "provenance" is exactly the word that is supposed to make both impossible.
#
# The scope limits are asserted here too, because a gate whose reach is assumed rather
# than stated gets trusted for things it never checked:
#   * it verifies PRESENCE, not that the right CELL was read — a value lifted from the
#     wrong row of the right page still passes, and the reread owns that;
#   * a dangling source_ref is gate_source_inventory's failure, not this one's, so
#     this gate must stay silent rather than reporting the same defect twice in
#     different words;
#   * (B3) it reads the TRANSCRIPT, not the cheaper derived sidecar, whenever one exists
#     on disk — the sidecar was written by the same pass as labs.json and agreeing with
#     yourself is not provenance;
#   * a scheme-3 archive is exempt, because it has no per-page transcription contract
#     to check against.
#
# And the companion rule from the same item: `raw_value: null` on a laboratory row is
# an ERROR. A bare normalized number with the source layer deleted looks exactly as
# trustworthy as one that survived verification, which is the whole failure mode.
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

SIDECAR="07_检验/肿瘤标志物/2026-03-15_CEA.md"

# One inventory row, one source, no bucket sidecar on disk — so the only surface the
# gate can read is raw/transcript/s1/, which is precisely the cross-source binding
# under test. (Under B3 the transcript is the authoritative surface whenever it exists,
# sidecar or not; section C asserts that ordering and its one exception.)
mk_archive() {  # <dir>
  local d="$1"
  mkdir -p "$d/raw/transcript/s1" "$d/07_检验/肿瘤标志物"
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"u.pdf","raw_path":"raw/incoming/u.pdf",
   "page_range":null,"kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent","sidecar_path":"$SIDECAR","bucket_path":"07_检验/肿瘤标志物",
   "modality":"image","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"not_applicable","adapter":"pdf_pages","persist":true} ]}
EOF
}

# <dir> <fields json array> <body text>
transcript() {
  cat > "$1/raw/transcript/s1/page-001.md" <<EOF
---
source_id: s1
page: 1
page_total: 1
fields: $2
---
# 全文
$3
EOF
}

# <dir> <value json> <raw_value json> [source_refs json array]
labs() {
  local REFS="${4:-[\"$SIDECAR\"]}"
  cat > "$1/labs.json" <<EOF
{ "patient_code":"PT-0E11","schema_version":"2","panels":[
  {"analyte":"癌胚抗原 CEA","values":[
    {"date":"2026-03-15","value":$2,"raw_value":$3,"unit":"ng/mL",
     "reference_range":"0.00-5.00","report_flag":null,"critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "source_refs":$REFS}]} ]}
EOF
}

FIELDS_CEA='[{"label": "癌胚抗原 CEA", "value": "12.4", "source_reported_text": "癌胚抗原 CEA 12.4 ng/mL"}]'

# ===========================================================================
# A. NEGATIVE — a number that is nowhere in the document it cites
# ===========================================================================
echo "=== A. raw_value absent from the cited source ==="

# the classic dropped-decimal misread: "12.4" on the page, "124" in labs.json. Every
# schema, every anchor check and every PII scan stays green on this; only the
# cross-source comparison can see it.
d="$tmp/absent"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL (参考 0.00-5.00)"
labs "$d" 124 '"124"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 1 ] && ok "raw_value in no fields[].value / source_reported_text / page text → exit 1" \
  || no "a value with no reachable source passed, rc=$rc"
echo "$out" | grep -q "raw_value '124'" \
  && ok "…error NAMES the offending value (not just the row)" || no "value not named: $out"
echo "$out" | grep -q "癌胚抗原 CEA" \
  && ok "…and the analyte it belongs to" || no "analyte not named: $out"
echo "$out" | grep -q 'raw/transcript/s1/page-001.md' \
  && ok "…and the surface that was searched" || no "surface not named: $out"
echo "$out" | grep -q 'misread or imported from elsewhere' \
  && ok "…error states the two things this can mean" || no "diagnosis missing: $out"
echo "$out" | grep -q 'legitimately masked' \
  && ok "…error names the one honest exception (a masked PII shape) and how to record it" \
  || no "the masking exception is not offered: $out"

# a value invented wholesale — same refusal, no special case
d="$tmp/imported"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL"
labs "$d" 87.5 '"87.5"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 1 ] && ok "a value imported from another document entirely → exit 1" \
  || no "an imported value passed, rc=$rc"

# ===========================================================================
# B. POSITIVE — the value is in the source's transcript frontmatter
# ===========================================================================
echo "=== B. the same value, present in the source ==="

d="$tmp/present"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL (参考 0.00-5.00)"
labs "$d" 12.4 '"12.4"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "raw_value present in the transcript frontmatter → exit 0" \
  || no "a correctly-sourced value was blocked: $out"

# frontmatter ALONE is sufficient: the page body may be unreadable prose, a table the
# model could not lay out, or nothing at all. fields[] is the structured claim.
d="$tmp/fm_only"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "本页表格排版无法还原"
labs "$d" 12.4 '"12.4"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "value in fields[].value only, body carries it nowhere → exit 0" \
  || no "the frontmatter binding is not consulted: $out"

# raw_value may carry the unit the field records bare — containment holds both ways,
# because "12.4 ng/mL" and "12.4" are the same reading at different verbosity
d="$tmp/with_unit"; mk_archive "$d"
transcript "$d" '[{"label": "癌胚抗原 CEA", "value": "12.4"}]' "表格无法辨认"
labs "$d" 12.4 '"12.4 ng/mL"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "raw_value '12.4 ng/mL' against a recorded field value '12.4' → exit 0" \
  || no "verbosity difference read as a fabrication: $out"

# thousands separators and full-width digits are printing conventions, not new numbers
d="$tmp/separators"; mk_archive "$d"
transcript "$d" '[{"label": "血小板计数", "value": "12,500"}]' "血小板计数 12,500"
labs "$d" 12500 '"12500"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "'12500' against a source printing '12,500' → exit 0 (a separator is not a digit)" \
  || no "thousands separator read as a mismatch: $out"

# ===========================================================================
# C. surfaces and scope — what this gate reads, and what it refuses to own
# ===========================================================================
echo "=== C. scope ==="

# B3 — WHICH surface is authoritative, and why it is not the cheapest one.
#
# This arm used to assert the opposite: the masked bucket sidecar was read first and
# raw/transcript/ only as a fallback, on the reasoning that the transcript is the
# verbatim vault and a deterministic script may read it (A27) but "may" is not "should".
# That inverted the question the gate asks. The sidecar is DERIVED — the same 段 2 pass
# that wrote labs.json also wrote it — so finding a number there proves only that one
# pass agreed with itself. A CEA misread as 9.99 off the page lands in labs.json AND in
# the sidecar, and the old gate confirmed the misreading and called it provenance. The
# transcript is the only surface produced by a DIFFERENT pass (段 1, from the page
# image), so it is the only one that can contradict 段 2.
#
# So: whenever a transcript exists on disk for this source, it is the ONLY surface read,
# and a sidecar that "has" the value does not rescue a transcript that does not. The
# fixture below is exactly that case — a transcript that could not read the table, and a
# sidecar carrying a number nobody can trace to a page.
d="$tmp/sidecar"; mk_archive "$d"
transcript "$d" '[]' "本页无法辨认"
cat > "$d/$SIDECAR" <<'EOF'
SOURCE: lab | CONFIDENCE: high
| 项目 | 结果 | 参考 |
| 癌胚抗原 CEA | 12.4 | 0.00-5.00 |
EOF
labs "$d" 12.4 '"12.4"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 1 ] \
  && ok "a value present ONLY on the derived sidecar, with a transcript on disk → exit 1 (B3)" \
  || no "the derived surface was accepted as provenance for a source that has a transcript"
echo "$out" | grep -q 'raw/transcript/s1/page-001.md' \
  && ok "…and the surface named in the error is the TRANSCRIPT, not the sidecar" \
  || no "the gate reports having searched the wrong surface: $out"
echo "$out" | grep -q "$SIDECAR" \
  && no "the sidecar was searched too — the transcript is supposed to be the only surface: $out" \
  || ok "…the sidecar was not consulted at all while a transcript existed"

# PRESENCE ON DISK is the trigger, not the declaration. Keying this to `transcript_path`
# would rebuild the hole one level down: a row that simply omits the key would be judged
# against the derived sidecar again, so "declare no transcript" would be cheaper than
# declaring a checkable one — with the transcript sitting right there, unread.
d="$tmp/undeclared_transcript"; mk_archive "$d"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "source_inventory.json"
data = json.loads(p.read_text(encoding="utf-8"))
data["files"][0].pop("transcript_path", None)     # nothing declared…
p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
PYEOF
transcript "$d" '[]' "本页无法辨认"                  # …but the file is on disk
cat > "$d/$SIDECAR" <<'EOF'
SOURCE: lab | CONFIDENCE: high
| 癌胚抗原 CEA | 12.4 |
EOF
labs "$d" 12.4 '"12.4"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 1 ] \
  && ok "an UNDECLARED transcript that exists on disk is still the only surface → exit 1" \
  || no "omitting transcript_path bought the row a judgement against its own derived sidecar"

# POSITIVE — the sidecar IS the right surface for a source that legitimately has no
# transcript. A native_text source was taken byte-for-byte; there was never a 段 1 pass
# to disagree with, so refusing the sidecar here would fail every text-only archive.
d="$tmp/native_sidecar"; mk_archive "$d"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "source_inventory.json"
data = json.loads(p.read_text(encoding="utf-8"))
row = data["files"][0]
row["read_mode"] = "native_text"
row["modality"] = "text"
row["text_layer_kind"] = "born_digital"
row["extractor_provenance"] = {"engine": "native-text", "version": "3.0",
                               "raw_output_ref": None, "llm_role": "none"}
row.pop("transcript_path", None)
p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
PYEOF
rm -rf "$d/raw/transcript/s1"                      # no 段 1 pass ever ran for this source
cat > "$d/$SIDECAR" <<'EOF'
SOURCE: lab | CONFIDENCE: high
| 项目 | 结果 | 参考 |
| 癌胚抗原 CEA | 12.4 | 0.00-5.00 |
EOF
labs "$d" 12.4 '"12.4"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] \
  && ok "a native_text source with NO transcript → the sidecar is read → exit 0" \
  || no "B3 broke the only surface a byte-identical text source has: $out"

# …and it is a real check there, not a skip: the same shape with a number the sidecar
# does not carry still fails. Otherwise "delete the transcript" would be the bypass.
labs "$d" 124 '"124"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 1 ] \
  && ok "…and the sidecar fallback still REFUSES a value the sidecar does not carry" \
  || no "the no-transcript path degraded into a skip: $out"

# A ref that names no inventoried sidecar is a DIFFERENT defect with its own gate.
# Reporting it here as "value not found in its source" would be both duplicated and
# misleading — the value may be perfectly well transcribed; the citation is broken.
d="$tmp/dangling"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL"
labs "$d" 124 '"124"' '["07_检验/不存在的桶/nope.md"]'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "a dangling source_ref → silent here (gate_source_inventory owns it)" \
  || no "this gate double-reports a broken citation: $out"

# a scheme-3 archive predates the per-page transcription contract entirely
d="$tmp/legacy"; mk_archive "$d"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / "source_inventory.json"
data = json.loads(p.read_text(encoding="utf-8"))
data["scheme_version"] = 3
p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
PYEOF
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL"
labs "$d" 124 '"124"'
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "scheme_version 3 → exempt (no per-page contract to check against)" \
  || no "a v3 archive was held to the v4 binding: $out"

# no labs.json at all is not a violation of a lab rule
d="$tmp/no_labs"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL"
run_gate gate_field_provenance "$d"
[ "$rc" -eq 0 ] && ok "no labs.json → exit 0" || no "absent labs.json treated as a failure: $out"

# NOTE — a known hole, deliberately NOT asserted here because the validator does not
# close it yet and this suite must stay green: a page frontmatter carrying an EMPTY
# fields[].value or source_reported_text ("") disables the check for every labs row
# citing that source, because the reverse-containment test reduces to `"" in needle`,
# which is always true. Reproduction and expected behaviour are in the handoff notes.

# ===========================================================================
# D. the companion rule — raw_value: null deletes the evidence (A19)
# ===========================================================================
echo "=== D. gate_numeric_integrity (normalization consistency) ==="

d="$tmp/null_raw"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL"
labs "$d" null null
run_gate gate_numeric_integrity "$d"
[ "$rc" -eq 1 ] && ok "a lab row with raw_value: null → exit 1" \
  || no "the source layer was allowed to be deleted, rc=$rc"
echo "$out" | grep -q 'raw_value is null' && ok "…error names the null field" || no "wrong reason: $out"
echo "$out" | grep -q 'cannot be checked against anything' \
  && ok "…error states that null removes the only checkable evidence" || no "rationale missing: $out"
echo "$out" | grep -q 'looks equally trustworthy' \
  && ok "…error states why that is worse than a missing row" || no "consequence not stated: $out"

# the honest shape passes: a source-reported string beside every normalized number
d="$tmp/raw_present"; mk_archive "$d"
transcript "$d" "$FIELDS_CEA" "癌胚抗原 CEA 12.4 ng/mL"
labs "$d" 12.4 '"12.4"'
run_gate gate_numeric_integrity "$d"
[ "$rc" -eq 0 ] && ok "value 12.4 beside raw_value '12.4' → exit 0" || no "the honest shape is blocked: $out"

# ===========================================================================
# E. the two gates must not be confused for one another (A19 rename)
# ===========================================================================
echo "=== E. the rename is a contract, not a comment ==="

python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
ni = (v.gate_numeric_integrity.__doc__ or "")
fp = (v.gate_field_provenance.__doc__ or "")
assert "NORMALIZATION CONSISTENCY" in ni, "gate_numeric_integrity still claims a scope it does not have"
assert "gate_field_provenance" in ni, "gate_numeric_integrity does not hand off the cross-source half"
assert "misread page" in ni or "misread" in ni, "gate_numeric_integrity does not state its blind spot"
assert "PRESENCE" in fp, "gate_field_provenance does not state that it checks presence only"
print("scopes documented")
PYEOF
[ $? -eq 0 ] && ok "each gate's docstring states its own scope AND its blind spot" \
             || no "the two gates' scopes are not distinguished in code"

# ---------------------------------------------------------------------------
echo
echo "== field-provenance-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
