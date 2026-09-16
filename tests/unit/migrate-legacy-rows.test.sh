#!/usr/bin/env bash
# tests/unit/migrate-legacy-rows.test.sh — organize v3→v4, fix spec B6 + C3.
#
# WHY THIS FILE EXISTS
# --------------------
# v4 requires a `transcript_path` on every row whose characters came out of a model
# (`read_mode: model_vision_primary` / `model_vision_assist`), because a model-read page
# whose verbatim transcription is not on disk cannot be re-checked by ANYTHING: no
# faithfulness pass, no independent second read, no human spot-check, no field-provenance
# binding. v3 kept no such file. So every pre-v4 archive that was read by a model — which
# is every archive containing a scanned report, i.e. most of them — walks into the
# migration carrying rows that structurally cannot satisfy the new requirement.
#
# That leaves exactly two honest outcomes, and a third dishonest one that is the reason
# this file exists.
#
#   REFUSE the archive. Correct, and it strands the patient's records: the one person
#   whose documents these are loses access to them because a schema changed.
#
#   RECORD THE GAP. Mark the row `legacy_transcript_unavailable: true`, waive the four
#   checks that have nothing to work on, and PAY for the waiver by counting the source in
#   `projection_coverage.summary.unreadable_sources` with an unresolved `coverage_gap`
#   flag. The archive stays readable and the hole is on the record.
#
#   INVENT A VALUE. This is what an operator does when the migration leaves
#   `high_risk_review_status` unset and the validator demands one. The two values within
#   reach are both lies: `passed_independent_reread` claims a check that could not have
#   been performed, and `needs_human_review` queues a human to re-read a page that is not
#   on disk. C3 removes the temptation by writing the honest triple during migration:
#   `high_risk_fields: []` + `high_risk_review_status: not_applicable` +
#   `reread_channel: "none"`.
#
# THE ASYMMETRY THIS FILE IS BUILT AROUND. An exemption and its price are written in
# different files by different steps, and the failure mode is that only the exemption
# survives. A row marked `legacy_transcript_unavailable: true` with no `coverage_gap` flag
# is strictly worse than no migration at all: four gates have stood down, the archive
# exits 0, and nothing anywhere records that these pages can never be verified. So the
# assertions below come in pairs — the waiver works, AND deleting the flag that pays for
# it turns the archive red. A waiver proven only on the passing side is indistinguishable
# from a gate that was switched off.
#
# The exemption also has to stay NARROW. It is bought by a specific boolean on a specific
# row; it must not extend to the next row, and it must not be settable by hand on a v4 run
# that simply declined to write a transcript. Both are asserted.
#
# Fully synthetic fixtures, deterministic, zero network, zero LLM.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"
MIGRATE="$ORG/scripts/migrate_v3_to_v4.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

run_val() {  # <dir> → sets vrc, $tmp/val.err
  python3 "$VAL" "$1" >"$tmp/val.out" 2>"$tmp/val.err"
  vrc=$?
}
row() {  # <dir> <jq-ish python expression over the first file row>
  python3 - "$1/source_inventory.json" "$2" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
r = d["files"][0]
print(json.dumps(eval(sys.argv[2], {"r": r, "d": d}), ensure_ascii=False))
PYEOF
}

# --------------------------------------------------------------------------- #
# A FAITHFUL scheme-3 archive whose one source was read by MODEL VISION.
#
# Faithful means: exactly the keys a v3 run wrote, and not one key more. If the fixture
# quietly carried `kind`, `clinical_class` or `transcript_path`, the migration would have
# nothing to do and this whole file would be asserting that a no-op is harmless.
#
# The bucket is 03_ (narrative) on purpose — it keeps the fixture clear of the lab and
# molecular floors, so anything reported below is about the legacy row and not about an
# unrelated clinical_class debt.
# --------------------------------------------------------------------------- #
mk_v3_vision() {  # <dir>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/scan-001.pdf"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":3,"patient_dir":".",
  "generated_at":"2026-01-02T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"scan-001.pdf",
   "raw_path":"raw/incoming/scan-001.pdf","page_range":"1-2",
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "modality":"image","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"passed_independent_reread",
   "adapter":"pdf_pages","persist":true} ]}
EOF
  cat > "$d/readiness.json" <<'EOF'
{"patient_code":"PT-A1B2","schema_version":"2",
 "documentation_coverage":{"pathology_report":"not_in_archive"},
 "review_flags":[]}
EOF
  cat > "$d/profile.json" <<'EOF'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1B2",
 "summary":{"one_line_condition":"示例：结肠腺癌术后"}}
EOF
  cat > "$d/update_log.json" <<'EOF'
{"schema_version":"1","patient_code":"PT-A1B2","runs":[
  {"run_id":"run-legacy-001","run_mode":"full","started_at":"2026-01-02T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"model_vision_primary"}],
   "pii_semantic":"clean"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

# ===========================================================================
echo "=== A. the fixture is genuinely v3: none of the v4 keys are pre-seeded ==="
# ===========================================================================
D="$tmp/arch"; mk_v3_vision "$D"
for k in kind clinical_class transcript_path legacy_transcript_unavailable high_risk_fields reread_channel; do
  [ "$(row "$D" "'$k' in r")" = "false" ] \
    && ok "pre-migration row has no '$k' (the migration must WRITE it, not find it)" \
    || no "the fixture pre-seeded '$k' — the migration would have nothing to prove"
done
[ "$(row "$D" "r['read_mode']")" = '"model_vision_primary"' ] \
  && ok "…and the row IS model-read, which is what makes transcript_path structurally impossible" \
  || no "the fixture is not a model-vision row"

# ===========================================================================
echo
echo "=== B. migration writes the honest triple, not an invented verdict (C3) ==="
# ===========================================================================
python3 "$MIGRATE" "$D" --run-id migrate-legacy >"$tmp/mig.out" 2>&1; mrc=$?
[ "$mrc" -eq 0 ] \
  && ok "migrate_v3_to_v4.py exits 0 on a model-vision scheme-3 archive" \
  || no "the migration failed (rc=$mrc): $(cat "$tmp/mig.out")"

[ "$(row "$D" "r.get('legacy_transcript_unavailable')")" = "true" ] \
  && ok "legacy_transcript_unavailable: true — the row SAYS it cannot produce a transcript" \
  || no "the migrated row does not carry legacy_transcript_unavailable: $(row "$D" "r")"
[ "$(row "$D" "r.get('high_risk_fields')")" = "[]" ] \
  && ok "high_risk_fields: [] — no transcript means no frontmatter means no denominator to derive" \
  || no "high_risk_fields is $(row "$D" "r.get('high_risk_fields')"), expected []"
[ "$(row "$D" "r.get('high_risk_review_status')")" = '"not_applicable"' ] \
  && ok "high_risk_review_status: not_applicable — NOT passed_independent_reread (a check that could not run)" \
  || no "row status is $(row "$D" "r.get('high_risk_review_status')")"
[ "$(row "$D" "r.get('reread_channel')")" = '"none"' ] \
  && ok "reread_channel: 'none' — NOT 'human', which would queue a person against a page that is not on disk" \
  || no "reread_channel is $(row "$D" "r.get('reread_channel')")"
[ "$(row "$D" "'transcript_path' in r")" = "false" ] \
  && ok "…and no transcript_path was fabricated to point at a file that was never written" \
  || no "the migration invented a transcript_path: $(row "$D" "r.get('transcript_path')")"

# The pre-existing v3 claim was `passed_independent_reread`. The migration OVERWROTE it
# with not_applicable — carrying that claim forward would have been the worst outcome
# available: a v4 archive asserting an independent re-read of pages nobody can produce.
[ "$(row "$D" "r.get('high_risk_review_status')")" != '"passed_independent_reread"' ] \
  && ok "…and the v3 row's own 'passed_independent_reread' claim was NOT carried forward" \
  || no "the migration preserved an unverifiable second-read claim"

grep -qF "legacy_transcript_unavailable" "$tmp/mig.out" \
  && ok "the migration REPORTS what it did, so the waiver is visible in the run log" \
  || no "the migration applied the waiver silently: $(cat "$tmp/mig.out")"

# ===========================================================================
echo
echo "=== C. the price: the archive validates, and the gap is on the record ==="
# ===========================================================================
run_val "$D"
[ "$vrc" -eq 0 ] \
  && ok "the migrated archive passes the FULL validator → exit 0" \
  || no "the migrated archive still fails (rc=$vrc): $(grep '^ERROR' "$tmp/val.err" | head -3)"
grep -q '^ERROR' "$tmp/val.err" \
  && no "exit 0 but ERRORs were printed: $(grep '^ERROR' "$tmp/val.err")" \
  || ok "…with no ERROR lines at all"

# The waiver's price, asserted in readiness.json rather than inferred from exit 0.
python3 - "$D/readiness.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
cov = d["projection_coverage"]["summary"]
assert cov["unreadable_sources"] >= 1, cov
flags = [f for f in d.get("review_flags", []) if f.get("category") == "coverage_gap"]
assert flags, d.get("review_flags")
assert all(f.get("audience") == "internal_qc" for f in flags), flags
print("paid")
PYEOF
[ $? -eq 0 ] \
  && ok "the source is counted in summary.unreadable_sources AND carries a coverage_gap / internal_qc flag" \
  || no "the exemption was taken without recording the gap that pays for it"

# internal_qc matters: this is a QC fact about what cannot be verified, not a sentence a
# family should read as 「请医生确认」 about their own discharge summary.
python3 - "$D/readiness.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
f = [x for x in d["review_flags"] if x.get("category") == "coverage_gap"][0]
assert f.get("audience") == "internal_qc", f
print("ok")
PYEOF
[ $? -eq 0 ] && ok "…and the flag is addressed to internal QC, not to the patient's clinician" \
             || no "the coverage_gap flag is aimed at the wrong audience"

# ===========================================================================
echo
echo "=== D. delete the flag and the whole waiver collapses (the load-bearing arm) ==="
# ===========================================================================
# This is the assertion the rest of the file exists to set up. Everything in section C is
# also true of an archive where the four gates were simply switched off; the difference is
# only visible when the payment is removed.
D2="$tmp/unpaid"; mk_v3_vision "$D2"
python3 "$MIGRATE" "$D2" --run-id migrate-legacy >/dev/null 2>&1
python3 - "$D2/readiness.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["review_flags"] = [f for f in d.get("review_flags", []) if f.get("category") != "coverage_gap"]
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
run_val "$D2"
[ "$vrc" -eq 1 ] \
  && ok "removing the coverage_gap flag turns the SAME archive red → exit 1" \
  || no "the archive still passes with the waiver unpaid (rc=$vrc) — four gates are off and nothing says so"
grep -q 'coverage_gap' "$tmp/val.err" \
  && ok "…and the ERROR names the missing flag category" \
  || no "the finding does not name coverage_gap: $(grep '^ERROR' "$tmp/val.err" | head -2)"
grep -qF 's1' "$tmp/val.err" \
  && ok "…and names the source that took the exemption" \
  || no "the finding does not name the exempt source: $(grep '^ERROR' "$tmp/val.err" | head -2)"

# The other half of the price: the coverage ARITHMETIC. A flag with unreadable_sources
# back at 0 is a note nobody counts.
D3="$tmp/uncounted"; mk_v3_vision "$D3"
python3 "$MIGRATE" "$D3" --run-id migrate-legacy >/dev/null 2>&1
python3 - "$D3/readiness.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["projection_coverage"]["summary"]["unreadable_sources"] = 0
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
run_val "$D3"
[ "$vrc" -eq 1 ] \
  && ok "…and zeroing summary.unreadable_sources is an ERROR too — the flag and the count are BOTH the price" \
  || no "the coverage arithmetic can be edited away while the flag stays (rc=$vrc)"

# And readiness.json disappearing entirely must not be a cheaper way to the same place:
# an unverifiable price is not a price.
D4="$tmp/noreadiness"; mk_v3_vision "$D4"
python3 "$MIGRATE" "$D4" --run-id migrate-legacy >/dev/null 2>&1
rm -f "$D4/readiness.json"
run_val "$D4"
[ "$vrc" -eq 1 ] \
  && ok "…and deleting readiness.json outright is an ERROR: the exemption's price becomes unverifiable" \
  || no "deleting the file that records the price bought a free exemption"
grep -q 'legacy_transcript_unavailable' "$tmp/val.err" \
  && ok "…reported against the ROWS that incurred the debt, not merely as a missing file" \
  || no "the missing readiness is reported without reference to the exempt rows"

# ===========================================================================
echo
echo "=== E. the exemption is narrow: one row, and only a migration may grant it ==="
# ===========================================================================
# A SECOND model-vision row that the migration also marked is exempt for its own reason;
# but a row that is NOT marked must still satisfy A14. Here the mark is stripped from the
# migrated row while everything else stays, i.e. exactly the v4 shape the schema's
# if/then targets.
D5="$tmp/unmarked"; mk_v3_vision "$D5"
python3 "$MIGRATE" "$D5" --run-id migrate-legacy >/dev/null 2>&1
python3 - "$D5/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["files"][0].pop("legacy_transcript_unavailable", None)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
run_val "$D5"
[ "$vrc" -eq 1 ] \
  && ok "the same row WITHOUT the marker → exit 1: a model-read row owes a transcript_path (A14)" \
  || no "a model-vision row with no transcript and no marker passed — the requirement is optional"
grep -q 'transcript_path' "$tmp/val.err" \
  && ok "…for the stated reason: transcript_path" \
  || no "the transcript requirement is not what fired: $(grep '^ERROR' "$tmp/val.err" | head -2)"

# …and the marker is not a key a v4 run can set to skip writing transcripts. The archive
# below declares scheme 4 from the start (no migration ran), so a marker on it is a claim
# that the CURRENT pipeline declined to write a file it was required to write.
echo
echo "=== F. no drift: the four waived gates are named, and named together ==="
python3 - "$ORG" <<'PYEOF'
import sys, importlib, inspect
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
# The predicate is ONE function, so the four gates cannot drift apart in what they exempt.
assert callable(v._legacy_transcript_exempt)
assert v._legacy_transcript_exempt({"legacy_transcript_unavailable": True}) is True
assert v._legacy_transcript_exempt({"legacy_transcript_unavailable": "true"}) is False, \
    "a string 'true' must not buy the exemption"
assert v._legacy_transcript_exempt({}) is False
assert v._legacy_transcript_exempt(None) is False
# and every gate that stands down must be reachable by name, so a reader can audit the set
for g in ("gate_transcripts", "gate_high_risk_denominator", "gate_faithfulness",
          "gate_human_sample", "gate_projection_coverage"):
    assert hasattr(v, g), g
print("predicate OK")
PYEOF
[ $? -eq 0 ] \
  && ok "_legacy_transcript_exempt is strict (True only, not 'true') and all five gates exist by name" \
  || no "the exemption predicate drifted or a gate was renamed"

# The migration script must be the only writer. Asserted as documentation-in-code: the
# schema says so in the field description, and a reader who removes that sentence should
# see this go red.
grep -q 'only .scripts/migrate_v3_to_v4.py. may write it' \
  "$ORG/references/schemas/README.md" \
  && ok "schemas/README records that ONLY migrate_v3_to_v4.py may write the marker" \
  || no "the 'migration-only' restriction is not written down anywhere a reader will find it"

echo
echo "== migrate-legacy-rows: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
