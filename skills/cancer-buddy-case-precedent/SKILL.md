---
name: cancer-buddy-case-precedent
description: "从患者已整理的病历档案出发，去 PubMed / Europe PMC 检索 **publication type = Case Reports** 的相似真实病例，逐病例返回「这位真实患者试过什么治疗、发生了什么」，作为**去研究和找医生讨论的线索**。**不是预后预测，不是治疗建议。** 个案报告是最弱证据且被发表偏倚系统性拉向乐观——每条结果强制披露偏倚、显式标 N、绝不聚合成生存率、逐维展示相似/分歧、PMID 逐字接地、过撤稿检查。输入：profile.json（癌种/分子/治疗线）+ 一个"想看像我这样的人怎么治"的诉求。输出：一份相似先例清单（PRECEDENTS.md），可打印分享、可对话追问细化。Triggers on: 相似病例, 像我这样的患者, 别人怎么治的, 有没有和我一样的, 同样情况的人怎么治, case report, 病例报告, 真实病例, 先例, precedent, 类似病例, 别人的治疗路径. **软触发（弱信号，只触发『提一句 + 问意图』，绝不自动检索）**：还有没有别的办法, 是不是只有我这样, 别人遇到这种情况怎么办, 换了方案不知道还有什么路, 别人是不是也这样, 是不是没别的路了. 这类是『找别人/找方向』形状的弱信号——按 Step 0 先接住、只问一句意图（求连接还是求方向），不砌文献墙、不直接跑检索；**纯绝望/自伤语（不想活了/撑不下去了）不归本 skill；搭子不做心理危机干预，简短接住并建议寻求精神卫生专业人员或当地急救/急诊**。"
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

### 披露前置
- 会话中出现情绪困扰或自伤念头 → 本 skill 不做检索、不做心理危机干预；简短接住，并建议寻求精神卫生专业人员或当地急救/急诊。
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

### Step 0 — 先接住 + 厘清意图（先做，别急着检索）

「有没有和我一样的人」表面是信息问题，底下常是**求连接 / 求希望 / 求下一步**。别一上来就甩文献。

1. **接住一句**（按 locale，共情不廉价）：先认这句话背后的情绪——"想找和你（或你家人）情况像的人、看看别人怎么走过来的，这个念头我懂"。
2. **厘清意图**（问一句再决定要不要检索）：
   - 想看 **别人试过哪些治疗方向**（好带去问医生）→ 继续 Step 1（本 skill 主线）。
   - 想知道 **有没有人情况像、后来还不错 / 只是需要有人听**（求希望 / 求连接）→ **文献个案给不了这个**（偏倚的小 N、不是能对话的人）。诚实说明这一点，把话题交回情绪本身、先陪着说说；真正的连接得找真实的人或专业心理支持，不在文献里。
3. 只有意图落在"看别人试过什么方案"时才进入检索。**别用一份 25 分钟的综述去回答一个求安慰的问题。**

**软信号入口（弱触发 / 主动提及 —— 用户没显式点名"找病例"）**：当用户是被 description 的软触发词带进来的（"还有没有别的办法""是不是只有我这样""换了方案不知道往哪走"），或从 `organize` 的整理结尾顺势路由过来时，**先给一句共情 + 一个二选一问句，不直接检索**：

> "<接住这句情绪的一句>。我想到一件也许帮得上的事：文献里记录过一些和你**情况有部分像**的真实病例，别人当时试过哪些方向、拿去问医生的。它给不了『谁比谁顺』那种安慰（那种连接得找真实的人，我也可以陪你聊心里这块）；但如果你现在更想要的是『下一步还有哪些牌能打』，我可以去翻一翻。你现在更想要哪一个——**有人听你说说**，还是**看看别人试过的路子**？"

- 选"有人听" / 情绪信号更强 → **不进检索**；先陪着说说，需要时建议寻求专业心理支持。
- 选"看路子" → 进 Step 1 检索。
- **主动提及 ask-once（防打扰）**：同一会话里这句主动邀请**最多提一次**；用户忽略/婉拒即不再复提（沿用与 organize 补料一致的"提过就沉默一段"纪律，别反复推销检索）。真正的显式请求（"帮我找相似病例"）不受此限，照常检索。

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

> **单进程 / 无 subagent host（如 Codex）fallback**：没有 Agent fan-out 时，**主 agent 顺序自己做**——对每条检索式逐条调用（或用 `codex exec` 子进程模拟"干净上下文/抗锚定"），把结果写到同样的 `raw/<name>.json`。功能等价，只是串行、慢一些。**`web-access`（CDP/Chrome）不可用时**，退化为 host 自带的 web 搜索/抓取（如 Codex 自带联网工具）直连 PubMed E-utilities / Europe PMC REST；`retrieval-sources.md` 的端点、pubtype 过滤、去重/撤稿规则与 host 无关，照用。

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

### Step 5 — 两层输出：患者版（主体）+ 医生版附录

产两份，写给两种读者。**默认先给患者版**；附录默认不主动展开，只提一句"要给医生看的详细版我也生成了，随时可展开"。脚手架按 locale，临床实体 + PMID 逐字。

**A. 患者版 brief（主体，是你回给用户的东西）** → 默认**聊天气泡语气**直接回给用户；同时把同样内容存一份 `相似病例_我可以问医生的.md`（可存档副本，非主体形态）。
- **聊天优先，文档次之**：默认输出是对话（先一句接住 + 治疗方向 + 一个问句），**不是甩一份 `.md` 清单**。6 维表 / 证据分级 / 结局明细都在"展开详细版"（§B）之后，用户说"展开详细版"才给。
- **开口先接住**（承接 Step 0），**不开场砌偏倚墙**。
- 只讲 **治疗方向**：把相似病例里试过的方案**按类别归并**（"有人用过 X 类、有人试过 Y 类方向"），**不逐例摊结局、不把预后当卖点**。
- **每个方向挂一条可点来源（PMID 超链接，每方向 ≤1 条）**：格式 `来源：[PMID <pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/)`（有 OA 全文可并挂 Europe PMC 链接）。这是让患者/医生能**一键核对、带去问医生**的锚——但**仍不逐例摊结局、不上 6 维表、不上偏倚横条**（那些在 §B）。这刻意放宽了旧的"患者版无 PMID"口径：目标是"可核验且不砌墙"，不是"零引用"。
- **不渲染死亡 / 急速恶化个案卡片**——单个 N=1 坏结局对患者是纯惊吓噪音（偏倚小 N，既非真希望也非诚实预后），这类结局只留在医生版附录作事实记录。
- **偏倚提醒轻编织进正文一句**（不是顶部一堵墙）：如"这些都是零散的个案、因为少见才被写下来，代表不了大多数人、更预测不了你——所以是**去问医生的线索**，不是答案"。
- **结尾一个具体下一步**（把人推向医生，不是推向更多文献）："我把这几个方向整理成你下次见医生能直接问的问题好不好？" → 路由 `cancer-buddy-visit-prep` / `cancer-buddy-second-opinion`。
- 末尾一行 canonical 免责（`不替代主诊医生的判断` 之义）。

**B. 医生版附录（次，默认不主动展开）** → `PRECEDENTS_临床附录.md`
- 完整严谨版：顶部偏倚横条 + 显式 N（含去重计数）+ 每例 6 维 match/mismatch（分歧必列）+ 逐线治疗 + **结局（含死亡，逐字接地）** + PMID + 逐字引文 + 审计 footer。
- 这是**给医生看的**，患者可点开但不是主体。证据分级 / 术语 / 结局明细都在这层，不进患者版。

模板见 [`references/output-template.md`](references/output-template.md)（§A 患者版 / §B 医生版）；患者版轻编织文案见 [`references/bias-disclosure.md`](references/bias-disclosure.md) 患者版一节。

**对话追问细化**：用户说"只看有脑转的 / 用过 XX 药的" → 在已检索结果上按维度过滤/重排；需新维度则二次检索（走 Step 2）。

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
- **G-TIER**：明确标注为**最弱证据（个案报告，证据层 C→D）**，低于试验、低于指南（`safety-guardrails.md` → Evidence grading）。证据分级/术语只进医生版附录。
- **G-LIVE**：live lookup，不用陈旧快照，网络不可达标"需现场核实"，不静默降级、不 LLM 合成个案。
- **G-PATIENT-FIRST（交互层）**：先厘清意图再检索（Step 0，含软信号只提一句不检索）；患者版**聊天优先、文档次之**，先接情绪、只给治疗方向、**每方向挂一条可点 PMID 来源**（可核验、可带去问医生）、**不摊死亡结局卡片**、偏倚轻编织不砌墙、结尾给一个下一步（推向医生非文献）。6 维表 / 证据分级 / 结局明细（含死亡）/ 偏倚横条降级到医生版附录（§B，用户说"展开详细版"才给），不作患者版主体。
- 其它：临床实体逐字禁译（P0）；绝不读 `raw/`/`99_`；披露规则照 `cancer-buddy` + `safety-guardrails.md`；情绪/心理危机不在本 skill 处理，建议专业支持。

## Output

```
patients/<patient_code>/reports/case-precedent/<slug>/
  ├── QUERY.md                      # Step 1 相似度画像
  ├── 相似病例_我可以问医生的.md     # 患者版 brief（主体，回给用户）
  ├── PRECEDENTS_临床附录.md         # 医生版附录（完整 6 维/PMID/结局，默认不主动展开）
  └── raw/
      ├── subagent-A.json           # Step 2 检索原始命中
      └── ...
```

`<slug>` 形如 `nsclc-egfr-t790m-3l-2026-07`，便于翻历史。

## Runtime adaptation（跨 host：Claude Code / Codex / 单进程）

本 skill 的 subagent 派发（Step 2 检索、Step 3/4 逐病例抽取与相似度判定）是 **Claude Code 的参考绑定，不是契约**。契约是"**产物**"：`QUERY.md` 相似度画像 → `raw/<name>.json` 检索命中 → 逐病例结构化抽取 + 6 维 match/mismatch → 两层输出（患者版 §A / 医生版 §B）。任何 host 只要产出同一套产物、守同样的安全门（G-BIAS/G-N/G-NO-AGGREGATE/G-GROUNDING/G-TIER/G-PATIENT-FIRST），就是对的。

- **Claude Code**：用 Agent tool 并行派检索 / 抽取 subagent（当前正文写法）。
- **单进程 / 无 subagent host（Codex 等）**：主 agent **顺序**遍历检索式与命中逐条做；需要"干净上下文/抗锚定"的抽取用 `codex exec` 子进程模拟。**并行只关乎速度，不关乎正确性**——串行结果等价。
- **联网**：`web-access`（CDP/Chrome）是 Claude Code 绑定；无它的 host 用自带 web 工具直连 PubMed/EPMC，`retrieval-sources.md` 的端点与过滤规则 host 无关。
- **接地不可降级**：无论哪种 host，PMID + 逐字引文、live 检索（不用陈旧快照）、撤稿检查这些是**契约级不变量**，不因缺 subagent 而放宽。

## References
- [retrieval-sources.md](references/retrieval-sources.md) — PubMed E-utilities + Europe PMC REST 端点、Case Reports pubtype 过滤语法、去重/撤稿检查、subagent 输出 schema
- [case-extraction-schema.md](references/case-extraction-schema.md) — 逐病例结构化抽取 schema（治疗路径 + 结局，逐字接地）
- [similarity-axes.md](references/similarity-axes.md) — 6 维相似度规则 + 分歧透明
- [bias-disclosure.md](references/bias-disclosure.md) — 偏倚披露文案（**患者版轻编织** + 医生版完整横条）+ no-aggregate 规则
- [output-template.md](references/output-template.md) — 两层输出模板：**§A 患者版 brief**（治疗方向 + 一个下一步）/ §B 医生版临床附录（6 维 + PMID + 结局 + 审计 footer）
- 共用：`../../references/roles.md`, `../../references/safety-guardrails.md`, `../../references/disclosure-behavior.md`, `../../references/i18n.md`, `../../references/patient-profile-schema.md`
- 联网底层依赖：`../web-access/SKILL.md`（subagent 必须加载）
