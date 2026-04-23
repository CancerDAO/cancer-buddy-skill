#!/usr/bin/env bash
# Validate cancer-buddy-skill plugin structure.
# Usage: validate-plugin.sh [plugin_root]  (defaults to repo root)
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
errs=0

say_err() { echo "ERROR: $*" >&2; errs=$((errs+1)); }

# 1. plugin.json exists and parses
if [[ ! -f "$ROOT/.claude-plugin/plugin.json" ]]; then
  say_err "missing .claude-plugin/plugin.json"
else
  python3 -c "
import json, sys
p = json.load(open('$ROOT/.claude-plugin/plugin.json'))
for k in ('name','description','version'):
    if k not in p:
        print(f'missing field: {k}'); sys.exit(1)
" || say_err ".claude-plugin/plugin.json missing required fields"
fi

# 2. Every skills/*/SKILL.md has YAML frontmatter with name + description
if [[ -d "$ROOT/skills" ]]; then
  while IFS= read -r skill_md; do
    head -1 "$skill_md" | grep -q '^---$' || { say_err "$skill_md: missing frontmatter open"; continue; }
    head -20 "$skill_md" | grep -q '^name:' || say_err "$skill_md: missing 'name' in frontmatter"
    head -20 "$skill_md" | grep -q '^description:' || say_err "$skill_md: missing 'description' in frontmatter"
  done < <(find "$ROOT/skills" -name SKILL.md)
fi

# 3. No legacy files at root
[[ -f "$ROOT/SKILL.md" ]] && say_err "legacy $ROOT/SKILL.md still exists — must be deleted after migration"

if (( errs > 0 )); then
  echo "validation failed with $errs error(s)" >&2
  exit 1
fi
echo "plugin structure OK"
