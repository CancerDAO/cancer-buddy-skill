#!/usr/bin/env bash
# Verify every companion-scope trigger word is listed in the meta-skill description.
# This is structural — it does not actually invoke Claude, only greps the SKILL.md files.
#
# After the v4 scope pivot, clinical triggers (MTB / 试验 / 扩展准入 / 缓和 / 副作用 /
# 换线 / 长期副作用 / 漏服 etc.) are intentionally NOT in the public skill —
# they live in cancer-buddy-pro-skill. The meta-skill explicitly declines those asks.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
META="$REPO_ROOT/skills/cancer-buddy/SKILL.md"

# Companion-scope triggers that must still route.
triggers=(
  "抗癌搭子"
  "搭子"
  "患者导航"
  "帮我分析病情"
  "刚确诊"
  "病历整理"
  "家属"
  "陪护"
  "burnout"
  "睡不着"
  "焦虑"
  "抑郁"
  "吃什么"
  "忌口"
  "第二意见"
  "跨境会诊"
  "告不告诉"
  "不想让对方知道"
  "数据保险箱"
  "宣教手册"
)

# The meta-skill uses a multi-line YAML block scalar:
#
#   description: |
#     抗癌搭子 ...
#     ... Triggers on: ...
#
# A single-line `^description:` rule only captures the `|` line (empty), which
# false-negatives every trigger. Extract the WHOLE block: everything between the
# first `---` and the second `---`, then keep the indented continuation lines that
# belong to the `description:` key. Simpler and more robust: just grep the whole
# SKILL.md (frontmatter description + body declare the same trigger vocabulary).
meta_desc=$(awk '
  /^---[[:space:]]*$/ { n++; next }
  n == 1 { print }            # everything inside the YAML frontmatter
' "$META")

# Fall back to the whole file if frontmatter extraction came up empty for any
# reason (keeps the test robust to formatting drift).
if [[ -z "$meta_desc" ]]; then
  meta_desc=$(cat "$META")
fi

errs=0
for t in "${triggers[@]}"; do
  if ! grep -qF "$t" <<<"$meta_desc"; then
    echo "MISSING trigger '$t' in meta-skill description" >&2
    errs=$((errs+1))
  fi
done

if (( errs > 0 )); then
  echo "$errs trigger regression(s)" >&2
  exit 1
fi
echo "all companion triggers preserved"
