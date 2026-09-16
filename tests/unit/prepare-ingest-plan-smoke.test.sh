#!/usr/bin/env bash
# tests/unit/prepare-ingest-plan-smoke.test.sh — organize v3 段 0 → 段 1 → 段 1.5 → 忠实度.
#
# An end-to-end smoke test over the four deterministic scripts that surround the one
# model call, run on SYNTHETIC pages generated here (no patient data, no network, no
# LLM):
#
#   prepare_pages.py       renders pages, probes the text layer, decides
#                          text_layer_kind, checks the content-addressed cache
#   ingest_transcripts.py  validates the model's per-page output, writes the verbatim
#                          copy under raw/transcript/ and the masked copy under ocr/,
#                          writes the cache, flags the pages that need an agent
#   plan_second_read.py    settles what a born-digital text layer already settled for
#                          free, batches the rest by page with a channel preference
#   verify_native_text.py  byte identity (modulo masked spans) for a native_text source
#
# The fixtures are chosen to exercise the ONE decision everything downstream keys off:
#   (a) a born-digital PDF   → text_layer_kind born_digital (its text layer IS truth,
#                              and it is an independent CHANNEL, so a high-risk field
#                              found verbatim there costs no second read at all)
#   (b) a pure-image PDF     → absent (pixels are truth; every high-risk field owes a
#                              channel-independent second read)
#   (c) a phone photo (png)  → absent
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SCRIPTS="$ORG/scripts"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

if ! python3 -c "import fitz, PIL" >/dev/null 2>&1; then
  echo "SKIP: prepare-ingest-plan-smoke needs PyMuPDF + Pillow to synthesize page fixtures" >&2
  exit 0
fi

P="$tmp/patient"
mkdir -p "$P/raw/incoming" "$P/07_检验/血常规"

# ---------------------------------------------------------------- fixtures ----
python3 - "$P/raw/incoming" <<'PYEOF'
import sys, fitz
from PIL import Image, ImageDraw
d = sys.argv[1]

# (a) born-digital: real embedded glyphs from the producing application
doc = fitz.open()
page = doc.new_page(width=595, height=842)
page.insert_text((72, 100), "BLOOD COUNT REPORT", fontsize=14)
page.insert_text((72, 130), "WBC 3.21 10^9/L  ref 3.50-9.50", fontsize=11)
page.insert_text((72, 160), "Report date 2026-03-15", fontsize=11)
doc.save(f"{d}/born-digital.pdf"); doc.close()

# (b) a picture of a page: one full-page raster, NO text layer
img = fitz.open()
pg = img.new_page(width=595, height=842)
pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 600, 850))
pix.set_rect(pix.irect, (255,))
for y in range(400, 430):
    for x in range(100, 400):
        pix.set_pixel(x, y, (30,))
pg.insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)
img.save(f"{d}/scan-photo.pdf"); img.close()

# (c) a phone photo
im = Image.new("L", (800, 1100), 255)
dr = ImageDraw.Draw(im)
dr.rectangle([100, 300, 700, 340], fill=40)
dr.rectangle([100, 500, 500, 540], fill=40)
im.save(f"{d}/photo.png")
PYEOF

SRC=(--source s001=raw/incoming/born-digital.pdf
     --source s002=raw/incoming/scan-photo.pdf
     --source s003=raw/incoming/photo.png)

# ===========================================================================
# A. prepare_pages — text_layer_kind is decided by the script, not by a model
# ===========================================================================
echo "=== A. prepare_pages (段 0) ==="

set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r1 --model-id test-model "${SRC[@]}" >"$tmp/prep1.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "prepare_pages exits 0 on a clean 3-source vault" \
  || no "prepare_pages exited $rc: $(cat "$tmp/prep1.log")"

MAN="$P/raw/_provenance/r1/pages.json"
[ -f "$MAN" ] && ok "pages.json manifest written under raw/_provenance/<run_id>/" \
  || no "pages.json not written"

kind_of() { python3 -c "
import json,sys
m=json.load(open(sys.argv[1]))
print(next(p['text_layer_kind'] for p in m['pages'] if p['source_id']==sys.argv[2]))" "$MAN" "$1"; }

[ "$(kind_of s001)" = "born_digital" ] \
  && ok "born-digital PDF → text_layer_kind=born_digital" \
  || no "born-digital PDF classified as $(kind_of s001)"
[ "$(kind_of s002)" = "absent" ] \
  && ok "pure-image PDF → text_layer_kind=absent (pixels are the truth)" \
  || no "image-only PDF classified as $(kind_of s002)"
[ "$(kind_of s003)" = "absent" ] \
  && ok "phone photo → text_layer_kind=absent" || no "photo classified as $(kind_of s003)"

set +e
python3 - "$MAN" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1]))
# fix spec A1: the prompt dropped prev_page_tail, so the prompt version moved to 3.1 and
# the cache key must carry it — an old 3.0 entry is a reading of a DIFFERENT question.
assert m["prompt_version"] == "3.1", f"cache key carries prompt_version {m['prompt_version']!r}"
assert m["counts"]["cache_hits"] == 0, "a first run must not report cache hits"
recipe = m["cache_key_recipe"]
assert "text_layer" in recipe, recipe          # a changed text layer is a different page
assert "prompt_version" in recipe and "model_id" in recipe, recipe
assert "prev" not in recipe and "tail" not in recipe, (
    f"the cache recipe still mentions a previous-page tail: {recipe}")
for p in m["pages"]:
    assert p["image_path"].startswith("raw/adapter_views/"), p["image_path"]
    assert not p["image_path"].startswith("/"), "manifest must not carry a host-absolute path"
    assert len(p["image_sha256"]) == 64
    # fix spec A28: the row names the per-page packet the model is handed
    assert p["packet_path"].startswith("raw/_provenance/r1/packets/"), p["packet_path"]
    assert p["prompt_version"] == "3.1" and p["model_id"] == "test-model", p
print("manifest shape OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "manifest paths are patient_dir-relative and carry the page sha256 + prompt_version + packet_path" \
             || no "manifest shape is wrong"

# fix spec A1 — the段 1 call is STATELESS. The packet is the whole input, and it must
# carry exactly {image, text_layer, text_layer_kind, page_index, page_total, source_id}
# plus cache/provenance bookkeeping — and NO tail of the previous page. Statelessness is
# both the anti-anchoring property (page N+1 cannot be contaminated by page N's reading)
# and what makes the cache content-addressable at all.
set +e
python3 - "$P/raw/_provenance/r1/packets/s001.page-001.json" <<'PYEOF'
import json, sys
pk = json.load(open(sys.argv[1]))
for k in ("source_id", "page_index", "page_total", "image_path", "text_layer", "text_layer_kind"):
    assert k in pk, f"packet is missing {k}"
for banned in ("prev_page_tail", "previous_page", "prev_tail", "context", "history"):
    assert banned not in pk, f"packet carries cross-page state: {banned}"
assert not pk["image_path"].startswith("/"), pk["image_path"]
print("packet shape OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "the per-page packet is stateless: no prev_page_tail, no cross-page context (A1)" \
             || no "the 段 1 packet carries cross-page state"

# ===========================================================================
# B. ingest_transcripts — validation is the point
# ===========================================================================
echo "=== B. ingest_transcripts (段 1) ==="

OUTD="$tmp/model_out"; mkdir -p "$OUTD"

# three legal pages …
cat > "$OUTD/s001.page-001.md" <<'EOF'
---
source_id: s001
page: 1
text_layer_kind: born_digital
doc_kind: 检验报告
clinical_class: lab
fields: [{"label": "WBC", "value": "3.21", "unit": "10^9/L", "span": {"page": 1, "bbox": [0.12, 0.14, 0.38, 0.17]}}, {"label": "报告日期", "value": "2026-03-15", "span": {"page": 1, "bbox": [0.12, 0.18, 0.40, 0.21]}}]
high_risk: ["WBC", "报告日期"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.0
needs_rotation: false
prompt_version: "3.1"
model_id: "test-model"
---
# 全文

BLOOD COUNT REPORT

| 项目 | 结果 | 参考 |
| WBC | 3.21 10^9/L | 3.50-9.50 |

Report date 2026-03-15
联系电话 13800138000
EOF

cat > "$OUTD/s002.page-001.md" <<'EOF'
---
source_id: s002
page: 1
text_layer_kind: absent
doc_kind: 检验报告
clinical_class: lab
fields: [{"label": "CEA", "value": "25.3", "unit": "ng/mL", "span": {"page": 1, "bbox": [0.16, 0.46, 0.66, 0.51]}}, {"label": "住院号", "value": "0012345", "span": {"page": 1, "bbox": [0.16, 0.58, 0.60, 0.63]}}]
high_risk: ["CEA", "住院号"]
uncertain: ["参考范围下限"]
discrepancy: []
unreadable_ratio: 0.45
needs_rotation: false
prompt_version: "3.1"
model_id: "test-model"
---
# 全文

[不可读] 表头

CEA 25.3 ng/mL
住院号 0012345
EOF

cat > "$OUTD/s003.page-001.md" <<'EOF'
---
source_id: s003
page: 1
text_layer_kind: absent
doc_kind: 出院小结
clinical_class: narrative
fields: [{"label": "出院日期", "value": "2026-03-20", "span": {"page": 1, "bbox": [0.10, 0.25, 0.45, 0.30]}}]
high_risk: ["出院日期"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.05
needs_rotation: false
prompt_version: "3.1"
model_id: "test-model"
---
# 全文

出院日期 2026-03-20
EOF

# … and one whose bbox leaves the normalized page. Pixel coordinates in a span look
# perfectly plausible and silently become wrong the next time the page is rendered at
# a different DPI, so this is a hard reject, not a warning.
cat > "$OUTD/s003.page-002.md" <<'EOF'
---
source_id: s003
page: 2
text_layer_kind: absent
doc_kind: 出院小结
clinical_class: narrative
fields: [{"label": "随访日期", "value": "2026-04-20", "span": {"page": 2, "bbox": [0.10, 0.25, 1.40, 0.30]}}]
high_risk: ["随访日期"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.05
needs_rotation: false
prompt_version: "3.1"
model_id: "test-model"
---
# 全文

随访日期 2026-04-20
EOF

set +e
python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r1 --from "$OUTD" --model-id test-model \
  >"$tmp/ingest.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && ok "one invalid page → ingest exits 1 (it is not a warning)" \
  || no "invalid page did not fail the run, rc=$rc"
grep -q 'bbox\[2\]=1.4 is outside 0-1' "$tmp/ingest.log" \
  && ok "…and the out-of-range bbox is named with its index and value" \
  || no "bbox violation not reported: $(cat "$tmp/ingest.log")"
grep -q 'NORMALIZED' "$tmp/ingest.log" \
  && ok "…with the reason (coordinates are normalized so they survive a DPI change)" \
  || no "normalization rationale absent"

# both copies land, for every VALID page only
for sid in s001 s002 s003; do
  [ -f "$P/raw/transcript/$sid/page-001.md" ] \
    && ok "verbatim copy written: raw/transcript/$sid/page-001.md" \
    || no "verbatim copy missing for $sid"
  [ -f "$P/ocr/$sid/page-001.md" ] \
    && ok "masked staging copy written: ocr/$sid/page-001.md" \
    || no "masked copy missing for $sid"
done
[ ! -f "$P/raw/transcript/s003/page-002.md" ] && [ ! -f "$P/ocr/s003/page-002.md" ] \
  && ok "the INVALID page was not half-written (no verbatim, no masked copy)" \
  || no "an invalid page was written anyway"

# the masking floor actually ran on the derived copy, and only on it
grep -q '13800138000' "$P/raw/transcript/s001/page-001.md" \
  && ok "the verbatim copy keeps the phone number (it is the character record)" \
  || no "the verbatim copy was masked — the audit trail is gone"
grep -q '13800138000' "$P/ocr/s001/page-001.md" \
  && no "the masked copy still carries an unmasked phone number" \
  || ok "the masked copy has no unmasked phone number"
grep -q '\[PII_MASKED\]' "$P/ocr/s001/page-001.md" \
  && ok "…it was replaced with [PII_MASKED]" || no "no mask token in the masked copy"
grep -q '3.21' "$P/ocr/s001/page-001.md" \
  && ok "…and the clinical characters (3.21) are untouched by masking" \
  || no "masking damaged a clinical value"

TM="$P/raw/_provenance/r1/transcribe-manifest.json"
set +e
python3 - "$TM" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1]))
c = m["counts"]
assert c["pages_in"] == 4, c
assert c["pages_ok"] == 3, c
assert c["pages_invalid"] == 1, c
assert c["escalate_to_agent"] == 1, c
ok_pages = {p["source_id"]: p for p in m["pages"] if p["status"] == "ok"}
esc = ok_pages["s002"]
assert esc["escalate_to_agent"] is True, esc
assert "0.45" in str(esc["escalate_reason"]), esc["escalate_reason"]
assert esc["unreadable_ratio"] == 0.45
assert ok_pages["s003"]["escalate_to_agent"] is False
assert ok_pages["s001"]["transcript_path"] == "raw/transcript/s001/page-001.md"
assert ok_pages["s001"]["masked_path"] == "ocr/s001/page-001.md"
assert ok_pages["s001"]["clinical_class"] == "lab"
assert ok_pages["s001"]["high_risk_n"] == 2
print("manifest counts OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "transcribe-manifest counts: in=4 ok=3 invalid=1 escalate=1, paths + per-page fields recorded" \
             || no "transcribe-manifest counts/shape are wrong"
grep -q 'unreadable_ratio 0.45 > 0.3' "$TM" \
  && ok "escalate_to_agent fires at unreadable_ratio 0.45 and says why" \
  || no "escalation reason does not name the ratio and threshold"

# ===========================================================================
# C. the content-addressed cache — a second run pays for nothing
# ===========================================================================
echo "=== C. transcription cache ==="

ls "$P/raw/_cache/transcripts/"*.3.1.test-model.md >/dev/null 2>&1 \
  && ok "cache entries keyed sha256(page image).sha256(text layer).prompt_version.model_id" \
  || no "no cache entries written"

set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r2 --model-id test-model "${SRC[@]}" >"$tmp/prep2.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "second prepare_pages run exits 0" || no "second run exited $rc"
set +e
python3 - "$P/raw/_provenance/r2/pages.json" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1]))
assert m["counts"]["cache_hits"] == 3, m["counts"]
for p in m["pages"]:
    assert p["cache_hit"] is True, p["source_id"]
    assert p["cached_path"].startswith("raw/_cache/transcripts/"), p["cached_path"]
print("cache hits OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "re-running the same pages with the same prompt+model → 3/3 cache hits" \
             || no "cache did not hit on an identical second run"

# a different model id is a different key — a cache that ignored it would serve one
# model's reading as another's
set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r3 --model-id other-model "${SRC[@]}" >/dev/null 2>&1
set -e
set +e
python3 -c "
import json,sys
m=json.load(open('$P/raw/_provenance/r3/pages.json'))
assert m['counts']['cache_hits']==0, m['counts']
print('model-id keying OK')"
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "a different --model-id misses the cache (the key includes the model)" \
             || no "cache ignored model_id"

# ===========================================================================
# D. plan_second_read — born-digital is free, pixels are not
# ===========================================================================
echo "=== D. plan_second_read (段 1.5) ==="

set +e
python3 "$SCRIPTS/plan_second_read.py" "$P" --run-id r1 >"$tmp/plan.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "plan_second_read exits 0" || no "plan_second_read exited $rc: $(cat "$tmp/plan.log")"

PLAN="$P/raw/_provenance/r1/second-read-plan.json"
set +e
python3 - "$PLAN" <<'PYEOF'
import json, sys
pl = json.load(open(sys.argv[1]))
packets = {p["source_id"]: p for p in pl["packets"]}

# fix spec A23: there is exactly ONE way to write "this field was verified through a
# second channel" — high_risk_fields[].status = passed_independent_reread plus the
# reread_channel that did it. The earlier `settled` / `settled_via` spelling is banned
# outright, because two vocabularies for one claim is how a tie-break gets recorded as a
# verification: `settled` reads like a fact about the VALUE, `passed_independent_reread`
# reads like a fact about the PROCEDURE, and only the second one is checkable.
raw = json.dumps(pl, ensure_ascii=False)
for banned in ("settled_via", "settled_fact", '"settled"'):
    assert banned not in raw, f"the plan still uses the banned spelling {banned}"

passed = {(x["source_id"], x["label"]): x for x in pl["passed_independent_reread"]}

# the born-digital page owes NOTHING: both its high-risk values are present verbatim
# in the embedded text layer, which is a genuinely independent modality.
assert "s001" not in packets, "born-digital page should not need a packet"
for label in ("WBC", "报告日期"):
    x = passed[("s001", label)]
    assert x["status"] == "passed_independent_reread", x
    assert x["reread_channel"] == "text_layer", x
# the pixel pages DO owe a second read
assert "s002" in packets and "s003" in packets, sorted(packets)
print("settlement OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "born-digital fields recorded as passed_independent_reread + reread_channel=text_layer (A23), kept OUT of the plan" \
             || no "born-digital settlement is wrong"

# fix spec A10/A18 — the packet shape is the prompt's shape:
#   {source_id, page, image, channel, fields_to_verify:[{label, trigger, bbox}]}
set +e
python3 - "$PLAN" <<'PYEOF'
import json, sys
pl = json.load(open(sys.argv[1]))
p = {x["source_id"]: x for x in pl["packets"]}["s002"]
for k in ("source_id", "page", "image", "channel", "fields_to_verify"):
    assert k in p, f"second-read packet is missing {k}: {sorted(p)}"
assert not p["image"].startswith("/"), p["image"]
fv = {f["label"]: f for f in p["fields_to_verify"]}
assert set(fv) == {"CEA", "住院号", "参考范围下限"}, sorted(fv)
# every entry says WHY it is being re-read, and carries the crop (or an explicit null)
for label, f in fv.items():
    assert set(f) >= {"label", "trigger", "bbox"}, (label, sorted(f))
    assert f["trigger"], f"{label} entered the plan with no recorded trigger"
assert fv["CEA"]["trigger"] == ["high_risk"], fv["CEA"]
assert fv["参考范围下限"]["trigger"] == ["uncertain"], fv["参考范围下限"]
assert fv["参考范围下限"]["bbox"] is None, "a field with no span must carry bbox null, not a guess"
print("packet shape OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "packet = {source_id, page, image, channel, fields_to_verify:[{label,trigger,bbox}]} (A10)" \
             || no "second-read packet shape is wrong"
[ "$rc" -eq 0 ] && ok "pixel pages DO enter the plan (high_risk ∪ uncertain ∪ discrepancy)" \
             || no "pixel pages did not enter the plan"

set +e
python3 - "$PLAN" <<'PYEOF'
import json, sys
pl = json.load(open(sys.argv[1]))
p = {x["source_id"]: x for x in pl["packets"]}["s002"]
ch = p["channel_preference"]
assert "text_layer" not in ch, f"a text-layer-absent page must not be offered text_layer: {ch}"
assert ch[-1] == "human", f"human must always terminate the list: {ch}"
assert "alternate_vision_model" in ch, ch
assert not any("same" in c for c in ch), f"the same model on the same image is never a channel: {ch}"
assert "tie-break" in pl["independence_rule"]
print("independence OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "channel_preference: no text_layer for a pixel page, human last, same-model never offered" \
             || no "channel_preference violates the independence rule"

# fix spec A10 — `barcode` is no longer appended unconditionally. For a pixel page with
# no barcode field and no OCR appendix, the only channel the run can actually reach
# unaided is a different vision model, so that must come FIRST. Offering `barcode` to a
# page with no barcode is offering a channel that does not exist, and a preference list
# whose head is unreachable is how a run ends up doing nothing and calling it verified.
set +e
python3 - "$PLAN" <<'PYEOF'
import json, sys
pl = json.load(open(sys.argv[1]))
p = {x["source_id"]: x for x in pl["packets"]}["s002"]
ch = p["channel_preference"]
assert ch[0] == "alternate_vision_model", (
    f"pixel page channel_preference[0] is {ch[0]!r}, expected 'alternate_vision_model' "
    f"(full list: {ch})")
assert "barcode" not in ch, (
    f"barcode was offered to a page whose frontmatter has no barcode field: {ch}")
assert "deterministic_ocr" not in ch, (
    f"deterministic_ocr was offered with no OCR appendix on the page: {ch}")
print("channel order OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "pixel page prefers alternate_vision_model, and unreachable channels are not offered" \
             || no "channel_preference offers a channel the page cannot reach"

# --available-channels — the HOST declares what it can actually reach, and the planner
# must not invent one. Restricting the host to `human` alone has to (a) collapse every
# preference list to human and (b) UNSETTLE the born-digital page: if text_layer is not
# a channel this host can use, "free" verification was never free.
set +e
python3 "$SCRIPTS/plan_second_read.py" "$P" --run-id r1 --available-channels human \
  >"$tmp/plan_human.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "--available-channels human exits 0" || no "restricted-channel plan failed: $(cat "$tmp/plan_human.log")"
set +e
python3 - "$PLAN" <<'PYEOF'
import json, sys
pl = json.load(open(sys.argv[1]))
assert pl["available_channels"] == ["human"], pl["available_channels"]
assert pl["passed_independent_reread"] == [], (
    "the born-digital page was still settled via a channel this host cannot reach")
sids = {p["source_id"] for p in pl["packets"]}
assert sids == {"s001", "s002", "s003"}, sorted(sids)
for p in pl["packets"]:
    assert p["channel_preference"] == ["human"], p["channel_preference"]
    assert p["channel"] == "human", p["channel"]
print("available-channels OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "--available-channels restricts the plan and un-settles what the host cannot verify" \
             || no "--available-channels was ignored"
# restore the full-capability plan for the assertions that follow
python3 "$SCRIPTS/plan_second_read.py" "$P" --run-id r1 >/dev/null 2>&1

# fix spec A4 — the spot-check is TWO files, and the script writes only the first.
# `human_sample_plan.json` is the ASK (what a person must go and look at);
# `human_sample_result.json` is the ANSWER and is written by the human. Collapsing them
# into one file is how "we planned a spot-check" became indistinguishable from "a person
# did it", which is the single claim the whole procedure exists to make.
HS="$P/raw/_provenance/r1/human_sample_plan.json"
[ -f "$HS" ] && ok "human_sample_plan.json written (the ASK)" || no "human_sample_plan.json missing"
[ ! -f "$P/raw/_provenance/r1/human_sample_result.json" ] \
  && ok "…and human_sample_result.json is NOT written by the script (a person writes it)" \
  || no "the script fabricated the human's own result file"
[ ! -f "$P/raw/_provenance/r1/human_sample.json" ] \
  && [ ! -f "$P/raw/_provenance/r1/human-sample.json" ] \
  && ok "…the merged pre-A4 spellings are gone (no human_sample.json / human-sample.json)" \
  || no "a legacy merged human_sample file is still produced"
set +e
python3 - "$HS" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["sample_size"] >= 3, d
assert len(d["sample"]) == d["sample_size"]
assert d["high_risk_fields_total"] == 5, d
# the sample must be drawn from ALL high-risk fields, including the ones a channel
# already settled — otherwise it only ever audits the fields the pipeline found hard.
assert any(s["source_id"] == "s001" for s in d["sample"]) or d["sample_size"] < 5, d
for item in d["sample"]:
    assert set(item) >= {"source_id", "page", "label", "bbox", "transcript_value"}, sorted(item)
assert "raw/" in d["rule"], "the spot-check must send a human to the ORIGINAL"
assert "human_sample_result.json" in d["rule"], "the plan must say where the verdicts go"
assert "not deliverable" in d["rule"], "the plan must state the two-mismatch consequence"
print("human sample OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "the plan carries ≥3 entries with their crops + transcript values, and points the reviewer at raw/" \
             || no "human sample plan is wrong"

# fix spec A36 — the seed is sha256(patient_code + sorted field keys), NOT the run id.
# Keying on the run id would let a failed spot-check be re-rolled simply by starting a
# new run, which turns the audit into a lottery you can play until you win.
cp "$HS" "$tmp/hs1.json"
python3 "$SCRIPTS/plan_second_read.py" "$P" --run-id r1 >/dev/null 2>&1
cmp -s "$tmp/hs1.json" "$HS" \
  && ok "the sample is deterministic on a re-run (it cannot be re-rolled in place)" \
  || no "re-running the planner produced a different human sample"

python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r4 --model-id test-model "${SRC[@]}" >/dev/null 2>&1
python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r4 --from-cache --model-id test-model >/dev/null 2>&1
python3 "$SCRIPTS/plan_second_read.py" "$P" --run-id r4 >/dev/null 2>&1
set +e
python3 - "$tmp/hs1.json" "$P/raw/_provenance/r4/human_sample_plan.json" <<'PYEOF'
import json, sys
a = json.load(open(sys.argv[1]))["sample"]
b = json.load(open(sys.argv[2]))["sample"]
assert a == b, "a NEW run id re-rolled the sample — the spot-check is re-rollable"
print("seed OK")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "a DIFFERENT run id yields the SAME sample (seeded on the archive, not the run — A36)" \
             || no "the human sample is seeded on the run id and can be re-rolled"

# fix spec A33 — a cache hit calls no model, but it still has to run through ingest:
# the cache holds only the VERBATIM page, and the masked sidecar is a derivative. Under
# "cache_hit ⇒ skip" a fully cached re-run leaves nothing downstream is allowed to read.
echo "=== C2. --from-cache re-ingest (A33) ==="
rm -rf "$P/ocr" "$P/raw/transcript"
set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r5 --model-id test-model "${SRC[@]}" >/dev/null 2>&1
python3 "$SCRIPTS/ingest_transcripts.py" "$P" --run-id r5 --from-cache --model-id test-model \
  >"$tmp/fromcache.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "--from-cache exits 0 with no model output directory at all" \
  || no "--from-cache failed: $(cat "$tmp/fromcache.log")"
miss=0
for sid in s001 s002 s003; do
  [ -f "$P/raw/transcript/$sid/page-001.md" ] || miss=1
  [ -f "$P/ocr/$sid/page-001.md" ] || miss=1
done
[ "$miss" -eq 0 ] \
  && ok "…and BOTH copies are re-derived for every cached page (verbatim + masked)" \
  || no "a cache hit left the masked sidecar missing — nothing downstream could read the page"
grep -q '13800138000' "$P/ocr/s001/page-001.md" \
  && no "the cache-derived masked copy still carries an unmasked phone number" \
  || ok "…the masked copy derived from cache went through masking too (fail-closed, not copied)"

# ===========================================================================
# E. verify_native_text — byte identity, modulo masked spans
# ===========================================================================
echo "=== E. verify_native_text (native_text_identity) ==="

cat > "$P/raw/incoming/labs.txt" <<'EOF'
检验报告
WBC 3.21 10^9/L 参考 3.50-9.50
CEA 25.3 ng/mL 参考 0.00-5.00
联系电话 13800138000
EOF
cat > "$P/07_检验/血常规/2026-03-15_血常规.md" <<'EOF'
SOURCE: lab | CONFIDENCE: high
ORIGINAL: raw/incoming/labs.txt
READ_MODE: native_text

检验报告
WBC 3.21 10^9/L 参考 3.50-9.50
CEA 25.3 ng/mL 参考 0.00-5.00
联系电话 [PII_MASKED]
EOF
cat > "$P/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f9","source_id":"s009","original_path":"labs.txt",
   "raw_path":"raw/incoming/labs.txt","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab","text_layer_kind":"not_applicable",
   "sidecar_path":"07_检验/血常规/2026-03-15_血常规.md","bucket_path":"07_检验/血常规",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"text_payload","version":"1","raw_output_ref":null,"llm_role":"none"},
   "high_risk_review_status":"not_applicable","adapter":"text_payload","persist":true} ]}
EOF

set +e
python3 "$SCRIPTS/verify_native_text.py" "$P" s009 --run-id r1 >"$tmp/vnt_ok.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "identical sidecar (modulo [PII_MASKED]) → exit 0" \
  || no "faithful native_text sidecar failed: $(cat "$tmp/vnt_ok.log")"
grep -q 'IDENTICAL (native_text_identity)' "$tmp/vnt_ok.log" \
  && ok "…and reports the method it used" || no "method not reported"
set +e
python3 -c "
import json
d=json.load(open('$P/raw/_provenance/r1/faithfulness-s009.json'))
assert d['faithfulness_method']=='native_text_identity', d
assert d['identical'] is True
assert d['content_units'][0]['masked_spans']==1, d['content_units'][0]
print('report OK')" >/dev/null
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "faithfulness-<source_id>.json records the method, the verdict and the mask count" \
  || no "faithfulness report is wrong"

# tamper ONE digit — the exact failure a model re-read calls "close enough"
python3 - "$P/07_检验/血常规/2026-03-15_血常规.md" <<'PYEOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text(encoding="utf-8").replace("CEA 25.3", "CEA 25.8"), encoding="utf-8")
PYEOF
set +e
python3 "$SCRIPTS/verify_native_text.py" "$P" s009 --run-id r1 >"$tmp/vnt_bad.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && ok "one tampered digit → exit 1" || no "a changed value passed as faithful, rc=$rc"
grep -q 'NOT IDENTICAL' "$tmp/vnt_bad.log" && ok "…reported as NOT IDENTICAL" || no "verdict not reported"
grep -q 'first difference at source line 3' "$tmp/vnt_bad.log" \
  && ok "…and the diff names the source line where they part" || no "diff location absent"

# a mask may not stand for a dropped paragraph: this is where a naive segment match
# silently inverts into the opposite of the guarantee it claims.
cat > "$P/07_检验/血常规/2026-03-15_血常规.md" <<'EOF'
SOURCE: lab | CONFIDENCE: high
ORIGINAL: raw/incoming/labs.txt
READ_MODE: native_text

检验报告
[PII_MASKED]
EOF
set +e
python3 "$SCRIPTS/verify_native_text.py" "$P" s009 --run-id r1 >"$tmp/vnt_swallow.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && ok "a trailing mask cannot swallow the rest of the file → exit 1" \
  || no "a mask absorbed dropped content and passed, rc=$rc"
grep -q 'dropped source content, not redaction' "$tmp/vnt_swallow.log" \
  && ok "…and says so in those words" || no "swallowed-content reason absent"

# a source that did NOT go through native_text is not eligible for byte identity
python3 - "$P/source_inventory.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["files"][0]["read_mode"] = "model_vision_primary"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF
set +e
python3 "$SCRIPTS/verify_native_text.py" "$P" s009 --run-id r1 >"$tmp/vnt_scope.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] && ok "a model_vision_primary source is refused, not silently passed" \
  || no "byte identity was applied to a derived source, rc=$rc"
grep -q "not 'native_text'" "$tmp/vnt_scope.log" \
  && ok "…and the refusal names the correct faithfulness path instead" \
  || no "scope refusal does not redirect: $(cat "$tmp/vnt_scope.log")"

# ===========================================================================
# F. nothing escaped the patient dir
# ===========================================================================
echo "=== F. containment ==="
python3 - "$P" <<'PYEOF'
import pathlib, sys, json
P = pathlib.Path(sys.argv[1])
bad = []
for f in P.rglob("*.json"):
    txt = f.read_text(encoding="utf-8", errors="replace")
    for needle in ("/Users/", "/private/", "/home/", "/var/folders/"):
        if needle in txt:
            bad.append(f"{f.relative_to(P)} contains {needle}")
assert not bad, bad
print("no host-absolute paths in any product")
PYEOF
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "no host-absolute path was written into any manifest/plan/report" \
             || no "a product leaked a host filesystem path"

# ---------------------------------------------------------------------------
echo
echo "== prepare-ingest-plan-smoke: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
