#!/usr/bin/env bash
# tests/unit/pii-deferred-gate.test.sh — organize v3→v4 fix spec A6.
#
# The semantic PII pass is the only thing standing between a patient's 住院号, a name
# in a letterhead, a signature and an exported file. It is expensive — several subagent
# reads over every masked surface — and a 14-line text-only lab increment genuinely
# should not cost that. So `pii_semantic: deferred` exists: an AUDITED shortcut that
# postpones the pass to the next full run.
#
# An audited shortcut and an un-run safety pass are the same object unless something
# keeps them apart. A6 is that something, and it is deliberately two INDEPENDENT
# mechanisms rather than one, because they fail differently:
#
#   (1) update_log.json, checked by gate_update_log_provenance. `deferred` is legal
#       only when ALL of these hold:
#         * run_mode ∈ {incremental, migration} (B5) — TWO modes may defer, for
#           OPPOSITE reasons, and the difference is why this is not just a longer list.
#           `incremental` defers because its new surface is small and text-only, so the
#           debt is bounded and someone can come back for it. `migration` defers because
#           migrate_v3_to_v4.py reads NO source characters at all — it rewrites metadata
#           in place — so demanding a semantic pass over material the migration never
#           touched would make every pre-v4 archive unmigratable without first re-running
#           organize end to end, which is precisely the data-loss event A13 exists to
#           avoid. `full` and `conversation_incremental` remain illegal: a full run
#           re-read everything, so there is no small surface to defer, and a conversation
#           run added no uploaded source at all. For both of those, "deferred" means the
#           pass simply did not run.
#         * every added_sources[] entry is read_mode == native_text — a pixel page is
#           exactly where the semantic pass earns its keep, because a name in a
#           letterhead is invisible to the deterministic shape floor (A7). (A migration
#           adds no sources, so this is vacuously true for it.)
#         * readiness.review_flags carries category: pii_semantic_deferred — a debt
#           recorded only in an audit log that no review surface repeats is
#           indistinguishable from a pass nobody ran. NEITHER run mode buys silence:
#           this is what the widened exemption still costs.
#       Any one missing turns the exemption into an unchecked archive wearing the word
#       "deferred", so each is asserted separately below: a conjunction tested only as
#       a whole hides which conjunct is dead.
#
#   (2) export_share.py, checked on its own. This duplication is the point, not an
#       oversight. The aggregate acceptance gate can be satisfied by a later unrelated
#       run, and it is evaluated over the archive; an export is a ONE-WAY boundary with
#       a different risk profile — once the files leave the vault, no later pass can
#       reach them. So export walks update_log.runs itself and refuses while the most
#       recent PII verdict is anything but `clean`, BEFORE it even calls the
#       acceptance gate.
#
# Both directions are asserted throughout. A refusal that also fires on a clean archive
# would simply be retired by whoever needs to ship, and a permission that never refuses
# is decoration.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
EXPORT="$ORG/scripts/export_share.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

run_gate() {  # <gate_fn> <patient_dir>   — errors only; the standing WARN is not a failure
  set +e
  out="$(python3 - "$ORG" "$1" "$2" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs, warns = [], []
getattr(v, sys.argv[2])(pathlib.Path(sys.argv[3]), errs, warns)
for e in errs:
    print(e)
for w in warns:
    print("WARN " + w)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# <dir> <run_mode> <added_sources json> <readiness flag category>
mk_run() {
  local d="$1"
  mkdir -p "$d"
  cat > "$d/update_log.json" <<EOF
{ "schema_version":"1","patient_code":"PT-0E11","runs":[
  {"run_id":"run-001","run_mode":"$2","started_at":"2026-09-16T00:00:00Z",
   "added_sources":$3,"pii_semantic":"deferred"} ]}
EOF
  cat > "$d/readiness.json" <<EOF
{ "review_flags":[
  {"category":"$4","audience":"internal_qc",
   "detail":"纯文本增量：语义 PII 复扫延后至下一次全量运行"} ]}
EOF
}

NATIVE='[{"source_id":"s1","read_mode":"native_text"}]'
MIXED='[{"source_id":"s1","read_mode":"native_text"},{"source_id":"s2","read_mode":"model_vision_primary"}]'

# ===========================================================================
# A. POSITIVE — all three preconditions hold
# ===========================================================================
echo "=== A. an auditable deferral ==="

d="$tmp/legal"; mk_run "$d" incremental "$NATIVE" pii_semantic_deferred
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 0 ] && ok "incremental + all-native_text + readiness flag → exit 0" \
  || no "a legal deferral was rejected: $out"
echo "$out" | grep -q 'WARN pii_semantic_deferred' \
  && ok "…and the debt is still WARNed on every run, so it cannot go quiet" \
  || no "the standing reminder disappeared: $out"

# the clean baseline: nothing deferred, nothing warned
d="$tmp/clean"; mkdir -p "$d"
cat > "$d/update_log.json" <<'EOF'
{ "schema_version":"1","patient_code":"PT-0E11","runs":[
  {"run_id":"run-001","run_mode":"full","started_at":"2026-09-16T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"model_vision_primary"}],
   "pii_semantic":"clean","faithfulness_method":"vision_second_read"} ]}
EOF
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 0 ] && ok "a full run recorded pii_semantic: clean → exit 0" \
  || no "the clean path is blocked: $out"
echo "$out" | grep -q 'pii_semantic_deferred' \
  && no "a clean run still carries the deferral WARN: $out" \
  || ok "…with no deferral WARN attached"

# ===========================================================================
# B. NEGATIVE — each precondition violated ON ITS OWN
# ===========================================================================
echo "=== B. each of the three conditions, separately ==="

d="$tmp/full_run"; mk_run "$d" full "$NATIVE" pii_semantic_deferred
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "run_mode=full + deferred → exit 1" || no "a full run deferred the PII pass, rc=$rc"
echo "$out" | grep -q "run_mode='full'" && ok "…error quotes the offending run_mode" || no "run_mode not quoted: $out"
echo "$out" | grep -q "legal only for \['incremental', 'migration'\]" \
  && ok "…error states the scope of the exemption, as the closed pair B5 defines" \
  || no "scope not stated: $out"

# B5 — a migration MAY defer, and this is the arm that says so. migrate_v3_to_v4.py
# rewrites inventory metadata in place; it opens no page, reads no new character and
# adds no source. Refusing its deferral would mean every pre-v4 archive had to be
# re-organized from the originals before it could be migrated at all — which is the
# data-loss event the whole v3 compatibility branch exists to prevent.
d="$tmp/migration_run"; mk_run "$d" migration '[]' pii_semantic_deferred
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 0 ] && ok "run_mode=migration + deferred + the readiness flag → exit 0 (B5)" \
  || no "a migration could not defer a pass over characters it never read: $out"
echo "$out" | grep -q 'WARN pii_semantic_deferred' \
  && ok "…and the migration's debt is WARNed exactly like the increment's" \
  || no "the migration deferral went quiet instead of standing as a debt: $out"

# what the migration does NOT buy is silence. Same run, no readiness flag → ERROR.
# Otherwise `run_mode: migration` would be a one-word way to make a semantic PII pass
# disappear, and it is the mode with the least evidence behind it.
d="$tmp/migration_no_flag"; mk_run "$d" migration '[]' coverage_gap
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "migration + deferred but NO pii_semantic_deferred flag → exit 1" \
  || no "run_mode=migration bought an unrecorded deferral, rc=$rc"
echo "$out" | grep -q 'category=pii_semantic_deferred' \
  && ok "…for the same named reason an increment gets" || no "category not named: $out"

# and the exemption really is a closed pair, not "any mode with an excuse":
# conversation_incremental adds no uploaded source either, and it still may NOT defer —
# because there was no new surface to scan, so there is nothing to owe.
d="$tmp/convo_run"; mk_run "$d" conversation_incremental '[]' pii_semantic_deferred
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "run_mode=conversation_incremental + deferred → exit 1 (still outside the pair)" \
  || no "the B5 widening leaked to a third run mode, rc=$rc"
echo "$out" | grep -q "run_mode='conversation_incremental'" \
  && ok "…error quotes that run_mode too" || no "run_mode not quoted: $out"

d="$tmp/non_native"; mk_run "$d" incremental "$MIXED" pii_semantic_deferred
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "an added source with read_mode != native_text → exit 1" \
  || no "a pixel page rode in on a text-increment exemption, rc=$rc"
echo "$out" | grep -q "\['s2'\]" && ok "…error names the non-native source" || no "source not named: $out"
echo "$out" | grep -q 'only a pure text increment may defer' \
  && ok "…error states why a pixel page cannot defer" || no "rationale missing: $out"

d="$tmp/no_flag"; mk_run "$d" incremental "$NATIVE" coverage_gap
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "readiness.review_flags carries no pii_semantic_deferred flag → exit 1" \
  || no "an invisible debt accepted, rc=$rc"
echo "$out" | grep -q 'category=pii_semantic_deferred' \
  && ok "…error names the flag category the archive owes" || no "category not named: $out"
echo "$out" | grep -q 'written where humans look' \
  && ok "…error states why the update log alone is not enough" || no "rationale missing: $out"

# readiness.json missing entirely is the same failure, not an exemption
d="$tmp/no_readiness"; mk_run "$d" incremental "$NATIVE" pii_semantic_deferred
rm -f "$d/readiness.json"
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "no readiness.json at all → exit 1 (an absent surface is not a clean one)" \
  || no "deleting the review surface bought the exemption, rc=$rc"

# and `failed` is never legal, under any run_mode — the pass is fail-closed
d="$tmp/failed"; mkdir -p "$d"
cat > "$d/update_log.json" <<'EOF'
{ "schema_version":"1","runs":[
  {"run_id":"run-001","run_mode":"incremental","started_at":"2026-09-16T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],"pii_semantic":"failed"} ]}
EOF
run_gate gate_update_log_provenance "$d"
[ "$rc" -eq 1 ] && ok "pii_semantic=failed → exit 1 regardless of run_mode" || no "a failed PII pass accepted, rc=$rc"
echo "$out" | grep -q 'fail-closed' && ok "…error states the pass is fail-closed" || no "fail-closed not stated: $out"

# ===========================================================================
# C. export_share.py refuses INDEPENDENTLY of the aggregate gate
# ===========================================================================
echo "=== C. export_share.py (A6, second mechanism) ==="

mk_vault() {  # <dir> <runs json body>
  local d="$1"
  mkdir -p "$d"
  cat > "$d/profile.json" <<'EOF'
{"patient_code":"PT-0E11"}
EOF
  cat > "$d/update_log.json" <<EOF
{ "runs":[$2] }
EOF
}

R_FULL_CLEAN='{"run_id":"run-001","run_mode":"full","started_at":"2026-09-01T00:00:00Z","added_sources":[{"source_id":"s1","read_mode":"model_vision_primary"}],"pii_semantic":"clean"}'
R_DEFERRED='{"run_id":"run-002","run_mode":"incremental","started_at":"2026-09-16T00:00:00Z","added_sources":[{"source_id":"s2","read_mode":"native_text"}],"pii_semantic":"deferred"}'
R_LATER_CLEAN='{"run_id":"run-003","run_mode":"full","started_at":"2026-09-17T00:00:00Z","added_sources":[],"pii_semantic":"clean"}'
R_IMG_DEFERRED='{"run_id":"run-002","run_mode":"incremental","started_at":"2026-09-16T00:00:00Z","added_sources":[{"source_id":"s2","read_mode":"model_vision_primary"}],"pii_semantic":"deferred"}'

# The acceptance gate is stubbed TRUE for these three runs on purpose: it isolates the
# PII refusal, so an exit 1 here can only have come from the A6 check and an exit 0
# proves the check actually clears. (Section D then verifies the ordering for real.)
export_rc() {  # <patient_dir> <dest>
  set +e
  out="$(python3 - "$EXPORT" "$1" "$2" 2>&1 <<'PYEOF'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m._run_acceptance_gate = lambda p: True      # isolate the A6 check
sys.exit(m.export_share(
    pathlib.Path(sys.argv[2]).resolve(), pathlib.Path(sys.argv[3]).resolve(),
    ["profile.json"], recipient="省人民医院 MDT", purpose="second opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-2026-09-16"))
PYEOF
)"
  rc=$?
  set -e
}

d="$tmp/vault_deferred"; mk_vault "$d" "$R_FULL_CLEAN,$R_DEFERRED"
export_rc "$d" "$tmp/out_deferred"
[ "$rc" -eq 1 ] && ok "latest PII verdict is 'deferred' → export exits 1" \
  || no "an un-cleared deferral was exported, rc=$rc"
echo "$out" | grep -q 'export refused' && ok "…stderr says the export was REFUSED" || no "no refusal line: $out"
echo "$out" | grep -q 'pii_semantic: deferred' && ok "…refusal quotes the verdict" || no "verdict not quoted: $out"
echo "$out" | grep -q "'run-002'" && ok "…refusal names the run that owes the pass" || no "run not named: $out"
[ -d "$tmp/out_deferred" ] && no "the destination directory was created despite the refusal" \
  || ok "…and nothing was written to the destination"

# a deferral that followed a run with an IMAGE source is the same refusal
d="$tmp/vault_img"; mk_vault "$d" "$R_FULL_CLEAN,$R_IMG_DEFERRED"
export_rc "$d" "$tmp/out_img"
[ "$rc" -eq 1 ] && ok "a deferral after a non-native_text source → export exits 1" \
  || no "image-source deferral exported, rc=$rc"

# `failed` blocks the export too — export is not laxer than the gate
d="$tmp/vault_failed"; mk_vault "$d" "{\"run_id\":\"run-002\",\"run_mode\":\"incremental\",\"started_at\":\"2026-09-16T00:00:00Z\",\"added_sources\":[],\"pii_semantic\":\"failed\"}"
export_rc "$d" "$tmp/out_failed"
[ "$rc" -eq 1 ] && ok "latest PII verdict is 'failed' → export exits 1" || no "a failed pass exported, rc=$rc"

# POSITIVE — a later run pays the debt and the boundary opens
d="$tmp/vault_cleared"; mk_vault "$d" "$R_FULL_CLEAN,$R_DEFERRED,$R_LATER_CLEAN"
export_rc "$d" "$tmp/out_cleared"
[ "$rc" -eq 0 ] && ok "a later run records pii_semantic: clean → export exits 0" \
  || no "the debt was paid but the export still refused: $out"
[ -f "$tmp/out_cleared/profile.json" ] && ok "…the selected file was actually written" \
  || no "export claimed success but wrote nothing"
[ -f "$tmp/out_cleared/_SHARE_MANIFEST.json" ] && ok "…with a purpose-limited share manifest beside it" \
  || no "no _SHARE_MANIFEST.json in the export"

# the debt is paid by APPENDING a clean run, never by editing the deferred one away:
# the deferred row is still in the log and the export still succeeds
grep -q '"pii_semantic":"deferred"' "$d/update_log.json" \
  && ok "…and the deferred run stays in the append-only log (debt and payment both visible)" \
  || no "the deferred run was expected to remain in the fixture's log"

# ===========================================================================
# D. the two mechanisms are genuinely independent
# ===========================================================================
echo "=== D. independence from the aggregate acceptance gate ==="

# No stub this time. The vault is structurally broken (no source_inventory.json, no
# readiness.json), so the acceptance gate would fail too — but the PII refusal must
# come FIRST and must be the message the operator sees. If A6 were implemented as a
# validator gate only, this fixture would report "acceptance gate failed" instead.
d="$tmp/vault_real"; mk_vault "$d" "$R_FULL_CLEAN,$R_DEFERRED"
set +e
real_out="$(python3 "$EXPORT" "$d" --out "$tmp/out_real" \
  --include profile.json --recipient r --purpose p \
  --expires-at 2099-01-01T00:00:00Z --authorization-ref a 2>&1)"
real_rc=$?
set -e
[ "$real_rc" -eq 1 ] && ok "the real CLI refuses an un-cleared deferral → exit 1" \
  || no "CLI rc=$real_rc"
echo "$real_out" | grep -q 'pii_semantic: deferred' \
  && ok "…the PII refusal is what the operator is told" || no "wrong message: $real_out"
echo "$real_out" | grep -q 'acceptance gate' \
  && no "the aggregate gate ran first — the A6 check is not independent: $real_out" \
  || ok "…and it never reached the aggregate gate (the check is genuinely its own)"

# ===========================================================================
# E. the legal set is a named constant, not a literal spread through the gate
# ===========================================================================
echo "=== E. no drift ==="

# Every arm above is about WHICH run modes may defer. If that set is re-spelled inline
# at each use site it will drift, and the drift will be in the permissive direction —
# that is the direction that makes a failing run pass. Pin it once, here.
python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
assert set(v.PII_DEFERRABLE_RUN_MODES) == {"incremental", "migration"}, \
    f"the deferrable run modes drifted from B5: {sorted(v.PII_DEFERRABLE_RUN_MODES)}"
assert set(v.PII_SEMANTIC_STATES) == {"clean", "deferred", "failed"}, \
    f"the pii_semantic vocabulary drifted: {sorted(v.PII_SEMANTIC_STATES)}"
print("deferral vocabulary OK")
PYEOF
[ $? -eq 0 ] \
  && ok "PII_DEFERRABLE_RUN_MODES pins {incremental, migration} and the state set stays closed" \
  || no "the deferral vocabulary drifted from fix spec B5"

# ---------------------------------------------------------------------------
echo
echo "== pii-deferred-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
