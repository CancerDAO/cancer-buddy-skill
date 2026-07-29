#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RENDERER="$REPO_ROOT/skills/cancer-buddy-organize/scripts/render_html_template.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/template.html" <<'EOF'
<html><body><div class="row {{direction}} {{status_class}}">{{value}}</div></body></html>
EOF
cat > "$TMP/data.json" <<'EOF'
{"fallbacks":{"__default__":"资料缺失"}}
EOF

python3 "$RENDERER" \
  --template "$TMP/template.html" \
  --data "$TMP/data.json" \
  --out "$TMP/out.html" >/dev/null

grep -Eq 'class="row[[:space:]]*"' "$TMP/out.html"
grep -q '>资料缺失</div>' "$TMP/out.html"
if grep -Eq 'class="[^"]*资料缺失' "$TMP/out.html"; then
  echo "visible fallback prose leaked into a CSS class" >&2
  exit 1
fi

cat > "$TMP/data.json" <<'EOF'
{"direction":"up","value":"2.8","fallbacks":{"__default__":"资料缺失"}}
EOF
python3 "$RENDERER" \
  --template "$TMP/template.html" \
  --data "$TMP/data.json" \
  --out "$TMP/out.html" >/dev/null
grep -q 'class="row up ' "$TMP/out.html"
grep -q '>2.8</div>' "$TMP/out.html"
