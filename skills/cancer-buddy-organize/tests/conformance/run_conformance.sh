#!/usr/bin/env bash
# organize 契约 conformance suite —— 三道确定性门（G1/G2/G3）对合成 fixtures 的
# 行为验收。任何 host（平台 CI / CLI）在部署前跑本脚本；非零退出即红。
# fixtures 全部为合成数据（假机构/假编号/无 PII）；真实样本脱敏版留内网，不入公仓。
set -u
export PYTHONDONTWRITEBYTECODE=1   # 勿在 gates 目录产 __pycache__(会污染 vendor 内容指纹)
HERE="$(cd "$(dirname "$0")" && pwd)"
GATES="$HERE/../../scripts/gates"
FX="$HERE/fixtures"
PY="${PYTHON:-python3}"
fails=0

check() { # name expr_python(读 stdin JSON，assert 后 exit 0/1)
  local name="$1" json="$2" expr="$3"
  if echo "$json" | "$PY" -c "import json,sys; r=json.load(sys.stdin); assert ($expr), r" 2>/dev/null; then
    echo "PASS  $name"
  else
    echo "FAIL  $name"; echo "$json" | head -40; fails=$((fails+1))
  fi
}

# ── G1 ──────────────────────────────────────────────────────────────
out="$("$PY" "$GATES/gate_name_content.py" "$FX/F1_name_shuffle/patients/me")"; rc=$?
check "F1 串位组: 拦下凝血名/肿瘤标志内容的串位" "$out" \
  "r['pass']==False and len(r['violations'])==2 and any('凝血功能筛查'==v['claimed'] and '肿瘤标志' in v['sidecar_says'] for v in r['violations'])"
check "F1 串位组: 检验项目键声明也能拦(名血常规实为生化28项,s000672 型)" "$out" \
  "any(v['claimed']=='血常规' and '生化' in v['sidecar_says'] for v in r['violations'])"
check "F1 串位组: 无报告类型字段的只标 unknown 不拦" "$out" \
  "len(r['unknown'])==2 and any('尿液分析' in u['claimed'] for u in r['unknown'])"
check "F1 串位组: 泛型 document_type(laboratory_report_image) 视同未声明 → unknown 不误杀" "$out" \
  "any('输血前感染筛查' in u['claimed'] for u in r['unknown']) and not any('输血前' in v['path'] for v in r['violations'])"
check "F1 串位组: 血常规↔血细胞分析走别名组放行(不误杀)" "$out" \
  "not any('s000002' in v['path'] for v in r['violations'])"
[ $rc -eq 1 ] || { echo "FAIL  F1 exit code (want 1, got $rc)"; fails=$((fails+1)); }

out="$("$PY" "$GATES/gate_name_content.py" "$FX/F1_positive/patients/me")"; rc=$?
check "F1 正例: 全部名实一致 → 全绿 0 violation" "$out" \
  "r['pass']==True and r['violations']==[] and r['checked']==2"
[ $rc -eq 0 ] || { echo "FAIL  F1_positive exit code (want 0, got $rc)"; fails=$((fails+1)); }

# ── G3 ──────────────────────────────────────────────────────────────
out="$("$PY" "$GATES/gate_same_test.py" "$FX/F2_same_test/candidates.json" "$FX/F2_same_test/patients/me")"
check "F2 同检验: 末3位重叠+双时间戳一致 → same_test_duplicate 不出冲突卡" "$out" \
  "r['candidates'][0]['relation_override']=='same_test_duplicate'"
check "F2 同检验: 值不一致 → internal_read_discrepancy(我方读取问题)" "$out" \
  "r['candidates'][0]['internal_read_discrepancy']==True"

out="$("$PY" "$GATES/gate_same_test.py" "$FX/F2_negative/candidates.json" "$FX/F2_negative/patients/me")"
check "F2 负例: 同批相邻管(采样差3秒) → 不误伤,不改判" "$out" \
  "r['candidates'][0]['relation_override'] is None"

out="$("$PY" "$GATES/gate_same_test.py" "$FX/F2_degraded/candidates.json" "$FX/F2_degraded/patients/me")"
check "F2 降级例: 档案编号全遮蔽 → possible_same_test(不硬改判)" "$out" \
  "r['candidates'][0]['relation_override']=='possible_same_test'"

# ── G2 ──────────────────────────────────────────────────────────────
out="$("$PY" "$GATES/gate_candidate_binding.py" "$FX/F3_binding/candidates.json" "$FX/F3_binding/patients/me")"; rc=$?
check "F3 c1: 档案值挂 needs_human_review + 新值第二读复现不了 → value_unverified 双理由" "$out" \
  "r['candidates'][0]['binding']=='value_unverified' and set(r['candidates'][0]['binding_reasons'])=={'old_value_needs_human_review','new_value_not_reproduced_by_second_read'}"
check "F3 c2 正例: 双方可复现且行标 double_read → verified(不误杀)" "$out" \
  "r['candidates'][1]['binding']=='verified' and r['candidates'][1]['binding_reasons']==[]"
check "F3 c3: 纯 supersede 无值 → not_applicable" "$out" \
  "r['candidates'][2]['binding']=='not_applicable'"
[ $rc -eq 1 ] || { echo "FAIL  F3 exit code (want 1, got $rc)"; fails=$((fails+1)); }

out="$("$PY" "$GATES/gate_candidate_binding.py" "$FX/F3b_override/candidates.json" "$FX/F3b_override/patients/me")"; rc=$?
check "F3b 放行链路: P8 裸数字 key 的 override + 第二读复现 → verified(复读升级打通)" "$out" \
  "r['candidates'][0]['binding']=='verified' and r['candidates'][0]['binding_reasons']==[]"
[ $rc -eq 0 ] || { echo "FAIL  F3b exit code (want 0, got $rc)"; fails=$((fails+1)); }

echo "----"
if [ $fails -eq 0 ]; then echo "CONFORMANCE OK (all cases green)"; exit 0
else echo "CONFORMANCE FAILED: $fails case(s)"; exit 1; fi
