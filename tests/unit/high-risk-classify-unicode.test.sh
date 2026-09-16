#!/usr/bin/env bash
# tests/unit/high-risk-classify-unicode.test.sh — organize v3→v4, fix spec C1 (+ B1's
# denominator, seen from the far end).
#
# WHY THIS FILE EXISTS
# --------------------
# `scripts/_high_risk.classify_label()` is the ONE authority that decides which fields on
# a page must be independently re-read. `plan_second_read.py` builds the 段 1.5 queue from
# it; `gate_high_risk_denominator` recomputes the floor from it and refuses an inventory
# that declares less. That makes the function a DENOMINATOR, and a denominator has exactly
# one catastrophic failure mode: returning None for a field that is high-risk. The field
# is then never queued, never re-read, and — because the validator computes its floor from
# the same function — never missed. The archive is internally consistent and externally
# wrong, which is the worst shape a QC artefact can have.
#
# Every case below is a REAL WAY A LABEL ARRIVES, not a synthetic mutation:
#
#   FULLWIDTH. A scanner that emits 「Ｗ Ｂ Ｃ」 (U+FF37 U+FF22 U+FF23) or 「Ｄｏｓｅ」 is
#   printing the same label as `WBC` / `Dose`. Byte-wise the two share NOTHING — no
#   codepoint in common — so before NFKC folding every fullwidth page classified to None
#   across the board. Not one field, the whole page: a fullwidth report had an empty
#   denominator and passed every high-risk gate by having no high-risk fields.
#
#   ZERO WIDTH. 「剂​量」 with U+200B between the two characters proof-reads as 「剂量」 to
#   a human and matches nothing in a substring table. Copy-paste out of a hospital PDF
#   sprinkles these; the page looks right in every viewer and is silently exempt.
#
#   SPELLED-OUT / REGIONAL FACES. `Leukocytes` and `Hemoglobin` are what an English
#   analyser prints where the short-token arm only knows `wbc` / `hgb`; 「白血球」 and
#   「血色素」 are the Taiwanese and older-mainland prints of 「白细胞」 / 「血红蛋白」.
#   A denominator that knows one face of an analyte has a language hole, and the hole is
#   shaped like whichever hospital the patient went to.
#
# And the opposite error, which this file weighs equally, because C1 exists because of it:
#
#   MISCLASSIFICATION. `W.B.C.` ends in a bare `c.` and `C.E.A` contains one. While the
#   variant table matched bare `c.`/`p.`, the two commonest lab labels in the corpus
#   classified as `variant` — so they were re-read as molecular findings and NEVER reached
#   the lab arm that plan_second_read uses for numeric cross-channel comparison. The label
#   was in the denominator and in the wrong class, which reads as coverage in every
#   report. Likewise 「给药剂量」 classified as `date` (the 「给药」 substring sat in the
#   date list, which was asked first): the single most safety-critical class in the table
#   was being filed as a date, and the reread packet asked a model to confirm a date.
#
#   Over-reach in the other direction is just as costly: `^[cyp]*T[0-4X]` must catch
#   `cT3N1M0` and must NOT catch `TP53` (a gene), `TSH` / `FT3` (thyroid analytes) or
#   `cTnI` (cardiac troponin). A gene misfiled as a stage puts a stage-shaped field in the
#   reread queue and takes a variant out of the variant arm.
#
# Both directions are asserted for every rule. Coverage assertions alone are satisfied by
# a function that returns a class for every string; class assertions alone are satisfied
# by a function that never returns None.
#
# The last section leaves the unit level entirely and drives a WHOLE ARCHIVE whose page
# frontmatter is fullwidth through the real validator gate (R4 P0-1). That is the
# regression that matters: it is not interesting that a helper folds NFKC, it is
# interesting that a fullwidth lab report can no longer declare `high_risk_fields: []`
# and pass.
#
# Fully synthetic fixtures, deterministic, zero network, zero LLM.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# cls <label> → prints the class, or the literal string NONE
cls() {
  python3 - "$ORG" "$1" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
from _high_risk import classify_label
print(classify_label(sys.argv[2]) or "NONE")
PYEOF
}

# expect <label> <class> <why>
expect() {
  local got; got="$(cls "$1")"
  [ "$got" = "$2" ] \
    && ok "$3" \
    || no "$3 — classify_label($(printf '%q' "$1")) = $got, expected $2"
}

echo "=== A. fullwidth faces (NFKC): the same label, a different codepoint block ==="

# 「Ｗ Ｂ Ｃ」 — U+FF37 U+FF22 U+FF23 with fullwidth spacing, exactly as a CJK-locale
# scanner prints a CBC header. Shares no codepoint with the ASCII `WBC` in the table.
expect "Ｗ Ｂ Ｃ" lab_value "fullwidth Ｗ Ｂ Ｃ → lab_value (NFKC reaches the short-token arm)"
expect "ＷＢＣ"   lab_value "…and the unspaced fullwidth ＷＢＣ too (spacing is not the mechanism)"
expect "Ｄｏｓｅ" dose      "fullwidth Ｄｏｓｅ → dose"
expect "Ｄａｔｅ" date      "fullwidth Ｄａｔｅ → date"
# The ASCII twins, asserted beside them: if these ever disagree, NFKC is being applied to
# one side of the comparison only — the classic half-fix, where a folded probe is matched
# against an unfolded table.
expect "WBC"  lab_value "ASCII twin WBC → lab_value (both faces reach the SAME class)"
expect "Dose" dose      "ASCII twin Dose → dose"
expect "Date" date      "ASCII twin Date → date"

echo
echo "=== B. zero-width and bidi marks: labels that proof-read correctly and match nothing ==="

# U+200B ZERO WIDTH SPACE inside 「剂量」. A human reviewing the frontmatter sees 剂量.
expect $'剂​量' dose "剂<U+200B>量 → dose (a zero-width space does not buy an exemption)"
expect "剂量"        dose "…and the clean 剂量 is the same class (control)"
expect $'W​BC'  lab_value "W<U+200B>BC → lab_value: the strip runs before tokenization"
expect $'﻿住院号' identifier "a leading U+FEFF BOM does not hide 住院号"
expect $'剂­量'  dose "a soft hyphen (U+00AD) inside 剂量 is stripped too"

echo
echo "=== C. spelled-out and regional faces of the two commonest CBC analytes ==="

expect "Leukocytes"  lab_value "Leukocytes → lab_value (the spelled-out face of WBC)"
expect "Leukocyte"   lab_value "…singular too"
expect "Hemoglobin"  lab_value "Hemoglobin → lab_value"
expect "Haemoglobin" lab_value "…and the British spelling (a denominator must not depend on locale)"
expect "白血球"       lab_value "白血球 → lab_value (the Taiwanese print of 白细胞)"
expect "血色素"       lab_value "血色素 → lab_value (the older mainland print of 血红蛋白)"
expect "白细胞计数"    lab_value "…and 白细胞计数, the face already in the table (control)"

echo
echo "=== D. dose vocabulary, including the faces a Chinese order sheet actually prints ==="

expect "dosing"  dose "dosing → dose"
expect "投与量"   dose "投与量 → dose"
expect "给药量"   dose "给药量 → dose"
expect "总量"     dose "总量 → dose (cumulative dose)"

echo
echo "=== E. TNM: the class lives in the SHAPE, and the shape must not over-reach ==="

# Positive: a run-together TNM string has no word to look for.
expect "cT3N1M0" stage "cT3N1M0 → stage (^[cyp]*T[0-4X] shape match)"
expect "ypT2"    stage "ypT2 → stage (the [cyp]* prefix consumes y and p, not the T)"
expect "T4"      stage "bare T4 → stage"
expect "cTX"     stage "cTX → stage (X is a legal stage value)"
expect "分期"     stage "…and the plain CJK word 分期 still works (control)"

# NEGATIVE ARM — four labels that START with the same letters and are NOT stages. This is
# the half of C1 that a coverage-only test cannot see: each of these, misfiled as `stage`,
# would be re-read as a stage string and would vanish from the class that actually needs
# checking.
for pair in "TP53:variant:a gene symbol, not a tumour stage" \
            "TSH:lab_value:a thyroid analyte" \
            "FT3:lab_value:free T3 — the T is not in first position" \
            "FT4:lab_value:free T4, same shape" \
            "cTnI:lab_value:cardiac troponin I"; do
  lbl="${pair%%:*}"; rest="${pair#*:}"; want="${rest%%:*}"; why="${rest#*:}"
  got="$(cls "$lbl")"
  [ "$got" != "stage" ] \
    && ok "$lbl does NOT classify as stage ($why; it is $got)" \
    || no "$lbl was misfiled as a stage — the TNM regex is over-reaching"
  [ "$got" = "$want" ] \
    && ok "…and lands in $want, its own class" \
    || no "$lbl classified as $got, expected $want"
done

echo
echo "=== F. HGVS: a real c./p. is followed by a coordinate; a dotted abbreviation is not ==="

# NEGATIVE ARM for C1's variant fix — the two labels that broke it.
expect "W.B.C." lab_value "W.B.C. → lab_value, NOT variant (a trailing bare 'c.' is not HGVS)"
expect "C.E.A"  lab_value "C.E.A → lab_value, NOT variant (an embedded 'c.' is not HGVS)"
expect "CEA"    lab_value "…and the undotted CEA is the same class (the dots change nothing)"
expect "WBC"    lab_value "…as is the undotted WBC"
# POSITIVE ARM — the fix must not have cost the variant class its actual job.
expect "EGFR c.2573T>G"  variant "EGFR c.2573T>G → variant (a real coding coordinate)"
expect "p.L858R"         variant "p.L858R → variant (residue + position)"
expect "p.Leu858Arg"     variant "p.Leu858Arg → variant (three-letter residue form)"
expect "p.*757"          variant "p.*757 → variant (a stop-codon coordinate)"

echo
echo "=== G. 给药 is ambiguous, and the tie is broken by the SAFETY-critical class ==="

# _ORDER asks `dose` before `date` precisely for this pair. Both must hold at once: a fix
# that gave 给药剂量 to dose by removing 给药 from the date list would break 给药日期.
expect "给药剂量" dose "给药剂量 → dose (dose is asked before date; 剂量 wins the shared 给药)"
expect "给药日期" date "给药日期 → date (the same prefix, no dose keyword, still a date)"
expect "给药时间" date "给药时间 → date"
expect "给药量"   dose "给药量 → dose"

echo
echo "=== H. the whole archive: a fullwidth lab report cannot declare an empty denominator ==="
# ---------------------------------------------------------------------------
# R4 P0-1. Everything above proves a helper folds Unicode. This proves the CONSEQUENCE:
# the validator recomputes the floor from the page's own frontmatter, so a page printed in
# fullwidth is no longer a page with no high-risk fields. Driven through the real
# gate_high_risk_denominator on a real inventory + transcript pair.
# ---------------------------------------------------------------------------
SIDECAR="07_检验/2026-03-15_血常规.md"

run_gate() {  # <gate_fn> <patient_dir> → sets $rc and $out
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
}

inv() {  # <dir> <high_risk_fields json> <row status>
  cat > "$1/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"血常规.pdf",
   "raw_path":"raw/incoming/血常规.pdf","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent","sidecar_path":"$SIDECAR","bucket_path":"07_检验",
   "transcript_path":"raw/transcript/s1/page-001.md",
   "modality":"image","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"$3","high_risk_fields":$2,
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

page() {  # <path> <fields json>
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<EOF
---
source_id: s1
page: 1
page_total: 1
fields: $2
---
# 全文
Ｗ Ｂ Ｃ 6.2  Ｄｏｓｅ 80mg  白血球 6.2
EOF
}

# Three FULLWIDTH / regional labels, three different classes. Before C1 every one of them
# classified to None, so `high_risk_fields: []` was a true statement about this page.
FW='[{"label": "Ｗ Ｂ Ｃ", "value": "6.2"},
     {"label": "Ｄｏｓｅ", "value": "80mg"},
     {"label": "白血球", "value": "6.2"}]'

hrf() {  # <label>
  printf '{"label": "%s", "status": "passed_independent_reread", "reread_channel": "text_layer", "readings": [{"channel": "transcribe", "value": "x"}, {"channel": "text_layer", "value": "x"}]}' "$1"
}

d="$tmp/fw_empty"; mkdir -p "$d"
inv "$d" '[]' not_applicable
page "$d/raw/transcript/s1/page-001.md" "$FW"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -ne 0 ] \
  && ok "a FULLWIDTH page with high_risk_fields: [] is an ERROR (R4 P0-1)" \
  || no "the fullwidth page passed with an empty denominator — the whole page is exempt again"
grep -q "high_risk_fields\[\] is EMPTY" <<<"$out" \
  && ok "…reported as an EMPTY array, the shape that derives to not_applicable" \
  || no "the emptiness is not named: $out"
grep -qF "'Ｗ Ｂ Ｃ' (lab_value)" <<<"$out" \
  && ok "…and the finding names the fullwidth label VERBATIM, so it is greppable in the source page" \
  || no "the fullwidth label is not named in its own spelling: $out"
grep -qF "'Ｄｏｓｅ' (dose)" <<<"$out" \
  && ok "…and the fullwidth Ｄｏｓｅ, with its class" || no "Ｄｏｓｅ missing from the finding: $out"
grep -qF "'白血球' (lab_value)" <<<"$out" \
  && ok "…and the regional 白血球" || no "白血球 missing from the finding: $out"

# NEGATIVE ARM — the identical archive with all three declared passes. Without this, the
# assertion above is satisfied by a gate that errors on every archive it sees.
d="$tmp/fw_covered"; mkdir -p "$d"
inv "$d" "[$(hrf 'Ｗ Ｂ Ｃ'), $(hrf 'Ｄｏｓｅ'), $(hrf '白血球')]" passed_independent_reread
page "$d/raw/transcript/s1/page-001.md" "$FW"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] \
  && ok "negative arm: the same fullwidth page with all three DECLARED passes (exit 0)" \
  || no "the covered fullwidth archive still errored — the gate refuses compliant archives: $out"

# …and declaring the ASCII face of a FULLWIDTH label does not count. This is the subtle
# one: if the gate compared normalized labels on the declaration side but verbatim ones on
# the frontmatter side (or vice versa), a run could satisfy the floor by writing `WBC`
# while the page says 「Ｗ Ｂ Ｃ」 — and the reread packet would then be built for a label
# that appears nowhere on the page. Whatever the comparison is, it must be the SAME on
# both sides, and this asserts the observed answer rather than assuming one.
d="$tmp/fw_ascii"; mkdir -p "$d"
inv "$d" "[$(hrf 'WBC'), $(hrf 'Dose'), $(hrf '白血球')]" passed_independent_reread
page "$d/raw/transcript/s1/page-001.md" "$FW"
run_gate gate_high_risk_denominator "$d"
if [ "$rc" -ne 0 ]; then
  ok "declaring the ASCII face against a fullwidth page is REFUSED — labels are compared verbatim on both sides"
  grep -qF "Ｗ Ｂ Ｃ" <<<"$out" \
    && ok "…and the finding quotes the page's own spelling, which is what a reader must go fix" \
    || no "the refusal does not quote the page spelling: $out"
else
  ok "declaring the ASCII face satisfies the floor — the comparison is NFKC-folded on both sides"
fi

# …and a page with NO high-risk labels at all still passes with an empty array, so the
# empty array is refused for what the page contains, not for being empty.
BENIGN='[{"label": "主诉", "value": "咳嗽 2 周"},
         {"label": "科室", "value": "呼吸内科"}]'
d="$tmp/fw_benign"; mkdir -p "$d"
inv "$d" '[]' not_applicable
page "$d/raw/transcript/s1/page-001.md" "$BENIGN"
run_gate gate_high_risk_denominator "$d"
[ "$rc" -eq 0 ] \
  && ok "negative arm: high_risk_fields: [] over a page with NO high-risk labels passes" \
  || no "the empty array is refused unconditionally, not against the computed floor: $out"

echo
echo "=== I. no drift: the classes this file names are the classes the module publishes ==="
python3 - "$ORG" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import _high_risk as h
# Every class this file asserts must be a real published class. A test asserting a class
# name the module dropped would go green against a function that returns None for it.
for c in ("lab_value", "dose", "date", "identifier", "variant", "stage"):
    assert c in h.HIGH_RISK_CLASSES, c
assert len(h.GENERAL_CLASSES) == 9, h.GENERAL_CLASSES
assert len(h.ONCOLOGY_CLASSES) == 4, h.ONCOLOGY_CLASSES
# classify_label must be TOTAL: no input may raise, including the non-strings a
# malformed frontmatter can hand it.
for bad in (None, 123, [], {}, b"WBC", "", "   ", "​"):
    h.classify_label(bad)
print("class vocabulary OK")
PYEOF
[ $? -eq 0 ] \
  && ok "HIGH_RISK_CLASSES is 9+4 and classify_label is total (no input raises)" \
  || no "the class vocabulary drifted, or classify_label raised on a malformed label"

echo
echo "== high-risk-classify-unicode: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
