#!/usr/bin/env bash
# tests/unit/migrate-v3-to-v4.test.sh — organize v3→v4, fix spec A13 + A40.
#
# v4 makes three things REQUIRED that no v3 archive ever wrote: `kind` and
# `clinical_class` on every source_inventory row, and `readiness.projection_coverage`.
# That leaves exactly two honest options for an archive somebody already has on disk —
# fail it (which turns an upgrade into a data-loss event) or accept rows missing the
# fields every open-world gate keys off (which makes the requirement decorative). The
# contract takes neither: the validator reads a scheme-3 archive leniently, WARNs, and
# names scripts/migrate_v3_to_v4.py, and THIS script performs the one-time conversion.
#
# The conversion is only worth anything if two things hold, and both are what this file
# asserts. First, it must actually clear the legacy branch: after it runs the archive is
# no longer detected as scheme 3, the WARN that pointed here is gone, and the v4 gates
# that were being SKIPPED now run and pass. A migration that leaves the archive readable
# but still legacy has bought nothing. Second, every value it writes must be derived from
# something the v3 archive already recorded — `clinical_class` from the bucket number and
# nothing else, `kind` from `read_mode` — and where v3 recorded nothing at all, the
# migration must say "unknown" rather than mint a number. `projection_coverage` is the
# dangerous one: an empty `unprojected_field_classes` renders downstream as "fully
# projected", so a skeleton of zeros would tell a cold session the archive is complete
# when in truth nobody ever looked. The skeleton is `["unknown"]`, per source, always.
#
# And --dry-run must write NOTHING. A migration you cannot inspect before committing to
# is one you run blind on the only copy of a patient's records, so the flag is checked
# here byte-for-byte across the whole tree, not by reading the script's output.
#
# Three defects that this file used to DOCUMENT rather than assert are now closed, and
# the assertions below were tightened accordingly. They are recorded here because the
# shape of the fix is the interesting part:
#   - the migrator writes `pii_semantic: "deferred"` on its `run_mode: "migration"`
#     entry, which A6 read as illegal, so the migrator's own output could not pass its
#     own validator. B5 widened the deferrable set to {incremental, migration} — for
#     opposite reasons, and with the readiness flag still mandatory for both — because a
#     migration reads no source characters at all, and demanding a semantic PII pass over
#     material it never touched would make every pre-v4 archive unmigratable without
#     first re-running organize from the originals. Section B now asserts a clean full
#     validator run, not "only the known complaint remains".
#   - a v3 row carries `doc_type`, which the v4 schema (additionalProperties: false)
#     rejects. B6 makes the migration rename it to `doc_kind`.
#   - `transcript_path` is required for read_mode in {model_vision_primary,
#     model_vision_assist} (A14) and a v3 model-read row has no transcript to point at.
#     B6 writes `legacy_transcript_unavailable: true` instead, which exempts the row from
#     that requirement and — this is the half that keeps it honest — forces it to be
#     counted in `projection_coverage.unreadable_sources` with a `coverage_gap` flag.
# The B5/B6 behaviour itself is pinned in tests/unit/migration-deferred.test.sh, on a
# two-source fixture that includes a model-read row. This file stays on the single
# native_text row so that its subject remains the A13 field mapping.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
MIGRATE="$ORG/scripts/migrate_v3_to_v4.py"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

jget() {  # <file> <python expr over `d`>
  python3 -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print($2)" "$1" 2>/dev/null
}

# --------------------------------------------------------------------------- #
# A MINIMAL scheme-3 archive: an old source_inventory.json with no kind /
# clinical_class / text_layer_kind / transcript_path, a readiness.json still
# declaring schema_version "2", and one bucket sidecar. It DECLARES `scheme_version: 3`
# out loud, because B4 stopped reading an omitted key as "legacy" — an archive that does
# not say which contract it was written to is now its own ERROR, and a migration fixture
# that failed for THAT reason would prove nothing about the migration. read_mode is native_text and
# the bucket is 03_ (narrative) deliberately: those are the two choices that keep the
# fixture clear of the lab floor and the transcript_path requirement, so anything this
# file reports is about the migration and not about an unrelated schema debt.
# --------------------------------------------------------------------------- #
mk_v3() {  # <dir>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/upload-001.txt"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":3,"patient_dir":".",
  "generated_at":"2026-01-02T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
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
  # B7 — update_log.json is a REQUIRED product for every archive, pre-v4 included. The
  # migration APPENDS its own runs[] row to this log (section B asserts that); starting
  # from no log at all would let the fixture pass by accident, because "the migration
  # created the file" and "the migration recorded itself" are different claims.
  cat > "$d/update_log.json" <<'EOF'
{"schema_version":"1","patient_code":"PT-A1B2","runs":[
  {"run_id":"run-legacy-001","run_mode":"full","started_at":"2026-01-02T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],
   "pii_semantic":"clean","faithfulness_method":"native_text_identity"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

# ===========================================================================
# A. the migration runs and clears the legacy branch
# ===========================================================================
echo "=== A. scheme 3 → 4 conversion ==="

D="$tmp/arch"
mk_v3 "$D"

python3 "$VAL" "$D" >"$tmp/pre.out" 2>"$tmp/pre.err"; pre_rc=$?
[ "$pre_rc" -eq 0 ] \
  && ok "the scheme-3 fixture is a VALID legacy archive before migration (exit 0)" \
  || no "fixture is broken for an unrelated reason, rc=$pre_rc: $(grep '^ERROR' "$tmp/pre.err")"
grep -q 'migrate_v3_to_v4.py' "$tmp/pre.err" \
  && ok "…and the run WARNs, naming scripts/migrate_v3_to_v4.py as the remedy" \
  || no "the legacy WARN does not point at the migration script"

python3 "$MIGRATE" "$D" --run-id migrate-test >"$tmp/mig.out" 2>&1; mig_rc=$?
[ "$mig_rc" -eq 0 ] && ok "migrate_v3_to_v4.py exits 0 on the scheme-3 archive" \
  || no "migration exited $mig_rc: $(cat "$tmp/mig.out")"

# ===========================================================================
# B. afterwards: the v4 gates run, and they pass
# ===========================================================================
echo "=== B. the archive is no longer legacy ==="

python3 "$VAL" "$D" >"$tmp/post.out" 2>"$tmp/post.err"; post_rc=$?

grep -q 'legacy_archive' "$tmp/post.err" \
  && no "the legacy_archive WARN survived the migration" \
  || ok "the legacy_archive WARN is GONE after migration"
grep -q 'legacy_schema: readiness.json declares schema_version 2' "$tmp/post.err" \
  && no "readiness.json is still read against the v2 shape" \
  || ok "readiness.json is no longer read against the legacy v2 shape"
grep -q 'migrate_v3_to_v4.py' "$tmp/post.err" \
  && no "the validator still tells the operator to run the migration they just ran" \
  || ok "no WARN still points at scripts/migrate_v3_to_v4.py"

python3 - "$ORG" "$D" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
sys.exit(0 if not v.archive_is_legacy_v3(pathlib.Path(sys.argv[2])) else 1)
PYEOF
[ $? -eq 0 ] && ok "archive_is_legacy_v3() is now False — the v4 gates are ARMED, not skipped" \
  || no "the archive still self-describes as scheme 3"

# EVERY gate, with no exclusion list. These are the gates A13 says a v3 archive was
# having SKIPPED, so running them is the whole point of the migration; a migration that
# produces rows they reject has converted nothing. The loop used to skip
# gate_update_log_provenance, because the migrator's own `pii_semantic: deferred` could
# not pass it — B5 closed that, and an exclusion list left behind after its reason is
# gone is how a suite quietly stops testing the thing it was written for.
python3 - "$ORG" "$D" <<'PYEOF'
import sys, inspect, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
p = pathlib.Path(sys.argv[2])
errs, warns = [], []
for name in sorted(n for n in dir(v) if n.startswith("gate_")):
    fn = getattr(v, name)
    params = list(inspect.signature(fn).parameters)
    if len(params) == 2 and params[1] == "warnings":
        fn(p, warns)
    elif len(params) == 2:
        fn(p, errs)
    elif len(params) == 3:
        fn(p, errs, warns)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
[ $? -eq 0 ] \
  && ok "EVERY v4 gate passes on the migrated archive (no gate is excluded from the sweep)" \
  || no "the migrated archive fails a v4 gate"

# …and the FULL validator, end to end, exits 0. This is the assertion the old known
# pii_semantic defect made impossible, and it is the only one that means "the migrator's
# own output is a valid v4 archive" rather than "it is valid apart from the parts we
# agreed not to look at".
[ "$post_rc" -eq 0 ] \
  && ok "the migrated archive passes the FULL validator → exit 0 (B5 closed the last gap)" \
  || no "the migrated archive still fails the full validator: $(grep '^ERROR' "$tmp/post.err")"
grep -q '^ERROR' "$tmp/post.err" \
  && no "the migrated archive still emits ERRORs: $(grep '^ERROR' "$tmp/post.err")" \
  || ok "…with no ERROR lines at all in its output"
# the debt the migration DID leave behind is still visible, though: a migration defers
# the semantic PII pass, and exit 0 must not be read as "that pass ran".
grep -q 'WARN: pii_semantic_deferred' "$tmp/post.err" \
  && ok "…while the deferred semantic PII pass is still WARNed, so exit 0 is not silence" \
  || no "the migration's PII debt went quiet: $(cat "$tmp/post.err")"

# ===========================================================================
# C. what it wrote, and how conservatively
# ===========================================================================
echo "=== C. derived fields (A13 mapping) ==="

INV="$D/source_inventory.json"
[ "$(jget "$INV" "d['scheme_version']")" = "4" ] \
  && ok "source_inventory.json now declares scheme_version 4" \
  || no "scheme_version is $(jget "$INV" "d.get('scheme_version')")"
[ "$(jget "$INV" "d['files'][0]['kind']")" = "known" ] \
  && ok "kind <- known (v3 rows were all accepted by a pinned bucket, so none can be novel)" \
  || no "kind is $(jget "$INV" "d['files'][0].get('kind')")"
[ "$(jget "$INV" "d['files'][0]['clinical_class']")" = "narrative" ] \
  && ok "clinical_class <- narrative for a 03_ row (derived from the bucket number)" \
  || no "clinical_class is $(jget "$INV" "d['files'][0].get('clinical_class')")"
[ "$(jget "$INV" "d['files'][0]['text_layer_kind']")" = "not_applicable" ] \
  && ok "text_layer_kind <- not_applicable for a native_text row (never a claim about pixels)" \
  || no "text_layer_kind is $(jget "$INV" "d['files'][0].get('text_layer_kind')")"

RD="$D/readiness.json"
[ "$(jget "$RD" "d['schema_version']")" = "3" ] \
  && ok "readiness.json schema_version bumped \"2\" → \"3\"" \
  || no "readiness schema_version is $(jget "$RD" "d.get('schema_version')")"
[ "$(jget "$RD" "d['projection_coverage']['per_source'][0]['unprojected_field_classes']")" \
  = "['unknown']" ] \
  && ok "projection_coverage skeleton is the CONSERVATIVE ['unknown'], never []" \
  || no "unprojected_field_classes is $(jget "$RD" "d['projection_coverage']['per_source'][0].get('unprojected_field_classes')")"
[ "$(jget "$RD" "d['projection_coverage']['per_source'][0]['source_id']")" = "s1" ] \
  && ok "…and it covers the archive's source_id (per_source is keyed to the inventory)" \
  || no "per_source does not name s1"
[ "$(jget "$RD" "d['projection_coverage']['summary']['sources_fully_projected']")" = "0" ] \
  && ok "…with sources_fully_projected 0 — a migration measured nothing, so it claims nothing" \
  || no "summary claims sources were fully projected"

# the bucket→class map itself, on a fixture that exercises every mapped number plus two
# that are deliberately NOT mapped. 06/07/05/04 are the four classes the downstream
# floors key off, so getting one of them wrong is the difference between a gate that
# runs and a gate that silently does not.
echo "=== C2. bucket number → clinical_class over the whole map ==="
M="$tmp/map"
mkdir -p "$M"
python3 - "$M" <<'PYEOF'
import json, sys, pathlib
rows, buckets = [], [
    ("06", "06_分子与组学/NGS报告"), ("07", "07_检验/血常规"),
    ("05", "05_影像/CT"), ("04", "04_诊断与分期/病理报告"),
    ("01", "01_身份与基础信息/人口学"), ("03", "03_病程与叙事文书/出院小结"),
    ("14", "14_患者自管补充/日记"), ("15", "15_未分类资料/whatever"),
    ("99", "99_无关文件"),
]
for i, (nn, path) in enumerate(buckets, 1):
    rows.append({
        "file_id": f"f{i}", "source_id": f"s{nn}", "original_path": f"u{i}.txt",
        "raw_path": f"raw/incoming/u{i}.txt", "page_range": None,
        "sidecar_path": f"{path}/x.md", "bucket_path": path,
        "modality": "text", "read_mode": "native_text" if nn != "99" else "stub_unreadable",
        "extractor_provenance": {"engine": "e", "version": "3.0",
                                 "raw_output_ref": None, "llm_role": "none"},
        "high_risk_review_status": "not_applicable",
        "adapter": "text_payload", "persist": True,
    })
pathlib.Path(sys.argv[1], "source_inventory.json").write_text(
    json.dumps({"schema": "source_inventory_v2", "patient_dir": ".",
                "generated_at": "2026-01-02T00:00:00Z", "files": rows},
               ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
python3 "$MIGRATE" "$M" --run-id migrate-map >/dev/null 2>&1
class_of() { jget "$M/source_inventory.json" \
  "next(r['clinical_class'] for r in d['files'] if r['source_id']=='s$1')"; }
for spec in "06 molecular" "07 lab" "05 imaging" "04 pathology" \
            "01 narrative" "03 narrative" "14 narrative" "15 unknown" "99 unknown"; do
  set -- $spec
  [ "$(class_of "$1")" = "$2" ] && ok "bucket ${1}_ → clinical_class=$2" \
    || no "bucket ${1}_ mapped to $(class_of "$1"), expected $2"
done
[ "$(jget "$M/source_inventory.json" \
      "next(r['kind'] for r in d['files'] if r['source_id']=='s99')")" = "unreadable" ] \
  && ok "read_mode=stub_unreadable → kind=unreadable (not 'known')" \
  || no "a stub_unreadable row was migrated as known"

# ===========================================================================
# D. the conversion is recorded (A40)
# ===========================================================================
echo "=== D. update_log.json provenance ==="

LOG="$D/update_log.json"
[ -f "$LOG" ] && ok "update_log.json exists after the migration" || no "no update_log.json written"
[ "$(jget "$LOG" "sum(1 for r in d['runs'] if r.get('run_mode')=='migration')")" = "1" ] \
  && ok "runs[] carries exactly one entry with run_mode: \"migration\"" \
  || no "no run_mode=migration entry: $(jget "$LOG" "[r.get('run_mode') for r in d['runs']]")"
[ "$(jget "$LOG" "next(r['run_id'] for r in d['runs'] if r['run_mode']=='migration')")" \
  = "migrate-test" ] \
  && ok "…under the run_id it was given (--run-id is honoured, not invented)" \
  || no "run_id not recorded"
[ "$(jget "$LOG" "next(r['added_sources'] for r in d['runs'] if r['run_mode']=='migration')")" \
  = "[]" ] \
  && ok "…with added_sources [] — a migration reads no new source text" \
  || no "the migration entry claims it added sources"
jget "$LOG" "next(r.get('note','') for r in d['runs'] if r['run_mode']=='migration')" \
  | grep -q 'INFERRED' \
  && ok "…and the note says the fields were INFERRED, not observed" \
  || no "the log does not record that the values are inferences"

# ===========================================================================
# E. NEGATIVE — --dry-run writes nothing at all
# ===========================================================================
echo "=== E. --dry-run is inert ==="

DR="$tmp/dry"
mk_v3 "$DR"
snap() { (cd "$1" && find . -type f | LC_ALL=C sort | xargs shasum -a 256); }
snap "$DR" > "$tmp/before.sha"

python3 "$MIGRATE" "$DR" --run-id migrate-dry --dry-run >"$tmp/dry.out" 2>&1; dry_rc=$?
[ "$dry_rc" -eq 0 ] && ok "--dry-run exits 0" || no "--dry-run exited $dry_rc"
grep -q 'would change' "$tmp/dry.out" \
  && ok "…and it REPORTS the changes it would make (otherwise there is nothing to review)" \
  || no "--dry-run printed no plan: $(cat "$tmp/dry.out")"

snap "$DR" > "$tmp/after.sha"
diff -q "$tmp/before.sha" "$tmp/after.sha" >/dev/null \
  && ok "every file in the archive is BYTE-IDENTICAL before and after --dry-run" \
  || no "--dry-run modified the archive: $(diff "$tmp/before.sha" "$tmp/after.sha")"
# the archive arrives with a run history already in it (B7 makes update_log.json a
# required product), so "no file" is no longer the observable. The observable is that
# the log is UNCHANGED: still one run, and none of them a migration.
[ "$(jget "$DR/update_log.json" "len(d['runs'])")" = "1" ] \
  && ok "…and update_log.json still holds exactly its one pre-existing run" \
  || no "--dry-run appended to update_log.json"
[ "$(jget "$DR/update_log.json" "any(r.get('run_mode')=='migration' for r in d['runs'])")" = "False" ] \
  && ok "…with no run_mode: migration row among them (a dry run is not a run)" \
  || no "--dry-run recorded itself as a migration"
[ "$(jget "$DR/source_inventory.json" "d.get('scheme_version')")" = "3" ] \
  && ok "…the inventory still declares scheme_version 3 (still legacy, as promised)" \
  || no "--dry-run bumped scheme_version"

# ===========================================================================
# F. NEGATIVE — the migration refuses what it cannot convert
# ===========================================================================
echo "=== F. refusals ==="

E1="$tmp/empty"; mkdir -p "$E1"
python3 "$MIGRATE" "$E1" >"$tmp/e1.out" 2>&1
[ $? -eq 1 ] && ok "a directory with no source_inventory.json → exit 1" \
  || no "a directory with nothing to migrate did not fail"
grep -q 'not found' "$tmp/e1.out" && ok "…and says which file is missing" \
  || no "missing-inventory reason not stated"

E2="$tmp/future"; mk_v3 "$E2"
python3 - "$E2/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["scheme_version"] = 5
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
python3 "$MIGRATE" "$E2" >"$tmp/e2.out" 2>&1
[ $? -eq 1 ] && ok "an unexpected scheme_version (5) → exit 1, never a silent downgrade" \
  || no "scheme_version 5 was migrated anyway"
grep -q 'unexpected scheme_version' "$tmp/e2.out" && ok "…and names the value it refused" \
  || no "refusal reason not stated"

E3="$tmp/broken"; mkdir -p "$E3"
printf '{not json' > "$E3/source_inventory.json"
python3 "$MIGRATE" "$E3" >"$tmp/e3.out" 2>&1
[ $? -eq 1 ] && ok "an unparseable source_inventory.json → exit 1 (never 'nothing to do')" \
  || no "a broken inventory was treated as migratable"

E4="$tmp/already"
mk_v3 "$E4"
python3 "$MIGRATE" "$E4" --run-id migrate-once >/dev/null 2>&1
python3 "$MIGRATE" "$E4" --run-id migrate-twice >"$tmp/e4.out" 2>&1
[ $? -eq 0 ] && ok "re-running on an already-v4 archive → exit 0 (idempotent, not an error)" \
  || no "the second migration failed"
grep -q 'nothing to do' "$tmp/e4.out" && ok "…and it says nothing to do" \
  || no "second run did not report a no-op: $(cat "$tmp/e4.out")"
# one pre-existing run + the FIRST migration = 2. The second migration must add
# nothing: an append-only log that grows on every no-op turns "how did this archive
# come to be" into noise, and noise is what nobody reads.
[ "$(jget "$E4/update_log.json" "len(d['runs'])")" = "2" ] \
  && ok "…and it did NOT append a second migration entry to update_log.json" \
  || no "a no-op migration still wrote a run entry"
[ "$(jget "$E4/update_log.json" "sum(1 for r in d['runs'] if r.get('run_mode')=='migration')")" = "1" ] \
  && ok "…exactly one run_mode: migration row survives two invocations" \
  || no "the migration recorded itself twice"

python3 "$MIGRATE" "$tmp/does-not-exist" >/dev/null 2>&1
[ $? -eq 2 ] && ok "a patient_dir that is not a directory → exit 2 (bad invocation)" \
  || no "a missing patient_dir did not exit 2"
python3 "$MIGRATE" "$tmp/arch" --run-id '../escape' >/dev/null 2>&1
[ $? -eq 2 ] && ok "a path-traversing --run-id → exit 2 (run ids are path components)" \
  || no "'../escape' was accepted as a run id"

# ---------------------------------------------------------------------------
echo
echo "== migrate-v3-to-v4: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
