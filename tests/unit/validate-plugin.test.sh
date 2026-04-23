#!/usr/bin/env bash
# Test that validate-plugin.sh catches structural issues.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/validate-plugin.sh"

tmpdir="$(mktemp -d)"
trap "rm -rf $tmpdir" EXIT

# Case 1: missing plugin.json should fail
mkdir -p "$tmpdir/case1"
if bash "$SCRIPT" "$tmpdir/case1" 2>/dev/null; then
  echo "FAIL: validator accepted missing plugin.json"
  exit 1
fi

# Case 2: plugin.json without required fields should fail
mkdir -p "$tmpdir/case2/.claude-plugin"
echo '{}' > "$tmpdir/case2/.claude-plugin/plugin.json"
if bash "$SCRIPT" "$tmpdir/case2" 2>/dev/null; then
  echo "FAIL: validator accepted empty plugin.json"
  exit 1
fi

# Case 3: valid minimal plugin should pass
mkdir -p "$tmpdir/case3/.claude-plugin"
mkdir -p "$tmpdir/case3/skills/sample"
cat > "$tmpdir/case3/.claude-plugin/plugin.json" <<'JSON'
{"name":"x","description":"y","version":"0.1.0"}
JSON
cat > "$tmpdir/case3/skills/sample/SKILL.md" <<'MD'
---
name: sample
description: sample skill
---
body
MD
bash "$SCRIPT" "$tmpdir/case3"

echo "ALL PASS"
