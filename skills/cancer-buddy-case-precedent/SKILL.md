---
name: cancer-buddy-case-precedent
description: "从患者已整理的病历档案出发，去 PubMed / Europe PMC 检索 **publication type = Case Reports** 的相似真实病例，逐病例返回「这位真实患者试过什么治疗、发生了什么」，作为**去研究和找医生讨论的线索**。**不是预后预测，不是治疗建议。** 个案报告是最弱证据且被发表偏倚系统性拉向乐观——每条结果强制披露偏倚、显式标 N、绝不聚合成生存率、逐维展示相似/分歧、PMID 逐字接地、过撤稿检查。输入：profile.json（癌种/分子/治疗线）+ 一个"想看像我这样的人怎么治"的诉求。输出：一份相似先例清单（PRECEDENTS.md），可打印分享、可对话追问细化。Triggers on: 相似病例, 像我这样的患者, 别人怎么治的, 有没有和我一样的, 同样情况的人怎么治, case report, 病例报告, 真实病例, 先例, precedent, 类似病例, 别人的治疗路径."
---

# cancer-buddy-case-precedent

帮你找有文献记录的**相似真实病例**，看别人试过什么、发生了什么——作为线索，不替你判断结局。

「有没有和我情况像的人？别人是怎么治的、后来怎么样了？」是患者反复问的问题。这个 skill 用患者自己的病历档案组装相似度画像，去 PubMed / Europe PMC 检索**真实的个案报告（case report）**，逐病例结构化呈现治疗路径与结局，全程带 PMID 可核验。

## When to use

触发场景（用户说类似这些话）：
- "有没有和我一样 KRAS G12C 的结直肠癌病人，别人怎么治的？"
- "像我这种三线进展的胰腺癌，文献里有类似的人吗？后来怎么样了？"
- "我这个罕见的病理类型，别人都用了什么方案？"
- "网上说有人用 XX 药活了很久，是真的吗？有没有真实病例？"

## What this skill is NOT — ⚠️ 本 skill 成败全在这里

**这不是预后预测，不是治疗建议，不是"像你的人这样治就对了"。**

- ❌ **不预测你本人的预后 / 生存期**——个案报告因罕见或疗效突出才被发表，系统性偏乐观；它们不是你的预后。
- ❌ **不给治疗方案推荐 / 不建议换线 / 不判断该不该用某药**——那是主诊医生 + `cancer-buddy-pro-skill`（内部版）/ MTB。
- ❌ **绝不把多个个案聚合成生存率、有效率或任何"率"**——N=3 的轶事推不出统计结论（见 Safety → G-NO-AGGREGATE）。
- ❌ 不做前瞻性临床试验匹配——找在招试验走 [`clinical-trial-matching`](https://github.com/CancerDAO/clinical-trial-matching-skill)；找能做 MTB 的医院走 `cancer-buddy-find-care`。
- ❌ 不冒充真实患者社区（PatientsLikeMe 式）——文献个案是过渡替身，叙事上不得暗示为真实队列。

我们做的是：**把文献里和你相似的真实病例找出来、诚实地摆给你和你的医生看。**

## Locale (i18n)

读共享 `../../references/i18n.md`。流程开始时：

1. caller / host 传入 `locale` → 直接用并写回 `profile.json.locale`。
2. 否则读 `patients/<patient_code>/profile.json` 的 `locale`，有值直接复用，**不重新检测**。
3. 无 profile / locale 为 null → 从当前对话语言检测 BCP-47，写回。
4. 用户显式换语言 → 更新 `profile.json.locale` 并照办。

**临床实体逐字禁译（P0）**：药名 / 基因 / 变异 / TNM / 分期 / 数值+单位 / biomarker / PMID / 期刊名一律 verbatim（见 `../../references/safety-guardrails.md` → 临床实体禁译）。只本地化脚手架（section 标题、字段标签、偏倚披露文案、匹配/分歧档位词、免责声明、日期）。派发 subagent 时在 prompt 写明 "Output all patient-visible scaffold prose in `<locale>`; keep clinical entities + PMIDs verbatim."

## Preflight

### Role check
- `role=patient` / `role=caregiver`：正常工作。
- `role=family`（远亲/朋友）：refuse + 引导回主照护者（按 locale 出同义文案）：`找相似病例涉及具体病情，需要患者本人或主照护者来推进。我可以把找到的信息整理给 Ta 看。`

### 危机与披露前置
- 会话中出现自杀意念 → 立即走 `cancer-buddy` 危机路径（凌驾一切），热线以 `../cancer-buddy-mind/references/crisis-resources.md` 为准。
- `profile.json.disclosure_state == "suppressed"` 且 `role=patient` → 见下方 Disclosure 行为。

### Profile completeness（病历侧从 organize 产出读，按档案读取协议）
| 字段 | 来源文件 | 必需？ | 用途 |
|---|---|---|---|
| `summary.primary` | `profile.json` | 必需 | 相似度第一维；无则先去 `organize` |
| `summary.histology` / `diagnosis.histology` | `profile.json` / `patient_summary.json` | 推荐 | 组织学维 |
| `summary.stage` / `diagnosis.stage` | `profile.json` / `patient_summary.json` | 推荐 | 分期维 |
| drivers（基因/变异） | `molecular.json#variants[]` | 强推荐 | 驱动维；无则相似度只能靠临床维 |
| 治疗线 | `treatment_lines.json#lines[]` | 推荐 | 治疗线维（"同样几线进展"） |
| 关键合并症 | `comorbidities.json#conditions[]` | 可选 | 合并症维 |

**读档遵 `cancer-buddy` 档案读取协议**：`profile.json → readiness.json → INDEX.md → 定向 JSON → source_refs sidecar`；**选择性读、不通读**；**绝不读 `raw/` 与 `99_无关文件/`**。必需字段缺失时回头让用户补齐或先去 `organize`，不让 subagent 瞎跑。

## Core workflow

### Step 1 — Build similarity profile → QUERY.md

把患者档案组装成一个结构化相似度画像，写到 `patients/<patient_code>/reports/case-precedent/<slug>/QUERY.md`：

```yaml
similarity_profile:
  primary:        非小细胞肺癌            # summary.primary (verbatim)
  histology:      腺癌                    # diagnosis.histology
  stage:          IV                      # diagnosis.stage
  key_drivers:    [EGFR L858R, T790M]     # molecular.json#variants[] (verbatim HGVS/gene)
  treatment_lines:                        # treatment_lines.json#lines[]
    - {line: 1, regimen: Osimertinib, best_response: PD}
  key_comorbidities: []                   # comorbidities.json#conditions[]
focus: 三线进展后还有什么真实病例用过的方案   # 用户这句诉求 (narrative, 按 locale)
patient_profile_ref: patients/PT-XXXX/profile.json
```

YAML 键语言无关；值里临床实体逐字，`focus` 叙事按 locale。缺的维度当面问用户，**别让 subagent 猜**。

### Step 2 — Retrieve case reports（派 subagent 加载 web-access）

按 `similarity_profile` 组装检索式，派 1–N 个 subagent（每个用 Agent tool 启动，**必须加载 `web-access` skill**）直连公共 API 检索 **只要 case report**。检索源、pubtype 过滤语法、去重与撤稿检查见 [`references/retrieval-sources.md`](references/retrieval-sources.md)。

- PubMed E-utilities：`esearch` + `"Case Reports"[Publication Type]` + 癌种/组织学/驱动基因/线数关键词 → `efetch` 取详情。
- Europe PMC REST：`PUB_TYPE:"Case Reports"` 同义检索，优先取 OA 全文。
- **去重 + 显式计数（不许断言"无重复"）**：按 PMID → DOI → 归一化标题去重，**必须真算两源交集**并把删掉的重叠**显式列出**（如"PubMed 20 + EPMC 14，去重 6 条重叠 → N=28 唯一"）。EPMC 本身镜像 PubMed，两源**零重叠是异常信号**——若出现，说明查询发散或 dedup 没真跑，需复核，**不得直接写"均无重复"**。N 是偏倚披露的头号数字，必须是真实的 post-dedup 唯一数。
- **撤稿检查**（PubMed `"Retracted Publication"[pt]` 关联 / EPMC 标记）在主 agent 汇总时做；撤稿/存疑条目剔除或明确标注。
- **live lookup，不用陈旧快照**（`safety-guardrails.md` → no-silent-snapshot）；网络不可达报错标"需现场核实"，不 LLM 编造个案。
- 返回 0 条 → 诚实报"未找到相似个案"，不编。

**时间预算与规模上限（患者向，必须有界）**：
- 每个检索 subagent **硬时限 ≤ 5 分钟**（照 find-care），超时返回"未完成 + 已采集部分"，不无限等。
- OA 全文抓取**只对去重后按相似度排序的 top ≤15 篇**做，其余用摘要，避免逐篇下全文拖成十几分钟。
- 逐病例展开卡片**上限 10 例**；其余列入"检索到但未展开"表。
- 总目标 wall-time 控制在数分钟量级；若某源明显拖尾，先用已回的那一源出结果并标注"另一源仍在检索"。

subagent 输出 JSON 写到 `.../raw/<subagent-name>.json`（schema 见 retrieval-sources.md）。

### Step 3 — Per-case structured extraction（逐病例抽治疗路径 + 结局）

对每篇命中的个案，逐病例结构化抽取（优先 OA 全文，无则摘要），schema 见 [`references/case-extraction-schema.md`](references/case-extraction-schema.md)：该病例的 patient descriptors、逐线治疗（方案/意图）、best response、随访时长、结局状态。

- **逐字接地**：每个抽取字段带 PMID + 逐字来源引文（子串可回溯）。**禁 LLM 合成结局**（`safety-guardrails.md`；反幻觉）。
- 抽不到的字段标 `未报告`，不猜。

### Step 4 — Per-axis similarity（6 维 match/mismatch，透明呈现）

对每个病例，用 sub-prompt LLM 逐维判 match / partial / mismatch / unknown（**不写硬编码打分表**），维度与规则见 [`references/similarity-axes.md`](references/similarity-axes.md)：`primary / histology / stage / key_driver / treatment_line / key_comorbidity`，每维附一句理由。

- **分歧维必须显式列出**（不只列相似）。
- 可按综合相似度排序，但**不把总分作为主视觉**（避免"最像=最该学"误读）；每条都展示 mismatch。

### Step 5 — Write PRECEDENTS.md + 对话追问

写到 `patients/<patient_code>/reports/case-precedent/<slug>/PRECEDENTS.md`，按 [`references/output-template.md`](references/output-template.md)。脚手架按 locale，临床实体 + PMID 逐字。

**每份清单强制包含**（见 Safety 的 P0 门）：
- **顶部偏倚披露横条** + **显式 N=<命中数>**（文案模板见 [`references/bias-disclosure.md`](references/bias-disclosure.md)）。
- 每条：相似度画像逐维对照（含分歧）+ 逐线治疗路径 + 结局 + 随访时长 + PMID 链接 + 逐字引文。
- **审计 footer**（`safety-guardrails.md` → Audit trail）：生成时间、skill 名+版本、profile hash 前 8 位、查询的数据库。
- 末尾 canonical 免责（按 locale 渲染 `不替代主诊医生的判断` 之义）：

```
> 这些是有文献记录的真实病例，不是对你结局的预测，也不是治疗建议。个案报告往往因罕见或疗效突出才被发表，系统性偏乐观、不代表总体。请把这份清单带给你的主诊医生一起看。
```

**对话追问细化**：用户说"只看有脑转的 / 同样二线进展的 / 只看用了 XX 药的" → 在已检索结果上按维度过滤/重排；若需新维度则二次检索（同样走 Step 2 的 pubtype 过滤 + 撤稿检查）。可再次沉淀为更新版清单。

## Role behavior
- **patient**：第二人称"你"，画像对照以本人为参照。
- **caregiver**：第二人称"你"，任务理解为帮家人；输出可分享给患者/医生。
- **family**：refuse（见 Preflight）。

## Disclosure 行为
`profile.json.disclosure_state == "suppressed"` 且 `role=patient`：正常执行检索，但 PRECEDENTS.md 里**避免**渲染"晚期/IV/进展后/生存期"等可能加重情绪的表述，用临床中性语；结局字段照实但克制呈现。详见 `../../references/disclosure-behavior.md`。

## Safety — P0 安全门（每条输出都过，违反即 bug）

- **G-BIAS**：每条结果 + 清单顶部强制发表/幸存者偏倚披露文案（`bias-disclosure.md`）。
- **G-N**：显式标 N；N 小不得暗示任何"率"或"大多数人"。
- **G-NO-AGGREGATE**：**绝不**计算/输出生存率、有效率、缓解率、预后百分比或"中位生存"——个案不可聚合。
- **G-SIMILARITY-TRANSPARENCY**：6 维 match/mismatch，**分歧维必列**。
- **G-GROUNDING**：每条结论挂真实 PMID + 逐字引文；过 Retraction Watch / `"Retracted Publication"[pt]`；抽不到标"未报告"，不猜。
- **G-NO-ADVICE / NO-PROGNOSIS**：无治疗推荐、无换线建议、无本人预后预测；用"匹配理由"不用"推荐理由"；决策权归患者+医生（`safety-guardrails.md` → Never say / Scoring and ranking）。
- **G-TIER**：明确标注为**最弱证据（个案报告，证据层 C→D）**，低于试验、低于指南（`safety-guardrails.md` → Evidence grading）。
- **G-LIVE**：live lookup，不用陈旧快照，网络不可达标"需现场核实"，不静默降级、不 LLM 合成个案。
- 其它：临床实体逐字禁译（P0）；绝不读 `raw/`/`99_`；危机/披露规则照 `cancer-buddy` + `safety-guardrails.md`。

## Output

```
patients/<patient_code>/reports/case-precedent/<slug>/
  ├── QUERY.md          # Step 1 相似度画像
  ├── PRECEDENTS.md     # 最终给用户的相似先例清单
  └── raw/
      ├── subagent-A.json   # Step 2 检索原始命中
      └── ...
```

`<slug>` 形如 `nsclc-egfr-t790m-3l-2026-07`，便于翻历史。

## References
- [retrieval-sources.md](references/retrieval-sources.md) — PubMed E-utilities + Europe PMC REST 端点、Case Reports pubtype 过滤语法、去重/撤稿检查、subagent 输出 schema
- [case-extraction-schema.md](references/case-extraction-schema.md) — 逐病例结构化抽取 schema（治疗路径 + 结局，逐字接地）
- [similarity-axes.md](references/similarity-axes.md) — 6 维相似度规则 + 分歧透明
- [bias-disclosure.md](references/bias-disclosure.md) — 强制偏倚披露文案模板 + no-aggregate 规则
- [output-template.md](references/output-template.md) — PRECEDENTS.md 模板（偏倚横条 + N + 逐条 + 审计 footer + 免责）
- 共用：`../../references/roles.md`, `../../references/safety-guardrails.md`, `../../references/disclosure-behavior.md`, `../../references/i18n.md`, `../../references/patient-profile-schema.md`
- 联网底层依赖：`../web-access/SKILL.md`（subagent 必须加载）
