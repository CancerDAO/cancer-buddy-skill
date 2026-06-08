# Organize Contract — runtime-neutral 行为契约

> `cancer-buddy-organize` 的**权威行为契约**。它规定 organize 由哪几个纯函数步骤组成、每步**产出什么 / 何时可写 / 必须满足什么不变量**,但**不规定**用什么工具、谁来跑、并行还是顺序。所有 binding(`runtime-bindings/*.md`)与各 prompt 的 `Runtime adaptation` 节都引用本契约;契约是分母,binding 是分子。
>
> **零工具名原则**:本文件刻意不出现任何宿主机制词(扇出原语 / 文件读取原语 / 图像转码命令 / 交互卡片 / 沙箱 / 持久化后端…)。"谁执行机制"属 binding 层,见 §6 接缝矩阵与 `runtime-bindings/`。某 host 的具体填法(参考实现是 Claude Code)永远写在 binding 里,不写进契约。
>
> 本契约**不改 organize 的逻辑 / schema / 产物结构**:脱敏 MD、进桶、canonical 改名、`redaction_manifest.json`、`review_flags`、6 结构化 JSON 全部按现有 prompt 定义,本文件只是把"行为"从"机制"里抽出来描述。字段级真值仍以 `organizer-prompt-phase1-ocr.md` / `organizer-prompt-phase2-synthesis.md` / `relevance-gate.md` / `upload-reconciliation.md` / `redaction-job.md` / `../../../references/confirm-gate.md` 为准。

## 0. 契约总览

organize 是 4 个纯函数步骤的有序组合。每步以 inputs → outputs(JSON / 文件产物)描述,带一组不变量。前三步是同一次 organize run 内的主链;第 4 步(段B 像素打码)是登记在册的**独立后续步骤**,可与主链解耦异步执行。

| # | 步骤 | 纯函数语义 | 主要产物 |
|---|---|---|---|
| 1 | Phase1 — per-file 脱敏 OCR | `(一个源文件, 稳定 file_id) → 一个脱敏 sidecar MD` | `<file>` 的脱敏 MD(`SOURCE/CONFIDENCE` 头 + 逐字脱敏正文 + `## PII` trailer) |
| 2 | Phase2 — 综合 | `(全部 sidecar, 源清单, file_id↔原名映射) → canonical 输出集` | 11 桶 + `profile.json` + `timeline.*` + `case_text.md` + `readiness.json` + `review_flags.md` + 6 结构化 JSON + `missing_items.json` + `update_log.json` + `redaction_manifest.json` + 桶相对锚点 |
| 3 | 确认门(产物化) | `(待写正式字段/待删文件) → 待确认项数据;经确认 → 写/删` | 待确认项数据(候选结构);确认后才落正式字段或不可逆删除 |
| 4 | 段B — 像素打码 | `(redaction_manifest.json, patient_dir) → 打码后桶图 + redaction_status.json` | 桶内图片替换为打码版 + 镜像收敛 + `redaction_status.json` |

**步骤间数据流的唯一前置**:Phase2 开始前,其覆盖范围内**所有源文件的 sidecar 必须就绪**(契约要求"就绪",不要求"如何就绪")。Phase2 产出 `redaction_manifest.json` 即把段B 的工作队列交接出去;段B 是否跑完不阻塞 Phase2 与 段D HTML(段D 只读脱敏 JSON/MD,不读图)。

---

## 1. Phase1 — per-file 脱敏 OCR(纯函数)

把**一个**源文件转成**一个**脱敏 sidecar MD。每个源文件独立成函数,彼此无依赖——这是契约把 Phase1 定义为"per-file 纯函数"的根本原因:就绪顺序、是否并行、用什么解码/识别都由 binding 决定,行为不受影响。

### 1.1 Inputs

| 字段 | 必需 | 含义 |
|---|---|---|
| `source_file` | 是 | 一个源文件(任意栅格 / PDF / 文本 / 文档)。 |
| `file_id` | 是 | 宿主分配的**稳定标识**,保证**源文件 ↔ sidecar 可一一对应**。同一源文件跨 run 同一 id;不同源文件 id 不碰撞。契约只要求"稳定且双向可查",不规定 id 形态(可为原名、哈希、序号…)。 |

> `file_id` 是 Phase2 的 `file_id↔原名映射` 与 §6「编排」接缝的契约基石。headless 单进程宿主同样必须维护它(见 §7 开放问题)。

### 1.2 Output — 一个脱敏 sidecar MD

每个源文件产出**恰好一个** sidecar,结构固定为三段:

1. **头**(强制):
   ```
   SOURCE: <source_type> | CONFIDENCE: <low|medium|high>
   ORIGINAL: <指回该源文件字节级原件的稳定引用>
   ```
   - `CONFIDENCE` 是**规则判定**,不是自评:命中 `[OCR_UNCERTAIN]`/`[CANDIDATES]`、手写/瓶贴/涂写 → `low`;单一来源无旁证 → `medium`;正式文书(出院小结/正式处方/病理/NGS/CT-MRI 叙述)且 ≥2 文档关键字段逐字一致 → `high`;默认 `medium`。详见 phase1-ocr.md §2.3。
2. **逐字脱敏 OCR 正文**:
   - text/mixed/pathology → **全文逐字转录**(表格转 Markdown 表;医嘱按 date|order|qty|sig|exec_status;出院证转 heading+治疗摘要+诊断+医嘱+签名 verbatim)。
   - 纯影像(切片/X 光/超声/照片)→ **stub**(≤5 行:模态 + 可见体区 + 可见日期)。
3. **`## PII` trailer**(强制):一行 `masked: <逗号分隔类别键>` 或 `masked: none`,登记本文件实际遮蔽的 PII 类别。供 Phase2 构建 `redaction_manifest.json` 的 `pii_hint`。该 trailer 是元数据,不带 `[[src:...]]` 锚点。

### 1.3 强制脱敏(P0,无豁免)

sidecar 是**整条下游管线的唯一读取源**(timeline / case_text / profile / 段D HTML / 段B job 都只读它、永不回读原图)。因此 PII 必须在此层**无条件**遮成 `[PII_MASKED]`,任何明文 PII 漏到 MD 就会一路泄到下游。遮蔽对象、判断方式(逐行语义判断,非固定正则名单)按 phase1-ocr.md §2.4。

**脱敏只动 PII token,绝不动任何临床字符**:不"纠正"/规范化/改写药名、剂量、TNM、分子标记、检验值、临床事件日期。拿不准是出生日期还是临床日期 → 当临床(保 verbatim);临床保真优先于过度遮蔽。

### 1.4 不变量(行为级,binding 不得违反)

- **逐字优先,不捏造**:不可读 → `[OCR_UNCERTAIN: verbatim | alternative]`;未知名 → verbatim + `[CANDIDATES: ...]`(不替用户选)。绝不发明医学事实。
- **anti-anchoring**:不用其它文件"纠正"当前文件;不把识别出的字符悄悄换成形近真实药名;同批内跨文件矛盾两边都记 verbatim、**不调和**(调和是 Phase2 的事)。这是本 skill 最大历史失败模式("一致但全错")的拦截层。
- **无采样、无预算上限**:覆盖范围内每个含文字图都出全 OCR,每个非文字图都出 stub,禁止抽样。
- **幂等**:对同一源文件重复执行,不覆盖比源文件更新的既有 sidecar。
- **不越界**:Phase1 只产 per-file sidecar,**绝不**写任何全局产物(INDEX/timeline/case_text/profile/readiness/review_flags/review_summary 全是 Phase2 的)——否则与并行实例产生竞态。

### 1.5 契约**不规定**(交 binding)

OCR 引擎(in-agent 视觉 / 外部识别 / 宿主直接喂文本皆可)、是否并行、单实例处理多少文件、非可读栅格(如 HEIC)如何解码为可读图。这些是 §6 的「OCR 源 / 图像解码 / 编排」接缝。**切片预算(如"≤N 图/实例")是某些宿主的多图预算特性,属 host-tunable 参数,不是契约不变量**——不切、按宿主预算切都合规,只要 1.4 不变量成立。

---

## 2. Phase2 — 综合(纯函数)

读全部 sidecar,分类进桶、canonical 改名、co-locate MD 与原图,产出全部全局结构化产物。

### 2.1 Inputs

| 字段 | 必需 | 含义 |
|---|---|---|
| `sidecars` | 是 | Phase1 产出的全部脱敏 sidecar MD(就绪是前置,见 §0)。 |
| `source_inventory` | 是 | 覆盖范围内的源文件清单(用于 coverage 校验:sidecar 数 < 源数 → 列缺口、记 `phase1_coverage_gap`,不中止)。 |
| `file_id_to_name` | 是 | `file_id ↔ 原名` 映射,保证 sidecar 能回指源文件、canonical 改名可追溯。 |
| `run_mode` | 否 | `full`(默认)/ `incremental`(只重分类增量并合并下游)。 |
| `caller_default_hospital` | 否 | 出具机构 4 级回退里的第 3 级(通常 `treating_hospitals[0]`)。 |
| `triggered_by` / `reason` | 否 | 写入 `update_log.json` 的调用上下文。 |

### 2.2 Output — canonical 输出集(结构不变)

| 产物 | 内容 | 关键约束 |
|---|---|---|
| 11 桶 | 每文件落 `<bucket>/<canonical>.<ext>` + co-located `<bucket>/<canonical>.md` | 禁止桶根裸文件;无明确子类落该桶 `其他/`。 |
| canonical 命名 | `<YYYY-MM-DD>_<doc_type>_<hospital>[_p<page>].<ext>` | doc_type/hospital/date 由 sidecar 语义判定(LLM,非正则);hospital 走 4 级回退;缺值 `unknown-date`/`unknown-org`。 |
| `INDEX.md` | 每文件一行(桶/类型/日期/机构/置信/canonical/MD),按日期升序 | 路径全为桶相对 co-located 路径。 |
| `timeline.md` / `timeline.json` | 时间序事件 + 机器可读镜像 | 每事件行 ≥1 个桶相对 `[[src:...]]` 锚点。 |
| `case_text.md` | 分节叙述,每事实句带锚点 | 锚点契约见 2.3;dangling 锚点 → 不写文件、记 `anchor_dangling`。 |
| `profile.json` | canonical schema(含 `locale`、`alias`,字段不变) | `current_therapy` 为 STRING 取最新;`alias` sticky 不覆写。 |
| `readiness.json` | 8 域评分 + grade + `blocking_gaps` + `warnings` + `review_flags` | grade 阈值:A≥.90 B≥.75 C≥.60 D≥.40 F<.40。 |
| `review_flags.md` | 非空时写(8 类审查) | 见 2.4。 |
| 6 结构化 JSON | `patient_summary/timeline/molecular/treatment_lines/labs/comorbidities` | 每事实字段带 `source_refs`;过 schema gate 才写,失败记 `schema_validation_failed`。 |
| `missing_items.json` | 癌种 checklist diff(stage-context) | 映射不明 → `cancer_type:null`+`checklist_unmapped`。 |
| `update_log.json` | 本次 run 审计条目 | full=全量条目;incremental=delta。 |
| `redaction_manifest.json` | 段B 工作队列交接(`redaction_manifest_v1`) | 只列栅格图;每条 `bucket_path`+`mirror_path`+`pii_hint`+`status:pending`;过 schema 校验。 |
| 业务别名指针 | 顶层 alias 指针(指回 `patient_code` 目录) | `alias` 已设时建立;不可建链时退化为 alias 映射文件。 |

字段级真值(schema、4 级机构回退、stage-context、8 域评分细则、locale 渲染)全部以 phase2-synthesis.md 为准,本契约不复述,只锚定"产出这些、满足这些不变量"。

### 2.3 锚点契约(co-located、桶相对)

- 语法 `[[src:<桶相对路径>]]` 或带 `#<fragment>`(`#L<a>-L<b>` 行段 / `#<slug>` 节段),或会话形式 `[[src:conversation:<ISO8601>]]`(段C 专用)。
- `<桶相对路径>` **必须**以 `NN_` 桶段开头,指向**现已位于其桶内、紧邻原图**的 MD sidecar。遗留 `ocr/` 与 `02_脱敏病历/` 前缀**已废弃、被拒**(综合结束后中央暂存区不复存在)。任何其它前缀被拒:不写该产物、把违规路径记入 `readiness.json.warnings` 为 `anchor_dangling: <path>`。
- 覆盖:每事实句 ≥1 锚点;纯过渡句 / 纯标题免锚。
- 写任何带锚产物前,逐个解析锚点、校验目标 MD 在其桶内存在;有 dangling → 不写、记 warning。
- 全文规范:`references/schemas/anchor-contract.md`。

### 2.4 review_flags 审查(必跑,可空)

Phase2 的跨文档审计(Phase1 做不到,因 Phase1 只见自己那片;Phase2 还能横看 patients root 下兄弟目录做跨患者检查)。对 profile 关键字段跑 8 类检查:`format_violation` / `cross_doc_contradiction` / `clinical_logic_anomaly` / `unverified_critical_field` / `value_trend_anomaly` / `cross_patient_name_collision`(**P0**:同名+同生年撞另一患者→`red`) / `anchor_coverage_gap` / `relevance_uncertain`(段E borderline,见 §3)。flag 形态、严重度校准(red 改下游 rec 或隐私/安全关键;yellow 应复核不阻断;green 信息性)见 phase2-synthesis.md §3。`review_summary.md` 每次必写(即便 grade A、flags 空)。

### 2.5 不变量

- **桶不变量**:每文件必进某桶的 typed 子目录,禁桶根裸文件;`NN_` 两位数字前缀是**语言无关稳定 key**,其后 slug 按 `locale` 渲染;下游一律按 `NN_` 数字前缀解析锚点,localize slug 不破坏解析(`bucket_path`/`file_dest`/`md_dest`/锚点用同一 localized slug,保证盘上路径与锚点一致)。
- **locale 不变量**:Phase2 是 `profile.json.locale` 的 canonical 写者——检测并持久化(已存在则复用,除非用户显式改语言);所有患者向 scaffold(桶 slug、timeline/case_text/review_summary 文案、gap/warning 文案、确认通知)按 locale 渲染。**临床实体(药/基因/变异/TNM/数值+单位)与 `doc_type` 永远 verbatim,绝不翻译/转写/规范化**——误译是 P0 安全 bug。
- **暂存区不残留**:综合结束后,中央 sidecar 暂存区必须被排空——每个 MD 都 co-located 进桶,排空失败 → 暴露 `ocr_drain_incomplete`、保留暂存区、不弃文件。任何产物不得在综合后引用中央暂存区。
- **manifest 必产**:返回前必产 `redaction_manifest.json`(段B 唯一交接);只列栅格图;校验失败记 warning,不发无效 manifest。
- **alias sticky**:incremental run 不覆写已设 `profile.json.alias`。
- **不发坏产物**:schema 不过的结构化 JSON 不写、dangling 锚点的 case_text 不写——暴露缺口,不出半成品。

### 2.6 契约**不规定**(交 binding)

- 单进程顺序综合 vs 扇出后 reduce——只要 2.1 inputs 就绪、2.2/2.5 成立,二者等价。
- canonical 改名 / 原子移动**由谁执行**:语义判定(哪个桶、什么 canonical 名)是必须的 LLM 判断并固化为一份"改名计划"数据;据此做的机械字节搬运(把原件按 canonical 名拷进桶、把 MD 移到旁边、回填映射、排空暂存区、生成 manifest)是无判断的纯搬运,可由宿主执行。契约要求"结果落在 2.2 的产物结构里",不要求"哪个原语搬的"。这是 §6「编排 / 存储」接缝。

---

## 3. 确认门(产物化,非 inline)

任何"写正式字段"或"不可逆删除文件"前,必须先产出**待确认项数据**,经用户显式确认后才落地。这是把 `confirm-gate.md` 的共享门**从某种特定呈现方式里解耦**出来的契约表述。

### 3.1 契约(不变)

- **未确认绝不写正式字段**:`profile.json` / `timeline.*` / `case_text.md` / `readiness.json` / 结构化 JSON 不从未确认候选写入。沉默 / 推迟 / "随便" / 关闭会话 = no-confirm → 该候选不写。
- **不可逆删除子规则(非对称,load-bearing)**:高置信非医疗文件 no-confirm ⇒ 删(隐私底线,by design,删前必须先告知"不留无关原件、沉默=删");borderline(`relevance_uncertain`)no-confirm ⇒ 留、永不自动删。删可能是真病历的文件是更坏的错。
- **不编造用户没给的精确值**;关键字段(分期/分子驱动/治疗线)歧义时在待确认项里问一句,而非猜。
- **关键字段变更绝不既成事实**;矛盾值绝不静默覆盖——两值并陈交用户裁。
- **候选检测/分类是 LLM 判断**(读上下文比对现有 profile/timeline/sidecar),不跑硬编码关键词名单或同名同日 Python 比较器。
- 每次 gated 动作必在 `update_log.json` 留一条(确认写入 / 推迟 / 不可逆删除的 ledger),无匹配条目就不许写/删。

### 3.2 产物形态:待确认项数据

确认门的**契约产物**是一份**待确认项数据**(沿用段C 候选结构 + `confirm-gate.md` 的 diff-card 内容契约):每候选含 `current_value → proposed_value`(字段改)/ 整条新行(timeline 行)/ "isolated as X — 一行理由"(relevance/删除候选);带依据(用户原话 / 检查名·日期·机构·矛盾字段);`low` 置信候选明标并给修正/退出动作;关键字段变更与"已替换/已删除"绝不呈现为已完成;矛盾两值并陈标 ⚠️。该数据是患者向 scaffold,按 `locale` 渲染,**内部临床实体 verbatim**。

### 3.3 契约**不规定**(交 binding)

确认怎么**呈现 / 往返**——**inline 即时往返**(交互宿主)或**confirm-as-product + 宿主 UI 两轮往返**(headless:第一轮产出待确认项数据落盘,宿主 UI 收集用户决定,第二轮回灌已确认决定再落地)**皆合规**,只要 3.1 不变量(未确认不写、删除非对称、留 ledger)成立。段E 处置门、upload-reconciliation 处置同此一门(各自 specialization 在其 doc:段E 三 relevance 类/`99_无关文件/`、段C 5 类可归档事实/会话锚、reconciliation 的 new/supersede/conflict + `_superseded_<ts>/`)。这是 §6「确认门」接缝。

---

## 4. 段B — 像素打码(已 runtime-neutral)

把桶里图片内的明文 PII 像素真正涂黑(段A 只做了 MD 文本级脱敏,桶图本身仍含明文 PII),QA 通过后用打码版**不可逆**覆盖原件,并收敛镜像。本步骤**本就 host-friendly**,在契约里登记为**独立后续步骤**,不改。

### 4.1 Inputs

| 字段 | 必需 | 含义 |
|---|---|---|
| `redaction_manifest.json` | 是 | Phase2 产出的工作队列(`redaction_manifest_v1`):每张待打码图的桶内路径 + 镜像路径 + 可选 `pii_hint`。 |
| `patient_dir` | 是 | 患者目录(段B 从中定位 manifest 与图)。 |

### 4.2 Output

- 桶内图片被替换为**打码版**;镜像(字节级审计目录)同步收敛为打码版。
- `redaction_status.json`(`redaction_status_v1`):`summary{total,pending,done,failed,blocked}` + per-file `{id,status,redacted_path,qa_passed,original_deleted,reason}`,与 manifest 按 `id` join。

### 4.3 不变量

- **QA 门是删原件的唯一前置**:打码先写临时文件不覆盖原图;对打码图二次扫描,仍检出 PII → QA 失败 → 弃临时图、保原图、标 `failed`、`original_deleted=false`。**仅 `qa_passed=true` 才允许删打码前原件**。
- **删原件不可逆**:`status=done` 的上传原件+镜像原图被打码版永久覆盖,不可恢复明文;删除只在 `qa_passed=true` 发生。
- **只遮 PII,不改临床字符**(黑框只盖 PII 区域 quad)。
- **幂等可重试**:每处理一张刷一次 status,重跑跳过 `done`。
- **时序**:段B 须在任何"持久化 / 离开本地工作区"之前跑,持久化的桶图才是打码版;原图永不离开本地工作区(段B 删前;段B 跑完只留打码版)。

### 4.4 契约**不规定**(交 binding)

段B 是一个**独立可调度步骤**:由谁触发、何时触发(与主链同步还是异步后端 job)、用哪个解释器/打码引擎拉起——全是宿主生命周期编排。契约只要求"读 manifest → 打码 → QA 门 → 仅 QA 通过删原件 → 写 status",以及 4.3 时序。运行细节(独立脚本、venv、退出码语义)见 `redaction-job.md`。这是 §6「存储」接缝在打码侧的体现。

---

## 5. 跨步骤全局不变量

无论哪个 host 驱动,以下行为不变量必须成立(它们是验收 §11 与"CC 不退化"的判据):

1. **sidecar 是唯一明文边界**:下游(Phase2 / 段D / 段B)只读脱敏 MD,永不回读原图;明文 PII 不得越过 Phase1。
2. **进桶 + 段B 打码留可浏览版**:每文件 co-located 进桶,原图打码后保留(可浏览档案库)且 at-rest 不留明文——这是新设计相对旧 organize 的增量,任何 binding 不得退化回"丢原图 / 不进桶"。
3. **未确认不落正式字段 / 不可逆删除**(§3 确认门),无论 inline 还是 confirm-as-product。
4. **临床保真 > 一切便利**:任何步骤、任何 binding 都不得翻译/规范化/平滑临床实体。
5. **逻辑/schema/产物结构零改动**:换 binding 只换"谁执行机制",§1–§4 的 inputs/outputs/schema 不变。

---

## 6. 接缝矩阵(§5 PRD)

5 个接缝把"契约不变量"与"per-runtime 机制"对齐。**契约要求列恒定**;各 host 列只换填法。Claude Code 列是**参考实现(reference binding)**,不是契约——CC 现机制原样保留,新中立层加在其上(§8 不退化保证)。完整每 host 填法见 `runtime-bindings/{claude-code,headless-codex,_template}.md`。

| 接缝 | 契约要求(不变) | Claude Code binding(参考) | headless codex | 其它 agent(模板) |
|---|---|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | 扇出 + reduce | 单进程顺序 | 各自 job 队列 |
| OCR 源 | 每文件产脱敏 MD(`SOURCE`/`CONFIDENCE`/`## PII`) | in-agent 视觉读取 | 宿主视觉识别 / 离线 OCR | 任意 OCR / 宿主喂文本 |
| 图像解码 | 给出可读栅格 | 平台转码命令 | 跨平台转码 | 宿主预处理 |
| 确认门 | 未确认不写正式字段 | inline diff 卡 | confirm-as-product + UI | 产物化 |
| 存储 | 结构化产物 + 桶 + manifest 为 canonical 输出集 | agent 写 `patient_dir` | 选定文件持久化到对象存储/库 | 各自存储原语 |

> 矩阵读法:**纵向**取一个 host 列 = 该 host 的薄 adapter 该填什么;**横向**取一行 = 该接缝在所有 host 上必须满足的同一契约要求。防 fork 漂移的根本:一份契约(本文件)+ N 个薄 binding,而非每家 fork 整条管道。

---

## 7. 开放问题(由 binding / 平台落实,非契约缺口)

- **file_id ↔ 原名映射**:headless 宿主必须分配稳定 id 并维护映射(§1.1 契约要求,宿主实现)。
- **段B 时序**:依赖宿主把打码步骤接进"持久化前"生命周期(§4.3 时序不变量,宿主侧)。
- **切片预算**:某些宿主的多图预算特性 → host-tunable 参数(§1.5),headless 可不切或按自己预算切,不影响 1.4 不变量。
- **OCR 源选型**:同一契约同时支持 in-agent 视觉 / 离线 OCR / 宿主喂文本,选哪种是 binding 侧重(影响具体 binding 草案,不影响契约)。
