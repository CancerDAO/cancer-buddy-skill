# 抗癌搭子 (cancer-buddy)

你的 AI 抗癌伙伴 —— Claude Code 插件。

## 这是什么

抗癌搭子是一个 Claude Code 插件，包含 1 个元技能 + 8 个专业子技能，覆盖癌症就医全旅程：病历整理、诊断与治疗路径探索、轻量版分子肿瘤委员会 (MTB)、患者视角的临床试验匹配、扩展准入导航、多线治疗管理、N=1 数据金库、患者教育手册。

和临床医生朝向的 [vmtb-skill](https://github.com/zwbao/vmtb-skill) 配套：抗癌搭子给患者看，vmtb-skill 给医生看。两个插件共享同一个 `patients/<patient_code>/` 病例目录，所以在搭子里整理过的病历可以直接被 vmtb-skill 的完整 MTB 委员会读取。

## 快速开始

1. 安装 Claude Code 插件：
   ```
   # 全局安装（推荐）
   cd ~/.claude/plugins && git clone https://github.com/CancerDAO/cancer-buddy-skill

   # 或项目级安装
   cd <your-project>/.claude/plugins && git clone https://github.com/CancerDAO/cancer-buddy-skill
   ```

2. 重启 Claude Code。

3. 和 Claude 说 "抗癌搭子" 或 "帮我分析病情"，搭子会接管并路由到合适的子技能。

## 子技能一览

| 子技能 | 作用 | 何时触发 |
|---|---|---|
| `cancer-buddy-organize` | 整理病历（PDF/图/docx）成结构化数据 | 我有一堆报告 |
| `cancer-buddy-explore` | 4 档诊断菜单 + 8 维治疗路径穷举 | 还能做什么检查 |
| `cancer-buddy-mtb-lite` | 单 agent 轻量版分子肿瘤委员会 | 分子肿瘤委员会 / MTB |
| `cancer-buddy-trial-match` | 患者视角的临床试验匹配 | 帮我找临床试验 |
| `cancer-buddy-access` | 扩展准入 / 同情用药 / 跨境治疗路径 | 博鳌 / 同情用药 |
| `cancer-buddy-manage` | 多线治疗管理、监测、RECIST 评估 | 多线治疗 |
| `cancer-buddy-vault` | N=1 个人健康数据金库 | 数据保险箱 |
| `cancer-buddy-education` | 患者教育手册（Markdown + Mermaid） | 宣教手册 |

## 和 vmtb-skill 的配合

想要完整版 MTB（病理/基因/临床试验三位专家并行讨论 + 5 维校验）？额外安装 vmtb-skill：
```
cd ~/.claude/plugins && git clone https://github.com/zwbao/vmtb-skill
```
装上之后，搭子在 MTB 步骤会问你要精简版还是深入版。

Tested against vmtb-skill >= 4.0.0-beta.6.

## 数据在哪里

所有病历和报告都写在本地 `patients/<patient_code>/` 目录。`patient_code` 由 `cb-organizer` 在首次整理时自动生成（基于输入路径与修改时间的哈希），形如 `PT-17CE02BC33`，与 vmtb-skill 共享同一套命名。完整 schema 见 [references/patient-profile-schema.md](references/patient-profile-schema.md)。

默认根目录依次回退：`$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`。想改用别的位置：
```
export CANCER_BUDDY_PATIENTS_DIR=/path/to/your/patients
```

## 安全声明

- 本工具提供信息导航，不替代主诊医生。所有治疗决策必须与医生确认。
- 所有数据默认本地存储；调用 Claude API 时会把相关病历内容传给 Anthropic（遵循其隐私条款）。
- 想更严格的本地隔离？用 vault 子技能设定数据分享等级。

## 贡献

issues、PRs 都欢迎。见 [CONTRIBUTING.md]（如果存在）。

## 协议

MIT License. 详见 [LICENSE](LICENSE).
