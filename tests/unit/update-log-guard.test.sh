#!/usr/bin/env bash
# tests/unit/update-log-guard.test.sh — organize v3→v4, fix spec B7 + H2 (+ the
# gate_settled_wording de-duplication that shipped alongside them).
#
# WHY THIS FILE EXISTS
# --------------------
# `update_log.json` is how an archive says how it came to be. It is the ONLY place that
# records which run added which sources, whether the semantic PII pass actually ran, and
# what verification backed it. Two independent readers depend on it: the validator, which
# audits the deferral; and `export_share.py`, which refuses to let an archive with an
# unpaid PII debt leave the vault. A6 makes that second check deliberately INDEPENDENT —
# export must refuse on its own evidence, because the operator who exports is not always
# the operator who last ran the validator.
#
# B7 closed the first hole: a MISSING update_log.json used to skip the gate and return
# `None` out of the export check, so deleting one file bought an unconditional export. The
# cheapest possible bypass, wearing the costume of backward compatibility.
#
# H2 closed the two that survived it, and they are the same defect in two spellings: an
# archive that says NOTHING is treated as an archive that says CLEAN.
#
#   `runs: []` — a well-formed file with an empty history. Every archive was built by at
#   least one run, so an empty history is not a history of doing nothing; it is the
#   absence of the record. It also reproduces the deleted-file effect exactly: no deferred
#   pass to find, no run_mode for export to anchor on, nothing for a later incremental run
#   to short-circuit against. An operator blocked by the missing-file error could write
#   `{"runs": []}` and be through.
#
#   a run with no `pii_semantic` key — a run that did work and recorded no verdict about
#   it. Omitting the key used to skip every check below it: the deferral legality test, the
#   fail-closed test, the readiness reconciliation. So a run that simply did not say was
#   CHEAPER than one that honestly said "deferred", and cheaper than one that said
#   "failed". Any rule that makes silence cheaper than disclosure will be satisfied with
#   silence.
#
# THE PROPERTY THIS FILE IS BUILT AROUND: both readers must refuse, SEPARATELY. A6 is not
# satisfied by "the validator catches it" — export_share.py must reach the same verdict
# from the same file without the validator's help, and this file drives the export path
# with the structural acceptance gate stubbed TRUE so an exit 1 there can only have come
# from its own retrospection. Every refusal is paired with its negative arm: the minimal
# repair of the same archive must export, or the assertions prove only that the gate is
# broken in the safe direction.
#
# The third section is unrelated in subject and identical in kind. `gate_settled_wording`
# globbed both `*.json` and `.*.json`; pathlib's `*.json` already matches leading-dot
# names (fnmatch has no hidden-file rule), so `.case_summary_data.json` was collected
# TWICE and every hit in it printed twice. A duplicated ERROR is not a harsher gate, it is
# a MISCOUNT: it makes one defect look like two and sends a reader hunting for a second
# occurrence that does not exist. It belongs here because it is the same class of failure
# as the two above — the archive's own bookkeeping saying something that is not so.
#
# Fully synthetic fixtures, deterministic, zero network, zero LLM.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
EXPORT="$ORG/scripts/export_share.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# The validator gate, in isolation: (patient_dir, errors, warnings).
run_gate() {  # <patient_dir> → sets $rc, $errs, $warns
  local o
  o="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib, json
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errors, warnings = [], []
v.gate_update_log_provenance(pathlib.Path(sys.argv[2]), errors, warnings)
print(json.dumps({"errors": errors, "warnings": warnings}, ensure_ascii=False))
PYEOF
)"
  errs="$(python3 -c "import json,sys;print('\n'.join(json.loads(sys.argv[1])['errors']))" "$o")"
  warns="$(python3 -c "import json,sys;print('\n'.join(json.loads(sys.argv[1])['warnings']))" "$o")"
  [ -n "$errs" ] && rc=1 || rc=0
}

# The export path, with the structural acceptance gate stubbed TRUE so the ONLY thing that
# can refuse is export's own A6/B7 retrospection.
export_rc() {  # <patient_dir> <dest> → sets $xrc, $out
  out="$(python3 - "$EXPORT" "$1" "$2" 2>&1 <<'PYEOF'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m._run_acceptance_gate = lambda p: True
sys.exit(m.export_share(
    pathlib.Path(sys.argv[2]).resolve(), pathlib.Path(sys.argv[3]).resolve(),
    ["profile.json"], recipient="省人民医院 MDT", purpose="second opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-2026-09-16"))
PYEOF
)"
  xrc=$?
}

arch() {  # <dir> <update_log body>
  rm -rf "$1"; mkdir -p "$1"
  printf '{"patient_code":"PT-0E11"}\n' > "$1/profile.json"
  printf '%s\n' "$2" > "$1/update_log.json"
}

FULL_CLEAN='{"run_id":"run-001","run_mode":"full","started_at":"2026-09-16T00:00:00Z","added_sources":[{"source_id":"s1","read_mode":"native_text"}],"pii_semantic":"clean","faithfulness_method":"native_text_identity"}'
FULL_SILENT='{"run_id":"run-silent","run_mode":"full","started_at":"2026-09-16T00:00:00Z","added_sources":[{"source_id":"s1","read_mode":"model_vision_primary"}]}'

# ===========================================================================
echo "=== A. runs: [] — a well-formed file with no history ==="
# ===========================================================================
D="$tmp/empty"; arch "$D" '{"schema_version":"1","patient_code":"PT-0E11","runs":[]}'

run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "the VALIDATOR errors on an empty runs[] (H2)" \
  || no "an empty runs[] passed the validator — emptying the array reproduces the deleted-file bypass"
grep -qF "no runs recorded" <<<"$errs" \
  && ok "…with the message 「no runs recorded」, which says what is absent rather than what is malformed" \
  || no "the empty-history error does not name itself: $errs"
grep -qF "EMPTY" <<<"$errs" \
  && ok "…and says the array is EMPTY, distinguishing it from a missing file" \
  || no "the error does not distinguish empty from missing: $errs"
grep -qF "export_share.py" <<<"$errs" \
  && ok "…and names the downstream reader that has nothing to anchor on" \
  || no "the error does not explain the downstream consequence: $errs"

export_rc "$D" "$tmp/out_empty"
[ "$xrc" -eq 1 ] \
  && ok "EXPORT refuses the same archive, independently (A6: not via the aggregate gate)" \
  || no "export accepted an archive with no recorded runs (rc=$xrc) — the two readers disagree"
printf '%s' "$out" | grep -qF "no runs recorded" \
  && ok "…for the same stated reason, so the two refusals are recognisably the same finding" \
  || no "export refused for a different reason: $out"
[ ! -e "$tmp/out_empty" ] \
  && ok "…and the destination was never created — a refusal that has already copied is not a refusal" \
  || no "the destination directory exists despite the refusal"

# NEGATIVE ARM — one real run, and both readers clear it.
D="$tmp/onerun"; arch "$D" "{\"schema_version\":\"1\",\"patient_code\":\"PT-0E11\",\"runs\":[$FULL_CLEAN]}"
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "negative arm: ONE recorded clean run → the validator is silent" \
  || no "the control archive errored: $errs"
export_rc "$D" "$tmp/out_onerun"
[ "$xrc" -eq 0 ] && [ -f "$tmp/out_onerun/profile.json" ] \
  && ok "…and it exports, writing its payload — the refusals above were bought by the emptiness" \
  || no "the control archive could not be exported (rc=$xrc): $out"

# The empty-runs error must NOT short-circuit the rest of the gate. The
# faithfulness_method scan below it does not read runs[] at all, and bailing out would let
# an empty array switch off a check that has nothing to do with it — the same silent-skip
# shape the error exists to stop.
D="$tmp/empty_badmethod"; arch "$D" '{"schema_version":"1","patient_code":"PT-0E11","runs":[]}'
mkdir -p "$D/raw/_provenance/r1"
printf '{"faithfulness_method":"vibes_based_verification","fields":[]}\n' \
  > "$D/raw/_provenance/r1/faithfulness-s1.json"
run_gate "$D"
n_err=$(printf '%s\n' "$errs" | grep -c .)
[ "$n_err" -ge 2 ] \
  && ok "an empty runs[] does not short-circuit the gate: the faithfulness scan still ran ($n_err findings)" \
  || no "the empty-runs error returned early and silenced an unrelated check: $errs"

# ===========================================================================
echo
echo "=== B. a run with no pii_semantic — silence must not be cheaper than disclosure ==="
# ===========================================================================
D="$tmp/silent"; arch "$D" "{\"schema_version\":\"1\",\"patient_code\":\"PT-0E11\",\"runs\":[$FULL_SILENT]}"

run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "the VALIDATOR errors on a run that omits pii_semantic (H2)" \
  || no "a run with no PII verdict passed — omitting the key is cheaper than saying 'deferred'"
grep -qF "run-silent" <<<"$errs" \
  && ok "…naming the run that said nothing" || no "the silent run is not named: $errs"
grep -qF "no pii_semantic" <<<"$errs" \
  && ok "…and the key it owes" || no "the missing key is not named: $errs"
grep -qF "clean" <<<"$errs" && grep -qF "deferred" <<<"$errs" && grep -qF "failed" <<<"$errs" \
  && ok "…and enumerates the three legal answers, so the fix is unambiguous" \
  || no "the error does not list the closed state vocabulary: $errs"

export_rc "$D" "$tmp/out_silent"
[ "$xrc" -eq 1 ] \
  && ok "EXPORT refuses it too, independently" \
  || no "export cleared a run that recorded no PII verdict (rc=$xrc)"
printf '%s' "$out" | grep -qF "run-silent" \
  && ok "…naming the same run" || no "export's refusal does not name the run: $out"
printf '%s' "$out" | grep -qF "pii_semantic" \
  && ok "…and the same key" || no "export's refusal does not name the key: $out"
[ ! -e "$tmp/out_silent" ] \
  && ok "…with the destination untouched" || no "the destination was created despite the refusal"

# NEGATIVE ARM — the identical run with the verdict filled in. The key is the whole
# difference: same run_id, same run_mode, same sources.
D="$tmp/silent_fixed"
arch "$D" "{\"schema_version\":\"1\",\"patient_code\":\"PT-0E11\",\"runs\":[$(printf '%s' "$FULL_SILENT" | python3 -c 'import json,sys; r=json.load(sys.stdin); r["pii_semantic"]="clean"; print(json.dumps(r))')]}"
run_gate "$D"
[ "$rc" -eq 0 ] \
  && ok "negative arm: the SAME run carrying pii_semantic: clean → the validator is silent" \
  || no "the repaired run still errors: $errs"
export_rc "$D" "$tmp/out_silent_fixed"
[ "$xrc" -eq 0 ] \
  && ok "…and it exports — one key is the entire difference" \
  || no "the repaired run was still refused (rc=$xrc): $out"

# SILENCE IS ITS OWN VERDICT, not an alias for 'deferred'. If the two ever print the same
# message, an operator reading the refusal goes looking for a PII pass that was never
# skipped — it was never recorded.
D="$tmp/deferred"
arch "$D" "{\"schema_version\":\"1\",\"patient_code\":\"PT-0E11\",\"runs\":[$(printf '%s' "$FULL_SILENT" | python3 -c 'import json,sys; r=json.load(sys.stdin); r["pii_semantic"]="deferred"; print(json.dumps(r))')]}"
export_rc "$D" "$tmp/out_deferred"
[ "$xrc" -eq 1 ] && ok "a run that says 'deferred' is also refused (the debt is real)" \
                 || no "a deferred full run exported: $out"
printf '%s' "$out" | grep -qF "deferred" \
  && ok "…as a DEFERRAL…" || no "the deferred refusal changed shape: $out"
printf '%s' "$out" | grep -qF "no pii_semantic" \
  && no "the deferred refusal now prints the silent-run message — the two verdicts merged" \
  || ok "…and not as a silent run: 「nothing recorded」 and 「recorded as owed」 stay distinct"

# ===========================================================================
echo
echo "=== C. the closed vocabulary: a fourth state is not a state ==="
# ===========================================================================
D="$tmp/bogus"
arch "$D" "{\"schema_version\":\"1\",\"patient_code\":\"PT-0E11\",\"runs\":[$(printf '%s' "$FULL_SILENT" | python3 -c 'import json,sys; r=json.load(sys.stdin); r["pii_semantic"]="mostly_clean"; print(json.dumps(r))')]}"
run_gate "$D"
[ "$rc" -eq 1 ] \
  && ok "pii_semantic: 'mostly_clean' is an ERROR — the state vocabulary is closed" \
  || no "an invented PII state was accepted: a fourth value is an unreviewable claim"
grep -qF "mostly_clean" <<<"$errs" \
  && ok "…quoting the value it refused" || no "the invalid value is not quoted: $errs"

# and the two malformed shapes that must not read as 'nothing to check'
D="$tmp/runsobj"; arch "$D" '{"schema_version":"1","patient_code":"PT-0E11","runs":{}}'
run_gate "$D"
[ "$rc" -eq 1 ] && ok "runs as an OBJECT is an ERROR (a non-list silently removes every check below it)" \
               || no "runs:{} passed the validator"
export_rc "$D" "$tmp/out_runsobj"
[ "$xrc" -eq 1 ] && ok "…and export refuses it too" || no "export accepted runs:{}"

D="$tmp/norunskey"; arch "$D" '{"schema_version":"1","patient_code":"PT-0E11"}'
run_gate "$D"
[ "$rc" -eq 1 ] && ok "an absent runs key is an ERROR" || no "a log with no runs key passed"
export_rc "$D" "$tmp/out_norunskey"
[ "$xrc" -eq 1 ] && ok "…and export refuses it too" || no "export accepted a log with no runs key"

# ===========================================================================
echo
echo "=== D. gate_settled_wording reports .case_summary_data.json exactly ONCE ==="
# ===========================================================================
# pathlib's `*.json` already matches leading-dot names — fnmatch has no hidden-file rule —
# so globbing `.*.json` as well collected the file twice and printed every hit twice.
run_settled() {  # <patient_dir> → sets $srrc, $serrs
  local o
  o="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib, json
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_settled_wording(pathlib.Path(sys.argv[2]), errs)
print(json.dumps(errs, ensure_ascii=False))
PYEOF
)"
  serrs="$(python3 -c "import json,sys;print('\n'.join(json.loads(sys.argv[1])))" "$o")"
}

D="$tmp/settled"; mkdir -p "$D"
printf '{"schema":"source_inventory_v2","scheme_version":4,"files":[]}\n' > "$D/source_inventory.json"
cat > "$D/.case_summary_data.json" <<'EOF'
{
  "labs": [
    {"label": "白细胞计数", "settled_fact": true, "settled_via": "text_layer"}
  ]
}
EOF
run_settled "$D"
n=$(printf '%s\n' "$serrs" | grep -c 'case_summary_data.json' || true)
[ "$n" -eq 1 ] \
  && ok ".case_summary_data.json is reported EXACTLY once (not twice: a duplicate is a miscount, not a harsher gate)" \
  || no "the leading-dot file was reported $n time(s) — one defect is being shown as $n"
grep -qF "settled_fact" <<<"$serrs" \
  && ok "…and the finding names the retired token it found" || no "the banned token is not named: $serrs"

# The count inside the single finding must be the real number of lines, not doubled.
grep -qF "1 line(s)" <<<"$serrs" \
  && ok "…and reports 1 line(s): the per-file hit count is not doubled either" \
  || no "the hit count inside the finding is wrong: $serrs"

# A NON-dot file must still be reported — once. Without this, the de-duplication could
# have been achieved by dropping the leading-dot glob and losing the hidden file entirely.
D="$tmp/settled_plain"; mkdir -p "$D"
printf '{"schema":"source_inventory_v2","scheme_version":4,"files":[]}\n' > "$D/source_inventory.json"
printf '{"labs":[{"label":"WBC","settled_via":"human"}]}\n' > "$D/labs.json"
run_settled "$D"
n=$(printf '%s\n' "$serrs" | grep -c 'labs.json' || true)
[ "$n" -eq 1 ] && ok "an ordinary labs.json is reported exactly once too" \
              || no "labs.json was reported $n time(s)"

# BOTH files at once: two distinct files, two findings, neither doubled.
D="$tmp/settled_both"; mkdir -p "$D"
printf '{"schema":"source_inventory_v2","scheme_version":4,"files":[]}\n' > "$D/source_inventory.json"
printf '{"labs":[{"settled_fact":true}]}\n' > "$D/.case_summary_data.json"
printf '{"labs":[{"settled_via":"human"}]}\n' > "$D/labs.json"
run_settled "$D"
total=$(printf '%s\n' "$serrs" | grep -c 'settled_wording:' || true)
[ "$total" -eq 2 ] \
  && ok "two offending files → exactly two findings (the dot-file is still SEEN, just not twice)" \
  || no "expected 2 findings across two files, got $total: $serrs"

# NEGATIVE ARM — the one legal survivor must not be matched. extracted_fields.json's
# `open_verification_status: settled` means 「this OPEN field's two reads agreed」, which
# is A16's deliberate carve-out; matching the bare word would fire on the contract itself.
D="$tmp/settled_legal"; mkdir -p "$D"
printf '{"schema":"source_inventory_v2","scheme_version":4,"files":[]}\n' > "$D/source_inventory.json"
printf '{"fields":[{"label":"血压","open_verification_status":"settled"}]}\n' \
  > "$D/extracted_fields.json"
run_settled "$D"
[ -z "$serrs" ] \
  && ok "negative arm: open_verification_status: settled is NOT matched (A16's permitted survivor)" \
  || no "the gate fired on the one legal use of the word: $serrs"

# …and a clean archive produces nothing at all, so section D is not satisfied by a gate
# that reports every file it opens.
D="$tmp/settled_clean"; mkdir -p "$D"
printf '{"schema":"source_inventory_v2","scheme_version":4,"files":[]}\n' > "$D/source_inventory.json"
printf '{"labs":[{"label":"WBC","value":"3.21"}]}\n' > "$D/labs.json"
printf '{"labs":[{"label":"WBC","value":"3.21"}]}\n' > "$D/.case_summary_data.json"
run_settled "$D"
[ -z "$serrs" ] && ok "…and a clean archive yields no findings at all" || no "unexpected findings: $serrs"

echo
echo "== update-log-guard: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
