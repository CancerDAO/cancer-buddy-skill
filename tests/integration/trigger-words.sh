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
  "要不要告诉"
  "不想让 Ta 知道"
  "数据保险箱"
  "宣教手册"
)

meta_desc=$(awk '/^---$/{n++; next} n==1 && /^description:/{sub(/^description:[[:space:]]*/,""); print}' "$META")

errs=0
for t in "${triggers[@]}"; do
  if ! echo "$meta_desc" | grep -q "$t"; then
    echo "MISSING trigger '$t' in meta-skill description" >&2
    errs=$((errs+1))
  fi
done

if (( errs > 0 )); then
  echo "$errs trigger regression(s)" >&2
  exit 1
fi
echo "all companion triggers preserved"
