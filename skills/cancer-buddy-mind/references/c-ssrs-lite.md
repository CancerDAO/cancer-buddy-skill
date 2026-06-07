# C-SSRS Lite — 哥伦比亚自杀严重程度量表（精简版）

> **Locale (i18n).** The 6 items below are the `zh` source rendering. Per `../../../references/i18n.md`: present them to the patient **in `profile.json.locale`** (read it; detect from conversation language if absent), using the validated C-SSRS translation for that locale where one exists. Keep the scale name "C-SSRS", item order, the yes/no logic and the "any yes → crisis rule" trigger **invariant across locales** — the trigger keys on the boolean answer, never on language. When a positive answer fires the crisis rule, the crisis acknowledgment and `crisis-resources.md` guidance are also surfaced in `locale` (hotline numbers/institutions verbatim).

## 问题 1

过去一个月里，你是否有过希望自己死去的念头？

- [ ] 是
- [ ] 否

## 问题 2

过去一个月里，你是否有过自杀的念头？

- [ ] 是
- [ ] 否

若以上均为否 → 筛查通过，返回主对话。

若问题 2 为是，继续：

## 问题 3

你是否想过怎么做？

- [ ] 是
- [ ] 否

## 问题 4

你是否有过真的想做的意图？

- [ ] 是
- [ ] 否

## 问题 5

你是否开始具体计划过细节（时间、地点、方式）？

- [ ] 是
- [ ] 否

## 问题 6

你是否为此做过任何准备或行动（例如获取药物、工具、写遗书）？

- [ ] 是
- [ ] 否

## 评估规则

**任何一题为"是"都触发 `cancer-buddy-mind` 危机规则。** 不需要所有题都回答。问题 3-6 任一阳性属于"活跃自杀意念"，是高风险。

## 执行

发现阳性答案时：
1. 立即停止 C-SSRS 继续提问——不要继续施加"你有计划吗"这类问题
2. 运行 `crisis-resources.md` 全文
3. 保存 `patients/<patient_code>/reports/mind/crisis-YYYY-MM-DD.md` 记录
4. 陪伴用户完成至少一个具体的求助行动（拨打热线 / 联系家人 / 去急诊）后才结束会话
