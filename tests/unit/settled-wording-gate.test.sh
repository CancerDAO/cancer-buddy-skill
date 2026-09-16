#!/usr/bin/env bash
# tests/unit/settled-wording-gate.test.sh — organize v3→v4 fix spec A23, enforced by B19.
#
# WHY A WORD IS A CONTRACT.
#
# Under the pre-v4 contract, a high-risk value that had been read twice was recorded as
# a 「settled fact」, optionally with a `settled_via` note saying how. A23 deleted that
# vocabulary, and the reason is not stylistic:
#
#   * `settled_fact` names the CONCLUSION. Nothing in the word requires a second
#     channel to exist, so the same pass that did the first reading could write it —
#     the model that read 白细胞 3.2 off a scan could, in the same breath, declare 3.2
#     settled. That is self-certification wearing the costume of verification.
#   * `settled_via` was OPTIONAL. A consumer holding a settled fact had no guaranteed
#     way to ask 「settled by what?」, and a provenance claim you cannot interrogate is
#     a provenance claim you cannot audit.
#
# The replacement inverts the order: the channel comes first and the status is
# unwriteable without it —
#
#     high_risk_fields[]: { label, status: passed_independent_reread,
#                           reread_channel: text_layer | barcode | deterministic_ocr |
#                                           alternate_vision_model | human,
#                           readings: [{channel, value}, ...] }
#
# `passed_independent_reread` is a claim ABOUT A CHANNEL. You cannot write it without
# naming which second channel produced the agreeing reading, and the surrounding gates
# (A5/B1/B2) then check that channel is real, distinct from the transcribe model, and —
# for `human` — backed by a verdict in human_sample_result.json.
#
# WHY A REGRESSION GATE AND NOT JUST A DOC EDIT.
#
# Deleted vocabulary comes back. It comes back from a prompt that still remembers the
# old key, from a partially-updated template, from a consumer that writes what it used
# to read, and from a model that saw ten thousand examples of the old shape. When it
# does, it comes back looking correct: `"settled_fact": true` reads like an assurance,
# and every downstream surface that merely displays strings will display it. B19 is the
# tripwire — the two compound tokens may not appear anywhere on a v4 archive's
# delivered surfaces.
#
# WHAT THE GATE DELIBERATELY DOES *NOT* CATCH, and why that matters just as much:
#
#   extracted_fields.json.open_verification_status: "settled"   ← LEGAL (A16 / A23)
#
# There, 「settled」 means 「this OPEN field's two reads agreed」 — a statement about an
# unanchorable candidate value sitting in 15_未分类资料/, explicitly NOT a verified
# clinical fact, and the field was renamed to `open_verification_status` precisely so it
# could not be confused with the structured JSONs' `verification_status`. A gate that
# matched the bare word `settled` would fire on the contract's own permitted survivor,
# and a gate that fires on legal output is a gate that gets switched off. Matching only
# the COMPOUND tokens is what makes this one survivable. That exemption is therefore
# asserted here as hard as the ban itself — and asserted in a file that ALSO contains a
# real violation, so we know the exemption is narrow rather than the gate being dead.
#
# The v3 negative arm exists for the same reason: scheme 3 archives were written when
# the vocabulary was legal, and re-flagging them would turn every legacy archive into a
# permanent red build — which is how a rule gets deleted. `archive_is_legacy_v3()` keys
# on source_inventory.json's own `scheme_version == 3`, and this file checks that the
# leniency is bought ONLY by that explicit declaration: not by an absent inventory, not
# by an unparseable one, not by the string "3" (B4 — a missing declaration must be an
# error of its own, never a free pass).
set -uo pipefail          # NOT -e: several assertions absorb a non-zero exit code
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# gate_settled_wording(patient_dir, errors) — the two-argument signature, confirmed
# against `grep -n "def gate_settled_wording" scripts/validate_structured_outputs.py`.
run_gate() {  # <gate_fn> <patient_dir>
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

# A v4 archive skeleton. Only source_inventory.json matters to this gate (it is what
# archive_is_legacy_v3 reads); the rest of the fixture is whatever the row is about.
mk_archive() {  # <dir> <inventory json>
  local d="$1"
  mkdir -p "$d"
  printf '%s\n' "$2" > "$d/source_inventory.json"
}
INV_V4='{"scheme_version":4,"sources":[]}'
INV_V3='{"scheme_version":3,"sources":[]}'

echo '=== A. the ban — settled_fact / settled_via on a v4 archive is an ERROR ==='

# --- A1. the canonical violation: a settled fact asserted in the delivered timeline ---
d="$tmp/a1"; mk_archive "$d" "$INV_V4"
cat > "$d/timeline.md" <<'EOF'
# 治疗时间线

- 2026-01-08 血常规：白细胞 3.2 ×10^9/L（settled_fact，二读一致）[[src:07_检验报告/血常规-20260108.md]]
- 2026-02-11 胸部 CT：右上叶结节 12mm [[src:05_影像报告/胸部CT-20260211.md]]
EOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "v4 timeline.md carrying settled_fact → ERROR" \
  || no "the retired vocabulary passed on a v4 archive: rc=$rc"
printf '%s' "$out" | grep -qF 'settled_wording:' \
  && ok "…the error is tagged settled_wording:" || no "untagged error: $out"
printf '%s' "$out" | grep -qF 'timeline.md' \
  && ok "…and names the offending file" || no "file not named: $out"
# the message must point at the ONE legal replacement, or whoever hits it will invent
# a second one; A23 says the only legal shape is high_risk_fields[].status
printf '%s' "$out" | grep -qF 'high_risk_fields[].status: passed_independent_reread' \
  && ok "…and points at A23's only legal写法: high_risk_fields[].status: passed_independent_reread" \
  || no "the error does not name the legal replacement: $out"
printf '%s' "$out" | grep -qF 'reread_channel' \
  && ok "…beside its reread_channel (the channel, not the conclusion, is the claim)" \
  || no "the error does not mention reread_channel: $out"
printf '%s' "$out" | grep -qF 'L3' \
  && ok "…and cites the line number so the fix is mechanical" || no "no line citation: $out"

# --- A2. `settled_via` inside a structured JSON ---
d="$tmp/a2"; mk_archive "$d" "$INV_V4"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
(d / "labs.json").write_text(json.dumps({
    "schema_version": "2",
    "labs": [
        {"test_name": "白细胞计数", "raw_value": "3.2", "unit": "×10^9/L",
         "collected_at": "2026-01-08", "source_ref": "[[src:07_检验报告/血常规-20260108.md]]",
         "settled_via": "text_layer"}
    ],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PYEOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "v4 labs.json carrying settled_via → ERROR" \
  || no "settled_via survived in a structured JSON: rc=$rc"
printf '%s' "$out" | grep -qF 'labs.json' \
  && ok "…and the JSON surface is named" || no "labs.json not named: $out"

# --- A3. every formal markdown surface + INDEX.md is in scope ---
# Scope is the point: a banned claim moved from timeline.md to review_summary.md is the
# same claim, and INDEX.md is the first thing a bare session reads.
for f in timeline.md case_text.md review_summary.md review_flags.md INDEX.md; do
  d="$tmp/a3-$f"; mk_archive "$d" "$INV_V4"
  printf '本行声称 settled_fact：白细胞 3.2\n' > "$d/$f"
  run_gate gate_settled_wording "$d"
  [ "$rc" -eq 1 ] && ok "$f is inside the scan surface → ERROR" \
    || no "$f escaped the scan: rc=$rc"
done

# --- A4. dotfile JSON surfaces (the build-side data the HTML renders from) ---
d="$tmp/a4"; mk_archive "$d" "$INV_V4"
printf '{"cards":[{"label":"WBC","note":"settled_via: alternate_vision_model"}]}\n' \
  > "$d/.case_summary_data.json"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok ".case_summary_data.json (dotfile) is inside the scan surface → ERROR" \
  || no "a dotfile JSON escaped the scan: rc=$rc"

# --- A5. multiple hits on one file are counted, not collapsed to the first ---
d="$tmp/a5"; mk_archive "$d" "$INV_V4"
cat > "$d/case_text.md" <<'EOF'
第一处 settled_fact
第二处 settled_via
第三处 settled_fact
第四处 settled_via
EOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "four hits in one file → ERROR" || no "multi-hit file passed: rc=$rc"
printf '%s' "$out" | grep -qF '4 line(s)' \
  && ok "…and the count is reported, so a partial fix is visible as a smaller number" \
  || no "hit count not reported: $out"

echo
echo "=== B. the exemption — open_verification_status: settled stays legal (A16/A23) ==="

# --- B1. the exemption alone ---
d="$tmp/b1"; mk_archive "$d" "$INV_V4"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
(d / "extracted_fields.json").write_text(json.dumps({
    "schema_version": "1",
    "fields": [
        {"label": "标本条码号", "value": "B2026010800317",
         "open_ref": {"source_id": "s-img", "page": 1, "bbox": [0.1, 0.1, 0.3, 0.14]},
         "open_verification_status": "settled"},
        {"label": "送检医师", "value": "（未能辨认）",
         "open_ref": {"source_id": "s-img", "page": 1, "bbox": [0.5, 0.1, 0.7, 0.14]},
         "open_verification_status": "needs_human_review"},
    ],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PYEOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 0 ] && ok "extracted_fields.json open_verification_status: settled → exit 0" \
  || no "the one permitted survivor was flagged: $out"

# --- B2. the exemption is NARROW, not a whitelist of the file ---
# Same file, plus a real violation. If the gate were exempting extracted_fields.json
# wholesale rather than exempting the WORD, this would pass — and the exemption would
# have become a bypass for the most model-written surface in the archive.
d="$tmp/b2"; mk_archive "$d" "$INV_V4"
python3 - "$d" <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
(d / "extracted_fields.json").write_text(json.dumps({
    "schema_version": "1",
    "fields": [
        {"label": "标本条码号", "value": "B2026010800317",
         "open_verification_status": "settled"},
        {"label": "危急值复核", "value": "3.2", "settled_via": "human"},
    ],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PYEOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "…but settled_via in that SAME file still ERRORs (word-scoped, not file-scoped)" \
  || no "extracted_fields.json is being whitelisted wholesale — the exemption is a bypass: rc=$rc"

# --- B3. the bare word `settled` in prose is not the banned token ---
d="$tmp/b3"; mk_archive "$d" "$INV_V4"
printf '患者自述近三月体重 settled，无明显波动。\n' > "$d/case_text.md"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 0 ] && ok "the bare word 'settled' in prose → exit 0 (only the compounds are banned)" \
  || no "the gate fires on the bare word and will be switched off: $out"

# --- B4. a clean v4 archive written the A23 way ---
d="$tmp/b4"; mk_archive "$d" '{"scheme_version":4,"sources":[{"source_id":"s-img","read_mode":"model_vision_primary","high_risk_fields":[{"label":"白细胞计数","status":"passed_independent_reread","reread_channel":"text_layer","readings":[{"channel":"transcribe","value":"3.2"},{"channel":"text_layer","value":"3.2"}]}]}]}'
cat > "$d/timeline.md" <<'EOF'
- 2026-01-08 血常规：白细胞 3.2 ×10^9/L [[src:07_检验报告/血常规-20260108.md]]
EOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 0 ] && ok "a v4 archive recording the reread the A23 way → exit 0" \
  || no "the compliant shape is rejected — this gate refuses everything: $out"

echo
echo "=== C. the v3 negative arm — the vocabulary was LEGAL under scheme 3 ==="

# --- C1. identical content, scheme_version 3 → not checked ---
d="$tmp/c1"; mk_archive "$d" "$INV_V3"
cat > "$d/timeline.md" <<'EOF'
# 治疗时间线

- 2026-01-08 血常规：白细胞 3.2 ×10^9/L（settled_fact，二读一致）[[src:07_检验报告/血常规-20260108.md]]
- 2026-02-11 胸部 CT：右上叶结节 12mm [[src:05_影像报告/胸部CT-20260211.md]]
EOF
run_gate gate_settled_wording "$d"
[ "$rc" -eq 0 ] && ok "the SAME settled_fact under scheme_version 3 → exit 0" \
  || no "a legacy v3 archive was re-flagged; every legacy archive becomes a red build: $out"

# the pair is the whole assertion: byte-identical markdown, opposite verdicts, and the
# only difference is the archive's own scheme declaration
cmp -s "$tmp/a1/timeline.md" "$tmp/c1/timeline.md" \
  && ok "…and the two timeline.md files are byte-identical, so scheme_version is the ONLY variable" \
  || no "the v3/v4 pair drifted apart; the comparison no longer isolates scheme_version"

# --- C2. leniency must be bought by an EXPLICIT 3, per B4 ---
# Each of these is a way an archive could have LOOKED legacy and bought a free pass.
d="$tmp/c2-missing"; mkdir -p "$d"          # no source_inventory.json at all
printf 'settled_fact\n' > "$d/timeline.md"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "no source_inventory.json → NOT legacy, still ERROR (fail-closed)" \
  || no "deleting the inventory bought an exemption: rc=$rc"

d="$tmp/c2-broken"; mk_archive "$d" '{"scheme_version": 3,,,'   # unparseable
printf 'settled_fact\n' > "$d/timeline.md"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "an unparseable source_inventory.json → NOT legacy, still ERROR" \
  || no "a broken inventory bought an exemption — being broken must never be cheaper: rc=$rc"

d="$tmp/c2-string"; mk_archive "$d" '{"scheme_version":"3","sources":[]}'   # string, not int
printf 'settled_fact\n' > "$d/timeline.md"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "scheme_version as the STRING \"3\" → NOT legacy, still ERROR" \
  || no "a stringly-typed scheme_version bought an exemption: rc=$rc"

d="$tmp/c2-absent-key"; mk_archive "$d" '{"sources":[]}'   # B4: absent is an error, not legacy
printf 'settled_fact\n' > "$d/timeline.md"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 1 ] && ok "scheme_version absent → NOT legacy (B4), still ERROR" \
  || no "omitting scheme_version bought an exemption — B4's cheapest bypass is back: rc=$rc"

echo
echo "=== D. scan surface boundaries, pinned so a silent narrowing is visible ==="

# A markdown file that is NOT one of the formal surfaces is out of scope today. This is
# not obviously right — a bucket sidecar is read by humans too — so it is pinned rather
# than assumed, and reported upstream. If the scan is ever widened this assertion flips
# and says so.
d="$tmp/d1"; mk_archive "$d" "$INV_V4"
mkdir -p "$d/07_检验报告"
printf 'settled_fact: 白细胞 3.2\n' > "$d/07_检验报告/血常规-20260108.md"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 0 ] \
  && ok "KNOWN-SCOPE pinned: bucket sidecars are outside the markdown scan (formal surfaces + INDEX.md only)" \
  || ok "SCOPE WIDENED: bucket sidecars are now scanned — update this file's expectation"

# Nested JSON below the archive root is likewise out of scope (the glob is not
# recursive). Same reasoning: pinned, not assumed.
d="$tmp/d2"; mk_archive "$d" "$INV_V4"
mkdir -p "$d/raw/_provenance/run-001"
printf '{"note":"settled_via: human"}\n' > "$d/raw/_provenance/run-001/faithfulness-s1.json"
run_gate gate_settled_wording "$d"
[ "$rc" -eq 0 ] \
  && ok "KNOWN-SCOPE pinned: the JSON glob is root-only, so raw/_provenance/** is not scanned" \
  || ok "SCOPE WIDENED: nested JSON is now scanned — update this file's expectation"

# --- D3. REAL BUG, pinned: dotfile JSONs are scanned twice ---
# gate_settled_wording builds its target list from patient_dir.glob("*.json") AND
# patient_dir.glob(".*.json"). pathlib's glob — unlike the glob module — matches leading
# dots, so "*.json" already returns .case_summary_data.json and the second glob appends
# it again. Every hit in a dotfile is therefore reported twice. It is a duplicate-message
# defect, not a false pass, so it is pinned here rather than patched (tests/** is the only
# writable surface in this work package) and reported upstream.
d="$tmp/d3"; mk_archive "$d" "$INV_V4"
printf '{"note":"settled_via: human"}\n' > "$d/.case_summary_data.json"
run_gate gate_settled_wording "$d"
dup=$(printf '%s\n' "$out" | grep -c 'settled_wording: .case_summary_data.json')
[ "$rc" -eq 1 ] && ok "a dotfile violation still ERRORs (the defect below is cosmetic, not a bypass)" \
  || no "dotfile violation passed: rc=$rc"
if [ "$dup" -eq 2 ]; then
  ok "KNOWN-BUG pinned: the dotfile error is emitted $dup times (pathlib glob('*.json') already matches dotfiles, so the extra .*.json glob double-counts)"
elif [ "$dup" -eq 1 ]; then
  ok "KNOWN-BUG fixed upstream: the dotfile error is now emitted once — drop this pin"
else
  no "unexpected duplicate count for the dotfile error: $dup — $out"
fi
# a non-dotfile is reported exactly once, which is what makes the line above a defect
# rather than the gate's normal behaviour
d="$tmp/d3b"; mk_archive "$d" "$INV_V4"
printf '{"note":"settled_via: human"}\n' > "$d/labs.json"
run_gate gate_settled_wording "$d"
single=$(printf '%s\n' "$out" | grep -c 'settled_wording: labs.json')
[ "$single" -eq 1 ] && ok "…while an ordinary .json is reported exactly once (so the doubling above is the bug)" \
  || no "ordinary JSON reported $single times: $out"

echo
echo "=== E. the gate is actually wired into the validator, not just defined ==="
# A gate that exists but is never called is the most expensive kind of green build.
grep -qE '^\s*gate_settled_wording\(patient_dir, errors\)' "$VAL" \
  && ok "gate_settled_wording is invoked from the validator's gate sequence" \
  || no "gate_settled_wording is defined but never called — B19 is not enforced"

echo
echo "== settled-wording-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
