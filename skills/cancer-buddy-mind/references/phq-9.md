# PHQ-9 — 患者健康问卷-9 (depression screener)

> **Locale (i18n).** The item text and rating labels below are the `zh` source rendering. Per `../../../references/i18n.md`: present these 9 items and the 0-3 rating anchors to the patient in the resolved locale (host `locale` first, otherwise `profile.json.locale`, otherwise conversation-language fallback). Use the validated translation of PHQ-9 for that locale where one exists; keep the scale name "PHQ-9", the item order, the 0-3 scoring, and every numeric cutoff in the scoring table **invariant across locales**. The `题 9` hard-trigger rule keys on item index 9 + score, not on any language. Do not invent items.

过去两周里，您有多少时候受到以下问题的困扰？

按 0-3 评分: 0=完全没有, 1=有几天, 2=一半以上的天数, 3=几乎每天

1. 做事时提不起劲或没有兴趣
2. 感到心情低落、沮丧或绝望
3. 入睡困难、睡不安稳或睡眠过多
4. 感觉疲倦或没有活力
5. 食欲不振或吃太多
6. 觉得自己很糟，或觉得自己是个失败者，或让自己或家人失望
7. 对事物专注有困难，例如阅读报纸或看电视时
8. 动作或说话速度缓慢到别人已经觉察？或正好相反——烦躁或坐立不安、动来动去的情况更胜于平常
9. **有不如死掉或用某种方式伤害自己的念头**

## 评分

总分 0-27:

| 总分 | 程度 | 建议 |
|---|---|---|
| 0-4 | 无/极轻 | 观察 |
| 5-9 | 轻度 | 自助 + 2 周后复测 |
| 10-14 | 中度 | 建议心理咨询 |
| 15-19 | 中重度 | 建议心理咨询 + 精神科评估 |
| 20-27 | 重度 | 立即寻求精神科 |

## 硬触发（立即 crisis）

- **题 9 ≥ 1**（任何频率的自伤/自杀念头）→ 立即触发 cancer-buddy-mind 危机规则，不管总分如何
- 总分 ≥ 20 → 同上

保留：最终选项与 [c-ssrs-lite.md](c-ssrs-lite.md) 交叉验证。

## 纵向追踪

每 2-4 周一次。保存到 `patients/<patient_code>/reports/mind/phq9-YYYY-MM-DD.md`。
