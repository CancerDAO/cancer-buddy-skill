#!/usr/bin/env bash
# O-09 pre-write bucket whitelist (scripts/check_bucket_path.py) — the same function the
# terminal gate uses, so the whitelist has one implementation. The two negative paths
# are the off-taxonomy folders real runs only discovered at the final gate.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CHK="$REPO_ROOT/skills/cancer-buddy-organize/scripts/check_bucket_path.py"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

expect_reject() {
  if python3 "$CHK" "$1" >/dev/null 2>"$tmp/err"; then no "should reject: $1"; else
    rc=$?; [ "$rc" -eq 1 ] && ok || no "reject must exit 1 (got $rc): $1"; fi
}
expect_accept() {
  python3 "$CHK" "$1" >/dev/null 2>"$tmp/err" && ok || no "should accept: $1 ($(cat "$tmp/err"))"
}

# the two real-run violations
expect_reject "14_患者自管补充/患者自述"
grep -q '患者补充' "$tmp/err" && ok || no "rejection should name the pinned sub-buckets (患者补充)"
expect_reject "03_病程与叙事文书/既往资料摘录"
grep -q '既往档案摘录' "$tmp/err" && ok || no "rejection should list the pinned 既往档案摘录"
expect_reject "03_病程与叙事文书/既往资料摘录/2029-06-01_摘录.md"
# pinned paths (dir and file forms, zh and en slugs)
expect_accept "07_检验/其他"
expect_accept "03_病程与叙事文书/既往档案摘录"
expect_accept "03_病程与叙事文书/既往档案摘录/2029-06-01_既往档案摘录.md"
expect_accept "03_clinical_notes/prior-archive-digest"
expect_accept "05_影像/CT/2030-01-12_胸部CT_示例医院.md"
expect_accept "14_患者自管补充/conversation_notes"
expect_accept "99_无关文件/uncertain"
# other rejections
expect_reject "11_不良反应/x.md"
expect_reject "raw/s001.jpg"
expect_reject "/abs/05_影像/CT"
expect_reject "05_影像/../07_检验"
expect_reject "99_无关文件/misc"

# multiple paths: exit 1 when any is bad; --json report
python3 "$CHK" 07_检验/其他 14_患者自管补充/患者自述 --json >"$tmp/j" 2>/dev/null && no "mixed batch must exit 1" || ok
python3 - "$tmp/j" <<'PY' && ok || no "--json report shape"
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["ok"] is False and r["checked"] == 2 and len(r["violations"]) == 1
assert r["violations"][0]["path"] == "14_患者自管补充/患者自述"
PY

# importable + shared with the terminal gate
python3 - "$REPO_ROOT" <<'PY' && ok || no "importable API"
import sys
sys.path.insert(0, sys.argv[1] + "/skills/cancer-buddy-organize/scripts")
import check_bucket_path as c
tax = c.load_taxonomy()
assert c.bucket_path_violation("07_检验/其他", tax) is None
assert c.bucket_path_violation("03_病程与叙事文书/既往资料摘录", tax)
assert c.check_paths(["07_检验/其他", "13_其他专科检查"], tax)[0][0] == "13_其他专科检查"
PY

# terminal gate: the new pinned sub-bucket is accepted on disk; recorded inventory
# paths are checked too (current archive → ERROR)
if python3 -c "import jsonschema" 2>/dev/null; then
python3 - "$REPO_ROOT" "$tmp" <<'PY' && ok || no "validator bucket binding"
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib
tmp = Path(sys.argv[2])
d = synlib.make(tmp / "clean")
errs = []
import validate_structured_outputs as v
v.gate_bucket_taxonomy(d, errs)
assert errs == [], errs  # 03_病程与叙事文书/既往档案摘录 is pinned
bad = synlib.make(tmp / "bad", lambda d: synlib.edit_json(d, "source_inventory.json",
      lambda doc: doc["files"][4].__setitem__("bucket_path", "14_患者自管补充/患者自述")))
errs, _ = synlib.gate("gate_source_inventory", bad)
assert any("bucket_path: 14_患者自管补充/患者自述 is not a pinned sub-bucket" in e for e in errs), errs
PY
fi

echo "bucket-precheck: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
