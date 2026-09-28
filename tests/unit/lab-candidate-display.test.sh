#!/usr/bin/env bash
# O-03 downstream guard: a lab result bound only by linear position (candidate) or whose
# pairing was refused must never be displayed as the patient's value by
# backfill_lab_trends.py (case-summary lab rows), nor count as chart-backing data.
# Synthetic labs.json built from the committed fixture.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/skills/cancer-buddy-organize/scripts"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$SCRIPTS" "$REPO_ROOT" "$tmp" <<'PY'
import copy, json, subprocess, sys
from pathlib import Path
scripts, repo, tmp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, scripts)
import backfill_lab_trends as bl

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


labs = json.loads((repo / "tests/fixtures/organize-regress/syn-current/src/labs.json").read_text(encoding="utf-8"))
data = {"lab_trends": []}
n = bl.backfill(copy.deepcopy(data), labs)
check("fixture: all 8 rows are position-paired candidates → no displayed lab row", n == 0, str(n))

confirmed = copy.deepcopy(labs)
v = confirmed["panels"][1]["values"][0]
v.update({"pairing_method": "native_table", "value": 118.2, "candidate_value": None, "pairing_confidence": "high"})
d = {"lab_trends": []}
bl.backfill(d, confirmed)
check("a confirmed (native_table) value is displayed", [r["lab_name"] for r in d["lab_trends"]] == [confirmed["panels"][1]["analyte"]]
      and d["lab_trends"][0]["current_value"] == "118.2个", str(d["lab_trends"]))

mixed = copy.deepcopy(labs)
p = mixed["panels"][1]
older = copy.deepcopy(p["values"][0])
older.update({"date": "2030-01-01", "pairing_method": "single_value", "value": 3.3, "raw_value": "3.3",
              "candidate_value": None, "pairing_confidence": None})
p["values"].insert(0, older)
d = {"lab_trends": []}
bl.backfill(d, mixed)
row = next(r for r in d["lab_trends"] if r["lab_name"] == p["analyte"])
check("a newer candidate never replaces the latest confirmed value", row["current_value"] == "3.3", str(row))
check("candidates never enter the series", [pt["v"] for pt in row["series"]] == [3.3], str(row["series"]))

legacy = copy.deepcopy(labs)
for pn in legacy["panels"]:
    for val in pn["values"]:
        for k in ("pairing_method", "candidate_value", "pairing_confidence", "pairing_note"):
            val.pop(k, None)
        val["value"] = 1.0
d = {"lab_trends": []}
check("legacy rows without pairing_method still display", bl.backfill(d, legacy) == 8)

# ---- a lab_trends row 段D already wrote: backfill only rewrites badges, so a candidate put
#      in current_value used to reach the case summary. It is now cleared (or replaced by
#      the latest CONFIRMED value), and compute_sparklines --labs rejects it outright.
cand = labs["panels"][2]["analyte"]
d = {"lab_trends": [{"lab_name": cand, "series": [], "current_value": "21.73"}]}
bl.backfill(d, labs)
check("existing row: candidate current_value cleared", d["lab_trends"][0]["current_value"] == "", str(d))
d = {"lab_trends": [{"lab_name": p["analyte"], "series": [], "current_value": "118.2"}]}
bl.backfill(d, mixed)
check("existing row: newest unconfirmed → latest confirmed value shown", d["lab_trends"][0]["current_value"] == "3.3", str(d))
bbox = copy.deepcopy(labs)
bbox["panels"][0]["values"][0].update({"pairing_method": "bbox", "pairing_confidence": "low"})
check("a candidate_value row is unconfirmed whatever the method (bbox)", bl.backfill({"lab_trends": []}, bbox) == 0)

spark = Path(scripts) / "compute_sparklines.py"
labs_path = tmp / "labs.json"
labs_path.write_text(json.dumps(labs, ensure_ascii=False), encoding="utf-8")
def spark_rc(rows):
    dp = tmp / "csd.json"
    dp.write_text(json.dumps({"trend_charts": [], "lab_trends": rows}, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([sys.executable, str(spark), "--data", str(dp), "--labs", str(labs_path)],
                          capture_output=True, text=True)
r = spark_rc([{"lab_name": cand, "series": [], "current_value": "21.73"}])
check("sparklines gate: candidate as current_value → exit 3", r.returncode == 3 and "current_value '21.73'" in r.stderr, r.stderr)
r = spark_rc([{"lab_name": cand, "series": [{"t": "2030-01-15", "v": 21.73}], "current_value": ""}])
check("sparklines gate: candidate plotted in a series → exit 3", r.returncode == 3, r.stderr)
labs_path.write_text(json.dumps(confirmed, ensure_ascii=False), encoding="utf-8")
r = spark_rc([{"lab_name": confirmed["panels"][1]["analyte"], "series": [{"t": "2030-01-15", "v": 118.2}], "current_value": "118.2个"}])
check("sparklines gate: confirmed value (raw string with glyph) passes", r.returncode == 0, r.stderr)

print(f"lab-candidate-display: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
