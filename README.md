# 抗癌搭子（Cancer Buddy）

面向癌症患者与获授权照护者的非临床导航 skill。它帮助整理病历、理解稳定概念、实时查证并解释权威指南/标准治疗的一般情况（带来源）、准备就诊问题、查找公开资源和制作来源可追溯的资料包；不替代医生，也不对你个人作诊断、分期、ECOG、疗效、进展、预后或治疗决策。

## 能做什么

| 模块 | 用途 | 临床边界 |
|---|---|---|
| `cancer-buddy-organize` | 把 PDF/图片/文档整理为带来源的结构化档案 | 不重算分期、不推断疗效/ECOG/治疗线；缺失只表示档案中没有该文件 |
| `cancer-buddy-visit-prep` | 医生速览、带什么、问什么 | questions only，不回答临床问题 |
| `cancer-buddy-education` | 患者教育与术语解释 | 指南/标签/批准/预后数字须在回答时核验现行一手来源，失败关闭 |
| `cancer-buddy-nutrition` | 症状导向饮食教育、药食/补充剂核验 | 不按癌种或治疗阶段自动开菜单/营养处方 |
| `cancer-buddy-caregiver` | 陪诊、家庭分工、儿童沟通、照护负担支持 | 亲属关系不自动授予病历访问权 |
| `cancer-buddy-disclosure` | 知情偏好与家庭沟通脚本 | 模型不判定能力，不协助长期欺骗 |
| `cancer-buddy-find-care` | 查官方医院/医生/服务/试验站点 | 输出不排序资源清单，不评价质量或试验资格 |
| `cancer-buddy-case-precedent` | 检索病例报告 | 展示全部结局和差异，不算相似度、不生成治疗方向或预后 |
| `cancer-buddy-second-opinion` | 来源型摘要、索引、转诊问题和发送清单 | 联系/邮寄要求每次从目标机构实时核验，skill 不自动外发 |
| `cancer-buddy-vault` | 本地清单、授权、导出和审计流程 | 依赖宿主鉴权；`patient_code` 不是密码或授权凭据 |
| `cancer-buddy-charts` | 把检验、治疗、分子与资料数据画成可打印可转发的静态图表 | 只呈现源报告已有的数值；不解读趋势含义、不判断疗效或病情；无数据不画 |

另含总入口 `cancer-buddy` 与联网底层 `web-access`。

## 临床安全原则

- 保留源临床字符串。药名、基因、变异、TNM、数值、单位和限定词不能被无痕改写；经验证的规范化和患者语言译文只能作为带标签的附加层。
- 病历层级分开：`source_reported`、`patient_reported`、`caregiver_reported`、`system_normalized`。患者确认只能确认自己的陈述被正确记录，不能覆盖医生来源或解决临床冲突。
- 不从影像描述、肿瘤标志物或症状推导 RECIST、进展或疗效；不从功能描述推 ECOG；不自动计算治疗线。
- 指南、药品标签、相互作用、试验、机构、法律和预后数字必须在使用时核验一手来源。无法核验时明确停止，不降级为模型记忆。
- 实验室结果保留该次报告自己的单位、参考范围、report flag 和 critical flag；程序不比较通用阈值、不生成“严重度”。
- 自伤/自杀风险由宿主 LLM 的平台级安全能力处理，本 skill 不另建可能冲突的路径。

临床治理总合同见 [`references/clinical-content-governance.md`](references/clinical-content-governance.md)。

## 安装

```bash
# 全局安装全部 skill
npx skills add CancerDAO/cancer-buddy-skill -g --all

# 或安装到当前项目
npx skills add CancerDAO/cancer-buddy-skill --all
```

详细说明见 [INSTALL.md](INSTALL.md)。本仓库不会在运行中自动安装或执行另一个临床 skill。若用户另行选择临床试验匹配工具，仍需研究中心依据最新方案和完整病历逐条预筛。

## 使用示例

```text
抗癌搭子，帮我整理这些报告
明天复诊，帮我把该问医生的问题列出来
请解释这份病理报告里的术语，并保留原文
帮我查杭州和上海哪些机构官网写明提供 MTB；不要排名
请检索这个罕见病理的病例报告，并把死亡/无效/严重不良事件也完整列出
```

## 数据与权限

默认患者目录：

```text
$CANCER_BUDDY_PATIENTS_DIR
→ $VMTB_PATIENT_DATA_ROOT
→ $HOME/CancerDAO/patients
```

- `patient_code` 由随机字节生成，只是存储定位符。
- 上传原件保存在受控 `raw/`；派生 sidecar 和交付表面做文本遮蔽与最小化，但仍可能被重识别，不能视为匿名。
- 患者、照护者和家属的访问由宿主鉴权与明确、限用途、可撤销授权决定；亲属关系或知道目录名不代表有权限。
- 分享/导出前必须确认接收方、范围、目的和期限，并写审计记录。

## 测试

```bash
bash tests/eval/run.sh
for test in tests/unit/*.sh tests/integration/*.sh; do bash "$test"; done
bash skills/cancer-buddy-organize/tests/conformance/run_conformance.sh   # organize 契约 conformance（三道确定性门）
```

静态测试检查安全合同和结构；`tests/eval/scenarios/` 是需要模型/人工评审的行为用例。

organize 契约自 `CONTRACT_VERSION` 2.2.0 起附带三道**确定性验收门**（`skills/cancer-buddy-organize/scripts/gates/`，stdlib-only 零 LLM）：G1 文件名↔sidecar 报告类型一致性、G2 对账候选值-源绑定、G3 同检验判重。任何宿主（平台/CLI）集成 organize 时必须在契约规定的时点执行这三道门，并保持 conformance suite 全绿——门与用例的由来见 `organize-contract.md` §Executable gates。

## 免责声明

本工具用于资料组织、教育和沟通准备，不提供医疗诊断或治疗建议。急性危险症状请按主诊团队指示联系医疗机构或当地急诊。

License: [MIT](LICENSE). Project: [CancerDAO](https://github.com/CancerDAO).
