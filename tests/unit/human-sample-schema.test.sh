#!/usr/bin/env bash
# tests/unit/human-sample-schema.test.sh — organize v3→v4 fix spec B11 (+ B1 末段, A4).
#
# A4 split the human spot-check into an ASK and an ANSWER. B11 is the follow-up that
# makes the split mean something: two files, each with its OWN schema, and a verdict
# vocabulary that is CLOSED.
#
# The reason is that the split alone bought nothing. Before B11 the two provenance
# artifacts were the only ones gate_human_sample read by hand — no schema, no enum, no
# shape check — so the gate saw whatever the writer felt like writing. `sample` could be
# a list of bare strings, and every keyed lookup below it quietly matched nothing.
# `verdicts[].verdict` could be 「ok」, 「通过」, 「n/a」, or a typo — and the ONLY
# arithmetic the gate did on that field was `verdict == "mismatch"`, so anything
# unrecognised counted as *not a mismatch*, i.e. silently as a PASS. A checker who could
# not make out the cell, or a script that wrote the wrong word, produced an archive that
# reads downstream as human-verified. That is the precise failure the spot-check exists
# to catch, arriving through the spot-check's own front door.
#
# So this file asserts, in both directions:
#
#   1. The two schema FILES exist AND the validator actually loads them. A schema
#      sitting in references/schemas/ that nothing validates against is documentation,
#      not a gate — and it is indistinguishable from one that works until the day it
#      matters, so the binding is asserted statically (the call site) and behaviourally
#      (a bad document is rejected).
#   2. They are TWO schemas, not one file copied twice. The plan is written by a
#      script and requires `sample[]` + `rule`; the result is written by a person and
#      requires `verdicts[]` + `performed_by` + `performed_at`. If either document
#      validated under the other's schema, the split would be cosmetic: one pass could
#      emit both halves in the same shape and nothing would notice.
#   3. `verdict` is a CLOSED set of exactly three words, and the error says which
#      three. A misspelling (`mismached`) must be louder than a mismatch, not quieter:
#      the mismatch is counted, the misspelling used to vanish. `unreadable` is the
#      load-bearing third value and must be ACCEPTED (it is not a mismatch) while never
#      being a silent pass.
#   4. (B1 末段) The plan is MANDATORY the moment any source carries a deterministic
#      high-risk field. Keying the gate off 「a plan file happens to exist」 made the
#      whole check opt-in — no plan, no result required, no error — so the cheapest way
#      to pass the human spot-check was never to start one. The trigger is the
#      denominator recomputed from the archive's own page frontmatter, and the positive
#      arm asserts the converse: an archive with no high-risk field anywhere is NOT
#      accused of skipping a sample it never owed.
#   5. (A4) Two mismatches make the archive NOT DELIVERABLE, and the error says those
#      words rather than merely flagging a field.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"
SCHEMA_DIR="$ORG/references/schemas"

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
  set +e
}

# Validate one JSON document against one named schema THROUGH the validator's own
# loader (validate_doc_schema), not through a private jsonschema call — so the test
# exercises the same resolution path, the same legacy-relaxation branch and the same
# error formatting the gate will use in production.
run_schema() {  # <json_file> <schema_name>
  set +e
  out="$(python3 - "$ORG" "$1" "$2" <<'PYEOF'
import sys, json, importlib, pathlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
doc = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
errs = []
v.validate_doc_schema(pathlib.Path(sys.argv[2]).name, doc, sys.argv[3], errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set +e
}

mk_archive() {  # <dir> — a scheme-4 archive with no rows (so only this gate speaks)
  local d="$1"
  mkdir -p "$d/raw/_provenance/run-001"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[] }
EOF
}

plan() {  # <dir> <sample[] body>
  cat > "$1/raw/_provenance/run-001/human_sample_plan.json" <<EOF
{ "run_id":"run-001",
  "seed":"sha256(PT-0E11 + sorted(field keys))",
  "rule":"每患者 ≥3 个高风险字段或全部高风险字段的 5%，取大者",
  "sample":[$2] }
EOF
}

result() {  # <dir> <verdicts[] body>
  cat > "$1/raw/_provenance/run-001/human_sample_result.json" <<EOF
{ "run_id":"run-001","performed_by":"护士 A","performed_at":"2026-09-16T10:00:00Z",
  "verdicts":[$2] }
EOF
}

S1='{"source_id":"s1","page":1,"label":"白细胞计数","bbox":[0.10,0.20,0.34,0.24],"transcript_value":"3.21"}'
S2='{"source_id":"s1","page":2,"label":"血红蛋白","bbox":[0.11,0.51,0.38,0.56],"transcript_value":"118"}'
V1_MATCH='{"source_id":"s1","page":1,"label":"白细胞计数","verdict":"match"}'
V2_MATCH='{"source_id":"s1","page":2,"label":"血红蛋白","verdict":"match"}'

# ===========================================================================
# A. the two schemas exist, and the validator really loads them
# ===========================================================================
echo "=== A. the schema files are wired into gate_human_sample ==="

[ -f "$SCHEMA_DIR/human_sample_plan.schema.json" ] \
  && ok "references/schemas/human_sample_plan.schema.json exists" \
  || no "the plan schema file is missing"
[ -f "$SCHEMA_DIR/human_sample_result.schema.json" ] \
  && ok "references/schemas/human_sample_result.schema.json exists" \
  || no "the result schema file is missing"

# Static binding: the constants point at those filenames AND gate_human_sample's own
# source text validates BOTH documents against them. A schema nobody calls is a file,
# not a check, and grepping the module globals alone would not tell the two apart.
set +e
bind="$(python3 - "$ORG" <<'PYEOF'
import sys, inspect, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
src = inspect.getsource(v.gate_human_sample)
print("PLAN_CONST", v.HUMAN_SAMPLE_PLAN_SCHEMA)
print("RESULT_CONST", v.HUMAN_SAMPLE_RESULT_SCHEMA)
print("PLAN_CALL", int("HUMAN_SAMPLE_PLAN_SCHEMA" in src and "validate_doc_schema" in src))
print("RESULT_CALL", int("HUMAN_SAMPLE_RESULT_SCHEMA" in src))
print("VERDICTS", " ".join(sorted(v.HUMAN_SAMPLE_VERDICTS)))
PYEOF
)"
set +e
echo "$bind" | grep -q '^PLAN_CONST human_sample_plan.schema.json$' \
  && ok "HUMAN_SAMPLE_PLAN_SCHEMA names the plan schema file" || no "plan constant wrong: $bind"
echo "$bind" | grep -q '^RESULT_CONST human_sample_result.schema.json$' \
  && ok "HUMAN_SAMPLE_RESULT_SCHEMA names the result schema file" || no "result constant wrong: $bind"
echo "$bind" | grep -q '^PLAN_CALL 1$' \
  && ok "gate_human_sample validates the PLAN against its schema (not merely imports it)" \
  || no "the plan schema is never passed to validate_doc_schema: $bind"
echo "$bind" | grep -q '^RESULT_CALL 1$' \
  && ok "gate_human_sample validates the RESULT against its schema" \
  || no "the result schema is never used inside the gate: $bind"
echo "$bind" | grep -q '^VERDICTS match mismatch unreadable$' \
  && ok "HUMAN_SAMPLE_VERDICTS is exactly {match, mismatch, unreadable}" \
  || no "the verdict vocabulary is not the closed three-value set: $bind"

# ===========================================================================
# B. two schemas, not one file twice
# ===========================================================================
echo "=== B. plan and result are governed by DIFFERENT schemas ==="

set +e
diffout="$(python3 - "$SCHEMA_DIR" <<'PYEOF'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
p = json.loads((d / "human_sample_plan.schema.json").read_text(encoding="utf-8"))
r = json.loads((d / "human_sample_result.schema.json").read_text(encoding="utf-8"))
pr, rr = set(p.get("required", [])), set(r.get("required", []))
print("SAME_ID", int(p.get("$id") == r.get("$id")))
print("SAME_REQUIRED", int(pr == rr))
print("PLAN_REQ_OK", int({"sample", "rule"} <= pr))
print("RESULT_REQ_OK", int({"verdicts", "performed_by", "performed_at"} <= rr))
print("PLAN_HAS_VERDICTS", int("verdicts" in p.get("properties", {})))
print("RESULT_HAS_SAMPLE", int("sample" in r.get("properties", {})))
enum = r["properties"]["verdicts"]["items"]["properties"]["verdict"].get("enum")
print("ENUM", " ".join(enum or []))
PYEOF
)"
set +e
echo "$diffout" | grep -q '^SAME_ID 0$' \
  && ok "the two schemas carry different \$id (they are not the same document)" \
  || no "plan and result schema share an \$id: $diffout"
echo "$diffout" | grep -q '^SAME_REQUIRED 0$' \
  && ok "…and different required[] sets" || no "identical required sets: $diffout"
echo "$diffout" | grep -q '^PLAN_REQ_OK 1$' \
  && ok "plan schema requires sample[] + rule (the ASK: what must be checked, chosen how)" \
  || no "plan schema does not require sample/rule: $diffout"
echo "$diffout" | grep -q '^RESULT_REQ_OK 1$' \
  && ok "result schema requires verdicts[] + performed_by + performed_at (the ANSWER, attributed and dated)" \
  || no "result schema does not require verdicts/performed_by/performed_at: $diffout"
echo "$diffout" | grep -q '^PLAN_HAS_VERDICTS 0$' \
  && ok "the plan schema has no verdicts[] — a script may not record the answer it asked for" \
  || no "the plan schema also defines verdicts[]: $diffout"
echo "$diffout" | grep -q '^RESULT_HAS_SAMPLE 0$' \
  && ok "the result schema has no sample[] — a person may not redraw the sample they answered" \
  || no "the result schema also defines sample[]: $diffout"
echo "$diffout" | grep -q '^ENUM match mismatch unreadable$' \
  && ok "the schema's verdict enum is the same closed three-value set" \
  || no "schema enum is not match|mismatch|unreadable: $diffout"

# POSITIVE: each half validates under its OWN schema.
d="$tmp/schema_pos"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MATCH,$V2_MATCH"
run_schema "$d/raw/_provenance/run-001/human_sample_plan.json" human_sample_plan.schema.json
[ "$rc" -eq 0 ] && ok "a well-formed plan passes human_sample_plan.schema.json → exit 0" \
  || no "a valid plan was rejected by its own schema: $out"
run_schema "$d/raw/_provenance/run-001/human_sample_result.json" human_sample_result.schema.json
[ "$rc" -eq 0 ] && ok "a well-formed result passes human_sample_result.schema.json → exit 0" \
  || no "a valid result was rejected by its own schema: $out"

# NEGATIVE: neither half validates under the OTHER's schema. If they did, one pass
# could emit both files in one shape and the split would be cosmetic.
run_schema "$d/raw/_provenance/run-001/human_sample_plan.json" human_sample_result.schema.json
[ "$rc" -eq 1 ] && ok "the plan FAILS the result schema (no verdicts/performed_by/performed_at)" \
  || no "the plan validated as a result — the two schemas are interchangeable, rc=$rc"
echo "$out" | grep -q "verdicts" \
  && ok "…error names the answer-half field the plan cannot supply" || no "wrong reason: $out"
run_schema "$d/raw/_provenance/run-001/human_sample_result.json" human_sample_plan.schema.json
[ "$rc" -eq 1 ] && ok "the result FAILS the plan schema (no sample/rule)" \
  || no "the result validated as a plan, rc=$rc"
echo "$out" | grep -qE "sample|rule" \
  && ok "…error names the ask-half field the result cannot supply" || no "wrong reason: $out"

# ===========================================================================
# C. the verdict vocabulary is CLOSED — a typo must be louder than a mismatch
# ===========================================================================
echo "=== C. verdict enum ==="

# The headline case. `mismached` is one keystroke from `mismatch`, and before B11 the
# difference between them was the difference between「不可交付」and「通过」: the gate
# only ever tested `== "mismatch"`, so the typo scored as *not a mismatch*.
d="$tmp/typo"; mk_archive "$d"
plan   "$d" "$S1"
result "$d" '{"source_id":"s1","page":1,"label":"白细胞计数","verdict":"mismached"}'
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "verdict 'mismached' (misspelt) → exit 1" \
  || no "a misspelt verdict passed silently as 'not a mismatch', rc=$rc"
echo "$out" | grep -q "'mismached'" \
  && ok "…error quotes the unrecognised value verbatim" || no "value not quoted: $out"
echo "$out" | grep -q "match" && echo "$out" | grep -q "mismatch" && echo "$out" | grep -q "unreadable" \
  && ok "…error lists the legal enum match|mismatch|unreadable" \
  || no "the legal vocabulary is not shown to the writer: $out"
echo "$out" | grep -q "is not one of" \
  && ok "…and the schema layer rejects it too (enum violation, not only the gate's own check)" \
  || no "no schema-level enum rejection: $out"
echo "$out" | grep -q "counted as" \
  && ok "…error states WHY an unrecognised verdict is dangerous (it reads as a pass)" \
  || no "rationale missing: $out"

# The plausible-sounding near-misses fail the same way. These are what a hurried
# reviewer or a helpful script actually writes.
for bad in ok pass 通过 n/a MATCH; do
  d="$tmp/bad_$(echo -n "$bad" | od -An -tx1 | tr -d ' \n')"; mk_archive "$d"
  plan   "$d" "$S1"
  result "$d" "{\"source_id\":\"s1\",\"page\":1,\"label\":\"白细胞计数\",\"verdict\":\"$bad\"}"
  run_gate gate_human_sample "$d"
  [ "$rc" -eq 1 ] && ok "verdict '$bad' → exit 1 (the set is closed, and case-sensitive)" \
    || no "verdict '$bad' accepted, rc=$rc"
done

# POSITIVE: all three legal values are accepted, and `unreadable` in particular is
# neither a mismatch (it must not condemn the run) nor silently a pass.
for good in match unreadable; do
  d="$tmp/good_$good"; mk_archive "$d"
  plan   "$d" "$S1"
  result "$d" "{\"source_id\":\"s1\",\"page\":1,\"label\":\"白细胞计数\",\"verdict\":\"$good\"}"
  run_gate gate_human_sample "$d"
  [ "$rc" -eq 0 ] && ok "verdict '$good' → exit 0" || no "legal verdict '$good' rejected: $out"
done

# two `unreadable` verdicts are NOT two mismatches — the third value exists so that
# 「我看不清」 has an honest home, not so it can be laundered into a failure either way
d="$tmp/two_unreadable"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" '{"source_id":"s1","page":1,"label":"白细胞计数","verdict":"unreadable"},{"source_id":"s1","page":2,"label":"血红蛋白","verdict":"unreadable"}'
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "2 × unreadable → exit 0 (unreadable is not mismatch)" \
  || no "unreadable was counted toward the deliverability threshold: $out"

# and a `sample[]` of bare strings — the shape the hand-rolled gate silently skipped
d="$tmp/scalar_sample"; mk_archive "$d"
cat > "$d/raw/_provenance/run-001/human_sample_plan.json" <<'EOF'
{ "run_id":"run-001","rule":"5%","sample":["白细胞计数","血红蛋白"] }
EOF
result "$d" "$V1_MATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "plan whose sample[] holds bare strings → exit 1 (schema shape, not a silent skip)" \
  || no "a malformed sample[] was skipped rather than rejected, rc=$rc"
echo "$out" | grep -q "schema violation" \
  && ok "…and the rejection comes from the schema layer" || no "no schema violation reported: $out"

# ===========================================================================
# D. (B1 末段) the plan is owed whenever the DENOMINATOR is non-empty
# ===========================================================================
echo "=== D. deterministic high-risk set D non-empty → human_sample_plan.json REQUIRED ==="

# <dir> <fields json array> — one transcribed source whose page frontmatter is the
# only honest statement of what fields the archive actually read.
mk_denominator_archive() {
  local d="$1" fields="$2"
  mkdir -p "$d/raw/transcript/s1" "$d/07_检验/血常规"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"u.pdf","raw_path":"raw/incoming/u.pdf",
   "page_range":null,"kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent","sidecar_path":"07_检验/血常规/a.md","bucket_path":"07_检验/血常规",
   "modality":"image","read_mode":"model_vision_primary","transcribe_model_id":"host-vision-1",
   "transcript_path":"raw/transcript/s1/page-001.md",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"not_applicable","adapter":"pdf_pages","persist":true} ]}
EOF
  cat > "$d/raw/transcript/s1/page-001.md" <<EOF
---
source_id: s1
page: 1
page_total: 1
fields: $fields
---
# 全文
（页面正文）
EOF
}

# NEGATIVE: the page itself declares 白细胞计数 / 血红蛋白. No plan was ever written,
# so under the old artifact-keyed trigger the gate said nothing at all.
d="$tmp/owed_plan"
mk_denominator_archive "$d" '[{"label": "白细胞计数", "value": "3.21"}, {"label": "血红蛋白", "value": "118"}]'
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "high-risk fields on the page, no human_sample_plan.json → exit 1" \
  || no "the human spot-check was skippable by never starting one, rc=$rc"
echo "$out" | grep -q "human_sample_plan.json" \
  && ok "…error names the file that was never written" || no "file not named: $out"
echo "$out" | grep -q "high-risk field" \
  && ok "…error reports the recomputed denominator, not the run's own claim" \
  || no "denominator not reported: $out"
echo "$out" | grep -q "not a feature a run may decline" \
  && ok "…error states that the sample is not optional" || no "rule not stated: $out"
echo "$out" | grep -q "plan_second_read.py" \
  && ok "…error names the script that writes the plan" || no "remedy missing: $out"

# POSITIVE: an archive whose pages carry no high-risk label at all owes no plan. Without
# this arm the rule above is indistinguishable from 「always demand a plan」, which would
# make every clean archive un-deliverable and get the gate disabled within a week.
d="$tmp/owes_nothing"
mk_denominator_archive "$d" '[{"label": "检查机构", "value": "示例医院"}, {"label": "标本类型", "value": "静脉血"}]'
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "no high-risk label on any page, no plan → exit 0 (nothing was owed)" \
  || no "a clean archive was accused of skipping a sample it never owed: $out"

# and once the plan exists, the demand is satisfied — the trigger is the denominator,
# the remedy is the artifact
d="$tmp/owed_and_paid"
mk_denominator_archive "$d" '[{"label": "白细胞计数", "value": "3.21"}]'
mkdir -p "$d/raw/_provenance/run-001"
plan   "$d" "$S1"
result "$d" "$V1_MATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "same archive WITH a plan and a covering verdict → exit 0" \
  || no "a satisfied demand still fired: $out"

# ===========================================================================
# E. (A4) mismatch >= 2 → the archive is NOT DELIVERABLE
# ===========================================================================
echo "=== E. two human-verified mismatches ==="

V1_MIS='{"source_id":"s1","page":1,"label":"白细胞计数","verdict":"mismatch","observed_value":"8.21"}'
V2_MIS='{"source_id":"s1","page":2,"label":"血红蛋白","verdict":"mismatch","observed_value":"148"}'

d="$tmp/two_mismatch"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MIS,$V2_MIS"
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "2 mismatches → exit 1" || no "mismatch>=2 accepted, rc=$rc"
echo "$out" | grep -q "not deliverable" \
  && ok "…error says NOT DELIVERABLE (a whole-archive verdict, not a per-field flag)" \
  || no "deliverability verdict missing: $out"
echo "$out" | grep -q "2 human-verified MISMATCHES" \
  && ok "…error counts them" || no "count missing: $out"
echo "$out" | grep -q "白细胞计数" \
  && ok "…and names the offending cells" || no "cells not named: $out"
echo "$out" | grep -q "unmeasured error rate" \
  && ok "…error explains the inference (the unsampled pages carry the same error rate)" \
  || no "inference not stated: $out"

# one mismatch is a field to re-read, not a failed run — the threshold must be a
# threshold, otherwise the honest reviewer who reports a single defect is punished
# harder than the one who reports none
d="$tmp/one_mismatch"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MIS,$V2_MATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "exactly 1 mismatch → exit 0 (a defect to fix, not an undeliverable archive)" \
  || no "the threshold fires at one mismatch: $out"

# a misspelt verdict must NOT be able to buy its way under the threshold: a run with one
# real mismatch and one 'mismached' is rejected for the typo, never silently for being
# "one short of two"
d="$tmp/typo_under_threshold"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MIS,{\"source_id\":\"s1\",\"page\":2,\"label\":\"血红蛋白\",\"verdict\":\"mismached\"}"
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "1 mismatch + 1 'mismached' → exit 1 (a typo cannot dilute the count)" \
  || no "a misspelling kept the archive under the deliverability threshold, rc=$rc"
echo "$out" | grep -q "'mismached'" \
  && ok "…and the typo is reported rather than absorbed" || no "typo not surfaced: $out"

# ---------------------------------------------------------------------------
echo
echo "== human-sample-schema: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
