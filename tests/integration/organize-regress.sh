#!/usr/bin/env bash
# organize v2.1 regression harness (synthetic in CI; real cases only on request).
#
#   1. The committed synthetic archive (tests/fixtures/organize-regress/syn-current/src)
#      equals what make_syn_current.py generates (drift guard).
#   2. That archive passes the whole terminal gate twice (the untrusted-content merge
#      must leave a readiness.json the next run accepts) and the repo profile check.
#   3. The deterministic scripts reproduce the fixture's recorded facts: the recorded
#      missing page, the recency fields, the eight lab candidates.
#   4. The same archive downgraded to the pre-v2.1 contract validates with WARNs only.
#   5. Optional: CB_REGRESS_CASES="case1=<organize dir>;case2=<dir>;…" replays real
#      archives READ-ONLY (copied to a temp dir without raw/). Only counts are printed —
#      never record text. Unset (CI) → skipped.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FIX="$REPO_ROOT/tests/fixtures/organize-regress"
SCRIPTS="$REPO_ROOT/skills/cancer-buddy-organize/scripts"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

# 1. drift guard
python3 "$FIX/make_syn_current.py" --out "$tmp/regen" >/dev/null
diff -r "$FIX/syn-current/src" "$tmp/regen" >/dev/null && ok || no "committed syn-current/src differs from make_syn_current.py output (regenerate it)"

# 2. whole gate, twice
cp -R "$FIX/syn-current/src" "$tmp/arch"
python3 "$SCRIPTS/fill_agents_md.py" "$tmp/arch" >/dev/null
python3 "$SCRIPTS/validate_structured_outputs.py" "$tmp/arch" >"$tmp/v1.out" 2>"$tmp/v1.err" && ok || { no "clean archive fails the gate"; cat "$tmp/v1.err" >&2; }
grep -q "current contract" "$tmp/v1.out" && ok || no "clean archive not recognised as current contract"
python3 "$SCRIPTS/validate_structured_outputs.py" "$tmp/arch" >/dev/null 2>&1 && ok || no "second gate run fails (gate wrote something it rejects)"
bash "$REPO_ROOT/scripts/validate-profile-schema.sh" "$tmp/arch" >/dev/null 2>&1 && ok || no "repo profile check rejects the clean archive"

# 3. deterministic scripts vs the fixture's recorded facts
python3 - "$SCRIPTS" "$tmp/arch" "$FIX" <<'PY' && ok || no "deterministic scripts disagree with the fixture"
import json, subprocess, sys
scripts, arch, fix = sys.argv[1:4]
sys.path.insert(0, scripts)
import page_completeness as pc, source_freshness as sf
mi = json.load(open(f"{arch}/missing_items.json", encoding="utf-8"))
gaps = pc.analyze(arch)["gaps"]
assert [(g["group_key"], g["pages_missing"]) for g in gaps] == \
       [(x["group_key"], x["pages_missing"]) for x in mi["document_gaps"] if x["gap_type"] == "missing_pages"], gaps
r = json.load(open(f"{arch}/readiness.json", encoding="utf-8"))
fr = sf.compute(arch)
assert (fr["latest_source_date"], fr["days_since_latest"]) == (r["latest_source_date"], r["days_since_latest"]), fr
p = subprocess.run([sys.executable, f"{scripts}/pair_lab_columns.py", "--text", f"{fix}/syn-lab-columns/src/linear.txt"],
                   capture_output=True, text=True)
pairs = json.loads(p.stdout)["pairs"]
labs = json.load(open(f"{arch}/labs.json", encoding="utf-8"))
assert [x["candidate_value"] for x in pairs] == [pn["values"][0]["candidate_value"] for pn in labs["panels"]]
PY

# 4. legacy downgrade → WARN only
python3 - "$FIX" "$tmp/legacy" <<'PY' && ok || no "legacy archive does not validate with WARNs"
import sys
sys.path.insert(0, sys.argv[1])
import synlib
d = synlib.make_legacy(sys.argv[2])
rc, errs, warns = synlib.validate(d)
assert rc == 0, errs
assert any(w.startswith("legacy_schema:") for w in warns)
PY

# 5. optional real archives (read-only copies, counts only)
if [ -n "${CB_REGRESS_CASES:-}" ]; then
  IFS=';' read -ra CASES <<< "$CB_REGRESS_CASES"
  for spec in "${CASES[@]}"; do
    name="${spec%%=*}"; dir="${spec#*=}"
    [ -d "$dir" ] || { echo "SKIP $name: not a directory (path withheld)"; continue; }
    dst="$tmp/real-$name"
    mkdir -p "$dst"
    (cd "$dir" && tar --exclude='./raw' --exclude='./smtb_runs' -cf - .) | (cd "$dst" && tar -xf -)
    python3 "$SCRIPTS/validate_structured_outputs.py" "$dst" >/dev/null 2>"$tmp/$name.err" && rc=0 || rc=$?
    nerr=$(grep -c '^ERROR:' "$tmp/$name.err" || true); nwarn=$(grep -c '^WARN:' "$tmp/$name.err" || true)
    gaps=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPTS'); import page_completeness as pc; print(len(pc.analyze('$dst')['gaps']))")
    days=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPTS'); import source_freshness as sf; print(sf.compute('$dst')['days_since_latest'])")
    echo "REAL $name: validator rc=$rc errors=$nerr warns=$nwarn page_gaps=$gaps days_since_latest=$days"
  done
else
  echo "SKIP: CB_REGRESS_CASES unset — real-archive replay not run"
fi

echo "organize-regress: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
