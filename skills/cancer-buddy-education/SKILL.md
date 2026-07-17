---
name: cancer-buddy-education
description: "生成来源可追溯的肿瘤患者教育材料，解释稳定概念并把个体问题整理给主诊团队。指南、药品标签、获批状态、预后数字、随访和急诊阈值必须在回答时从版本可核验的一手来源读取：可用用户合法持有的现行指南并标版本/页码，否则实时查官方来源；不可用时失败关闭，不以模型记忆兜底。Triggers on 患者教育, 宣教手册, 看懂癌症, 看懂治疗, NCCN, CSCO, 指南建议, 严不严重, 能治好吗."
---

# cancer-buddy-education

患者教育帮助理解概念，不能把一般知识变成个人诊断、预后或治疗方案。

## Inputs and provenance

可读取来源型 `patient_summary.json`、`molecular.json`、`treatment_lines.json`、`comorbidities.json` 与具体 `source_refs`。缺失或冲突字段标明，不阻止一般概念教育。`readiness.json` 仅用于 documentation coverage/来源忠实度，不作分数或全局阻断。

每条患者特异信息标注 `source_reported | patient_reported | caregiver_reported | system_normalized`、日期和来源。只复制医生来源明确写出的分期、ECOG、疗效和进展。

## Evidence modes

### Stable conceptual education

可解释“病理、分期、基因检测、放疗、化疗、靶向、免疫、缓和医疗是什么”等稳定概念。必须使用条件性措辞，不能判断患者落在哪一分支。

### Version-sensitive education

以下内容每次都按 [guideline-lookup.md](references/guideline-lookup.md) 在回答时核验一手来源：具体方案与线次、检测建议、剂量/给药、药品说明书、相互作用、批准/报销状态、临床试验、随访频率、急诊阈值、预后/生存数字、法律。可读取用户合法持有且版本清楚的对口现行指南并记录页码，否则实时查官方来源。记录发布者、标题、版本/日期、直接 URL 或受控本地来源引用，以及访问日期。

来源不可访问或不能验证时，明确说“本次未能核实”，不输出具体药名组合、线次、阈值、批准状态、存活数字或法律结论；不得从模型记忆补写。

## Workflow

1. 确认用户要理解的概念和希望的深度。
2. 将已知个体信息与一般教育分栏，避免两者混在一句话里。
3. 对版本敏感主张执行 answer-time 来源核验；不同地区/指南差异并列，不替患者选择。
4. 按 [handbook-template.md](references/handbook-template.md) 生成手册或短答。癌种模块与 FAQ 只提供提问框架，不能自带静态方案，见 [cancer-type-modules.md](references/cancer-type-modules.md) 与 [expanded-faq.md](references/expanded-faq.md)。
5. 结尾提供一组带给主诊团队的问题，并列出尚未核实或缺失的来源。

## Medication and urgent-care content

- 药物页只解释经当前官方说明书核验的用途、常见/严重风险、相互作用和患者应遵循的机构联系指引；不建议停药、改剂量或自行处理。
- 不把一个固定体温或实验室阈值当作所有治疗的通用规则。若用户正在接受化疗，强调发热可能是急症，并让其遵循肿瘤团队给出的个体阈值；需要引用通用公共卫生建议时实时核验并注明适用范围。
- 当前出现呼吸困难、意识改变、大量出血、严重过敏反应或治疗团队列出的急症信号时，先按 `../../references/safety-guardrails.md` 路由，不等待手册生成。

## Locale and disclosure

按 resolved locale 解释。保留源临床字符串：源药名、基因、变异、TNM、数值和单位保持可见；翻译/规范化并列且带标签。一个有能力的患者明确要求自己的信息时，不因家属 suppression 偏好拒绝；依法/依授权只展示该 viewer 有权访问的内容。

## Outputs

可写入 `patients/<pid>/reports/education/`：

- 患者教育手册；
- quick-reference card；
- 经回答时现行官方标签核验的药物信息页；
- 来源清单与检索日期。

每个产物注明：这是教育材料，不是个体诊断或治疗建议；用药和就医决定按主诊团队的具体指示。

每个产物还必须：

- 在正文直接显示连续、无缺口的编号脚注；每条脚注标 `〔档案〕`、`〔本地指南〕`、`〔联网〕` 或 `〔文献〕`，并与对应原子主张一一关联；
- 对本地指南标发布者、标题、版本/日期、页码和受控来源引用；不得在患者输出中泄露主机绝对路径；
- 对联网来源标直接 URL 和访问日期；
- 尊重版权与部署场景的再分发限制，不将付费指南表格默认打包给第三方；
- 每份手册、quick-reference card 和药物页保留“不替代主诊医生的判断/任何治疗调整须与主诊医生确认”的同义 footer。

## Role behavior

- **Role = patient**：在认证后查看自己的来源型信息和一般教育；明确知情请求不因家属偏好被拒绝。
- **Role = caregiver**：只在有效授权范围内使用患者资料；否则提供一般教育。
- **Role = family**：只提供一般教育和支持方式，不披露患者特异内容。

## Disclosure

披露规则用于防止向无权 viewer 暴露，不用于拒绝一个有能力患者对自身信息的明确请求。存在能力/代理争议时由临床与伦理/法律流程处理。

## References

- [guideline-lookup.md](references/guideline-lookup.md)
- [handbook-template.md](references/handbook-template.md)
- [mechanism-diagrams.md](references/mechanism-diagrams.md)
- [cancer-type-modules.md](references/cancer-type-modules.md)
- [expanded-faq.md](references/expanded-faq.md)
- [clinical-content-governance.md](../../references/clinical-content-governance.md)
- [safety-guardrails.md](../../references/safety-guardrails.md)
- [i18n.md](../../references/i18n.md)
- [disclosure-behavior.md](../../references/disclosure-behavior.md)
