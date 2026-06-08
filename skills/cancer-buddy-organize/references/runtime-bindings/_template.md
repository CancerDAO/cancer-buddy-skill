# Runtime Binding — `<HOST_NAME>`(模板 / template)

> `cancer-buddy-organize` 第三方 host 绑定**空模板**,供 workbuddy / openclaw / OpenCode / Cursor 等照填。复制本文件为 `runtime-bindings/<host>.md`,把每个接缝的 `<填法: …>` 换成你这个 host 的原语,**但不得改任何"契约要求(不变)"行**——那些是 `organize-contract.md` 的不变量,所有 binding 共享。
>
> **读法**:每个接缝 = 一段。`契约要求(不变)` 是你必须满足的;`填法` 是你用自己原语填的;`不变量` 是你填完后必须自检成立的。填完后跑契约 §5 的跨步骤全局不变量与 PRD §11 验收。
>
> **参照实现**:`runtime-bindings/claude-code.md`(交互式宿主:扇出 + in-agent 视觉 + inline 确认)与 `runtime-bindings/headless-codex.md`(单进程 headless:顺序 + 外部 OCR + confirm-as-product)是两组已填好的对照——你的 host 落在它们之间的某处,照最接近的那个改。
>
> **零工具名原则只约束契约,不约束 binding**:契约刻意不写工具名;binding **就是**写你 host 工具名的地方。

## 0. 绑定总览(填表)

| 接缝 | 契约要求(不变) | `<HOST_NAME>` 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | `<填法: 扇出 / 单进程顺序 / job 队列?>` |
| OCR 源 | 每文件产脱敏 MD(`SOURCE`/`CONFIDENCE`/`## PII`) | `<填法: in-agent 视觉 / 外部 OCR / 宿主喂文本?>` |
| 图像解码 | 给出可读栅格 | `<填法: 什么命令把 HEIC/PDF 转可读栅格?>` |
| 确认门 | 未确认不写正式字段 | `<填法: inline 往返 / confirm-as-product 两轮?>` |
| 存储 | 结构化产物 + 桶 + manifest 为 canonical 输出集 | `<填法: 写哪、persist 到哪?>` |

**宿主额外职责检查**:你的 OCR 源是否知道原文件名?
- **知道**(按路径读图,如 CC `Read`)→ `file_id` 可用原名,无需额外映射。
- **不知道**(喂匿名字节,如 codex `-i`)→ **宿主必须分配稳定 `file_id` 并维护 `file_id ↔ 原名` 双向映射**(契约 §1.1 / §7)。这是 Phase2 `file_id_to_name` input 的基石,漏了 canonical 改名无法追溯。

---

## 1. 接缝:编排(orchestration)

- **契约要求(不变)**:Phase2 开始前,覆盖范围内**所有源文件的 sidecar 必须就绪**。契约只要"就绪",不规定并行/顺序。
- **`<HOST_NAME>` 填法**:`<填法: 你怎么保证全 sidecar 就绪?扇出后 reduce / 单进程顺序遍历 / 你自己的 job 队列。worker 内文件顺序还是并行?continuation/retry 怎么做?>`
- **切片预算**:`<填法: 你的模型有多图/上下文预算吗?有就按预算切(host-tunable,非契约不变量);没有就不切。>`
- **不变量(填完自检)**:Phase1 阶段**只**写 sidecar 暂存区 + 原图镜像,**绝不**写 INDEX/timeline/profile 等全局产物(否则与并行实例竞态);幂等(重跑跳过比源更新的既有 sidecar)。

## 2. 接缝:OCR 源(OCR source)

- **契约要求(不变)**:每文件产**恰好一个**脱敏 sidecar MD,三段固定——`SOURCE: <type> | CONFIDENCE: <low|medium|high>` + `ORIGINAL: <稳定引用>` 头 / 逐字脱敏 OCR 正文(文字图全文逐字、影像图 ≤5 行 stub)/ `## PII` trailer。sidecar 是**下游唯一读取源**,**强制 PII 脱敏**成 `[PII_MASKED]`,不得带明文。`CONFIDENCE` 是规则判定非自评(phase1-ocr.md §2.3)。
- **`<HOST_NAME>` 填法**:`<填法: 用什么识别?in-agent 多模态视觉 / 外部 OCR 引擎 / 宿主直接喂已有文本。脱敏在哪一步做?>`
- **不变量(填完自检)**:anti-anchoring(不跨文件"纠正"、矛盾两边都记 verbatim 不调和)、unreadable→`[OCR_UNCERTAIN]`、未知名→verbatim+`[CANDIDATES]`、无采样无预算上限、只动 PII token 绝不动临床字符、只写 per-file sidecar 不写全局产物。

## 3. 接缝:图像解码(image decode)

- **契约要求(不变)**:给 OCR 源一张**可读栅格**。
- **`<HOST_NAME>` 填法**:`<填法: HEIC/HEIF/PDF 怎么转可读栅格?sips(macOS)/ heif-convert / ImageMagick / pdftoppm / 宿主喂图前预处理。>`
- **不变量(填完自检)**:解码只为"给出可读栅格",不改像素语义,不在此步做任何 PII 处理(PII 脱敏属 OCR 源接缝)。

## 4. 接缝:确认门(confirm gate)

- **契约要求(不变)**:任何写正式字段 / 不可逆删除前先产**待确认项数据**,**未确认绝不写**;删除非对称(高置信非医疗 no-confirm⇒删、borderline `relevance_uncertain` no-confirm⇒留永不自动删);每次 gated 动作在 `update_log.json` 留一条 ledger。待确认项数据形态见 confirm-gate.md / 契约 §3.2。
- **`<HOST_NAME>` 填法**:`<填法: 怎么呈现 / 往返?交互宿主走 inline 即时往返;headless 走 confirm-as-product——第一轮落盘待确认项 JSON、宿主 UI 收决定、第二轮回灌已确认决定再落地。>`
- **不变量(填完自检)**:沉默/推迟/"随便"/关闭 = no-confirm 不写;高置信非医疗 no-confirm⇒删(删前必告知"沉默=删")、borderline no-confirm⇒留;矛盾两值并陈交用户裁、关键字段绝不既成事实;候选检测/分类是 LLM 判断(不跑硬编码关键词名单);无匹配 `update_log.json` 条目不许写/删。段E / upload-reconciliation 复用这同一门(不开第二道门)。

## 5. 接缝:存储(storage)

- **契约要求(不变)**:结构化产物 + 桶(含 co-located 脱敏 MD)+ `redaction_manifest.json` 为 canonical 输出集,落在契约 §2.2 产物结构里。
- **`<HOST_NAME>` 填法**:`<填法: Phase2 产物写哪?语义判定(哪个桶/什么 canonical 名,固化为 .rename_plan.json)由 LLM 做;机械 mv/co-locate/排空暂存/生成 manifest 可由宿主 bash 做。persist 到哪——本地 FS / 对象存储 / 库?选哪些文件 persist?>`
- **段B 时序(硬约束,契约 §4.3)**:段B 像素打码必须在**任何"持久化/离开本地工作区"之前**跑,持久化的桶图才是打码版;原图永不离开本地工作区(段B 删前)。段B 本就 runtime-neutral,用同一 `run_redaction_job.py` + 同一 manifest/status 契约,你只负责"接进 persist 前"的触发时序。
- **不变量(填完自检)**:sidecar 是唯一明文边界(Phase2/段D/段B 只读脱敏 MD 不回读原图);**进桶 + 段B 打码留可浏览版不退化**回"丢原图/不进桶"(这是新设计相对旧 organize 的增量,任何 binding 不得退化);桶 `NN_` 数字前缀稳定 key、localize slug 不破坏锚点解析;暂存区综合后必须排空(`ocr_drain_incomplete` 暴露);manifest 必产且过 schema;schema 不过的 JSON 不写、dangling 锚点的 case_text 不写。

---

## 6. 填完自检(契约 §5 全局不变量 + PRD §11 验收)

1. `<HOST_NAME>` 的 5 接缝填法都不违反对应"不变量"行。
2. **sidecar 是唯一明文边界**:明文 PII 不越过 Phase1。
3. **进桶 + 段B 打码留可浏览版**:每文件 co-located 进桶,原图打码后保留且 at-rest 不留明文。
4. **未确认不落正式字段 / 不可逆删除**(确认门,无论 inline 还是 confirm-as-product)。
5. **临床保真 > 一切便利**:任何步骤不翻译/规范化/平滑临床实体。
6. **逻辑/schema/产物结构零改动**:你只换"谁执行机制",契约 §1–§4 的 inputs/outputs/schema 不变;产物与参考实现同 schema。

## 7. 相关文件

- `organize-contract.md` — 运行时中立契约(本模板的分母,所有"契约要求"行的出处)。
- `runtime-bindings/claude-code.md` — 交互式宿主参考实现。
- `runtime-bindings/headless-codex.md` — 单进程 headless 参考实现。
- `phase1-ocr.md` / `phase2-synthesis.md` / `confirm-gate.md` / `relevance-gate.md` / `upload-reconciliation.md` / `redaction-job.md` — 字段级真值出处。
