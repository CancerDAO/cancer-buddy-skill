# Patient Profile Card Template

## Patient Profile Card

```
═══════════════════════════════════════════════
  患者档案 | PATIENT PROFILE CARD
═══════════════════════════════════════════════

【基本信息 | BASICS】
  姓名/ID:        ___
  年龄/性别:       ___岁 / 男|女
  身高/体重/BSA:   ___cm / ___kg / ___m²
  ECOG评分:        ___
  合并症:          ___

【诊断 | DIAGNOSIS】
  癌种 Cancer Type:     ___
  病理分型 Histology:    ___
  分期 Stage:            ___ (TNM: T_N_M_)
  转移部位 Metastases:   ___
  确诊日期:              ___

【分子特征 | MOLECULAR FEATURES】
  驱动突变 Driver Mutations:
    - Gene: ___ | Variant: ___ | VAF: ___% | Actionability: ___
  免疫标志物 Immune Markers:
    - MSI/MMR:   ___ (MSS/MSI-H/dMMR)
    - PD-L1:     TPS ___% / CPS ___
    - TMB:       ___ mut/Mb
  其他关键变异:
    - ___

【治疗史 | TREATMENT HISTORY】
  Line 1: [方案] | [开始-结束] | 最佳疗效: CR/PR/SD/PD | 关键毒性: ___
  Line 2: [方案] | [开始-结束] | 最佳疗效: ___         | 关键毒性: ___
  Line N: ...
  当前治疗: ___ (第___周期, 末次___日)

【当前状态 | CURRENT STATUS】
  疾病状态:    进展/稳定/缓解
  关键指标趋势: ___
  主要症状:    ___
  器官功能限制: 肾___  肝___  骨髓___  心___

【信息缺口 | INFORMATION GAPS】
  (覆盖度 — 缺什么. 来源: readiness.json.blocking_gaps)
  🔴 关键缺失 (影响治疗决策):
    - ___
  🟡 建议补充 (提升精准度):
    - ___
  🟢 已充分:
    - ___

【待人工确认 | REVIEW FLAGS】
  (可信度 — 已提取但可疑. 来源: readiness.json.review_flags[])
  🔴 影响下游推荐 (进入 trial-match / mtb-lite 前必须确认):
    - [RF-NNN] field=___, 现写="___", 可疑点: ___
      建议: ___ ⬜ 接受 / ⬜ 保留原写 / ⬜ 自定义
  🟡 建议核对:
    - ___
  🟢 提示:
    - ___
═══════════════════════════════════════════════
```

## Display rules

- "信息缺口" 是覆盖度（缺什么），"待人工确认" 是可信度（写得对不对）—— 两个是不同失败模式，必须分开展示
- 当 `readiness.json.review_flags[]` 为空数组 → 显示 "✅ 所有提取字段已通过 5 项可疑值检查"
- 当存在 🔴 项 → 在 Card 末尾追加: "进入下游 skill 之前请先逐条确认 🔴 项, 它们会直接影响推荐结果"
- 用户的逐项决定 (accept_suggestion / keep_original / custom_value / defer) 写回 `review_flags[i].user_confirmed`
