# Similarity axes（6 维相似度规则）

Step 4 用这个把患者的 `similarity_profile`（Step 1 的 QUERY.md）和每一个命中的个案（Step 3 抽取产物）逐维对照。产出**不是**一个「有多像」的分数，而是一张**逐维 match / partial / mismatch / unknown 的透明对照表**——**相似在哪、更重要的是分歧在哪**。

**这不是医学推荐，是线索匹配度。** 一个表面很像、却在关键驱动上分歧的病例，如果被当成「和你一样的人」呈现，是临床误导（见 G-SIMILARITY-TRANSPARENCY / G-NO-ADVICE）。

## 判定方式 = LLM sub-prompt，**不是硬编码打分表**（P0）

每一维的档位由 **LLM sub-prompt 判断**，读患者 `similarity_profile` 的这一维 + 病例抽取的对应字段，输出 `{axis, verdict, rationale}`。

- ❌ **禁止**写 `keyword → score` 的硬编码映射表 / Python 关键词字典 / 固定权重求和。生物学等价性（例如「同基因不同变异是否算像」）需要**领域判断**，不是字符串匹配能覆盖的。
- ✅ 每维 verdict **必须**带**一句理由**（rationale），说清为什么判 match / partial / mismatch，理由里引具体临床实体（逐字，禁译）。
- 判据模糊 / 病例未报告该维 → 判 `unknown`，理由写「病例未报告 X」，**不猜**。

派 subagent 判定时在 prompt 写明：`Output verdict rationale in <locale>; keep clinical entities (gene/variant/TNM/stage/drug/histology) verbatim.`

## 6 维定义与判据

| 轴 | 对比什么 | match | partial | mismatch | unknown |
|---|---|---|---|---|---|
| **primary**（癌种） | `summary.primary` ↔ 病例原发癌种 | 同一原发癌种 | 同器官系统 / 强相关癌种（如同为肺原发的不同大类）| 不同器官原发 | 病例未写原发 |
| **histology**（组织学） | `diagnosis.histology` ↔ 病例组织学亚型 | 同一组织学亚型 | 相关亚型（同大类不同细分）| 完全不同组织学 | 病例未报告组织学 |
| **stage**（分期/范围） | `diagnosis.stage` ↔ 病例分期/播散范围 | 同分期 / 同播散范围 | 相邻分期（如 III vs IV 局部 vs 远处早段）| 差距很大（如 I vs IV）| 病例未报告分期 |
| **key_driver**（关键驱动） | `key_drivers[]`（gene+variant, 逐字 HGVS）↔ 病例可靶向驱动 | 同基因**且同变异**（biology 一致）| **同基因不同变异**（如 EGFR L858R vs T790M vs exon20ins）—— biology 不同故判 partial，**非 match** | 不同基因 / 无共享驱动 | 病例未报告分子/NGS |
| **treatment_line**（治疗线情境）| `treatment_lines[]` 推出的线数情境 ↔ 病例当时线数 | 同一 line-of-therapy 情境（如都是 3L 进展后）| 相近线数（如 2L vs 3L）| 差距大（如初治 1L vs 多线难治）| 病例未交代治疗线 |
| **key_comorbidity**（关键合并症）| `key_comorbidities[]` ↔ 病例合并症 | 共享临床相关合并症（糖尿病 / 肾功能 / 心脏）| 有合并症但类别不同 | 无共享 / 病例无合并症负担 | 病例未报告合并症 |

**key_driver 的 partial 规则是本 skill 最容易被误读的地方**：同一基因不同变异（同 EGFR，但一个 L858R、一个 exon20ins）驱动生物学与可用药物都不同，**必须判 partial 并在 rationale 里点明变异差异**，绝不因「同基因」就升成 match——否则会把一个用药逻辑完全不同的病例伪装成「和你一样」。

## 分歧必须显式列出（P0 — G-SIMILARITY-TRANSPARENCY）

- 输出**不能只列 match 的维**。`partial` 和 `mismatch` 的维**同等重要**，必须**显式列出并给理由**。
- 每条个案的呈现里都要有一句「**这个病例和你不同的地方**」，把 partial / mismatch 的轴摆出来。
- `unknown` 也要列——「病例没报告这一维，无法对照」本身就是给患者和医生的信息。

## 排序与呈现（不把总分当主信号）

- **可以**按整体接近度给病例排个序（大致 match 多、关键维一致的排前），方便浏览。
- **不得**把一个「综合相似度分数 / 百分比 / N/6」当作主视觉或主标题——那会诱发「最像 = 我就该照着治」的误读（G-NO-ADVICE / NO-PROGNOSIS）。
- **主视觉是逐维对照表，不是数字**。若要表达接近度，用档位词（高度相似 / 部分相似 / 关键维分歧），按 `locale` 渲染，临床实体逐字不译。
- 用「匹配理由」措辞，不用「推荐理由」。

## worked example

**患者 `similarity_profile`**（来自 QUERY.md）：

```yaml
primary:        非小细胞肺癌
histology:      腺癌
stage:          IV
key_drivers:    [EGFR L858R, T790M]
treatment_lines:
  - {line: 1, regimen: Osimertinib, best_response: PD}
  ...（进展至三线）
key_comorbidities: []
```

**候选病例**（Step 3 抽取）：EGFR exon20ins 的非小细胞肺癌腺癌，IV 期，当时处于 2L；合并 2 型糖尿病。

6 维对照：

| 轴 | 患者 | 病例 | verdict | rationale（一句） |
|---|---|---|---|---|
| **primary** | 非小细胞肺癌 | 非小细胞肺癌 | **match** | 同为非小细胞肺癌原发。 |
| **histology** | 腺癌 | 腺癌 | **match** | 均为腺癌亚型。 |
| **stage** | IV | IV | **match** | 均为 IV 期远处转移。 |
| **key_driver** | EGFR L858R + T790M | EGFR exon20ins | **partial** | 同为 EGFR 基因，但变异不同（L858R/T790M vs exon20ins）——可用药与耐药生物学不同，故非 match。 |
| **treatment_line** | 3L 进展后 | 2L | **partial** | 线数相近但不同情境（患者 3L 难治 vs 病例 2L），治疗压力与既往暴露不一致。 |
| **key_comorbidity** | 无 | 2 型糖尿病 | **mismatch** | 病例带糖尿病合并症，患者无——耐受性/用药限制不可直接类比。 |

**呈现给患者时必须点明的分歧**：`key_driver` 是 partial（EGFR **exon20ins ≠ 你的 L858R/T790M**，别的病例用的药未必适用你）、`treatment_line` partial、`key_comorbidity` mismatch。癌种/组织学/分期三维一致会让这个病例「看起来很像你」，但**关键驱动的变异差异**决定了它的治疗路径**未必迁移到你身上**——这正是必须把分歧摆到台面上的原因。
