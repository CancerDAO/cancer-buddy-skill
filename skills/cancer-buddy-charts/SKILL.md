---
name: cancer-buddy-charts
description: 抗癌搭子·图表——把档案里的检验、肿瘤标志物、体重等数据画成静态趋势图。触发词：画图、趋势图、变化曲线、指标走势、CEA 变化、化验趋势、肿瘤标志物走势、都画出来。English: chart, plot, trend, graph my labs, tumor marker trend. Requires the cancer-buddy skill.
---

# 趋势图

把源报告里的数字按时间画出来，让患者和医生一眼看到变化。图只展示，不下结论。

## 什么时候画

- 用户明确要图。
- 用户问到某个具体指标（"CEA 最近怎么样"），且有 ≥2 个可比点：总入口会主动调用这里附一张图。
- 用户说"都画"就把可画的都画；否则只画用户问的，不替用户挑"重要指标"。

## 读什么

`labs.json`、`longitudinal_observations.json`、`treatment_lines.json`（在图上标出治疗时间段）。按 [archive.md](../cancer-buddy/references/archive.md) 找档案。

## 怎么调用

```
python3 "<cancer-buddy 目录>/scripts/cb.py" chart <patient_dir> --list
python3 "<cancer-buddy 目录>/scripts/cb.py" chart <patient_dir> <指标> [--title "…"]
```

先 `--list` 看哪些指标能画、各有几个点，再画。产出 `<patient_dir>/charts/<指标>_趋势.html`，把路径给用户。

脚本会自己处理：只用该次报告的参考区间、检测方法变了就断开序列、单点不画、不画趋势箭头。脚本拒绝时，照它给的原因用一句话告诉用户。

## 标题和说明

- 标题是读图指引，如"CEA 各次检测值（2026-01 至 2026-08）"，不是结论。不写"好转""下降说明有效""进展"。
- 图下说明两三句：数据来自哪几份报告、参考区间来自各次报告、标志物变化只是观察，要结合影像和医生判断。
- 数值看不清或是未核实读数的点，不画进图，在说明里提一句。

## 边界

- 不画瀑布图、生存曲线、风险仪表盘。
- 不在不同单位之间换算后硬画在一张图上。
- 不根据图判断疗效或进展（见 guardrails 第 1、2 节）。

规则：[guardrails](../cancer-buddy/references/guardrails.md) · [引用](../cancer-buddy/references/citations.md)
