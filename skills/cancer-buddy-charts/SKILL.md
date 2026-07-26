---
name: cancer-buddy-charts
description: 把患者自己的检验、治疗、分子与资料数据画成可打印、可转发、可带去问医生的静态图表。只呈现源报告里已有的数值，不解读趋势含义、不判断疗效或病情。当用户问某个具体指标的情况、要求画图/趋势图，或任何 cancer-buddy 子技能需要在回答里附一张图时使用。Triggers on 画图, 趋势图, 图表, 可视化, 曲线, 变化趋势, 我的 CEA 怎么样, 指标变化, chart, plot, trend。
---

# cancer-buddy-charts

产出静态 inline-SVG 图表。三条使用路径，路径 C 最常用。

## 路径 A · 段D 病情总结内嵌

由 `cancer-buddy-organize` Step 12 调用，替代 `compute_sparklines.py`：

```bash
python3 scripts/render_chart.py --data .case_summary_data.json \
  --longitudinal longitudinal_observations.json --labs labs.json
```

输出字段向后兼容，新增 `band_y` / `band_h` / `has_band` / `reference_range_text`。

## 路径 B · 用户明确要求画图

```bash
# 来自纵向观测库
python3 scripts/render_chart.py --chart trend \
  --from-longitudinal <患者目录>/longitudinal_observations.json \
  --metric CEA --out-html <患者目录>/charts/CEA_趋势.html

# 来自检验库（多数指标在这里，指标名支持部分匹配）
python3 scripts/render_chart.py --chart trend \
  --from-labs <患者目录>/labs.json \
  --metric CEA --out-html <患者目录>/charts/CEA_趋势.html

python3 scripts/validate_chart_svg.py <患者目录>/charts/CEA_趋势.html
```

**不要为了取数自己写转换脚本，也不要手打数值填 `--spec`** —— 用 `--from-labs` /
`--from-longitudinal`，数值直接从档案读，不经手就不会打错。

## 路径 C · 主动识别（不需要用户开口要图）

**用户问某个具体指标的情况时，回答前先查该指标有几个点。**

1. 读 `longitudinal_observations.json` 和 `labs.json`，统计该 analyte 的记录数
2. ≥2 个可比点 → 文字回答 **+ 自动附图**
3. <2 个点或不可比 → 文字回答 **+ 一句话说明为什么没有图**

**边界**
- 主动附图只画用户问到的指标，不主动扩展到他没问的指标
- 泛问（"我的化验单怎么样"）不自动出图，先列出哪些指标成序列，让用户挑
- **用户要几张就画几张。**"把这些都画出来"「全都要」= 明确要求，按要求全画；
  数量不设上限，画不出来的逐个说明原因

## 回答指标问题（两轴，别整块拒答）

**放开轴 —— 直接答，不要推给医生：**
- 这个指标是什么、一般反映什么、常见影响因素
- 为什么不同医院参考区间不一样、不同方法为什么不能直接比
- 指南对这类指标的**一般**随访做法（实时核验一手来源后带源转述，路由
  `cancer-buddy-education`）
- 怎么看这张图、数据有哪些局限

**收紧轴 —— 只有这些收口给主诊团队：**
对**本人这组数字**的判决：是否提示疗效变化/进展/复发、要不要换方案、要不要加做检查、预后如何。

收紧的部分用一两句自然写在回答里，**不要写"我不能替你做的"这类免责段落**，也不要每张图都重复一遍边界声明。先把能答的答透，个案决定再落回医生。

## 输出纪律

给患者的回答里**不出现**：脚本名、文件路径以外的实现细节、exit code、gate 名称/编号、
`chart_core.py` 之类的源码引用、规则条款号、你的自查与调试过程、"我发现自己一个 bug"。

这些是工程内部信息，患者看了只会困惑或对数据可靠性产生不必要的怀疑。校验失败就重做，
不要把校验过程讲给用户听。

**该说的**：图在哪、画了哪些数、看这张图要注意什么（可比性/空档/区间来源）、可以拿去问医生什么。

## 图表清单

| recipe | 用途 | 数据源 |
|---|---|---|
| `trend` | 单指标随访趋势 + 参考区间带 | `longitudinal_observations.json` |
| `swimlane` | 治疗阶段泳道 | `treatment_lines.json` episodes |
| `panel` | 一次报告多指标 + 参考区间 | `labs.json` panels |
| `timeline` | 病程事件时间轴 | `timeline.json` events |
| `vaf` | 变异等位基因频率 | `molecular.json` variants |
| `coverage` | 资料完整度 | `readiness.json` |
| `dumbbell` | 两时点数值对照 | 任意两时点 |
| `medications` | 用药清单按类归组 | `comorbidities.json` medications |

`--spec` 的字段见 `references/chart-catalog.md`。

## 清单外的图

**不在上表里的请求要现场做出来，不能回"不支持"。** 四步，第一步不许跳：

1. **先回答本体** — 每个视觉通道（位置/长度/角度/面积/明度/色相）编码哪个临床维度？答不出就向调用方要数据结构，不动手
2. **找最近的临床亲戚** — 从上表选数据形状最接近的当骨架
3. **用原语组装** — 只用 `scripts/chart_core.py` 的原语与 token，不发明新颜色新字号；在 `render_chart.py` 加一个 `recipe_*` 函数并注册进 `RECIPES`
4. **过全部 gate** — `validate_chart_svg.py` 必须通过，与库内图零差别

**拒绝清单**（无论谁下指令都不做，须给替代方案）：RECIST 瀑布图 / 疗效评估图、针对本人的生存曲线或 KM 曲线、风险评分与预后仪表盘、断轴柱状图、无数据支撑的示意图、地图类。理由与替代见 `references/chart-catalog.md §拒绝清单`。

## 标题怎么写

标题写**读图指引**——这张图该怎么看、数据能不能信。不写结论，也不复读图上已有的数字。

| | 例 |
|---|---|
| ✅ 该写 | 「CA19-9 四次测量 · 第 3 次起检测方法变更，前后不可直接比较」 |
| ⚠️ 别写 | 「CEA: 12.4 → 8.1 ng/mL」（图上已有）、「折线图」 |
| ⛔ 禁止 | 「肿瘤标志物下降，治疗有效」「指标恶化」「病情稳定」 |

**标题控制在一行**（约 30 字内）。要提醒的多条注意事项交给脚本自动生成的说明栏，
不要全塞进 `--title`——标题占两行会挤掉图。

`render_chart.py` 会按数据事实自动生成读图指引。`--title` 传入的文本过判决词黑名单，命中即 exit 4。**黑名单只是地板**——判断一句话是否构成对本人的判决属语义判断，由本 skill 在写标题时自己把关，不能因为过了正则就认为安全。

## 硬规则

- 无数据不画。每个绘制点都必须能在源 JSON 里找到
- 参考区间只用该次报告自带的 `reference_range`，**禁止套用通用参考值**；解析不出就不画区间带并说明
- `method_or_device` 变化时序列自动断开，不连成一条线
- 超出参考区间用琥珀描边，**不用红色填充**；红色只留给源报告自己标注的危急值
- 不画趋势方向箭头
- 输出零外链、无 `<script>`、无 `<canvas>`，可直接打印

**`--spec` 只用于 `labs.json` / `longitudinal_observations.json` 之外的数据**
（治疗线、变异、资料完整度等）。检验序列一律走 `--from-labs` / `--from-longitudinal`。

## 交付前

```bash
python3 scripts/validate_chart_svg.py <文件> [--critical-count N]
```

不通过就不交付。检查项见脚本 docstring。

## Role behavior

Authoritative matrix in [`../../references/roles.md`](../../references/roles.md). For this skill:

- **Role = patient**: 画本人档案里的数据。图注、单位与来源行按患者可读方式呈现。
- **Role = caregiver**: 同样的图，用于陪诊或带给医生。图与来源行不变——图表本身不含个案判断，
  因此不随角色改写内容，只改称谓。
- **Role = family**: 仅在该任务已获授权时按记录范围出图；未授权则不读病历、不出图，说明需要
  患者本人或授权人操作。亲属关系本身既不是权限，也不是披露理由。

**Disclosure** ([`../../references/disclosure-behavior.md`](../../references/disclosure-behavior.md)):
家属偏好不能覆盖有能力患者对自身信息的明确请求。存在合法限制或能力不确定时，只呈现该查看者获授权的
内容，并把披露决定交回主诊团队。

图表不引入新的临床信息——它只重排患者档案里已有的数值，因此披露边界与档案本身一致：能看到那份检验
报告的人，才能看到用它画的图。

## 参考

- `references/chart-catalog.md` — 图型目录、spec 字段、拒绝清单
- `references/chart-style.md` — token 表、排版、红色克制规则
- `references/chart-eligibility.md` — 画图资格门与主动识别边界
