#!/usr/bin/env bash
# tests/unit/migrate-force-noop.test.sh — organize v3→v4, fix spec C4 (+ B4, B5).
#
# WHY THIS FILE EXISTS
# --------------------
# B4 gave `migrate_v3_to_v4.py` a `--force` flag so a HALF-migrated archive — one that
# declares `scheme_version: 4` while some row still lacks `kind` / `clinical_class` — can
# be completed in place instead of being rejected forever. The validator's own error text
# tells the operator to run it. That makes `--force` a command people are INSTRUCTED to
# run against archives they have not inspected, which is exactly the situation where
# "what does it do when there is nothing to do?" stops being an academic question.
#
# The first implementation had no answer, and the failure was self-amplifying. The PII
# deferral flag was appended during the readiness pass, i.e. BEFORE the completeness
# verdict was taken, so `notes` was never empty, the no-op branch was unreachable, and
# every `--force` on a FINISHED archive:
#
#   * rewrote source_inventory.json and readiness.json (touching files it had no change
#     to make to — and a rewritten file is a file whose mtime, and any external integrity
#     record, now disagrees with its content history);
#   * stacked another `run_mode: "migration"` entry onto update_log.json, recording a
#     migration that nobody performed and that converted nothing;
#   * re-wrote the `pii_semantic_deferred` flag and a `pii_semantic: "deferred"` run —
#     which, by B5/B7, RE-BLOCKS EXPORT.
#
# That last one is the sharp edge. An operator who runs the command the validator
# recommends, on an archive that is already correct, LOSES the ability to export it. And
# the remedy for a deferred PII pass is to run the semantic pass again, which produces a
# clean run, after which running `--force` once more defers it again. The tool the
# operator was told to reach for is the thing breaking the archive, and running it more
# does not converge.
#
# C4 fixes it by moving the completeness verdict ahead of every migration-shaped write:
# a complete v4 archive produces no notes, and no notes means no writes, no run, no flag,
# exit 0 with "nothing to do".
#
# HOW THIS FILE ASSERTS IT. "No-op" is a claim about the WHOLE archive, not about the two
# files the script happens to touch, so the positive arm takes a checksum of every file in
# the tree and compares the full manifest byte for byte. A test that only re-read
# source_inventory.json would pass against a script that rewrote readiness.json,
# update_log.json or AGENTS.md — and update_log.json is the file whose growth causes the
# export failure. The export check is then run FOR REAL, before and after, because
# "update_log did not change" and "the archive can still leave the vault" are different
# claims and it is the second one the patient cares about.
#
# And the negative arm matters just as much: a script that detects "complete" by refusing
# to do anything is not a fix, it is a broken tool with good manners. So the same command,
# on an archive missing ONE v4 key, must write that key and record exactly one new run.
#
# Fully synthetic fixtures, deterministic, zero network, zero LLM.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
MIGRATE="$ORG/scripts/migrate_v3_to_v4.py"
VAL="$ORG/scripts/validate_structured_outputs.py"
EXPORT="$ORG/scripts/export_share.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# --------------------------------------------------------------------------- #
# A COMPLETE v4 archive, written by hand rather than produced by a migration.
#
# Hand-written on purpose: an archive produced by `migrate_v3_to_v4.py` carries a
# migration run with `pii_semantic: "deferred"`, so its export is legitimately blocked
# and the before/after export comparison below would be comparing two refusals. The
# fixture has to be an archive an operator could actually export, or the sharpest
# consequence of the bug is invisible.
# --------------------------------------------------------------------------- #
mk_v4() {  # <dir>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/upload-001.txt"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "kind":"known","doc_kind":"出院小结","clinical_class":"narrative",
   "text_layer_kind":"not_applicable",
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable",
   "adapter":"text_payload","persist":true} ]}
EOF
  cat > "$d/readiness.json" <<'EOF'
{"patient_code":"PT-A1B2","schema_version":"3",
 "documentation_coverage":{"pathology_report":"not_in_archive"},
 "projection_coverage":{
   "per_source":[{"source_id":"s1","unprojected_field_classes":[]}],
   "summary":{"sources_total":1,"sources_fully_projected":1,
              "novel_sources":0,"unreadable_sources":0}},
 "review_flags":[]}
EOF
  cat > "$d/profile.json" <<'EOF'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1B2",
 "summary":{"one_line_condition":"示例：结肠腺癌术后"}}
EOF
  cat > "$d/update_log.json" <<'EOF'
{"schema_version":"1","patient_code":"PT-A1B2","runs":[
  {"run_id":"run-001","run_mode":"full","started_at":"2026-09-16T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],
   "pii_semantic":"clean","faithfulness_method":"native_text_identity"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

# Every file in the tree, with its digest. `find -type f` and not just the two JSON files
# the script is known to touch — the point is what it did NOT touch.
tree_sum() {  # <dir> → sorted "<sha> <relpath>" lines
  ( cd "$1" && find . -type f | LC_ALL=C sort | while read -r f; do
      printf '%s  %s\n' "$(shasum -a 256 "$f" | awk '{print $1}')" "$f"
    done )
}
n_runs() {  # <dir>
  python3 -c "import json,sys;print(len(json.load(open(sys.argv[1],encoding='utf-8'))['runs']))" \
    "$1/update_log.json"
}
run_ids() {  # <dir>
  python3 -c "import json,sys;print(','.join(r.get('run_id','?') for r in json.load(open(sys.argv[1],encoding='utf-8'))['runs']))" \
    "$1/update_log.json"
}
# the REAL export path, with the structural acceptance gate stubbed true so the only
# thing that can refuse is the A6/B7 PII retrospection
export_rc() {  # <patient_dir> <dest> → sets $rc, $out
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
  rc=$?
}

# ===========================================================================
echo "=== A. the fixture really is a complete, exportable v4 archive ==="
# ===========================================================================
D="$tmp/complete"; mk_v4 "$D"
python3 "$VAL" "$D" >"$tmp/v0.out" 2>"$tmp/v0.err"; vrc=$?
[ "$vrc" -eq 0 ] \
  && ok "the hand-written v4 archive passes the validator (exit 0) BEFORE any --force" \
  || no "the fixture is not a valid v4 archive: $(grep '^ERROR' "$tmp/v0.err" | head -3)"
export_rc "$D" "$tmp/exp_before"
[ "$rc" -eq 0 ] \
  && ok "…and it EXPORTS (exit 0): there is something real to lose" \
  || no "the fixture could not be exported even before --force: $out"
[ "$(n_runs "$D")" -eq 1 ] \
  && ok "…with exactly one recorded run" || no "fixture has $(n_runs "$D") runs, expected 1"

# ===========================================================================
echo
echo "=== B. --force on a complete archive changes NOTHING (C4) ==="
# ===========================================================================
tree_sum "$D" > "$tmp/before.sums"
before_runs="$(run_ids "$D")"

python3 "$MIGRATE" "$D" --run-id force-noop-1 >"$tmp/f1.out" 2>&1; frc=$?
[ "$frc" -eq 0 ] && ok "…is a no-op even WITHOUT --force (scheme is already 4) → exit 0" \
                 || no "a plain run on a v4 archive failed (rc=$frc): $(cat "$tmp/f1.out")"

python3 "$MIGRATE" "$D" --force --run-id force-noop-2 >"$tmp/f2.out" 2>&1; frc=$?
[ "$frc" -eq 0 ] \
  && ok "--force on a complete v4 archive exits 0" \
  || no "--force failed on a complete archive (rc=$frc): $(cat "$tmp/f2.out")"
grep -qF "nothing to do" "$tmp/f2.out" \
  && ok "…and SAYS nothing to do, so the operator is not left guessing what it changed" \
  || no "--force did not report a no-op: $(cat "$tmp/f2.out")"

tree_sum "$D" > "$tmp/after.sums"
if diff -u "$tmp/before.sums" "$tmp/after.sums" > "$tmp/tree.diff"; then
  ok "EVERY file in the tree is byte-identical after --force (whole-tree digest, not just the two JSONs)"
else
  no "--force modified the archive: $(head -20 "$tmp/tree.diff")"
fi
[ "$(n_runs "$D")" -eq 1 ] \
  && ok "…update_log.json still has exactly ONE run — no phantom migration was recorded" \
  || no "--force stacked a migration run: runs=$(n_runs "$D") ($(run_ids "$D"))"
[ "$(run_ids "$D")" = "$before_runs" ] \
  && ok "…and the run ids are unchanged, in order" || no "run ids changed: $(run_ids "$D")"

python3 - "$D/readiness.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
bad = [f for f in (d.get("review_flags") or [])
       if isinstance(f, dict) and f.get("category") == "pii_semantic_deferred"]
sys.exit(1 if bad else 0)
PYEOF
[ $? -eq 0 ] \
  && ok "…and NO pii_semantic_deferred flag was minted (the flag that re-blocks export)" \
  || no "--force wrote a PII deferral onto a complete archive"

# THE CONSEQUENCE, checked for real rather than inferred from the run count.
export_rc "$D" "$tmp/exp_after"
[ "$rc" -eq 0 ] \
  && ok "the archive STILL EXPORTS after --force — running the recommended command did not cost the operator the export" \
  || no "--force on a complete archive broke export (rc=$rc): $out"
[ -f "$tmp/exp_after/profile.json" ] \
  && ok "…and the export actually wrote its payload (not a silent zero exit)" \
  || no "export reported success but wrote nothing"

python3 "$VAL" "$D" >"$tmp/v1.out" 2>"$tmp/v1.err"
[ $? -eq 0 ] && ok "…and the archive still validates" \
             || no "--force broke validation: $(grep '^ERROR' "$tmp/v1.err" | head -3)"

# Idempotence under repetition: an operator who is unsure often runs a command twice.
python3 "$MIGRATE" "$D" --force --run-id force-noop-3 >/dev/null 2>&1
python3 "$MIGRATE" "$D" --force --run-id force-noop-4 >/dev/null 2>&1
tree_sum "$D" > "$tmp/after4.sums"
diff -q "$tmp/before.sums" "$tmp/after4.sums" >/dev/null \
  && ok "three further --force runs still change nothing — the no-op does not drift" \
  || no "repeated --force runs accumulated changes: $(diff "$tmp/before.sums" "$tmp/after4.sums" | head)"
[ "$(n_runs "$D")" -eq 1 ] \
  && ok "…and update_log still has one run after FOUR migration invocations" \
  || no "runs grew to $(n_runs "$D") across repeated no-ops"

# ===========================================================================
echo
echo "=== C. the negative arm: one missing v4 key, and --force does its job ==="
# ===========================================================================
# Without this, section B is satisfied by a --force that never does anything at all —
# a tool the validator tells people to run and which cannot fix what it was named for.
D2="$tmp/partial"; mk_v4 "$D2"
python3 - "$D2/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
del d["files"][0]["clinical_class"]          # exactly ONE v4 key, nothing else touched
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF

# the state B4 describes: a header claiming scheme 4 over a row that cannot answer to it
python3 "$VAL" "$D2" >"$tmp/p0.out" 2>"$tmp/p0.err"; prc=$?
[ "$prc" -eq 1 ] \
  && ok "the half-migrated archive is an ERROR before --force (B4)" \
  || no "a row missing clinical_class validated (rc=$prc)"
grep -q -- '--force' "$tmp/p0.err" \
  && ok "…and the error names --force as the remedy, which is why the no-op above matters" \
  || no "the validator does not point at --force: $(grep '^ERROR' "$tmp/p0.err" | head -2)"

runs_before=$(n_runs "$D2")
python3 "$MIGRATE" "$D2" --force --run-id force-fix >"$tmp/f5.out" 2>&1; frc=$?
[ "$frc" -eq 0 ] && ok "--force on the partial archive exits 0" \
                 || no "--force failed on a partial archive (rc=$frc): $(cat "$tmp/f5.out")"
grep -qF "nothing to do" "$tmp/f5.out" \
  && no "--force reported 'nothing to do' on an archive that WAS missing a key" \
  || ok "…and does NOT claim 'nothing to do' — it distinguishes complete from incomplete"

[ "$(python3 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['files'][0].get('clinical_class'))" "$D2/source_inventory.json")" = "narrative" ] \
  && ok "…the missing clinical_class was filled deterministically from the bucket number (03_ → narrative)" \
  || no "--force did not fill clinical_class"

runs_after=$(n_runs "$D2")
[ "$runs_after" -eq $((runs_before + 1)) ] \
  && ok "…and recorded EXACTLY ONE new run ($runs_before → $runs_after)" \
  || no "run count went $runs_before → $runs_after, expected +1"
python3 - "$D2/update_log.json" <<'PYEOF'
import json, sys
runs = json.load(open(sys.argv[1], encoding="utf-8"))["runs"]
last = runs[-1]
assert last["run_mode"] == "migration", last
assert last["run_id"] == "force-fix", last
assert "started_at" in last, last
print("ok")
PYEOF
[ $? -eq 0 ] \
  && ok "…recorded as run_mode: migration under the run-id given on the command line" \
  || no "the new run is not a well-formed migration entry"

python3 "$VAL" "$D2" >"$tmp/p1.out" 2>"$tmp/p1.err"; prc=$?
[ "$prc" -eq 0 ] \
  && ok "…and the repaired archive now validates → exit 0" \
  || no "the archive still fails after --force: $(grep '^ERROR' "$tmp/p1.err" | head -3)"

# A second --force on the NOW-complete archive must fall back into the no-op branch. This
# is the loop the bug created: fix, then re-run, then be worse off than before.
runs_mid=$(n_runs "$D2")
tree_sum "$D2" > "$tmp/d2.before"
python3 "$MIGRATE" "$D2" --force --run-id force-again >"$tmp/f6.out" 2>&1
grep -qF "nothing to do" "$tmp/f6.out" \
  && ok "a SECOND --force on the just-repaired archive is a no-op" \
  || no "--force kept working on an archive it had already completed: $(cat "$tmp/f6.out")"
[ "$(n_runs "$D2")" -eq "$runs_mid" ] \
  && ok "…adding no further runs (the fix/re-run loop terminates)" \
  || no "the second --force stacked another run: $(run_ids "$D2")"
diff -q "$tmp/d2.before" <(tree_sum "$D2") >/dev/null \
  && ok "…and touching no files" || no "the second --force rewrote files"

echo
echo "== migrate-force-noop: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
