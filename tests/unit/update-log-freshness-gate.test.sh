#!/usr/bin/env bash
# Unit tests for the CB-P2-1 update_log edit-trail freshness gate in
# validate_structured_outputs.py.
#   - gate_update_log_freshness: update_log.json present AND profile.json mtime
#     newer than update_log.json → advisory WARN (never a hard FAIL).
# Deterministic fixtures with explicitly-stamped mtimes (touch -t), no LLM.
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

# ===========================================================================
# 1. STALE fixture — profile.json edited AFTER update_log.json → WARN.
# ===========================================================================
s="$tmp/stale"
mkdir -p "$s"
echo '{"schema":"update_log_v1"}' > "$s/update_log.json"
echo '{"schema":"cancer_buddy_profile_v3"}' > "$s/profile.json"
touch -t 202607010900 "$s/update_log.json"   # older
touch -t 202607011200 "$s/profile.json"      # newer (manual edit)
out="$(run_freshness "$s")"
echo "----- stale fixture output -----"
echo "${out:-<none>}"
echo "--------------------------------"
echo "$out" | grep -q 'update_log_freshness' && ok || no "stale profile.json should WARN"
echo "$out" | grep -q 'edited outside the organize flow' && ok || no "WARN should name the edit-outside-flow cause"

# stale fixture through the full entrypoint: must print as WARN, not ERROR, and
# must NOT by itself flip the exit code (advisory only).
python3 "$VAL" "$s" >/dev/null 2>"$tmp/stale.err" && rc=0 || rc=$?
grep -q 'WARN: update_log_freshness' "$tmp/stale.err" && ok || no "freshness gate must print as WARN in entrypoint"
grep -q 'ERROR: update_log_freshness' "$tmp/stale.err" && no "freshness gate must NOT be an ERROR (advisory only)" || ok

# ===========================================================================
# 2. FRESH fixture — update_log.json newer than profile.json → silent.
# ===========================================================================
f="$tmp/fresh"
mkdir -p "$f"
echo '{"schema":"cancer_buddy_profile_v3"}' > "$f/profile.json"
echo '{"schema":"update_log_v1"}' > "$f/update_log.json"
touch -t 202607010900 "$f/profile.json"      # older
touch -t 202607011200 "$f/update_log.json"   # newer (changelog written by flow)
out="$(run_freshness "$f")"
[ -z "$out" ] && ok || no "fresh fixture (update_log newer) must stay silent (got: $out)"

# 2b. equal mtimes → silent (a normal organize run writes both together)
e="$tmp/equal"
mkdir -p "$e"
echo '{}' > "$e/profile.json"
echo '{}' > "$e/update_log.json"
touch -t 202607011200 "$e/profile.json" "$e/update_log.json"
out="$(run_freshness "$e")"
[ -z "$out" ] && ok || no "equal mtimes must stay silent (got: $out)"

# ===========================================================================
# 3. NO update_log.json — gate must skip silently (first run / no changelog).
# ===========================================================================
n="$tmp/no_log"
mkdir -p "$n"
echo '{"schema":"cancer_buddy_profile_v3"}' > "$n/profile.json"
touch -t 202607011200 "$n/profile.json"
out="$(run_freshness "$n")"
[ -z "$out" ] && ok || no "no update_log.json → gate must skip silently (got: $out)"

# 3b. no profile.json (only update_log) → also silent (other gates own that case)
p="$tmp/no_profile"
mkdir -p "$p"
echo '{}' > "$p/update_log.json"
out="$(run_freshness "$p")"
[ -z "$out" ] && ok || no "no profile.json → gate must skip silently (got: $out)"

# ---------------------------------------------------------------------------
echo "update-log-freshness-gate: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
