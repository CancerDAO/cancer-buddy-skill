# 第一方指令（主诊团队对本人的交代）

`safety-guardrails.md` 与 `clinical-content-governance.md` 有四处条款把「主诊团队的书面交代」
列为**最高优先级来源**，公共指南只是它不可用时的 fallback：

- `safety-guardrails.md` §Urgency：Follow the patient's written oncology-team instructions when available.
- 同上：化疗期发热 use the team's treatment-specific threshold and contact route；**没有**时才去核验公共指南
- `clinical-content-governance.md` §Red flags：Use the treating team's written emergency plan when available.
- 同上：follow that team's stated temperature threshold

本文件定义这类内容存在哪、怎么建模、怎么引用、什么时候失效。

## 1. 存放位置

`<patient_dir>/10_随访与监测/团队交代/`（slug `team_instructions`）。它是**档案的一部分**，
不是参考资料——参考资料在 `library/`，见 `reference-library.md`。

放进来的是：出院小结里的联系与阈值交代、化疗宣教单、PICC/造口维护卡、口服药服法与漏服处理、
条件式随访指令（"CEA 升高提前来"）、试验知情同意书里的随访与联系条款。

## 2. `instruction_source`：转述者 ≠ 指令来源

`provenance_layer` 的四值（`source_reported | patient_reported | caregiver_reported |
system_normalized`）描述的是**谁说的**，无法表达**这条指令原本出自谁**。患者口述
「医生说我发烧超过 38 就打电话」时，provenance 是患者，指令来源却是团队——两者可信度不同。

因此每条第一方指令带一个正交维度：

| `instruction_source` | 含义 | 引用规则 |
|---|---|---|
| `team_written` | 团队书面，有源文件锚点 | 可直接引用并据以行动 |
| `team_verbal_relayed` | 团队口头交代，经患者/照护者转述 | 可引用，但必须在正文点明"这是你告诉我的"，**并强制并列公共 fallback** |
| `patient_interpretation` | 患者自己的理解或推断 | **永不作为指令依据**，只能作为带给医生的问题素材 |

`team_verbal_relayed` 必须并列 fallback 的理由很具体：患者可能把 38.0 记成 38.5。
急诊阈值上的转述误差会直接造成伤害，所以「引用 + 并列公共来源 + 提示与团队复核」是三件套，
不是可选项。

## 3. 必填字段

`stated_at`（交代日期）、`stated_by`（交代人或机构，"管床医生"这类非实名写法可接受）、
`linked_treatment_line`（关联 `treatment_lines.json` 的条目）、`source_ref`
（档案锚点，`team_written` 必填）。

## 4. 失效：指令比指南过期得快

指南有出版者版本号，个人指令没有。方案 2–3 个月一换，阈值随方案变——2024 年一线定的
「38.0 打电话」，2026 年换成免疫治疗后阈值和急诊路径都可能不同。

- `treatment_lines.json` 出现新线时，旧线关联的指令自动标 `possibly_superseded`
- 引用 `possibly_superseded` 的指令时，必须显示原始日期并提示与团队确认
- 被取代的原件按 `upload-reconciliation.md` 归档到 `_superseded_<ts>/`，不删除

## 5. 引用方式

第一方指令**本来就在档案里**，用 `〔档案〕` 标签，不新造标签（见 `citation-format.md`）。
出处用自然语言写进正文：

> 你出院小结上写着「体温≥38.0℃ 立即联系管床医生 13x-xxxx-xxxx」<sup>[1]</sup>，
> 你现在 38.4℃ 已经超过这条线了——现在就打这个电话。打不通就直接去当地急诊。
> 这条记录于 2026-05-12，对应你当时的方案；如果之后换过方案，联系上团队时顺便确认一下。

## 6. 它放开什么、不放开什么

有团队书面交代时，原本收紧的问题**可以据实回答**：漏服怎么处理、发热找谁、导管多久换、
复查条件触发项。依据不是模型判断，是患者团队的白纸黑字。

**但它不放开个案判决轴**：分期、ECOG、疗效、进展、预后、换线、试验入组资格，
即使档案里有相关文字，也只能**转述团队写了什么**，不能由产品作出新的判断。
「医生写了 PR」是转述；「你达到了 PR」是判决。
