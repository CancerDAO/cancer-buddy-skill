---
name: cancer-buddy-organize
description: "Organize patient medical records into a provenance-preserving patient directory. Produces source-attributed summaries and schema-validated JSON while keeping source-reported, patient-reported and normalized layers separate. It does not infer diagnosis, stage, ECOG, response, progression, treatment line, prognosis or testing indications. Triggers on 病历整理, 整理报告, organize medical records."
---

# cancer-buddy-organize（Kimi / Codex lite）

把一个病历文件夹整理成可追溯的患者档案。只转录、归类和汇总来源明确写出的事实；不诊断，
不重算分期、ECOG、疗效、进展、治疗线或预后。看不清就标不确定，绝不猜。

这是开放编排，不是调度 runtime。全程只有一个 `patient_dir` 和一个固定 `run_id`；不要在
恢复、复扫或重试时重新建患者或 run。任何模型单元最多重试一次，且只重试缺失/失败单元。

## Step 0 — 建档并固定 run（零 LLM）

```bash
python="${CANCER_BUDDY_PYTHON:-python3}"
if ! "$python" -c 'import jsonschema; from jsonschema import Draft202012Validator' 2>/dev/null; then
  for candidate in "$HOME/anaconda3/bin/python3" "$HOME/miniconda3/bin/python3"; do
    if [ -x "$candidate" ] && "$candidate" -c 'from jsonschema import Draft202012Validator' 2>/dev/null; then
      python="$candidate"; break
    fi
  done
fi
"$python" -c 'from jsonschema import Draft202012Validator' || exit 1
code="PT-$(openssl rand -hex 5 | tr a-f A-F)"
root="${CANCER_BUDDY_PATIENTS_DIR:-$HOME/CancerDAO/patients}"
patient_dir="$root/$code"
mkdir -p "$patient_dir"
run_json="$("$python" <skill_dir>/scripts/run_context.py start "$patient_dir")"
run_id="$(printf '%s' "$run_json" | "$python" -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')"
bash <skill_dir>/scripts/phase0_prepare.sh "$patient_dir" <每个输入目录...>
run_dir="$patient_dir/.staging/runs/$run_id"
```

`run_context.py start` 对 active run 只会返回同一个 `run_id`；调用失败就停止，不能另造 run
绕过。`phase0_manifest.json` 中 `status != ok` 的来源记为 blocked，保留但不派视觉 worker。
所有后续 ID 逐字使用 manifest 的 `source_id`；若 manifest 有 `file_id`，以 `file_id` 为稳定
内容键，否则 lite 的 1:1 来源用 `source_id`。

**HEIC 派生光栅契约**：HEIC/HEIF 源（iPhone 直出病历照片的主流格式）在 phase0 转码时
必须同时产出 JPEG 派生光栅（`.staging/rasters/<source_id>/page1.jpg`），供 Step 2 高危
字段二读与争议复核使用；生命周期与 `.staging/` 一致（lite 档永久保留）。任何链路不得因
"原格式不是位图"而跳过 HEIC 源的二读——没有可用光栅的 HEIC 高危源是覆盖缺口，不是
`no_raster` 跳过项。

## Step 1 — 小切片并行转录 + Phase-1 PII 门

把可读来源按每组 **3–4 件**切片，最多同时派 3 个 worker。先把本轮所有 worker 派出，再
等待；不要派一个等完再派下一个。每个 prompt 只含：

- [`references/runtime-bindings/kimi-phase1-worker-card.md`](references/runtime-bindings/kimi-phase1-worker-card.md) 全文；
- 本组 manifest 行（`source_id/raw_path/raster_paths`）、`patient_dir`、`slice_id`。

worker 每完成一件立即写 `ocr/<source_id>.md`。全部返回后，按 manifest 精确对账；缺件只重派
缺失 ID 一次。可读来源数与 sidecar 数仍不一致就停止，不能进入 Step 2。

先跑确定性形状门：

```bash
"$python" <skill_dir>/scripts/pii_rescan.py "$patient_dir"
```

再执行一次语义 PII 门。先创建冻结 scope：

```bash
"$python" <skill_dir>/scripts/semantic_pii_gate.py scope "$patient_dir" \
  --run-id "$run_id" --stage phase1 --pass before
```

派一个独立 reviewer，只给它该命令返回的 `scope_path/report_path` 与
[`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md)。reviewer 只读 scope
列出的文本，只写 report。随后 `validate-report`：

- 若第一次报告 `clean=true`：直接 `record-clean`，不调用 `apply`；
- 若有 findings：调用 `apply` 做固定 `[PII_MASKED]` 精确替换，再创建同一 `run_id` 的
  `--pass after` scope，重新派一次 clean reviewer，`validate-report --require-clean` 后
  `record-clean --corrections <apply 返回的 receipt_path>`；
- 报告格式错误只允许在同一冻结 scope 重派一次；仍失败就停止。

最后必须重新跑 `pii_rescan.py`，并通过：

```bash
"$python" <skill_dir>/scripts/semantic_pii_gate.py check "$patient_dir" --stage phase1
```

## Step 2 — 高危页独立第二读（稳定 ID）

```bash
"$python" <skill_dir>/scripts/highrisk_page_filter.py "$patient_dir" --dir ocr \
  --json "$run_dir/high_risk_filter.json"
```

对 `high_risk[]` 每个来源单独派一次视觉复读，最多 3 个并发；worker 只返回 JSON，不写共享
文件。核对药名/剂量/频次、分期串、化验值/单位、分子结果和标识遮蔽。两读不一致不选胜者，
把该来源设为 `needs_human_review` 并在 values 中只记录已确认的临床值；本步骤不改 sidecar
字节。标识复核的 key 只写 `identifier:<字段名>`，value 仍写下述复核状态；绝不把原始姓名、
号码或地址写进 ledger。

编排层一次写 `high_risk_review.json`：

```json
{
  "schema": "high_risk_review_v2",
  "sources": {
    "<file_id；没有则source_id>": {
      "file_id": "<可选>",
      "source_id": "<SRC-...>",
      "sidecar_path": "ocr/<source_id>.md",
      "status": "not_applicable | passed_independent_reread | needs_human_review",
      "values": {"<已确认临床值或identifier:字段名>": "verified_by_second_read"}
    }
  }
}
```

每个可读来源必须恰有一条：筛选未命中写 `not_applicable`；完整独立复读才可写
`passed_independent_reread`；部分、超时或冲突一律 `needs_human_review`。路径只是审计属性，
后续查找只用稳定 ID。

## Step 3 — 逐源归类命名

每个 sidecar 单独发一次轻调用；输入是该 sidecar 全文与
[`references/bucket-taxonomy.md`](references/bucket-taxonomy.md)。worker 只返回：

```json
{"path":"NN_桶/子类/YYYY-MM-DD_报告类型_机构_来源<source_id>.md"}
```

编排层验证路径属于 taxonomy 后再移动；worker 不动文件系统。报告类型逐字取自该 sidecar；
unknown 固定落 `14_患者自管补充/患者补充/待归类资料_<source_id>.md`。日期缺失就保留 unknown，
不拿别的文档日期补——**唯一例外是多页文书归组**（下述）。

### 多页文书归组（首页日期/机构继承）

一份多页文书常被拆成多个源文件（如入院记录 2 页 = 2 张图），而**只有首页有完整页眉**
（日期/机构/文书类型）。后续页 sidecar 若已诚实标注「本页未见明确记录日期」，归类时
**不得**以"日期未知"落待归类，而应按确定性规则归组继承：

1. 归组键：同机构 + 同文书类型声明 + 页码/时间连续性（如文件名序号相邻、sidecar 页脚
   页码 `第 N 页/共 M 页`、采样时间同日相邻）。
2. 组内非首页继承组头的**记录日期与机构**；sidecar 与 INDEX.md 中注明
   `归组继承自 <组头 source_id>`，不伪造成本页所见。
3. 不满足归组键的（机构/类型对不上、页序断档）仍按原规则落 unknown——归组不裁决
   不相干文档。

全部移动后删除空 `ocr/`，并运行：

```bash
"$python" <skill_dir>/scripts/gates/gate_name_content.py "$patient_dir"
```

violation 移回待归类；不要错名硬过门。

## Step 4 — 简单并行 DAG

先生成确定性 inventory/INDEX，并验证 DAG：

```bash
"$python" <skill_dir>/scripts/build_inventory_index.py "$patient_dir" --run-mode full
"$python" <skill_dir>/scripts/plan_phase4.py --validate-only
```

然后循环调用：

```bash
"$python" <skill_dir>/scripts/plan_phase4.py "$patient_dir" \
  --run-id "$run_id" --available-slots 3
```

只执行本次返回的 `ready[]`；该批全部结束后再 replan。`llm_worker` 使用
[`references/runtime-bindings/phase4-worker-cards.md`](references/runtime-bindings/phase4-worker-cards.md)
对应小节和任务列出的桶/输入/`schemas`，并把任务里的 `python_executable` 原样交给 worker；
worker 校验产物只能调用该绝对路径，不得用裸 `python` / `python3`。每个文件只有一个 owner。`deterministic` 执行 planner
返回的 `commands` 或 `procedure`。失败只重派该 task 一次。

每一批结束后、replan 之前先运行 progressive validator：

```bash
"$python" <skill_dir>/scripts/validate_structured_outputs.py "$patient_dir"
```

若它指出本批 JSON/schema/source-ref 失败，该 task 不算完成：把该 task 本轮拥有的输出移到
`$run_dir/failed-phase4/<task_id>/` 留存，按同一 schema 只重派该 owner 一次；canonical 中仍有
无效非空文件时不得 replan。这样 planner 的“非空文件=完成”只接收已经过门的文件。

并行规则是硬约束：

- Wave A：`labs / comorbidities / missing_items` 三个必须全部派出后才等待；
- Wave B：`molecular / treatment / patient_summary / timeline / case_text` 按空闲槽位派满后等待；
- `molecular` 只读稳定桶前缀 `06_`；`treatment` 只读 `03_/08_/09_`；
  `comorbidities` 只读 `02_/03_`；
- `patient_summary` 只写 `patient_summary.json`；`profile.json` 由 `build_profile.py`
  确定性生成；
- `readiness.json/review_summary.md` 后置；模型只写 `.case_summary_data.json`，HTML 由模板
  确定性渲染；
- source-ref 合同统一：JSON 只写现存 `01_…14_` 桶内相对 sidecar 路径（可带 fragment）；
  正式 Markdown 每个引用 token 必须是 `[[src:<相对路径>#<fragment>]]`。禁止绝对路径、
  反斜线、`.`/`..`、`raw/ocr/99_` 和悬空引用。

HTML task 按 planner procedure：复制 `.case_summary_data.json` 到患者目录外的临时文件，
依次运行 `backfill_lab_trends.py`、`compute_version_delta.py`、`compute_sparklines.py`，再用
`render_html_template.py` + `case-summary.template.html` 生成 `病情简要总结.html`，最后用
`validate_case_summary_html.py --html --template --profile --data` 验证。不得手写 HTML。

DAG 最后一个 task 是 `finalize_log`：只在 Phase 4 其余产物齐全且 Phase-1 PII receipt 存在
时，以固定 `run_id` 写 `update_log.json`。此时 DAG complete；还不能向用户宣称完成。

## Step 5 — 最终 PII、严格验收、完成 run

在所有最终产物（包括 `update_log.json`）写好以后，先跑：

```bash
"$python" <skill_dir>/scripts/pii_rescan.py "$patient_dir"
```

再按 Step 1 的同一分支执行 final semantic gate：`scope --stage final --pass before`；初次 clean
就直接 `record-clean`，有 findings 才 `apply` → 同一 `run_id` 的 after scope → clean rescan →
`record-clean --corrections ...`。随后必须通过：

```bash
"$python" <skill_dir>/scripts/pii_rescan.py "$patient_dir"
"$python" <skill_dir>/scripts/semantic_pii_gate.py check "$patient_dir" --stage final
"$python" <skill_dir>/scripts/validate_structured_outputs.py --require-complete "$patient_dir"
"$python" <skill_dir>/scripts/gates/gate_name_content.py "$patient_dir"
"$python" <skill_dir>/scripts/run_context.py complete "$patient_dir" --run-id "$run_id"
```

最终 PII scope 创建以后，除 `.organize_run.json` 的完成状态外不得再写交付产物；否则 receipt
会因 membership/hash 变化失效。任一门失败、必需产物缺失或 run 仍 active，都只能报告
“未完成”，不能假绿。

向用户只报告：档案位置、来源/blocked/待归类/needs-human 数量、各阶段真实耗时和失败单元；
不要在消息中回显 PII 或病历原文。

## Role behavior

- `role=patient`：患者本人可在当前任务授权范围内整理自己的档案。
- `role=caregiver`：只处理患者明确、可撤销、限用途授权的文件与产物。
- `role=family`：亲属关系本身不构成授权；没有患者明确授权就不读取本人档案。

三种角色都不能绕过确认、PII、来源保真或严格验收门。

## 持久化与安全边界

- `raw/` 与 `.staging/rasters/` 保留在患者本机档案，后续模型不得读取；下游唯一临床文本源
  是完成遮蔽的桶内 sidecar。
- **文本脱敏（text masking）**只替换 PII，不改临床字符（anti-anchoring）。MD sidecar 是
  下游唯一读取源且不携带 plaintext PII；clean scan 也不等于匿名化，外发仍需最小化与授权。
- `ocr/` 在 Step 3 后不保留副本；sidecar 只移动，不复制成第二真相源。
- 完整共享/角色/确认/安全契约仍适用：
  [`references/organize-contract.md`](references/organize-contract.md)、
  [`../../references/roles.md`](../../references/roles.md)、
  [`../../references/disclosure-behavior.md`](../../references/disclosure-behavior.md)、
  [`../../references/confirm-gate.md`](../../references/confirm-gate.md)、
  [`../../references/safety-guardrails.md`](../../references/safety-guardrails.md)、
  [`../../references/i18n.md`](../../references/i18n.md)、
  [`../../references/citation-format.md`](../../references/citation-format.md)、
  [`../../references/evidence-trust-tiers.md`](../../references/evidence-trust-tiers.md)、
  [`../../references/reference-library.md`](../../references/reference-library.md)。
