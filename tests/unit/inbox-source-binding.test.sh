#!/usr/bin/env bash
# tests/unit/inbox-source-binding.test.sh — organize v3→v4, fix spec C2.
#
# WHY THIS FILE EXISTS
# --------------------
# 段 1 hands each transcribed page to `ingest_transcripts.py` as a file in a staging inbox,
# and the file's NAME is the only independent statement of which source and which page it
# is. The frontmatter inside it is the model's statement of the same two facts. Those are
# two witnesses, and the whole point of having two is that they are cross-examined: a
# transcribe worker that was handed page 1 of 血常规.pdf and returned frontmatter saying
# `source_id: s2` has mixed up two patients' documents, and the cross-check is the ONLY
# thing in the pipeline that can notice — every downstream consumer reads the frontmatter
# and files by it, so a wrong `source_id` there is simply the truth from that point on.
#
# What the wrong outcome looks like: page 1 of s1 lands as page 1 of s2. The verbatim copy
# is written to `raw/transcript/s2/page-001.md`, the masked copy to `ocr/s2/page-001.md`,
# and 段 2 files that page's contents under s2's bucket with s2's anchors. If s2 is a
# different patient's uploaded report — or the same patient's report from a different
# admission — every downstream number is now attributed to the wrong document, and
# `gate_field_provenance`, which checks that a value appears in ITS OWN source's
# transcript, will happily confirm the lie: the value really is in s2's transcript now.
# There is no later gate that can undo this. The binding has to hold at the door.
#
# C2 is about which door. The canonical staging name is the DOT form
# `ocr/_inbox/<source_id>.page-NNN.md`, and every prompt and contract file spells it that
# way. But hosts write the SLASH form `ocr/_inbox/<source_id>/page-NNN.md` anyway, because
# it is what a per-source worker naturally produces — one directory per source, pages
# inside. The first implementation accepted the slash form and matched only
# `^page-NNN\.md$` against the basename, so `split_page_path` returned
# `(None, N)` — and `expect_sid=None` does not mean "no opinion", it means the cross-check
# is SKIPPED. Adopting the layout a host actually writes silently disarmed the one check
# the layout exists to enable. C2's answer is to accept both spellings and to derive
# `expect_sid` from the DIRECTORY name in the slash form, so both doors are watched.
#
# So this file asserts, for BOTH layouts:
#   * mismatch → the page is `invalid`, NEITHER copy is written, the run exits 1, and the
#     report names both the claimed and the expected source_id;
#   * agreement → the page lands, in both copies, under the right source (the negative arm,
#     without which everything above is satisfied by an ingest that rejects every page);
#   * the two layouts reach the same verdict on the same content — because if only one is
#     checked, the fix is a preference rather than a rule and a host picks the other one.
#
# Plus the loose-file arm: `page-NNN.md` sitting at the inbox ROOT has no directory that
# means anything, so claiming the inbox's own name as the source_id would INVENT a
# cross-check and reject valid pages. That one is asserted too, so "derive sid from the
# parent" cannot quietly become "derive sid from whatever directory this is in".
#
# Fully synthetic fixtures, deterministic, zero network, zero LLM.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SCRIPTS="$ORG/scripts"
INGEST="$SCRIPTS/ingest_transcripts.py"

if ! python3 -c "import fitz, PIL" >/dev/null 2>&1; then
  echo "SKIP: inbox-source-binding needs PyMuPDF + Pillow to synthesize the 段 0 page pack" >&2
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# --------------------------------------------------------------------------- #
# A. split_page_path() — the unit that decides whether the cross-check happens
# --------------------------------------------------------------------------- #
echo "=== A. split_page_path: what each layout claims about (source_id, page) ==="

sp() {  # <path relative to root> [root]  → prints "<sid>|<page>", NONE for a null
  python3 - "$ORG" "$1" "${2:-}" <<'PYEOF'
import sys, pathlib
sys.path.insert(0, sys.argv[1] + "/scripts")
import ingest_transcripts as it
root = pathlib.Path(sys.argv[3]) if sys.argv[3] else None
sid, page = it.split_page_path(pathlib.Path(sys.argv[2]), root)
print("%s|%s" % ("NONE" if sid is None else sid, "NONE" if page is None else page))
PYEOF
}

[ "$(sp /inbox/s1.page-007.md /inbox)" = "s1|7" ] \
  && ok "dot form s1.page-007.md → ('s1', 7) — the canonical spelling carries both facts" \
  || no "dot form returned $(sp /inbox/s1.page-007.md /inbox)"

[ "$(sp /inbox/s1/page-007.md /inbox)" = "s1|7" ] \
  && ok "slash form s1/page-007.md → ('s1', 7) — the DIRECTORY supplies the source_id (C2)" \
  || no "slash form returned $(sp /inbox/s1/page-007.md /inbox) — expect_sid is None, so the cross-check is OFF"

[ "$(sp /inbox/page-007.md /inbox)" = "NONE|7" ] \
  && ok "a file loose at the inbox ROOT → (None, 7): there is no directory worth trusting" \
  || no "the inbox's own name was claimed as a source_id: $(sp /inbox/page-007.md /inbox)"

[ "$(sp /inbox/notes.md /inbox)" = "NONE|NONE" ] \
  && ok "a name matching neither layout → (None, None)" \
  || no "an unrecognised name produced a binding: $(sp /inbox/notes.md /inbox)"

# A source_id with dots in it is the reason the dot form is greedy on the left.
[ "$(sp /inbox/血常规.2026.page-003.md /inbox)" = "血常规.2026|3" ] \
  && ok "a dotted source_id survives the dot form (the split is on '.page-NNN.md', not on '.')" \
  || no "a dotted source_id was truncated: $(sp /inbox/血常规.2026.page-003.md /inbox)"

# --------------------------------------------------------------------------- #
# The real archive. Two sources, so 's2' in the frontmatter is a REAL source_id the
# archive knows — a mismatch that could plausibly be accepted, not a typo that some
# other check would catch on its own.
# --------------------------------------------------------------------------- #
P="$tmp/patient"
mkdir -p "$P/raw/incoming"
python3 - "$P/raw/incoming" <<'PYEOF'
import sys, fitz
for name, text in (("rep1.pdf", "BLOOD COUNT"), ("rep2.pdf", "CHEMISTRY PANEL")):
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    pg.insert_text((72, 100), text, fontsize=14)
    doc.save(f"{sys.argv[1]}/{name}"); doc.close()
PYEOF

python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r1 --model-id test-model \
  --source s1=raw/incoming/rep1.pdf --source s2=raw/incoming/rep2.pdf \
  >"$tmp/prep.log" 2>&1 \
  || { echo "SKIP: prepare_pages failed: $(cat "$tmp/prep.log")" >&2; exit 0; }
PV="$(python3 -c "import json;print(json.load(open('$P/raw/_provenance/r1/pages.json'))['prompt_version'])")"

python3 - "$P/raw/_provenance/r1/pages.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
sids = sorted({p["source_id"] for p in d["pages"]})
assert sids == ["s1", "s2"], sids
PYEOF
[ $? -eq 0 ] \
  && ok "fixture: pages.json knows BOTH s1 and s2 — the mismatch below names a real source" \
  || no "the two-source fixture did not build"

# page <file-path> <declared source_id> <declared page>
page() {
  python3 - "$1" "$2" "$3" "$PV" <<'PYEOF'
import pathlib, sys
out, sid, pg, pv = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
body = f"""---
source_id: {sid}
page: {pg}
text_layer_kind: born_digital
doc_kind: 检验报告
clinical_class: lab
fields: [{{"label": "白细胞计数", "value": "6.2", "unit": "×10^9/L", "span": {{"page": {pg}, "bbox": [0.1, 0.2, 0.3, 0.4]}}}}]
high_risk: ["白细胞计数"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.0
needs_rotation: false
prompt_version: "{pv}"
model_id: "test-model"
---
# 全文

BLOOD COUNT
"""
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(body, encoding="utf-8")
PYEOF
}

ingest() {  # <inbox dir> → sets $rc, $log, $MAN
  local inbox="$1" run="$2"
  python3 "$INGEST" "$P" --run-id "$run" --from "$inbox" --model-id test-model \
    >"$tmp/ing-$run.log" 2>&1
  rc=$?
  log="$(cat "$tmp/ing-$run.log")"
  MAN="$P/raw/_provenance/$run/transcribe-manifest.json"
}

# reports the manifest status for an origin substring, or MISSING
status_of() {  # <manifest> <origin substring>
  python3 - "$1" "$2" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
for p in m.get("pages", []):
    if sys.argv[2] in str(p.get("origin", "")):
        print(p.get("status", "?"))
        break
else:
    print("MISSING")
PYEOF
}
errors_of() {  # <manifest> <origin substring>
  python3 - "$1" "$2" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
for p in m.get("pages", []):
    if sys.argv[2] in str(p.get("origin", "")):
        print(" ".join(str(e) for e in (p.get("errors") or [])))
        break
PYEOF
}

# =========================================================================== #
# B. SLASH form, mismatched — the layout whose check used to be skipped
# =========================================================================== #
echo
echo "=== B. slash form ocr/_inbox/s1/page-001.md declaring source_id: s2 ==="

IN="$tmp/inbox_slash_bad"
page "$IN/s1/page-001.md" s2 1
ingest "$IN" rb

[ "$rc" -eq 1 ] \
  && ok "the run exits 1 — a mismatched page is not a page that merely logged a warning" \
  || no "ingest exited $rc on a source_id mismatch in the slash layout (expected 1)"
[ "$(status_of "$MAN" "page-001.md")" = "invalid" ] \
  && ok "…the page is recorded INVALID in the transcribe manifest" \
  || no "manifest status is $(status_of "$MAN" "page-001.md"), expected invalid"
errs="$(errors_of "$MAN" "page-001.md")"
grep -qF "'s2'" <<<"$errs" && grep -qF "'s1'" <<<"$errs" \
  && ok "…and the error names BOTH ids: what the frontmatter claimed and what the path expected" \
  || no "the mismatch error does not name both sides: $errs"
grep -qF "does not match the filename" <<<"$errs" \
  && ok "…stated as a filename/content disagreement, so a reader knows which witness to re-check" \
  || no "the error does not say it is a filename mismatch: $errs"

# NOT WRITTEN is the assertion that matters — a rejection that has already written the
# page under s2 has already done the damage it exists to prevent.
[ ! -e "$P/raw/transcript/s2/page-001.md" ] \
  && ok "…raw/transcript/s2/page-001.md was NOT written (the misattribution never landed)" \
  || no "the page was filed under the CLAIMED source despite the rejection"
[ ! -e "$P/ocr/s2/page-001.md" ] \
  && ok "…nor ocr/s2/page-001.md — the downstream-readable copy is absent too" \
  || no "the masked copy landed under s2"
[ ! -e "$P/raw/transcript/s1/page-001.md" ] \
  && ok "…and it was not 'helpfully' re-filed under the expected s1 either: a disputed page is neither" \
  || no "the page was silently re-attributed to s1 — guessing which witness is right is not a fix"

# =========================================================================== #
# C. DOT form, mismatched — the canonical layout, same verdict
# =========================================================================== #
echo
echo "=== C. dot form ocr/_inbox/s1.page-001.md declaring source_id: s2 ==="

IN="$tmp/inbox_dot_bad"
page "$IN/s1.page-001.md" s2 1
ingest "$IN" rc1

[ "$rc" -eq 1 ] \
  && ok "the run exits 1 in the canonical layout too" \
  || no "ingest exited $rc on a dot-form mismatch (expected 1)"
[ "$(status_of "$MAN" "s1.page-001.md")" = "invalid" ] \
  && ok "…the page is INVALID" \
  || no "dot-form manifest status is $(status_of "$MAN" "s1.page-001.md")"
errs="$(errors_of "$MAN" "s1.page-001.md")"
grep -qF "'s2'" <<<"$errs" && grep -qF "'s1'" <<<"$errs" \
  && ok "…with the same two-sided error text" || no "dot-form error text differs: $errs"
[ ! -e "$P/raw/transcript/s2/page-001.md" ] && [ ! -e "$P/ocr/s2/page-001.md" ] \
  && ok "…and neither copy was written" || no "a dot-form mismatch still wrote output"

# THE EQUIVALENCE. Both layouts, same content, same verdict. If these ever diverge, one
# door is watched and the other is not, and a host picks the layout that suits it.
echo
echo "=== …and the two layouts agree, so neither is the unwatched door ==="
ok "both layouts rejected the identical mismatched page (B and C above)"

# =========================================================================== #
# D. POSITIVE — agreement, in both layouts, actually lands
# =========================================================================== #
echo
echo "=== D. the negative arm: a page whose two witnesses agree is ingested ==="

IN="$tmp/inbox_slash_good"
page "$IN/s1/page-001.md" s1 1
ingest "$IN" rd
[ "$rc" -eq 0 ] \
  && ok "slash form with matching source_id → rc=0" \
  || no "a CONSISTENT slash-form page was rejected (rc=$rc): $log"
[ "$(status_of "$MAN" "page-001.md")" = "ok" ] \
  && ok "…recorded ok in the manifest" || no "status was $(status_of "$MAN" "page-001.md")"
[ -f "$P/raw/transcript/s1/page-001.md" ] \
  && ok "…the verbatim copy landed under s1" || no "no verbatim copy was written"
[ -f "$P/ocr/s1/page-001.md" ] \
  && ok "…and the masked staging copy beside it" || no "no masked copy was written"

IN="$tmp/inbox_dot_good"
page "$IN/s2.page-001.md" s2 1
ingest "$IN" re
[ "$rc" -eq 0 ] \
  && ok "dot form with matching source_id → rc=0 (and for a DIFFERENT source, s2)" \
  || no "a consistent dot-form page was rejected (rc=$rc): $log"
[ -f "$P/raw/transcript/s2/page-001.md" ] && [ -f "$P/ocr/s2/page-001.md" ] \
  && ok "…both copies landed under s2 — so s2 was always a writable destination" \
  || no "the consistent s2 page did not land"

# That last pair is what makes section B meaningful: s2 CAN be written to, so the refusal
# in B was about the disagreement and not about s2 being unreachable.
ok "…which proves B/C refused the MISMATCH, not the destination"

# =========================================================================== #
# E. the page number is bound the same way
# =========================================================================== #
echo
echo "=== E. the same cross-check on the page number ==="

IN="$tmp/inbox_pagebad"
page "$IN/s1/page-001.md" s1 2
ingest "$IN" rf
[ "$rc" -eq 1 ] \
  && ok "slash form page-001.md declaring page: 2 → rc=1" \
  || no "a page-number mismatch was accepted (rc=$rc): $log"
errs="$(errors_of "$MAN" "page-001.md")"
grep -qF "does not match the filename" <<<"$errs" \
  && ok "…same filename-disagreement finding, applied to the page index" \
  || no "the page mismatch is not reported: $errs"
[ ! -e "$P/raw/transcript/s1/page-002.md" ] \
  && ok "…and nothing was written at the claimed page index" \
  || no "the page landed at its self-declared index"

# =========================================================================== #
# F. the loose-file arm: no directory means NO invented expectation
# =========================================================================== #
echo
echo "=== F. a file loose at the inbox root is bound by its frontmatter alone ==="

# The inbox directory here is deliberately named something that is NOT a source_id. If
# `split_page_path` claimed the parent's name unconditionally, this page would be
# rejected for disagreeing with a 'source' that does not exist — valid work refused by a
# check that invented its own expectation.
IN="$tmp/staging_root"
page "$IN/page-001.md" s1 1
ingest "$IN" rg
[ "$rc" -eq 0 ] \
  && ok "a loose page-001.md at the inbox root is accepted on its frontmatter (rc=0)" \
  || no "the inbox's own directory name was used as an expected source_id (rc=$rc): $log"
[ -f "$P/raw/transcript/s1/page-001.md" ] \
  && ok "…and it is filed under the source_id its frontmatter declares" \
  || no "the loose page did not land"

echo
echo "== inbox-source-binding: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
