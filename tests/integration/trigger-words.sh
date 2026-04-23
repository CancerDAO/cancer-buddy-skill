#!/usr/bin/env bash
# Verify every legacy cancer-buddy trigger word is listed in the meta-skill description.
# This is structural — it does not actually invoke Claude, only greps the SKILL.md files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
META="$REPO_ROOT/skills/cancer-buddy/SKILL.md"

# List every legacy trigger phrase that must still route somewhere.
triggers=(
  "抗癌搭子"
  "搭子"
  "患者导航"
  "帮我分析病情"
  "刚确诊"
  "标准治疗用尽"
  "帮我找临床试验"
  "基因报告解读"
  "分子肿瘤委员会"
  "临床试验匹配"
  "扩展准入"
  "同情用药"
  "病历整理"
  "治疗方案"
  "家属"
  "陪护"
  "burnout"
  "睡不着"
  "焦虑"
  "抑郁"
  "肿瘤长大了"
  "换线"
  "第二意见"
  "跨境会诊"
  "吃什么"
  "忌口"
  "忘记吃药"
  "漏服"
  "治疗结束"
  "治愈"
  "随访"
  "长期副作用"
  "晚发效应"
  "要不要告诉"
)

# Scan the description field in the meta-skill frontmatter.
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
echo "all legacy triggers preserved"
