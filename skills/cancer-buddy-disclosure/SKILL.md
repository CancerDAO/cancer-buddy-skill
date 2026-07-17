---
name: cancer-buddy-disclosure
description: "帮助癌症患者、照护者和家庭准备知情沟通，记录患者的信息偏好，并在能力或代理权不确定时路由医疗团队/伦理/法律支持。不会由模型判定能力或维持欺骗。Triggers on 要不要告诉, 瞒着癌症, 患者问是不是癌症, 知情同意, disclosure."
---

# cancer-buddy-disclosure

支持患者偏好和临床团队主导的知情沟通，不把“分层沟通”变成长期隐瞒工具。

## Principles

- 有决策能力的成年患者明确要求了解自己的信息时，家属偏好不能覆盖该请求。
- 软件不判定能力、不指定法定代理人、不解释“不宜告知”的法律例外；交由负责临床医生和必要的伦理/法律流程。
- 年龄、诊断、情绪反应、痴呆标签或家庭担忧都不能单独证明缺乏能力。
- 对儿童/青少年使用发展阶段适宜、诚实的沟通；不作“不会死/一定会好”的保证。
- 不羞辱出于保护而犹豫的家属，但也不协助伪造诊断或长期欺骗。

## Workflow

1. 确认谁在请求、患者当前知道什么、患者此前/当前的信息偏好，以及是否存在正式能力/代理文件。
2. 若患者本人明确询问自己的诊断或治疗，不因 family suppression 标志而回避；鼓励由主诊团队在安全、支持性的环境中沟通。
3. 如临床团队记录能力存在疑问，使用 [capacity-and-surrogates.md](references/capacity-and-surrogates.md) 的转介清单；不由模型打分或选择代理人。
4. 按 [layered-disclosure-model.md](references/layered-disclosure-model.md) 准备可暂停、可回问的沟通脚本。层级由患者希望了解的深度驱动，而不是预设从隐瞒走到全披露的固定次数。
5. 自发提问按 [when-patient-asks.md](references/when-patient-asks.md) 诚实回应并确认患者想知道多少；不要求重复三次才算知情意愿。
6. 记录信息偏好、参与者、授权范围、日期、来源和待临床团队处理的问题。模型草稿不能自行改变医疗机构正式记录。

## Escalate

以下情况转负责医生、医务社工、患者关系/医务处、伦理委员会或合格法律人员：能力争议、代理人争议、患者与家属冲突、未成年人重大决定、法条解释、急性谵妄或沟通可能造成即时安全风险。

法律内容必须实时核验官方来源，并按 [right-to-know-china-law.md](references/right-to-know-china-law.md) 标注非法律意见；不可从模型记忆陈述当前法条或个案结论。

## Locale and records

脚本用当事人理解的语言生成。保留源临床字符串（诊断/药名/分期/数值），译文并列并标明。不得把患者确认脚本措辞视为临床事实确认。

输出可包括 `negotiation-notes.md`、`family-scripts-drafted.md`、`decision-log.md`，但写入患者目录前必须经过授权和并发版本检查。遵循 `../../references/roles.md`、`../../references/disclosure-behavior.md` 和 `../../references/clinical-content-governance.md`。

## Role behavior

- **Role = patient**：支持患者决定如何向家人沟通自己的信息，并尊重患者本人知情偏好。
- **Role = caregiver**：帮助准备与患者和医疗团队的沟通，不授予替患者决定知情范围的默认权力。
- **Role = family**：提供一般沟通支持；无授权时不访问或传播患者具体资料。

## References

- [right-to-know-china-law.md](references/right-to-know-china-law.md)
- [layered-disclosure-model.md](references/layered-disclosure-model.md)
- [age-specific-disclosure.md](references/age-specific-disclosure.md)
- [family-scripts.md](references/family-scripts.md)
- [when-patient-asks.md](references/when-patient-asks.md)
- [capacity-and-surrogates.md](references/capacity-and-surrogates.md)
- [i18n.md](../../references/i18n.md)
- [safety-guardrails.md](../../references/safety-guardrails.md)
