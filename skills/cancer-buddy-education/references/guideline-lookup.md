# 指南实时检索（guideline live lookup）— 条件式教育的 (b) 子路径

条件式教育有两种子问法（见 SKILL.md `When to use` + `../../cancer-buddy/SKILL.md` 「条件式教育」）：

- **(a) 严重度/预后条件图**（"严不严重 / 能治好吗 / 是不是晚期 / 还能活多久 / 会不会复发"）＝疾病生物学级的一般规律 → **不走本文件**，用模型通识 + `cancer-type-modules.md` 框架即可。
- **(b) 指南级断言**（"NCCN/CSCO/ESMO 指南建议 / 标准治疗是什么 / 一线二线是什么方案 / 我这类一般用什么药 / 最新获批"）＝**版本敏感的外部目录事实**，落 `../../../references/safety-guardrails.md` no-silent-snapshot 红线 → **走本文件：live-first 实时联网检索**。联网拿到 → 逐字接地 + 编号引用；联网**不可达** → 可优雅降级到**显式标注**的模型知识兜底（见下方「优雅降级」），但**绝不把记忆冒充成已核实来源、绝不挂编号角标**。

边界模糊时**倾向 (b)**。

---

## 何时触发（LLM 意图判定，不写 keyword 硬表）

在条件式教育分支里先做一步意图判定：问法**点名指南/学会/标准治疗/具体方案线数/证据级别/获批状态**，或问"我这类（癌种+分子型）一般用什么方案" → 判为 (b)，走下面的检索。否则 (a)。

字段不全时**不要让 subagent 瞎跑**：先读 `patients/<pid>/profile.json` 拿 `primary_site` / `summary.stage` / `molecular.json` 的 drivers；缺关键字段（如癌种/分子型）先当面问用户或先去 organize，别让 subagent 替你猜。

---

## 源面优先级（licensing —— 硬约束）

NCCN 全文是**登录墙 + 版权保护**，患者产品里逐字复制其推荐表 / category-of-evidence 是**授权灰区**。故：

| 优先 | 源 | 性质 | 用法 |
|---|---|---|---|
| P0 | **NCI PDQ**（cancer.gov） | 美国政府公开、可自由引用 | 患者版/医生版均可逐字引 |
| P0 | **CSCO 指南**（中文用户最对口） | 学会指南 | 引要点 + 版本号 |
| P1 | **ESMO** guidelines | 公开 | 可引 |
| P1 | **PubMed / Europe PMC** 一级研究（注册试验、NEJM/Lancet/JCO 等） | 公开摘要 | 逐字接地 pivotal 证据 |
| P2 | **NCCN** | 版权 / 登录墙 | **只"指向 + 引其 category 级别"，不复制表格全文、也不逐句改写其推荐**（"润色转述"既不干净规避版权、又丢掉逐字接地的准确性锚）；能用 PDQ/CSCO 覆盖就不碰 NCCN 原文 |

---

## 派发（web-access 子 agent，镜像 find-care）

每条检索路线一个 subagent，用 Agent tool 启动。控制在 1–3 个（癌种指南 / pivotal 证据 / 中国可及性），避免过度联网。

prompt 模板：

```
任务：查 <癌种 + 分期 + 分子型> 的指南级标准治疗与循证方案。
优先源顺序：NCI PDQ → CSCO → ESMO → PubMed/EPMC 一级研究。NCCN 只指向 + 引 category，不复制其表格全文。

约束：
- **必须加载 web-access skill 并遵循指引**（登录墙/反爬按其指引，CDP 直连用户已登录 Chrome）
- **禁 LLM 凭记忆合成**：每条方案/线数/证据级别必须有真实抓取到的 URL 或 PMID + 可逐字回溯的原文片段；抽不到就标"未取到"，不要编
- PMID 类过撤稿检查（`"Retracted Publication"[pt]` / EPMC 撤稿标记）
- 临床实体（药名/基因/变异/TNM/数值+单位/证据级别）逐字保留，不翻译不改写
- 单个 subagent 最多 5 分钟，超时返回"未完成 + 已采集到的部分"

输出 JSON（写到 patients/<pid>/reports/education/guideline/<slug>/raw/<subagent-name>.json）：
{
  "source_type": "pdq|csco|esmo|primary_study|nccn_pointer",
  "source_url": "...",
  "pmid": "…（文献类才有）",
  "fetched_at": "ISO8601",
  "guideline_version": "…（如 CSCO 2025 / PDQ updated 2026-xx）",
  "items": [
    {"regimen_or_claim": "...", "line_or_setting": "...", "evidence_level": "…（如有）", "evidence_quote": "原文片段", "molecular_context": "..."}
  ],
  "retraction_checked": true,
  "notes": "未覆盖的子目标 / 网络问题"
}
```

网络不可达或某源无法确认 → 该条标 `需现场核实`。**subagent 层永不编造**（抽不到就返回"未取到"）；要不要给模型知识兜底是**主 agent 呈现层**的决定，且只能走下方「优雅降级」的显式标注——**绝不静默把记忆 / 静态模块冒充成已核实来源**。

---

## 呈现（回到条件式教育的形态）

subagent 汇总后，主 agent 按条件式教育的既有形态出，**不变成个案判决**：

1. 先接情绪 + "这个'你该不该换/该上什么'的结论要你主诊医生定"。
2. **一般性条件化**呈现查到的指南内容："对 <你这类情况>，指南一般把 X 列为 <line/setting> 的方案<sup>[n]</sup>……（这是对'这一类情况'的一般说法，不是对你个案的判决。）"
3. 每条指南断言挂**联网锚编号引用**（见 `../../cancer-buddy/SKILL.md` 「来源引用」——URL 或 PMID，档案锚与联网锚共用同一编号序列）。
4. 带去问医生的具体问题 + "你具体落在哪一支、要不要换，得你主诊医生结合完整情况定"。
5. 强制 footer（见 SKILL.md Safety）。

**locale**：所有患者可见脚手架/叙事按 `profile.json.locale`；临床实体 + URL + PMID + 证据级别逐字保留。

---

## 优雅降级（联网不可达时的兜底 —— live-first 的唯一例外）

live-first 是默认。只有当**联网确实不可达 / 源无法确认**时才允许兜底，目的是"不硬甩墙"，**不是"放开合成"**：

- **subagent 层不变**：仍禁编造，抽不到就返回"未取到 / 需现场核实"。
- **主 agent 兜底（唯一允许处）**：可以给一段模型知识的**一般性**说明，但必须同时满足——
  1. **显式打标**：开头标 `⚠️ 未经实时核实 · 基于模型知识（可能滞后于最新指南）`；
  2. **不挂编号角标**（角标 = 已核实来源的专属标记，记忆不配）；
  3. **催核实**：结尾说明"这段没连上实时指南（原因：网络 / 源不可达），请以主诊医生 + 官方指南为准"；
  4. 仍是**一般条件图**，不是个案换线判决。
- 一句话：**容忍降级，绝不把记忆冒充成已核实来源。**

---

## 安全门（本子路径，全过才算完成）

- **G-NO-SYNTH**：**编号角标**只能挂真实抓取、可逐字回溯的源；模型记忆只能作**显式标注**的兜底（见「优雅降级」）——绝不挂角标、绝不冒充已核实。
- **G-NO-VERDICT**：输出是"对你这类情况一般…"，绝不出个人分期/预后数字/换线判决。
- **G-LICENSE**：NCCN 不复制表格全文，主引 PDQ/CSCO。
- **G-LIVE-OR-HONEST**：联网不可达 → "需现场核实"，不静默降级。
- **G-CITE**：每条指南断言带联网锚编号引用；撤稿源不引。
- **G-DISCLOSURE**：`disclosure_state=suppressed` + role=patient 时按 `../../../references/disclosure-behavior.md` 让位。
- **G-NO-OVERFETCH**：纯 (a) 严重度/预后问法**不触发**联网。
