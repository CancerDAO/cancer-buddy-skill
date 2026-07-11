#!/usr/bin/env bash
# E2E for the 段D trend-visualization pipeline, run through the REAL scripts +
# template (no LLM): build render-data → compute_version_delta → compute_sparklines
# → render_html_template → validate_case_summary_html. Multi-case, ≥2 cancer types:
#   A. CRC   — 3-pt CEA hero + treatment marker + version_delta (has a prior snapshot)
#   B. NSCLC — first-ever summary (no prior snapshot → delta strip hidden) + single-pt lab
#   C. edge  — no longitudinal data → empty trend_charts placeholder + empty lab_trends
#   D. multi — 2 featured trend_charts (skill-decided count) → 2 charts render side by side
# Each case must render AND pass every shape/print-safe invariant (exit 0).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
TMPL="$ORG/references/templates/case-summary.template.html"
SPARK="$ORG/scripts/compute_sparklines.py"
DELTA="$ORG/scripts/compute_version_delta.py"
RENDER="$ORG/scripts/render_html_template.py"
VALIDATE="$ORG/scripts/validate_case_summary_html.py"
cd "$ORG"

tmp="$(mktemp -d)"
trap "rm -rf $tmp" EXIT
pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

# shared locale scaffold (patient-independent)
I18N='{"html_lang":"zh-CN","doc_title":"病情简要总结","disclaimer":"仅用于临床交流参考，不替代主诊医生的判断","report_date_label":"报告日期","sec_identity":"患者标识","lbl_sex_age":"性别 / 年龄","lbl_hwbmi":"身高 / 体重 / BMI","lbl_ecog":"ECOG 体能评分","sec_summary":"病情概要","sec_stage":"分期 (TNM)","sec_trend":"关键趋势","sec_lesions":"主要病灶分布","sec_molecular":"核心分子检测","sec_labs":"实验室指标","sec_treatment":"治疗史","sec_path":"当前治疗路径","sec_caveats":"数据说明","delta_title":"自上次总结的变化","delta_vs":"对比","delta_none":"与上次总结相比，关键指标无变化","trend_none":"暂无足够时间点数据，补充随访化验后自动生成趋势","val_male":"男","val_female":"女","val_pending":"待主诊医生补充 / 资料缺失","val_ecog_inferred":"（推断，待主诊医生正式签署）","val_to_start":"待启动","footer_doc":"病情简要总结","brand_generated_by":"本报告由 CancerDAO 生成","brand_qr_hint":"扫码访问官网"}'

run_case() {  # $1=name $2=data.json $3=longitudinal(or "") $4=labs.json(or "") $5=prev(or "")
  local name="$1" data="$2" long="$3" labs="$4" prev="$5"
  local d="$tmp/$name"; mkdir -p "$d/case_summary_versions"
  cp "$data" "$d/.case_summary_data.json"
  [ -n "$prev" ] && cp "$prev" "$d/case_summary_versions/case_summary_data_2026-01-01.json"
  local pv; pv=$(ls -1 "$d/case_summary_versions/case_summary_data_"*.json 2>/dev/null | sort | tail -1 || true)
  python3 "$DELTA" --data "$d/.case_summary_data.json" ${pv:+--prev "$pv"} >/dev/null 2>&1 || { no "$name: version_delta failed"; return; }
  local la=""; [ -n "$long" ] && la="--longitudinal $long"
  local lb=""; [ -n "$labs" ] && lb="--labs $labs"
  python3 "$SPARK" --data "$d/.case_summary_data.json" $la $lb >/dev/null 2>"$d/spark.err" || { no "$name: sparklines failed: $(cat "$d/spark.err")"; return; }
  python3 "$RENDER" --template "$TMPL" --data "$d/.case_summary_data.json" --out "$d/summary.html" >/dev/null 2>&1 || { no "$name: render failed"; return; }
  python3 "$VALIDATE" --html "$d/summary.html" --template "$TMPL" >/dev/null 2>"$d/val.err" || { no "$name: validate failed: $(cat "$d/val.err")"; return; }
  ok
  echo "$d/summary.html"
}

# ---- Case A: CRC, hero + marker + delta ----
cat > "$tmp/A.json" <<EOF
{"i18n":$I18N,"fallbacks":{"__default__":"资料缺失"},
 "one_line_condition":"结直肠癌 IV 期 · KRAS G12D · 肝转移 · 二线治疗中","report_date":"2026-06-28",
 "sex":"女","age":"52 岁","height_weight_bmi":"160 cm / 55 kg / 21.5","ecog":"1",
 "case_summary_narrative":"患者 2025 年 10 月确诊结直肠癌伴多发肝转移，KRAS G12D 突变。一线 XELOX 后进展，2026 年 2 月改二线 FOLFIRI 联合贝伐珠单抗，CEA 持续下降，最近复查提示部分缓解。",
 "labs_period":"2025-11 至 2026-06",
 "trend_charts":[{"metric":"CEA","unit":"ng/mL","series":[{"t":"2025-11-03","v":8.2},{"t":"2026-02-10","v":4.3},{"t":"2026-06-20","v":2.1}],"treatment_markers":[{"t":"2026-02-01","label":"二线 FOLFIRI"}],"interpretation":"肿瘤标志物 CEA 自二线以来整体下降，提示治疗反应较好。"}],
 "lab_trends":[{"lab_name":"CEA","series":[{"t":"2025-11-03","v":8.2},{"t":"2026-02-10","v":4.3},{"t":"2026-06-20","v":2.1}],"current_value":"2.1","unit":"ng/mL","status_class":"normal","status_label":"正常"},
   {"lab_name":"HGB","series":[{"t":"2026-06-20","v":104}],"current_value":"104","unit":"g/L","status_class":"low","status_label":"偏低"}],
 "lesions":[{"lesion_site":"原发灶","lesion_detail":"乙状结肠占位约 3.2 cm"},{"lesion_site":"肝转移","lesion_detail":"肝右叶多发结节"}],
 "molecular_rows":[{"molecular_label":"驱动突变","molecular_value":"KRAS G12D (VAF 32%)"},{"molecular_label":"免疫表型","molecular_value":"MSS / pMMR"}],
 "treatment_lines":[{"line_label":"一线","line_marker_class":"","line_date_range":"2025-10 → 2026-01","line_badge_class":"pd","line_badge_text":"进展","line_regimen":"XELOX","line_note":"SD 后进展"},
   {"line_label":"二线","line_marker_class":"","line_date_range":"2026-02 → 至今","line_badge_class":"","line_badge_text":"进行中","line_regimen":"FOLFIRI + 贝伐珠单抗","line_note":"CEA 下降，PR"}],
 "path_items":[{"path_label":"当前较可能的路径：","path_content":"继续二线，每 2 周期评估"}],
 "caveats":[{"caveat_text":"化验趋势数值来自照片 OCR，请以检验原件核对"}]}
EOF
cat > "$tmp/A_prev.json" <<EOF
{"report_date":"2026-04-30","lab_trends":[{"lab_name":"CEA","current_value":"4.3"},{"lab_name":"HGB","current_value":"118"}],"treatment_lines":[{"line_label":"一线","line_regimen":"XELOX"}],"ecog":"1"}
EOF
cat > "$tmp/A_long.json" <<EOF
{"schema_version":"longitudinal_observations_v1","patient_code":"PT-A","observations":[
 {"obs_type":"lab","metric":"CEA","value":8.2,"unit":"ng/mL","timestamp":"2025-11-03T00:00:00","modality":"structured","source_ref":"07_检验/a.md#L1"},
 {"obs_type":"lab","metric":"CEA","value":4.3,"unit":"ng/mL","timestamp":"2026-02-10T00:00:00","modality":"structured","source_ref":"07_检验/b.md#L1"},
 {"obs_type":"lab","metric":"CEA","value":2.1,"unit":"ng/mL","timestamp":"2026-06-20T00:00:00","modality":"structured","source_ref":"07_检验/c.md#L1"},
 {"obs_type":"lab","metric":"HGB","value":104,"unit":"g/L","timestamp":"2026-06-20T00:00:00","modality":"structured","source_ref":"07_检验/f.md#L1"}]}
EOF
cat > "$tmp/A_labs.json" <<EOF
{"schema_version":"labs_v1","panels":[
 {"analyte":"CEA","unit":"ng/mL","reference_range":"0-5","values":[{"date":"2026-06-20","value":2.1,"flag":""}]},
 {"analyte":"HGB","unit":"g/L","reference_range":"115-150","values":[{"date":"2026-06-20","value":104,"flag":"L"}]}]}
EOF
htmlA=$(run_case A "$tmp/A.json" "$tmp/A_long.json" "$tmp/A_labs.json" "$tmp/A_prev.json") || true
if [ -n "${htmlA:-}" ] && [ -f "${htmlA:-/nope}" ]; then
  grep -q 'class="delta-item new"' "$htmlA" && ok || no "A: delta strip should show a new treatment line"
  grep -q '<polyline points="12,12' "$htmlA" && ok || no "A: hero polyline present"
  grep -q 'class="trend-chip"' "$htmlA" && ok || no "A: treatment marker legend present"
  [ "$(grep -c '<circle' "$htmlA")" -ge 3 ] && ok || no "A: hero dots present (>=3)"
fi

# ---- Case B: NSCLC, first-ever (no prev → no delta), single-pt lab ----
cat > "$tmp/B.json" <<EOF
{"i18n":$I18N,"fallbacks":{"__default__":"资料缺失"},
 "one_line_condition":"非小细胞肺癌 IV 期 · EGFR 19del · 一线奥希替尼","report_date":"2026-06-28",
 "sex":"男","age":"61 岁","height_weight_bmi":"172 cm / 68 kg / 23.0","ecog":"1",
 "case_summary_narrative":"患者确诊 EGFR 19del 非小细胞肺癌，一线奥希替尼治疗，标志物下降。",
 "labs_period":"2026-03 至 2026-06",
 "trend_charts":[{"metric":"CYFRA21-1","unit":"ng/mL","series":[{"t":"2026-03-01","v":6.4},{"t":"2026-06-10","v":3.1}],"treatment_markers":[{"t":"2026-03-05","label":"奥希替尼"}],"interpretation":"CYFRA21-1 下降，提示治疗有效。"}],
 "lab_trends":[{"lab_name":"CYFRA21-1","series":[{"t":"2026-03-01","v":6.4},{"t":"2026-06-10","v":3.1}],"current_value":"3.1","unit":"ng/mL","status_class":"high","status_label":"偏高"},
   {"lab_name":"NSE","series":[{"t":"2026-06-10","v":14}],"current_value":"14","unit":"ng/mL","status_class":"normal","status_label":"正常"}],
 "lesions":[{"lesion_site":"原发灶","lesion_detail":"右上肺占位"}],
 "molecular_rows":[{"molecular_label":"驱动突变","molecular_value":"EGFR 19del"}],
 "treatment_lines":[{"line_label":"一线","line_marker_class":"","line_date_range":"2026-03 → 至今","line_badge_class":"","line_badge_text":"进行中","line_regimen":"奥希替尼","line_note":"标志物下降"}],
 "path_items":[{"path_label":"当前较可能的路径：","path_content":"继续一线奥希替尼"}],
 "caveats":[]}
EOF
# NSE is intentionally ONLY in labs.json (panels[]) — not in longitudinal — so the
# gate must find it via the real labs shape or it would false-reject and fail-close.
cat > "$tmp/B_long.json" <<EOF
{"schema_version":"longitudinal_observations_v1","patient_code":"PT-B","observations":[
 {"obs_type":"lab","metric":"CYFRA21-1","value":6.4,"unit":"ng/mL","timestamp":"2026-03-01T00:00:00","modality":"structured","source_ref":"07_检验/a.md#L1"},
 {"obs_type":"lab","metric":"CYFRA21-1","value":3.1,"unit":"ng/mL","timestamp":"2026-06-10T00:00:00","modality":"structured","source_ref":"07_检验/b.md#L1"}]}
EOF
cat > "$tmp/B_labs.json" <<EOF
{"schema_version":"labs_v1","panels":[
 {"analyte":"CYFRA21-1","unit":"ng/mL","reference_range":"0-3.3","values":[{"date":"2026-06-10","value":3.1,"flag":"H"}]},
 {"analyte":"NSE","unit":"ng/mL","reference_range":"0-16.3","values":[{"date":"2026-06-10","value":14,"flag":""}]}]}
EOF
htmlB=$(run_case B "$tmp/B.json" "$tmp/B_long.json" "$tmp/B_labs.json" "") || true
if [ -n "${htmlB:-}" ] && [ -f "${htmlB:-/nope}" ]; then
  grep -q 'class="delta ' "$htmlB" && no "B: first-ever summary must NOT show delta strip" || ok
  grep -q 'CYFRA21-1' "$htmlB" && ok || no "B: lab trend row present"
fi

# ---- Case C: edge — no trend data at all ----
cat > "$tmp/C.json" <<EOF
{"i18n":$I18N,"fallbacks":{"__default__":"资料缺失"},
 "one_line_condition":"胃癌 · 新诊断","report_date":"2026-06-28",
 "sex":"女","age":"48 岁","height_weight_bmi":"资料缺失","ecog":"资料缺失",
 "case_summary_narrative":"新诊断胃癌，尚在完善检查。",
 "labs_period":"资料缺失",
 "trend_charts":[],"lab_trends":[],
 "lesions":[],"molecular_rows":[],"treatment_lines":[],"path_items":[],"caveats":[]}
EOF
htmlC=$(run_case C "$tmp/C.json" "" "" "") || true
if [ -n "${htmlC:-}" ] && [ -f "${htmlC:-/nope}" ]; then
  grep -q 'class="trend-none"' "$htmlC" && ok || no "C: no-trend → placeholder shown"
  [ "$(grep -c '<h2>' "$htmlC")" = "9" ] && ok || no "C: all 9 section <h2> still render even with no data"
  grep -q '<polyline' "$htmlC" && no "C: no chart should render with empty trend_charts + empty lab_trends" || ok
fi

# ---- Case D: multi — 2 featured trend charts (skill-decided count) ----
cat > "$tmp/D.json" <<EOF
{"i18n":$I18N,"fallbacks":{"__default__":"资料缺失"},
 "one_line_condition":"卵巢高级别浆液性癌 · 复发","report_date":"2026-06-28",
 "sex":"女","age":"58 岁","height_weight_bmi":"-","ecog":"1","case_summary_narrative":"复发，双标志物随访。","labs_period":"2025-2026",
 "trend_charts":[
   {"metric":"CA125","unit":"U/mL","series":[{"t":"2025-12-01","v":420},{"t":"2026-03-01","v":180},{"t":"2026-06-01","v":66}],"treatment_markers":[{"t":"2025-12-15","label":"二线 PLD"}],"interpretation":"CA125 显著下降。"},
   {"metric":"HE4","unit":"pmol/L","series":[{"t":"2025-12-01","v":320},{"t":"2026-06-01","v":140}],"treatment_markers":[],"interpretation":"HE4 下降。"}],
 "lab_trends":[{"lab_name":"CA125","series":[{"t":"2025-12-01","v":420},{"t":"2026-06-01","v":66}],"current_value":"66","unit":"U/mL","status_class":"high","status_label":"偏高"}],
 "lesions":[],"molecular_rows":[],"treatment_lines":[],"path_items":[],"caveats":[]}
EOF
cat > "$tmp/D_long.json" <<EOF
{"schema_version":"longitudinal_observations_v1","patient_code":"PT-D","observations":[
 {"obs_type":"lab","metric":"CA125","value":420,"unit":"U/mL","timestamp":"2025-12-01T00:00:00","modality":"structured","source_ref":"07_检验/a.md#L1"},
 {"obs_type":"lab","metric":"CA125","value":180,"unit":"U/mL","timestamp":"2026-03-01T00:00:00","modality":"structured","source_ref":"07_检验/b.md#L1"},
 {"obs_type":"lab","metric":"CA125","value":66,"unit":"U/mL","timestamp":"2026-06-01T00:00:00","modality":"structured","source_ref":"07_检验/c.md#L1"},
 {"obs_type":"lab","metric":"HE4","value":320,"unit":"pmol/L","timestamp":"2025-12-01T00:00:00","modality":"structured","source_ref":"07_检验/d.md#L1"},
 {"obs_type":"lab","metric":"HE4","value":140,"unit":"pmol/L","timestamp":"2026-06-01T00:00:00","modality":"structured","source_ref":"07_检验/e.md#L1"}]}
EOF
htmlD=$(run_case D "$tmp/D.json" "$tmp/D_long.json" "" "") || true
if [ -n "${htmlD:-}" ] && [ -f "${htmlD:-/nope}" ]; then
  [ "$(grep -c 'class="trend-hero"' "$htmlD")" = "2" ] && ok || no "D: 2 featured trend charts should render"
  grep -q 'CA125' "$htmlD" && grep -q 'HE4' "$htmlD" && ok || no "D: both metrics present"
fi

# ---- Case E: upper bound — 4 featured trend charts (new cap is 2–4, up from 1–3) ----
# Proves the template + validator + anti-fabrication gate don't choke at the new
# upper bound: 4 charts render side by side, each series point backed by longitudinal.
cat > "$tmp/E.json" <<EOF
{"i18n":$I18N,"fallbacks":{"__default__":"资料缺失"},
 "one_line_condition":"卵巢高级别浆液性癌 · 铂耐药复发 · 多指标随访","report_date":"2026-06-28",
 "sex":"女","age":"60 岁","height_weight_bmi":"158 cm / 52 kg / 20.8","ecog":"1","case_summary_narrative":"铂耐药复发，四项指标并行随访以判读治疗反应与肿瘤负荷。","labs_period":"2025-2026",
 "trend_charts":[
   {"metric":"CA-125","unit":"U/mL","series":[{"t":"2025-11-01","v":880},{"t":"2026-02-01","v":410},{"t":"2026-06-01","v":150}],"treatment_markers":[{"t":"2025-11-15","label":"三线 拓扑替康"}],"interpretation":"CA-125 整体下降。"},
   {"metric":"HE4","unit":"pmol/L","series":[{"t":"2025-11-01","v":520},{"t":"2026-06-01","v":210}],"treatment_markers":[],"interpretation":"HE4 下降。"},
   {"metric":"CEA","unit":"ng/mL","series":[{"t":"2025-11-01","v":9.1},{"t":"2026-06-01","v":5.4}],"treatment_markers":[],"interpretation":"CEA 缓慢下降。"},
   {"metric":"LDH","unit":"U/L","series":[{"t":"2025-11-01","v":420},{"t":"2026-02-01","v":300},{"t":"2026-06-01","v":250}],"treatment_markers":[],"interpretation":"LDH 回落，提示肿瘤负荷下降。"}],
 "lab_trends":[{"lab_name":"CA-125","series":[{"t":"2025-11-01","v":880},{"t":"2026-06-01","v":150}],"current_value":"150","unit":"U/mL","status_class":"high","status_label":"偏高"}],
 "lesions":[],"molecular_rows":[],"treatment_lines":[],"path_items":[],"caveats":[]}
EOF
cat > "$tmp/E_long.json" <<EOF
{"schema_version":"longitudinal_observations_v1","patient_code":"PT-E","observations":[
 {"obs_type":"lab","metric":"CA-125","value":880,"unit":"U/mL","timestamp":"2025-11-01T00:00:00","modality":"structured","source_ref":"07_检验/a.md#L1"},
 {"obs_type":"lab","metric":"CA-125","value":410,"unit":"U/mL","timestamp":"2026-02-01T00:00:00","modality":"structured","source_ref":"07_检验/b.md#L1"},
 {"obs_type":"lab","metric":"CA-125","value":150,"unit":"U/mL","timestamp":"2026-06-01T00:00:00","modality":"structured","source_ref":"07_检验/c.md#L1"},
 {"obs_type":"lab","metric":"HE4","value":520,"unit":"pmol/L","timestamp":"2025-11-01T00:00:00","modality":"structured","source_ref":"07_检验/d.md#L1"},
 {"obs_type":"lab","metric":"HE4","value":210,"unit":"pmol/L","timestamp":"2026-06-01T00:00:00","modality":"structured","source_ref":"07_检验/e.md#L1"},
 {"obs_type":"lab","metric":"CEA","value":9.1,"unit":"ng/mL","timestamp":"2025-11-01T00:00:00","modality":"structured","source_ref":"07_检验/f.md#L1"},
 {"obs_type":"lab","metric":"CEA","value":5.4,"unit":"ng/mL","timestamp":"2026-06-01T00:00:00","modality":"structured","source_ref":"07_检验/g.md#L1"},
 {"obs_type":"lab","metric":"LDH","value":420,"unit":"U/L","timestamp":"2025-11-01T00:00:00","modality":"structured","source_ref":"07_检验/h.md#L1"},
 {"obs_type":"lab","metric":"LDH","value":300,"unit":"U/L","timestamp":"2026-02-01T00:00:00","modality":"structured","source_ref":"07_检验/i.md#L1"},
 {"obs_type":"lab","metric":"LDH","value":250,"unit":"U/L","timestamp":"2026-06-01T00:00:00","modality":"structured","source_ref":"07_检验/j.md#L1"}]}
EOF
htmlE=$(run_case E "$tmp/E.json" "$tmp/E_long.json" "" "") || true
if [ -n "${htmlE:-}" ] && [ -f "${htmlE:-/nope}" ]; then
  [ "$(grep -c 'class="trend-hero"' "$htmlE")" = "4" ] && ok || no "E: 4 featured trend charts should render (new 2–4 upper bound)"
  grep -q 'CA-125' "$htmlE" && grep -q 'HE4' "$htmlE" && grep -q 'CEA' "$htmlE" && grep -q 'LDH' "$htmlE" && ok || no "E: all 4 metrics present"
fi

echo "case-summary-trend E2E: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
