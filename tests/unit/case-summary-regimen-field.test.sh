#!/usr/bin/env bash
# validate_case_summary_html.core_completeness_check — "当前方案" core field.
# treatment_lines.json carries its episodes under `episodes` (schema); the check read a
# stale `lines` key and could never fire. Episodes in the source + an empty
# treatment_lines table in the rendered summary data must now FAIL. Synthetic files.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT/skills/cancer-buddy-organize/scripts" "$tmp" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import validate_case_summary_html as vch
tmp = Path(sys.argv[2])
passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


_seq = [0]


def run(tl, rows):
    _seq[0] += 1
    d = tmp / f"c{_seq[0]:03d}"
    d.mkdir()
    (d / "profile.json").write_text(json.dumps({"summary": {}}), encoding="utf-8")
    (d / "treatment_lines.json").write_text(json.dumps(tl), encoding="utf-8")
    (d / "data.json").write_text(json.dumps({"treatment_lines": rows}), encoding="utf-8")
    errs: list[str] = []
    vch.core_completeness_check(str(d / "profile.json"), str(d / "data.json"), errs)
    return errs


ep = {"episodes": [{"episode_id": "EP-1", "regimen": "示例方案B"}]}
errs = run(ep, [])
check("episodes in source + empty summary table → FAIL", any("当前方案" in e for e in errs), str(errs))
check("episodes in source + rows in summary → pass", run(ep, [{"regimen": "示例方案B"}]) == [])
check("no episodes → pass", run({"episodes": []}, []) == [])
check("legacy `lines` key still honoured", any("当前方案" in e for e in run({"lines": [{"regimen": "x"}]}, [])))

print(f"case-summary-regimen-field: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
