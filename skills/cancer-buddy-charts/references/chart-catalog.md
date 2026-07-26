# 图型目录

`--chart <recipe> --spec <file>.json`。所有 spec 的日期字段接受 ISO 8601（`2026-01-08` 或带时间），数值字段接受数字或数字字符串（容忍前导 `<` `>` `≤` `≥`）。

## trend · 单指标随访趋势 + 参考区间带

最常用。直接从 organize 产物生成，不必手写 spec：

```bash
--chart trend --from-labs labs.json --metric CEA                       # 检验库(多数指标在这)
--chart trend --from-longitudinal longitudinal_observations.json --metric CEA
```

`--from-labs` 的指标名支持部分匹配（`CEA` 命中 `CEA 癌胚抗原`）；匹配到多个时报错并列出候选，不猜。

手写 spec：

```json
{"metric":"CA19-9","unit":"U/mL","reference_range":"0-37","reference_source":"本次报告",
 "series":[{"t":"2026-01-08","v":412,"unit":"U/mL","method":"电化学发光 Roche e601",
            "reference_range":"0-37","critical":false}]}
```

- `method` 变化 → 序列自动断开分段，接缝画虚线
- `reference_range` 解析不出 → 不画带，说明栏写明
- `critical: true` → 该点用红色（源报告标注的危急值）
- 少于 2 个可比点 → exit 5，附可读原因

## swimlane · 治疗阶段泳道

```json
{"episodes":[{"start":"2026-01-20","end":"2026-03-15","label":"吉西他滨+白蛋白紫杉醇","intent":"一线"},
             {"start":"2026-06-10","end":null,"label":"mFOLFIRINOX","intent":"二线"}]}
```

`end: null` → 虚线尾，不画硬边（硬边会暗示一个记录里没有的结束日期）。`intent` 用源记录里的意图标签（新辅助/维持/姑息…），**不要**从序号派生"一线/二线"。

## panel · 一次报告多指标 + 参考区间

```json
{"rows":[{"analyte":"白蛋白","value":32,"unit":"g/L","reference_range":"40-55"},
         {"analyte":"隐血试验","value":"阳性","reference_range":"阴性"}]}
```

非数值结果或无可解析区间 → 该行画虚线轨道 + 值 + "无参考区间"，行不塌陷。

## timeline · 病程事件

```json
{"events":[{"t":"2025-11-12","label":"确诊"},{"t":"2026-01-08","label":"手术"}]}
```

标签自动分行避让；同一月份只标一次。

## vaf · 变异等位基因频率

```json
{"variants":[{"gene":"KRAS","change":"p.G12D","vaf":38.2}]}
```

`vaf` ≤ 1 视为小数，> 1 视为百分数。每 10% 一根立柱，条形可数。

## coverage · 资料完整度

```json
{"items":[{"label":"影像报告","have":6,"need":8}]}
```

`need ≤ 24` 时画分隔刻痕，每格 = 1 份文件。

## dumbbell · 两时点对照

```json
{"t1_label":"治疗前","t2_label":"最近一次",
 "rows":[{"label":"体重","v1":68.0,"v2":61.5,"unit":"kg"}]}
```

**每行按该行自身最大值缩放**，位置 = 占该行最大值的比例，行间长度不可比（自动写进说明）。空心 = 时点 1，实心 = 时点 2；**时间顺序由标记形状表达，不由左右位置表达**。

## medications · 用药清单按类归组

```json
{"medications":[{"group":"抗肿瘤","name":"吉西他滨","note":"静脉"}]}
```

---

# 清单外的图

上表不是天花板。不在表里的请求按 `SKILL.md §清单外的图` 的四步现场组装：先答本体 → 找最近的临床亲戚 → 用 `chart_core.py` 原语组装 → 过全部 gate。

新配方写成 `render_chart.py` 里的 `recipe_*(spec)` 函数，返回 `(Svg, note, legend, caveats, subject)`，并注册进 `RECIPES`。可复用的原语：

- `TimeAxis` / `ValueAxis`（含参考区间域扩展）
- `parse_reference_range` / `range_status` / `point_colour`
- `stack_rows`（标签分行避让）/ `truncate`（超长名截断 + `<title>`）
- `Svg.rail` / `Svg.band`（环境结构层）
- `page`（卡片四件套 + 零外链包装）

## 已实现的库外示例

`med-overlap`（用药重叠密度）不在原目录里，是按上述四步事后加的：阶梯线 = 每天同时在用的药物数，泳道 = 各药覆盖区间。骨架继承 `swimlane`，只用 `chart_core.py` 原语组装，未新增任何颜色或字号，过与目录内图完全相同的 gate。

```json
{"medications":[{"name":"吉西他滨","start":"2026-01-20","end":"2026-03-15"},
                {"name":"二甲双胍","start":"2026-01-20","end":null}]}
```

`end: null` 延伸到图窗末端 + 虚线尾——未写结束日期不等于当天停用，塌成零宽会把"仍在用"画成"用了一天"。

## 拒绝清单

即使调用方明确要求也不做，须给出替代方案：

| 请求 | 替代 |
|---|---|
| RECIST 瀑布图 / 疗效评估图 / 缓解率图 | 画径线原始数值序列，判读留给医生 |
| 针对本人的生存曲线 / KM 曲线 | 个体不存在生存曲线，画出来必被误读为个人预后；群体数据的 KM 属 `oncoevidence` / `smtb` 范畴 |
| 风险评分 / 预后打分仪表盘 | 属个案判决轴，路由主诊团队 |
| 断轴柱状图 | 三个诚实方案：让极端值冲天 / 主图 + 放大镜小图 / 撕柱不撕轴并明说 |
| 无数据支撑的示意图、概念图 | 无数据不画 |
| 地图类（转移分布地图等） | 没有地理管线，老实说做不了，不硬画走样的 |

## 未实现

**靶病灶径线之和多序列**（C5）：`case_summary_data.schema.json` 的 `lesions[]` 只有 `lesion_site` + `lesion_detail`（影像描述自由文本），没有结构化径线数值与测量日期，无数据基础。需先扩 organize 的影像抽取能力（LLM 判断任务，走 sub-skill prompt，不写正则）。

该图临床风险最高——径线之和距 RECIST 判读只有一步，实现时必须同步加 caption 门。单开 PRD，本 skill 不做。
