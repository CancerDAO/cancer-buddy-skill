---
name: cancer-buddy-find-care
description: "查找可核验的肿瘤医院、医生、服务和临床试验站点资源。只做资源发现与联系方式核验，输出不排序的候选清单；不评价医疗质量，不推荐医生/医院，不判断试验资格或治疗适用性。Triggers on 找医院, 找医生, 找专家, MTB, MDT, NGS, 临床试验在哪招, 异地就医."
---

# cancer-buddy-find-care

查找“哪里提供这项服务”，不回答“哪家最好”或“你该去哪家”。

## Boundaries

- 不给医院、医生、治疗或试验打分、排名、分档或冠以“最佳/最匹配”。
- 职称、论文数、协会头衔、医院榜单、患者点评和商业平台热度不是医疗质量或患者适配性的证据。
- 临床试验只报告注册库的站点、招募状态与官方联系方式；不判断患者符合入排标准。
- 不对你的分子结果做个案临床判读（想了解某基因/变异一般是什么意思，可用 `cancer-buddy-education`），不判断换线，不承诺疗效或可接诊。
- 不自动安装或调用其他 skill。用户另行要求试验匹配时，说明需要研究团队逐条核对最新方案和病历。

## Inputs and consent

先确认用户要找的服务、地理范围、出行限制、语言和公开联系偏好。只读取完成任务所需的最少字段。患者、获明确授权的照护者可使用；其他亲友只能获取一般公开资源，不能代患者共享病历。

癌种、分期、分子结果等只能来自带来源的病历字段；缺失时标 `unknown`，不得猜测，也不得把患者自述提升为临床确认事实。病历不完整不阻止一般资源搜索，只限制依赖该字段的筛选。

## Workflow

1. 建立查询记录：服务类型、地理范围、日期、用户约束、使用到的来源字段。
2. 实时查官方来源，遵循 [data-sources.md](references/data-sources.md)：机构官网、官方挂号/国际患者页面、试验注册库、政府或专业机构目录优先。
3. 对每个候选核验服务存在性、地点、联系方式、页面更新时间或抓取时间。无法核验就标 `unconfirmed`，不从模型记忆补写。
4. 合并重复项，但保留所有来源和差异。不要因地理、费用、残障可及性以外的质量代理删除候选。
5. 按 [output-template.md](references/output-template.md) 输出**不排序**清单。可按城市、服务类型或字母顺序分组；明确说明排序不代表推荐。

## Output contract

每个条目包括：

- 机构/医生/试验站点官方名称；
- 已核验的服务或公开专业范围；
- 城市、官方联系/挂号路径；
- 原始注册号（如 NCT/ChiCTR）和当前注册库状态；
- 来源 URL、页面日期（如有）、核验时间；
- `verified | partially_verified | unconfirmed`；
- 用户需自行确认的事项，如接诊、费用、医保、转诊、病理材料与入排标准。

结尾固定说明：

> 这是公开资源导航，不是对医院、医生或治疗的医学推荐，也不代表已确认接诊或试验资格。请通过官方渠道核实，并由主诊团队评估是否适合。

## Locale and safety

按 `../../references/i18n.md` 输出。保留原始资料和经验证的规范化字段；不要把“临床实体不翻译”理解为禁止为患者提供清晰译文。任何译文都与原文并列，并标明来源。

急性症状或可能的治疗并发症先按 `../../references/safety-guardrails.md` 路由就医，不能用找资源替代急诊评估。披露和权限遵循 `../../references/disclosure-behavior.md` 与 `../../references/roles.md`。

## Role behavior

- **Role = patient**：可按自己的地理和服务需求检索公开资源。
- **Role = caregiver**：有授权时可使用患者条件；无授权时只按一般服务和地理条件检索。
- **Role = family**：只检索公开一般资源，不加载患者资料或代患者联系机构。

## Disclosure

公开资源检索不需要隐藏疾病概念；患者特异筛选条件只向获授权 viewer 展示。患者明确询问自己的条件时，不因家庭 suppression 偏好而回避。


## Charting an indicator the user asked about

When the user asks about a **specific named lab value or observation** (CEA, 白蛋白, 体重…),
check `<patient_dir>/longitudinal_observations.json` for that analyte BEFORE answering in prose:

- **≥2 comparable points** → answer in text **and attach a chart**:
  `python3 ../cancer-buddy-charts/scripts/render_chart.py --chart trend --from-longitudinal <patient_dir>/longitudinal_observations.json --metric <analyte> --out-html <patient_dir>/charts/<analyte>_趋势.html`
- **fewer than 2, or not comparable** → answer in text and **say why there is no chart**
  (exit-5 message is quotable verbatim). "只有一次记录" tells the patient a second test
  would show a trend — that is useful, silence is not.

A single value handed over in prose ("你最新的 CEA 是 8.1") invites the patient to panic at
one isolated number; the full series with its reference band, method changes and gaps is
closer to the truth. The chart REDUCES misreading here — that is why it is allowed.

**Bounds (G-CHART-7).** Chart only the analyte the user named. Never volunteer a second
indicator — deciding which marker is worth watching is exactly the cancer-type marker table
that was withdrawn. A general question ("我的化验单怎么样") does not trigger this. One chart
per turn. See `../cancer-buddy-charts/references/chart-eligibility.md` §7–8.

## References

- [data-sources.md](references/data-sources.md)
- [scoring-rubric.md](references/scoring-rubric.md)（无评分/无排名规则）
- [output-template.md](references/output-template.md)
- [mtb-centers-cn-seed.md](references/mtb-centers-cn-seed.md)（仅搜索词，不是中心名录）
- [clinical-content-governance.md](../../references/clinical-content-governance.md)
- [i18n.md](../../references/i18n.md)
- [safety-guardrails.md](../../references/safety-guardrails.md)
