#!/usr/bin/env bash
# tests/unit/high-risk-denominator.test.sh — organize v3→v4 fix spec B1.
#
# Every other high-risk check in validate_structured_outputs.py inspects the QUALITY of
# a declared claim: is this re-read channel independent of the first read, is the second
# model a different model, does a `human` channel have a matching verdict, does the
# row-level status agree with the per-field statuses. Not one of them ever asked whether
# the claim set was COMPLETE. So the entire structure rested on the run's own answer to
# "which fields on this page are high-risk?", and the cheapest answer was "none".
#
# That answer costs one character. `high_risk_fields: []` derives cleanly to
# `high_risk_review_status: not_applicable`; gate_high_risk_fields then has nothing to
# check and passes; gate_faithfulness requires coverage of an empty set and passes;
# gate_human_sample never fires because no source carries a high-risk field. A page whose
# frontmatter prints 住院号, WBC and 奥希替尼 80mg — an identifier, a lab value and a dose
# string, the three things a single wrong character ruins — walks through every
# field-level gate in the file by declaring that it has no fields. Nothing in that chain
# is a lie. The chain simply never crosses back to the source.
#
# gate_high_risk_denominator is the crossing. It RECOMPUTES the set from the page
# frontmatter the archive itself stores, through the one shared table in
# scripts/_high_risk.py, and requires the inventory's `high_risk_fields[]` to COVER it.
# Declaring more than the table knows is always legal; shrinking below the computed floor
# is an ERROR.
#
# This file asserts both arms of every rule, because a gate proven only by its negative
# arm is a gate that may be refusing everything, and a denominator that fires on a clean
# archive teaches runs to delete labels from frontmatter to keep the validator quiet —
# which is the same defect one level down. Specifically:
#
#   * the empty-array arm and its complement (the same archive, fully declared, passes);
#   * partial declaration — and the message must NAME the label that was dropped, because
#     "coverage is incomplete" with no label is a finding nobody can act on;
#   * the native_text exemption (A35): bytes lifted verbatim from a born-digital file were
#     never read by a model, there is no second channel to demand of them, and the row is
#     `not_applicable` by contract — asserted together with its twin, an otherwise
#     IDENTICAL archive read by model vision, which must fail. An exemption proven only
#     on the passing side is indistinguishable from a gate that never runs;
#   * scope is decided by three tests, not by the declared key. A row that simply omits
#     `transcript_path` while raw/transcript/<sid>/page-*.md sits on disk is still in the
#     denominator — deleting one key from one JSON file must not be a way out, for the
#     same reason B3 gives gate_field_provenance the disk as its authority;
#   * `high_risk_fields: []` with a row-level status other than not_applicable — a row
#     asserting an outcome for records it does not hold.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

run_gate() {  # <gate_fn> <patient_dir>   → sets $rc and $out
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

SIDECAR="07_检验/2026-03-15_血常规.md"

# One inventory row. Everything the denominator's scope depends on is a parameter:
# the read mode, whether transcript_path is declared, the declared high_risk_fields[],
# the row-level summary and the archive's scheme version.
inv() {  # <dir> <read_mode> <transcript_path|-> <high_risk_fields json> <row status> [scheme]
  local d="$1" mode="$2" tp="$3" hrf="$4" status="$5" scheme="${6:-4}"
  local tline=""
  [ "$tp" = "-" ] || tline="\"transcript_path\":\"$tp\","
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":$scheme,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"血常规.pdf",
   "raw_path":"raw/incoming/血常规.pdf","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent","sidecar_path":"$SIDECAR","bucket_path":"07_检验",
   $tline
   "modality":"image","read_mode":"$mode",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"$status","high_risk_fields":$hrf,
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

page() {  # <path> <fields json array>
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<EOF
---
source_id: s1
page: 1
page_total: 1
fields: $2
---
# 全文
住院号 [PII_MASKED]  白细胞计数 6.2 ×10^9/L  奥希替尼 80mg qd
EOF
}

# Three labels, three DIFFERENT high-risk classes, so a partial declaration cannot be
# explained away as one table entry being over-eager:
#   住院号         → identifier   (an admission number; one digit wrong is another patient)
#   WBC            → lab_value    (the Latin abbreviation arm B1 added to the table)
#   奥希替尼 80mg   → drug_name    (the dose string; a zero decides the dose)
THREE='[{"label": "住院号", "value": "[PII_MASKED]"},
        {"label": "WBC", "value": "6.2"},
        {"label": "奥希替尼 80mg", "value": "奥希替尼 80mg qd"}]'
# Not one of these is in the table: 主诉 / 影像所见 / 科室 all classify to None.
BENIGN='[{"label": "主诉", "value": "咳嗽 2 周"},
         {"label": "影像所见", "value": "右上叶结节"},
         {"label": "科室", "value": "呼吸内科"}]'

hrf_entry() {  # <label>
  printf '{"label": "%s", "status": "passed_independent_reread", "reread_channel": "text_layer", "readings": [{"channel": "transcribe", "value": "x"}, {"channel": "text_layer", "value": "x"}]}' "$1"
}
ALL_THREE="[$(hrf_entry 住院号), $(hrf_entry WBC), $(hrf_entry '奥希替尼 80mg')]"
TWO_OF_THREE="[$(hrf_entry 住院号), $(hrf_entry WBC)]"

# ===========================================================================
# A. NEGATIVE — the total version: an empty array against a page full of fields
# ===========================================================================
echo "=== A. high_risk_fields: [] while the page declares three high-risk fields ==="

d="$tmp/empty"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" '[]' not_applicable
page "$d/raw/transcript/s1/page-001.md" "$THREE"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "empty high_risk_fields[] against a non-empty computed set is an ERROR" \
                || no "empty high_risk_fields[] passed — the denominator is self-declared"
grep -q "high_risk_fields\[\] is EMPTY" <<<"$out" \
  && ok "message states the array is empty, not merely 'incomplete'" \
  || no "message does not say the array is empty: $out"
grep -q "3 high-risk field(s)" <<<"$out" \
  && ok "message reports the recomputed count (3)" \
  || no "message does not report the recomputed count: $out"

# The three classes must each be visible in the finding. A message that named only the
# identifier would let a run fix that one label and re-run into a green board.
for spec in "'住院号' (identifier)" "'WBC' (lab_value)" "'奥希替尼 80mg' (drug_name)"; do
  grep -qF "$spec" <<<"$out" \
    && ok "finding names $spec" \
    || no "finding omits $spec: $out"
done
grep -q "not_applicable" <<<"$out" \
  && ok "message explains WHY an empty array is load-bearing (derives to not_applicable)" \
  || no "message does not explain the downstream effect: $out"

# ===========================================================================
# B. NEGATIVE — partial declaration, and the message must name the DROPPED label
# ===========================================================================
echo
echo "=== B. two of the three declared ==="

d="$tmp/partial"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" "$TWO_OF_THREE" passed_independent_reread
page "$d/raw/transcript/s1/page-001.md" "$THREE"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "declared ⊉ computed is an ERROR even when two of three are covered" \
                || no "partial coverage passed — a run can shrink its own denominator"
grep -q "1 high-risk field(s) appear in this source" <<<"$out" \
  && ok "message reports exactly one uncovered field" \
  || no "message does not report the uncovered count: $out"
grep -qF "'奥希替尼 80mg' (drug_name)" <<<"$out" \
  && ok "message NAMES the dropped label — actionable, not just 'coverage incomplete'" \
  || no "message does not name the dropped label: $out"
# The two labels that WERE declared must not appear in the missing list; a gate that
# re-reports covered fields is noise that trains readers to skim the finding.
grep -qF "'住院号'" <<<"$out" \
  && no "message wrongly lists the declared 住院号 as missing: $out" \
  || ok "declared 住院号 is not reported as missing"
grep -qF "'WBC'" <<<"$out" \
  && no "message wrongly lists the declared WBC as missing: $out" \
  || ok "declared WBC is not reported as missing"

# ===========================================================================
# C. POSITIVE — the same archive, fully declared, is silent
# ===========================================================================
echo
echo "=== C. all three declared ==="

d="$tmp/covered"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" "$ALL_THREE" passed_independent_reread
page "$d/raw/transcript/s1/page-001.md" "$THREE"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] && ok "full coverage of the computed set passes (exit 0)" \
                || no "full coverage still errored — the gate refuses compliant archives: $out"
[ -z "$out" ] && ok "no output on the passing arm" || no "unexpected output: $out"

# Over-declaration is legal by design: the table is deliberately over-inclusive at the
# margins and an archive may record second reads for fields it does not know about.
# 血压 classifies to None, so it is in the declaration and not in the computed set.
d="$tmp/over"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" \
    "[$(hrf_entry 住院号), $(hrf_entry WBC), $(hrf_entry '奥希替尼 80mg'), $(hrf_entry 血压)]" \
    passed_independent_reread
page "$d/raw/transcript/s1/page-001.md" "$THREE"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] && ok "declaring MORE than the table knows about (血压) is not an error" \
                || no "over-declaration rejected — the floor became a ceiling: $out"

# ===========================================================================
# D. The native_text exemption (A35) — and its twin, which must NOT be exempt
# ===========================================================================
echo
echo "=== D. read_mode: native_text is outside the denominator ==="

# A born-digital source: characters copied byte-for-byte, verified by
# verify_native_text.py as `native_text_identity`, row `not_applicable` by contract.
# No transcript_path, nothing under raw/transcript/ — the labels live only in the masked
# sidecar. All three scope tests in _is_transcribed_source() must answer no.
d="$tmp/native"; mkdir -p "$d/07_检验"
inv "$d" native_text "-" '[]' not_applicable
mkdir -p "$(dirname "$d/$SIDECAR")"
page "$d/$SIDECAR" "$THREE"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] && ok "native_text source with no transcript is exempt (A35)" \
                || no "native_text source was pulled into the denominator: $out"

# The twin. Byte-identical archive, ONE field changed: the same labels, the same sidecar,
# read by a model instead of copied. This is what proves the exemption is a scope rule
# and not a gate that quietly never runs.
d="$tmp/native-twin"; mkdir -p "$d/07_检验"
inv "$d" model_vision_primary "-" '[]' not_applicable
mkdir -p "$(dirname "$d/$SIDECAR")"
page "$d/$SIDECAR" "$THREE"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "the SAME archive at read_mode=model_vision_primary is an ERROR" \
                || no "model-read source escaped the denominator: the exemption is a hole"
grep -q "high_risk_fields\[\] is EMPTY" <<<"$out" \
  && ok "twin fails for the right reason (empty array vs a non-empty computed set)" \
  || no "twin failed for some other reason: $out"

# ===========================================================================
# E. Scope follows the DISK, not the declared key
# ===========================================================================
echo
echo "=== E. omitting transcript_path does not leave the denominator ==="

# Same native_text row as D — except raw/transcript/s1/page-001.md exists on disk. The
# row never mentions it. If scope were keyed to the declared key alone, deleting one key
# from one JSON file would be the cheapest bypass in the file (the hole one level down
# from the one this gate closes), so the glob is the authority. Same reasoning as B3.
d="$tmp/disk"; mkdir -p "$d"
inv "$d" native_text "-" '[]' not_applicable
page "$d/raw/transcript/s1/page-001.md" "$THREE"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "transcript on disk pulls the row in even with transcript_path absent" \
                || no "deleting transcript_path bought an exemption: $out"
grep -qF "'住院号' (identifier)" <<<"$out" \
  && ok "labels were read off the on-disk transcript, not off the declaration" \
  || no "on-disk transcript labels were not counted: $out"

# The complement: delete that one file and the identical row is exempt again. This is
# what shows the disk file — not the read_mode string, not some fallback — decided it.
rm -f "$d/raw/transcript/s1/page-001.md"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] && ok "removing the transcript restores the native_text exemption" \
                || no "row still in the denominator with no transcript anywhere: $out"

# The third scope test: read_mode alone. No transcript_path, nothing under
# raw/transcript/, labels still staged under ocr/ before the 段 2 bucket move.
d="$tmp/staged"; mkdir -p "$d"
inv "$d" model_vision_assist "-" '[]' not_applicable
page "$d/ocr/s1/page-001.md" "$THREE"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "model_vision_assist + labels staged under ocr/ is in the denominator" \
                || no "a page still staged under ocr/ escaped the denominator: $out"
grep -qF "'WBC' (lab_value)" <<<"$out" \
  && ok "ocr/ staging is a label surface: the pre-move page is held to the same set" \
  || no "labels staged under ocr/ were not counted: $out"

# ===========================================================================
# F. An empty array may only summarise to not_applicable
# ===========================================================================
echo
echo "=== F. empty high_risk_fields[] with a row-level status that claims an outcome ==="

# No high-risk labels anywhere (主诉 / 影像所见 / 科室 all classify to None), so the
# computed set is legitimately empty — and the row still claims its fields passed an
# independent re-read. There are no fields. The claim is about nothing.
d="$tmp/status"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" '[]' passed_independent_reread
page "$d/raw/transcript/s1/page-001.md" "$BENIGN"

run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "empty array + status≠not_applicable is an ERROR" \
                || no "a row asserted an outcome for an array it does not hold: $out"
grep -q "only summary an empty array supports is not_applicable" <<<"$out" \
  && ok "message states the derivation rule it is enforcing" \
  || no "message does not state the rule: $out"
# It must NOT also fire the coverage branch — the computed set really is empty here, and
# a gate that reports two findings for one defect makes the real one harder to find.
grep -q "high_risk_fields\[\] is EMPTY, but this source" <<<"$out" \
  && no "coverage branch also fired on a legitimately empty computed set: $out" \
  || ok "coverage branch stays silent when the computed set is genuinely empty"

d="$tmp/status-ok"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" '[]' not_applicable
page "$d/raw/transcript/s1/page-001.md" "$BENIGN"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] && ok "empty array + not_applicable on a page with no high-risk labels passes" \
                || no "a genuinely field-free page was rejected: $out"

# ===========================================================================
# G. Scope: a scheme-3 archive predates the per-page contract
# ===========================================================================
echo
echo "=== G. legacy (scheme_version: 3) archives are out of scope ==="

d="$tmp/legacy"; mkdir -p "$d"
inv "$d" model_vision_primary "raw/transcript/s1/page-001.md" '[]' not_applicable 3
page "$d/raw/transcript/s1/page-001.md" "$THREE"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] && ok "scheme_version: 3 is exempt — it has no high_risk_fields[] contract" \
                || no "legacy archive was held to a v4 contract: $out"

# …but only when it says 3. B4 made a MISSING scheme_version an error of its own
# precisely so that deleting the key cannot buy this exemption; here the observable is
# that the v4 twin (section A, same page, same empty array) fails.

# ===========================================================================
# H. An unreadable inventory is UNCHECKED, not passed
# ===========================================================================
echo
echo "=== H. unparseable source_inventory.json ==="

d="$tmp/broken"; mkdir -p "$d"
printf '{"files": [' > "$d/source_inventory.json"
page "$d/raw/transcript/s1/page-001.md" "$THREE"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] && ok "a broken inventory is reported, not silently treated as empty" \
                || no "broken inventory passed silently — zero rows read as zero defects"
grep -q "not parseable JSON" <<<"$out" \
  && ok "message says the gate could not run" \
  || no "message does not say the gate could not run: $out"

echo
echo "== high-risk-denominator: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
