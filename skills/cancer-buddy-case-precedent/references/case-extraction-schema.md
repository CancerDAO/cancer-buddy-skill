# case-extraction-schema.md — 逐病例结构化抽取

> Step 3 用。对每篇命中的个案报告（case report），把「这位真实患者试过什么、发生了什么」抽成一条结构化记录。**抽取器只搬运论文里写了的东西，不合成、不推断、不计算。** 每个临床值必须有逐字来源引文可回溯，无引文的值 = 编造 = 禁止。
>
> 临床实体逐字禁译（P0，见 `../../references/safety-guardrails.md` → 临床实体禁译）：药名 / 方案 / 基因 / 变异 / RECIST 码 / TNM / 分期 / 数值+单位 / PMID 一律 verbatim from source。只有 `未报告` 这类脚手架标记按 locale。

## 1. Per-case JSON schema（抽取输出）

每篇个案抽成一个 JSON 对象，写进 Step 2 subagent 的 `raw/` 或主 agent 汇总层：

```jsonc
{
  "case_id": "case-01",                    // 本次运行内稳定序号
  "pmid": "12345678",                       // verbatim；无 PMID 用 DOI，两者皆无标 未报告
  "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
  "oa_fulltext_available": true,            // bool；true=抽自 OA 全文，false=只有摘要

  "patient_descriptors": {
    "age": "67",                            // verbatim（"67-year-old" → "67"），无则 未报告
    "sex": "female",                        // verbatim from source
    "primary": "non-small cell lung cancer",// verbatim 原发癌种（禁译）
    "histology": "adenocarcinoma",          // verbatim；无则 未报告
    "stage": "IV",                          // verbatim TNM/分期；无则 未报告
    "drivers": [                            // gene/variant 逐字，禁译、禁归一
      {"gene": "EGFR", "variant": "L858R", "verbatim_quote": "..."},
      {"gene": "EGFR", "variant": "T790M", "verbatim_quote": "..."}
    ],
    "prior_lines_count": 2                   // int；论文明确写了才填，否则 未报告
  },

  "treatment_path": [                        // 有序，按论文陈述的线序
    {
      "line": 1,                            // int
      "regimen": "osimertinib",             // verbatim 药名/方案（禁译、禁展开缩写）
      "intent": "palliative",               // adjuvant/neoadjuvant/palliative/maintenance/…；无则 未报告
      "started_relative": "at diagnosis",   // 仅在论文写了时序时填，否则 未报告
      "verbatim_quote": "The patient received osimertinib 80 mg daily as first-line therapy."
    }
  ],

  "outcome": {
    "best_response": "PR",                  // RECIST 码 verbatim（CR/PR/SD/PD）；无则 未报告
    "followup_duration": "18 months",       // verbatim；无则 未报告
    "status": "alive",                      // alive/deceased/NED/progression/未报告，须逐字有据
    "verbatim_quote": "At 18 months of follow-up, the patient remained alive with a partial response."
  },

  "extraction_confidence": "high",          // high/medium/low
  "missing_fields": ["prior_lines_count"]   // 标了 未报告 的字段路径列表
}
```

字段速览：

| 字段 | 类型 | 规则 |
|---|---|---|
| `case_id` / `pmid` / `source_url` | string | 标识，PMID 逐字 |
| `oa_fulltext_available` | bool | 决定抽取源（全文 vs 摘要） |
| `patient_descriptors.*` | string/int/[] | 相似度画像输入；临床实体逐字禁译 |
| `treatment_path[]` | ordered [] | 每线一对象，`line` 升序；`regimen` 逐字 |
| `outcome.*` | string | `best_response`/`status` 须逐字有据，禁推断 |
| `extraction_confidence` | enum | high/medium/low（见 §6） |
| `missing_fields[]` | [] | 所有 `未报告` 字段的路径 |

## 2. Verbatim grounding rules（P0）

- **每个临床值都要有 backing quote**：`drivers[]` / `treatment_path[]` / `outcome` 里的每个药名、RECIST 码、随访时长、状态，都必须能在论文文本里逐字找到，并挂一个 `verbatim_quote` 子串供回溯核对。
- **`verbatim_quote` 是论文原文子串**，不改写、不翻译、不概括。核验方式：该 quote 应能在 OA 全文 / 摘要里做字符串 `contains` 命中。
- **药名 / 方案 / 基因 / 变异永不翻译、永不归一**（不把 `osimertinib` 写成"奥希替尼"，不把 `L858R` 展开成解释）。
- **一个没有 backing quote 的值 = 一个编造的数据点 = 禁止写入**。宁可标 `未报告`，不要填一个凑出来的值。
- 抽取器**不接触 `raw/` 原始上传件**，只读检索命中的论文文本（`../../references/safety-guardrails.md`）。

## 3. `未报告` rule

- 论文**没写**的字段一律标 `未报告` —— 不猜、不推、不用先验知识补。
- **禁止跨字段推断**：不得从治疗反推结局（"用了三线还活着 → 结局好"），也不得从结局反推治疗强度。`treatment_path` 与 `outcome` 各自独立、各自有据。
- `prior_lines_count`、`intent`、`started_relative`、`best_response`、`followup_duration`、`status` 任一没有明确文本支撑 → `未报告`，并加入 `missing_fields[]`。
- `未报告` 是脚手架标记，可按 locale 渲染同义词；但它标记的位置由"论文有没有写"决定，与语言无关。

## 4. No synthesis rule

抽取器是**搬运工，不是分析师**（对齐 `../../references/safety-guardrails.md` → 禁 LLM 合成证据）：

- ❌ 不计算预后、不估生存期、不算任何"率"（有效率/缓解率/生存率——个案不可聚合，见 SKILL G-NO-AGGREGATE）。
- ❌ 不泛化（"这类患者通常…"）、不外推到本人。
- ❌ 不添加论文里没有的数字（不换算月/年、不折算剂量、不补 RECIST 码）。
- ✅ 只做：定位论文陈述 → 逐字摘出 → 填进对应字段 + 附 `verbatim_quote`。
- 结局矛盾/含糊（论文自身表述不清）→ 照实标 `未报告` 或原样引用，不替论文"修正"。

## 5. 抽取样例（EGFR NSCLC，虚构但写实）

> 仅示范字段填法与 `verbatim_quote` / `未报告` 用法；PMID 与引文为演示占位，非真实文献。

```jsonc
{
  "case_id": "case-01",
  "pmid": "39001234",
  "source_url": "https://pubmed.ncbi.nlm.nih.gov/39001234/",
  "oa_fulltext_available": true,

  "patient_descriptors": {
    "age": "67",
    "sex": "female",
    "primary": "non-small cell lung cancer",
    "histology": "adenocarcinoma",
    "stage": "IV",
    "drivers": [
      {"gene": "EGFR", "variant": "L858R",
       "verbatim_quote": "molecular testing revealed an EGFR L858R mutation"},
      {"gene": "EGFR", "variant": "T790M",
       "verbatim_quote": "repeat biopsy at progression showed an acquired EGFR T790M mutation"}
    ],
    "prior_lines_count": 2
  },

  "treatment_path": [
    {"line": 1, "regimen": "gefitinib", "intent": "palliative",
     "started_relative": "at diagnosis",
     "verbatim_quote": "She was started on first-line gefitinib at the time of diagnosis."},
    {"line": 2, "regimen": "osimertinib", "intent": "palliative",
     "started_relative": "after first-line progression",
     "verbatim_quote": "Upon progression, treatment was switched to osimertinib 80 mg daily."}
  ],

  "outcome": {
    "best_response": "PR",
    "followup_duration": "18 months",
    "status": "未报告",
    "verbatim_quote": "A partial response was observed, sustained through 18 months of follow-up."
  },

  "extraction_confidence": "high",
  "missing_fields": ["outcome.status"]
}
```

说明：`outcome.status` 标 `未报告` —— 论文只写了 18 个月随访仍有 PR，**没有**明确写患者 alive/deceased/NED，抽取器**不从"仍有缓解"推断"存活"**（§3 禁跨字段推断），照实留空并记入 `missing_fields`。

## 6. `extraction_confidence` 定级

| 档 | 判据 |
|---|---|
| `high` | 抽自 OA 全文；治疗线与结局字段大多有明确逐字引文；`missing_fields` 少 |
| `medium` | 只有摘要，或全文但部分关键字段（如 `best_response`/`status`）需从零散句子拼读 |
| `low` | 信息稀薄（仅标题+短摘要）、字段大量 `未报告`、或论文表述含糊难逐字定位 |

`low` 条目仍可入清单，但在 PRECEDENTS.md 里须显式标证据薄弱（对齐 SKILL G-GROUNDING / G-TIER）。
