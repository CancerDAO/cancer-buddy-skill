#!/usr/bin/env bash
# tests/unit/mask-structure-edge.test.sh — organize v3, fix spec B10 + A7 (+ the B10
# hard-link refusal in _pathsafe).
#
# WHY THIS FILE EXISTS
# --------------------
# 段 1 writes every transcribed page TWICE: the verbatim copy under `raw/transcript/`,
# which never leaves the vault, and a shape-masked copy under `ocr/`, which 段 2 files
# into a bucket and which every downstream consumer reads. `mask_structure()` is the only
# thing standing between those two files. It walks the parsed frontmatter and masks each
# LEAF, because the previous implementation json.dumps()ed the whole block, ran a line
# masker over the text, and json.loads()ed it back — with a bare
# `except JSONDecodeError: masked_fm = fm` fallback that turned every masking FAILURE into
# a masking BYPASS, writing the unmasked frontmatter to the downstream-readable copy.
#
# A leaf masker has two opposite ways to be wrong, and this file is built around the fact
# that BOTH are catastrophic and they pull in opposite directions:
#
#   UNDER-MASKING — an identifier survives into `ocr/` and from there into every context
#   the archive is ever read in. B10 names two shapes that got through: a NEGATIVE integer
#   id (`住院号: -12345`, an OCR'd 「—12345」 or a spreadsheet-typed column), because the
#   shape regex is anchored and does not match a leading minus; and, historically, any
#   numeric leaf at all, because a text pass over JSON could only reach one by accident.
#
#   OVER-MASKING — a measurement is destroyed and nothing says so. This is the failure
#   people forget, so it gets the most weight here. `repr(0.15000000000000002)` is a
#   19-character string containing a 17-digit unbroken run, and the loose ">=11 bare
#   digits" arm matched it: EVERY `span.bbox` coordinate that happened to land on a
#   binary-inexact float was rewritten to the STRING "[PII_MASKED]". That destroys the
#   page anchor `gate_faithfulness` (A20) checks bbox area and page against, and it
#   destroys it SELECTIVELY — only on the coordinates that happened to be inexact — so the
#   archive half-works and the gate reports a shape error about a coordinate nobody typed.
#   That is the single most important assertion in this file. The same class of damage is
#   why a >=11-digit leaf under a 时间/日期/采集/报告 label is NOT rewritten: a collection
#   datetime `20240808143000` is the timeline, and a masked timeline is a silently wrong
#   archive rather than a visibly incomplete one. The skip is RECORDED
#   (`skipped_as_timestamp`) rather than performed silently, because a silent exemption and
#   a silent leak look identical from outside.
#
# And the third way to be wrong: FAILING OPEN. A leaf type the masker does not understand
# used to be handed back untouched and counted as clean. It now raises, ingest catches it,
# and the page is `invalid` with NEITHER copy written — a page that vanishes loudly is
# recoverable, a page that lands unmasked is not. Asserting that only against
# `mask_structure()` would prove the raise and not the consequence, so the fail-closed arm
# below is driven through the REAL `ingest_transcripts.py` and checks the filesystem.
#
# The hard-link arm belongs with these because it is the same property one layer down:
# `contained()` resolves symlinks, but a hard link has no target to resolve — the second
# name IS the file — so a perfectly ordinary-looking `ocr/<sid>/page-NNN.md` can make every
# masked-copy write land simultaneously at a name outside the archive. `st_nlink > 1` on an
# output path is never a legitimate state, because every file this pipeline writes is one
# this pipeline created.
#
# Every rule below is asserted in BOTH directions. A masker proven only by what it masks is
# a masker that may be masking everything, and a masker proven only by what it leaves alone
# is a masker that may be doing nothing at all.
#
# Fully synthetic fixtures, deterministic, zero network, zero LLM.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SCRIPTS="$ORG/scripts"
INGEST="$SCRIPTS/ingest_transcripts.py"

if ! python3 -c "import fitz, PIL" >/dev/null 2>&1; then
  echo "SKIP: mask-structure-edge needs PyMuPDF + Pillow to synthesize the 段 0 page pack" >&2
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# m <json-node> -> prints "<masked-json>\t<spans-json>", or "RAISED:<Type>:<msg>"
m() {
  python3 - "$ORG" "$1" <<'PYEOF'
import json, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import pii_rescan as p
node = json.loads(sys.argv[2])
try:
    out, spans = p.mask_structure(node)
except Exception as exc:                                   # noqa: BLE001 - the point
    print("RAISED:%s:%s" % (type(exc).__name__, exc))
else:
    print(json.dumps(out, ensure_ascii=False) + "\t" + json.dumps(spans, ensure_ascii=False))
PYEOF
}
masked_of() { m "$1" | cut -f1; }
spans_of()  { m "$1" | cut -f2; }

# ===========================================================================
# A. mask_structure() leaf edges — B10 + A7, unit level
# ===========================================================================
echo "=== A. leaf shape decisions (B10 / A7) ==="

# ---- A1/A2/A3: a negative integer identifier is judged on its ABSOLUTE value ----
# `"%d" % -12345` renders `-12345` and `^[A-Za-z]{0,3}\d{4,}$` does not match a leading
# minus, so the id walked straight through. A sign is not part of an identifier's shape;
# it is a transcription artefact.
[ "$(masked_of '{"住院号": -12345}')" = '{"住院号": "[PII_MASKED]"}' ] \
  && ok "住院号: -12345 (negative int leaf) -> [PII_MASKED] (shape judged on |value|)" \
  || no "negative identifier leaf survived masking: $(masked_of '{"住院号": -12345}')"

echo "$(spans_of '{"住院号": -12345}')" | grep -q '"kind": "record_number"' \
  && ok "…and it is recorded as a record_number span (the mask is auditable)" \
  || no "no record_number span for the negative identifier"

echo "$(spans_of '{"住院号": -12345}')" | grep -qv '\-12345' \
  && ok "…and the span records kind+len only, never the original value" \
  || no "the span leaked the original identifier"

[ "$(masked_of '{"住院号": 12345}')" = '{"住院号": "[PII_MASKED]"}' ] \
  && ok "control: the same id WITHOUT the sign is masked identically (no new behaviour introduced)" \
  || no "positive identifier leaf was not masked"

# NEGATIVE ARM — the rule is (identifier KEY x identifier SHAPE), not "mask negatives".
# Without this, A1 is satisfied by a masker that erases every negative number on the page,
# which would take out every 基线变化 and every 差值.
[ "$(masked_of '{"较基线变化": -12345}')" = '{"较基线变化": -12345}' ] \
  && ok "negative arm: -12345 under a NON-identifier key is left alone (it is a measurement)" \
  || no "a negative measurement was masked: $(masked_of '{"较基线变化": -12345}')"

# ---- A4/A5/A6: the >=11-digit timestamp carve-out is KEY-gated -------------------
ts_node='{"采集时间": 20240808143000}'
[ "$(masked_of "$ts_node")" = '{"采集时间": 20240808143000}' ] \
  && ok "采集时间: 20240808143000 (14 digits) is NOT rewritten — a masked timeline is a silently wrong archive" \
  || no "a compact collection datetime was masked: $(masked_of "$ts_node")"

echo "$(spans_of "$ts_node")" | grep -q '"kind": "skipped_as_timestamp"' \
  && ok "…and the skip is RECORDED as skipped_as_timestamp (a silent exemption is unreviewable)" \
  || no "the timestamp skip was performed silently: $(spans_of "$ts_node")"

echo "$(spans_of "$ts_node")" | grep -q '"key": "采集时间"' \
  && ok "…naming the key that excused it, so a reviewer can see which shapes were let through" \
  || no "the skipped_as_timestamp record does not name the key"

# `masked_spans` must stay EMPTY for this leaf: nothing was masked, and a skip counted as
# a mask would inflate every downstream "N identifiers removed" number.
[ "$(python3 -c "
import json,sys
s=json.loads(sys.argv[1]); print(len([x for x in s if x['kind']!='skipped_as_timestamp']))" "$(spans_of "$ts_node")")" = "0" ] \
  && ok "…and it contributes ZERO masking spans (a skip is not a mask)" \
  || no "the timestamp leaf produced a masking span"

# NEGATIVE ARM 1 — an identifier key WINS over a timestamp-ish shape.
[ "$(masked_of '{"检验号": 20240808143000}')" = '{"检验号": "[PII_MASKED]"}' ] \
  && ok "negative arm: the same 14 digits under 检验号 IS masked (identifier key beats the carve-out)" \
  || no "a 14-digit 检验号 escaped through the timestamp carve-out"

# NEGATIVE ARM 2 — a neutral key gets no carve-out either. This is what proves the
# exemption is gated on the LABEL and not merely on "looks like a date".
[ "$(masked_of '{"备注": 20240808143000}')" = '{"备注": "[PII_MASKED]"}' ] \
  && ok "negative arm: the same 14 digits under a neutral key IS masked (carve-out is label-gated, not length-gated)" \
  || no "a 14-digit run under a neutral key was skipped as a timestamp"

# ---- A7/A8/A9: THE bbox float regression (the P0 this file exists for) -----------
# First establish that the shape WOULD have matched, or the assertion below is vacuous.
[ "$(python3 -c 'print(len(str(0.15000000000000002)), max(len(r) for r in __import__("re").findall(r"\d+", str(0.15000000000000002))))')" = "19 17" ] \
  && ok "str(0.15000000000000002) is 19 chars with a 17-digit run — squarely inside the >=11-digit arm" \
  || no "the float repr assumption no longer holds; the regression fixture needs rebuilding"

bbox='{"span": {"page": 1, "bbox": [0.15000000000000002, 0.2, 0.3, 0.4]}}'
[ "$(masked_of "$bbox")" = '{"span": {"page": 1, "bbox": [0.15000000000000002, 0.2, 0.3, 0.4]}}' ] \
  && ok "bbox float 0.15000000000000002 survives UNTOUCHED (G2 P0: a masked coordinate destroys the page anchor)" \
  || no "a binary-inexact bbox float was masked: $(masked_of "$bbox")"

[ "$(spans_of "$bbox")" = "[]" ] \
  && ok "…and the whole bbox produces ZERO spans (nothing was even considered masked)" \
  || no "the bbox produced spans: $(spans_of "$bbox")"

# NEGATIVE ARM 1 — a real identifier in the same slot IS masked, so the float exemption is
# not "anything inside span.bbox is exempt".
idcard='{"span": {"page": 1, "bbox": ["11010519491231002X", 0.2, 0.3, 0.4]}}'
[ "$(masked_of "$idcard")" = '{"span": {"page": 1, "bbox": ["[PII_MASKED]", 0.2, 0.3, 0.4]}}' ] \
  && ok "negative arm: an 18-digit 身份证 string in the SAME bbox slot IS masked" \
  || no "an identity-card string inside bbox survived: $(masked_of "$idcard")"

# NEGATIVE ARM 2 — the same digit run, without the decimal point, IS masked. This is the
# assertion that pins the exemption to the TYPE (a float is a measured quantity by
# construction) rather than to the digits.
digits='{"span": {"page": 1, "bbox": ["15000000000000002", 0.2, 0.3, 0.4]}}'
[ "$(masked_of "$digits")" = '{"span": {"page": 1, "bbox": ["[PII_MASKED]", 0.2, 0.3, 0.4]}}' ] \
  && ok "negative arm: the same 17-digit run as a STRING is masked (the exemption is type-based, not digit-based)" \
  || no "a 17-digit string escaped: $(masked_of "$digits")"

# ---- A10: the semantic key of a fields[] value lives in a SIBLING ----------------
# `{"label": "住院号", "value": 12345}`: the key of the numeric leaf is the literal string
# "value", which says nothing. Without the sibling lookup, every identifier a model lifted
# OUT of the body and INTO fields[] survived untouched — and fields[] is exactly where
# 段 2 reads values from.
sib='{"label": "住院号", "value": -12345, "span": {"page": 1, "bbox": [0.15000000000000002, 0.2, 0.3, 0.4]}}'
echo "$(masked_of "$sib")" | grep -q '"value": "\[PII_MASKED\]"' \
  && ok "fields[] entry: the sibling 'label' supplies the identifier context for 'value'" \
  || no "a fields[] identifier survived because its own key was just \"value\": $(masked_of "$sib")"

echo "$(masked_of "$sib")" | grep -q '"label": "住院号"' \
  && ok "…while the label itself is preserved (keys and labels are schema, not content)" \
  || no "the label was masked away, destroying what the masked value was"

echo "$(masked_of "$sib")" | grep -q '0.15000000000000002' \
  && ok "…and the inexact bbox float in the SAME object is still untouched" \
  || no "the bbox float was masked inside a fields[] entry"

# ---- A11/A12: fail closed on a leaf type the masker cannot inspect ---------------
out="$(m '{"adapter_note": "x"}')"   # sanity: a plain str leaf does not raise
echo "$out" | grep -qv "RAISED" \
  && ok "a plain string leaf does not raise (the fail-closed arm is not firing on everything)" \
  || no "a string leaf raised: $out"

tup="$(python3 - "$ORG" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import pii_rescan as p
try:
    p.mask_structure({"adapter_note": ("a", "b")})
except Exception as exc:                                   # noqa: BLE001
    print("RAISED:%s:%s" % (type(exc).__name__, exc))
else:
    print("RETURNED")
PYEOF
)"
echo "$tup" | grep -q "^RAISED:TypeError:" \
  && ok "a tuple leaf raises TypeError (fail closed: it is NOT handed back unmasked)" \
  || no "a tuple leaf did not raise TypeError: $tup"
echo "$tup" | grep -q "unmaskable leaf type 'tuple'" \
  && ok "…and the message names the type it could not inspect" \
  || no "the TypeError message does not name the leaf type: $tup"
echo "$tup" | grep -q "adapter_note" \
  && ok "…and the key, so the offending leaf can be found" \
  || no "the TypeError message does not name the key: $tup"

byt="$(python3 - "$ORG" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import pii_rescan as p
try:
    p.mask_structure({"blob": b"\x01\x02"})
except TypeError as exc:
    print("RAISED:%s" % exc)
else:
    print("RETURNED")
PYEOF
)"
echo "$byt" | grep -q "^RAISED:" \
  && ok "a bytes leaf raises too — the refusal is 'any type I cannot inspect', not a tuple special case" \
  || no "a bytes leaf was passed through: $byt"

# ---- A13: recursion does not mangle the structure --------------------------------
nest='{"fields": [{"label": "白细胞计数", "value": "3.21", "unit": "10^9/L"}, {"label": "住院号", "value": 987654}], "page": 3}'
echo "$(masked_of "$nest")" | grep -q '"value": "3.21"' \
  && ok "a clinical value inside a nested list survives the walk verbatim" \
  || no "a lab value was altered by the recursive walk: $(masked_of "$nest")"
echo "$(masked_of "$nest")" | grep -q '"page": 3' \
  && ok "…and a small structural integer (page: 3) is not masked" \
  || no "a structural integer was masked"
echo "$(masked_of "$nest")" | grep -q '"住院号", "value": "\[PII_MASKED\]"' \
  && ok "…while the identifier in the next list element IS masked (the walk reaches every leaf)" \
  || no "the second list element was not walked"

# ===========================================================================
# B. the SAME rules through the real 段 0 -> 段 1 pipeline
#
# A7's contract is not "mask_structure raises"; it is "if masking fails in ANY step the
# page is invalid and NEITHER copy is written". That is a statement about the filesystem
# after ingest_transcripts.py ran, so it is asserted against the filesystem after
# ingest_transcripts.py ran.
# ===========================================================================
echo
echo "=== B. fail-closed and shape decisions through the real ingest flow ==="

P="$tmp/patient"
mkdir -p "$P/raw/incoming"
python3 - "$P/raw/incoming" <<'PYEOF'
import sys, fitz
doc = fitz.open()
for i in range(4):
    pg = doc.new_page(width=595, height=842)
    pg.insert_text((72, 100 + i), f"PAGE {i+1} REPORT", fontsize=14)
doc.save(f"{sys.argv[1]}/rep.pdf"); doc.close()
PYEOF

python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r1 --model-id test-model \
  --source s001=raw/incoming/rep.pdf >"$tmp/prep.log" 2>&1 \
  || { echo "SKIP: prepare_pages failed: $(cat "$tmp/prep.log")" >&2; exit 0; }
PV="$(python3 -c "import json;print(json.load(open('$P/raw/_provenance/r1/pages.json'))['prompt_version'])")"

# page writer: `extra` is spliced into the frontmatter verbatim.
page() {  # <outdir> <page> [extra-frontmatter-line]
  python3 - "$1" "$2" "$PV" "${3:-}" <<'PYEOF'
import pathlib, sys
out, pg, pv, extra = pathlib.Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
fields = (
    '[{"label": "住院号", "value": -12345, "unit": null, '
    f'"span": {{"page": {pg}, "bbox": [0.15000000000000002, 0.2, 0.3, 0.4]}}}}, '
    '{"label": "采集时间", "value": 20240808143000, "unit": null, '
    f'"span": {{"page": {pg}, "bbox": [0.11, 0.22, 0.33, 0.44]}}}}]'
)
body = f"""---
source_id: s001
page: {pg}
text_layer_kind: born_digital
doc_kind: 检验报告
clinical_class: lab
fields: {fields}
high_risk: ["住院号"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.0
needs_rotation: false
prompt_version: "{pv}"
model_id: "test-model"
{extra}
---
# 全文

PAGE {pg} REPORT
"""
out.mkdir(parents=True, exist_ok=True)
out.joinpath(f"s001.page-{pg:03d}.md").write_text(body, encoding="utf-8")
PYEOF
}

nlink() { python3 -c "import os,sys;print(os.stat(sys.argv[1]).st_nlink)" "$1"; }

# --- the hard-link trap, planted BEFORE ingest runs ------------------------------
# `ocr/s001/page-003.md` is a second name for a file outside the archive. containment
# approves it (it resolves to exactly where it claims to be); only st_nlink sees it.
printf 'OUTSIDE SECRET — must never be overwritten\n' > "$tmp/outside.md"
mkdir -p "$P/ocr/s001"
ln "$tmp/outside.md" "$P/ocr/s001/page-003.md"
[ "$(nlink "$tmp/outside.md")" -eq 2 ] \
  && ok "fixture: ocr/s001/page-003.md is a hard link (st_nlink=2) to a file outside the archive" \
  || no "could not create the hard-link fixture (st_nlink=$(nlink "$tmp/outside.md"))"

# --- the NEGATIVE arm of the hard-link rule: an ordinary stale file is overwritten --
printf 'stale placeholder from an earlier run\n' > "$P/ocr/s001/page-004.md"

O1="$tmp/out1"
page "$O1" 1
page "$O1" 3
page "$O1" 4

python3 "$INGEST" "$P" --run-id r1 --from "$O1" --model-id test-model >"$tmp/ing1.log" 2>&1
rc=$?
cp "$P/raw/_provenance/r1/transcribe-manifest.json" "$tmp/manifest1.json"

[ "$rc" -eq 1 ] \
  && ok "ingest exits 1 when a page was rejected (the run does not report success)" \
  || no "ingest exit code was $rc, expected 1"

# ---- B1/B2/B3/B4: the good page ---------------------------------------------------
[ -f "$P/raw/transcript/s001/page-001.md" ] && [ -f "$P/ocr/s001/page-001.md" ] \
  && ok "page 1 landed in BOTH raw/transcript/ and ocr/" \
  || no "page 1 is missing one of its two copies"

grep -q '"住院号", "value": "\[PII_MASKED\]"' "$P/ocr/s001/page-001.md" \
  && ok "…the masked copy has 住院号: -12345 -> [PII_MASKED] (B10 negative-id, end to end)" \
  || no "the negative identifier survived into ocr/: $(grep -m1 fields: "$P/ocr/s001/page-001.md")"

grep -q '"住院号", "value": -12345' "$P/raw/transcript/s001/page-001.md" \
  && ok "…while the verbatim vault copy still holds the real value (masking is a projection, not an edit)" \
  || no "the verbatim copy was altered"

grep -qF '0.15000000000000002' "$P/ocr/s001/page-001.md" \
  && ok "…the inexact bbox float is byte-identical in the masked copy (G2 P0, end to end)" \
  || no "a bbox coordinate was rewritten in the masked copy — gate_faithfulness anchors are destroyed"

grep -q '"采集时间", "value": 20240808143000' "$P/ocr/s001/page-001.md" \
  && ok "…and the 14-digit 采集时间 is preserved in the masked copy" \
  || no "the collection datetime was masked in ocr/"

python3 - "$tmp/manifest1.json" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
pg = next(p for p in m["pages"] if p.get("page") == 1)
skips = pg.get("skipped_as_timestamp") or []
spans = pg.get("masked_spans") or []
assert any("采集时间" in s.get("key", "") for s in skips), f"no skip record: {skips}"
assert any(s["kind"] == "record_number" for s in spans), f"no mask span: {spans}"
assert all(s["kind"] != "skipped_as_timestamp" for s in spans), f"skip counted as mask: {spans}"
assert all("value" not in s and "-12345" not in json.dumps(s) for s in spans), "span leaked a value"
PYEOF
[ $? -eq 0 ] \
  && ok "…manifest records skipped_as_timestamp separately from masked_spans, and no span carries a value" \
  || no "the manifest span bookkeeping is wrong for page 1"

# ---- B7: the hard-link refusal ----------------------------------------------------
grep -q "hard links" "$tmp/ing1.log" \
  && ok "page 3 refused with a message naming the hard link" \
  || no "the hard-link refusal message is missing: $(cat "$tmp/ing1.log")"

grep -q "has no target to resolve" "$tmp/ing1.log" \
  && ok "…and the message says WHY containment cannot see it" \
  || no "the refusal does not explain why containment is insufficient"

[ "$(cat "$tmp/outside.md")" = "OUTSIDE SECRET — must never be overwritten" ] \
  && ok "…the file outside the archive is byte-for-byte unchanged" \
  || no "the out-of-archive file was overwritten through its second name: $(cat "$tmp/outside.md")"

[ ! -f "$P/raw/transcript/s001/page-003.md" ] \
  && ok "…and page 3's VERBATIM copy was not written either (a refusal at any step writes nothing)" \
  || no "the verbatim copy landed although the masked write was refused — half a page is worse than none"

python3 - "$tmp/manifest1.json" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
bad = [p for p in m["pages"] if p.get("status") == "invalid"
       and any("hard link" in e for e in p.get("errors", []))]
sys.exit(0 if len(bad) == 1 else 1)
PYEOF
[ $? -eq 0 ] \
  && ok "…and the manifest records exactly one invalid page carrying the hard-link reason" \
  || no "the hard-link rejection is not recorded in the manifest"

# ---- B8: negative arm — an ordinary pre-existing file is replaced normally ---------
[ -f "$P/ocr/s001/page-004.md" ] && ! grep -q "stale placeholder" "$P/ocr/s001/page-004.md" \
  && ok "negative arm: an ordinary (st_nlink=1) stale ocr file IS overwritten — the rule is 'second name', not 'file exists'" \
  || no "a pre-existing single-linked ocr file was refused or left stale"

[ -f "$P/raw/transcript/s001/page-004.md" ] \
  && ok "…and page 4's verbatim copy landed too" \
  || no "page 4 did not complete"

# ---- B5/B6: the unmaskable leaf, through real ingest ------------------------------
# JSON cannot express a tuple, so the ONLY way an unmaskable leaf reaches mask_structure
# today is the scenario the code's own docstring names: a parser variant that yields a
# type JSON does not have (a PyYAML path returning datetime.date, a binary leaf, a custom
# object). That is simulated at the narrowest possible point — the frontmatter scalar
# decoder — and everything downstream of it is the real script: validation, masking, the
# path checks, the writes, the manifest and the exit code.
O2="$tmp/out2"
page "$O2" 2 'adapter_note: __UNMASKABLE_LEAF__'

run_patched() {  # <outdir>
  python3 - "$ORG" "$P" "$1" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import ingest_transcripts as it
_orig = it._scalar
def patched(blob):
    v = _orig(blob)
    return ("unmaskable", "leaf") if v == "__UNMASKABLE_LEAF__" else v
it._scalar = patched
sys.exit(it.main([sys.argv[2], "--run-id", "r1", "--from", sys.argv[3],
                  "--model-id", "test-model"]))
PYEOF
}

run_patched "$O2" >"$tmp/ing2.log" 2>&1
rc=$?
[ "$rc" -eq 1 ] \
  && ok "an unmaskable leaf makes the ingest run exit 1" \
  || no "ingest exited $rc on an unmaskable leaf, expected 1"

grep -q "masking failed (TypeError" "$tmp/ing2.log" \
  && ok "…reported as 'masking failed (TypeError…)', naming the real cause" \
  || no "the ingest log does not report the masking failure: $(cat "$tmp/ing2.log")"

grep -q "NEITHER copy is written" "$tmp/ing2.log" \
  && ok "…and states the fail-closed contract in the message a human will read" \
  || no "the message does not state that neither copy is written"

[ ! -f "$P/raw/transcript/s001/page-002.md" ] \
  && ok "…raw/transcript/s001/page-002.md was NOT written" \
  || no "the verbatim copy of an unmaskable page landed on disk"

[ ! -f "$P/ocr/s001/page-002.md" ] \
  && ok "…ocr/s001/page-002.md was NOT written (the bypass this rule exists to prevent)" \
  || no "the DOWNSTREAM-READABLE copy of an unmaskable page landed on disk"

python3 - "$P/raw/_provenance/r1/transcribe-manifest.json" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
bad = [p for p in m["pages"] if p.get("status") == "invalid"
       and any("masking failed" in e for e in p.get("errors", []))]
sys.exit(0 if len(bad) == 1 else 1)
PYEOF
[ $? -eq 0 ] \
  && ok "…and the manifest records the page as invalid with the masking reason" \
  || no "the masking failure is not recorded in the manifest"

# NEGATIVE ARM — the SAME page, same patched runner, without the unmaskable leaf, lands
# normally. Without this, everything above is satisfied by a runner that rejects every
# page it is handed, and the fail-closed arm would prove nothing about masking.
O3="$tmp/out3"
page "$O3" 2
run_patched "$O3" >"$tmp/ing3.log" 2>&1
rc=$?
[ "$rc" -eq 0 ] \
  && ok "negative arm: the identical page WITHOUT the unmaskable leaf ingests cleanly (rc=0)" \
  || no "the control page was rejected too (rc=$rc): $(cat "$tmp/ing3.log")"

[ -f "$P/raw/transcript/s001/page-002.md" ] && [ -f "$P/ocr/s001/page-002.md" ] \
  && ok "…and both copies of it exist — the rejection above was about the leaf, not the harness" \
  || no "the control page produced no output"

grep -qF '0.15000000000000002' "$P/ocr/s001/page-002.md" \
  && ok "…with its inexact bbox float intact" \
  || no "the control page lost its bbox float"

# ===========================================================================
# C. THE STRING ARM — the two B10 carve-outs now reach string leaves (H1)
#
# B10 describes both carve-outs in terms of "叶子" without qualifying the leaf's JSON type,
# but they used to live ONLY in the numeric arm of mask_scalar(): the string arm called
# mask_text(value) and never received `key` at all. That split was the wrong way round for
# the shipping pipeline. The canonical transcribe prompt
# (references/organizer-prompt-phase1-transcribe.md §2, examples at :100) writes every
# fields[].value as a QUOTED JSON string, so in practice ALMOST EVERY leaf that reaches
# mask_structure() arrives as a string — meaning the numeric-only carve-outs were dormant
# exactly where they were needed and the two shapes below behaved the OPPOSITE way from
# their numeric twins:
#
#   an OCR'd 「—12345」 typed as the string "-12345" under 住院号 walked through UNMASKED
#   (under-masking: an identifier reaching `ocr/` and every downstream consumer), while
#
#   a collection datetime "20240808143000" under 采集时间 was rewritten to the STRING
#   "[PII_MASKED]" (over-masking: the timeline destroyed, silently, by JSON quoting).
#
# H1 closes that: mask_scalar() now takes `key` on both arms, so the shape decision is made
# on the VALUE and its LABEL, never on whether the transcriber happened to quote it. The
# assertions below are the paired form of A1/A6 — same values, both JSON types, and the
# numeric twin is re-asserted beside each string case so a future regression that fixes one
# arm by breaking the other cannot pass.
# ===========================================================================
echo
echo "=== C. the string arm carries both carve-outs (H1) ==="

# ---- C1: identifier-shaped STRING leaf is masked, sign and quoting notwithstanding ----
[ "$(masked_of '{"住院号": "-12345"}')" = '{"住院号": "[PII_MASKED]"}' ] \
  && ok "住院号 as the STRING \"-12345\" IS masked — the abs-value rule reaches the string arm (H1)" \
  || no "the string form of the negative identifier survived: $(masked_of '{"住院号": "-12345"}')"

echo "$(spans_of '{"住院号": "-12345"}')" | grep -q '"kind": "record_number"' \
  && ok "…recorded as a record_number span, exactly like its numeric twin" \
  || no "the string identifier was masked with no record_number span: $(spans_of '{"住院号": "-12345"}')"

echo "$(spans_of '{"住院号": "-12345"}')" | grep -qv '12345' \
  && ok "…and the span still records kind+len only, never the original value" \
  || no "the span leaked the identifier it masked"

[ "$(masked_of '{"住院号": -12345}')" = '{"住院号": "[PII_MASKED]"}' ] \
  && ok "…and the NUMERIC twin is masked identically — same value, same outcome, quoting no longer decides" \
  || no "the numeric twin stopped being masked: $(masked_of '{"住院号": -12345}')"

# ---- C2: timestamp-labelled STRING leaf is exempt, and the exemption is RECORDED ----
[ "$(masked_of '{"采集时间": "20240808143000"}')" = '{"采集时间": "20240808143000"}' ] \
  && ok "采集时间 as the STRING \"20240808143000\" is NOT masked — skipped_as_timestamp reaches the string arm (H1)" \
  || no "the string collection datetime was destroyed: $(masked_of '{"采集时间": "20240808143000"}')"

echo "$(spans_of '{"采集时间": "20240808143000"}')" | grep -q '"kind": "skipped_as_timestamp"' \
  && ok "…and the exemption is RECORDED, not silent — a silent skip and a silent leak look alike from outside" \
  || no "the string timestamp was exempted with no skipped_as_timestamp span: $(spans_of '{"采集时间": "20240808143000"}')"

echo "$(spans_of '{"采集时间": "20240808143000"}')" | grep -q '"key": "采集时间"' \
  && ok "…and the span names the LABEL that bought the exemption, so a wrong label is auditable" \
  || no "the skipped_as_timestamp span does not name the key that triggered it"

[ "$(masked_of '{"采集时间": 20240808143000}')" = '{"采集时间": 20240808143000}' ] \
  && ok "…and the NUMERIC twin is exempt identically (the arms did not swap defects)" \
  || no "the numeric timestamp twin started being masked: $(masked_of '{"采集时间": 20240808143000}')"

# ---- C3: the exemption is bought by the LABEL, not by the digit run ----
# Without this, C2 is satisfied by an implementation that stopped masking 14-digit strings
# altogether — which would re-open the under-masking hole C1 just closed.
[ "$(masked_of '{"检验号": "20240808143000"}')" = '{"检验号": "[PII_MASKED]"}' ] \
  && ok "negative arm: the SAME 14-digit string under 检验号 IS masked — the label buys the exemption, not the length" \
  || no "a 14-digit string under a record-number label escaped: $(masked_of '{"检验号": "20240808143000"}')"

[ "$(masked_of '{"报告日期": "20240808143000"}')" = '{"报告日期": "20240808143000"}' ] \
  && ok "…and 报告日期 (another 时间/日期 label) is exempt too — the carve-out is the label CLASS, not one word" \
  || no "报告日期 did not get the timestamp exemption: $(masked_of '{"报告日期": "20240808143000"}')"

# ---- C4: the string arm did not become a blanket pass ----
# mask_text()'s own shapes must still fire on string leaves whose key says nothing.
[ "$(masked_of '{"备注": "联系电话 13812345678"}')" != '{"备注": "联系电话 13812345678"}' ] \
  && ok "negative arm: a CN mobile inside an unlabelled string leaf is still rewritten by mask_text (A7 intact)" \
  || no "the string arm stopped applying mask_text — the H1 change turned it into a pass-through"

[ "$(masked_of '{"检验项目": "白细胞计数 3.21"}')" = '{"检验项目": "白细胞计数 3.21"}' ] \
  && ok "…while an ordinary clinical string is untouched (no new over-masking came in with H1)" \
  || no "a clinical string leaf was rewritten: $(masked_of '{"检验项目": "白细胞计数 3.21"}')"

echo
echo "== mask-structure-edge: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
