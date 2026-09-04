# Phase 4 worker cards（lite）

本卡只用于 Step 4 的产物生成 worker。宿主按 `phase4-dag.json` 派工；worker 不创建
run、receipt、WAL，不移动或重命名 sidecar，也不写未分配给自己的文件。

## 共同输出合同

1. 只读脱敏后的 `01_…14_` 桶内 Markdown sidecar；不得读 `raw/`、`ocr/`、
   `99_无关文件/` 或绝对路径。缺桶表示“本档案没有该桶的文档”，不是“患者没有该病史”。
2. 每项事实只复制来源。不得重分期、判断疗效、推断 ECOG、自动计算治疗线、推荐检查或治疗。
   冲突值并列保留并标 `disputed`，不选胜者。
3. JSON 的 `source_refs[]` 只写存在的桶内相对 sidecar 路径，可带 `#L…` 或 `#section`；
   正式 Markdown 的事实行必须写 `[[src:<桶内相对路径>#<fragment>]]`。禁止绝对路径、
   反斜线、`.`/`..`、`raw/`、`ocr/`、`99_…` 和悬空引用。
4. 宿主必须把 planner 返回的 `python_executable` 与 `schemas` 原样提供给 worker。worker
   做 JSON/schema 检查时只能使用这个绝对解释器路径；不得退回裸 `python` / `python3`，
   解释器或 `jsonschema` 不可用就返回失败，不得跳过校验。
5. 每个 JSON 只按对应 schema 写，
   写盘前检查 required/additionalProperties/enum；没有资料时写 schema 合法的空数组或 null，
   不得跨桶搜索“补齐”。Markdown 输出没有 JSON schema，但仍受 source-ref 合同约束。
6. 只写本节列出的输出。完成后只返回：
   `{"task_id":"<id>","status":"ok","outputs":["<owned output>"]}`。

## labs

- 只读：匹配稳定前缀 `07_*/**/*.md` 的本地化检验桶
- 唯一拥有：`labs.json`
- 数值、单位、参考范围、报告 flag、危急值标记逐字复制；不按通用阈值自行分级。

## comorbidities

- 只读：匹配稳定前缀 `02_*/**/*.md`、`03_*/**/*.md` 的本地化桶
- 唯一拥有：`comorbidities.json`
- 只记录来源明确写出的共病、用药和过敏；“未见记载”不能写成“无”。

## missing_items

- 只读：`source_inventory.json`、桶名和 sidecar 的报告类型声明；只有癌种已由来源明确写出时，
  才可读取相应 checklist。
- 唯一拥有：`missing_items.json`
- 只列“现有文档档案缺口”。不得把 checklist 变成检查建议；癌种不确定时写 unknown。

> 调度屏障：`labs`、`comorbidities`、`missing_items` 是 Wave A。宿主必须三个全部派出后再等待。

## molecular

- 只读：匹配稳定前缀 `06_*/**/*.md` 的本地化分子与组学桶
- 唯一拥有：`molecular.json`
- 缺少 `06_*` 桶时写 schema 合法空产物；不得回退读取叙事桶猜分子结果。

## treatment

- 只读：匹配稳定前缀 `03_*`、`08_*`、`09_*` 的本地化桶内 Markdown
- 唯一拥有：`treatment_lines.json`
- `sequence_index` 只表示来源事件的时间顺序；只有来源明写时才填治疗线标签。

## patient_summary

- 只读：所有已有的 `01_…14_` 桶内 sidecar。
- 唯一拥有：`patient_summary.json`。
- **禁止写 `profile.json`**。`profile.json` 由 `build_profile.py` 从通过 schema 的
  `patient_summary.json` 确定性生成。
- 年龄、身高、体重、ECOG 等时变字段必须保留各自 `_as_of`；不同日期的变化不是冲突。

## timeline

- 只读：所有已有的 `01_…14_` 桶内 sidecar。
- 唯一拥有：`timeline.json`、`timeline.md`；仅在存在时序/趋势数据时额外拥有
  `longitudinal_observations.json`。
- 按来源日期排序；日期不完整时保持不完整并说明，不补日/月。时间相邻不表示因果或疗效。

## case_text

- 只读：所有已有的 `01_…14_` 桶内 sidecar。
- 唯一拥有：`case_text.md`
- 这是带来源锚点的中性档案叙事，不是诊疗建议或疾病解释。

> `molecular`、`treatment`、`patient_summary`、`timeline`、`case_text` 是 Wave B。
> Wave A 全部完成后，宿主一次最多派满当前可用 worker 槽位，等待该批完成后再派余项。

## readiness_review

- 后置：所有 Wave B 产物和确定性 `profile.json`、`AGENTS.md` 完成后才运行。
- 只读：DAG 中列出的结构化产物与 Markdown。
- 唯一拥有：`readiness.json`、`review_summary.md`；`review_flags` 非空时额外拥有
  `review_flags.md`。
- `readiness.json` 只写文档覆盖与来源/忠实度问题，不写 A–F、分数或临床可行动性。
- 交叉检查只报告冲突，不修改上游产物；`review_summary.md` 每条事实继续使用桶内来源锚点。
- **每条 review_flag 必须在 flag 级带 `source_refs`**（桶内相对路径 + `#L` 行号锚点），
  渲染进 `review_flags.md` 时每行 flag 同样带 `[[src:path#L..]]`——锚点门对非空
  review_flags.md 强制锚点；没有真实锚点的 flag 不得写入（也不许编造锚点过门）。

## 域提取器通用纪律（labs / molecular / treatment / timeline / case_text / patient_summary）

- **禁止以空集合应付修复轮**：主集合（panels/events/episodes/reports）修不好就保留错误
  返回让编排层处置，绝不清空集合过门——桶内有 sidecar 而主集合为空是白卷，
  validator 的 `empty_collection_with_nonempty_bucket` 门会判不合格。
- **单域输出规模上限**：一次读取超过 ~12 份 sidecar 时按组切片输出、由编排层确定性
  合并（map-reduce），不要把几十份 sidecar 压进一次超长 JSON 输出（provider 截断
  是真实事故源）。
- **timeline 两段式**：先产 `timeline.json`（全部事实与锚点），`timeline.md` 必须从
  JSON 确定性派生，不二次自由发挥——锚点格式不一致的修复撞墙多源于手写 md。

## case_summary_data

- 后置：`readiness_review` 完成后才运行。
- 只读：DAG 中列出的脱敏结构化产物和 `case_text.md`。
- 唯一拥有：`.case_summary_data.json`；不得写 HTML。
- 严格遵守 `case-summary-html-prompt.md` 与 `case_summary_data.schema.json`；几何、版本差异、
  lab backfill 和 HTML 全由后续确定性脚本处理。
