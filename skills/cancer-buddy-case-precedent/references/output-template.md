# case-precedent 输出模板 — 两层（§A 患者版 / §B 医生版）

本 skill 产**两份**，写给两种读者。**默认先给 §A 患者版**；§B 附录默认不主动展开，只提一句"给医生看的详细版我也生成了，随时可展开"。

> **i18n**：两层都**按 `profile.json.locale` 渲染**（见 `../../../references/i18n.md`）。中文骨架是 `zh` 渲染样例；其它 locale 时所有脚手架字符串查下方 §locale 表渲染，markdown 结构 1:1 不变。**临床实体逐字不译**（P0，`../../references/safety-guardrails.md` → 临床实体禁译）：癌种/组织学、基因、变异、TNM/分期、RECIST 码（CR/PR/SD/PD）、药名/方案、数值+单位、期刊原名、**PMID** 一律保持源文；每个抽取字段挂论文**逐字来源引文**（子串可回溯）。

---

## §A 患者版 brief — `相似病例_我可以问医生的.md`

写给一个害怕的患者/家属，**不是写给医生**。**默认是聊天气泡直接回给用户**（下面的 markdown 是同内容的可存档副本形态，不是要求先甩一份 `.md`）。规则（对齐 SKILL 的 **G-PATIENT-FIRST**）：
- **聊天优先、文档次之**：先一句接住 + 治疗方向 + 一个问句，重装内容（§B）藏在"展开详细版"之后。
- **开口先接住情绪**（承接 Step 0 的对话），**不砌偏倚墙**。
- 只讲 **治疗方向**（把相似病例试过的方案**按类别归并**），**不逐例摊结局、不放死亡/急速恶化个案卡片**。
- 偏倚提醒**轻编织进一句正文**（文案见 `bias-disclosure.md` 患者版一节），不是顶部横条。
- **每个方向挂一条可点来源（PMID 超链接，每方向 ≤1 条）**——让患者/医生能一键核对、带去问医生。**仍无** 6 维对照表、**无**证据分级术语、**无**逐例 PMID 轰炸、**无**偏倚横条——想看细节 → 指向 §B。（这放宽了旧口径的"患者版零 PMID"：从"零引用"改为"每方向一条可点来源"，目标是可核验且不砌墙。）
- 结尾**一个具体下一步**（推向医生 / visit-prep / second-opinion）。

**模板**：
```markdown
<接住的一句 —— 承接刚才的对话，认情绪>

我去文献里翻了和你（/你家人）情况**有部分相似**的真实病例，看别人试过哪些方向。先说清楚：这些都是零散的个案、因为少见才被写下来，**代表不了大多数人、也预测不了你**——所以下面是**去和医生讨论的线索**，不是答案。

**别人试过的治疗方向**（不是推荐，是拿去问医生的选项；每条后面是出处，可点开核对）：
- **<方向一，如某类靶向/免疫组合>** —— 有几位情况部分像你的人试过这个方向。来源：[PMID <pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/)
- **<方向二>** —— … 来源：[PMID <pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/)
- **<方向三>** —— … 来源：[PMID <pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/)

（我没有把每个人的结局一个个列出来——单个病例的结局既代表不了你、也容易误导。给医生看的完整版在 `PRECEDENTS_临床附录.md`，你或医生想看细节随时展开。）

**下一步我能帮你**：把这几个方向整理成你下次见医生可以直接问的问题（"这些对我适用吗？"），要不要？

> 这不替代主诊医生的判断，也不是治疗建议。真正适不适合你，要你和医生一起定。
```

**填充示例**（GEJ 印戒细胞癌真实案例的患者版）：
```markdown
你想找和你爸情况像的人、看别人怎么走过来的——这个念头我懂。

我去 PubMed / Europe PMC 翻了和你爸**有部分相似**的真实病例（食管胃结合部腺癌、腹膜转移这一类）。先说清楚：这些是零散的个案，因为少见才被写下来，**代表不了大多数人、也预测不了你爸**——是去问医生的线索，不是答案。

**别人试过的治疗方向**（拿去问医生的选项，不是推荐；每条后面是出处，可点开核对）：
- **化疗 + 免疫联合、再看能不能转化手术** —— 有人在腹膜播散后走这个方向，播散一度消失后做了手术。来源：[PMID 38712345](https://pubmed.ncbi.nlm.nih.gov/38712345/)
- **同步放化疗 + 免疫维持** —— 局部复发时有人走过这条。来源：[PMID 37990011](https://pubmed.ncbi.nlm.nih.gov/37990011/)
- **针对特定靶点的方案** —— 前提是先做基因检测明确靶点（你爸目前没测）。来源：[PMID 39004567](https://pubmed.ncbi.nlm.nih.gov/39004567/)

（每个人的结局我没有一个个摊开——单个病例的好坏都代表不了你爸。给医生看的完整版在 `PRECEDENTS_临床附录.md`。）

**下一步**：要不要我把这三个方向整理成你下次见主诊医生能直接问的问题？

> 这不替代主诊医生的判断，也不是治疗建议。
```

---

## §B 医生版临床附录 — `PRECEDENTS_临床附录.md`

给医生看的完整严谨版（患者可点开，**非主体**）。证据分级 / 6 维对照 / 逐例结局（含死亡，逐字接地）/ PMID / 审计 footer 都在这层。以下是 §B 的完整模板。

> **i18n**：同 §A，脚手架按 locale、临床实体逐字。

> **本模板的三条硬约束**（对齐 SKILL Safety 的 P0 门）：
> 1. **偏倚横条 + 显式 `N=<命中数>` 必须在最顶部**，任何病例之前——它是读这份清单的前提，不是脚注（G-BIAS / G-N）。
> 2. **绝不出现任何"率"或聚合数字作为主视觉**——不算生存率/有效率/缓解率，不按综合相似度打一个总分挂在标题上（G-NO-AGGREGATE）。可按"接近程度"分组，但组标题是**定性**档位词，不是分数。
> 3. **每条病例的相似度对照 6 维都要列，分歧维（mismatch/partial/unknown）必须可见**，不能只挑相似的展示（G-SIMILARITY-TRANSPARENCY）。

```markdown
# 相似先例清单 — <一句话描述本次查询>

> ⚠️ **请先读这段再往下看 —— 这决定你怎么理解下面每一条。**
> 下面是 **N=<命中数>** 例有文献记录的**真实个案报告（case report）**。个案报告是**最弱一级的证据**（证据层 C→D，**低于临床试验、低于诊疗指南**）。一篇个案会被发表，往往正是因为它**罕见**或**疗效特别突出**——所以"它被发表"这件事本身，就把这批病例**系统性地推向乐观**。它们**不代表大多数人**，**更不是对你本人结局的预测**。这里**不做、也不能做**任何生存率 / 有效率 / 缓解率的统计——N 这么小，任何"率"都是误导。
> 请把这份清单当作**去研究、去和你的主诊医生讨论的线索**，不是治疗建议，不是预后预测。

> 查询定义：见 [QUERY.md](QUERY.md)
> 命中：**N=<命中数>** 例（已去重 + 过撤稿检查）
> 生成时间：YYYY-MM-DD

---

## 你的相似度画像（对照基准）

| 维度 | 你（本人） |
|---|---|
| 原发癌种 | <primary，verbatim> |
| 组织学 | <histology，verbatim / 未报告> |
| 分期 | <stage，verbatim / 未报告> |
| 关键驱动 | <key_drivers，逐字 gene/variant / 未测> |
| 治疗线 | <当前第几线 / 进展情况> |
| 关键合并症 | <comorbidity，verbatim / 无> |

> 下面每条病例都会**逐维**和这张表对照，相符与分歧一起摆出来。

---

## 较相似（接近程度：高）

### 病例 1 · PMID [<pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/) · <期刊原名> · <year>

> 🔖 **为何可能被发表**：<per-case bias tag，例如"罕见 T790M 三线长缓解"——提醒这条个案的发表动机，即它的乐观偏倚来源>

**相似度对照**（分歧维已一并列出，不隐藏）

| 维度 | 你 | 本病例 | 判定 | 一句话理由 |
|---|---|---|---|---|
| 原发癌种 | <primary> | <case primary> | ✅ 相符 | <rationale> |
| 组织学 | <histology> | <case histology> | ✅ 相符 | <rationale> |
| 分期 | <stage> | <case stage> | 🟡 部分相符 | <rationale> |
| 关键驱动 | <driver> | <case driver> | ✅ 相符 | <rationale> |
| 治疗线 | <line> | <case line> | ❌ 不符 | <rationale> |
| 关键合并症 | <comorbidity> | <case comorbidity> | ❔ 未知 | 论文未报告，无法对照 |

> 判定档：✅ 相符 · 🟡 部分相符 · ❌ 不符 · ❔ 未知（论文未报告）。**不把这 6 格折算成一个总分**——分歧本身就是要你看见的信息。

**治疗路径**（逐线，方案逐字来自论文）

| 线 | 方案（verbatim） | 意图 | 时序 |
|---|---|---|---|
| 1 | <regimen，verbatim> | <intent / 未报告> | <started_relative / 未报告> |
| 2 | <regimen，verbatim> | <intent / 未报告> | <started_relative / 未报告> |
| … | … | … | … |

**结局**（每项挂逐字引文；论文没写的标 未报告，不猜）

- **最佳缓解（best response）**：<RECIST 码 verbatim / 未报告>
  - > "<verbatim_quote from source>"
- **随访时长（follow-up）**：<duration verbatim / 未报告>
  - > "<verbatim_quote from source>"
- **状态（status）**：<alive / deceased / NED / progression / 未报告>
  - > "<verbatim_quote from source>"

> 证据强度：<extraction_confidence：抽自 OA 全文 / 仅摘要 / 信息稀薄>。<若 low：⚠️ 本条信息稀薄、多字段未报告，仅作弱线索。>

**来源**：PMID [<pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/) · <期刊原名> · <year>
> 逐字引文（可回溯）："<key verbatim source quote>"

---

### 病例 2 · PMID [<pmid>](https://pubmed.ncbi.nlm.nih.gov/<pmid>/) · <期刊原名> · <year>

（同上结构：per-case bias tag → 相似度对照 6 维 → 治疗路径 → 结局 → 来源逐字引文）

---

## 部分相似（接近程度：中）

### 病例 3 · …

（同上结构）

---

## 分歧较大但仍相关（接近程度：低）

### 病例 4 · …

（同上结构；这一组通常关键驱动或组织学与你不符，放这里是为了透明，不是为了凑数）

---

## 检索到但未纳入

| 病例 / PMID | 为何未纳入 |
|---|---|
| PMID <pmid> | 撤稿（Retracted Publication），已剔除 |
| PMID <pmid> | Expression of Concern，存疑，仅登记不作证据 |
| PMID <pmid> | 去重（与病例 1 同一 PMID / DOI） |
| PMID <pmid> | 非个案报告（pubtype 不含 Case Reports） |

---

<!-- 审计 footer（safety-guardrails.md → Audit trail），供主诊医生核验患者读了什么 -->
---
生成时间：YYYY-MM-DDTHH:MM:SS+08:00
技能：cancer-buddy-case-precedent vX.Y.Z
档案指纹：<profile.json sha256 前 8 位>
查询数据库：PubMed（E-utilities）· Europe PMC（REST）
命中 N=<命中数>（已去重 + 过撤稿检查）

---

> **这些是有文献记录的真实病例，不是对你结局的预测，也不是治疗建议。** 个案报告往往因罕见或疗效突出才被发表，系统性偏乐观、不代表总体，更**不替代主诊医生的判断**。请把这份清单带给你的主诊医生一起看。
```

## locale 字符串表

模板里的每个脚手架字符串有一个稳定 string id（语言无关）。渲染时按 `profile.json.locale` 取该 locale 列的值；表里没有的 locale，按 string id 的英文语义在目标语言生成同义文案（不硬编码新表，交 LLM 按语义本地化输出）。**临床实体、PMID、期刊原名、RECIST 码不进字符串表**——它们逐字来自数据，不本地化。偏倚横条 / 免责声明的**权威文案**在 [`bias-disclosure.md`](bias-disclosure.md)，此表只登记其 string id 与 zh/en 参考渲染，二者须保持一致。

| string id | `zh`（现有骨架） | `en`（canonical） |
|---|---|---|
| `title.precedents` | 相似先例清单 | Similar-case precedents |
| `banner.bias` | ⚠️ 请先读这段再往下看 —— 这决定你怎么理解下面每一条。下面是 N=<命中数> 例有文献记录的真实个案报告（case report）。个案报告是最弱一级的证据（证据层 C→D，低于临床试验、低于诊疗指南）。一篇个案会被发表，往往正是因为它罕见或疗效特别突出——所以"它被发表"这件事本身，就把这批病例系统性地推向乐观。它们不代表大多数人，更不是对你本人结局的预测。这里不做、也不能做任何生存率 / 有效率 / 缓解率的统计——N 这么小，任何"率"都是误导。请把这份清单当作去研究、去和你的主诊医生讨论的线索，不是治疗建议，不是预后预测。 | ⚠️ Read this first — it changes how you should read every case below. What follows are N=<count> real case reports from the literature. Case reports are the weakest tier of evidence (level C→D, below clinical trials, below guidelines). A case report usually gets published precisely because it is rare or the response was unusually good — so the very fact these were published skews this set toward the optimistic. They do NOT represent most patients, and they are NOT a prediction of your outcome. No survival / response / remission rate is computed here — with N this small, any "rate" would mislead. Treat this list as leads to research and to discuss with your treating physician — not treatment advice, not a prognosis. |
| `meta.query_ref` | 查询定义：见 | Query definition: see |
| `meta.hits` | 命中 | Hits |
| `meta.hits_note` | 例（已去重 + 过撤稿检查） | cases (deduplicated + retraction-checked) |
| `meta.generated_at` | 生成时间 | Generated |
| `sec.your_profile` | 你的相似度画像（对照基准） | Your similarity profile (comparison baseline) |
| `sec.group.high` | 较相似（接近程度：高） | More similar (closeness: high) |
| `sec.group.mid` | 部分相似（接近程度：中） | Partly similar (closeness: medium) |
| `sec.group.low` | 分歧较大但仍相关（接近程度：低） | More divergent but still relevant (closeness: low) |
| `sec.not_included` | 检索到但未纳入 | Retrieved but not included |
| `field.you` | 你（本人） | You |
| `field.you_short` | 你 | You |
| `field.this_case` | 本病例 | This case |
| `field.primary` | 原发癌种 | Primary cancer |
| `field.histology` | 组织学 | Histology |
| `field.stage` | 分期 | Stage |
| `field.key_driver` | 关键驱动 | Key driver |
| `field.treatment_line` | 治疗线 | Treatment line |
| `field.comorbidity` | 关键合并症 | Key comorbidity |
| `field.sim_table` | 相似度对照 | Similarity comparison |
| `field.verdict` | 判定 | Verdict |
| `field.rationale` | 一句话理由 | One-line rationale |
| `field.per_case_bias` | 为何可能被发表 | Why this may have been published |
| `field.treatment_path` | 治疗路径 | Treatment path |
| `field.line` | 线 | Line |
| `field.regimen` | 方案 | Regimen |
| `field.intent` | 意图 | Intent |
| `field.timing` | 时序 | Timing |
| `field.outcome` | 结局 | Outcome |
| `field.best_response` | 最佳缓解（best response） | Best response |
| `field.followup` | 随访时长（follow-up） | Follow-up duration |
| `field.status` | 状态 | Status |
| `field.evidence_strength` | 证据强度 | Evidence strength |
| `field.source` | 来源 | Source |
| `field.source_quote` | 逐字引文（可回溯） | Verbatim quote (traceable) |
| `verdict.match` | ✅ 相符 | ✅ Match |
| `verdict.partial` | 🟡 部分相符 | 🟡 Partial |
| `verdict.mismatch` | ❌ 不符 | ❌ Mismatch |
| `verdict.unknown` | ❔ 未知 | ❔ Unknown |
| `verdict.legend` | 判定档：✅ 相符 · 🟡 部分相符 · ❌ 不符 · ❔ 未知（论文未报告）。不把这 6 格折算成一个总分——分歧本身就是要你看见的信息。 | Verdict scale: ✅ Match · 🟡 Partial · ❌ Mismatch · ❔ Unknown (not reported). These 6 cells are NOT collapsed into one score — the divergences are exactly what you need to see. |
| `val.not_reported` | 未报告 | Not reported |
| `val.not_tested` | 未测 | Not tested |
| `val.none` | 无 | None |
| `conf.fulltext` | 抽自 OA 全文 | extracted from OA full text |
| `conf.abstract_only` | 仅摘要 | abstract only |
| `conf.sparse` | 信息稀薄 | sparse |
| `conf.low_warn` | ⚠️ 本条信息稀薄、多字段未报告，仅作弱线索。 | ⚠️ This case is sparse with many fields not reported; treat as a weak lead only. |
| `col.case_pmid` | 病例 / PMID | Case / PMID |
| `col.why_excluded` | 为何未纳入 | Why excluded |
| `excl.retracted` | 撤稿（Retracted Publication），已剔除 | Retracted publication — removed |
| `excl.eoc` | Expression of Concern，存疑，仅登记不作证据 | Expression of Concern — logged, not used as evidence |
| `excl.dedupe` | 去重（与已列病例同一 PMID / DOI） | Deduplicated (same PMID / DOI as a listed case) |
| `excl.not_case_report` | 非个案报告（pubtype 不含 Case Reports） | Not a case report (pubtype lacks Case Reports) |
| `audit.generated_at` | 生成时间 | Generated at |
| `audit.skill` | 技能 | Skill |
| `audit.profile_hash` | 档案指纹 | Profile hash |
| `audit.databases` | 查询数据库 | Databases queried |
| `disclaimer.footer` | 这些是有文献记录的真实病例，不是对你结局的预测，也不是治疗建议。个案报告往往因罕见或疗效突出才被发表，系统性偏乐观、不代表总体，更不替代主诊医生的判断。请把这份清单带给你的主诊医生一起看。 | These are real cases documented in the literature — not a prediction of your outcome, and not treatment advice. Case reports tend to be published because they are rare or the response stood out, so they skew optimistic and don't represent the whole; they do not replace your treating physician's judgment. Bring this list to your treating physician and read it together. |

> 叙事段（per-case bias tag、判定理由句、证据强度说明）走 prompt 指令直接用 locale 写，不查表——prompt 写明 "Output all patient-visible scaffold prose in `<locale>`; keep clinical entities + PMIDs + journal names + RECIST codes verbatim per `../../references/i18n.md` §4 and `../../references/safety-guardrails.md` → 临床实体禁译."

## 渲染原则

- **偏倚横条 + `N=<命中数>` 永远在最顶部**，任何病例之前——它是理解整份清单的前提（G-BIAS / G-N）。文案权威版在 `bias-disclosure.md`。
- **绝不出现聚合数字作主视觉**——不算生存率/有效率/缓解率，不把 6 维相似度折算成一个总分挂标题；分组用定性档位词（高/中/低接近程度），不是分数（G-NO-AGGREGATE）。
- **6 维对照必须全列，分歧维（🟡/❌/❔）必须可见**——只挑相符维展示 = bug（G-SIMILARITY-TRANSPARENCY）。
- **每条病例每个结局字段挂逐字引文**，论文没写的标 `未报告`，不跨字段推断（G-GROUNDING；`case-extraction-schema.md` §2–4）。
- **PMID 逐字且可点**（`https://pubmed.ncbi.nlm.nih.gov/<pmid>/`）；期刊原名、药名、基因、变异、RECIST 码逐字不译。
- **撤稿 / 存疑 / 去重条目进"检索到但未纳入"表**，绝不当有效证据混入正文（撤稿检查见 `retrieval-sources.md` §4）。
- **审计 footer 不能省**——生成时间 + skill 名+版本 + profile hash 前 8 位 + 查询数据库，供主诊医生核验（`safety-guardrails.md` → Audit trail）。
- **末尾 canonical 免责不能省**——须同时表达「不替代主诊医生的判断」+「不是预后预测」+「不是治疗建议」三层（`safety-guardrails.md` → Always say；对齐 `bias-disclosure.md`）。
- **披露抑制态**（`disclosure_state == "suppressed"` 且 `role=patient`）：结局字段照实但用临床中性语，避免"晚期/进展后/生存期"等加重情绪的表述（`../../references/disclosure-behavior.md`）。

---

## 填充示例（EGFR NSCLC 三线，虚构但写实）

> 仅示范渲染形态与逐字接地写法；下面的 PMID、期刊、引文均为**演示占位**，非真实文献。真实运行时每个 PMID / 引文都来自 live 检索命中，可回溯核验。

```markdown
# 相似先例清单 — 像我这样 EGFR L858R + T790M、三线进展的非小细胞肺癌，别人怎么治的

> ⚠️ **请先读这段再往下看 —— 这决定你怎么理解下面每一条。**
> 下面是 **N=2** 例有文献记录的真实个案报告（case report）。个案报告是最弱一级的证据（证据层 C→D，低于临床试验、低于诊疗指南）。一篇个案会被发表，往往正是因为它罕见或疗效特别突出——所以"它被发表"这件事本身，就把这批病例系统性地推向乐观。它们不代表大多数人，更不是对你本人结局的预测。这里不做、也不能做任何生存率 / 有效率 / 缓解率的统计——N 这么小，任何"率"都是误导。
> 请把这份清单当作去研究、去和你的主诊医生讨论的线索，不是治疗建议，不是预后预测。

> 查询定义：见 [QUERY.md](QUERY.md)
> 命中：**N=2** 例（已去重 + 过撤稿检查）
> 生成时间：2026-07-06

---

## 你的相似度画像（对照基准）

| 维度 | 你（本人） |
|---|---|
| 原发癌种 | non-small cell lung cancer |
| 组织学 | adenocarcinoma |
| 分期 | IV |
| 关键驱动 | EGFR L858R；EGFR T790M（获得性） |
| 治疗线 | 三线进展（osimertinib 后） |
| 关键合并症 | 无 |

> 下面每条病例都会逐维和这张表对照，相符与分歧一起摆出来。

---

## 较相似（接近程度：高）

### 病例 1 · PMID [39001234](https://pubmed.ncbi.nlm.nih.gov/39001234/) · Lung Cancer · 2024

> 🔖 **为何可能被发表**：一例 T790M 患者 osimertinib 耐药后再挑战仍获长缓解——正因"疗效突出"才成文，请带着这层乐观偏倚读。

**相似度对照**（分歧维已一并列出，不隐藏）

| 维度 | 你 | 本病例 | 判定 | 一句话理由 |
|---|---|---|---|---|
| 原发癌种 | non-small cell lung cancer | non-small cell lung cancer | ✅ 相符 | 同为 NSCLC |
| 组织学 | adenocarcinoma | adenocarcinoma | ✅ 相符 | 同为腺癌 |
| 分期 | IV | IV | ✅ 相符 | 同为 IV 期 |
| 关键驱动 | EGFR L858R；T790M | EGFR L858R；T790M | ✅ 相符 | 同为 L858R 合并获得性 T790M |
| 治疗线 | 三线进展 | 二线进展 | 🟡 部分相符 | 本病例在二线进展后即报告，你已到三线 |
| 关键合并症 | 无 | 未报告 | ❔ 未知 | 论文未报告合并症，无法对照 |

> 判定档：✅ 相符 · 🟡 部分相符 · ❌ 不符 · ❔ 未知（论文未报告）。不把这 6 格折算成一个总分——分歧本身就是要你看见的信息。

**治疗路径**（逐线，方案逐字来自论文）

| 线 | 方案（verbatim） | 意图 | 时序 |
|---|---|---|---|
| 1 | gefitinib | palliative | at diagnosis |
| 2 | osimertinib 80 mg daily | palliative | after first-line progression |

**结局**（每项挂逐字引文；论文没写的标 未报告，不猜）

- **最佳缓解（best response）**：PR
  - > "A partial response was observed, sustained through 18 months of follow-up."
- **随访时长（follow-up）**：18 months
  - > "sustained through 18 months of follow-up"
- **状态（status）**：未报告
  - > 论文仅写 18 个月随访仍有 PR，未明确写 alive/deceased/NED——不从"仍有缓解"推断"存活"。

> 证据强度：抽自 OA 全文，治疗线与缓解字段均有明确逐字引文。

**来源**：PMID [39001234](https://pubmed.ncbi.nlm.nih.gov/39001234/) · Lung Cancer · 2024
> 逐字引文（可回溯）："Upon progression, treatment was switched to osimertinib 80 mg daily. A partial response was observed, sustained through 18 months of follow-up."

---

## 部分相似（接近程度：中）

### 病例 2 · PMID [38550777](https://pubmed.ncbi.nlm.nih.gov/38550777/) · JTO Clinical and Research Reports · 2023

> 🔖 **为何可能被发表**：一例 EGFR 突变肺癌在标准 TKI 用尽后尝试非常规联合方案——因"路径少见"成文，样本极端，勿外推。

**相似度对照**（分歧维已一并列出，不隐藏）

| 维度 | 你 | 本病例 | 判定 | 一句话理由 |
|---|---|---|---|---|
| 原发癌种 | non-small cell lung cancer | non-small cell lung cancer | ✅ 相符 | 同为 NSCLC |
| 组织学 | adenocarcinoma | adenocarcinoma | ✅ 相符 | 同为腺癌 |
| 分期 | IV | IIIB | ❌ 不符 | 本病例为 IIIB，未到 IV 期 |
| 关键驱动 | EGFR L858R；T790M | EGFR exon 19 deletion | 🟡 部分相符 | 同属 EGFR 敏感突变，但为 19 外显子缺失，非 L858R；未报告 T790M |
| 治疗线 | 三线进展 | 三线进展 | ✅ 相符 | 同为三线进展后 |
| 关键合并症 | 无 | type 2 diabetes | 🟡 部分相符 | 本病例合并 2 型糖尿病，你无此项 |

> 判定档：✅ 相符 · 🟡 部分相符 · ❌ 不符 · ❔ 未知（论文未报告）。不把这 6 格折算成一个总分——分歧本身就是要你看见的信息。

**治疗路径**（逐线，方案逐字来自论文）

| 线 | 方案（verbatim） | 意图 | 时序 |
|---|---|---|---|
| 1 | osimertinib | palliative | at diagnosis |
| 2 | carboplatin + pemetrexed | palliative | 未报告 |
| 3 | osimertinib + bevacizumab | palliative | after second-line progression |

**结局**（每项挂逐字引文；论文没写的标 未报告，不猜）

- **最佳缓解（best response）**：SD
  - > "The best response to the combination was stable disease."
- **随访时长（follow-up）**：未报告
  - > 论文未给出明确随访时长。
- **状态（status）**：alive
  - > "The patient remained on treatment and alive at the time of report."

> 证据强度：仅摘要，二线时序为 未报告；⚠️ 关键驱动与你不同（exon 19 del vs L858R），此条相关但请注意分歧。

**来源**：PMID [38550777](https://pubmed.ncbi.nlm.nih.gov/38550777/) · JTO Clinical and Research Reports · 2023
> 逐字引文（可回溯）："A third-line combination of osimertinib plus bevacizumab was initiated after second-line progression; the best response to the combination was stable disease."

---

## 检索到但未纳入

| 病例 / PMID | 为何未纳入 |
|---|---|
| PMID 37220001 | 撤稿（Retracted Publication），已剔除 |
| PMID 39001234 | 去重（PubMed 与 Europe PMC 命中同一 PMID，已合并为病例 1） |
| PMID 36540123 | 非个案报告（pubtype 为 Review，不含 Case Reports） |

---

---
生成时间：2026-07-06T22:14:03+08:00
技能：cancer-buddy-case-precedent v0.1.0
档案指纹：a1b2c3d4
查询数据库：PubMed（E-utilities）· Europe PMC（REST）
命中 N=2（已去重 + 过撤稿检查）

---

> **这些是有文献记录的真实病例，不是对你结局的预测，也不是治疗建议。** 个案报告往往因罕见或疗效突出才被发表，系统性偏乐观、不代表总体，更不替代主诊医生的判断。请把这份清单带给你的主诊医生一起看。
```
