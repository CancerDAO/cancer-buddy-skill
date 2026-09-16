#!/usr/bin/env bash
# tests/unit/merge-fields.test.sh — organize v3, fix spec A19 + A22.
#
# 段 2 is the projection step: deciding that THIS page's 白细胞计数 belongs in labs.json
# as WBC with this unit. Collecting the `fields[]` blocks that 段 1 already wrote is not
# projection — the value is already a string on the page and its span already points at a
# bbox in raw/ — so doing it with a model costs a subagent per group and adds a step at
# which a number can change with nothing noticing. merge_fields.py is the deterministic
# half: it reads every ok page's frontmatter, groups the fields, and writes ONE ledger,
# raw/_provenance/<run>/field_candidates.json. gate_field_provenance later requires every
# labs.json raw_value to appear in that ledger, which only works if the ledger is verbatim.
#
# The grouping is the load-bearing part, and it is keyed on `clinical_class`, never on the
# bucket a document was filed in (A22). Those differ constantly: a discharge summary filed
# under 03_ can carry the only molecular result in the archive. The four 段 2 worker groups
# are labs ← lab; molecular_pathology ← molecular + pathology; timeline_narrative ←
# narrative + imaging; open_fields_filing ← admin + unknown, plus EVERY `kind: novel` page
# whatever class it looks like, because novel material has no pinned projection target.
# The point of the split is isolation: a labs worker that never sees the molecular pages
# cannot source a lab value out of a variant table, and its context is a fraction of the
# archive. A page landing in the wrong group is that guarantee quietly removed.
#
# The other rule this file pins is WHICH COPY gets read. The default is the masked surface
# under ocr/, not raw/transcript/ — the verbatim vault is for deterministic scripts and
# authorised humans (A27), and the ledger is an intermediate that 段 2 workers read, so it
# must be built from the same surface they are allowed to see. A field whose value was
# shape-masked arrives as [PII_MASKED] and is recorded as such: a masked identifier is a
# fact about the page, not a gap to be filled in from somewhere else. --from-transcript
# reads the verbatim pages instead and is for deterministic auditing only.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SCRIPTS="$ORG/scripts"
MERGE="$SCRIPTS/merge_fields.py"

if ! python3 -c "import fitz, PIL" >/dev/null 2>&1; then
  echo "SKIP: merge-fields needs PyMuPDF + Pillow to synthesize page fixtures" >&2
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# --------------------------------------------------------------------------- #
# Fixture: one 9-page born-digital PDF run through the real 段 0 → 段 1 scripts, so
# the manifest merge_fields reads is a REAL transcribe-manifest.json and not a
# hand-written idea of one. Each page declares a different clinical_class, which is
# what makes the grouping observable; page 8 is `novel:` with clinical_class lab (the
# case where kind must beat class), and page 9 carries a 14-digit identifier so the
# masked and verbatim surfaces differ on a value we can name.
# --------------------------------------------------------------------------- #
P="$tmp/patient"
mkdir -p "$P/raw/incoming"
python3 - "$P/raw/incoming" <<'PYEOF'
import sys, fitz
doc = fitz.open()
for i in range(9):
    pg = doc.new_page(width=595, height=842)
    pg.insert_text((72, 100 + i), f"PAGE {i+1} REPORT", fontsize=14)
doc.save(f"{sys.argv[1]}/multi.pdf"); doc.close()
PYEOF

python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r1 --model-id test-model \
  --source s001=raw/incoming/multi.pdf >"$tmp/prep.log" 2>&1 \
  || { echo "SKIP: prepare_pages failed: $(cat "$tmp/prep.log")" >&2; exit 0; }

PV="$(python3 -c "
import json; print(json.load(open('$P/raw/_provenance/r1/pages.json'))['prompt_version'])")"

OUT="$tmp/model_out"; mkdir -p "$OUT"
python3 - "$OUT" "$PV" <<'PYEOF'
import sys, pathlib
out, pv = pathlib.Path(sys.argv[1]), sys.argv[2]
specs = [
    (1, "lab",       "检验报告",              "WBC",          "3.21"),
    (2, "molecular", "NGS报告",               "EGFR",         "p.L858R"),
    (3, "pathology", "病理报告",              "组织学类型",   "腺癌"),
    (4, "narrative", "出院小结",              "出院日期",     "2026-03-20"),
    (5, "imaging",   "CT报告",                "靶病灶长径",   "32mm"),
    (6, "admin",     "费用发票",              "发票金额",     "1234.50"),
    (7, "unknown",   "其他",                  "不明字段",     "abc"),
    (8, "lab",       "novel:microbiome-panel", "丰度",        "0.42"),
    (9, "lab",       "检验报告",              "住院号",       "12345678901234"),
]
for page, cc, dk, label, val in specs:
    (out / f"s001.page-{page:03d}.md").write_text(f"""---
source_id: s001
page: {page}
text_layer_kind: born_digital
doc_kind: {dk}
clinical_class: {cc}
fields: [{{"label": "{label}", "value": "{val}", "unit": null, "span": {{"page": {page}, "bbox": [0.10, 0.12, 0.40, 0.18]}}}}]
high_risk: ["{label}"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.0
needs_rotation: false
prompt_version: "{pv}"
model_id: "test-model"
---
# 全文

PAGE {page} REPORT
{label} {val}
""", encoding="utf-8")
PYEOF

python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r1 --from "$OUT" --model-id test-model \
  >"$tmp/ingest.log" 2>&1 \
  || { echo "SKIP: ingest_transcripts failed: $(cat "$tmp/ingest.log")" >&2; exit 0; }

LEDGER="$P/raw/_provenance/r1/field_candidates.json"

# where did label X land?
group_of() {  # <ledger> <label>
  python3 -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(next((g for g,v in d['groups'].items() for x in v if x['label']==sys.argv[2]), 'ABSENT'))" \
    "$1" "$2"
}
value_of() {  # <ledger> <label>
  python3 -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print(next((x['value'] for v in d['groups'].values() for x in v if x['label']==sys.argv[2]), 'ABSENT'))" \
    "$1" "$2"
}

# ===========================================================================
# A. the ledger is written where 段 2 looks for it
# ===========================================================================
echo "=== A. merge_fields writes one ledger per run ==="

python3 "$MERGE" "$P" --run-id r1 >"$tmp/merge.log" 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "merge_fields exits 0 on a clean 9-page run" \
  || no "merge_fields exited $rc: $(cat "$tmp/merge.log")"
[ -f "$LEDGER" ] && ok "ledger written to raw/_provenance/<run>/field_candidates.json" \
  || no "field_candidates.json not written"
[ "$(python3 -c "
import json; print(json.load(open('$LEDGER'))['group_key'])")" = "clinical_class" ] \
  && ok "the ledger declares group_key=clinical_class (A22), not the bucket path" \
  || no "group_key is not clinical_class"
[ "$(python3 -c "
import json; print(json.load(open('$LEDGER'))['counts']['pages_read'])")" = "9" ] \
  && ok "all 9 ok pages were read" \
  || no "pages_read is $(python3 -c "import json;print(json.load(open('$LEDGER'))['counts']['pages_read'])")"

# ===========================================================================
# B. the A22 grouping, one clinical_class at a time
# ===========================================================================
echo "=== B. clinical_class → 段 2 worker group ==="

for spec in "WBC labs lab" \
            "EGFR molecular_pathology molecular" \
            "组织学类型 molecular_pathology pathology" \
            "出院日期 timeline_narrative narrative" \
            "靶病灶长径 timeline_narrative imaging" \
            "发票金额 open_fields_filing admin" \
            "不明字段 open_fields_filing unknown"; do
  set -- $spec
  [ "$(group_of "$LEDGER" "$1")" = "$2" ] \
    && ok "clinical_class=$3 → group $2" \
    || no "clinical_class=$3 landed in $(group_of "$LEDGER" "$1"), expected $2"
done

# the one case where kind beats class: a novel page is filed open regardless
[ "$(group_of "$LEDGER" "丰度")" = "open_fields_filing" ] \
  && ok "a doc_kind: novel:* page goes to open_fields_filing EVEN THOUGH its class is lab" \
  || no "a novel page was routed by clinical_class instead of by kind: $(group_of "$LEDGER" "丰度")"

# exactly four groups, always all four present — a 段 2 worker that reads an absent key
# and a worker that reads an empty list must not be different code paths
python3 - "$LEDGER" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
want = {"labs", "molecular_pathology", "timeline_narrative", "open_fields_filing"}
got = set(d["groups"])
assert got == want, f"groups {sorted(got)} != A22 groups {sorted(want)}"
for g in want:
    assert f"fields_{g}" in d["counts"], f"counts has no fields_{g}"
print("group keys OK")
PYEOF
[ $? -eq 0 ] && ok "the ledger carries exactly the four A22 groups, always all four" \
  || no "the group key set does not match A22"

# a labs worker must not be able to see a molecular page at all — that isolation IS the
# reason for the split, so it is asserted directly rather than inferred from the counts
python3 - "$LEDGER" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
labs_classes = {x["clinical_class"] for x in d["groups"]["labs"]}
assert labs_classes <= {"lab"}, f"the labs group can see {sorted(labs_classes)}"
mp = {x["clinical_class"] for x in d["groups"]["molecular_pathology"]}
assert mp <= {"molecular", "pathology"}, f"molecular_pathology can see {sorted(mp)}"
tn = {x["clinical_class"] for x in d["groups"]["timeline_narrative"]}
assert tn <= {"narrative", "imaging"}, f"timeline_narrative can see {sorted(tn)}"
print("isolation OK")
PYEOF
[ $? -eq 0 ] && ok "no group can see a clinical_class that is not its own (worker isolation)" \
  || no "a worker group carries a foreign clinical_class"

# provenance travels with every candidate, or gate_field_provenance has nothing to bind to
python3 - "$LEDGER" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
for g, rows in d["groups"].items():
    for x in rows:
        for k in ("source_id", "page", "label", "value", "open_ref"):
            assert k in x, f"{g}: candidate missing {k}: {x}"
        assert x["open_ref"]["source_id"] == x["source_id"]
        assert x["open_ref"]["page"] == x["page"]
        assert isinstance(x["open_ref"]["bbox"], list), x["open_ref"]
print("provenance OK")
PYEOF
[ $? -eq 0 ] && ok "every candidate carries source_id + page + open_ref bbox back to raw/" \
  || no "a candidate has no usable provenance"

# ===========================================================================
# C. WHICH copy it reads: masked by default, verbatim only on demand
# ===========================================================================
echo "=== C. masked surface is the default (A27) ==="

[ "$(python3 -c "
import json; print(json.load(open('$LEDGER'))['read_from'])")" = "ocr/ (masked)" ] \
  && ok "the default ledger records read_from = ocr/ (masked)" \
  || no "the default run did not read the masked surface"
[ "$(value_of "$LEDGER" "住院号")" = "[PII_MASKED]" ] \
  && ok "…and a shape-masked identifier arrives as [PII_MASKED], recorded as the fact it is" \
  || no "the masked ledger leaked a raw identifier: $(value_of "$LEDGER" "住院号")"
grep -q '12345678901234' "$LEDGER" \
  && no "the default ledger contains the unmasked 14-digit identifier" \
  || ok "…the 14-digit identifier appears NOWHERE in the default ledger"
[ "$(value_of "$LEDGER" "WBC")" = "3.21" ] \
  && ok "…while clinical values pass through verbatim (masking did not touch 3.21)" \
  || no "masking damaged a clinical value: $(value_of "$LEDGER" "WBC")"

cp "$LEDGER" "$tmp/masked.json"
python3 "$MERGE" "$P" --run-id r1 --from-transcript >"$tmp/merge_vb.log" 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "--from-transcript exits 0" || no "--from-transcript exited $rc"
[ "$(python3 -c "
import json; print(json.load(open('$LEDGER'))['read_from'])")" = "raw/transcript/" ] \
  && ok "--from-transcript records read_from = raw/transcript/ (the audit surface)" \
  || no "--from-transcript did not switch surfaces"
[ "$(value_of "$LEDGER" "住院号")" = "12345678901234" ] \
  && ok "…and the verbatim pages still carry the real identifier (the character record)" \
  || no "the verbatim ledger is masked too — the audit trail is gone"
[ "$(group_of "$LEDGER" "丰度")" = "open_fields_filing" ] \
  && ok "…with the SAME grouping (the surface changes, the routing does not)" \
  || no "--from-transcript regrouped the candidates"
cp "$tmp/masked.json" "$LEDGER"   # leave the archive on the masked ledger

# ===========================================================================
# D. NEGATIVE — a manifest it cannot trust is a refusal, not an empty ledger
# ===========================================================================
echo "=== D. refusals ==="

python3 "$MERGE" "$P" --run-id r-nonexistent >"$tmp/d1.log" 2>&1
[ $? -ne 0 ] && ok "a run with no transcribe-manifest.json → non-zero exit" \
  || no "a missing manifest produced a successful empty ledger"
grep -q 'no transcribe-manifest.json' "$tmp/d1.log" \
  && ok "…and says which run has no manifest" || no "reason not stated: $(cat "$tmp/d1.log")"

mkdir -p "$P/raw/_provenance/rbad"
printf '{not json' > "$P/raw/_provenance/rbad/transcribe-manifest.json"
python3 "$MERGE" "$P" --run-id rbad >"$tmp/d2.log" 2>&1
[ $? -ne 0 ] && ok "an unparseable manifest → non-zero exit" \
  || no "a corrupt manifest was read as an empty run"
grep -q 'unreadable manifest' "$tmp/d2.log" \
  && ok "…and names it as unreadable rather than reporting zero pages" \
  || no "corrupt manifest not reported: $(cat "$tmp/d2.log")"
[ ! -f "$P/raw/_provenance/rbad/field_candidates.json" ] \
  && ok "…and no ledger is written for a run whose manifest could not be read" \
  || no "a ledger was written from an unreadable manifest"

# a manifest row pointing at a page that is not there: reported, never guessed at by
# searching the archive for a file with the right name (that is how one source's page
# gets read as another's)
MISSING="$tmp/patient_missing"
cp -R "$P" "$MISSING"
rm -f "$MISSING/ocr/s001/page-001.md"
python3 "$MERGE" "$MISSING" --run-id r1 >"$tmp/d3.log" 2>&1
[ $? -ne 0 ] && ok "a manifest row whose masked page is gone → non-zero exit" \
  || no "a missing page copy was silently dropped"
grep -q 'page copy not found' "$tmp/d3.log" \
  && ok "…and the ledger's problems[] names the page it could not read" \
  || no "missing page not reported: $(cat "$tmp/d3.log")"

# a page 段 1 rejected must not contribute candidates: it was never validly transcribed
SKIP="$tmp/patient_invalid"
cp -R "$P" "$SKIP"
python3 - "$SKIP/raw/_provenance/r1/transcribe-manifest.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
for rec in d["pages"]:
    if rec.get("page") == 2:
        rec["status"] = "invalid"
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
python3 "$MERGE" "$SKIP" --run-id r1 >/dev/null 2>&1
[ "$(group_of "$SKIP/raw/_provenance/r1/field_candidates.json" "EGFR")" = "ABSENT" ] \
  && ok "a page whose manifest status is not 'ok' contributes no candidates" \
  || no "an invalid page's fields reached the ledger"

python3 "$MERGE" "$P" --run-id '../escape' >/dev/null 2>&1
[ $? -eq 2 ] && ok "a path-traversing --run-id → exit 2 (run ids are path components)" \
  || no "'../escape' was accepted as a run id"
python3 "$MERGE" "$tmp/does-not-exist" --run-id r1 >/dev/null 2>&1
[ $? -eq 2 ] && ok "a patient_dir that is not a directory → exit 2" \
  || no "a missing patient_dir did not exit 2"

# ===========================================================================
# E. the grouping table is the script's, not a copy in this test
# ===========================================================================
echo "=== E. no drift between the test and CLASS_GROUPS ==="

python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
m = importlib.import_module("merge_fields")
want = {
    "lab": "labs",
    "molecular": "molecular_pathology", "pathology": "molecular_pathology",
    "narrative": "timeline_narrative", "imaging": "timeline_narrative",
    "admin": "open_fields_filing", "unknown": "open_fields_filing",
}
assert m.CLASS_GROUPS == want, f"CLASS_GROUPS drifted: {m.CLASS_GROUPS}"
# kind beats class, for every class
for cc in want:
    assert m.group_for(cc, "novel") == "open_fields_filing", cc
# an unseen class falls open rather than being dropped on the floor
assert m.group_for("a_class_that_does_not_exist") == "open_fields_filing"
print("CLASS_GROUPS OK")
PYEOF
[ $? -eq 0 ] && ok "merge_fields.CLASS_GROUPS is exactly the A22 table, and novel overrides it" \
  || no "CLASS_GROUPS does not match fix spec A22"

# ---------------------------------------------------------------------------
echo
echo "== merge-fields: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
