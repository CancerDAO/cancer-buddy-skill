<div align="center">

# 抗癌搭子.skill

> *"医生说标准治疗用尽了，但你的路还没走完。"*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![CancerDAO](https://img.shields.io/badge/CancerDAO-Open%20Source-orange)](https://github.com/CancerDAO)

<br>

刚确诊，看不懂病理报告上写的什么？<br>
基因检测做了，不知道哪些突变能用上？<br>
医生说没有标准方案了，但你不想放弃？<br>
想找临床试验，不知道从哪里找、怎么匹配？<br>
同时在尝试好几种治疗，理不清头绪？<br>

**你需要一个搭子 — 一个懂行的、随时在的、帮你一起想办法的 AI 伙伴。**

<br>

给搭子你的病历报告、基因检测、影像结果<br>
它帮你 **理解病情、穷尽所有治疗路径、管理整个抗癌过程**<br>
从临床试验匹配到扩展准入，从检查规划到跨境医疗，一个 Skill 全搞定

[功能](#功能) · [安装](#安装) · [使用](#使用) · [效果示例](#效果示例) · [English](#english)

</div>

---

## 这个搭子能帮你做什么

一个癌症患者从确诊到治疗，需要跑多少个地方、问多少个人、查多少资料？

**抗癌搭子把这些全装进了一个 Skill 里：**

| 你遇到的问题 | 搭子怎么帮你 |
|-------------|-------------|
| 拿到报告看不懂 | 用大白话帮你解读每一项，告诉你什么重要 |
| 不知道还该做什么检查 | 按预算给你列出完整检查清单，从 ¥3000 到 ¥10 万+ |
| 想知道有哪些治疗方案 | 穷尽 8 个维度：标准方案、靶向药、免疫治疗、临床试验、前沿疗法… |
| 想找临床试验 | 同时搜 ClinicalTrials.gov + 中国临床试验注册中心，逐条评估 |
| 医生说"没办法了" | 5 条准入路径 + 跨境医疗方案 + 申请材料模板 |
| 同时尝试多种治疗 | 多线治疗仪表盘，监测日历，药物相互作用提醒 |
| 想记录自己的抗癌数据 | 帮你建一个属于自己的数据档案 |
| 看不懂医生说的话 | 生成通俗易懂的患者教育手册 |

---

## 功能

### 9 个导航阶段

```
Phase 0  病历处理     PDF/图片 → 结构化患者画像
Phase 1  认知搭子     用大白话解读诊断，列出信息缺口
Phase 2  诊断搭子     4 层检查菜单，适配你的预算
Phase 3  解读搭子     帮你读懂基因检测和各种报告
Phase 4  路径搭子     8 维度穷尽所有治疗选项
Phase 5  准入搭子     扩展准入 / 同情用药 / 跨境医疗导航
Phase 6  作战搭子     多线并行治疗管理 + 监测日历
Phase 7  数据搭子     建立你自己的 N=1 数据金库
Phase 8  教育搭子     生成患者教育手册
```

不用按顺序来。搭子会根据你说的话，自动判断你在哪个阶段。

### 设计哲学

灵感来自 GitLab 创始人 Sid Sijbrandij 的 ["Founder Mode on Cancer"](https://centuryofbio.com/p/sid) — 他在标准治疗用尽后，组建精英团队、穷尽所有诊断和治疗手段，最终实现了无可检测癌症（NED）。

他的三个核心策略被编码进了搭子的每一个阶段：

1. **极致诊断** — 做一切可能的检查，不遗漏任何信息
2. **并行不串行** — 同时探索多条路，不等一个失败再试下一个
3. **数据即力量** — 记录一切，建立你自己的数据集

> Sid 花了数百万美元和一个精英团队。搭子的目标：让每个人都能获得同等水平的信息支持。

---

## 安装

### Claude Code

```bash
# 安装到当前项目
mkdir -p .claude/skills
git clone https://github.com/CancerDAO/cancer-buddy-skill .claude/skills/cancer-buddy

# 或安装到全局（所有项目都能用）
git clone https://github.com/CancerDAO/cancer-buddy-skill ~/.claude/skills/cancer-buddy
```

### 依赖

无额外依赖。搭子基于 Claude Code 原生能力运行。

可选增强：
- `chictr-mcp-server` — 增加中国临床试验注册中心搜索能力（[安装指南](https://github.com/PancrePal-xiaoyibao/chictr-mcp-server)）

---

## 使用

在 Claude Code 中输入：

```
抗癌搭子
```

或者：

```
抗癌搭子
帮我分析一下病情
标准治疗用尽了怎么办
帮我找临床试验
这个基因报告怎么解读
```

### 你可以给搭子什么

| 输入 | 格式 |
|------|------|
| 病理报告 | PDF / 图片 / 文字描述 |
| 基因检测报告 | PDF / 图片 / 文字 |
| 影像报告（CT/MRI/PET-CT） | PDF / 图片 / 文字 |
| 血液检测 | PDF / 图片 / 文字 |
| 治疗经历 | 直接告诉搭子就行 |

---

## 效果示例

### 场景一：刚确诊，看不懂报告

```
用户        ❯ 帮我看看这个病理报告 [上传 PDF]

抗癌搭子    ❯ 我帮你看了，整理成你能看懂的版本：

              癌种：乙状结肠中分化腺癌
              分期：IV 期 — 简单说就是有远处转移了，转移到了双肺
              关键突变：KRAS G12C — 这个突变有靶向药可以打
              免疫标志物：MSS — 免疫治疗单独用效果一般

              🔴 建议尽快补充：ctDNA 检测（监测血液里的肿瘤信号）
              🟡 建议考虑做：RNA 测序（可能发现更多靶点）

              需要我帮你找这个分型的治疗方案吗？
```

### 场景二：标准治疗用尽

```
用户        ❯ 五线治疗都用过了，医生说没有标准方案了

抗癌搭子    ❯ 标准方案用尽不等于没有路了。让我帮你查一下：

              🟢 高可行性：
              1. KRAS G12C 抑制剂临床试验 — 3 个正在招募
              2. 博鳌乐城先行区可获得的境外新药

              🟡 中可行性：
              3. 个性化新抗原疫苗 — 国内 2 家机构在做
              4. 拓展性临床试验 — 需联系药企医学事务部

              🔴 探索性：
              5. 德国 Lu-177 靶向放射治疗

              要不要我帮你评估哪个最适合你的情况？
```

### 场景三：找临床试验

```
用户        ❯ 帮我找临床试验

抗癌搭子    ❯ 基于你的情况，我同时搜了 ClinicalTrials.gov 和
              中国临床试验注册中心，找到 7 个匹配的试验：

              高度匹配（2 个）：
              ✅ NCT06XXXXXX — 上海某医院，正在招募
              ✅ ChiCTR-XXXX — 北京某医院

              条件匹配（3 个）：
              ⚠️ NCT05XXXXXX — 需确认部分指标是否达标

              已排除（2 个）：
              ❌ 仅限一线患者

              需要我帮你生成联系研究中心的材料吗？
```

---

## 项目结构

```
cancer-buddy-skill/
├── SKILL.md                           # Skill 入口
└── references/                        # 按需加载的参考文档
    ├── templates.md                   #   输出模板
    ├── vmtb-protocol.md               #   专业会诊协议
    ├── databases.md                   #   医药数据库查询参考
    ├── trial-matching.md              #   临床试验匹配协议
    ├── pathway-exploration.md         #   治疗路径探索策略
    ├── access-pathways.md             #   准入路径 + 跨境医疗
    ├── diagnostics.md                 #   诊断菜单（中国机构 + 费用）
    ├── data-vault.md                  #   数据金库 Schema
    └── sid-framework.md               #   设计哲学参考
```

---

## 注意事项

- **搭子不是医生**。所有输出都是信息整理和参考，不构成医疗建议。请务必与你的医疗团队确认后再做决定。
- **数据隐私**：搭子在本地运行，你的数据不会被上传到任何第三方服务。
- **信息时效**：药物审批、临床试验招募状态会变化，请核实时效。
- **报告质量影响结果**：给搭子的资料越完整，整理的信息越准确。

---

## 贡献

欢迎贡献！特别是：

- 特定癌种的治疗路径补充
- 中国各地医院 / 检测机构的信息更新
- 多语言支持
- Bug 修复和体验改善

请提 [Issue](https://github.com/CancerDAO/cancer-buddy-skill/issues) 或 PR。

---

<a id="english"></a>

## English

**Cancer Buddy (抗癌搭子)** is a Claude Code Skill that gives every cancer patient access to the same level of information navigation that previously required millions of dollars and a full-time expert team.

It covers: report interpretation, clinical trial matching (ClinicalTrials.gov + ChiCTR), treatment pathway exploration, expanded access navigation, parallel treatment management, and patient data vault — all in one Skill.

Inspired by Sid Sijbrandij's ["Founder Mode on Cancer"](https://centuryofbio.com/p/sid) approach.

```bash
git clone https://github.com/CancerDAO/cancer-buddy-skill ~/.claude/skills/cancer-buddy
```

Then say `抗癌搭子` or `cancer buddy` in Claude Code.

---

## 谁在做这个

[CancerDAO](https://github.com/CancerDAO) — 用 AI + 开源的方式，让每个人都能获得个性化抗癌信息支持。

---

<div align="center">

MIT License © [CancerDAO](https://github.com/CancerDAO)

**每一个 Star 都是对"不放弃"的支持。**

</div>
