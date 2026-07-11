# NCCN Distress Thermometer — 苦难温度计

> **Locale (i18n).** The thermometer prompt, the problem-list categories/items and the interpretation labels below are the `zh` source rendering. Per `../../cancer-buddy/references/i18n.md`: present the 0-10 thermometer and the problem list to the patient in the resolved locale (host `locale` first, otherwise `profile.json.locale`, otherwise conversation-language fallback), using the NCCN-validated translation for that locale where one exists. Keep the scale name "NCCN Distress Thermometer", the 0-10 range, the problem-list category structure and all numeric cutoffs (0-3 / 4-6 / 7-10) **invariant across locales**. The routing actions (→ PHQ-9 / → GAD-7 / → the SKILL.md direct safety assessment) key on the items, not their language.

## 问题 1：温度计

在过去一周内（包括今天），您感受到的 distress（痛苦、困扰、烦恼）有多强烈？

```
  10 极度痛苦
   9
   8
   7
   6
   5
   4
   3
   2
   1
   0 毫无痛苦
```

请选一个数字 (0-10):

## 问题 2：问题清单

请勾出过去一周里您遇到的问题（多选）：

### 实际问题
- [ ] 住房
- [ ] 保险/经济
- [ ] 交通
- [ ] 工作/学习
- [ ] 照顾孩子
- [ ] 其他

### 家庭问题
- [ ] 和配偶/伴侣的关系
- [ ] 和孩子的关系
- [ ] 和其他家人的关系
- [ ] 要照顾的家人生病

### 情绪问题
- [ ] 抑郁 → 建议继续 PHQ-9
- [ ] 恐惧
- [ ] 紧张 → 建议继续 GAD-7
- [ ] 悲伤
- [ ] 担心
- [ ] 对过去活动失去兴趣
- [ ] 对信仰/意义的困惑

### 身体问题（选主要的 3 个）
- [ ] 外观改变 (脱发/皮疹/体重变化/手术痕迹)
- [ ] 洗澡/穿衣
- [ ] 呼吸
- [ ] 排便（便秘/腹泻）
- [ ] 进食
- [ ] 疲倦 → 几乎所有癌症患者有
- [ ] 感觉胀气
- [ ] 发烧 → 立即联系医生
- [ ] 活动/行走
- [ ] 消化不良
- [ ] 记忆/注意
- [ ] 口腔疼痛
- [ ] 恶心 → 化疗期常见
- [ ] 鼻塞
- [ ] 疼痛
- [ ] 性问题
- [ ] 皮肤干燥/瘙痒
- [ ] 睡眠问题
- [ ] 底物使用（酒/烟）

## 解读

| 温度计 | 建议 |
|---|---|
| 0-3 | 轻度 — 观察 + 自助策略 |
| 4-6 | 中度 — 建议和医生/护士讨论；跑 PHQ-9 和 GAD-7 精确分型 |
| 7-10 | 重度 — 需要专业心理支持或精神科评估 |

勾选的问题决定下一步：
- 实际/家庭问题为主 → 可能需要社工或家庭治疗
- 情绪问题为主 → 跑 PHQ-9 / GAD-7
- 身体问题为主 → 副作用处理交主诊医生（已装私有 pro-skill `cancer-buddy-manage` 时可走它）；持续 > 2 周同时跑 PHQ-9（身体疼痛和抑郁常共病）
- **任何自伤/自杀念头提及** → 立即走 SKILL.md 的直接安全评估 + 危机规则（正式 C-SSRS 仅在用户同意后作为补充，不是获得帮助的前置条件）
