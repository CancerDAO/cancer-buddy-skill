#!/usr/bin/env bash
# tests/unit/readings-channel.test.sh — organize v3 fix spec B2.
#
# `high_risk_fields[].readings[]` is the only place in the archive where the SAME value
# read by two different channels sits side by side, and `channel` is the word that says
# which read is which. Everything downstream keys off that word: the validator derives
# the row-level `high_risk_review_status` from it, `--apply-second-read` looks up the
# first read by `channel == "transcribe"` before it will call anything verified, and a
# human reviewing a disagreement decides what to trust by reading the channel names.
#
# So the vocabulary has to be CLOSED, and it has to be closed in the same words in all
# three places that touch it:
#
#   references/schemas/source_inventory.schema.json  (the reader that rejects)
#   scripts/ingest_transcripts.py                    (the only writer)
#   references/high-risk-fields.md §2.4              (what a human/model is told)
#
# Two failures this file exists to prevent, both of which were real:
#
#   `first_read` — the collector wrote the 段 1 reading under that name while the schema
#   only ever knew `transcribe`. A channel name nothing matches is a channel nothing
#   checks: `apply_second_read` looking for `transcribe` found no first reading, compared
#   the second read against the empty string, and every second read "disagreed" — or,
#   flipped the other way by a later edit, a field with NO first reading at all would
#   have looked like a clean single-channel record. The name is gone; writing it must be
#   a schema violation, not a stylistic difference.
#
#   `none` — `none` is a fact about the ENVIRONMENT ("no second channel was reachable")
#   and it lives on `reread_channel`. It is not a reading, because there is no value that
#   somebody read through no channel. An entry `{"channel": "none", "value": ""}` is an
#   assertion that a second read happened and returned nothing, which reads to every
#   consumer — and to a human counting readings — as one more channel than actually ran.
#   That is precisely the claim the whole second-read contract exists to make impossible.
#
# Both arms are asserted here, and the positive arm runs the REAL collector on REAL
# synthesized pages rather than on a hand-written manifest: a gate that only ever sees
# fixtures the test author typed proves the schema is self-consistent and proves nothing
# about what the script actually writes. The drift arm compares the three declarations
# token for token, because "they agree" is a property of today's files, not of the repo.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SCRIPTS="$ORG/scripts"
SCHEMA="$ORG/references/schemas/source_inventory.schema.json"
HRDOC="$ORG/references/high-risk-fields.md"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

if ! python3 -c "import fitz, PIL" >/dev/null 2>&1; then
  echo "SKIP: readings-channel needs PyMuPDF + Pillow to synthesize the page fixtures" >&2
  exit 0
fi
if ! python3 -c "import jsonschema" >/dev/null 2>&1; then
  echo "SKIP: readings-channel needs jsonschema to check source_inventory.schema.json" >&2
  exit 0
fi

# schema_check <inventory.json> — validate against source_inventory.schema.json,
# printing every error message (the negative arms grep these).
schema_check() {
  out="$(python3 - "$SCHEMA" "$1" <<'PYEOF' 2>&1
import json, sys
import jsonschema
schema = json.load(open(sys.argv[1], encoding="utf-8"))
doc = json.load(open(sys.argv[2], encoding="utf-8"))
v = jsonschema.Draft202012Validator(schema)
errs = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
for e in errs:
    print(f"/{'/'.join(str(p) for p in e.path)}: {e.message}")
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
}

P="$tmp/patient"
mkdir -p "$P/raw/incoming"

# ===========================================================================
# A. the REAL collector: what ingest_transcripts.py actually writes
# ===========================================================================
echo "=== A. ingest_transcripts writes channel=transcribe for the first read ==="

python3 - "$P/raw/incoming" <<'PYEOF'
import sys, fitz
from PIL import Image, ImageDraw
d = sys.argv[1]
# born-digital: real embedded glyphs
doc = fitz.open()
pg = doc.new_page(width=595, height=842)
pg.insert_text((72, 100), "BLOOD COUNT REPORT", fontsize=14)
pg.insert_text((72, 130), "WBC 3.21 10^9/L  ref 3.50-9.50", fontsize=11)
pg.insert_text((72, 160), "Report date 2026-03-15", fontsize=11)
doc.save(f"{d}/born-digital.pdf"); doc.close()
# a phone photo of a page: pixels only
im = Image.new("L", (800, 1100), 255)
dr = ImageDraw.Draw(im)
dr.rectangle([100, 300, 700, 340], fill=40)
dr.rectangle([100, 500, 500, 540], fill=40)
im.save(f"{d}/photo.png")
PYEOF

python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r1 --model-id test-model \
  --source s001=raw/incoming/born-digital.pdf \
  --source s002=raw/incoming/photo.png >"$tmp/prep.log" 2>&1
[ $? -eq 0 ] && ok "prepare_pages (段 0) exits 0 on the synthesized 2-source vault" \
  || no "prepare_pages failed: $(cat "$tmp/prep.log")"

OUTD="$tmp/model_out"; mkdir -p "$OUTD"
cat > "$OUTD/s001.page-001.md" <<'EOF'
---
source_id: s001
page: 1
text_layer_kind: born_digital
doc_kind: 检验报告
clinical_class: lab
fields: [{"label": "白细胞计数", "value": "3.21", "unit": "10^9/L", "span": {"page": 1, "bbox": [0.12, 0.14, 0.38, 0.17]}}, {"label": "报告日期", "value": "2026-03-15", "span": {"page": 1, "bbox": [0.12, 0.18, 0.40, 0.21]}}]
high_risk: ["白细胞计数", "报告日期"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.0
needs_rotation: false
prompt_version: "3.1"
model_id: "test-model"
---
# 全文

BLOOD COUNT REPORT
白细胞计数 3.21 10^9/L 参考 3.50-9.50
报告日期 2026-03-15
EOF
cat > "$OUTD/s002.page-001.md" <<'EOF'
---
source_id: s002
page: 1
text_layer_kind: absent
doc_kind: 检验报告
clinical_class: lab
fields: [{"label": "癌胚抗原", "value": "25.3", "unit": "ng/mL", "span": {"page": 1, "bbox": [0.16, 0.46, 0.66, 0.51]}}]
high_risk: ["癌胚抗原"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.05
needs_rotation: false
prompt_version: "3.1"
model_id: "test-model"
---
# 全文

癌胚抗原 25.3 ng/mL
EOF

python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r1 --from "$OUTD" \
  --model-id test-model >"$tmp/ingest.log" 2>&1
rc=$?
[ "$rc" -eq 0 ] && ok "ingest_transcripts (段 1) exits 0 on two valid pages" \
  || no "ingest_transcripts exited $rc: $(cat "$tmp/ingest.log")"

MAN="$P/raw/_provenance/r1/transcribe-manifest.json"
out="$(python3 - "$ORG" "$MAN" <<'PYEOF' 2>&1
import importlib, json, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
it = importlib.import_module("ingest_transcripts")
m = json.load(open(sys.argv[2], encoding="utf-8"))
pages = [p for p in m["pages"] if p.get("status") == "ok"]
assert len(pages) == 2, f"expected 2 ok pages, got {len(pages)}"
seen = 0
for p in pages:
    hrf = p.get("high_risk_fields") or []
    assert hrf, f"{p['source_id']} carries high_risk labels but no high_risk_fields[]"
    for e in hrf:
        rds = e.get("readings") or []
        assert len(rds) == 1, (
            f"{p['source_id']} {e['label']!r}: the collector wrote {len(rds)} readings "
            f"before 段 1.5 ran — a second read that did not happen is already recorded")
        assert rds[0]["channel"] == "transcribe", (
            f"{p['source_id']} {e['label']!r}: first reading channel is "
            f"{rds[0]['channel']!r}, expected 'transcribe'")
        assert e["reread_channel"] == "none", e
        assert e["status"] == "needs_human_review", e
        seen += 1
assert seen == 3, f"expected 3 high-risk fields across the two pages, got {seen}"
# the constant the writer actually uses, not a coincidence of this fixture
assert it.FIRST_READ_CHANNEL == "transcribe", it.FIRST_READ_CHANNEL
raw = json.dumps(m, ensure_ascii=False)
assert "first_read" not in raw, "the manifest still carries the retired first_read spelling"
print("collector output OK")
PYEOF
)"
[ $? -eq 0 ] && ok "every readings[].channel the collector wrote is 'transcribe' (one reading, reread_channel none)" \
  || no "collector output is wrong: $out"

# The manifest's high_risk_fields[] arrays ARE the inventory row's high_risk_fields[] —
# so lift them verbatim rather than retyping them. A fixture the test author typed by
# hand can agree with the schema while the script disagrees with both.
build_inv() {  # <out.json> [python mutation of `files`]
  python3 - "$MAN" "$1" "${2:-}" <<'PYEOF'
import json, sys
man = json.load(open(sys.argv[1], encoding="utf-8"))
files = []
for i, p in enumerate(x for x in man["pages"] if x.get("status") == "ok"):
    hrf = p["high_risk_fields"]
    files.append({
        "file_id": f"f{i+1:03d}",
        "source_id": p["source_id"],
        "original_path": f"{p['source_id']}.pdf",
        "raw_path": f"raw/incoming/{p['source_id']}.pdf",
        "page_range": None,
        "kind": "known",
        "doc_kind": p["doc_kind"],
        "clinical_class": p["clinical_class"],
        "text_layer_kind": p["text_layer_kind"],
        "sidecar_path": f"07_检验/血常规/{p['source_id']}.md",
        "bucket_path": "07_检验/血常规",
        "modality": "image",
        "read_mode": "model_vision_primary",
        "transcript_path": p["transcript_path"],
        "extractor_provenance": {"engine": "host_vision", "version": "1",
                                 "raw_output_ref": p["transcript_path"],
                                 "llm_role": "primary_transcription"},
        "transcribe_model_id": p["transcribe_model_id"],
        "high_risk_fields": hrf,
        "high_risk_review_status": "needs_human_review",
        "reread_channel": "none",
        "adapter": "pdf_pages",
        "persist": True,
    })
doc = {"schema": "source_inventory_v2", "scheme_version": 4, "patient_dir": ".",
       "generated_at": "2026-09-17T00:00:00Z", "files": files}
mut = sys.argv[3]
if mut:
    exec(mut, {"doc": doc, "files": files})
json.dump(doc, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF
}

build_inv "$tmp/inv_ok.json"
schema_check "$tmp/inv_ok.json"
[ "$rc" -eq 0 ] \
  && ok "the collector's own high_risk_fields[] validate against source_inventory.schema.json → exit 0" \
  || no "the REAL collector output is rejected by the schema: $out"

# ===========================================================================
# B. negative arm — the two names that must not validate
# ===========================================================================
echo "=== B. first_read / none are schema violations ==="

build_inv "$tmp/inv_first_read.json" \
  'files[0]["high_risk_fields"][0]["readings"][0]["channel"] = "first_read"'
schema_check "$tmp/inv_first_read.json"
[ "$rc" -ne 0 ] && ok "channel 'first_read' is REJECTED (the retired spelling is not tolerated)" \
  || no "the schema accepted the retired channel name 'first_read'"
grep -q "first_read" <<<"$out" \
  && ok "…and the error names the offending value verbatim" \
  || no "the rejection does not name 'first_read': $out"
grep -q "'transcribe'" <<<"$out" && grep -q "'human'" <<<"$out" \
  && ok "…and prints the closed enum, so the fix is readable off the error" \
  || no "the rejection does not show the enum: $out"

build_inv "$tmp/inv_none.json" \
  'files[0]["high_risk_fields"][0]["readings"][0]["channel"] = "none"'
schema_check "$tmp/inv_none.json"
[ "$rc" -ne 0 ] && ok "channel 'none' is REJECTED (no value is read through no channel)" \
  || no "the schema accepted channel 'none' on a reading"
grep -q "'none' is not one of" <<<"$out" \
  && ok "…and says so as 'none' is not one of […]" \
  || no "the 'none' rejection is not the enum error: $out"

# `none` must stay LEGAL where it belongs — a negative arm that also banned it from
# reread_channel would be testing "the word none is forbidden", which is not the rule.
build_inv "$tmp/inv_reread_none.json" \
  'files[0]["high_risk_fields"][0]["reread_channel"] = "none"'
schema_check "$tmp/inv_reread_none.json"
[ "$rc" -eq 0 ] \
  && ok "…while reread_channel: none stays legal (it describes the environment, not a read)" \
  || no "reread_channel: none was rejected — the rule was over-applied: $out"

# ===========================================================================
# C. --apply-second-read refuses `none` as a second-read channel
# ===========================================================================
echo "=== C. apply_second_read rejects channel none ==="

cat > "$tmp/sr_none.json" <<'EOF'
{"results": [
  {"source_id": "s002", "page": 1, "label": "癌胚抗原", "channel": "none",
   "model_id": "other-model", "value": "25.3", "agree": true}
]}
EOF
python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r1 \
  --apply-second-read "$tmp/sr_none.json" >"$tmp/sr_none.log" 2>&1
rc=$?
[ "$rc" -eq 1 ] && ok "--apply-second-read with channel 'none' → exit 1 (not folded in silently)" \
  || no "a 'none'-channel second read was accepted, rc=$rc: $(cat "$tmp/sr_none.log")"
grep -q "is not a second-read channel" "$tmp/sr_none.log" \
  && ok "…and the message says 'none' is not a second-read channel" \
  || no "rejection text missing: $(cat "$tmp/sr_none.log")"
grep -q "belongs on reread_channel" "$tmp/sr_none.log" \
  && ok "…and redirects it to reread_channel (the ENVIRONMENT, not a reading)" \
  || no "the message does not redirect 'none' to reread_channel: $(cat "$tmp/sr_none.log")"
python3 - "$MAN" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
for p in m["pages"]:
    for e in p.get("high_risk_fields") or []:
        chans = [r["channel"] for r in e.get("readings") or []]
        assert chans == ["transcribe"], (p["source_id"], e["label"], chans)
        assert e["status"] != "passed_independent_reread", e
assert m["counts"].get("second_read_rejected_channel") == 1, m["counts"]
print("no phantom reading landed")
PYEOF
[ $? -eq 0 ] \
  && ok "…and NO reading was appended: the rejected result left the field unverified" \
  || no "a rejected second read still mutated readings[] or the status"

# positive control: the same payload on a real channel DOES fold in, so the rejection
# above is about the channel name and not about the harness being broken.
cat > "$tmp/sr_ok.json" <<'EOF'
{"results": [
  {"source_id": "s002", "page": 1, "label": "癌胚抗原", "channel": "alternate_vision_model",
   "model_id": "other-model", "value": "25.3", "agree": true}
]}
EOF
python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r1 \
  --apply-second-read "$tmp/sr_ok.json" >"$tmp/sr_ok.log" 2>&1
rc=$?
[ "$rc" -eq 0 ] && ok "the SAME payload on channel alternate_vision_model is applied → exit 0" \
  || no "a legal second read was refused, rc=$rc: $(cat "$tmp/sr_ok.log")"
python3 - "$MAN" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
e = next(e for p in m["pages"] if p.get("source_id") == "s002"
         for e in p["high_risk_fields"] if e["label"] == "癌胚抗原")
assert [r["channel"] for r in e["readings"]] == ["transcribe", "alternate_vision_model"], e
assert e["status"] == "passed_independent_reread", e
assert e["reread_channel"] == "alternate_vision_model", e
print("second reading landed with its channel name")
PYEOF
[ $? -eq 0 ] \
  && ok "…appending a SECOND reading whose channel names the channel that produced it" \
  || no "the accepted second read was not recorded as its own reading"

# ===========================================================================
# D. no drift — schema, script and reference doc declare the SAME six words
# ===========================================================================
echo "=== D. three declarations, one vocabulary ==="

# NOTE: this script is written to a file rather than piped through `python3 - <<EOF`
# inside a command substitution. It has to quote backticks (the reference doc writes its
# channel list in markdown code spans), and bash re-scans a heredoc nested inside `$(…)`
# for backquote substitution even when the delimiter is quoted — which would silently
# delete the very strings this check greps for and turn the drift gate green by accident.
cat > "$tmp/drift.py" <<'PYEOF'
import importlib, json, re, sys, pathlib
ORG, SCHEMA, HRDOC = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, ORG + "/scripts")
it = importlib.import_module("ingest_transcripts")

schema = json.load(open(SCHEMA, encoding="utf-8"))
hrf = schema["properties"]["files"]["items"]["properties"]["high_risk_fields"]
enum = hrf["items"]["properties"]["readings"]["items"]["properties"]["channel"]["enum"]

script = list(it.READING_CHANNELS)
assert script == enum, f"script READING_CHANNELS {script} != schema enum {enum}"
assert it.FIRST_READ_CHANNEL == enum[0] == "transcribe", (it.FIRST_READ_CHANNEL, enum[0])
assert list(it.REREAD_CHANNELS) == enum[1:], (it.REREAD_CHANNELS, enum[1:])
assert "none" not in enum and "first_read" not in enum, enum

# references/high-risk-fields.md §2.4 — the closed list a human/model is handed.
doc = pathlib.Path(HRDOC).read_text(encoding="utf-8")
lines = doc.splitlines()
i = next(n for n, l in enumerate(lines) if "`readings[].channel`" in l and "闭合取值" in l)
para = "\n".join(lines[i:i + 6])
toks, seen = [], set()
for t in re.findall(r"`([a-z_]+)`", para):
    if t not in seen:
        seen.add(t); toks.append(t)
assert toks[:6] == enum, f"high-risk-fields.md lists {toks[:6]}, schema enum is {enum}"
# and it must retire the old name EXPLICITLY, not merely omit it: a reader who has
# seen `first_read` in an old archive needs to be told which spelling won.
assert "没有 `first_read`" in para, "the doc does not explicitly retire `first_read`"
assert "`none`" in para and "第二通道" in para, "the doc does not explain why `none` is absent"
# The worked example in §2.4 is what gets copied, so check IT, not the whole file:
# the prose above deliberately quotes `channel: none` in order to forbid it, and a
# naive file-wide grep would read that prohibition as the violation it warns about.
block = re.search(r"```yaml\n(.*?)```", doc, re.S)
assert block, "§2.4 no longer carries a yaml example of high_risk_fields[]"
ex = block.group(1)
assert "{channel: transcribe," in ex, "the §2.4 example does not use channel: transcribe"
for retired in ("channel: first_read", "channel: none"):
    assert retired not in ex, f"the §2.4 example still shows `{retired}`"
for ch in re.findall(r"\{channel:\s*([a-z_]+)", ex):
    assert ch in enum, f"the §2.4 example uses channel {ch!r}, outside the enum {enum}"
print("three-way agreement OK:", enum)
PYEOF
out="$(python3 "$tmp/drift.py" "$ORG" "$SCHEMA" "$HRDOC" 2>&1)"
[ $? -eq 0 ] && ok "schema enum == ingest_transcripts.READING_CHANNELS == high-risk-fields.md §2.4, in order" \
  || no "the three declarations of readings[].channel have drifted: $out"

echo
echo "== readings-channel: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
