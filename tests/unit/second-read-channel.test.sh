#!/usr/bin/env bash
# tests/unit/second-read-channel.test.sh — organize v3, hard rule 3.
#
# `high_risk_review_status: passed_independent_reread` is a CLAIM about how a value
# was verified. The only thing that makes it true is a channel independent of the
# first read: a different modality (born-digital text layer / barcode / a parseable
# deterministic OCR run), a different model, or a human. Re-prompting the SAME model
# on the SAME image — including a cropped region — is a tie-break and never sets it.
#
# Without `reread_channel` the claim is self-certifying: the schema describes the
# rule, nothing enforces it, and a run can mark every high-risk field verified having
# read each one exactly once. So `passed_independent_reread` with reread_channel
# absent / `none` / off-enum is an ERROR, not advice.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

gate() {  # <patient_dir>  — row-level summary rules (gate_source_inventory)
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_source_inventory(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

hrf_gate() {  # <patient_dir>  — PER-FIELD rules (gate_high_risk_fields)
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_high_risk_fields(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# mk_hrf <dir> <text_layer_kind> <transcribe_model_id json literal>
#        <row high_risk_review_status> <row reread_channel> <high_risk_fields json array>
mk_hrf() {
  local d="$1"
  mkdir -p "$d/07_检验/血常规" "$d/raw/incoming" "$d/raw/transcript/s1" "$d/raw/_provenance/r1"
  : > "$d/raw/incoming/upload-001.pdf"
  printf -- '---\nsource_id: s1\npage: 1\n---\n# 全文\n白细胞计数 3.21\n' \
    > "$d/raw/transcript/s1/page-001.md"
  printf 'SOURCE: lab | CONFIDENCE: high\n白细胞计数 3.21\n' \
    > "$d/07_检验/血常规/2026-03-15_血常规.md"
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.pdf",
   "raw_path":"raw/incoming/upload-001.pdf","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab","text_layer_kind":"$2",
   "transcript_path":"raw/transcript/s1/page-001.md",
   "sidecar_path":"07_检验/血常规/2026-03-15_血常规.md","bucket_path":"07_检验/血常规",
   "modality":"text","read_mode":"model_vision_primary","transcribe_model_id":$3,
   "extractor_provenance":{"engine":"host-vision","version":"3.1","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"$4","reread_channel":"$5",
   "high_risk_fields":$6,
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

# mk_verdict <dir> <label> <verdict>
mk_verdict() {
  mkdir -p "$1/raw/_provenance/r1"
  cat > "$1/raw/_provenance/r1/human_sample_result.json" <<EOF
{"run_id":"r1","performed_by":"reviewer-1","performed_at":"2026-09-16T01:00:00Z",
 "verdicts":[{"source_id":"s1","page":1,"label":"$2","verdict":"$3"}]}
EOF
}

# <dir> <high_risk_review_status> <reread_channel json fragment, may be empty>
#
# The row carries `transcript_path` because fix spec A14 made it REQUIRED for any
# read_mode in {model_vision_primary, model_vision_assist} (schema if/then). That is not
# bookkeeping: omitting it used to short-circuit all three of gate_transcripts'
# assertions, so "no transcript declared" was strictly cheaper than "transcript declared
# and checkable". A fixture without it never reaches the channel rules this file is about.
mk() {
  local d="$1"
  mkdir -p "$d/07_检验/血常规" "$d/raw/incoming" "$d/raw/transcript/s1"
  : > "$d/raw/incoming/upload-001.pdf"
  printf -- '---\nsource_id: s1\npage: 1\n---\n# 全文\n白细胞计数 3.21\n' \
    > "$d/raw/transcript/s1/page-001.md"
  cat > "$d/07_检验/血常规/2026-03-15_血常规.md" <<'EOF'
SOURCE: lab | CONFIDENCE: high
| 项目 | 结果 | 参考 |
| 白细胞计数 | 3.21 | 3.50-9.50 |
EOF
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.pdf",
   "raw_path":"raw/incoming/upload-001.pdf","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab","text_layer_kind":"born_digital",
   "sidecar_path":"07_检验/血常规/2026-03-15_血常规.md","bucket_path":"07_检验/血常规",
   "transcript_path":"raw/transcript/s1/page-001.md",
   "modality":"text","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"$2"$3,
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

# ===========================================================================
# A. NEGATIVE — the claim without the channel
# ===========================================================================
echo "=== A. passed_independent_reread without an independent channel ==="

d="$tmp/no_channel"
mk "$d" passed_independent_reread ""
gate "$d"
[ "$rc" -eq 1 ] && ok "passed_independent_reread + reread_channel ABSENT → exit 1" \
  || no "self-certifying reread claim accepted, rc=$rc"
echo "$out" | grep -q 'passed_independent_reread but reread_channel' \
  && ok "…error names the missing channel" || no "wrong reason: $out"
echo "$out" | grep -q 'tie-break' \
  && ok "…error states that re-prompting the same model is only a tie-break" \
  || no "independence rule not stated: $out"
echo "$out" | grep -q 'needs_human_review' \
  && ok "…error says what the status must be instead when no channel was available" \
  || no "remedy not stated: $out"

d="$tmp/channel_none"
mk "$d" passed_independent_reread ',"reread_channel":"none"'
gate "$d"
[ "$rc" -eq 1 ] && ok "passed_independent_reread + reread_channel=none → exit 1" \
  || no "'none' channel accepted as independent, rc=$rc"
echo "$out" | grep -q "reread_channel is 'none'" \
  && ok "…error quotes the offending value" || no "value not quoted: $out"

# an off-enum channel is not a loophole either
d="$tmp/channel_bogus"
mk "$d" passed_independent_reread ',"reread_channel":"same_model_crop"'
gate "$d"
[ "$rc" -eq 1 ] && ok "an invented channel name → exit 1" || no "off-enum channel accepted, rc=$rc"
echo "$out" | grep -qE "schema violation|is not one of" \
  && ok "…rejected against the closed reread_channel enum" || no "enum not enforced: $out"

# ===========================================================================
# B. POSITIVE — every genuinely independent channel
# ===========================================================================
echo "=== B. a real independent channel ==="

for ch in text_layer barcode deterministic_ocr alternate_vision_model human; do
  d="$tmp/ok_$ch"
  mk "$d" passed_independent_reread ",\"reread_channel\":\"$ch\""
  gate "$d"
  [ "$rc" -eq 0 ] && ok "passed_independent_reread + reread_channel=$ch → exit 0" \
    || no "legal channel '$ch' rejected: $out"
done

# ===========================================================================
# C. the rule is scoped to the CLAIM, not to the field
# ===========================================================================
echo "=== C. scope ==="

# needs_human_review with reread_channel=none is an honest record, not a violation
d="$tmp/honest_none"
mk "$d" needs_human_review ',"reread_channel":"none"'
gate "$d"
[ "$rc" -eq 0 ] && ok "needs_human_review + reread_channel=none → exit 0 (an honest 'not verified')" \
  || no "honest unverified record wrongly blocked: $out"

# not_applicable likewise
d="$tmp/na"
mk "$d" not_applicable ""
gate "$d"
[ "$rc" -eq 0 ] && ok "not_applicable + no channel → exit 0" \
  || no "not_applicable wrongly blocked: $out"

# ===========================================================================
# E. PER-FIELD independence — high_risk_fields[] (fix spec A5 / A14)
# ===========================================================================
# The row-level word was a single verdict covering every high-risk field in a document,
# so 「passed」 could rest on one value found verbatim in a born-digital text layer while
# the handwritten dose beside it was read exactly once. The per-field array makes each
# claim carry its own channel, and these are the three ways a channel gets ASSERTED but
# does not exist.
echo "=== E. per-field high_risk_fields[] ==="

PASS_TL='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"text_layer","readings":[{"channel":"first_read","value":"3.21"},{"channel":"text_layer","value":"3.21"}]}]'

# E1 POSITIVE — text_layer on a born-digital page is a real modality
d="$tmp/hrf_tl_ok"; mk_hrf "$d" born_digital '"host-vision-3.1"' passed_independent_reread text_layer "$PASS_TL"
hrf_gate "$d"
[ "$rc" -eq 0 ] && ok "text_layer on a born_digital page → exit 0" || no "legal text_layer blocked: $out"

# E1b POSITIVE — not_applicable (a VCF / DICOM header: a deterministic adapter produced
# the characters, which is independent of any vision read)
d="$tmp/hrf_tl_na"; mk_hrf "$d" not_applicable '"host-vision-3.1"' passed_independent_reread text_layer "$PASS_TL"
hrf_gate "$d"
[ "$rc" -eq 0 ] && ok "text_layer on a not_applicable unit → exit 0 (deterministic adapter output)" \
  || no "not_applicable text_layer blocked: $out"

# E1c NEGATIVE — absent / embedded_ocr are the same image read twice
for tlk in absent embedded_ocr; do
  d="$tmp/hrf_tl_$tlk"; mk_hrf "$d" "$tlk" '"host-vision-3.1"' passed_independent_reread text_layer "$PASS_TL"
  hrf_gate "$d"
  [ "$rc" -eq 1 ] && ok "text_layer on a $tlk page → exit 1 (impossible channel)" \
    || no "$tlk was accepted as an independent text layer, rc=$rc"
done
echo "$out" | grep -q 'same image twice' \
  && ok "…error says why (a scanner's own OCR of the same pixels is a tie-break)" \
  || no "rationale absent: $out"

# E2 NEGATIVE — alternate_vision_model with no second model id is unfalsifiable
AVM_NOID='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"alternate_vision_model"}]'
d="$tmp/hrf_avm_noid"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread alternate_vision_model "$AVM_NOID"
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "alternate_vision_model with no reread_model_id → exit 1" \
  || no "an unfalsifiable independence claim was accepted, rc=$rc"
echo "$out" | grep -q 'not even falsifiable' && ok "…error names what is missing" || no "wrong reason: $out"

# E2b NEGATIVE — the SAME model re-prompted on the same image
AVM_SAME='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"alternate_vision_model","reread_model_id":"host-vision-3.1"}]'
d="$tmp/hrf_avm_same"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread alternate_vision_model "$AVM_SAME"
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "reread_model_id == transcribe_model_id → exit 1 (a crop is still a tie-break)" \
  || no "one model twice was accepted as two channels, rc=$rc"
echo "$out" | grep -q 'SAME model' && ok "…error names the identity" || no "wrong reason: $out"

# E2c NEGATIVE — a different model, but the FIRST read's model id was never recorded
AVM_OK='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"alternate_vision_model","reread_model_id":"other-vision-2.0"}]'
d="$tmp/hrf_avm_nofirst"; mk_hrf "$d" absent 'null' passed_independent_reread alternate_vision_model "$AVM_OK"
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "no transcribe_model_id on the row → exit 1 (nothing to differ FROM)" \
  || no "a second model with no first model was accepted, rc=$rc"

# E2d POSITIVE — two genuinely different models
d="$tmp/hrf_avm_ok"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread alternate_vision_model "$AVM_OK"
hrf_gate "$d"
[ "$rc" -eq 0 ] && ok "a different reread_model_id → exit 0" || no "two distinct models blocked: $out"

# E3 NEGATIVE — `human` with no record of the human
HUMAN='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"human"}]'
d="$tmp/hrf_human_bare"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread human "$HUMAN"
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "reread_channel=human with no human_sample_result.json → exit 1" \
  || no "「人工核对过」 was accepted with nothing behind it, rc=$rc"
echo "$out" | grep -q 'not a no-channel placeholder' \
  && ok "…error refuses human as a polite spelling of no-channel" || no "wrong reason: $out"

# E3b NEGATIVE — a verdict exists, but for a DIFFERENT field
d="$tmp/hrf_human_other"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread human "$HUMAN"
mk_verdict "$d" "报告日期" match
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "a verdict for another field does not verify this one → exit 1" \
  || no "an unrelated verdict satisfied the human channel, rc=$rc"

# E3c POSITIVE — the matching verdict exists
d="$tmp/hrf_human_ok"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread human "$HUMAN"
mk_verdict "$d" "白细胞计数" match
hrf_gate "$d"
[ "$rc" -eq 0 ] && ok "reread_channel=human + a matching verdict → exit 0" \
  || no "a recorded human read was rejected: $out"

# E4 NEGATIVE — the row-level summary must be DERIVED, not asserted
MIXED='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"text_layer"},{"label":"报告日期","status":"needs_human_review","reread_channel":"none"}]'
d="$tmp/hrf_derived"; mk_hrf "$d" born_digital '"host-vision-3.1"' passed_independent_reread text_layer "$MIXED"
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "row says passed while a field says needs_human_review → exit 1" \
  || no "a summary contradicting its own rows was accepted, rc=$rc"
echo "$out" | grep -q 'DERIVED' \
  && ok "…error states the row is a derived summary, not an independent assertion" \
  || no "derivation rule not stated: $out"

# E4b POSITIVE — the honest derivation of the same array
d="$tmp/hrf_derived_ok"; mk_hrf "$d" born_digital '"host-vision-3.1"' needs_human_review text_layer "$MIXED"
hrf_gate "$d"
[ "$rc" -eq 0 ] && ok "the same array summarised as needs_human_review → exit 0" \
  || no "the honest derivation was blocked: $out"

# E5 NEGATIVE — a field claiming passed with channel `none`
NONE='[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"none"}]'
d="$tmp/hrf_none"; mk_hrf "$d" absent '"host-vision-3.1"' passed_independent_reread none "$NONE"
hrf_gate "$d"
[ "$rc" -eq 1 ] && ok "a FIELD claiming passed with reread_channel=none → exit 1" \
  || no "a self-certifying field claim was accepted, rc=$rc"

# E5b POSITIVE — no high-risk fields at all derives to not_applicable
d="$tmp/hrf_empty"; mk_hrf "$d" born_digital '"host-vision-3.1"' not_applicable none '[]'
hrf_gate "$d"
[ "$rc" -eq 0 ] && ok "no high-risk fields → not_applicable + none → exit 0" \
  || no "an empty high_risk_fields[] was flagged: $out"

# ===========================================================================
# D. schema-level assertions on the source_inventory contract
# ===========================================================================
echo "=== D. source_inventory.schema.json ==="

schema_says() {  # <grep-pattern> <label>
  grep -q "$1" "$ORG/references/schemas/source_inventory.schema.json" \
    && ok "$2" || no "$2 — not found in source_inventory.schema.json"
}
schema_says '"reread_channel"' "schema declares reread_channel"
schema_says 'alternate_vision_model' "schema enumerates alternate_vision_model as a channel"
schema_says 'tie-break' "schema records that the same model on the same image is a tie-break"

# and the gate's channel vocabulary is the schema's, not a private copy that can drift
python3 - "$ORG" <<'PYEOF'
import sys, json, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
schema = json.loads(
    (pathlib.Path(sys.argv[1]) / "references/schemas/source_inventory.schema.json")
    .read_text(encoding="utf-8"))
enum = set(schema["properties"]["files"]["items"]["properties"]["reread_channel"]["enum"])
assert enum == v.REREAD_CHANNELS, f"gate {sorted(v.REREAD_CHANNELS)} != schema {sorted(enum)}"
print("channel vocabulary in sync")
PYEOF
[ $? -eq 0 ] && ok "gate REREAD_CHANNELS is in sync with the schema enum (no silent drift)" \
             || no "gate and schema disagree on the channel vocabulary"

# ---------------------------------------------------------------------------
echo
echo "== second-read-channel: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
