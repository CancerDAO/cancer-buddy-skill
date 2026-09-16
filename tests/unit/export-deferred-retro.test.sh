#!/usr/bin/env bash
# tests/unit/export-deferred-retro.test.sh — organize v3→v4 fix spec A6 as amended by B7.
#
# WHY THIS GATE EXISTS, stated as the failure it prevents.
#
# `pii_semantic: deferred` is an audited shortcut. A fourteen-line text-only lab
# increment should not have to pay for a full semantic PII sweep over every masked
# surface, so the archive is allowed to write down "the pass is owed" and move on. The
# debt is real but bounded, and the next heavy run settles it.
#
# An export is where that bookkeeping stops being reversible. Files leave the vault; no
# later pass can reach them. So export_share.py checks the debt ITSELF rather than
# trusting the aggregate acceptance gate — the two are deliberately duplicated, because
# a gate evaluated over the whole archive can be satisfied by a later unrelated run,
# while the export boundary is one-way.
#
# The first version of that check kept only the MOST RECENT pii_semantic verdict of any
# kind. That is the bug B7 names, and it is worth spelling out because it does not look
# like a bug:
#
#     run-001  full        pii_semantic: deferred     ← 300 scanned pages, never swept
#     run-002  conversation_incremental  clean        ← patient typed two sentences
#
# The second run's `clean` is honest: the semantic pass DID run, over the two sentences.
# It is also completely uninformative about the 300 scanned pages, because a
# conversation increment never opens one. Under last-verdict-wins, the cheapest run in
# the system — a chat message — laundered the most expensive debt in the system. The
# same holds for `migration`, which reads no page content at all and whose whole point
# is to declare that nothing has been swept under the v4 surface list.
#
# B7 replaces last-verdict-wins with two ideas:
#
#   1. ANCHOR (retrospection). Walk back to the most recent run that is `full` or that
#      added a non-native_text source. Everything before it describes an archive state
#      that has since been superseded; everything from the anchor ONWARD is the state
#      being exported. Without an anchor the check would either look only at the tail
#      (bug above) or at all history forever (a single ancient `failed` would brick the
#      archive permanently, which is how a safety rule gets deleted by whoever needs to
#      ship).
#   2. CLASS (payment). A `clean` pays a debt only if the paying run is at least the
#      debt's class. full / image-increment `clean` pays anything; a conversation or
#      text-only `clean` pays only a text-only debt; a migration `clean` pays nothing
#      heavy, because a migration reads no pixels.
#
# Plus the fail-closed half: a MISSING or malformed update_log.json is now a refusal.
# The previous `return None` meant that deleting one file, or writing `"runs": {}`,
# bought an unconditional export — the cheapest possible bypass, wearing the costume of
# backward compatibility. An archive that cannot say what was done to it cannot be
# cleared to leave the vault.
#
# WHAT THIS FILE ASSERTS. A gate proven only by its negative arm is a gate that may be
# refusing everything, and one proven only by its positive arm is decoration. So the
# table below is deliberately mixed: 17 of the 25 rows expect REFUSE and 8 expect ALLOW,
# and the allow rows are not token green checks — each one is a near-miss of a refuse
# row, differing by exactly the property B7 says is load-bearing:
#
#   row 4 (full deferred → text increment clean → REFUSE) vs
#   row 20 (full deferred → IMAGE increment clean → ALLOW)
#
# is the whole class rule in two rows. Likewise 1-vs-2, 3-vs-2, 5-vs-6, 9-vs-8.
# Every refuse row additionally asserts (a) a phrase from the refusal text, so that a
# refusal cannot silently become a different refusal, and (b) that the destination
# directory was never created — a refusal that has already copied the files is not a
# refusal.
#
# The export is driven through export_share() with `_run_acceptance_gate` stubbed TRUE
# (the idiom is copied from pii-deferred-gate.test.sh section C, not imported), so an
# exit 1 here can only have come from the A6/B7 retrospection and an exit 0 proves that
# check genuinely clears.
#
# H2 closed the last two gaps this file used to pin as KNOWN-GAP. Both were shapes that
# update_log.schema.json already rejects, so the AGGREGATE validator caught them — and
# both walked straight through export's own check, which is precisely the dependency A6
# forbids: `export_share.py` must refuse on its own evidence, because the operator who
# exports is not always the operator who last ran the validator. `runs: []` and a run
# with no `pii_semantic` key are the two ways an archive can say NOTHING about its
# semantic-PII state while still presenting a well-formed file, and saying nothing used
# to be treated as saying clean. They are now refusals, asserted as rows 23/24 and
# re-derived independently in the 'silence' section below.
set -uo pipefail          # NOT -e: every row deliberately absorbs a non-zero exit code
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
EXPORT="$ORG/scripts/export_share.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# ---------------------------------------------------------------------------
# The export driver. Copied verbatim from tests/unit/pii-deferred-gate.test.sh
# section C (the acceptance gate is stubbed TRUE to isolate the PII retrospection);
# the surrounding `set +e` / `set -e` pair is dropped because this file never turns
# -e on in the first place, and turning it on mid-file would abort the table loop
# on the first expected-non-zero row.
# ---------------------------------------------------------------------------
export_rc() {  # <patient_dir> <dest>
  out="$(python3 - "$EXPORT" "$1" "$2" 2>&1 <<'PYEOF'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m._run_acceptance_gate = lambda p: True      # isolate the A6/B7 check
sys.exit(m.export_share(
    pathlib.Path(sys.argv[2]).resolve(), pathlib.Path(sys.argv[3]).resolve(),
    ["profile.json"], recipient="省人民医院 MDT", purpose="second opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-2026-09-16"))
PYEOF
)"
  rc=$?
}

# ---------------------------------------------------------------------------
# Run vocabulary. Every fixture is assembled from these, so a row is readable as a
# sequence of runs and nothing else.
# ---------------------------------------------------------------------------
IMG='[{"source_id":"s-img","read_mode":"model_vision_primary"}]'
TXT='[{"source_id":"s-txt","read_mode":"native_text"}]'

r() {  # <run_id> <run_mode> <added_sources json> [pii_semantic]
  if [ "$#" -ge 4 ]; then
    printf '{"run_id":"%s","run_mode":"%s","started_at":"2026-09-16T00:00:00Z","added_sources":%s,"pii_semantic":"%s"}' "$1" "$2" "$3" "$4"
  else
    printf '{"run_id":"%s","run_mode":"%s","started_at":"2026-09-16T00:00:00Z","added_sources":%s}' "$1" "$2" "$3"
  fi
}

FULL_DEF="$(r run-full-def full "$IMG" deferred)"
FULL_CLEAN="$(r run-full-clean full "$IMG" clean)"
FULL_CLEAN_LATER="$(r run-full-later full '[]' clean)"
FULL_FAILED="$(r run-full-failed full "$IMG" failed)"
FULL_NOPII="$(r run-full-silent full "$IMG")"
CONV_CLEAN="$(r run-conv conversation_incremental '[]' clean)"
MIG_CLEAN="$(r run-mig-clean migration '[]' clean)"
MIG_DEF="$(r run-mig-def migration '[]' deferred)"
INC_TXT_CLEAN="$(r run-inc-txt-clean incremental "$TXT" clean)"
INC_TXT_DEF="$(r run-inc-txt-def incremental "$TXT" deferred)"
INC_TXT_FAILED="$(r run-inc-txt-failed incremental "$TXT" failed)"
INC_IMG_DEF="$(r run-inc-img-def incremental "$IMG" deferred)"
INC_IMG_CLEAN="$(r run-inc-img-clean incremental "$IMG" clean)"
# provenance that cannot be parsed must be treated as the HEAVY case, never skipped
INC_BADSRC_DEF="$(r run-inc-badsrc incremental '["oops"]' deferred)"

# ---------------------------------------------------------------------------
# THE SCENARIO TABLE
#
#   <id> | <log spec> | allow|refuse | <;-separated fixed strings the message must contain>
#
# <log spec> is one of
#   runs:<json array body>   → update_log.json with that runs[]
#   raw:<literal file body>  → update_log.json written verbatim (malformed shapes)
#   none                     → no update_log.json at all
# ---------------------------------------------------------------------------
TABLE=$(cat <<TBL
01 full-deferred → conversation clean|runs:$FULL_DEF,$CONV_CLEAN|refuse|export refused;pii_semantic: deferred;'run-full-def';a full / image run;conversation-only or migration
02 full-deferred → full clean|runs:$FULL_DEF,$FULL_CLEAN_LATER|allow|
03 full-deferred → migration clean|runs:$FULL_DEF,$MIG_CLEAN|refuse|pii_semantic: deferred;'run-full-def';a full / image run;cannot clear a full/image deferral
04 full-deferred → text increment clean|runs:$FULL_DEF,$INC_TXT_CLEAN|refuse|pii_semantic: deferred;'run-full-def';a full / image run
05 full clean → text increment deferred|runs:$FULL_CLEAN,$INC_TXT_DEF|refuse|pii_semantic: deferred;'run-inc-txt-def';a later run
06 full clean → text increment deferred → full clean|runs:$FULL_CLEAN,$INC_TXT_DEF,$FULL_CLEAN_LATER|allow|
07 full clean → image increment deferred|runs:$FULL_CLEAN,$INC_IMG_DEF|refuse|pii_semantic: deferred;'run-inc-img-def';a full / image run
08 migration deferred → full clean|runs:$MIG_DEF,$FULL_CLEAN_LATER|allow|
09 migration deferred, nothing after|runs:$MIG_DEF|refuse|pii_semantic: deferred;'run-mig-def';a full / image run
10 no update_log.json at all|none|refuse|update_log.json is missing;absent file must never read as an absent problem
11 runs is an object, not a list|raw:{"schema_version":"1","runs":{}}|refuse|no runs[] array
12 runs is a string|raw:{"schema_version":"1","runs":"run-001"}|refuse|no runs[] array
13 runs key absent entirely|raw:{"schema_version":"1","patient_code":"PT-0E11"}|refuse|no runs[] array
14 update_log.json is not JSON|raw:{oops|refuse|could not be read;JSONDecodeError
15 full failed, nothing after|runs:$FULL_FAILED|refuse|pii_semantic: failed;'run-full-failed';a full / image run
16 full clean → text increment failed|runs:$FULL_CLEAN,$INC_TXT_FAILED|refuse|pii_semantic: failed;'run-inc-txt-failed';a later run
17 all-clean full run|runs:$FULL_CLEAN|allow|
18 unparseable added_sources entry, deferred|runs:$FULL_CLEAN,$INC_BADSRC_DEF|refuse|pii_semantic: deferred;'run-inc-badsrc';a full / image run
19 non-dict run rows are dropped, debt survives|runs:"garbage",$FULL_DEF|refuse|pii_semantic: deferred;'run-full-def'
20 full-deferred → image increment clean|runs:$FULL_DEF,$INC_IMG_CLEAN|allow|
21 full-deferred → conversation clean → full clean|runs:$FULL_DEF,$CONV_CLEAN,$FULL_CLEAN_LATER|allow|
22 pre-anchor failed superseded by full clean|runs:$INC_TXT_FAILED,$FULL_CLEAN_LATER|allow|
23 runs is an empty list|raw:{"schema_version":"1","runs":[]}|refuse|export refused;records no runs;no runs recorded;never recorded a semantic PII pass
24 full run with no pii_semantic key|runs:$FULL_NOPII|refuse|export refused;run-full-silent;carry no;asserts nothing;Record the verdict
25 conversation-only archive, clean|runs:$CONV_CLEAN|allow|
TBL
)

echo "=== export_share.py — A6/B7 deferred-PII retrospection, ${0##*/} ==="
echo

row_n=0
while IFS='|' read -r label spec expect keywords; do
  [ -n "${label:-}" ] || continue
  row_n=$((row_n + 1))
  id="$(printf '%s' "$label" | awk '{print $1}')"
  d="$tmp/case-$id"
  dest="$tmp/out-$id"
  mkdir -p "$d"
  printf '{"patient_code":"PT-0E11"}\n' > "$d/profile.json"
  case "$spec" in
    none)      : ;;                                   # deliberately no update_log.json
    raw:*)     printf '%s\n' "${spec#raw:}" > "$d/update_log.json" ;;
    runs:*)    printf '{"schema_version":"1","patient_code":"PT-0E11","runs":[%s]}\n' "${spec#runs:}" > "$d/update_log.json" ;;
    *)         no "row $id: unreadable log spec: $spec"; continue ;;
  esac

  export_rc "$d" "$dest"

  if [ "$expect" = "refuse" ]; then
    if [ "$rc" -eq 1 ]; then
      ok "$label → export exits 1"
    else
      no "$label → expected refusal, got rc=$rc: $out"
    fi
    # a refusal that has already copied the files is not a refusal
    if [ -e "$dest" ]; then
      no "$label → destination $dest was created despite the refusal"
    else
      ok "$label → …destination untouched"
    fi
  else
    if [ "$rc" -eq 0 ]; then
      ok "$label → export exits 0"
    else
      no "$label → expected success, got rc=$rc: $out"
    fi
    # an "allow" that writes nothing proves nothing about the boundary opening
    if [ -f "$dest/profile.json" ]; then
      ok "$label → …selected file actually written"
    else
      no "$label → export reported success but wrote no profile.json"
    fi
    if [ -f "$dest/_SHARE_MANIFEST.json" ]; then
      ok "$label → …with a purpose-limited share manifest beside it"
    else
      no "$label → no _SHARE_MANIFEST.json in the export"
    fi
  fi

  # the refusal TEXT is part of the contract: a refusal that stops naming the run and
  # the class of payment it wants is a refusal an operator will work around by guessing
  if [ -n "${keywords:-}" ]; then
    old_ifs="$IFS"; IFS=';'
    for kw in $keywords; do
      [ -n "$kw" ] || continue
      if printf '%s' "$out" | grep -qF -- "$kw"; then
        ok "$label → …message contains: $kw"
      else
        no "$label → message missing: $kw -- got: $out"
      fi
    done
    IFS="$old_ifs"
  fi
done <<< "$TABLE"

echo
echo "-- table rows executed: $row_n --"
[ "$row_n" -ge 12 ] && ok "the table carries at least the 12 scenarios B7 enumerates ($row_n rows)" \
  || no "scenario table shrank to $row_n rows — B7 requires at least 12"

# ---------------------------------------------------------------------------
# Structural assertions ABOUT the table, so it cannot decay into an all-negative or
# all-positive suite without the suite saying so.
# ---------------------------------------------------------------------------
n_refuse=$(printf '%s\n' "$TABLE" | grep -c '|refuse|')
n_allow=$(printf '%s\n' "$TABLE" | grep -c '|allow|')
[ "$n_refuse" -ge 6 ] && ok "…of which $n_refuse assert a REFUSAL" \
  || no "only $n_refuse refusing rows — the negative arm has been hollowed out"
[ "$n_allow" -ge 5 ] && ok "…and $n_allow assert the boundary OPENS (a gate that always refuses is not a gate)" \
  || no "only $n_allow allowing rows — this suite can no longer detect a gate that refuses everything"

# ---------------------------------------------------------------------------
# The pair that IS the B7 class rule. Asserted separately from the table because if
# these two ever agree, the fix has been reverted and every other row still passes.
# ---------------------------------------------------------------------------
echo
echo "=== the discriminating pair: same debt, different payer ==="
rc_txt=$(grep -c '^04 .*|refuse|' <<< "$TABLE")
rc_img=$(grep -c '^20 .*|allow|' <<< "$TABLE")
[ "$rc_txt" -eq 1 ] && [ "$rc_img" -eq 1 ] \
  && ok "rows 04/20 differ only in the paying run's read_mode and differ in verdict" \
  || no "the text-vs-image discriminating pair is no longer in the table"

# rerun both explicitly and compare, so the claim rests on behaviour not on the table text
mkdir -p "$tmp/pairA" "$tmp/pairB"
printf '{"patient_code":"PT-0E11"}\n' | tee "$tmp/pairA/profile.json" > "$tmp/pairB/profile.json"
printf '{"schema_version":"1","runs":[%s,%s]}\n' "$FULL_DEF" "$INC_TXT_CLEAN" > "$tmp/pairA/update_log.json"
printf '{"schema_version":"1","runs":[%s,%s]}\n' "$FULL_DEF" "$INC_IMG_CLEAN" > "$tmp/pairB/update_log.json"
export_rc "$tmp/pairA" "$tmp/pairOutA"; rc_a=$rc
export_rc "$tmp/pairB" "$tmp/pairOutB"; rc_b=$rc
[ "$rc_a" -eq 1 ] && [ "$rc_b" -eq 0 ] \
  && ok "…and at runtime: native_text clean CANNOT pay a full deferral, image clean CAN" \
  || no "the class rule collapsed at runtime: text=$rc_a image=$rc_b (expected 1 and 0)"

# ---------------------------------------------------------------------------
# SILENCE IS NOT A CLEAN VERDICT (rows 23/24, re-derived).
#
# Rows 23/24 run through the shared table driver, which proves the exit code and the
# message. This section proves the two properties the table cannot: that the refusal is
# export's OWN (the acceptance gate is stubbed TRUE, so nothing else could have produced
# it), and that each refusal is bought by the SILENCE and not by the fixture — the
# minimal repair of each shape exports cleanly.
#
# Both shapes are well-formed JSON that an operator would read as "fine". `runs: []` is
# the archive equivalent of a blank logbook, and a run without `pii_semantic` is a run
# that performed work and recorded no verdict about it. The old behaviour let both
# through, which made the missing-file refusal (row 10) decorative: anyone blocked by a
# deleted update_log.json could write `{"runs": []}` and export.
# ---------------------------------------------------------------------------
echo
echo "=== silence is not a clean verdict: the two shapes that used to export ==="

mkdir -p "$tmp/gapEmpty"; printf '{"patient_code":"PT-0E11"}\n' > "$tmp/gapEmpty/profile.json"
printf '{"schema_version":"1","runs":[]}\n' > "$tmp/gapEmpty/update_log.json"
export_rc "$tmp/gapEmpty" "$tmp/gapEmptyOut"
[ "$rc" -eq 1 ] \
  && ok "runs:[] REFUSES (H2) — an archive with zero recorded runs says as little as a missing file" \
  || no "runs:[] still exports (rc=$rc): the missing-file refusal can be bypassed by writing an empty log"
printf '%s' "$out" | grep -qF 'no runs recorded' \
  && ok "…refused for the stated reason, not as a side effect of some later check" \
  || no "the empty-runs refusal does not name itself: $out"
[ -e "$tmp/gapEmptyOut" ] \
  && no "runs:[] was refused but the destination was created anyway" \
  || ok "…and nothing was copied: a refusal that has already written the files is not a refusal"

# NEGATIVE ARM — the SAME archive with one clean full run exports. Without this, the
# assertion above is satisfied by an export that refuses every archive it is shown.
mkdir -p "$tmp/gapEmptyFixed"; printf '{"patient_code":"PT-0E11"}\n' > "$tmp/gapEmptyFixed/profile.json"
printf '{"schema_version":"1","runs":[%s]}\n' "$FULL_CLEAN" > "$tmp/gapEmptyFixed/update_log.json"
export_rc "$tmp/gapEmptyFixed" "$tmp/gapEmptyFixedOut"
[ "$rc" -eq 0 ] && [ -f "$tmp/gapEmptyFixedOut/profile.json" ] \
  && ok "…while the same archive with ONE recorded clean run exports — the refusal is bought by the emptiness" \
  || no "the control archive was refused too (rc=$rc): $out"

mkdir -p "$tmp/gapSilent"; printf '{"patient_code":"PT-0E11"}\n' > "$tmp/gapSilent/profile.json"
printf '{"schema_version":"1","runs":[%s]}\n' "$FULL_NOPII" > "$tmp/gapSilent/update_log.json"
export_rc "$tmp/gapSilent" "$tmp/gapSilentOut"
[ "$rc" -eq 1 ] \
  && ok "a run that OMITS pii_semantic REFUSES (H2) — a run that asserts nothing cannot clear an export" \
  || no "a run with no pii_semantic verdict still exports (rc=$rc): omitting the key is cheaper than deferring it"
printf '%s' "$out" | grep -qF 'run-full-silent' \
  && ok "…and the refusal names the run that said nothing, so the operator knows what to record" \
  || no "the silent run is not named in the refusal: $out"
printf '%s' "$out" | grep -qF 'pii_semantic' \
  && ok "…and names the key it wanted" || no "the refusal does not name pii_semantic: $out"
[ -e "$tmp/gapSilentOut" ] \
  && no "the silent-run archive was refused but the destination was created anyway" \
  || ok "…with the destination untouched"

# NEGATIVE ARM — the same run, same sources, with the verdict filled in.
mkdir -p "$tmp/gapSilentFixed"; printf '{"patient_code":"PT-0E11"}\n' > "$tmp/gapSilentFixed/profile.json"
printf '{"schema_version":"1","runs":[%s]}\n' "$FULL_CLEAN" > "$tmp/gapSilentFixed/update_log.json"
export_rc "$tmp/gapSilentFixed" "$tmp/gapSilentFixedOut"
[ "$rc" -eq 0 ] \
  && ok "…while the identical run carrying pii_semantic: clean exports — the key is the whole difference" \
  || no "the control run with a clean verdict was refused too (rc=$rc): $out"

# THE THREE-WAY CONTRAST that makes 'silence' a distinct verdict rather than an alias.
# A run that says `deferred` is refused for the deferral; a run that says nothing is
# refused for saying nothing. If those two ever produce the same message, the silent
# case has been folded into the deferred case and an operator reading the refusal will
# go looking for a PII pass that was never skipped — it was never recorded.
mkdir -p "$tmp/gapDef"; printf '{"patient_code":"PT-0E11"}\n' > "$tmp/gapDef/profile.json"
printf '{"schema_version":"1","runs":[%s]}\n' "$FULL_DEF" > "$tmp/gapDef/update_log.json"
export_rc "$tmp/gapDef" "$tmp/gapDefOut"; def_out="$out"
printf '%s' "$def_out" | grep -qF 'pii_semantic: deferred' \
  && ok "a DEFERRED run is refused as a deferral…" || no "the deferred control changed shape: $def_out"
printf '%s' "$def_out" | grep -qF 'carry no' \
  && no "the deferred refusal now reports the silent-run reason — the two verdicts have merged" \
  || ok "…and the silent-run refusal is a DIFFERENT message: 'nothing recorded' ≠ 'recorded as skipped'"

# ---------------------------------------------------------------------------
# Ordering: the retrospection runs BEFORE the acceptance gate, i.e. a refusal here is
# not reachable only through a gate that a future refactor might move or skip.
# ---------------------------------------------------------------------------
echo
echo "=== ordering: the PII retrospection precedes the acceptance gate ==="
mkdir -p "$tmp/order"; printf '{"patient_code":"PT-0E11"}\n' > "$tmp/order/profile.json"
printf '{"schema_version":"1","runs":[%s,%s]}\n' "$FULL_DEF" "$CONV_CLEAN" > "$tmp/order/update_log.json"
export_rc "$tmp/order" "$tmp/orderOut"
printf '%s' "$out" | grep -qF 'running structural acceptance gate' \
  && no "the acceptance gate ran before the PII refusal — the refusal is not the first boundary" \
  || ok "the acceptance gate was never reached; the PII refusal fired first"

echo
echo "== export-deferred-retro: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
