# 上传文件相关性门

相关性分类用于路由，不用于自动删除。

## 分类

- `medical_or_administrative`: 病历、影像、药盒/处方、症状/伤口照片、设备、费用、保险、转诊、给药和预约资料；
- `possibly_relevant`: 内容不清、截断、低质量或模型不确定；
- `likely_unrelated`: 明显生活内容，但仍需用户确认。

## 行为

- 前两类默认保留并归档进临床域桶；**不进隔离区**。`possibly_relevant` 进复核队列（问用户），
  不是隔离，也**不进 `15_未分类资料/`**（见 §`possibly_relevant` 的落位）。
- **只有 `likely_unrelated` 才进 `99_无关文件/`**（`high_confidence/` `uncertain/` 两个子目录）。
  展示文件名、缩略图和原因；用户逐项明确确认后才删除。
- 沉默、关闭、延期、“随便”都等于不删除。
- 任何删除记录 actor、时间、文件 hash、预览、确认文本和结果。
- 不用关键词/模型置信度声称某张皮疹、药盒、账单或行政资料“无临床价值”。

## `novel` ≠ 隔离（不要把「不认识」当成「无关」）

一份医疗/行政材料**不属于任何已知 `doc_kind`**，这是**分类缺口**，不是相关性判断。
它的去处是开放桶 `15_未分类资料/<slug>/`（`kind: novel` + `novel_reason` +
`clinical_class`），**不是 `99_无关文件/`**。

| 情况 | 缺口类型 | 去处 | inventory `kind` | 会被删吗 |
|---|---|---|---|---|
| 已知类型的医疗/行政材料 | 无 | `01_…14_` 对应桶 | `known` | 否 |
| 医疗/行政材料，但类型不在 taxonomy 里 | **类型缺口** | `15_未分类资料/<slug>/` | `novel` | **永不自动删** |
| 内容不清/截断/低质量/模型不确定 | **质量缺口** | **最佳匹配的 `01_…14_` 桶**（拿不准用该桶的 `其他/`） | `unreadable` | 否 |
| 明显生活内容（自拍、风景、外卖截图…） | — | `99_无关文件/` | — | 只在用户逐项确认后 |

## `possibly_relevant` 的落位：留在最佳匹配的临床桶，不进 `15_`

**`15_未分类资料/` 只收 `kind: novel`。** 这两个缺口是**正交**的，别混：

| | 类型缺口（`novel`） | 质量缺口（`possibly_relevant` → `unreadable`） |
|---|---|---|
| 问的是什么 | 「这是**什么**类型的材料？」taxonomy 里没有这种抽屉 | 「这张纸上**写了什么**？」看不清 / 截断 / 低质量 / 模型不确定 |
| 去处 | `15_未分类资料/<slug>/` | **最佳匹配的 `01_…14_` 桶**（含该桶 `其他/` 兜底） |
| `kind` | `novel`（+ `novel_reason` ≥ 8 字符） | `unreadable` |
| review flag | 不必然有 | **必有**：`category: coverage_gap`，`audience: internal_qc` |

一张糊掉的化验单**仍然是化验单**——它进 `07_检验`，`kind: unreadable`，带一条
`coverage_gap` / `internal_qc` 的 flag，不是「类型不明」。把它塞进 `15_` 会让
「我们不认识这种报告」和「我们没看清这张纸」两种完全不同的缺口在下游无法区分，
并让 `15_` 从开放档案退化成低质量堆场。

**gate（`validate_structured_outputs.py` 强制）：**

1. `15_` 下每个 sidecar 对应的 inventory 行必须 `kind == novel`，且 `novel_reason` ≥ 8 字符；
2. 任何 `kind: novel` 的行，其 sidecar 必须在 `15_` 下。

两条都是双向绑定，任一不满足即 ERROR。

`15_` 是**开放档案**，不是隔离区、不是垃圾桶、不是待删队列。它照常被转写、照常有遮蔽版 MD、
照常有 inventory 行、照常进 `projection_coverage`；下游按 `clinical_class` 决定要不要读它
（`15_` 不可 anchor，开放字段走 `extracted_fields.json` 的 `open_ref`）。

把 novel 材料丢进 `99_` 是一个**会导致临床材料被删**的分类错误——`99_` 的唯一语义是
「这很可能不是医疗材料」。拿不准是不是医疗材料时选 `possibly_relevant`（保留 + 问），
不选 `likely_unrelated`。

执行共享 `../../../references/confirm-gate.md`（skill 根目录的共享库，不是本 skill 的 `references/`）。
