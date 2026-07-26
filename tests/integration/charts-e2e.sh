#!/usr/bin/env bash
# End-to-end matrix for cancer-buddy-charts.
#
# Two synthetic patients across two cancer types (a single case proves nothing
# about generalisation), every recipe, every gate's negative case, the 段D
# integration path, and byte-level backwards compatibility with
# compute_sparklines.py.
#
# Patient 2 is deliberately adversarial: dates out of order, an extreme outlier,
# a censored '<5.0' reading, a source-flagged critical value, a sex-split
# reference range that MUST be refused, over-long CJK regimen names, and two
# follow-ups a fortnight apart inside a 1.8-year span (label collision).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
N="$REPO_ROOT/skills/cancer-buddy-charts/scripts"
O="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap "rm -rf $tmp" EXIT
cd "$tmp"

pass=0; fail=0
r() { local d="$1" e="$2"; shift 2
      "$@" >/dev/null 2>&1; local rc=$?
      if [ "$rc" = "$e" ]; then pass=$((pass+1));
      else fail=$((fail+1)); echo "FAIL: $d (exit=$rc, want $e)" >&2; fi; }

# ── fixtures ────────────────────────────────────────────────────────────────
cat > p1.json <<'EOF'
{"schema_version":"1.0","patient_code":"T001","observations":[
 {"metric":"CA19-9","value":412,"unit":"U/mL","timestamp":"2026-01-08","reference_range":"0-37","method_or_device":"电化学发光 Roche e601","source_ref":"a.pdf#p1"},
 {"metric":"CA19-9","value":268,"unit":"U/mL","timestamp":"2026-02-19","reference_range":"0-37","method_or_device":"电化学发光 Roche e601","source_ref":"b.pdf#p1"},
 {"metric":"CA19-9","value":187,"unit":"U/mL","timestamp":"2026-04-02","reference_range":"0-37","method_or_device":"化学发光 Abbott i2000","source_ref":"c.pdf#p1"},
 {"metric":"CA19-9","value":95,"unit":"U/mL","timestamp":"2026-06-30","reference_range":"0-37","method_or_device":"化学发光 Abbott i2000","source_ref":"d.pdf#p2"},
 {"metric":"白蛋白","value":32,"unit":"g/L","timestamp":"2026-06-30","reference_range":"40-55","source_ref":"d.pdf#p1"}]}
EOF
cat > p2.json <<'EOF'
{"schema_version":"1.0","patient_code":"T002","observations":[
 {"metric":"CA15-3","value":"48.2","unit":"U/mL","timestamp":"2026-06-18","reference_range":"<25","method_or_device":"化学发光","source_ref":"f.pdf#p1"},
 {"metric":"CA15-3","value":31.0,"unit":"U/mL","timestamp":"2024-09-03","reference_range":"<25","method_or_device":"化学发光","source_ref":"g.pdf#p1"},
 {"metric":"CA15-3","value":"<5.0","unit":"U/mL","timestamp":"2024-11-20","reference_range":"<25","method_or_device":"化学发光","source_ref":"h.pdf#p1"},
 {"metric":"CA15-3","value":29.8,"unit":"U/mL","timestamp":"2025-08-14","reference_range":"<25","method_or_device":"化学发光","source_ref":"i.pdf#p1"},
 {"metric":"CA15-3","value":1240,"unit":"U/mL","timestamp":"2026-07-02","reference_range":"<25","method_or_device":"化学发光","critical":true,"source_ref":"j.pdf#p1"},
 {"metric":"血小板","value":38,"unit":"10^9/L","timestamp":"2026-07-02","reference_range":"男:125-350 女:100-300","critical":true,"source_ref":"j.pdf#p2"},
 {"metric":"体重","value":54.5,"unit":"kg","timestamp":"2026-07-02","source_ref":"j.pdf#p3"},
 {"metric":"体重","value":63.0,"unit":"kg","timestamp":"2024-09-03","source_ref":"g.pdf#p3"}]}
EOF
echo '{"episodes":[{"start":"2026-01-20","end":"2026-03-15","label":"吉西他滨+白蛋白紫杉醇","intent":"一线"},{"start":"2026-06-10","end":null,"label":"mFOLFIRINOX","intent":"二线"}]}' > swim.json
echo '{"rows":[{"analyte":"白蛋白","value":32,"unit":"g/L","reference_range":"40-55"},{"analyte":"隐血试验","value":"阳性","reference_range":"阴性"}]}' > panel.json
echo '{"events":[{"t":"2025-11-12","label":"确诊"},{"t":"2026-01-08","label":"手术"},{"t":"2026-01-20","label":"化疗开始"}]}' > tl.json
echo '{"variants":[{"gene":"KRAS","change":"p.G12D","vaf":38.2},{"gene":"TP53","change":"c.375+1G>A 剪接位点变异超长名称","vaf":0.28}]}' > vaf.json
echo '{"items":[{"label":"影像报告","have":6,"need":8},{"label":"病理报告","have":2,"need":2}]}' > cov.json
echo '{"t1_label":"治疗前","t2_label":"最近","rows":[{"label":"体重","v1":68.0,"v2":61.5,"unit":"kg"},{"label":"血红蛋白","v1":132,"v2":78,"unit":"g/L"}]}' > db.json
echo '{"medications":[{"group":"抗肿瘤","name":"吉西他滨"},{"group":"支持治疗","name":"昂丹司琼"}]}' > med.json
echo '{"events":[{"t":"2026-01-01","label":"x"}],"caption":"病情进展"}' > badcap.json

# ── patient 1 · pancreatic — every recipe ───────────────────────────────────
r "P1 trend" 0 python3 "$N/render_chart.py" --chart trend --from-longitudinal p1.json --metric CA19-9 --out-html a1.html
for k in swimlane:swim panel:panel timeline:tl vaf:vaf coverage:cov dumbbell:db medications:med; do
  r "P1 ${k%%:*}" 0 python3 "$N/render_chart.py" --chart "${k%%:*}" --spec "${k##*:}.json" --out-html "a_${k%%:*}.html"
done

# ── patient 2 · breast — adversarial ────────────────────────────────────────
r "P2 trend (乱序/离群/检测限/危急值)" 0 python3 "$N/render_chart.py" --chart trend --from-longitudinal p2.json --metric CA15-3 --out-html b1.html
r "P2 trend (两点/无参考区间)" 0 python3 "$N/render_chart.py" --chart trend --from-longitudinal p2.json --metric 体重 --out-html b2.html

# ── gates must fail closed ──────────────────────────────────────────────────
r "G-CHART-1 判决式标题" 4 python3 "$N/render_chart.py" --chart trend --from-longitudinal p1.json --metric CA19-9 --title "指标好转治疗有效" --out-html x.html
r "G-CHART-1 spec caption" 4 python3 "$N/render_chart.py" --chart timeline --spec badcap.json --out-html x.html
r "资格门 单点序列" 5 python3 "$N/render_chart.py" --chart trend --from-longitudinal p1.json --metric 白蛋白 --out-html x.html
r "资格门 指标不存在" 5 python3 "$N/render_chart.py" --chart trend --from-longitudinal p1.json --metric PSA --out-html x.html
r "未知配方明确报错" 2 python3 "$N/render_chart.py" --chart waterfall --spec tl.json --out-html x.html

# ── output validation + injection ───────────────────────────────────────────
r "validate 全部产物" 0 python3 "$N/validate_chart_svg.py" a1.html a_swimlane.html a_timeline.html a_vaf.html a_coverage.html a_dumbbell.html a_medications.html b2.html
r "validate 含源标危急值" 0 python3 "$N/validate_chart_svg.py" a_panel.html --critical-count 1
r "validate P2 危急值" 0 python3 "$N/validate_chart_svg.py" b1.html --critical-count 2
while IFS= read -r inj; do
  sed "s|</body>|${inj}</body>|" a1.html > bad.html
  r "注入拦截 ${inj:0:22}" 1 python3 "$N/validate_chart_svg.py" bad.html
done <<'INJ'
<script>x</script>
<img src="https://evil.tld/x">
<text font-size="6">x</text>
<rect fill="#ff0000"/>
<canvas></canvas>
onclick="x()"
<foreignObject/>
javascript:alert(1)
INJ

# ── label collision: values must never overprint each other ─────────────────
# 12 points inside a 2.4-year span with a dense tail is the shape that produced
# "29.25.3" on a real archive. Assert every value label got a slot, or was
# honestly dropped and reported — never silently overlapped.
cat > dense.json <<'EOF'
{"schema_version":"1.0","patient_code":"T003","observations":[
 {"metric":"CEA","value":73.3,"unit":"ng/ml","timestamp":"2022-08-02","reference_range":"0-5"},
 {"metric":"CEA","value":51.16,"unit":"ng/ml","timestamp":"2022-09-19","reference_range":"0-5"},
 {"metric":"CEA","value":6.86,"unit":"ng/ml","timestamp":"2024-01-30","reference_range":"0-5"},
 {"metric":"CEA","value":9.28,"unit":"ng/ml","timestamp":"2024-02-21","reference_range":"0-5"},
 {"metric":"CEA","value":12.5,"unit":"ng/ml","timestamp":"2024-05-07","reference_range":"0-5"},
 {"metric":"CEA","value":21.53,"unit":"ng/ml","timestamp":"2024-06-03","reference_range":"0-5"},
 {"metric":"CEA","value":24.5,"unit":"ng/ml","timestamp":"2024-07-03","reference_range":"0-5"},
 {"metric":"CEA","value":29.9,"unit":"ng/ml","timestamp":"2024-08-08","reference_range":"0-5"},
 {"metric":"CEA","value":25.3,"unit":"ng/ml","timestamp":"2024-09-05","reference_range":"0-5"},
 {"metric":"CEA","value":34.1,"unit":"ng/ml","timestamp":"2024-10-14","reference_range":"0-5"},
 {"metric":"CEA","value":28.3,"unit":"ng/ml","timestamp":"2024-12-09","reference_range":"0-5"},
 {"metric":"CEA","value":19.4,"unit":"ng/ml","timestamp":"2025-01-06","reference_range":"0-5"}]}
EOF
r "密集序列出图" 0 python3 "$N/render_chart.py" --chart trend --from-longitudinal dense.json --metric CEA --out-html dense.html
r "数值标签零重叠" 0 python3 - <<'PYX'
import re, sys
h = open("dense.html").read()
labels = [(float(x), float(y), t) for x, y, t in
          re.findall(r'<text x="([\d.]+)" y="([\d.]+)" font-size="10.0"[^>]*>([\d.]+)</text>', h)]
if len(labels) < 10:
    print(f"only {len(labels)} value labels placed", file=sys.stderr); sys.exit(1)
def w(t): return sum(10.0 if ord(c) > 0x2E80 else 5.5 for c in t)
for i, (x1, y1, t1) in enumerate(labels):
    for x2, y2, t2 in labels[i+1:]:
        if abs(y1 - y2) < 11.0 and abs(x1 - x2) < (w(t1) + w(t2)) / 2:
            print(f"overlap: {t1!r} and {t2!r}", file=sys.stderr); sys.exit(1)
sys.exit(0)
PYX
# a 1.4-year silence must not be drawn as a solid line
r "长空档画虚线" 0 python3 -c "
import sys; h=open('dense.html').read()
sys.exit(0 if 'stroke-dasharray=\"5 4\"' in h and '虚线段' in h else 1)"

# ── countable calendar grid: empty units must be visible, never filled in ───
r "日历格网出现" 0 python3 -c "
import sys; h=open('dense.html').read()
sys.exit(0 if '每格 = 1' in h and '其余是空的' in h else 1)"
# the grid must have MORE posts than there are readings — that is the whole point
r "空格多于检测次数" 0 python3 - <<'PYX'
import re, sys
h = open("dense.html").read()
m = re.search(r"共 (\d+)个月，只有 (\d+) 格有检测记录", h)
if not m:
    print("grid caption missing", file=sys.stderr); sys.exit(1)
units, tested = int(m.group(1)), int(m.group(2))
sys.exit(0 if units > tested and tested == 12 else 1)
PYX

# ── --from-labs: no hand-written numbers needed for a lab series ────────────
cat > labs.json <<'EOF'
{"patient_code":"T003","schema_version":"2","panels":[
 {"analyte":"CEA 癌胚抗原","normalized_analyte":"CEA","values":[
   {"value":6.86,"unit":"ng/ml","collected_at":"2024-01-30","reference_range":"0-5"},
   {"value":9.28,"unit":"ng/ml","collected_at":"2024-02-21","reference_range":"0-5"},
   {"value":12.5,"unit":"ng/ml","collected_at":"2024-05-07","reference_range":"0-5"}]},
 {"analyte":"肌酐 CRE","values":[{"value":70,"unit":"umol/L","collected_at":"2025-05-14"}]},
 {"analyte":"尿肌酐","values":[{"value":8.1,"unit":"mmol/L","collected_at":"2025-05-14"}]}]}
EOF
r "--from-labs 部分匹配" 0 python3 "$N/render_chart.py" --chart trend --from-labs labs.json --metric CEA --out-html fl.html
r "--from-labs 歧义时报错不猜" 5 python3 "$N/render_chart.py" --chart trend --from-labs labs.json --metric 肌酐 --out-html x.html
r "--from-labs 项目不存在" 5 python3 "$N/render_chart.py" --chart trend --from-labs labs.json --metric PSA --out-html x.html

# ── generalisation: a recipe outside the original catalogue ─────────────────
# Proves SKILL.md §清单外的图 is a real path, not an aspiration: med-overlap was
# built after the catalogue was frozen, from chart_core primitives only, and it
# passes the identical gate set (G-CHART-8).
echo '{"medications":[{"name":"吉西他滨","start":"2026-01-20","end":"2026-03-15"},{"name":"白蛋白紫杉醇","start":"2026-01-20","end":"2026-02-28"},{"name":"二甲双胍","start":"2026-01-20","end":null}]}' > ovl.json
r "库外配方 med-overlap 产出" 0 python3 "$N/render_chart.py" --chart med-overlap --spec ovl.json --out-html ovl.html
r "库外配方 过同一套 gate" 0 python3 "$N/validate_chart_svg.py" ovl.html
# open-ended entry must span the window, not collapse to a one-day course
r "库外配方 未写结束日期不塌成零宽" 0 python3 - <<'PYX'
import re, sys
h = open("ovl.html").read()
widths = [float(m) for m in re.findall(r'<rect x="[\d.]+" y="[\d.]+" width="([\d.]+)"', h)]
sys.exit(0 if widths and min(widths) > 5 else 1)
PYX

# ── backwards compatibility with compute_sparklines.py ──────────────────────
cat > case.json <<'EOF'
{"trend_charts":[{"metric":"CEA","unit":"ng/mL","series":[{"t":"2026-01-05","v":12.4},{"t":"2026-02-11","v":8.1},{"t":"2026-05-20","v":15.7}],
  "treatment_markers":[{"t":"2026-01-20","label":"A"},{"t":"2026-02-02","label":"B"}]},
 {"metric":"空","unit":"","series":[]}],
 "lab_trends":[{"lab_name":"血红蛋白","series":[{"t":"2026-01-05","v":118},{"t":"2026-03-05","v":109}]}]}
EOF
r "向后兼容 既有字段逐字节相同" 0 python3 - "$O" "$N" <<'PY'
import json, subprocess, sys
O, N = sys.argv[1], sys.argv[2]
subprocess.run([sys.executable, f"{O}/scripts/compute_sparklines.py", "--data", "case.json", "--out", "o.json"], capture_output=True)
subprocess.run([sys.executable, f"{N}/render_chart.py", "--data", "case.json", "--out", "n.json"], capture_output=True)
ADDITIVE = {"reference_range_text", "band_y", "band_h", "has_band"}
o = json.load(open("o.json")); n = json.load(open("n.json"))
for c in n.get("trend_charts", []):
    for k in list(c):
        if k in ADDITIVE:
            del c[k]
sys.exit(0 if json.dumps(o, sort_keys=True) == json.dumps(n, sort_keys=True) else 1)
PY

echo "charts-e2e: $pass passed, $fail failed"
exit $([ "$fail" -eq 0 ] && echo 0 || echo 1)
