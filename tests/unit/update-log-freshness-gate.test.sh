#!/usr/bin/env bash
# Unit tests for the update_log edit-trail freshness gate in
# validate_structured_outputs.py (CB-P2-1, O-04/O-09).
#
# The gate compares CONTENT HASHES, not mtimes (the mtime version false-fired on a
# plain `cp -R` and missed an edit that preserved the timestamp):
#   (a) every source_inventory files[].sha256 must be among the latest update_log
#       entry's inputs[].sha256 (and vice versa unless listed in removed[]);
#   (b) a file listed in the entry's outputs[] {file, sha256} whose bytes now hash
#       differently was edited outside the organize flow.
# Always an advisory WARN, never an ERROR. Deterministic synthetic fixtures, no LLM.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap "rm -rf $tmp" EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

# helper: run gate_update_log_freshness directly, print each collected warning
run_freshness() {
  python3 - "$ORG" "$1" <<'PY'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
warns = []
v.gate_update_log_freshness(pathlib.Path(sys.argv[2]), warns)
for w in warns:
    print(w)
PY
}

sha() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
H1=1111111111111111111111111111111111111111111111111111111111111111
H2=2222222222222222222222222222222222222222222222222222222222222222

write_inventory() {  # dir, sha...
  local d="$1"; shift
  python3 - "$d" "$@" <<'PY'
import json, sys
d, shas = sys.argv[1], sys.argv[2:]
rows = [{"source_id": f"s{i+1:03d}", "sha256": h} for i, h in enumerate(shas)]
json.dump({"schema": "source_inventory_v2.1", "files": rows}, open(d + "/source_inventory.json", "w"))
PY
}

# ===========================================================================
# 1. profile.json EDITED after the flow recorded its hash → WARN (not ERROR).
# ===========================================================================
s="$tmp/stale"
mkdir -p "$s"
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1","summary":{}}' > "$s/profile.json"
PHASH="$(sha "$s/profile.json")"
write_inventory "$s" "$H1"
cat > "$s/update_log.json" <<JSON
{"schema_version":"1","entries":[{"at":"2030-01-20T09:00:00Z","run_mode":"full","workers":[],
 "inputs":[{"source_id":"s001","sha256":"$H1"}],"outputs":[{"file":"profile.json","sha256":"$PHASH"}]}]}
JSON
echo '{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1","summary":{"primary":"hand edit"}}' > "$s/profile.json"
out="$(run_freshness "$s")"
echo "----- stale fixture output -----"; echo "${out:-<none>}"; echo "--------------------------------"
echo "$out" | grep -q 'update_log_freshness' && ok || no "hash-changed profile.json should WARN"
echo "$out" | grep -q 'edited outside the organize flow' && ok || no "WARN should name the edit-outside-flow cause"

# through the full entrypoint: printed as WARN, never as ERROR (advisory only)
python3 "$VAL" "$s" >/dev/null 2>"$tmp/stale.err" && rc=0 || rc=$?
grep -q 'WARN: update_log_freshness' "$tmp/stale.err" && ok || no "freshness gate must print as WARN in entrypoint"
grep -q 'ERROR: update_log_freshness' "$tmp/stale.err" && no "freshness gate must NOT be an ERROR (advisory only)" || ok

# ===========================================================================
# 2. mtime is irrelevant: identical bytes with a NEWER mtime → silent
#    (the old mtime gate false-fired here, e.g. after `cp -R`).
# ===========================================================================
f="$tmp/fresh"
mkdir -p "$f"
echo '{"schema":"cancer_buddy_profile_v3"}' > "$f/profile.json"
PHASH="$(sha "$f/profile.json")"
write_inventory "$f" "$H1"
cat > "$f/update_log.json" <<JSON
{"schema_version":"1","entries":[{"at":"2030-01-20T09:00:00Z","run_mode":"full","workers":[],
 "inputs":[{"source_id":"s001","sha256":"$H1"}],"outputs":[{"file":"profile.json","sha256":"$PHASH"}]}]}
JSON
touch -t 202607010900 "$f/update_log.json"
touch -t 202607011200 "$f/profile.json"      # newer mtime, same bytes
out="$(run_freshness "$f")"
[ -z "$out" ] && ok || no "same bytes, newer mtime must stay silent (got: $out)"

# ===========================================================================
# 3. an input in source_inventory that the latest entry never logged → WARN.
# ===========================================================================
u="$tmp/unlogged"
mkdir -p "$u"
write_inventory "$u" "$H1" "$H2"
cat > "$u/update_log.json" <<JSON
{"schema_version":"1","entries":[{"at":"2030-01-20T09:00:00Z","run_mode":"full","workers":[],
 "inputs":[{"source_id":"s001","sha256":"$H1"}]}]}
JSON
out="$(run_freshness "$u")"
echo "$out" | grep -q 'not in the latest update_log entry' && ok || no "unlogged inventory input should WARN (got: $out)"

# 3b. a logged input missing from the inventory without a removed[] record → WARN;
#     with removed[] → silent.
g="$tmp/gone"
mkdir -p "$g"
write_inventory "$g" "$H1"
cat > "$g/update_log.json" <<JSON
{"schema_version":"1","entries":[{"at":"2030-01-20T09:00:00Z","run_mode":"incremental","workers":[],
 "inputs":[{"source_id":"s001","sha256":"$H1"},{"source_id":"s009","sha256":"$H2"}]}]}
JSON
out="$(run_freshness "$g")"
echo "$out" | grep -q 'no longer in source_inventory' && ok || no "vanished logged input should WARN (got: $out)"
python3 - "$g/update_log.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["entries"][0]["removed"] = ["s009"]; json.dump(d, open(p, "w"))
PY
out="$(run_freshness "$g")"
[ -z "$out" ] && ok || no "removed[] input must stay silent (got: $out)"

# ===========================================================================
# 4. legacy update_log without hashes → one WARN (cannot be verified).
# ===========================================================================
l="$tmp/legacy"
mkdir -p "$l"
echo '{"schema_version":"1","patient_code":"PT-A1","entries":[{"at":"2030-02-14T08:00:00Z","run_mode":"full","phase":"phase2","input_count":3,"source_ids":["s001"],"summary":"x"}]}' > "$l/update_log.json"
out="$(run_freshness "$l")"
echo "$out" | grep -q 'records no content hashes' && ok || no "legacy hashless update_log should WARN once (got: $out)"
[ "$(echo "$out" | grep -c update_log_freshness)" -eq 1 ] && ok || no "legacy update_log should WARN exactly once"

# ===========================================================================
# 5. NO update_log.json / no entries — gate must skip silently.
# ===========================================================================
n="$tmp/no_log"
mkdir -p "$n"
echo '{"schema":"cancer_buddy_profile_v3"}' > "$n/profile.json"
out="$(run_freshness "$n")"
[ -z "$out" ] && ok || no "no update_log.json → gate must skip silently (got: $out)"

p="$tmp/no_entries"
mkdir -p "$p"
echo '{}' > "$p/update_log.json"
out="$(run_freshness "$p")"
[ -z "$out" ] && ok || no "update_log without entries → silent (got: $out)"

# ===========================================================================
# 6-8. outputs[] across entries: the hash to compare is the MOST RECENT outputs[] row
#      recording each file. A 段C conversation entry (inputs: [], run_mode
#      conversation_incremental) rewrites timeline.json and logs its new hash after a
#      full run; the full run's hash of it is then stale, not an outside edit.
# ===========================================================================
c="$tmp/segc"
mkdir -p "$c"
echo '{"events":["full run"]}' > "$c/timeline.json"
echo '{"summary":"full run"}' > "$c/patient_summary.json"
T1="$(sha "$c/timeline.json")"; S1="$(sha "$c/patient_summary.json")"
echo '{"events":["full run","段C turn"]}' > "$c/timeline.json"
T2="$(sha "$c/timeline.json")"
write_inventory "$c" "$H1"
cat > "$c/update_log.json" <<JSON
{"schema_version":"1","entries":[
 {"at":"2030-01-20T09:00:00Z","run_mode":"full","workers":[],"inputs":[{"source_id":"s001","sha256":"$H1"}],
  "outputs":[{"file":"timeline.json","sha256":"$T1"},{"file":"patient_summary.json","sha256":"$S1"}]},
 {"at":"2030-01-22T10:00:00Z","run_mode":"conversation_incremental","workers":[],"inputs":[],
  "outputs":[{"file":"timeline.json","sha256":"$T2"}]}]}
JSON
out="$(run_freshness "$c")"
# 7. positive: the 段C entry's hash names the current timeline.json → silent
[ -z "$out" ] && ok || no "full run + later 段C entry carrying the new timeline.json hash must stay silent (got: $out)"
# 8. regression: patient_summary.json is recorded only by the full run and untouched → no WARN for it
echo "$out" | grep -q 'patient_summary.json' && no "file recorded only in the full-run entry and untouched must not WARN" || ok
# 6. negative: a hand edit of timeline.json after the last entry that recorded it → WARN
echo '{"events":["full run","段C turn","hand edit"]}' > "$c/timeline.json"
out="$(run_freshness "$c")"
echo "$out" | grep -q 'timeline.json edited outside the organize flow' && ok \
  || no "hand edit after the latest entry recording timeline.json should WARN (got: $out)"
echo "$out" | grep -q 'patient_summary.json' && no "untouched patient_summary.json must stay silent (got: $out)" || ok
# the input check still runs against the latest entry that reconciled inputs (the full run),
# not the 段C entry with inputs: [] — no false "inputs changed" WARN
echo "$out" | grep -q 'not in the latest update_log entry' && no "段C entry (inputs: []) must not hide the full run's inputs" || ok

# ---------------------------------------------------------------------------
echo "update-log-freshness-gate: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
