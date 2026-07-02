#!/usr/bin/env bash
# Unit tests for the 段D trend-visualization helpers:
#   - compute_sparklines.py    : series → inline-SVG geometry + anti-fabrication gate
#   - compute_version_delta.py : current vs previous snapshot → version_delta
# Deterministic synthetic fixtures (no LLM), so assertions are stable.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SPARK="$ORG/scripts/compute_sparklines.py"
DELTA="$ORG/scripts/compute_version_delta.py"

tmp="$(mktemp -d)"
trap "rm -rf $tmp" EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }
# jq-free field probe: pv <json> <python-expr over `d`> — expr passed as argv, not interpolated
pv() { python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(eval(sys.argv[2]))' "$1" "$2"; }

# ---------------------------------------------------------------------------
# source store shared by the sparkline tests (backs the anti-fabrication gate)
# ---------------------------------------------------------------------------
cat > "$tmp/longitudinal.json" <<'EOF'
{"schema_version":"longitudinal_observations_v1","patient_code":"PT-T","observations":[
 {"obs_type":"lab","metric":"CEA","value":8.2,"unit":"ng/mL","timestamp":"2025-11-03T00:00:00","modality":"structured","source_ref":"07_labs/a.md#L1"},
 {"obs_type":"lab","metric":"CEA","value":4.3,"unit":"ng/mL","timestamp":"2026-02-10T00:00:00","modality":"structured","source_ref":"07_labs/b.md#L1"},
 {"obs_type":"lab","metric":"CEA","value":2.1,"unit":"ng/mL","timestamp":"2026-06-20T00:00:00","modality":"structured","source_ref":"07_labs/c.md#L1"},
 {"obs_type":"lab","metric":"SCC","value":2.4,"unit":"ng/mL","timestamp":"2026-01-01T00:00:00","modality":"structured","source_ref":"07_labs/d.md#L1"},
 {"obs_type":"lab","metric":"SCC","value":1.81,"unit":"ng/mL","timestamp":"2026-06-20T00:00:00","modality":"structured","source_ref":"07_labs/e.md#L1"},
 {"obs_type":"lab","metric":"HGB","value":104,"unit":"g/L","timestamp":"2026-06-20T00:00:00","modality":"structured","source_ref":"07_labs/f.md#L1"}
]}
EOF

# ---------------------------------------------------------------------------
# 1. hero + labs enrichment: geometry, direction, endpoints, marker alignment
# ---------------------------------------------------------------------------
cat > "$tmp/d1.json" <<'EOF'
{"trend_charts":[{"metric":"CEA","unit":"ng/mL",
  "series":[{"t":"2025-11-03","v":8.2},{"t":"2026-02-10","v":4.3},{"t":"2026-06-20","v":2.1}],
  "treatment_markers":[{"t":"2026-02-01","label":"二线 FOLFOX"}],
  "interpretation":"下降"}],
 "lab_trends":[
  {"lab_name":"SCC","series":[{"t":"2026-01-01","v":2.4},{"t":"2026-06-20","v":1.81}],"current_value":"1.81"},
  {"lab_name":"HGB","series":[{"t":"2026-06-20","v":104}],"current_value":"104"}]}
EOF
python3 "$SPARK" --data "$tmp/d1.json" --longitudinal "$tmp/longitudinal.json" --out "$tmp/o1.json" >/dev/null 2>&1 && ok || no "1: enrichment should exit 0"
[ "$(pv "$tmp/o1.json" "d['trend_charts'][0]['direction']")" = "down" ] && ok || no "1: chart direction=down"
[ "$(pv "$tmp/o1.json" "d['trend_charts'][0]['point_count']")" = "3" ] && ok || no "1: chart point_count=3"
# first x at left pad (12), last x at W-pad (308); highest value → smallest y (top pad 12)
python3 - "$tmp/o1.json" <<'PY' && ok || no "1: chart endpoints + baseline geometry"
import json,sys
d=json.load(open(sys.argv[1]))["trend_charts"][0]
pts=[tuple(map(float,p.split(","))) for p in d["svg_points"].split()]
assert abs(pts[0][0]-12)<0.5, pts       # left pad
assert abs(pts[-1][0]-348)<0.5, pts     # W-pad (HERO_W 360 - pad 12)
assert abs(pts[0][1]-12)<0.5, pts       # v=8.2 is max → top
assert abs(pts[-1][1]-108)<0.5, pts     # v=2.1 is min → bottom
assert d["svg_area_d"].startswith("M ") and d["svg_area_d"].endswith("Z")
m=d["treatment_markers"][0]
mx=float(m["marker_x"])
assert 12 < mx < 348, mx                # marker sits within the plotted span
assert m["idx"]==1, m                   # 1-based marker index for the on-chart badge + legend
assert m["marker_date"]=="2026-02", m   # YYYY-MM for the legend/tooltip
PY
[ "$(pv "$tmp/o1.json" "d['lab_trends'][0]['direction']")" = "down" ] && ok || no "1: SCC direction=down"
[ "$(pv "$tmp/o1.json" "d['lab_trends'][1]['direction']")" = "single" ] && ok || no "1: HGB single point → direction=single"

# ---------------------------------------------------------------------------
# 2. edge cases: flat series, min==max, empty series
# ---------------------------------------------------------------------------
cat > "$tmp/d2.json" <<'EOF'
{"trend_charts":[{"metric":"CEA","series":[{"t":"2026-01-01","v":5},{"t":"2026-03-01","v":5},{"t":"2026-06-01","v":5}]}],
 "lab_trends":[{"lab_name":"EMPTY","series":[]}]}
EOF
python3 "$SPARK" --data "$tmp/d2.json" --out "$tmp/o2.json" >/dev/null 2>&1 && ok || no "2: edge enrichment exit 0"
[ "$(pv "$tmp/o2.json" "d['trend_charts'][0]['direction']")" = "flat" ] && ok || no "2: flat series → direction=flat"
python3 - "$tmp/o2.json" <<'PY' && ok || no "2: flat series sits on midline y=60"
import json,sys
d=json.load(open(sys.argv[1]))["trend_charts"][0]
ys=[float(p.split(",")[1]) for p in d["svg_points"].split()]
assert all(abs(y-60)<0.5 for y in ys), ys
PY
[ "$(pv "$tmp/o2.json" "d['lab_trends'][0]['svg_points']")" = "" ] && ok || no "2: empty series → empty svg_points"
[ "$(pv "$tmp/o2.json" "d['lab_trends'][0]['point_count']")" = "0" ] && ok || no "2: empty series → point_count 0"

# ---------------------------------------------------------------------------
# 3. anti-fabrication gate: a plotted value absent from the source store → exit 3
# ---------------------------------------------------------------------------
cat > "$tmp/d3.json" <<'EOF'
{"trend_charts":[{"metric":"CEA","series":[{"t":"2025-11-03","v":8.2},{"t":"2026-06-20","v":99.9}]}],"lab_trends":[]}
EOF
rc=0; python3 "$SPARK" --data "$tmp/d3.json" --longitudinal "$tmp/longitudinal.json" >/dev/null 2>"$tmp/g3.err" || rc=$?
[ "$rc" = "3" ] && ok || no "3: fabricated point should exit 3 (got $rc)"
grep -q "99.9" "$tmp/g3.err" && ok || no "3: gate should name the fabricated value"
# clean series with NO gate args → still exit 0 (gate is opt-in)
python3 "$SPARK" --data "$tmp/d3.json" --out "$tmp/o3.json" >/dev/null 2>&1 && ok || no "3: no-gate mode ignores integrity"
# a point backed ONLY by the real labs.json panels[] shape (not in longitudinal) → accepted
cat > "$tmp/labs_real.json" <<'EOF'
{"schema_version":"labs_v1","panels":[{"analyte":"ALB","unit":"g/L","reference_range":"40-55","values":[{"date":"2026-06-20","value":38,"flag":"L"}]}]}
EOF
cat > "$tmp/d3b.json" <<'EOF'
{"trend_charts":[],"lab_trends":[{"lab_name":"ALB","series":[{"t":"2026-06-20","v":38}],"current_value":"38"}]}
EOF
python3 "$SPARK" --data "$tmp/d3b.json" --labs "$tmp/labs_real.json" >/dev/null 2>&1 && ok || no "3: point backed by real panels[] labs.json should be ACCEPTED"
# same point NOT in any source → rejected (exit 3)
rc=0; python3 "$SPARK" --data "$tmp/d3b.json" --labs "$tmp/longitudinal.json" >/dev/null 2>&1 || rc=$?
[ "$rc" = "3" ] && ok || no "3: ALB absent from source → should exit 3 (got $rc)"

# ---------------------------------------------------------------------------
# 4. version_delta: lab moves + new treatment line + ECOG; and first-ever → null
# ---------------------------------------------------------------------------
cat > "$tmp/prev.json" <<'EOF'
{"report_date":"2026-05-12","lab_trends":[{"lab_name":"SCC","current_value":"2.4"},{"lab_name":"HGB","current_value":"120"}],
 "treatment_lines":[{"line_label":"一线","line_regimen":"XELOX"}],"ecog":"1"}
EOF
cat > "$tmp/cur.json" <<'EOF'
{"report_date":"2026-06-28","lab_trends":[{"lab_name":"SCC","current_value":"1.81"},{"lab_name":"HGB","current_value":"104"}],
 "treatment_lines":[{"line_label":"一线","line_regimen":"XELOX"},{"line_label":"二线","line_regimen":"FOLFIRI"}],"ecog":"0"}
EOF
python3 "$DELTA" --data "$tmp/cur.json" --prev "$tmp/prev.json" --out "$tmp/cd.json" >/dev/null 2>&1 && ok || no "4: delta exit 0"
[ "$(pv "$tmp/cd.json" "d['version_delta']['prev_date']")" = "2026-05-12" ] && ok || no "4: prev_date carried"
[ "$(pv "$tmp/cd.json" "len(d['version_delta']['items'])")" = "4" ] && ok || no "4: 4 changes (2 lab + 1 tx + 1 ecog)"
python3 - "$tmp/cd.json" <<'PY' && ok || no "4: SCC down + new FOLFIRI + ECOG down present"
import json,sys
items=json.load(open(sys.argv[1]))["version_delta"]["items"]
kinds={(i["kind"],i["dir"]) for i in items}
assert ("lab","down") in kinds
assert ("treatment","new") in kinds
assert ("status","down") in kinds
assert any("FOLFIRI" in i["text"] for i in items)
PY
python3 "$DELTA" --data "$tmp/cur.json" --out "$tmp/cn.json" >/dev/null 2>&1 && ok || no "4: no-prev exit 0"
[ "$(pv "$tmp/cn.json" "d['version_delta']")" = "None" ] && ok || no "4: first-ever summary → version_delta null"

# ---------------------------------------------------------------------------
# 5. backfill_lab_trends: populate from real panels[] shape when producer left []
# ---------------------------------------------------------------------------
BACKFILL="$ORG/scripts/backfill_lab_trends.py"
cat > "$tmp/bf_labs.json" <<'EOF'
{"schema_version":"labs_v1","panels":[
 {"analyte":"CEA","unit":"ng/ml","reference_range":"0-5.0","values":[{"date":"2025-01-20","value":11.78,"flag":"H"},{"date":"2026-06-02","value":550,"flag":"H"}]},
 {"analyte":"CA19-9","unit":"U/ml","reference_range":"0-27","values":[{"date":"2026-06-02","value":"<2.00","flag":null}]},
 {"analyte":"ALB","unit":"g/L","reference_range":"40-55","values":[{"date":"2026-06-02","value":38,"flag":null}]}]}
EOF
cat > "$tmp/bf_profile.json" <<'EOF'
{"locale":"zh"}
EOF
# empty lab_trends → backfilled from panels
echo '{"lab_trends":[]}' > "$tmp/bf_empty.json"
python3 "$BACKFILL" --data "$tmp/bf_empty.json" --labs "$tmp/bf_labs.json" --profile "$tmp/bf_profile.json" >/dev/null 2>&1 && ok || no "5: backfill exit 0"
[ "$(pv "$tmp/bf_empty.json" "len(d['lab_trends'])")" = "3" ] && ok || no "5: 3 rows backfilled from panels"
[ "$(pv "$tmp/bf_empty.json" "d['lab_trends'][0]['status_class']")" = "high" ] && ok || no "5: CEA flag=H → status high"
[ "$(pv "$tmp/bf_empty.json" "d['lab_trends'][0]['status_label']")" = "偏高" ] && ok || no "5: zh label 偏高"
[ "$(pv "$tmp/bf_empty.json" "d['lab_trends'][2]['status_class']")" = "low" ] && ok || no "5: ALB 38 in 40-55 → range compare low"
[ "$(pv "$tmp/bf_empty.json" "d['lab_trends'][1]['current_value']")" = "<2.00" ] && ok || no "5: string value '<2.00' preserved verbatim"
# already-populated lab_trends → NO-OP (LLM selection respected)
echo '{"lab_trends":[{"lab_name":"KEEP","current_value":"1"}]}' > "$tmp/bf_full.json"
python3 "$BACKFILL" --data "$tmp/bf_full.json" --labs "$tmp/bf_labs.json" --profile "$tmp/bf_profile.json" >/dev/null 2>&1
[ "$(pv "$tmp/bf_full.json" "d['lab_trends'][0]['lab_name']")" = "KEEP" ] && ok || no "5: populated lab_trends left untouched"
[ "$(pv "$tmp/bf_full.json" "len(d['lab_trends'])")" = "1" ] && ok || no "5: no-op keeps single row"
# no panels → no-op, stays empty
echo '{"lab_trends":[]}' > "$tmp/bf_none.json"
echo '{"panels":[]}' > "$tmp/bf_nopanels.json"
python3 "$BACKFILL" --data "$tmp/bf_none.json" --labs "$tmp/bf_nopanels.json" >/dev/null 2>&1
[ "$(pv "$tmp/bf_none.json" "len(d['lab_trends'])")" = "0" ] && ok || no "5: no panels → stays empty []"

# ---------------------------------------------------------------------------
# 6. treatment-marker badge de-collision: close markers stagger onto rows;
#    far markers share the top row. Also badge_pct present for the HTML tooltip.
# ---------------------------------------------------------------------------
cat > "$tmp/mk_close.json" <<'EOF'
{"trend_charts":[{"metric":"CEA","series":[{"t":"2025-11-01","v":8},{"t":"2026-06-01","v":2}],
  "treatment_markers":[{"t":"2026-01-01","label":"A"},{"t":"2026-01-06","label":"B"}]}],"lab_trends":[]}
EOF
python3 "$SPARK" --data "$tmp/mk_close.json" >/dev/null 2>&1 && ok || no "6: close-marker enrich exit 0"
python3 - "$tmp/mk_close.json" <<'PY' && ok || no "6: markers ~5d apart stagger to different rows"
import json,sys
ms=json.load(open(sys.argv[1]))["trend_charts"][0]["treatment_markers"]
assert ms[0]["badge_cy"] != ms[1]["badge_cy"], ms   # different rows → no overlap
assert all(m.get("badge_pct") for m in ms)          # HTML-tooltip x% present
PY
cat > "$tmp/mk_far.json" <<'EOF'
{"trend_charts":[{"metric":"CEA","series":[{"t":"2025-01-01","v":8},{"t":"2026-06-01","v":2}],
  "treatment_markers":[{"t":"2025-02-01","label":"A"},{"t":"2026-05-01","label":"B"}]}],"lab_trends":[]}
EOF
python3 "$SPARK" --data "$tmp/mk_far.json" >/dev/null 2>&1
python3 - "$tmp/mk_far.json" <<'PY' && ok || no "6: far-apart markers share the top row"
import json,sys
ms=json.load(open(sys.argv[1]))["trend_charts"][0]["treatment_markers"]
assert ms[0]["badge_cy"] == ms[1]["badge_cy"], ms   # same row (no needless stagger)
PY

# ---------------------------------------------------------------------------
echo "compute_sparklines / compute_version_delta / backfill_lab_trends unit tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
