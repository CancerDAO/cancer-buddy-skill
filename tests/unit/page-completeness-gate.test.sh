#!/usr/bin/env bash
# tests/unit/page-completeness-gate.test.sh — organize v3→v4, fix spec C5.
#
# WHY THIS FILE EXISTS
# --------------------
# Every other per-page gate in validate_structured_outputs.py iterates over what EXISTS.
# gate_faithfulness checks the spans that were recorded; gate_field_provenance checks that
# each value occurs in its source's transcript; gate_high_risk_denominator recomputes the
# high-risk set from the frontmatter that is on disk; the second-read gates check the
# channels declared on the pages that came back. Not one of them can see a page that never
# arrived.
#
# So the cheapest way to pass the entire file at once was never to cheat on a page. It was
# to LOSE one. A five-page report that yields four transcripts has four clean pages, four
# verified spans, a faithful sidecar set and a provenance record that reconciles
# perfectly. The fifth page — the one carrying the 剂量, or the 分期, or the variant — is
# simply not in any denominator, and nothing anywhere in the archive says a page went
# missing. Every gate reports green. The archive is not merely incomplete, it is
# CONFIDENTLY incomplete, which is worse, because the next reader has a validator's word
# for it.
#
# `pages.json` is the one surface written BEFORE the transcription pass, by a
# deterministic script that opened the file and counted its pages. It is the archive's
# only independent statement of how many pages a document has, and this gate is the
# reconciliation against it.
#
# WHAT THIS FILE WEIGHS EQUALLY. The gate has two ways to be wrong and they pull opposite:
#
#   MISSING THE MISSING PAGE — the failure above, asserted first and with the page NUMBER,
#   because 「4 of 5 pages transcribed」 is a statistic and 「page 2 is missing」 is an
#   instruction.
#
#   REFUSING A DECLARED GAP — an `unreadable` page is a page prepare_pages.py already said
#   it could not rasterize. That record IS the disclosure. Demanding a transcript for it
#   would make every archive containing one damaged scan permanently red, and a gate that
#   is always red is a gate people disable. A declared gap and an undeclared one are
#   different things and must be treated differently — that is the whole distinction the
#   gate encodes, so it is asserted from both sides.
#
# And the third position, which is neither: pages.json ABSENT while transcripts exist. The
# gate cannot tell a dropped page from a page that was never claimed, so it WARNs. 「I
# could not measure this」 and 「I measured this and it was fine」 must never print the
# same way — a silent pass here would make deleting the provenance directory the cheapest
# way to lose a page.
#
# The cross-run merge gets its own section because it is where the gate could be undone
# without touching the gate: if a LATER run's pages.json replaced an earlier one, a run
# that gave up on page 2 would retire the obligation a previous run had already proven
# (it transcribed that page once). Page sets may grow. They may not shrink.
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

# The gate takes (patient_dir, errors, warnings) — three-arg, so errors and warnings are
# reported SEPARATELY. A harness that merged them could not tell the ERROR arm from the
# WARN arm, which is the single distinction this gate is built around.
run_gate() {  # <patient_dir> → sets $rc (1 if errors), $errs, $warns
  local o
  o="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib, json
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errors, warnings = [], []
v.gate_page_completeness(pathlib.Path(sys.argv[2]), errors, warnings)
print(json.dumps({"errors": errors, "warnings": warnings}, ensure_ascii=False))
PYEOF
)"
  errs="$(python3 -c "import json,sys;print('\n'.join(json.loads(sys.argv[1])['errors']))" "$o")"
  warns="$(python3 -c "import json,sys;print('\n'.join(json.loads(sys.argv[1])['warnings']))" "$o")"
  [ -n "$errs" ] && rc=1 || rc=0
}

# --------------------------------------------------------------------------- #
# A two-page scanned report, read by model vision. Everything else about the archive is
# deliberately minimal — this gate reads exactly two things (the inventory row and the
# transcript directory) plus the run provenance, and a richer fixture would only add ways
# for an unrelated defect to be mistaken for this one.
# --------------------------------------------------------------------------- #
inv() {  # <dir>
  cat > "$1/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"scan.pdf",
   "raw_path":"raw/incoming/scan.pdf","page_range":"1-2",
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent","sidecar_path":"07_检验/2026-03-15_血常规.md",
   "bucket_path":"07_检验","transcript_path":"raw/transcript/s1/page-001.md",
   "modality":"image","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"not_applicable","high_risk_fields":[],
   "adapter":"pdf_pages","persist":true} ]}
EOF
}

pages_json() {  # <dir> <run-id> <pages json array>
  mkdir -p "$1/raw/_provenance/$2"
  cat > "$1/raw/_provenance/$2/pages.json" <<EOF
{"run_id":"$2","prompt_version":"3.1","model_id":"test-model","pages":$3}
EOF
}

transcript() {  # <dir> <page number>
  mkdir -p "$1/raw/transcript/s1"
  printf -- '---\nsource_id: s1\npage: %s\n---\n# 全文\nPAGE %s\n' "$2" "$2" \
    > "$(printf '%s/raw/transcript/s1/page-%03d.md' "$1" "$2")"
}

P_OK='[{"source_id":"s1","page":1,"kind":"known"},{"source_id":"s1","page":2,"kind":"known"}]'

# ===========================================================================
echo "=== A. pages.json says two pages, the disk holds one ==="
# ===========================================================================
D="$tmp/missing"; mkdir -p "$D"
inv "$D"; pages_json "$D" r1 "$P_OK"; transcript "$D" 1

run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "a page that never came back is an ERROR (C5)" \
  || no "the gate passed with one of two pages transcribed — a lost page is invisible again"
grep -qF "missing page(s) 2" <<<"$errs" \
  && ok "…and the message names the missing page NUMBER (2), not just a count" \
  || no "the missing page number is not in the finding: $errs"
grep -qF "s1" <<<"$errs" \
  && ok "…and the source it belongs to" || no "the source is not named: $errs"
grep -qF "records 2 readable page(s)" <<<"$errs" \
  && ok "…and both sides of the reconciliation: what was claimed…" || no "claimed count missing: $errs"
grep -qF "holds 1" <<<"$errs" \
  && ok "…and what was found" || no "found count missing: $errs"
grep -qF "kind: unreadable" <<<"$errs" \
  && ok "…and the message offers the LEGITIMATE alternative (declare it unreadable) beside 're-transcribe'" \
  || no "the finding does not name the declared-gap escape: $errs"
[ -z "$warns" ] \
  && ok "…reported purely as an ERROR, with nothing in the WARN channel to soften it" \
  || no "the missing page also produced a WARN: $warns"

# NEGATIVE ARM — the identical archive with both pages present. Without this, everything
# above is satisfied by a gate that errors on every archive it is shown.
echo
echo "=== B. the negative arm: both pages present ==="
D="$tmp/complete"; mkdir -p "$D"
inv "$D"; pages_json "$D" r1 "$P_OK"; transcript "$D" 1; transcript "$D" 2
run_gate "$D"
[ "$rc" -eq 0 ] && ok "two declared pages with two transcripts → no finding" \
                || no "the complete archive was flagged: $errs"
[ -z "$warns" ] && ok "…and no WARN either: measured, and fine" || no "unexpected WARN: $warns"

# Extra transcripts are not an error. A run that transcribed a page pages.json never
# listed has MORE evidence, not less, and the gate is a floor rather than an equality.
transcript "$D" 3
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "an EXTRA transcript page beyond pages.json is not an error (the gate is a floor, not an equality)" \
  || no "a superset of the declared pages was rejected: $errs"

# ===========================================================================
echo
echo "=== C. a page declared unreadable is a DECLARED gap, and is exempt ==="
# ===========================================================================
D="$tmp/unreadable"; mkdir -p "$D"
inv "$D"
pages_json "$D" r1 '[{"source_id":"s1","page":1,"kind":"known"},{"source_id":"s1","page":2,"kind":"unreadable"}]'
transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "page 2 marked kind: unreadable needs no transcript — prepare_pages already disclosed it" \
  || no "a declared unreadable page was demanded as a transcript: $errs"

# The exemption is bought by the DECLARATION, not by absence. Same archive, same missing
# file, `kind: known` — and it is an error again. This pair is the entire distinction.
D="$tmp/unreadable_flipped"; mkdir -p "$D"
inv "$D"; pages_json "$D" r1 "$P_OK"; transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "…and the SAME absent page with kind: known is an ERROR — the declaration is the whole difference" \
  || no "the unreadable exemption leaked to undeclared pages"

# An all-unreadable source is exempt entirely, and the message (when there is one) must
# say which pages were discounted, so a reader can see how small the denominator got.
D="$tmp/mixed"; mkdir -p "$D"
inv "$D"
pages_json "$D" r1 '[{"source_id":"s1","page":1,"kind":"known"},{"source_id":"s1","page":2,"kind":"unreadable"},{"source_id":"s1","page":3,"kind":"known"}]'
transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 1 ] && ok "a mixed source still errors for its readable missing page (3)" \
               || no "the mixed source passed: $errs"
grep -qF "missing page(s) 3" <<<"$errs" \
  && ok "…naming ONLY page 3 — page 2 is not reported as missing" \
  || no "the mixed case reported the wrong pages: $errs"
grep -qF "declared unreadable" <<<"$errs" \
  && ok "…and the message states that page 2 was discounted, so the denominator is visible" \
  || no "the discounted page is not disclosed: $errs"

# ===========================================================================
echo
echo "=== D. pages.json absent, transcripts present → WARN, never silence ==="
# ===========================================================================
D="$tmp/nopages"; mkdir -p "$D"
inv "$D"; transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "no pages.json → not an ERROR (a pruned provenance dir is not proof of a lost page)" \
  || no "an absent page manifest was treated as a defect: $errs"
[ -n "$warns" ] \
  && ok "…but a WARN IS emitted: 'could not measure' must not print like 'measured and fine'" \
  || no "the gate passed SILENTLY with no page manifest — deleting provenance is now the cheapest way to lose a page"
grep -qF "s1" <<<"$warns" \
  && ok "…naming the source whose page set cannot be recovered" || no "the WARN does not name the source: $warns"
grep -qF "prepare_pages.py" <<<"$warns" \
  && ok "…and the command that restores the manifest" || no "no remedy in the WARN: $warns"
grep -qiF "complete" <<<"$warns" \
  && ok "…and saying explicitly that completeness is UNKNOWN, not established" \
  || no "the WARN does not state what it failed to establish: $warns"

# …and an archive with neither pages.json nor transcripts says nothing at all: there is
# no source of a page obligation, so inventing a WARN would be noise on every text-only
# archive.
D="$tmp/neither"; mkdir -p "$D"
inv "$D"
run_gate "$D"
[ -z "$warns" ] && [ "$rc" -eq 0 ] \
  && ok "neither manifest nor transcripts → silent (no obligation exists to report on)" \
  || no "an archive with no page evidence produced output: errs=$errs warns=$warns"

# ===========================================================================
echo
echo "=== E. the cross-run merge: a page set may grow, never shrink ==="
# ===========================================================================
# This is where the gate could be disarmed without touching the gate. Two runs, two
# pages.json files. If the LATER one replaced the earlier, run-2's shorter page list would
# retire an obligation run-1 had already established.
D="$tmp/tworuns"; mkdir -p "$D"
inv "$D"
pages_json "$D" r1 "$P_OK"
pages_json "$D" r2 '[{"source_id":"s1","page":1,"kind":"known"}]'
transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "a later run listing FEWER pages does not retire the earlier obligation" \
  || no "run-2's shorter pages.json shrank the page set — a lazier re-run is now a way to lose page 2"
grep -qF "missing page(s) 2" <<<"$errs" \
  && ok "…page 2 is still owed, by number" || no "page 2 was forgotten: $errs"

# The same, in the other direction: run-1 gave up on page 2, run-2 read it. The page
# demonstrably CAN be read, so the obligation is live.
D="$tmp/tworuns_up"; mkdir -p "$D"
inv "$D"
pages_json "$D" r1 '[{"source_id":"s1","page":1,"kind":"known"},{"source_id":"s1","page":2,"kind":"unreadable"}]'
pages_json "$D" r2 "$P_OK"
transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "a page once marked unreadable but READ by a later run is owed a transcript (read wins over unreadable)" \
  || no "an earlier 'unreadable' verdict survived a later successful read: $errs"

# …and the reverse order of the same two runs must reach the same verdict, because
# directory iteration order is not a contract anyone should be relying on.
D="$tmp/tworuns_rev"; mkdir -p "$D"
inv "$D"
pages_json "$D" r1 "$P_OK"
pages_json "$D" r2 '[{"source_id":"s1","page":1,"kind":"known"},{"source_id":"s1","page":2,"kind":"unreadable"}]'
transcript "$D" 1
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "…and the SAME two runs in the opposite order reach the same verdict (merge is order-independent)" \
  || no "the verdict depends on which run directory is read first: $errs"

# ===========================================================================
echo
echo "=== F. scope: the two populations the gate must NOT demand pages from ==="
# ===========================================================================
# A native_text source took its characters byte-for-byte from a born-digital file (A35).
# It has no per-page transcript BY CONTRACT; demanding one would fail every text archive.
D="$tmp/native"; mkdir -p "$D"
cat > "$D/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"note.txt",
   "raw_path":"raw/incoming/note.txt","page_range":null,
   "kind":"known","doc_kind":"出院小结","clinical_class":"narrative",
   "text_layer_kind":"not_applicable","sidecar_path":"03_病程与叙事文书/出院小结/a.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable","high_risk_fields":[],
   "adapter":"text_payload","persist":true} ]}
EOF
pages_json "$D" r1 '[{"source_id":"s1","page":1,"kind":"known"}]'
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a native_text source with no transcripts is out of scope (A35)" \
  || no "a born-digital text source was asked for page transcripts: $errs"

# A migrated row is exempt for the reason C3 gives, and pays for it in projection_coverage.
D="$tmp/legacy"; mkdir -p "$D"
python3 - "$D" <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
inv = {"schema": "source_inventory_v2", "scheme_version": 4, "patient_dir": ".",
       "generated_at": "2026-09-16T00:00:00Z",
       "files": [{"file_id": "f1", "source_id": "s1", "original_path": "scan.pdf",
                  "raw_path": "raw/incoming/scan.pdf", "page_range": "1-2",
                  "kind": "known", "doc_kind": "检验报告", "clinical_class": "lab",
                  "text_layer_kind": "absent", "sidecar_path": "07_检验/a.md",
                  "bucket_path": "07_检验", "modality": "image",
                  "read_mode": "model_vision_primary",
                  "legacy_transcript_unavailable": True,
                  "extractor_provenance": {"engine": "host-vision", "version": "3.0",
                                           "raw_output_ref": None,
                                           "llm_role": "primary_transcription"},
                  "high_risk_review_status": "not_applicable", "high_risk_fields": [],
                  "reread_channel": "none",
                  "adapter": "pdf_pages", "persist": True}]}
(d / "source_inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
pages_json "$D" r1 "$P_OK"
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "a legacy_transcript_unavailable row is exempt (C3; paid for in projection_coverage)" \
  || no "the migration exemption does not reach this gate: $errs"

echo
echo "== page-completeness-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
