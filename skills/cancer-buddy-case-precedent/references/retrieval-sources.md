# Retrieval sources for case-precedent

检索源 + pubtype 过滤语法 + 去重 + 撤稿检查 + subagent 输出 schema。**只检索 publication type = Case Reports**（Step 2）。派 subagent 时挑本次相关的 1–3 行进 prompt，subagent 自己加载 `web-access` skill 处理抓取；**不要把整个文档塞 prompt**。

一手公共 API > 通用搜索引擎。所有实体（癌种/组织学/基因/变异/药名/PMID/期刊）逐字，不译不改。

---

## 1. PubMed E-utilities

Base：`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`；`db=pubmed`。

| 端点 | 作用 | 关键参数 |
|---|---|---|
| `esearch.fcgi` | 检索式 → PMID 列表 | `db=pubmed` · `term=<query>` · `retmax=<N>` · `retmode=json` |
| `efetch.fcgi` | PMID 列表 → 详情（XML） | `db=pubmed` · `id=<pmid,pmid,...>` · `rettype=abstract` · `retmode=xml` |

**Pubtype 过滤（硬门）**：检索式必须 `AND` 上
```
"Case Reports"[Publication Type]
```

**从 similarity_profile 组装 term**：`primary` + `histology` + `key_drivers`（基因/变异逐字）+ 治疗线/分期关键词，各维用 `AND` 串，同维同义词用 `OR`。

示例 1（NSCLC / EGFR T790M / 三线）：
```
("Carcinoma, Non-Small-Cell Lung"[MeSH] OR "non-small cell lung cancer"[tiab])
AND ("EGFR"[tiab] AND ("T790M"[tiab] OR "L858R"[tiab]))
AND ("third-line"[tiab] OR "3rd line"[tiab] OR "osimertinib resistance"[tiab])
AND "Case Reports"[Publication Type]
```
示例 2（CRC / KRAS G12C）：
```
("Colorectal Neoplasms"[MeSH] OR "colorectal cancer"[tiab])
AND ("KRAS G12C"[tiab] OR ("KRAS"[tiab] AND "G12C"[tiab]))
AND "Case Reports"[Publication Type]
```

**esearch → efetch 流程**：`esearch` 拿 PMID 列表（建议 `retmax=20`，可对话追问时再扩），`efetch` 批量拉 XML 解析：`ArticleTitle`（逐字）、`AbstractText`（多段 itertext 拼全，勿只取首段）、`PMID`、`PubDate`（year）、`Journal/Title`、`PublicationType` 列表。

**速率限制**：无 API key ≤3 req/s（有 key ≤10）。抓取与限速由 `web-access` skill 处理，subagent 不自己 sleep/重试逻辑。

---

## 2. Europe PMC REST

端点：`https://www.ebi.ac.uk/europepmc/webservices/rest/search`

| 参数 | 值 |
|---|---|
| `query` | `PUB_TYPE:"Case Reports" AND <profile terms>` |
| `format` | `json` |
| `pageSize` | `25`（对话追问可扩） |
| `resultType` | `core`（带 fullTextUrlList / 期刊 / pubType） |

示例 query：
```
PUB_TYPE:"Case Reports" AND (EGFR AND T790M) AND "non-small cell lung cancer"
```

**OA 全文**：`resultType=core` 返回 `fullTextUrlList`；OA 文章可取全文 XML 供 Step 3 逐病例抽取（优于摘要）：
```
https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/fullTextXML
# 例：.../PMC/PMC1234567/fullTextXML  或  .../MED/<pmid>/fullTextXML
```
`isOpenAccess=="Y"` 才走全文；非 OA 只用摘要，抽不到的字段标 `未报告`。

---

## 3. 去重 + 显式计数（主 agent 汇总时做）

subagent 各自返回 raw JSON，**主 agent 合并**时去重：
1. 主键 **PMID**（PubMed 与 EPMC 命中同一 PMID 视为同一条）。
2. 无 PMID → 回退 **DOI**。
3. 均无 → 回退**标题规范化**（小写、去标点/空白）匹配。

合并保留信息更全的一条（优先有 OA 全文 URL 的）。

**必须真算、并显式报告重叠数**——EPMC 索引本身镜像 PubMed，两源对同一查询**几乎必有交集**：
- 计算 `overlap = |PubMed ∩ EPMC|`（按上面主键），`N = PubMed + EPMC − overlap`。
- 在 PRECEDENTS.md 的命中行**显式写出**：`PubMed X + EPMC Y，去重 overlap 条重叠 → N 唯一`。
- **禁止**在未真算交集的情况下写"均无重复 / 无重叠"。若算出 `overlap == 0`，这是**异常信号**（查询过度发散或 dedup 未真跑）——复核后再出，不得默认放行。
- `N` 是偏倚披露（G-N）的头号数字，必须是真实 post-dedup 唯一数，不是两源相加。

## 3b. 时间预算与规模上限（患者向，必须有界）

- 每个检索 subagent **硬时限 ≤ 5 分钟**；超时返回"未完成 + 已采集部分"，不无限等。
- **OA 全文只抓去重后按相似度排序的 top ≤15 篇**，其余用摘要——逐篇下全文是十几分钟拖尾的主因。
- 若一源明显拖尾，先用已返回的另一源出结果并标注"另一源仍在检索"。
- 逐病例展开卡片 ≤ 10 例（见 SKILL Step 3/5）。

---

## 4. 撤稿检查（G-GROUNDING 门）

发表偏倚之外，个案库里撤稿/存疑条目须剔除或显式标注：

| 源 | 方法 |
|---|---|
| PubMed | 交叉检索 `"Retracted Publication"[Publication Type]`；或 efetch XML 里 `PublicationType` 含 `Retracted Publication` / `Retraction of Publication` |
| Europe PMC | 结果对象的撤稿标记 / `commentCorrectionList`（`RETRACTION` / `EXPRESSION_OF_CONCERN`） |

命中 → `retraction_status` 标 `retracted` / `expression_of_concern`；这类条目**从 PRECEDENTS.md 剔除，或明确标注**为撤稿/存疑，绝不当有效证据呈现。此步满足 SKILL 的 **G-GROUNDING** 门。

---

## 5. Live-lookup 红线

- **不使用陈旧静态快照**——每次现场查 PubMed / Europe PMC（`../../references/safety-guardrails.md` → no-silent-snapshot）。
- 网络不可达 / API 报错 → 标 **"需现场核实"**，如实报错，**绝不 LLM 编造个案 / 编造 PMID / 编造结局**（G-LIVE + 反幻觉）。
- 返回 0 条 → 诚实报"未找到相似个案"，不降级、不编。

---

## 6. Subagent 输出 JSON schema

每个检索 subagent 写到：
```
patients/<patient_code>/reports/case-precedent/<slug>/raw/<subagent-name>.json
```

```json
{
  "source": "pubmed",                       // "pubmed" | "europepmc"
  "query_used": "(...) AND \"Case Reports\"[Publication Type]",
  "fetched_at": "2026-07-06T14:32:00+08:00",  // ISO8601
  "items": [
    {
      "pmid": "34567890",                   // 无则 null
      "doi": "10.1000/xyz123",              // 无则 null
      "title": "…",                          // verbatim，原文标题不译不改
      "journal": "Lung Cancer",
      "year": 2023,
      "pub_types": ["Case Reports", "Journal Article"],
      "oa_fulltext_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC/PMC1234567/fullTextXML",  // 无 OA 则 null
      "abstract_snippet": "…",               // verbatim 摘要片段（供去重/预筛），非改写
      "retraction_status": "none"            // "none" | "retracted" | "expression_of_concern"
    }
  ],
  "notes": "retmax=20；命中 12 条，其中 1 条 EXPRESSION_OF_CONCERN 已标注"
}
```

字段约定：
- `title` / `abstract_snippet` **verbatim**——不摘要、不翻译、不润色（下游 Step 3 逐字接地依赖原文子串）。
- 抓不到的字段填 `null`，**不猜测、不补全**。
- `retraction_status` 默认 `none`；第 4 节命中才改。
- 一个 subagent 一个 source 一个 JSON；主 agent 按第 3 节合并去重、按第 4 节过撤稿后进 Step 3。
