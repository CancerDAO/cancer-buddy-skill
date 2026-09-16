#!/usr/bin/env bash
# tests/unit/human-sample-gate.test.sh — organize v3→v4 fix spec A4.
#
# The human spot-check used to live in ONE file. That single file was written at the
# end of the run, by the run, and it contained both the sample that was drawn and the
# verdicts on it. Which means 「人工抽查通过」 was self-certifying: the pass that
# transcribed the pages also chose which fields a human would look at and also recorded
# what the human saw. Nothing in that loop could ever disagree with itself, so the
# check cost nothing and proved nothing — the most expensive-sounding line in the DoD
# was the cheapest one to satisfy.
#
# A4 splits it in two, and the split is the entire mechanism:
#   * raw/_provenance/<run>/human_sample_plan.json — written by a SCRIPT, from a seed
#     the run cannot influence (A36: sha256(patient_code + sorted field keys), with no
#     run_id in it, so re-running until the sample looks easy is not a strategy).
#   * raw/_provenance/<run>/human_sample_result.json — written by a PERSON, carrying
#     performed_by / performed_at and one verdict per planned item.
#
# From that split three rules follow, and this file asserts each of them in both
# directions, because a gate that only fires on the broken case is indistinguishable
# from a gate that never runs:
#
#   1. A plan with no result is an UNFINISHED check, not a passed one. Silence must
#      never be cheaper than a recorded verdict.
#   2. Every planned item needs a verdict. A partial result — the three fields that
#      happened to agree, with the two awkward ones dropped — is WORSE than no
#      sampling at all, because downstream it reads as a completed spot-check.
#   3. mismatch >= 2 makes the archive NOT DELIVERABLE. One mismatch is a field to
#      re-read. Two say the transcription pass is unreliable on this material, and the
#      pages nobody sampled carry the same unmeasured error rate — so patching the
#      sampled fields and shipping is precisely the wrong repair.
#
# And the companion binding (A5, gate_high_risk_fields): a field whose
# `reread_channel` is `human` must point at a real verdict. `human` is a claim that a
# person read this value off the original; without the record of them doing it, it is
# the no-channel placeholder wearing the strongest-sounding word in the enum.
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

# A scheme-4 archive with no rows: gate_human_sample never reads the inventory except
# to learn that this is NOT a legacy v3 archive (which would exempt it wholesale).
mk_archive() {  # <dir>
  local d="$1"
  mkdir -p "$d/raw/_provenance/run-001"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[] }
EOF
}

plan() {  # <dir> <json array body for sample[]>
  cat > "$1/raw/_provenance/run-001/human_sample_plan.json" <<EOF
{ "run_id":"run-001",
  "rule":"seed=sha256(patient_code + sorted(field keys)); 5% of high-risk fields, min 3",
  "sample":[$2] }
EOF
}

result() {  # <dir> <json array body for verdicts[]>
  cat > "$1/raw/_provenance/run-001/human_sample_result.json" <<EOF
{ "run_id":"run-001","performed_by":"护士 A","performed_at":"2026-09-16T10:00:00Z",
  "verdicts":[$2] }
EOF
}

S1='{"source_id":"s1","page":1,"label":"白细胞计数","bbox":[0.10,0.20,0.34,0.24],"transcript_value":"3.21"}'
S2='{"source_id":"s1","page":2,"label":"给药剂量","bbox":[0.11,0.51,0.38,0.56],"transcript_value":"135 mg"}'
V1_MATCH='{"source_id":"s1","page":1,"label":"白细胞计数","verdict":"match"}'
V2_MATCH='{"source_id":"s1","page":2,"label":"给药剂量","verdict":"match"}'
V1_MISMATCH='{"source_id":"s1","page":1,"label":"白细胞计数","verdict":"mismatch","note":"页面读作 3.21，实为 8.21"}'
V2_MISMATCH='{"source_id":"s1","page":2,"label":"给药剂量","verdict":"mismatch","note":"135 mg vs 185 mg"}'

# ===========================================================================
# A. NEGATIVE — the ASK recorded as if it were the ANSWER
# ===========================================================================
echo "=== A. a plan with no result ==="

d="$tmp/plan_only"; mk_archive "$d"
plan "$d" "$S1"
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "human_sample_plan.json without human_sample_result.json → exit 1" \
  || no "an unfinished spot-check passed, rc=$rc"
echo "$out" | grep -q 'human_sample_result.json does not' \
  && ok "…error names the missing result file" || no "wrong reason: $out"
echo "$out" | grep -q 'the plan is the ASK, not the' \
  && ok "…error states that a plan is not a verdict" || no "rule not stated: $out"

# ===========================================================================
# B. POSITIVE — a complete, clean spot-check
# ===========================================================================
echo "=== B. verdicts covering the whole plan, 0 mismatches ==="

d="$tmp/complete"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MATCH,$V2_MATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "every planned item has a match verdict → exit 0" \
  || no "a complete clean spot-check was wrongly blocked: $out"

# and an archive that never planned a sample is not retroactively accused of one
d="$tmp/no_plan"; mk_archive "$d"
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "no human_sample_plan.json at all → exit 0 (this gate audits the plan it finds)" \
  || no "gate invented a plan that was never written: $out"

# ===========================================================================
# C. NEGATIVE — a result that covers only the convenient half
# ===========================================================================
echo "=== C. partial verdicts ==="

d="$tmp/partial"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "2 planned items, 1 verdict → exit 1" \
  || no "a partial spot-check read as complete, rc=$rc"
echo "$out" | grep -q "p2 '给药剂量' has no verdict" \
  && ok "…error names the planned item that was skipped" || no "skipped item not named: $out"
echo "$out" | grep -q 'happened to agree' \
  && ok "…error states why a partial result is worse than none" || no "rationale missing: $out"

# attribution is part of the record: an unsigned, undated result is not one
d="$tmp/unattributed"; mk_archive "$d"
plan "$d" "$S1"
cat > "$d/raw/_provenance/run-001/human_sample_result.json" <<EOF
{ "run_id":"run-001","verdicts":[$V1_MATCH] }
EOF
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "result with no performed_by/performed_at → exit 1" \
  || no "an unattributed human check accepted, rc=$rc"
echo "$out" | grep -q 'performed_by' && ok "…error names performed_by" || no "performed_by not named: $out"
echo "$out" | grep -q 'performed_at' && ok "…error names performed_at" || no "performed_at not named: $out"

# ===========================================================================
# D. the mismatch threshold — 1 is a defect, 2 is a verdict on the whole run
# ===========================================================================
echo "=== D. mismatch >= 2 ==="

d="$tmp/one_mismatch"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MISMATCH,$V2_MATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 0 ] && ok "exactly 1 mismatch → exit 0 (a field to re-read, not a failed run)" \
  || no "the threshold fires at one mismatch: $out"

d="$tmp/two_mismatch"; mk_archive "$d"
plan   "$d" "$S1,$S2"
result "$d" "$V1_MISMATCH,$V2_MISMATCH"
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "2 mismatches → exit 1" || no "mismatch>=2 accepted, rc=$rc"
echo "$out" | grep -q 'not deliverable' \
  && ok "…error says the archive is NOT DELIVERABLE (not merely flagged)" \
  || no "deliverability verdict missing: $out"
echo "$out" | grep -q '2 human-verified MISMATCHES' \
  && ok "…error counts the mismatches" || no "count missing: $out"
echo "$out" | grep -q 'do not patch the sampled fields and ship' \
  && ok "…error rules out the wrong repair (patch the sampled fields only)" \
  || no "remedy not stated: $out"

# the threshold counts ACROSS runs — two runs with one mismatch each is still two
d="$tmp/two_runs"; mk_archive "$d"
mkdir -p "$d/raw/_provenance/run-002"
plan   "$d" "$S1"
result "$d" "$V1_MISMATCH"
cat > "$d/raw/_provenance/run-002/human_sample_plan.json" <<EOF
{ "run_id":"run-002","rule":"seed","sample":[$S2] }
EOF
cat > "$d/raw/_provenance/run-002/human_sample_result.json" <<EOF
{ "run_id":"run-002","performed_by":"护士 B","performed_at":"2026-09-17T10:00:00Z","verdicts":[$V2_MISMATCH] }
EOF
run_gate gate_human_sample "$d"
[ "$rc" -eq 1 ] && ok "1 mismatch in run-001 + 1 in run-002 → exit 1 (the threshold is per ARCHIVE)" \
  || no "splitting mismatches across runs evaded the threshold, rc=$rc"

# ===========================================================================
# E. the companion binding — reread_channel: human must point at a verdict (A5)
# ===========================================================================
echo "=== E. gate_high_risk_fields: 'human' is a claim about a person ==="

# <dir> <label the inventory row claims a human verified>
mk_human_row() {
  local d="$1" label="$2"
  mkdir -p "$d/raw/_provenance/run-001" "$d/07_检验/血常规"
  : > "$d/07_检验/血常规/a.md"
  plan   "$d" "$S1"
  result "$d" "$V1_MATCH"
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"u.pdf","raw_path":"raw/incoming/u.pdf",
   "page_range":null,"kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent","sidecar_path":"07_检验/血常规/a.md","bucket_path":"07_检验/血常规",
   "modality":"image","read_mode":"model_vision_primary","transcribe_model_id":"host-vision-1",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"passed_independent_reread","reread_channel":"human",
   "high_risk_fields":[{"label":"$label","status":"passed_independent_reread",
                        "reread_channel":"human","readings":[{"channel":"human","value":"3.21"}]}],
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

d="$tmp/human_bound"; mk_human_row "$d" "白细胞计数"
run_gate gate_high_risk_fields "$d"
[ "$rc" -eq 0 ] && ok "reread_channel=human WITH a matching verdict → exit 0" \
  || no "a genuinely human-verified field was blocked: $out"

d="$tmp/human_unbound"; mk_human_row "$d" "给药剂量"
run_gate gate_high_risk_fields "$d"
[ "$rc" -eq 1 ] && ok "reread_channel=human with NO matching verdict → exit 1" \
  || no "'human' accepted as a bare word, rc=$rc"
echo "$out" | grep -q 'no matching verdict' \
  && ok "…error says the verdict is missing" || no "wrong reason: $out"
echo "$out" | grep -q 'human_sample_result.json' \
  && ok "…error names the file that would make the claim true" || no "file not named: $out"
echo "$out" | grep -q 'not a no-channel placeholder' \
  && ok "…error states that 'human' is not a synonym for 'no channel'" || no "rule not stated: $out"

# ---------------------------------------------------------------------------
echo
echo "== human-sample-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
