#!/usr/bin/env bash
# tests/unit/scheme-version-gate.test.sh — organize v3→v4, fix spec B4.
#
# `scheme_version` is the only thing in a patient archive that says WHICH CONTRACT the
# rest of it was written to. Every open-world gate in validate_structured_outputs.py —
# open-domain filing, the clinical_class floors, per-field second-read independence, the
# human spot-check, faithfulness coverage, projection coverage, review-flag audience,
# field provenance, the high-risk denominator reconciliation — reads that one integer
# before deciding whether it applies to this archive at all. So the question this file
# asks is not "is the key present" but "can an archive get a lenient verdict it did not
# ask for, and can it get a strict one it cannot act on".
#
# There are exactly four states, and the failure mode of each is different:
#
#   1. NO DECLARATION. The first draft read silence as 3, which meant deleting one JSON
#      key switched off nine gates at once while the archive still exited 0 with a
#      reassuring legacy WARN. This file asserts the two halves of that fix TOGETHER, in
#      one arm: an undeclared archive ERRORs *and* is handed no `WARN: legacy_archive`.
#      Asserting only the exit code would pass on a build that errored for an unrelated
#      schema reason while still quietly relaxing the archive-level gates; asserting only
#      the WARN would pass on a build that relaxed nothing but let the archive through.
#      Silence has to cost the leniency AND the verdict, or it has bought something.
#
#   2. scheme_version: 3. A real pre-v4 archive is READ against the shape it was written
#      to, WARNed, and passed. That is a grace period, and the WARN is the whole of what
#      separates "readable under the old contract" from "clean".
#
#   3. scheme_version: 4 over rows that are still scheme-3 shaped. This is the state the
#      other two arms cannot describe: the header promises the full contract, the rows
#      cannot answer to it, and the validator's raw output is a dozen unrelated-looking
#      schema violations (`'kind' is a required property`, `'clinical_class' is a
#      required property`, `additional properties are not allowed ('doc_type' ...)`,
#      `projection_coverage is missing`). An operator reading that list concludes the
#      archive is corrupt and starts hand-patching JSON. It is not corrupt — it is ONE
#      unfinished migration wearing a dozen faces, and there is a command that finishes
#      it. So the ERROR must diagnose the state ("HALF-migrated") and name the command,
#      and it must arrive FIRST, before the dozen faces.
#
#   4. …and then the command has to actually work. This is the arm that exists because
#      an error message naming a remedy is a CLAIM, and an unverified claim in an error
#      message is worse than no remedy at all: it sends the one person holding the only
#      copy of a patient's records down a path that may not lead anywhere. Section D does
#      not run a command this test hard-codes. It SCRAPES the command out of the
#      validator's own error text and runs that, so the assertion breaks the day the
#      message drifts from the script — and then re-runs the full validator over the same
#      directory and requires exit 0. Not "fewer errors". Zero.
#
# The negative arms below check the error TEXT, not just the exit code, for the same
# reason: a gate that fails everything passes every exit-code test ever written for it.
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

# --------------------------------------------------------------------------- #
# One fixture, four declarations. The rows are scheme-3 shaped in every arm — no
# `kind`, no `clinical_class`, `doc_type` where v4 wants `doc_kind`, a readiness.json
# still at schema_version "2" with no projection_coverage. That is deliberate: the ONLY
# thing that differs between the arms is the string spliced in at $2, so any difference
# in verdict is attributable to the declaration and to nothing else.
#
# B7: update_log.json is written even though the archive is otherwise pre-v4, because it
# is a REQUIRED product for every archive and a fixture that omits it would fail the
# scheme-3 arm for a reason that has nothing to do with the scheme.
# --------------------------------------------------------------------------- #
mk() {  # <dir> <scheme_version json fragment, may be empty>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/upload-001.txt"
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2",$2"patient_dir":".",
  "generated_at":"2026-01-02T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "doc_type":"出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable",
   "adapter":"text_payload","persist":true} ]}
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
  {"run_id":"run-001","run_mode":"full","started_at":"2026-01-02T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],
   "pii_semantic":"clean","faithfulness_method":"native_text_identity"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

run_val() {  # <dir> -> sets vrc; stderr in $tmp/val.err
  python3 "$VAL" "$1" >"$tmp/val.out" 2>"$tmp/val.err"
  vrc=$?
}

set_scheme() {  # <dir> <int>
  python3 - "$1/source_inventory.json" "$2" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["scheme_version"] = int(sys.argv[2])
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
}

# ===========================================================================
# A. STATE 1 — no scheme_version at all
# ===========================================================================
echo "=== A. undeclared: ERROR, and no relaxation (both, at once) ==="

D="$tmp/undeclared"
mk "$D" ""
run_val "$D"

# The conjunction is the assertion. Either half alone is satisfiable by a build that
# still hands out the leniency this arm exists to deny.
if [ "$vrc" -ne 0 ] && ! grep -q '^WARN: legacy_archive' "$tmp/val.err"; then
  ok "an undeclared archive ERRORs *and* gets NO legacy_archive WARN — silence buys neither a verdict nor a relaxation"
else
  no "undeclared archive: rc=$vrc, legacy_archive WARN present=$(grep -c '^WARN: legacy_archive' "$tmp/val.err") — one half of the B4 fix is missing"
fi
grep -q 'no scheme_version' "$tmp/val.err" \
  && ok "…and the ERROR names the missing DECLARATION as the cause, not the fields it could not check" \
  || no "the undeclared state is not reported as such: $(grep '^ERROR' "$tmp/val.err" | head -1)"
grep -q 'Silence is not a version' "$tmp/val.err" \
  && ok "…saying out loud that an omitted version is not a version" \
  || no "the ERROR does not state the principle it is enforcing"

# archive_is_legacy_v3() is the function every gate consults. The WARN is downstream of
# it, so pin the predicate itself: if this ever returns True for an absent key, the WARN
# assertion above becomes decoration.
python3 - "$ORG" "$D" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
sys.exit(0 if v.archive_is_legacy_v3(pathlib.Path(sys.argv[2])) else 1)
PYEOF
[ $? -ne 0 ] \
  && ok "archive_is_legacy_v3() is False for an absent key — the predicate, not just its WARN" \
  || no "archive_is_legacy_v3() still reads silence as scheme 3"

# ===========================================================================
# B. STATE 2 — scheme_version: 3
# ===========================================================================
echo "=== B. declared scheme 3: WARN + exit 0 ==="

D3="$tmp/three"
mk "$D3" '"scheme_version":3,'
run_val "$D3"
[ "$vrc" -eq 0 ] \
  && ok "the SAME rows declaring scheme_version 3 → exit 0 (the grace period is bought by declaring)" \
  || no "an explicitly declared scheme-3 archive failed, rc=$vrc: $(grep '^ERROR' "$tmp/val.err" | head -1)"
grep -q '^WARN: legacy_archive' "$tmp/val.err" \
  && ok "…and it is WARNed, tagged legacy_archive so the reason is greppable" \
  || no "scheme 3 passed with no legacy_archive WARN — exit 0 now reads as clean"
grep -q 'not a clean bill of health' "$tmp/val.err" \
  && ok "…and the WARN refuses to let exit 0 be read as a clean bill of health" \
  || no "the legacy WARN does not disclaim its own exit 0"

# ===========================================================================
# C. STATE 3 — scheme_version: 4 over rows that cannot answer to it
# ===========================================================================
echo "=== C. declared scheme 4, rows still scheme 3: one migration, not a dozen defects ==="

D4="$tmp/half"
mk "$D4" '"scheme_version":4,'
run_val "$D4"
[ "$vrc" -ne 0 ] \
  && ok "a v4 declaration over v3 rows → non-zero (the leniency is not claimable by asking for the strict contract)" \
  || no "a half-migrated archive passed, rc=$vrc"

# The raw schema output for this state really is a pile of unrelated-looking failures;
# that is the problem being solved, so assert the pile exists before asserting it is
# explained. Otherwise "the diagnosis is first" could pass trivially on an archive that
# produced no other errors at all.
schema_errs=$(grep -c "is a required property\|Additional properties are not allowed" "$tmp/val.err")
[ "$schema_errs" -ge 3 ] \
  && ok "…and it does produce ≥3 raw schema violations ($schema_errs) — the pile this diagnosis exists to explain" \
  || no "the fixture is not actually half-migrated; only $schema_errs raw schema violations"

grep -q 'HALF-migrated' "$tmp/val.err" \
  && ok "…the ERROR diagnoses the STATE (「HALF-migrated」), not the symptoms" \
  || no "no half-migration diagnosis: the operator is left with $schema_errs unrelated schema complaints"
grep -q 'one unfinished migration wearing a dozen faces' "$tmp/val.err" \
  && ok "…and says the violations below are one cause, so nobody hand-patches JSON row by row" \
  || no "the ERROR does not connect the schema violations to a single cause"
grep -q 'still scheme-3 shaped: s1 (no kind/clinical_class)' "$tmp/val.err" \
  && ok "…naming the offending row AND the fields it lacks (a diagnosis has to be checkable)" \
  || no "the half-migration ERROR does not name the row/fields: $(grep 'HALF-migrated' "$tmp/val.err")"
grep -q 'migrate_v3_to_v4.py <patient_dir> --force' "$tmp/val.err" \
  && ok "…and names the remedy with --force, the flag that completes a PARTIAL v4 archive" \
  || no "the ERROR offers no --force remedy: $(grep 'HALF-migrated' "$tmp/val.err")"

# Ordering matters as much as content: gate_scheme_version runs first precisely so the
# diagnosis is not buried under the symptoms it explains.
first_err=$(grep '^ERROR' "$tmp/val.err" | head -1)
case "$first_err" in
  *HALF-migrated*) ok "…and the diagnosis is the FIRST error printed, ahead of the symptoms" ;;
  *) no "the half-migration diagnosis is buried; first error is: ${first_err:0:110}" ;;
esac

# ===========================================================================
# D. STATE 4 — the remedy the ERROR names actually clears the archive
# ===========================================================================
echo "=== D. the named command is a working remedy, not a consoling sentence ==="

# Scraped from the validator's own output, not hard-coded here. If the message ever
# drifts from the script's real interface — a renamed flag, a moved path — this arm
# fails instead of silently testing a command nobody is being told to run.
cmd=$(grep -o 'scripts/migrate_v3_to_v4\.py <patient_dir> --force' "$tmp/val.err" | head -1)
[ -n "$cmd" ] \
  && ok "the remedy is extractable verbatim from the ERROR text" \
  || no "could not scrape a runnable command out of the error message"

real_cmd="${cmd/scripts\//$ORG/scripts/}"
real_cmd="${real_cmd/<patient_dir>/$D4}"
# shellcheck disable=SC2086
python3 $real_cmd >"$tmp/mig.out" 2>&1
mig_rc=$?
[ "$mig_rc" -eq 0 ] \
  && ok "…running exactly that command exits 0" \
  || no "the command the validator told the operator to run failed, rc=$mig_rc: $(cat "$tmp/mig.out")"

run_val "$D4"
[ "$vrc" -eq 0 ] \
  && ok "…and the SAME directory then passes the FULL validator — exit 0, not merely fewer errors" \
  || no "the named remedy did not clear the archive, rc=$vrc: $(grep '^ERROR' "$tmp/val.err" | head -2)"
grep -q 'HALF-migrated' "$tmp/val.err" \
  && no "the half-migration ERROR survived the migration it asked for" \
  || ok "…the half-migration diagnosis is gone (it described a state, and the state changed)"
grep -q '^WARN: legacy_archive' "$tmp/val.err" \
  && no "a migrated v4 archive is still being treated as legacy" \
  || ok "…and the archive is NOT relaxed afterwards: the open-world gates ran and passed"
# What it gained instead is a visible debt, not silence: the migration read no page
# characters, so it records pii_semantic: deferred and says so on every run from here.
grep -q '^WARN: pii_semantic_deferred' "$tmp/val.err" \
  && ok "…exit 0 comes WITH the deferred-PII WARN — the migration's debt is stated, not absorbed" \
  || no "the migrated archive passes silently; the deferred semantic PII pass left no visible debt"

# ===========================================================================
# E. the four states are a CHAIN, walked on one directory
# ===========================================================================
echo "=== E. undeclared → declared 4 → --force → pass, on the same bytes ==="

# The point: declaring the current contract is NOT the fix for silence — it moves the
# archive from "unverdictable" to "half-migrated". Only the migration finishes it. An
# operator who reads the first ERROR and adds `"scheme_version": 4` has done a real,
# necessary step and must not be told they are done.
DC="$tmp/chain"
mk "$DC" ""
run_val "$DC"; rc_a=$vrc
grep -q 'no scheme_version' "$tmp/val.err" && step_a=1 || step_a=0

set_scheme "$DC" 4
run_val "$DC"; rc_b=$vrc
grep -q 'HALF-migrated' "$tmp/val.err" && step_b=1 || step_b=0

python3 "$MIGRATE" "$DC" --force --run-id migrate-chain >/dev/null 2>&1
run_val "$DC"; rc_c=$vrc

[ "$rc_a" -ne 0 ] && [ "$step_a" -eq 1 ] \
  && ok "step 1/3: undeclared → ERROR 「no scheme_version」" \
  || no "step 1/3 did not behave as the undeclared state (rc=$rc_a)"
[ "$rc_b" -ne 0 ] && [ "$step_b" -eq 1 ] \
  && ok "step 2/3: declaring 4 does NOT clear it — it becomes the half-migrated state (a different ERROR)" \
  || no "step 2/3: declaring scheme 4 produced rc=$rc_b without the half-migration diagnosis"
[ "$rc_c" -eq 0 ] \
  && ok "step 3/3: --force finishes it → exit 0 (three distinct states, two distinct fixes)" \
  || no "step 3/3: --force did not clear the chain fixture, rc=$rc_c: $(grep '^ERROR' "$tmp/val.err" | head -1)"

# and the migration is what wrote the v4 fields — not the declaration
python3 - "$DC/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
row = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][0]
missing = [k for k in ("kind", "clinical_class", "doc_kind", "text_layer_kind") if k not in row]
assert not missing, f"still missing {missing}"
assert "doc_type" not in row, "the v3 doc_type key survived the migration"
PYEOF
[ $? -eq 0 ] \
  && ok "…and the row now carries kind / clinical_class / doc_kind / text_layer_kind, with doc_type gone" \
  || no "the chain fixture passed the validator without actually gaining the v4 row fields"

# ---------------------------------------------------------------------------
echo
echo "== scheme-version-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
