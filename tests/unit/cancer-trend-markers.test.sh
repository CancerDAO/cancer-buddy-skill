#!/usr/bin/env bash
set -euo pipefail
ORG="$(cd "$(dirname "$0")/../.." && pwd)/skills/cancer-buddy-organize"
V="$ORG/scripts/validate_cancer_trend_markers.py"
MD="$ORG/references/cancer-trend-markers.md"
LAND="/Users/baozhiwei/cancer_therapy_corpus/landscapes"
tmp="$(mktemp -d)"; trap "rm -rf $tmp" EXIT
pass=0; fail=0; ok(){ pass=$((pass+1)); }; no(){ echo "FAIL: $1">&2; fail=$((fail+1)); }

# 1) 真表须过结构校验（slug 数 = landscapes 目录里的 69，列齐、primary 非空或为 —）
python3 "$V" --markers "$MD" --slugs "$LAND" && ok || no "real markers table failed validation"

# 2) 缺列的坏表须被拒
printf '| slug | 癌种 |\n|---|---|\n| foo | 结直肠 |\n' > "$tmp/bad.md"
if python3 "$V" --markers "$tmp/bad.md" --slugs "$LAND"; then no "malformed table passed"; else ok; fi

# 3) prompt §关键趋势 选取规则须引用 marker 参考表 + 分层规则 + hero 总数上限
P="$ORG/references/case-summary-html-prompt.md"
grep -q "cancer-trend-markers.md" "$P" && ok || no "prompt 未引用 marker 参考表"
grep -q "Tier 1" "$P" && grep -q "Tier 2" "$P" && ok || no "prompt 缺分层规则"
grep -Eq "2[–-]4" "$P" && ok || no "prompt 未写 hero 总数 2–4"

echo "pass=$pass fail=$fail"; [ "$fail" -eq 0 ]
