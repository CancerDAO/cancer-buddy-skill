# 调研需求覆盖矩阵 (2026-05)

把 2026-05 用户调研里 12 个候选功能逐项对照到当前公开版 cancer-buddy-skill（含按需自动安装的 [clinical-trial-matching](https://github.com/CancerDAO/clinical-trial-matching-skill) companion）。每项给出：投票占比、覆盖判定、走哪个 sub-skill、用户视角的真实调用示例、缺口（如有）。

## 总览

| # | 投票 | 功能 | 覆盖 | 路径 |
|---|---|---|---|---|
| F | 65% | 临床试验智能匹配 | ✅ | `find-care` 出短名单 → 自动拉 `clinical-trial-matching` 跑 criterion 级匹配 |
| A | 55% | 跨境医疗助手 | ✅ | `organize` + `find-care` + `second-opinion` 三件套 |
| G | 40% | AI 心理健康伙伴 | ✅ | `mind`（PHQ-9/GAD-7/Distress/C-SSRS Lite + 危机热线） |
| J | 35% | 医学报告"人话翻译器" | 🔶 | `organize` 的 `review_summary.md` 部分覆盖；缺单文件原子入口 |
| I | 25% | 中药/补品 × 抗癌药交互 | ✅ | `nutrition` 的 `drug-food-interactions.md` + `forbidden-supplement-claims.md` |
| B | 20% | 一家人的慢病管家 | ❌ | 主动 out-of-scope（搭子只管癌症路上的事） |
| C | 10% | 出院后居家护理助手 | ⚠️ | `caregiver` 有单次 chemo-companion checklist；缺"每日症状日志 → 周报给医生"持续追踪流 |
| D | 10% | 治疗费用规划师 | ⚠️ | `education` 含 cost/insurance 章节；`find-care` 短名单含费用注释；缺"方案 A vs B 总成本"专项工具 |
| L | 10% | 治疗期营养方案生成器 | ✅ | `nutrition`（phase-based + 中式菜谱模板） |
| E | 0% | 身心状态守护（每日主动评估） | ⚠️ | `mind` 有筛查；缺主动 daily-check-in 引擎 |
| H | 0% | 女性周期 / 激素管理 | ❌ | 不在 scope（普通女性健康，非癌陪伴专项） |
| K | 0% | 复诊问题清单生成器 | ⚠️ | `organize.review_summary.md` + `education.quick-reference-card.md` 可拼；缺"基于上次治疗自动生成 Top 5 问题"原子 |

**直接覆盖 5 项**（F / A / G / I / L），其中 F 是带最多票的功能，刚通过 lazy-install companion 闭环。
**部分覆盖 4 项**（J / C / D / K）—— 都有切入点但缺专项原子。
**主动不做 2 项**（B / H）—— 超出 cancer companion scope。
**仅工具缺口 1 项**（E）—— 需要主动监控引擎。

## 详细场景与示例

### F — 临床试验智能匹配（65% 投票，✅）

**用户原话**：自动整合全平台临床试验信息，根据你的诊断和病情筛选正在招募的试验，给出最近的几个建议。

**路径**：[`cancer-buddy-find-care`](../skills/cancer-buddy-find-care/SKILL.md)（资源发现）→ 用户要求 criterion 级匹配时，find-care 自动 `npx skills add` 拉 [`clinical-trial-matching`](https://github.com/CancerDAO/clinical-trial-matching-skill)（≈3 s）→ Skill 工具调用 companion。

**示例**：

```
👤 用户："我妈非小细胞肺癌 EGFR 19del 经治后耐药，杭州/上海有哪些在招的临床试验？"

🤖 搭子（find-care）：
  - 读 patients/PT-XX/profile.json（cancer_type, molecular_profile, geo）
  - 并行 dispatch 多个 subagent：ChiCTR / ClinicalTrials.gov / 复旦肿瘤 / 上海胸科 / 浙大一院招募页
  - 输出 SHORTLIST.md：
    1. NCT0XXXXXXX  第三代 TKI 耐药后 amivantamab+lazertinib  上海胸科  匹配度高
    2. ChiCTR2XXXXXXX  HER3-DXd  浙大一院  匹配度中
    3. ...
  - 末尾追加：「这份名单只是把"在招"的试验筛了一遍，不等于你符合入排标准。
    要做 criterion 级匹配，跑 clinical-trial-matching skill。
    一句话触发：给 patients/PT-XX 跑临床试验匹配」

👤 用户："好，跑一下"

🤖 搭子：
  - 检查 ~/.claude/skills/clinical-trial-matching/ → missing
  - 告知用户："我先把 clinical-trial-matching companion 装上（CancerDAO 开源，约 3 秒）"
  - 跑 npx skills add CancerDAO/clinical-trial-matching-skill -g --all
  - Skill 工具调用 clinical-trial-matching
  - 输出决策报告（HTML）：
    · 入排逐条 CoT 评估（R1-R5 硬规则）
    · 机制风险注释
    · vs 标准治疗 head-to-head
    · Top-N 决策合成 + Goals-of-Care 触发
```

**为什么 F 在这一版完全闭环**：cancer-buddy 公开版主动不做临床判断（companion-scope），但用户最高票需求恰好是"criterion 级匹配"——这是 clinician-grade 工作。通过 lazy-install + 路由把工作转给 [`clinical-trial-matching-skill`](https://github.com/CancerDAO/clinical-trial-matching-skill)，既不破坏 scope 边界又能闭环。

---

### A — 跨境医疗助手（55%，✅）

**用户原话**：把散落在不同城市/医院的病历整合成一条时间线，同时帮你判断某个病该去香港 / MSK / MDA 看。

**路径**：[`organize`](../skills/cancer-buddy-organize/SKILL.md)（病历→时间线）→ [`find-care`](../skills/cancer-buddy-find-care/SKILL.md)（查具备跨境会诊接收资格的医院）→ [`second-opinion`](../skills/cancer-buddy-second-opinion/SKILL.md)（出英文 packet）。

**示例**：

```
👤 用户："我爸结直肠癌肝转移 3 处，国内化疗 6 程效果一般，想看跨境会诊。
        手里有北京肿瘤、上海中山、协和的病历共 73 份文件"

🤖 搭子（organize）：
  - fan-out 6 个 Phase 1 worker 并行 OCR（73 张图按 3 家医院 ×2 半切分）
  - Phase 2 synthesis：跨切片 review_flags audit + readiness 打分
  - 输出 patients/PT-XX/timeline.md（按时间序列：诊断→分期→T1/T2 化疗→复查→...）
  - 显示 review_summary.md 让用户核对 5 个关键字段
  - readiness_grade = B（缺 NGS 报告）

👤 用户："NGS 报告我有的，可以再加进去吗"
🤖 搭子（organize 增量）：跑一次 retry-mini-Phase1 → readiness 升到 A

👤 用户："好，那 MSK 和 MD Anderson 怎么选？"

🤖 搭子（find-care）：
  - 出短名单：MSK GI 团队（接收，需 PDF 病例 + 邮寄玻片）/ MDA 结直肠科 / 香港养和（中文病例直接接收）
  - 给挂号路径 + 大致费用 + 排期

👤 用户："那走 MSK"

🤖 搭子（second-opinion，target=MSK）：
  - 生成 patients/PT-XX/reports/second-opinion/MSK/：
    · case-summary.md（1-2 页英文）
    · records-index.md（病理/NGS/影像清单）
    · cover-letter.md（doctor-to-doctor，250-400 字）
    · shipping-instructions.md（DHL 流程 + customs declarations）
    · presentation-script.md（拿到二意见后跟主诊医生怎么沟通）
```

**Gap 提示**：搭子不主动建议"该去 MSK 还是 MDA" 这种临床决策——遵循公开版 companion-scope，给资源短名单 + 让患者和主诊医生讨论。

---

### G — AI 心理健康伙伴（40%，✅）

**用户原话**：能做日常情绪疏导，也能在你需要时提供专业心理咨询的入口。

**路径**：[`cancer-buddy-mind`](../skills/cancer-buddy-mind/SKILL.md)。

**示例**：

```
👤 用户："这一周一直睡不着。看到爸的下次化疗单就喘不过气来"

🤖 搭子（mind）：
  - 总是先跑 C-SSRS Lite（1 题）：「过去一周有没有想过结束自己的生命？」
  - 用户答"没有"
  - 用户报告主诉=焦虑 → GAD-7（7 题）
  - 评分 12 → "Seek clinician" tier
  - 输出：
    · 写到 patients/PT-XX/reports/mind/gad7-2026-05-08.md
    · 自助 tier 内容：sleep hygiene 1 页 + 5-min mindfulness practice
    · 临床建议：「12 分意味着中度焦虑——这种状态自己扛 2-3 周以上不会自己好。
      建议看一次精神科或心理咨询。如果你在杭州，浙大一院心理卫生科和邵逸夫医院心身科都接诊」
    · 附：浙江省心理援助热线 0571-85029595（24 h）

👤 用户（一个月后）："最近想结束这一切，没意思"

🤖 搭子（crisis rule，非可覆盖）：
  - 立即停止任何工作流
  - 「我听到你说的了。这个念头出现本身就是一个信号——你现在需要专业的人立刻帮你」
  - 完整输出 crisis-resources.md（不是摘要——全部内容）：
    · 全国心理援助热线 400-161-9995
    · 北京心理危机研究与干预中心 010-82951332
    · 各省热线表
  - 「你现在身边有家人或朋友吗？能先让 Ta 知道你现在的状态吗？」
  - 不再问"什么让你这么觉得"或继续 GAD-7
  - 写 patients/PT-XX/reports/mind/crisis-2026-06-XX.md
```

**关键安全设计**：crisis rule 写死在 `cancer-buddy-mind/SKILL.md` 顶端，任何子技能检测到自杀念头都路由到 mind 走 crisis 流，不在原 sub-skill 处理。

---

### J — 医学报告"人话翻译器"（35%，🔶 PARTIAL）

**用户原话**：把病理报告、基因检测报告、影像报告翻译成你能看懂的语言——不只是逐字解释。

**当前路径**：[`organize`](../skills/cancer-buddy-organize/SKILL.md) Phase 2 输出的 `review_summary.md` 已经是"关键字段 + 原文证据 + 通俗解释"的 1 页清单；[`education`](../skills/cancer-buddy-education/SKILL.md) 在有 MTB 报告后生成完整宣教手册（含每个药物的 plain-language sheet）。

**示例**：

```
👤 用户："这是我妈刚拿的病理报告 PDF，能给我翻成人话吗？"

🤖 搭子（organize 单文件路径）：
  - 单文件 input → 跑单 Phase 1 worker → Phase 2 synthesis
  - 输出 review_summary.md：
    ┌────────────────────────────────────────────────────┐
    │ 1. 主诊断：浸润性导管癌（IDC）                       │
    │   通俗：乳腺里最常见的恶性肿瘤类型                   │
    │   原文：第 2 页 "诊断：(右乳)浸润性导管癌"           │
    │                                                    │
    │ 2. 分级：G2（中分化）                               │
    │   通俗：肿瘤细胞的成熟度中等——不是最好但也不是最差   │
    │   原文：第 3 页 "Grade: 2/3"                        │
    │                                                    │
    │ 3. 大小：2.3 cm                                    │
    │   通俗：肿瘤的最长直径，单位厘米                     │
    │ ...                                                │
    └────────────────────────────────────────────────────┘
  - 用户立即可以看懂前 5 个最关键字段
```

**Gap**：用户期望可能是"丢一份 PDF → 立即出整段解读"（不需要建 patient_code、不需要时间线）。当前必须走 organize 全流程（虽然单文件已经支持，但仍会建立 patient 目录）。

**建议**（不在本次 PR 范围）：加一个 `cancer-buddy-translate` 轻量级子技能或在 organize 加 `--quick-translate` 单文件模式，跳过建档直接输出 review_summary 风格的解读。

---

### I — 中药/补品 × 抗癌药交互查询（25%，✅）

**用户原话**：查你正在吃的西药和家里炖的汤、中药方子、保健品之间有没有冲突。

**路径**：[`cancer-buddy-nutrition`](../skills/cancer-buddy-nutrition/SKILL.md) 的 `drug-food-interactions.md` + `forbidden-supplement-claims.md`。

**示例**：

```
👤 用户："我妈在吃奥希替尼（第三代肺癌靶向药），家里炖了灵芝枸杞汤想给她喝，
        还有人参鸡汤每周一次。能喝吗？"

🤖 搭子（nutrition）：
  - 读 profile.json.current_therapy = ["Osimertinib"]
  - cross-check drug-food-interactions.md：
    · TKI ↔ 葡萄柚 / 橘子皮（CYP3A4 抑制 → 药效升高）：禁
    · TKI ↔ 圣约翰草（CYP3A4 诱导 → 药效降低）：禁
    · 灵芝（含 Triterpenoids，弱 CYP 干扰）：临床证据不足，不推荐与 TKI 同期连续大量服用
    · 人参（人参皂苷弱抗血小板）：与抗凝/抗血小板药需警惕；与 TKI 单独无明确冲突
  - check forbidden-supplement-claims.md：
    · 灵芝：尚无可靠循证支持抗肿瘤疗效；与 TKI 同期不推荐
    · 人参：无抗癌证据；适量可
  - 输出 interactions-flagged.md：
    🔴 不建议：TKI 期间灵芝汤每日服用
    🟡 警惕：人参鸡汤如果患者还在用阿司匹林，需主诊医生确认
    🟢 OK：枸杞（无 CYP 干扰证据）
  - 末尾："以上是循证证据视角的提醒，最终请和主诊医生确认"
```

---

### B — 一家人的慢病管家（20%，❌ OUT-OF-SCOPE）

**用户原话**：帮你管理全家人的慢病——统一排药、排饭、排复诊。

**为什么不覆盖**：搭子是 cancer companion，不是 family chronic disease manager。把全家慢病塞进来会模糊核心定位。

**示例**（搭子的回应）：

```
👤 用户："我爸糖尿病、我妈高血压、奶奶癌症在化疗，能一起管吗？"

🤖 搭子：
  「我能陪的是癌症路上的事——奶奶的化疗、副作用、心理、饮食、宣教手册我都能帮上。
   爸爸的糖尿病和妈妈的高血压属于慢病管理，不在搭子范围。可以试试 Apple Health
   / 微医的家庭健康记录，或者你们家的家庭医生是更合适的统一管理方。
   
   奶奶这边我可以做的：
   - 跑 organize 整理她的病历
   - 用 nutrition 给她按化疗期出 7 天菜单（如果你们一起吃饭，也会顺手考虑爸妈的限糖/限盐）
   - 用 caregiver 给你们家做分工模板，谁陪诊、谁取药、谁做饭」
```

---

### C — 出院后居家护理助手（10%，⚠️ PARTIAL）

**用户原话**：管理出院后的居家护理，每天记录副作用并生成结构化报告同步给医生。

**当前路径**：[`caregiver`](../skills/cancer-buddy-caregiver/SKILL.md) 的 `chemo-companion-checklist.md` 是单次（每次化疗一份），不是日度持续追踪。CTCAE 副作用分级是主动 out-of-scope（cancer-buddy-pro-skill 内部版才做）。

**示例**：

```
👤 用户："我老公胃癌术后出院第三天，每天有点恶心、刀口疼，怎么记下来下周复诊给医生看？"

🤖 搭子（caregiver）：
  - 跑 chemo-companion-checklist（虽然是术后不是化疗，但 checklist 适配）
  - 输出 patients/PT-XX/reports/caregiver/post-op-day3.md：
    · 今天观察的内容（体温、刀口、恶心/呕吐次数、疼痛 0-10 分、排便、活动量）
    · 红旗症状清单（什么情况立即就医）
  - 但这是单次报告，不是"每天自动提醒+周报合成"

⚠️ Gap：搭子目前不做：
  - 每天主动 ping 用户填症状日志
  - 自动按周聚合成给医生的结构化报告
  - 检测到趋势异常（连续 3 天疼痛 > 6）主动提醒
```

**建议**：加一个 `cancer-buddy-monitor` 持续追踪子技能，配合 hooks/scheduled-tasks 实现 daily check-in。架构上和 mind / caregiver 平级，专门做纵向数据。

---

### D — 治疗费用规划师（10%，⚠️ PARTIAL）

**用户原话**：结合病情、医保情况、实际生活成本（路费、住宿、误工），对比不同方案的总花费。

**当前路径**：[`education`](../skills/cancer-buddy-education/SKILL.md) 含 `## 费用与医保导航` 章节；[`find-care`](../skills/cancer-buddy-find-care/SKILL.md) 短名单条目含「潜在风险/限制（费用 / 等候期 / 异地医保）」。

**示例**：

```
👤 用户："靶向药月花 2 万 vs 化疗+免疫月花 5 千，但化疗要每月去外地，加上路费住宿误工
        总花费怎么算划算？"

🤖 搭子（当前能做的）：
  - education 出医保章节：靶向药是否进国谈/医保乙类，自付比例大概多少
  - find-care 出医院短名单：当地能做的医院 vs 必须跨城的医院
  - 提示："具体方案选择不在搭子范围（属于临床决策），但费用维度可以这样想：
    · 靶向药：可能进医保，自付 30-40%；但需药店续方
    · 化疗+免疫：医院执行，医保占比通常更高；但跨城需考虑路费住宿"

⚠️ Gap：缺一个把"方案 A 总成本 = 药费 × 月数 + 路费 × 次数 + 住宿 × 天数 + 误工 × 工资 + 报销返还"
        定量算清楚的工具。

建议：cancer-buddy-finance 子技能，读 profile.json + 用户输入的工资/通勤参数 → 出对比表。
不做"哪个方案更好"判断（仍是临床决策），只算成本。
```

---

### L — 治疗期营养方案生成器（10%，✅）

**用户原话**：针对你当前的治疗阶段，给出具体的饮食方案——化疗期白细胞低吃什么、放疗口腔溃疡吃什么。

**路径**：[`cancer-buddy-nutrition`](../skills/cancer-buddy-nutrition/SKILL.md)。

**示例**：

```
👤 用户："我妈下周一开始 FOLFIRINOX 第一程（胰腺癌），杭州人，能不能给一周菜单？
        她最近食欲也不好"

🤖 搭子（nutrition）：
  - 读 profile.json：primary_cancer=PDAC, current_therapy=FOLFIRINOX, location_hint=杭州
  - 识别 phase = "active chemo, oxaliplatin-containing"
  - 检查 drug-food-interactions：
    · 奥沙利铂 + 冷食 → 严重感觉异常（critical）
    · 5-FU + 大量叶酸/复合 B → 警惕（mild）
  - 加载 china-dietary-templates 的"江浙"模块
  - 输出 plan-2026-05-08.md：
    7-day menu（早中晚 + 加餐）：
    Day 1：早=温热豆浆 + 白粥 + 蒸蛋；午=白切鸡（温热）+ 冬瓜虾仁汤 + 米饭；
           晚=蒸鲈鱼 + 西兰花 + 山药粥
    Day 2-7：...
    
    特别提示（红色）：
    🔴 第一程开始 5 天内 → 所有饮食必须温热以上，避免冰水/冷饮/凉拌菜/冰镇水果
    🔴 喝水也要温的，刷牙水可以稍温
    🟡 口腔溃疡若出现 → Day 4 起改流食模板
  - 食欲差对策：6 餐制（每 2 h 少量）+ 高蛋白零食（蛋羹、奶昔）+ 餐前 30 min 散步
```

---

### E — 身心状态守护（每日主动评估，0% 投票，⚠️ PARTIAL）

**用户原话**：每天用简单的问答评估你和家属照护者的身心状态，检测到疲劳或情绪低落时主动提醒休息。

**当前**：[`mind`](../skills/cancer-buddy-mind/SKILL.md) 有完整筛查工具（PHQ-9 / GAD-7 / Distress / C-SSRS Lite），但需要用户主动开启会话。`caregiver` 的 Zarit 同样。

**Gap**：缺"主动每日 ping + 趋势检测 + 自动升级到 crisis 流"的 daemon。

**建议**：依赖 Claude Code 的 hooks / scheduled-tasks。可以做一个 `cancer-buddy-pulse` 子技能，每天某个时间段触发轻量 check-in（1-3 题），数据写入 `patients/PT-XX/reports/mind/daily-YYYY-MM-DD.md`，连续 3 天异常自动 nudge 用户跑 mind 全套。

---

### H — 女性周期与激素管理（0%，❌ OUT-OF-SCOPE）

**为什么不覆盖**：这是普通女性健康/生殖医学领域，不是癌症陪伴专项。即便用户是癌症患者，激素管理通常由妇科/内分泌科专科处理（化疗诱发停经、内分泌治疗对周期影响等是 hormonal-cancer-specific 议题，应在 cancer-buddy-pro-skill 内部版处理）。

---

### K — 复诊问题清单生成器（0%，⚠️ PARTIAL）

**用户原话**：每次看医生前，AI 根据你最近的症状记录、检查结果和上次医嘱，自动生成"这些问题你应该问"的清单。

**当前**：[`organize`](../skills/cancer-buddy-organize/SKILL.md) 的 `review_summary.md` 已经含"待人工确认"清单（虽然是给搭子核对而非给医生问的）；[`education`](../skills/cancer-buddy-education/SKILL.md) 的 `quick-reference-card.md` 是 1 页本次治疗要点（可作为问诊参考）。

**Gap**：没有专门的"基于 timeline 差异 + 上次 follow-up 节点 → 自动生成 Top 5 问题"的原子工具。

**示例（当前能拼凑的）**：

```
👤 用户："周三去复诊我该问医生什么？"

🤖 搭子（当前）：
  - 读 patients/PT-XX/reports/education/quick-reference-card.md
  - 读 patients/PT-XX/timeline.md 最近一次随访
  - 拼凑："基于你上次随访 4 周前到现在，可以问医生：
    · 这次 CT 比 4 周前如何
    · 副作用 X / Y 还要持续多久
    · 下一个治疗节点是什么时候
    · 现在的方案要不要调整"
  - 但这不是结构化原子，只是基于上下文的临时拼接

建议：cancer-buddy-visit-prep 子技能。
输入：profile.json + 最近 4 周症状记录（如果有 cancer-buddy-monitor）+ 上次复诊摘要
输出：Top 5-7 问题清单 + 每个问题的"为什么问" + 携带的检查报告 checklist
```

---

## 修订建议（roadmap）

按 cost / impact 排序，建议加入下个迭代的候选：

| 优先级 | 新子技能 | 目标 | 闭环的调研项 |
|---|---|---|---|
| P0 | `cancer-buddy-monitor` | 每日症状日志 + 周报合成 | C, E |
| P1 | `cancer-buddy-visit-prep` | 复诊前 Top-N 问题清单 | K |
| P1 | `cancer-buddy-translate`（或 organize 加 `--quick` 模式）| 单文件→人话解读，不建档 | J |
| P2 | `cancer-buddy-finance` | 方案 A vs B 总成本（含路费住宿误工） | D |

**不打算做的**：B（家庭慢病，超 scope）、H（女性周期，超 scope）。被问到时由 router 友善路由到合适的外部资源（Apple Health / 妇科）。

## 维护者注

- 本表对应 cancer-buddy-skill `main` HEAD（commit ≥ a4a1674）。
- 调研原始数据见 `references/survey-2026-05-raw.md`（如未来加入）。
- 当某项从 ⚠️/❌ 升到 ✅ 时同步更新本表 + 投票占比注释。
