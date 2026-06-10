#!/usr/bin/env bash
# =============================================================================
# tests/integration/case-summary.sh
# 集成测试：验证 cancer-buddy-organize 产出的病例总结文件符合 case-summary-template.md
#
# 用法：
#   bash tests/integration/case-summary.sh <patient_dir>
#   # 例：bash tests/integration/case-summary.sh patients/宫颈癌_2024-03_4f2a
#
# 依赖：bash ≥ 4、grep
# =============================================================================

set -euo pipefail

PATIENT_DIR="${1:-}"

# ── 帮助 ─────────────────────────────────────────────────────────────────────
usage() {
  echo "用法: $0 <patient_dir>"
  echo "  patient_dir 是 organize 产出的 patients/<code>/ 目录路径"
  exit 1
}

[[ -z "$PATIENT_DIR" ]] && usage
[[ ! -d "$PATIENT_DIR" ]] && { echo "❌ 目录不存在: $PATIENT_DIR"; exit 1; }

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0

pass()  { echo -e "${GREEN}  ✅ PASS${NC}  $1"; ((PASS++))  || true; }
fail()  { echo -e "${RED}  ❌ FAIL${NC}  $1"; ((FAIL++))   || true; }
warn()  { echo -e "${YELLOW}  ⚠️  WARN${NC}  $1"; ((WARN++)) || true; }
header(){ echo -e "\n${YELLOW}▸ $1${NC}"; }

# ── 断言辅助函数 ─────────────────────────────────────────────────────────────
assert_file_exists() {
  local file="$1" label="${2:-$1}"
  if [[ -f "$file" ]]; then
    pass "文件存在: $label"
  else
    fail "文件缺失: $label"
  fi
}

assert_contains() {
  local file="$1" pattern="$2" label="$3"
  if grep -qP "$pattern" "$file" 2>/dev/null; then
    pass "$label"
  else
    fail "$label  (pattern: $pattern)"
  fi
}

assert_not_contains() {
  local file="$1" pattern="$2" label="$3"
  if ! grep -qP "$pattern" "$file" 2>/dev/null; then
    pass "$label"
  else
    fail "$label  (禁用 pattern 出现了: $pattern)"
  fi
}

assert_line_count_le() {
  local file="$1" max="$2" label="$3"
  local count
  count=$(wc -l < "$file")
  if [[ "$count" -le "$max" ]]; then
    pass "$label  ($count 行 ≤ $max)"
  else
    warn "$label  ($count 行 > $max，超出软上限)"
  fi
}

assert_contains_any() {
  # 文件包含至少一个 pattern（用 | 分隔）
  local file="$1" patterns="$2" label="$3"
  if grep -qP "$patterns" "$file" 2>/dev/null; then
    pass "$label"
  else
    fail "$label  (patterns: $patterns)"
  fi
}

# =============================================================================
BRIEF="${PATIENT_DIR}/case_summary_brief.md"
DETAILED="${PATIENT_DIR}/case_summary_detailed.md"

echo ""
echo "==================================================================="
echo "  Case Summary 集成测试"
echo "  Patient dir : $PATIENT_DIR"
echo "==================================================================="

# ─────────────────────────────────────────────────────────────────────────────
header "1. 文件存在性"
# ─────────────────────────────────────────────────────────────────────────────
assert_file_exists "$BRIEF"    "case_summary_brief.md"
assert_file_exists "$DETAILED" "case_summary_detailed.md"

# 后续断言仅在文件存在时有意义；如果文件缺失则直接报错退出
if [[ ! -f "$BRIEF" || ! -f "$DETAILED" ]]; then
  echo -e "\n${RED}文件缺失，终止后续检查。${NC}"
  echo "PASS=$PASS  FAIL=$FAIL  WARN=$WARN"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
header "2. 简要总结 — 结构完整性"
# ─────────────────────────────────────────────────────────────────────────────
assert_contains "$BRIEF" "病例简要总结|Case Summary Brief" "有标题行"
assert_contains "$BRIEF" "基本信息|Basic Demographics" "模块1：基本信息"
assert_contains "$BRIEF" "病情概要" "模块2：病情概要"
assert_contains "$BRIEF" "治疗史" "模块6：治疗史"
assert_contains "$BRIEF" "当前状态|治疗路径|下一步" "模块7：治疗路径"
assert_contains "$BRIEF" "case-summary-template" "模板版本水印"
assert_contains "$BRIEF" "AI 自动生成|自动生成" "免责声明"
# 篇幅控制（soft）：简要版正文不应超过 120 行
assert_line_count_le "$BRIEF" 120 "简要版篇幅（soft 上限 120 行）"

# ─────────────────────────────────────────────────────────────────────────────
header "3. 详细总结 — 七大模块完整性"
# ─────────────────────────────────────────────────────────────────────────────
assert_contains "$DETAILED" "病例详细总结|Case Summary Detailed" "有标题行"
assert_contains "$DETAILED" "模块.?1|基本信息" "模块1"
assert_contains "$DETAILED" "模块.?2|病情概要" "模块2"
assert_contains "$DETAILED" "模块.?3|分子检测|标志物" "模块3"
assert_contains "$DETAILED" "模块.?4|影像学" "模块4"
assert_contains "$DETAILED" "模块.?5|实验室|Lab" "模块5"
assert_contains "$DETAILED" "模块.?6|治疗史" "模块6"
assert_contains "$DETAILED" "模块.?7|治疗路径" "模块7"
assert_contains "$DETAILED" "附录|未解决问题" "未解决问题清单"
assert_contains "$DETAILED" "信息来源|来源索引" "信息来源索引"

# ─────────────────────────────────────────────────────────────────────────────
header "4. 必要字段存在"
# ─────────────────────────────────────────────────────────────────────────────
for FILE in "$BRIEF" "$DETAILED"; do
  LABEL=$(basename "$FILE")
  assert_contains "$FILE" "(姓名|年龄|性别)" "${LABEL}：含姓名/年龄/性别"
  assert_contains "$FILE" "ECOG" "${LABEL}：含 ECOG"
  assert_contains "$FILE" "(确诊|诊断).*(20\d\d|年)" "${LABEL}：含确诊时间"
  assert_contains "$FILE" "(分期|T[0-4]N[0-3]M[0-1]|Stage)" "${LABEL}：含分期信息"
done

# ─────────────────────────────────────────────────────────────────────────────
header "5. 缺失字段显性化检查（不允许静默空白）"
# ─────────────────────────────────────────────────────────────────────────────
# 如果有缺失字段，必须出现规定标签之一
MISSING_KEYWORDS="未检测|Pending|未取得|客观无法获得|建议完善|待回报|待核实"
# 检测方式：如果 detailed 版里有空行紧跟模块标题（意味着整段内容被跳过），判为警告
# 更实用的检查：只要 detailed 里任何模块下出现了"-"或"N/A"独立行，必须同时有明确说明
if grep -qP "^-\s*$|^N/A\s*$|^无\s*$|^—\s*$" "$DETAILED"; then
  # 存在纯"无/N/A/—"行，检查是否有对应说明
  if grep -qP "$MISSING_KEYWORDS" "$DETAILED"; then
    pass "缺失字段有显性说明"
  else
    fail "存在空行或 N/A，但缺少缺失类型说明（应含：$MISSING_KEYWORDS）"
  fi
else
  pass "未检测到裸 N/A 行（或无缺失字段）"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "6. 禁用写法检查"
# ─────────────────────────────────────────────────────────────────────────────
for FILE in "$BRIEF" "$DETAILED"; do
  LABEL=$(basename "$FILE")
  # 不得有治疗推荐语气
  assert_not_contains "$FILE" "建议使用|推荐方案|应该选择" \
    "${LABEL}：无推荐用药语气"
  # 不得抄整段影像原文（连续超过100字的引号包围文字视为可疑）
  assert_not_contains "$FILE" '".{100,}"' \
    "${LABEL}：无整段影像原文引用（>100字引号块）"
  # 不得出现"一切都会好的"类安慰语
  assert_not_contains "$FILE" "一切都会好|不用担心|会治好" \
    "${LABEL}：无不当安慰语"
done

# ─────────────────────────────────────────────────────────────────────────────
header "7. 治疗史时间线格式检查（详细版）"
# ─────────────────────────────────────────────────────────────────────────────
# 至少一条包含"一线|二线|三线"或明确日期的治疗记录
assert_contains_any "$DETAILED" \
  "(一线|二线|三线|[Ll]ine\s*[1-9]|20\d\d-\d\d.*方案|方案.*20\d\d-\d\d)" \
  "详细版：治疗史包含线别或日期"

# ─────────────────────────────────────────────────────────────────────────────
header "8. 数据来源标注（详细版）"
# ─────────────────────────────────────────────────────────────────────────────
assert_contains "$DETAILED" "(来源|SOURCE|出处)[：:].*(报告|记录|sidecar|\.md|\.pdf)" \
  "详细版：有来源标注"

# ─────────────────────────────────────────────────────────────────────────────
header "9. review_flags 提示（若有红旗）"
# ─────────────────────────────────────────────────────────────────────────────
READINESS="${PATIENT_DIR}/readiness.json"
if [[ -f "$READINESS" ]]; then
  RED_FLAGS=$(python3 -c "
import json,sys
r=json.load(open('$READINESS'))
flags=r.get('review_flags',[])
print(sum(1 for f in flags if f.get('severity')=='red' and not f.get('user_confirmed',False)))
" 2>/dev/null || echo "0")
  if [[ "$RED_FLAGS" -gt 0 ]]; then
    # 总结里应该有红旗警告
    assert_contains_any "$DETAILED" \
      "(红旗|review_flag|未解决|🔴|red flag|RF-[0-9])" \
      "详细版：提示了未解决红旗 (${RED_FLAGS} 个)"
  else
    pass "readiness.json：无未解决红旗，跳过红旗提示检查"
  fi
else
  warn "readiness.json 不存在，跳过红旗检查"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "10. 一致性检查（brief vs detailed）"
# ─────────────────────────────────────────────────────────────────────────────
# 两份文件的 patient_code 必须一致
PT_CODE_BRIEF=$(grep -oP "PT-[A-F0-9]{8,}" "$BRIEF"    | head -1 || true)
PT_CODE_DET=$(  grep -oP "PT-[A-F0-9]{8,}" "$DETAILED" | head -1 || true)
if [[ -n "$PT_CODE_BRIEF" && -n "$PT_CODE_DET" ]]; then
  if [[ "$PT_CODE_BRIEF" == "$PT_CODE_DET" ]]; then
    pass "patient_code 在两份文件中一致 ($PT_CODE_BRIEF)"
  else
    fail "patient_code 不一致：brief=$PT_CODE_BRIEF  detailed=$PT_CODE_DET"
  fi
else
  warn "未能从文件中提取 patient_code（可能格式不同，人工检查）"
fi

# =============================================================================
echo ""
echo "==================================================================="
printf "  结果：${GREEN}%d PASS${NC}  ${RED}%d FAIL${NC}  ${YELLOW}%d WARN${NC}\n" \
  "$PASS" "$FAIL" "$WARN"
echo "==================================================================="
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}❌ 测试未通过。请检查上方 FAIL 项。${NC}"
  exit 1
else
  echo -e "${GREEN}✅ 所有强制检查通过。${NC}"
  [[ "$WARN" -gt 0 ]] && echo -e "${YELLOW}⚠️  有 $WARN 个警告，建议人工复核。${NC}"
  exit 0
fi
