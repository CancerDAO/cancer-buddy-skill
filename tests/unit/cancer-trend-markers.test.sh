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

echo "pass=$pass fail=$fail"; [ "$fail" -eq 0 ]
