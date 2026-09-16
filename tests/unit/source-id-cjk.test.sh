#!/usr/bin/env bash
# tests/unit/source-id-cjk.test.sh — organize v3 fix spec A8, prepare_pages.py source_id.
#
# A `source_id` is not a label, it is an IDENTITY. It becomes a directory name three
# places over:
#
#     raw/adapter_views/<source_id>/page-NNN.png
#     raw/transcript/<source_id>/page-NNN.md
#     the manifest row in raw/_provenance/<run>/pages.json that joins those two
#
# so two documents that end up with the same id do not merely confuse a report — they
# overwrite each other's rendered pages and each other's transcripts, and the archive
# afterwards contains one patient's pathology under the other's filename with nothing
# anywhere recording that it happened.
#
# THE CJK COLLAPSE. An id derived from a filename alone through an ASCII-only sanitizer
# maps EVERY non-ASCII character to `_`, so 血常规报告.pdf and 病理报告.pdf both fold to
# `____` — or, once the empty-string fallback fires, both fold to `src`. In an archive
# where Chinese filenames are the norm rather than the exception, that is not an edge
# case: it is the default case. A8 fixes it from both ends —
#
#   * sanitize() KEEPS `[A-Za-z0-9一-鿿_-]`, so the readable half of the id stays
#     readable and stays distinct for Chinese names;
#   * the id is `sanitize(stem) + "-" + sha256(file_bytes)[:8]`, so identity is
#     content-addressed. Two files with the same name in different folders, or the same
#     name re-uploaded after an edit, are DIFFERENT sources and get different ids.
#
# THE RESIDUAL COLLISION IS A HARD ERROR. A hash prefix makes collision unlikely, not
# impossible, and an explicit `--source dup=A.pdf --source dup=B.pdf` makes it trivial.
# A8 says exit 1 and name the collision rather than silently picking a winner: whichever
# winner is picked, the loser's pages are gone and the manifest still claims both were
# prepared.
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
  echo "SKIP: source-id-cjk needs PyMuPDF + Pillow to synthesize page fixtures" >&2
  exit 0
fi

# ---------------------------------------------------------------- fixtures ----
# Two REAL PDFs with different Chinese filenames AND different bytes. Different bytes
# matters: it makes the test able to tell apart "the ids differ because the CJK stems
# survived" from "the ids differ only because the hashes differ".
P="$tmp/patient"
mkdir -p "$P/raw/incoming"
python3 - "$P/raw/incoming" <<'PYEOF'
import sys
import fitz

d = sys.argv[1]
for name, body in (("血常规报告", "WBC 3.21 10^9/L  ref 3.50-9.50"),
                   ("病理报告", "invasive adenocarcinoma, moderately differentiated")):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), body, fontsize=11)
    doc.save(f"{d}/{name}.pdf")
    doc.close()
PYEOF

# ===========================================================================
# A. two DIFFERENT Chinese filenames → two DIFFERENT source_ids
# ===========================================================================
echo "=== A. CJK filenames must not collapse onto one id ==="

set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id r1 --model-id test-model --quiet \
  >"$tmp/r1.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "prepare_pages exits 0 on a vault of two Chinese-named PDFs" \
  || no "prepare_pages exited $rc: $(cat "$tmp/r1.log")"

MAN="$P/raw/_provenance/r1/pages.json"
[ -f "$MAN" ] && ok "pages.json written to raw/_provenance/<run>/ (A28)" \
  || no "pages.json not written"

set +e
out="$(python3 - "$MAN" <<'PYEOF' 2>&1
import json
import sys

m = json.load(open(sys.argv[1], encoding="utf-8"))
ids = sorted({p["source_id"] for p in m["pages"]})
assert len(ids) == 2, f"two sources collapsed to {len(ids)} source_id(s): {ids}"

# the CJK stem survived into the readable half — this is the actual A8 assertion, and
# the reason a plain "the ids differ" check is not enough: two `src-<hash>` ids also
# differ, while telling a human nothing and losing the stem forever.
assert any(i.startswith("血常规报告-") for i in ids), ids
assert any(i.startswith("病理报告-") for i in ids), ids
assert not any(i.startswith("src-") for i in ids), f"a CJK stem folded to the fallback: {ids}"
assert not any("_" * 2 in i for i in ids), f"CJK folded to underscores: {ids}"

# ... and the other half is a content hash, 8 lowercase hex characters
import re
for i in ids:
    stem, _, digest = i.rpartition("-")
    assert re.fullmatch(r"[0-9a-f]{8}", digest), f"{i!r} does not end in sha256[:8]"
    assert stem, f"{i!r} has no readable half"

# each id owns its own adapter_views directory — the thing a collision would merge
dirs = sorted({p["image_path"].split("/")[2] for p in m["pages"] if p.get("image_path")})
assert dirs == ids, f"adapter_views dirs {dirs} != source_ids {ids}"
print("IDS:" + "|".join(ids))
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "血常规报告.pdf and 病理报告.pdf get two distinct, CJK-preserving source_ids" \
  || no "CJK source_id generation is wrong: $out"
echo "$out" | grep -q "血常规报告-" \
  && ok "…the readable half is the verbatim Chinese stem, not '____' or 'src'" \
  || no "CJK stem did not survive into the id: $out"
echo "$out" | grep -q "IDS:.*|" \
  && ok "…each source owns its own raw/adapter_views/<source_id>/ directory" \
  || no "adapter_views directories do not match the ids: $out"

# ---------------------------------------------------------------------------
# the hash half earns its keep: SAME Chinese stem, DIFFERENT bytes → different ids
# ---------------------------------------------------------------------------
Q="$tmp/patient_same_stem"
mkdir -p "$Q/raw/2026-01" "$Q/raw/2026-06"
python3 - "$Q/raw" <<'PYEOF'
import sys
import fitz

d = sys.argv[1]
for sub, body in (("2026-01", "WBC 3.21"), ("2026-06", "WBC 9.87")):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), body, fontsize=11)
    doc.save(f"{d}/{sub}/血常规报告.pdf")
    doc.close()
PYEOF

set +e
python3 "$SCRIPTS/prepare_pages.py" "$Q" --run-id r1 --model-id test-model --quiet \
  >"$tmp/q1.log" 2>&1
rc=$?
out="$(python3 - "$Q/raw/_provenance/r1/pages.json" <<'PYEOF' 2>&1
import json
import sys

m = json.load(open(sys.argv[1], encoding="utf-8"))
ids = sorted({p["source_id"] for p in m["pages"]})
assert len(ids) == 2, f"same-stem different-bytes collapsed to {ids}"
assert all(i.startswith("血常规报告-") for i in ids), ids
assert ids[0] != ids[1]
print("|".join(ids))
PYEOF
)"
rc2=$?
set -e
[ "$rc" -eq 0 ] && [ "$rc2" -eq 0 ] \
  && ok "the same Chinese filename re-uploaded with different bytes → two different ids (content-addressed)" \
  || no "same-stem/different-bytes did not separate: rc=$rc $out"

# ===========================================================================
# B. NEGATIVE — an explicit source_id collision is a hard ERROR, not a winner-pick
# ===========================================================================
echo "=== B. source_id collision ==="

cp "$P/raw/incoming/血常规报告.pdf" "$P/raw/incoming/A.pdf"
cp "$P/raw/incoming/病理报告.pdf" "$P/raw/incoming/B.pdf"

set +e
out="$(python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id rdup --model-id test-model --quiet \
        --source dup=raw/incoming/A.pdf --source dup=raw/incoming/B.pdf 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] \
  && ok "--source dup=A.pdf --source dup=B.pdf → exit 1 (A8: any collision is an ERROR)" \
  || no "a source_id collision exited $rc instead of 1: $out"
echo "$out" | grep -q "source_id collision" \
  && ok "…the error is named as a source_id collision" || no "collision not named: $out"
echo "$out" | grep -q "'dup'" \
  && ok "…the error quotes the colliding id" || no "colliding id not quoted: $out"
echo "$out" | grep -q "A.pdf" && echo "$out" | grep -q "B.pdf" \
  && ok "…the error names BOTH documents that claimed it" \
  || no "the two colliding documents are not both named: $out"
echo "$out" | grep -qE "overwrite|refusing" \
  && ok "…and says why it refuses rather than picking a winner (the loser's pages are lost)" \
  || no "the refusal rationale is missing: $out"

# a collision must abort BEFORE anything is written under the contested id
[ ! -d "$P/raw/adapter_views/dup" ] \
  && ok "nothing was rendered under the contested id (fail-closed, not fail-halfway)" \
  || no "raw/adapter_views/dup/ exists — the run wrote pages before refusing"
[ ! -f "$P/raw/_provenance/rdup/pages.json" ] \
  && ok "no pages.json was left behind claiming the collided run succeeded" \
  || no "a manifest was written for the aborted run"

# ===========================================================================
# C. POSITIVE — the collision rule does not fire on the legal shapes
# ===========================================================================
echo "=== C. what is NOT a collision ==="

set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id rok --model-id test-model --quiet \
  --source sA=raw/incoming/A.pdf --source sB=raw/incoming/B.pdf >"$tmp/rok.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] && ok "two DIFFERENT ids for two different files → exit 0" \
  || no "distinct explicit ids were rejected: $(cat "$tmp/rok.log")"

set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id rsame --model-id test-model --quiet \
  --source dup=raw/incoming/A.pdf --source dup=raw/incoming/A.pdf >"$tmp/rsame.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "the SAME id for the SAME file twice → exit 0 (a repeat, not a collision)" \
  || no "an idempotent repeat was treated as a collision: $(cat "$tmp/rsame.log")"

# CJK is legal in an EXPLICIT id too, or the inventory could not round-trip minted ids
set +e
python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id rcjk --model-id test-model --quiet \
  --source 血常规报告-aabbccdd=raw/incoming/A.pdf >"$tmp/rcjk.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "an explicit CJK source_id is accepted (minted ids must be re-passable)" \
  || no "the path whitelist rejects its own minted CJK ids: $(cat "$tmp/rcjk.log")"

# ...but a traversal dressed up as an id is still refused (A9 applied at the A8 boundary)
set +e
out="$(python3 "$SCRIPTS/prepare_pages.py" "$P" --run-id rbad --model-id test-model --quiet \
        --source ../../escape=raw/incoming/A.pdf 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] \
  && ok "--source ../../escape=... is refused (an id becomes a directory name)" \
  || no "a traversal source_id was accepted, rc=$rc"
echo "$out" | grep -q "source_id" \
  && ok "…and the refusal says it was the source_id that was unsafe" \
  || no "refusal does not name source_id: $out"

# ===========================================================================
# D. the rule is documented where the next editor will read it
# ===========================================================================
echo "=== D. A8 rationale in prepare_pages.py ==="

says() {  # <pattern> <label>
  grep -q "$1" "$SCRIPTS/prepare_pages.py" && ok "$2" \
    || no "$2 — not found in prepare_pages.py"
}
says "sanitize" "the id-minting rule is named in the source"
says "sha256" "the content-hash half is named"
says "collision" "the collision rule is stated"
says "keeps CJK verbatim\|CJK" "the CJK-preservation reason is written down"

# ---------------------------------------------------------------------------
echo
echo "== source-id-cjk: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
