#!/usr/bin/env bash
# tests/unit/sidecar-transcript-consistency.test.sh — organize v3→v4, fix spec C6.
#
# WHY THIS FILE EXISTS
# --------------------
# 段 1 writes each page TWICE. `raw/transcript/<sid>/page-NNN.md` is what the transcriber
# read off the page; the bucket sidecar is that same page with PII shapes rewritten to
# [PII_MASKED]. The sidecar is DERIVED, and the only legal difference between the two is
# the masking. A27 then makes that asymmetry consequential: `raw/transcript/` is readable
# only by deterministic scripts and authorised humans, so EVERY downstream consumer — the
# synthesis workers, the summary renderer, the clinician-facing HTML — reads the sidecar
# and nothing else.
#
# So a value that drifts between the two is a value the whole archive believes and no page
# ever printed. A sidecar carrying `白细胞计数 9.99` where the transcript says `3.21`
# passed EVERY OTHER GATE in the validator, and it is worth being precise about why,
# because the reflex is to assume something else would catch it:
#
#   gate_field_provenance validates labs.json against the TRANSCRIPT when one exists
#   (B3), so it confirms the transcript's 3.21 and never looks at the sidecar;
#   gate_transcripts checks the sidecar for UNMASKED PII — the opposite direction;
#   gate_numeric_integrity compares two fields the same synthesis pass wrote, so it is
#   internally consistent with whichever number that pass picked up;
#   gate_faithfulness checks that a span exists and is shaped like a span.
#
# Nothing compared the two surfaces to each other. Whichever file the synthesis pass
# happened to open became the truth, and a white-cell count of 9.99 versus 3.21 is the
# difference between a normal count and neutropenia.
#
# THE DIRECTION IS THE CONTRACT. The check is one-directional: every sidecar value must be
# findable in the transcript, never the reverse. 段 2 projects a SUBSET, so a transcript
# holding values the sidecar dropped is normal operation; a sidecar holding a value the
# transcript does not is fabrication. A symmetric check would fire on every correctly
# filed archive, and a gate that fires on correct behaviour gets switched off.
#
# TWO EXCLUSIONS, both principled rather than convenient, and both asserted from both
# sides because an exclusion is a hole until it is bounded:
#
#   [PII_MASKED] is skipped. Masking is the one transformation that legitimately destroys
#   the original, so demanding the masked form be findable in the transcript would make
#   CORRECT MASKING an error — and the archive's escape from that error would be to stop
#   masking. The exclusion has to be the token, though, not the field: a sidecar that
#   replaces 3.21 with 9.99 must not be able to buy silence by also masking some unrelated
#   field on the same page.
#
#   Probes shorter than two characters are skipped. A one-character probe is inside almost
#   any string, so matching it proves nothing and failing it means nothing.
#
# AND THE PRECISION THAT MAKES IT WORTH HAVING. `3.2` must NOT match inside `3.21`. That
# single assertion is the reason the comparison uses word boundaries instead of
# containment: a dropped final digit is the most common OCR slip there is, it is
# invisible to a human skimming two files, and a substring-based check would call it a
# match every time. Formatting tolerance (`3.5-9.5` vs `3.5 - 9.5`, `3.21` vs
# `3.21 ×10^9/L`, `1,234` vs `1234`) must survive; a changed DIGIT must not.
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

SIDECAR="07_检验/2026-03-15_血常规.md"

run_gate() {  # <patient_dir> → sets $rc, $out
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_sidecar_transcript_consistency(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
}

inv() {  # <dir>
  mkdir -p "$1/07_检验" "$1/raw/transcript/s1"
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
   "high_risk_review_status":"not_applicable","high_risk_fields":[],
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

# md <path> <fields json>
md() {
  mkdir -p "$(dirname "$1")"
  cat > "$1" <<EOF
---
source_id: s1
page: 1
fields: $2
---
# 全文
血常规报告正文。
EOF
}

# build <dir> <transcript fields> <sidecar fields>
build() {
  rm -rf "$1"; mkdir -p "$1"
  inv "$1"
  md "$1/raw/transcript/s1/page-001.md" "$2"
  md "$1/$SIDECAR" "$3"
}

T_WBC='[{"label": "白细胞计数", "value": "3.21", "unit": "×10^9/L"}]'

# ===========================================================================
echo "=== A. the value drifted: transcript 3.21, sidecar 9.99 ==="
# ===========================================================================
D="$tmp/drift"
build "$D" "$T_WBC" '[{"label": "白细胞计数", "value": "9.99", "unit": "×10^9/L"}]'
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "a sidecar value that appears nowhere in its own transcript is an ERROR (C6)" \
  || no "9.99 against a transcript saying 3.21 passed — the derived surface can invent numbers"
grep -qF "'9.99'" <<<"$out" \
  && ok "…and the finding quotes the value the SIDECAR carries (what a clinician would read)" \
  || no "the drifted value is not quoted: $out"
grep -qF "白细胞计数" <<<"$out" \
  && ok "…under its label" || no "the label is not named: $out"
grep -qF "$SIDECAR" <<<"$out" \
  && ok "…and names the sidecar file, which is the file to go fix" || no "the sidecar path is missing: $out"
grep -qF "raw/transcript/s1/" <<<"$out" \
  && ok "…and the transcript directory it was checked against" || no "the transcript surface is not named: $out"
grep -qF "page 1" <<<"$out" \
  && ok "…scoped to the PAGE, so the comparison is against the right page's fields" \
  || no "the finding does not say which page was compared: $out"
grep -qF "ingest_transcripts.py" <<<"$out" \
  && ok "…and names the command that re-derives the sidecar" || no "no remedy in the message: $out"

# ===========================================================================
echo
echo "=== B. the negative arm: identical values are silent ==="
# ===========================================================================
D="$tmp/same"
build "$D" "$T_WBC" "$T_WBC"
run_gate "$D"
[ "$rc" -eq 0 ] && ok "a sidecar that matches its transcript exactly → no finding" \
               || no "an identical pair was flagged: $out"

# The legal asymmetry: 段 2 projects a SUBSET. A transcript with MORE fields than the
# sidecar is normal operation, and a symmetric check would fire on every real archive.
D="$tmp/subset"
build "$D" '[{"label": "白细胞计数", "value": "3.21"}, {"label": "血红蛋白", "value": "128"}, {"label": "血小板", "value": "210"}]' \
           '[{"label": "白细胞计数", "value": "3.21"}]'
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a transcript holding MORE fields than the sidecar is fine — the check is one-directional" \
  || no "the gate demanded symmetry and rejected a legitimate projection subset: $out"

# …and the reverse is exactly what it must catch: a field in the sidecar that the
# transcript never had at all.
D="$tmp/invented"
build "$D" "$T_WBC" '[{"label": "白细胞计数", "value": "3.21"}, {"label": "血红蛋白", "value": "128"}]'
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "…while a field present ONLY in the sidecar is an ERROR (that direction is fabrication)" \
  || no "the sidecar added a field the page never printed and the gate was silent"
grep -qF "'128'" <<<"$out" \
  && ok "…naming the invented value" || no "the invented value is not named: $out"

# ===========================================================================
echo
echo "=== C. formatting tolerance must survive; a changed DIGIT must not ==="
# ===========================================================================
tol() {  # <label> <transcript value> <sidecar value> <expect: ok|err> <why>
  local d="$tmp/tol_$RANDOM$RANDOM"
  build "$d" "[{\"label\": \"$1\", \"value\": \"$2\"}]" "[{\"label\": \"$1\", \"value\": \"$3\"}]"
  run_gate "$d"
  if [ "$4" = "ok" ]; then
    [ "$rc" -eq 0 ] && ok "$5" || no "$5 — but the gate errored: $out"
  else
    [ "$rc" -eq 1 ] && ok "$5" || no "$5 — but the gate was SILENT"
  fi
}

tol 白细胞计数 "3.21" "3.21 ×10^9/L" ok  "the sidecar may carry the unit the transcript omitted (containment, one side)"
tol 白细胞计数 "3.21 ×10^9/L" "3.21" ok  "…and the reverse (the unit may be on either side)"
tol 参考范围   "3.5-9.5" "3.5 - 9.5"  ok  "spacing around a range separator is formatting, not a change"
tol 血小板     "1,234"   "1234"       ok  "a thousands separator is formatting"
tol 血小板     "1234"    "1,234"      ok  "…in either direction"
tol 报告结论   "未见异常" "未见异常"    ok  "an identical CJK string agrees"

# THE ASSERTION THIS SECTION EXISTS FOR. A dropped final digit is the commonest OCR slip
# and is invisible to a human comparing two files. Substring containment calls it a match.
tol 白细胞计数 "3.21" "3.2"  err "'3.2' does NOT match inside '3.21' — a dropped decimal digit is caught"
tol 白细胞计数 "3.2"  "3.21" err "…and the reverse: an ADDED digit is caught too"
tol 白细胞计数 "3.21" "32.1" err "a moved decimal point (32.1 vs 3.21) is caught — an order of magnitude"
tol 白细胞计数 "3.21" "9.99" err "a wholly different number is caught"
tol 血红蛋白   "128"  "129"  err "a one-off integer is caught"
tol 报告结论   "未见异常" "未见明显异常" err "a changed CJK conclusion is caught"

# ===========================================================================
echo
echo "=== D. [PII_MASKED] is skipped — and the skip is the TOKEN, not the page ==="
# ===========================================================================
# Masking is the one transformation that legitimately destroys the original. If the masked
# form had to be findable in the transcript, correct masking would be an error and the
# archive's escape would be to stop masking.
D="$tmp/masked"
build "$D" '[{"label": "住院号", "value": "1234567890123"}, {"label": "白细胞计数", "value": "3.21"}]' \
           '[{"label": "住院号", "value": "[PII_MASKED]"}, {"label": "白细胞计数", "value": "3.21"}]'
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a value masked to [PII_MASKED] is skipped — correct masking is not a drift" \
  || no "correct masking was reported as an inconsistency: $out"

# THE BOUND. The skip applies to the masked FIELD only. A sidecar that masks 住院号 and
# ALSO changes the white-cell count must still be caught; otherwise masking one field
# would launder every other field on the page.
D="$tmp/masked_and_drifted"
build "$D" '[{"label": "住院号", "value": "1234567890123"}, {"label": "白细胞计数", "value": "3.21"}]' \
           '[{"label": "住院号", "value": "[PII_MASKED]"}, {"label": "白细胞计数", "value": "9.99"}]'
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "…but masking one field does NOT launder the others on the same page" \
  || no "a drifted value rode along beside a legitimately masked one"
grep -qF "'9.99'" <<<"$out" && ok "…the drifted value is still named" || no "wrong field reported: $out"
grep -qF "住院号" <<<"$out" \
  && no "the correctly masked 住院号 was ALSO reported — correct masking must not generate noise" \
  || ok "…and the masked field is not reported (no noise from doing the right thing)"

# A value that merely CONTAINS the token (a partially masked string) is skipped too — the
# unmasked remainder is not independently checkable against a value the mask destroyed.
D="$tmp/partial_mask"
build "$D" '[{"label": "联系方式", "value": "张三 13812345678"}]' \
           '[{"label": "联系方式", "value": "张三 [PII_MASKED]"}]'
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a partially masked value is skipped (the token appears anywhere in the value)" \
  || no "a partially masked value was reported as drift: $out"

# ===========================================================================
echo
echo "=== E. scope: the populations with nothing to compare ==="
# ===========================================================================
# No transcript on disk → gate_field_provenance reads the sidecar instead (B3). There is
# no second surface, so there is no comparison to make and inventing one would fail every
# native_text archive.
D="$tmp/notranscript"
build "$D" "$T_WBC" '[{"label": "白细胞计数", "value": "9.99"}]'
rm -rf "$D/raw/transcript"
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a source with no transcript at all is out of scope (B3 gives it to field_provenance)" \
  || no "the gate fabricated a comparison with no second surface: $out"

# A transcript that declares no fields[] while its sidecar declares some is a sidecar that
# did not come from that transcript. Silence here used to be the pinned behaviour; the gate
# now refuses it (an empty transcript frontmatter must not be a way to buy silence).
D="$tmp/nofields"
build "$D" '[]' '[{"label": "白细胞计数", "value": "9.99"}]'
run_gate "$D"
[ "$rc" -ne 0 ] && echo "$out" | grep -q "declares none" \
  && ok "a transcript declaring no fields[] cannot be the origin of a populated sidecar (GAP CLOSED: ERROR)" \
  || no "an empty transcript fields[] bought silence from the gate: rc=$rc $out"

# A one-character value is skipped: a one-character probe sits inside almost any string,
# so matching proves nothing and failing means nothing.
D="$tmp/short"
build "$D" '[{"label": "血型", "value": "A"}]' '[{"label": "血型", "value": "B"}]'
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a sub-2-character value is skipped (_MIN_EVIDENCE_PROBE), as documented" \
  || no "a one-character value produced a finding: $out"

# …and a two-character one is NOT, so the threshold is a threshold rather than a blanket.
D="$tmp/short2"
build "$D" '[{"label": "分期", "value": "T2"}]' '[{"label": "分期", "value": "T4"}]'
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "…while a TWO-character value IS compared (T2 vs T4 — a whole stage)" \
  || no "the short-probe skip swallowed a two-character clinical value: $out"

# A legacy migrated row has no transcript by contract (C3).
D="$tmp/legacy"
build "$D" "$T_WBC" '[{"label": "白细胞计数", "value": "9.99"}]'
python3 - "$D/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["files"][0]["legacy_transcript_unavailable"] = True
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a legacy_transcript_unavailable row is exempt (C3)" \
  || no "the migration exemption does not reach this gate: $out"

# ===========================================================================
echo
echo "=== F. multi-page: the comparison is per PAGE, not against the whole source ==="
# ===========================================================================
# The sidecar declares `page: 2`, so it must match page 2's fields. If the gate pooled
# every page of the source, a value from page 1 would excuse a wrong value on page 2 —
# and a two-page report where the same analyte is printed twice is the normal case.
D="$tmp/perpage"
rm -rf "$D"; mkdir -p "$D"; inv "$D"
md "$D/raw/transcript/s1/page-001.md" '[{"label": "白细胞计数", "value": "9.99"}]'
cat > "$D/raw/transcript/s1/page-002.md" <<'EOF'
---
source_id: s1
page: 2
fields: [{"label": "白细胞计数", "value": "3.21"}]
---
# 全文
第二页。
EOF
cat > "$D/$SIDECAR" <<'EOF'
---
source_id: s1
page: 2
fields: [{"label": "白细胞计数", "value": "9.99"}]
---
# 全文
第二页。
EOF
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "a page-2 sidecar carrying page 1's value is an ERROR — the comparison is page-scoped" \
  || no "a value from another page of the same source excused the mismatch: $out"
grep -qF "page 2" <<<"$out" \
  && ok "…and the finding says which page it compared against" || no "the page scope is not stated: $out"

echo
echo "== sidecar-transcript-consistency: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
