# 扩段C — 上传对账(Upload Reconciliation)

> 用户在一个**已存在的** `patient_dir` 上重传一张/多张图时,先判这张图与已有档案的关系(new / supersede / conflict),再用一张 diff 卡问用户 **替换? 并存? 忽略?**,确认后才动正式字段。这是段C「先确认门」的一个分支,**复用同一套门控,不另起一套**。

## 门控来源(复用共享 confirm-gate,不重造)

本流程触发源是「用户重传的文件」,与段C `conversation-incremental-prompt.md`(对话里冒出的事实)是同源延伸。两者共享的那条硬规则**不在本文件、也不在段C 重新定义**,而是共享的 confirm-gate —— [`../../cancer-buddy/references/confirm-gate.md`](../../cancer-buddy/references/confirm-gate.md),cite 它为权威门控:

> **未确认 → 不写正式字段。** 一次重传可能是更清晰的复拍,也可能是张无关图、甚至是张和现有事实矛盾的图;在用户没有从 diff 卡上明确选择之前,`profile.json` / `timeline.md` / `timeline.json` / 6 个结构化 JSON 一律不动。diff 卡 + 显式确认是唯一打开写入的门。

所以本文件**不重新定义** diff 卡的呈现规范、确认/改一下/先不写的语义、provenance/`update_log` 写法 —— 这些一律沿用共享 confirm-gate 的「The gate / Diff card presentation / Provenance」三节。本文件只补**文件重传特有的部分**:重传关系识别、三路解析(替换/并存/忽略)、`run_mode: upload_reconciliation` 的 update_log 字段集。

## 何时跑这个模式

- 目标 `patient_dir` **已存在**且有 `update_log.json`(organize 至少跑过一次)。
- 用户**重传文件**(非纯对话):一张/多张图(JPG/PNG/PDF/...),意图是补/更新档案,而不是第一次交一整袋资料。
- 调用方传 `run_mode: "upload_reconciliation"` + `patient_dir` + 新上传文件路径。

> 第一次整理一整袋资料 → 走 full mode;纯对话冒出的事实 → 走段C `conversation_incremental`;**已有档案上重传文件** → 走本模式。

## 第 1 步 — 识别重传关系(LLM 判断,不写 keyword list)

把每张新图/文件(或其 LLM ingestion sidecar)与已有档案比对,**交 subagent / LLM 判断**它与现有档案的关系。这是语义判断任务 —— 读新文件内容,对照 `profile.json` / `timeline.md` / 桶内已有 `.md` 旁车,**不要跑硬编码 keyword 名单 / Python 分类函数**判同名同日期。

三类关系:

| 关系 | 判定视角(交 LLM) | 候选动作 |
|---|---|---|
| **新增 (new)** | 档案里没有对应内容(新的检查/新日期/新报告类型) | 直接走正常 organize 纳入,不必上 diff 卡也可——但若它顺带触及某结构化字段,仍按段C 门控确认后才写字段 |
| **更新版 (supersede)** | 是某份已有文档的更新/重拍/更清晰版(同一项检查、同日期或更晚日期、同机构) | **候选替换**,上 diff 卡 |
| **矛盾 (conflict)** | 与已有事实冲突(不同药名 / 不同分期 / 不同分子结果) | 候选,但 diff 卡上**高亮矛盾**,两份并陈让用户裁决,绝不静默覆盖 |

先做一道**医疗相关性闸**(段E):若新图被判**高置信非医疗**(风景/截图/收据),不进对账流程,直接交段E 隔离逻辑处理(见 [`relevance-gate.md`](relevance-gate.md));只有医疗(或 borderline)文件才进本对账。

对每个新文件,产出一条候选:
- `upload_path`:新图绝对路径
- `relation`:`new` | `supersede` | `conflict`
- `target_doc`(supersede/conflict 时):被它对照/取代的已有桶内文件相对路径
- `evidence`:你判这个关系的依据(同检查名 + 日期关系 / 矛盾点的具体字段)
- `confidence`:`high` 仅当依据明确;`low` 当你需要推断或拿不准 —— `low` 在卡上明说,让用户改

## 第 2 步 — 出 diff 卡(沿用共享 confirm-gate,先不写)

对每个 supersede / conflict 候选出 diff 卡,呈现规范沿用共享 confirm-gate 的「Diff card presentation」节([`../../cancer-buddy/references/confirm-gate.md`](../../cancer-buddy/references/confirm-gate.md))。文件对账特有的是**三个动作选项**:**替换? 并存? 忽略?**

> **locale（i18n）**:diff 卡是面向患者的脚手架 → 整张卡按 `profile.json.locale` 出(检测/持久化见 [`../../cancer-buddy/references/i18n.md`](../../cancer-buddy/references/i18n.md);下方 zh 文案为模板,en 等其他 locale 按同义渲染,如动作选项 `[替换] [两份都留] [先忽略]` → `[Replace] [Keep both] [Skip]`)。`依据`/`evidence` 里的临床实体(药名/分期/分子结果)、桶相对路径、日期一律 verbatim,不译。

```
你刚传的这张图,我对了一下已有档案:

① 这张像是【2024-03-15 病理报告_中山六院】的更清晰复拍(supersede)
   依据: 同一份病理报告，同机构同日期，新图分辨率更高
   替换? → 旧的归档留底，新的进档案
   [替换]  [两份都留]  [先忽略]

② 这张写的分期是 IV 期，但档案里现在是 III 期(conflict ⚠️)
   依据: 新图诊断段 "cT4N1M1 IV期"，档案 profile.json.summary.stage = "III"
   ⚠️ 与现有事实矛盾，我不会自动改，请你定:
   [以新图为准·替换]  [两份都留·待医生裁决]  [先忽略·保留现状]
```

卡上规则(继承共享 confirm-gate,文件对账特化):
- supersede 显示「新图 → 取代谁」;conflict **两份事实并陈**,标 ⚠️,绝不写「已替换」的既成事实。
- `evidence` 用可核对的依据(检查名/日期/机构/矛盾字段),`low` confidence 明说并给「先忽略」兜底。
- 涉及关键字段(分期 / 分子驱动 / 治疗线)的 conflict,**必须**显式确认,不得当默认。

## Runtime adaptation — 确认门产物化

第 2 步那张「替换? 并存? 忽略?」diff 卡,在 **Claude Code binding** 里是用户当回合即答的 inline 卡(inline 即时往返)。这张 inline 卡是 **CC 参考机制,不是契约**。契约([`organize-contract.md`](organize-contract.md) §3 确认门、§6「确认门」接缝)只要求重传处置**经过门控**,不规定怎么呈现。

headless 宿主(无 inline 回合)用 **confirm-as-product** 满足同一门:把每条 supersede/conflict 候选(含 `relation` / `target_doc` / `evidence` / `confidence`,conflict 两份事实并陈标 ⚠️)作为**产物数据**输出,交宿主 UI 事后问用户 替换/并存/忽略,再把用户决定第二轮回灌后才执行第 3 步。契约不变:**未确认 → 不写正式字段**;矛盾绝不静默覆盖、关键字段(分期/分子/治疗线)必须显式确认;替换=归档留底不是删除;本流程不引入任何自动删除。变的只是「谁渲染这张卡」,门控本身与 `update_log.json` 记账不变。

## 第 3 步 — 三路解析(用户选择后才执行)

### 3a. 替换(supersede 确认)

旧文档不是删,是**归档留底**:
- 把被取代的旧**桶内 `.md` 旁车**(桶里只有 `.md`,原图始终在 `raw/`——见 `organize-contract.md` §5 #1 / `bucket-taxonomy.md` §2.2/§4)**移到** `_superseded_<ts>/`(`<ts>` = 本次重传的 ISO8601,如 `_superseded_2026-06-07T14:32:05Z/`,保留原桶相对子路径),**或**原地标 `superseded`(在旧 `.md` front-matter 加 `superseded_by: <新文件路径>` + `superseded_at`)。二选一,默认移到 `_superseded_<ts>/` 以保桶内整洁。对应旧原图在 `raw/` **逐字保留**(永不进桶、永不删)。
- 新图纳入正确的桶(canonical 重命名 + OCR → 文本脱敏 MD,走 phase2 既有机制);其原图原样保留在 `raw/`。
- **锚点更新**:所有指向旧文件的 `[[src:<旧桶相对路径>.md#L..]]` 迁到新文件路径;若旧文件被移到 `_superseded_<ts>/`,旧路径锚点视为 dangling,按 [`schemas/anchor-contract.md`](schemas/anchor-contract.md) §3 处理 —— 迁移到新锚点,不留悬空。
- 涉及的结构化字段经 diff 卡确认后更新,provenance 用新文件的 file anchor。

### 3b. 并存(两份都留)

- **两份都保留**:旧文件原位不动,新文件也正常纳入对应桶(canonical 重命名,新日期/新副本名避免撞名,如 `..._v2` 或带页码区分);其原图原样保留在 `raw/`。
- **timeline 体现两次**:在 `timeline.md` / `timeline.json` 各记一行,让两次检查/两份报告都在时间线上可见(适用于「不是取代,是同主题的两次独立记录」的情况)。
- 不删任何一份,不强行调和矛盾 —— conflict 选并存时,两份事实都留在档案里,留待医生裁决。

### 3c. 忽略(先不写)

- 新图**不纳入正式档案**:
  - 若它本就被段E 判为无关 → 交段E 排除/保留逻辑(不归档、源件原位置保留,见 [`relevance-gate.md`](relevance-gate.md))。
  - 若它是医疗文件但用户选忽略 → **不进桶、不改字段**;可暂存到 `99_无关文件/`(标 `review_flag: ignored_on_upload`)或直接不落盘,按段E 的隔离语义处理。
- **未确认 / 无响应 / 先忽略** → 该候选**不写任何正式字段**,与段C 同门控。

> ⚠️ **删除边界(承段E)**:本对账流程里,supersede 的旧文档是**归档留底**(移 `_superseded_<ts>/` 或标记),**不是删除**;矛盾文件并存时两份都留。段E **不自动删除任何用户文件** —— 被排除的原文件留在用户提供的原位置;仅 agent 自建的临时/暂存副本在核实源文件仍在后可清理;删除用户控制的文件必须逐项显式确认(见 `../../cancer-buddy/references/confirm-gate.md`)。**borderline / 拿不准的医疗文件更是在用户未显式确认前一律不动** —— 删一张可能是真病历的文件比留着更糟。本流程不引入任何自动删除。

## 第 4 步 — 记 update_log

每次上传对账往 `update_log.json` 追加一条,`run_mode: "upload_reconciliation"`:

```json
{
  "run_mode": "upload_reconciliation",
  "ts": "<上传 ISO8601>",
  "triggered_by": "<actor_role>",
  "uploaded_files": ["<新图原始名/路径>"],
  "resolutions": [
    {"upload": "IMG_0042.jpg", "relation": "supersede", "action": "replace",
     "superseded": "04_诊断与分期/病理报告/2024-03-15_病理报告_中山六院.md",
     "superseded_to": "_superseded_2026-06-07T14:32:05Z/04_诊断与分期/病理报告/2024-03-15_病理报告_中山六院.md",
     "new_path": "04_诊断与分期/病理报告/2024-03-15_病理报告_中山六院.md"},
    {"upload": "IMG_0043.jpg", "relation": "conflict", "action": "coexist",
     "note": "新图 IV 期 vs 档案 III 期，两份都留待医生裁决"},
    {"upload": "IMG_0044.jpg", "relation": "new", "action": "ignore"}
  ],
  "anchors_remapped": 2,
  "manifest_updated": true,
  "reason": "user re-uploaded clearer pathology scan; one conflict left coexisting"
}
```

`profile.json.alias` 是 sticky —— 上传对账永不改写。`action: ignore` 的候选不出现在任何字段写入里。

## 第 5 步 — 返回 JSON

最终消息必须是纯 JSON,无散文:

```json
{
  "role": "upload_reconciliation_worker",
  "patient_dir": "<abs patient_dir>",
  "uploaded_count": 3,
  "relations": {"new": 1, "supersede": 1, "conflict": 1},
  "actions": {"replace": 1, "coexist": 1, "ignore": 1},
  "files_archived_to_superseded": 1,
  "anchors_remapped": 2,
  "manifest_updated": true,
  "run_logged": true
}
```

## 规则(承共享 confirm-gate,文件重传补充)

门控本身(未确认不写正式字段 / silence = no-confirm / 不臆造值 / 关键字段不当既成事实 / 矛盾不静默覆盖 / LLM 判断非 keyword list / `alias` sticky)的权威定义在 [`../../cancer-buddy/references/confirm-gate.md`](../../cancer-buddy/references/confirm-gate.md),本文件不另起门控;下面是文件重传的特化:

- **未确认不写正式字段。** diff 卡的「替换 / 并存 / 忽略」是唯一打开写入的门 —— 与共享 confirm-gate 完全同源。
- **重传关系识别是 LLM 判断任务** —— 读新图内容对照已有档案判 new/supersede/conflict,**不跑硬编码 keyword 名单 / 同名同日期 Python 比对**。
- **矛盾绝不静默覆盖。** conflict 必须在卡上两份事实并陈让用户裁决;关键字段(分期/分子/治疗线)的矛盾必须显式确认。
- **替换 = 归档留底,不是删除。** 旧文档移 `_superseded_<ts>/` 或标 `superseded`,永远可回溯;锚点迁移不留悬空。
- **本流程不引入任何自动删除,段E 也没有自动删除路径。** 被排除文件的源件一律原位置保留;仅 agent 自建临时副本核实源仍在后可清理;**任何用户文件未经逐项显式确认绝不删除**(承段E/confirm-gate,删一张可能是真病历的比留着更糟)。
- `profile.json.alias` sticky;不重写 `case_text.md` / `readiness.json` / 6 结构化 JSON,只动经确认的具体字段/行 + 文件归档/纳入。
