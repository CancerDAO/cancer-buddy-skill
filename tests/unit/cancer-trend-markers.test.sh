#!/usr/bin/env bash
set -euo pipefail
ORG="$(cd "$(dirname "$0")/../.." && pwd)/skills/cancer-buddy-organize"
V="$ORG/scripts/validate_cancer_trend_markers.py"
MD="$ORG/references/cancer-trend-markers.md"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0; ok(){ pass=$((pass+1)); }; no(){ echo "FAIL: $1" >&2; fail=$((fail+1)); }

python3 "$V" --markers "$MD" && ok || no "real no-static-mapping policy failed"

cat > "$tmp/bad.md" <<'EOF'
# Marker map
| slug | 癌种 | marker |
|---|---|---|
| crc | 结直肠癌 | CEA |
EOF
if python3 "$V" --markers "$tmp/bad.md" >/dev/null 2>&1; then no "static mapping passed"; else ok; fi

P="$ORG/references/case-summary-html-prompt.md"
grep -q "cancer-trend-markers.md" "$P" && ok || no "summary contract does not cite trend policy"
grep -qiE "患者|用户|user" "$MD" && grep -qiE "descriptive|描述" "$MD" && ok || no "trend policy lacks request + descriptive-only rule"

echo "pass=$pass fail=$fail"; [[ "$fail" -eq 0 ]]
