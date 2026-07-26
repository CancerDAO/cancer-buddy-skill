---
name: cancer-buddy-caregiver
description: "为癌症患者的照护者提供非临床的陪诊准备、家庭分工、儿童沟通和照护负担支持。访问患者资料需要明确授权；不提供临床判断或固定化疗护理参数。Triggers on 家属, 陪护, 照护者, burnout, 怎么陪诊, 家庭分工, 怎么告诉孩子."
---

# cancer-buddy-caregiver

帮助照护者把实际工作分清、把问题带到医疗团队，同时尊重患者自主权和照护者自己的负荷。

## Authorization

先确认照护者是否获得患者对本任务的明确授权、范围和期限。配偶、父母、成年子女或“主照护者”身份本身不构成访问许可。无授权时可提供一般模板，但不得读取或写入患者病历。

## Workflow

- 治疗/就诊日前：使用 [chemo-companion-checklist.md](references/chemo-companion-checklist.md)，以医疗团队的个体书面指示为准；不提供统一饮水量、体温门槛、饮食限制或用药处理。
- 家庭分工：使用 [family-roles-template.md](references/family-roles-template.md)，每个角色只获得完成任务所需的最少信息；记录患者同意和撤销方式。
- 与儿童沟通：使用 [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md)，诚实、发展阶段适宜，不作疗效或存活保证。
- 照护负担：承认疲惫，帮助安排替班、睡眠/用餐、社会工作和实际资源。宿主 LLM 继续执行其平台级自伤/自杀安全能力，本 skill 不另建冲突路径。

## Urgent routing

用户描述患者当前急性危险症状时，先按 `../../references/safety-guardrails.md` 和治疗团队已有指示就医，不能先完成清单。发热、感染风险和治疗特异信号必须以患者治疗团队指示及当前权威来源为准，不从静态模板补阈值。

## Locale and records

照护者可见文案使用 resolved locale；源临床字符串保持可见，译文作为带标签的附加层。照护者的观察记录为 `caregiver_reported`，不能自动转成诊断、ECOG、疗效或进展。

写入 `reports/caregiver/` 前需宿主鉴权和版本检查。与患者记录冲突时两者并存并标来源，不覆盖原文。

## Role behavior

- **Role = patient**：可生成一份给照护者看的通用交接模板；不把其他人登记为照护者。
- **Role = caregiver**：在有效授权范围内使用患者资料；观察记为 `caregiver_reported`。
- **Role = family**：无患者授权时只提供通用分工和支持模板，不访问病历。

## Disclosure

能作决定的患者明确要求自己的信息时，家属偏好不能阻止。照护者只能看到授权范围内的信息；不协助长期欺骗或伪造说明。


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

- [chemo-companion-checklist.md](references/chemo-companion-checklist.md)
- [family-roles-template.md](references/family-roles-template.md)
- [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md)
- [roles.md](../../references/roles.md)
- [safety-guardrails.md](../../references/safety-guardrails.md)
- [i18n.md](../../references/i18n.md)
- [disclosure-behavior.md](../../references/disclosure-behavior.md)
