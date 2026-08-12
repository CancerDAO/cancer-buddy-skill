---
name: cancer-buddy-organize
description: "Organize patient medical records into a provenance-preserving patient directory. Produces source-attributed summaries and schema-validated JSON while keeping source-reported, patient-reported and normalized layers separate. It does not infer diagnosis, stage, ECOG, response, progression, treatment line, prognosis or testing indications. Triggers on 病历整理, 整理报告, organize medical records."
---

# cancer-buddy-organize（Kimi 专用变体 · lite 产物档位）

> 本分支（`kimi/organize-lite`）是主线的**派生变体**：唯一入口、无绑定选择。行为底线
> （[`references/organize-contract.md`](references/organize-contract.md)：来源保真、红线字段、
> 三道确定性门）与主线共享同一份文件——**改契约/门请去主线分支，勿在本分支改**。
> 判断留 prompt（转录/归类/命名），验证与簿记留脚本（转码/hash/ID/门/对账）。

把原始病历变成结构化档案。只抽取和组织，不做临床推断：不诊断、不重算分期/ECOG/疗效/
进展/治疗线/预后。看不清就标注不确定，**绝不猜**。

## Step 0 — 建档 + 确定性前置（零 LLM，先跑再说）

```bash
code="PT-$(openssl rand -hex 5 | tr a-f A-F)"
root="${CANCER_BUDDY_PATIENTS_DIR:-$HOME/CancerDAO/patients}"
patient_dir="$root/$code"; mkdir -p "$patient_dir"
bash <skill_dir>/scripts/phase0_prepare.sh "$patient_dir" <每个输入目录...>
```

`phase0_prepare.sh` 一次完成：原件 sha256 入 `raw/`、HEIC/PDF 批量转码到
`.staging/rasters/`、**预分配全部 `source_id`（`SRC-<hash12>`）写进
`phase0_manifest.json`**。后续所有环节只用 manifest 里的 ID，任何 worker 不得自造 ID。
manifest 里 `status != ok` 的来源是 blocked（转不动/不支持），保留在清单里，最终报告
必须如实列出——绝不静默跳过。

> **打点纪律（每步都做）**：每个 Step 结束时执行
> `echo "step<N> $(date +%H:%M:%S)" >> "$patient_dir/.run_timing.log"`——
> Step 5 的交付报告必须引用这份文件报各步耗时，不得凭印象。

## Step 1 — 逐字转录（视觉，小切片并行）

把 manifest 里 `status: ok` 的来源按 **6–8 个/组** 切片（宁多组、勿大组：切片大小 =
宿主后台任务超时预算的一半，超时重跑是最贵的失败模式）。每组派一个 subagent，其
prompt = **[`references/runtime-bindings/kimi-phase1-worker-card.md`](references/runtime-bindings/kimi-phase1-worker-card.md)
全文内嵌** + 该组的 manifest 行（source_id / raw_path / raster_paths）+ patient_dir。
worker 除卡片外不读任何其它文件；逐个处理、每完成一个立即写盘。

全组返回后，对账：`ls ocr/*.md` 数量必须 == 派发数。缺的重派**只缺的那几个**（小重派，
不整组重跑）。

## Step 2 — 定向第二读（只复读高危页）

```bash
python3 <skill_dir>/scripts/highrisk_page_filter.py "$patient_dir" --dir ocr
```

对筛出的每个高危来源（含药名/剂量/分期/化验值/标识——化验单会全中，正常）派一次轻量
视觉比对：重新看 raster，逐项核对 sidecar 里的高危值。不一致的行改标
`[uncertain: 甲|乙]` 并在 sidecar 末尾「不确定项」登记。
**worker 只返回核对结果 JSON，不写共享文件**——编排层收齐后统一合并写
`$patient_dir/high_risk_review.json`（`{"values": {"<sidecar相对路径>": {"<裸数字>": "verified_by_second_read"}}}`），
避免并发写冲突。**第二读只核对不改判**：两读不一致时保留两个候选标不确定，不选边。

## Step 3 — 逐源归类命名（每个 sidecar 一次轻调用）

对每个 sidecar 单独发一次小调用（**逐源，不批量**——批量归档会串位）：输入 = 该 sidecar
全文 + [`references/bucket-taxonomy.md`](references/bucket-taxonomy.md)；**worker 只返回**
`{"path": "NN_桶/子类/YYYY-MM-DD_报告类型_机构_来源<source_id>.md"}`，
**文件移动由编排层确定性执行**（worker 不动文件系统）。
命名铁律：文件名报告类型段**逐字取自该 sidecar 自己的报告类型声明**；sidecar 写的是
unknown → 归 `14_患者自管补充/患者补充/待归类资料_<source_id>.md`，不得冠具体类型名；
日期段取该文档自己的记录/报告日期，sidecar 内无记录日期时用页内唯一所见日期并在
INDEX.md 说明。全部移动完成后跑 G1 校验：

```bash
python3 <skill_dir>/scripts/gates/gate_name_content.py "$patient_dir"
```

violation 的文件改移待归类（不得以错名落盘），unknown 只记录不阻塞。

## Step 4 — 综合（三层：确定性 → 并行提取 → 串行收尾）

综合阶段对**已归好桶**的档案工作，任何一层都**不改文件名、不移动文件**——归类命名已在
Step 3 定稿。冲突并列保留标 `disputed`，不裁决。schema 与字段规则见
[`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md)。

### 4a 确定性件（零 LLM，先跑）

```bash
python3 <skill_dir>/scripts/build_inventory_index.py "$patient_dir" --run-mode full
```

生成 `source_inventory.json`（全字段从 manifest+落位推导，source_id 逐字来自 manifest）、
`INDEX.md` 骨架、`update_log.json` 追加。这些是簿记，不花模型调用。脚本报
`missing_sidecars` 非空 = 覆盖有洞，先回 Step 1 补齐再继续。

### 4b 并行域提取器（一次全部派出，互不等待）

| worker | 产物 | 喂什么（桶已分好，别多喂） |
|---|---|---|
| labs | `labs.json` | 只喂 `07_检验/` 各 sidecar |
| molecular | `molecular.json` | 只喂 `08_基因与分子/`（缺桶则喂含分子内容的叙事桶） |
| comorbidities | `comorbidities.json` | 只喂 `03_病程与叙事文书/` |
| treatment_lines | `treatment_lines.json` | 只喂 `03_病程与叙事文书/` + `04_治疗/` |
| timeline | `timeline.md` + `timeline.json` | 全档 sidecar（跨文档产物） |
| case_text | `case_text.md` | 全档 sidecar（跨文档产物） |
| patient_summary | `patient_summary.json` + `profile.json`（locale 从病历主语言检测） | 全档 sidecar |

每个 worker 独立读 schema 中与自己相关的部分；并行的代价是跨产物小不一致的可能——
一致性由 4c 审计与 validator 兜底，不靠单体自洽。

### 4c 串行收尾（等 4b 全齐）

`missing_items.json`（对照 checklist 只列文档缺口）→ review_flags 审计 →
`review_flags.md`（非空时）+ `review_summary.md`（必写）→ INDEX.md 追加叙事注释。
审计范围包括 4b 产物之间的交叉一致性（如 timeline 与 treatment_lines 的日期冲突）。

### 4d 段D 病情简要总结 HTML（患者可见交付物，不可省略）

按 [`references/case-summary-html-prompt.md`](references/case-summary-html-prompt.md)：
派一个 subagent 组装 `case_summary_data.json`（只读脱敏 JSON），然后**确定性渲染**——
`backfill_lab_trends.py` → `compute_version_delta.py` → `compute_sparklines.py` →
`render_html_template.py` → `validate_case_summary_html.py`，fail-closed：subagent 必须
返回 `{status:"ok", template_sha:"<64-hex>"}` 才算完成，绝不接受手写 HTML 或无
`template_sha` 的"done"声明；`status:"failed"` 就重派。产物为
`$patient_dir/病情简要总结.html`。

## Step 5 — 验收与交付报告

1. 覆盖对账（确定性）：manifest 全部 source_id 都能在桶内或待归类中找到 sidecar；
   blocked 清单如实列出。
2. 门已绿：G1 无 violation 残留；若本次涉及再上传对账候选，出卡前跑
   `gates/gate_same_test.py`（同检验双载体不出冲突卡）与 `gates/gate_candidate_binding.py`
   （卡上数值未经绑定验证的一律「数值待核对」）。
3. 产物齐全性（确定性 ls 核对，缺一即未完成）：Step 4 全部 JSON/MD +
   `case_text.md` + `病情简要总结.html`（带 Step 4d 的 template_sha 凭证）。
4. 向用户交付：档案位置、各桶清单、待归类/blocked/不确定项数量、review_summary 要点、
   **各步耗时（读 `.run_timing.log`，不凭印象）**。
   **失败也如实报**：哪些没读出来、哪些标了不确定，不藏。

## 中间产物保留（lite 档，与平台策略的刻意差异）

- **`raw/` 原件与 `.staging/` 转码图：永久保留在档案内。** 自动删原件是平台的服务器端
  隐私策略（不留明文 PII）；个人单机场景是本人设备上本人的数据，保留原件才是对的——
  将来复读、重归类、换引擎重跑都靠它们。
- **`ocr/` 不留副本**：sidecar 在 Step 3 是*移动*进桶（内容零丢失，只换位置），归类后
  ocr/ 应为空并删除。同一份 sidecar 绝不两处存放——双源必漂移。
- 可选调试快照（默认关）：需要"归类前状态"时，Step 3 移动前
  `cp -R ocr/ .staging/ocr-snapshot/`，快照只读、不是真相源、不参与任何后续步骤。

## Role behavior

角色与授权按 [`../../references/roles.md`](../../references/roles.md) 与
[`../../references/disclosure-behavior.md`](../../references/disclosure-behavior.md)：

- `role=patient`（患者本人）：完全访问自己的档案与全部产物。
- `role=caregiver`（照护者）：仅在明确、可撤销、限用途的授权范围内访问；授权范围之外的
  桶/产物不读不引不概括。
- `role=family`（家属）：亲属关系本身**不授权**——未经患者明确授权按无权限处理，只能得到
  一般性、非本人档案的教育内容。

不可逆动作（删除/替换/字段更正）无论角色，一律走共享确认门
[`../../references/confirm-gate.md`](../../references/confirm-gate.md)：逐项明确确认，
沉默不删，替换留底。

## 安全与共享契约（与主线一致，lite 档不豁免）

- 安全边界：[`../../references/safety-guardrails.md`](../../references/safety-guardrails.md)
  （含症状急迫性路由——整理资料不得拖延就医）。
- **文本脱敏（text masking / desensitization）**：Phase-1 写盘前完成 PII 遮蔽——姓名/
  证件号/病案号/检验编号/电话/住址遮蔽主体、保留末位后缀。**遮蔽只针对 PII，临床字符
  一律原样保留**（数值/单位/参考范围/诊断/日期不动，防锚点漂移 anti-anchoring）；
  **MD sidecar 是下游唯一读取源，任何下游环节不得回读含明文 PII 的原件**（原件只留在
  访问受控的 `raw/`）。遮蔽不等于匿名化，导出前须提醒。
- 语言与本地化：[`../../references/i18n.md`](../../references/i18n.md)（源临床字符串
  verbatim 不翻译；患者可见解释按 locale 渲染）。
- 引用与证据分级（review_summary 等涉及外部资料时）：
  [`../../references/citation-format.md`](../../references/citation-format.md)、
  [`../../references/evidence-trust-tiers.md`](../../references/evidence-trust-tiers.md)、
  [`../../references/reference-library.md`](../../references/reference-library.md)。
