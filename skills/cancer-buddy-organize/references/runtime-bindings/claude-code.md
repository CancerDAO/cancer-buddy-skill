# Runtime Binding — Claude Code(参考实现 / reference binding)

> `cancer-buddy-organize` 在 **Claude Code** 上的运行时绑定。它把 SKILL.md 现有的具体机制(`Agent` 扇出 + reduce / in-agent `Read` 视觉 / `sips` 转码 / ≤15 图切片 / inline diff 卡)**逐接缝登记为参考实现**——不是契约,是契约的一种填法。`references/organize-contract.md` 是分母(行为不变量),本文件是分子(谁来跑)。
>
> **这是 CC binding,Claude Code 用户照此跑。** 现 SKILL.md 与各 prompt 描述的就是这条路径,行为/产物零变化(PRD §8 不退化保证)。本文件不引入任何新机制,只是把"已经在用的 CC 专有原语"对齐到契约的 5 个接缝上,使非-CC 宿主能照矩阵换填法而 CC 路径原样保留。
>
> 字段级真值仍以 `organizer-prompt-phase1-ocr.md` / `organizer-prompt-phase2-synthesis.md` / `relevance-gate.md` / `upload-reconciliation.md` / `confirm-gate.md` 为准;本文件只标"CC 用什么原语满足契约的哪条要求",不复述逻辑。

## 0. 绑定总览

| 契约步骤(`organize-contract.md`) | CC 在哪实现 | CC 用的原语 |
|---|---|---|
| Phase1 — per-file 脱敏 OCR | SKILL.md Step 3–4 + `phase1-ocr.md` | `Agent`(`general-purpose` subagent)并行扇出;worker 内 `Read` 视觉 + `sips` 解码 |
| Phase2 — 综合 | SKILL.md Step 5–6 + `phase2-synthesis.md` | 单个 `Agent` reduce;agent 自己写 `patient_dir` |
| 确认门(产物化) | SKILL.md Step 9–11 / 14 + `confirm-gate.md` | inline diff 卡(同会话即时往返) |
| 段B — 像素打码 | SKILL.md Step 13 + `redaction-job.md` | `Bash` 拉起 `run_redaction_job.py`(runtime-neutral,见 `_template.md`/§5 存储) |

CC 是唯一一个把 Phase1 **并行扇出**且把 OCR 跑在 **agent 上下文内视觉**的 binding;headless 宿主(见 `headless-codex.md`)走单进程顺序 + 外部 OCR。两者满足同一份契约。

---

## 1. 接缝:编排(orchestration)

- **契约要求(不变)**:所有 sidecar 在 Phase2 前就绪。
- **CC 填法**:`Agent` 工具**扇出 + reduce**。SKILL.md Step 2 按子目录/文件数切片(单 message 内 N 个并发 `Agent` 调用 = 并行 Phase1 worker;worker 内文件顺序跑);Step 4 是 per-slice continuation loop(只重发 context 撑满的 laggard slice);Step 5 在**每个** worker 回报 `continuation_needed: false` 后,发**单个** `Agent` 做 Phase2 reduce;Step 6 coverage gap retry 直到 `coverage_complete: true`。
- **为什么这样满足契约**:契约只要求"Phase2 前所有 sidecar 就绪",不要求并行。CC 用并行扇出是**性能选择**(73 图档案 ~33min→~3×),不是契约义务——其中立性正体现在 `headless-codex.md` 用单进程顺序填同一接缝、产物不变。
- **CC-specific,可被替换的部分**:`Agent` 扇出 / continuation loop / N-并发 message 全是 CC 多 subagent 编排原语;非-CC 宿主用自己的 job 队列或单进程顺序填此接缝。
- **不变量(任何 binding 含 CC 都不得违反)**:worker 间不共享 context(结构性强制 anti-anchoring——每 worker 只见自己那片);Phase1 worker **只**写 sidecar 暂存区 + `10_原始文件/` 镜像,**绝不**碰 INDEX/timeline/profile 等全局产物(否则与并行实例竞态)。

## 2. 接缝:OCR 源(OCR source)

- **契约要求(不变)**:每文件产一个脱敏 sidecar MD(`SOURCE`/`CONFIDENCE` 头 + 逐字脱敏正文 + `## PII` trailer);sidecar 是下游唯一读取源,不得带明文 PII。
- **CC 填法**:Phase1 worker 在**自己的 agent 上下文内**用 `Read` 工具**视觉读图**(`phase1-ocr.md` Step 2C:对 JPEG/PDF/图直接 `Read`,逐行转录文字图、给非文字图出 stub)。强制 PII 脱敏成 `[PII_MASKED]` 在 worker 内逐行语义判断完成。
- **为什么这样满足契约**:契约规定"产脱敏 MD",不规定"用什么识别"。CC 用 in-agent 视觉是因为 Claude 本身具备多模态读图能力,省一个外部 OCR 依赖。
- **CC-specific,可被替换的部分**:in-agent `Read` 视觉。headless 宿主用 `codex -i` 视觉或沙箱内 PaddleOCR 填此接缝(`headless-codex.md` §2);产出的 sidecar MD 结构必须逐字相同。
- **不变量**:anti-anchoring(不跨文件"纠正"、矛盾两边都记 verbatim、不调和);unreadable→`[OCR_UNCERTAIN]`、未知名→verbatim+`[CANDIDATES]`;无采样无预算上限;只动 PII token 绝不动临床字符;只写 per-file sidecar 不写全局产物。

## 3. 接缝:图像解码(image decode)

- **契约要求(不变)**:给 OCR 源一张可读栅格。
- **CC 填法**:`sips -s format jpeg -Z 1500 <heic> --out <jpg>`(`phase1-ocr.md` Step 2B)把 HEIC 转 JPEG 供 `Read` 视觉。
- **CC-specific,可被替换的部分**:`sips` 是 **macOS-only** 命令——这是本 binding 最硬的平台耦合点。非-macOS / headless 宿主用 `heif-convert` / ImageMagick(`headless-codex.md` §3)或由宿主在喂图前预处理填此接缝。`sips` 不是契约,只是 CC-on-macOS 的填法。
- **host-tunable(非契约不变量)**:`-Z 1500` 长边像素是 CC 的视觉预算取值;其它解码路径可用自己的尺寸。
- **不变量**:解码只为"给出可读栅格",不改像素语义,不在此步做任何 PII 处理(PII 脱敏属 OCR 源接缝)。

## 4. 接缝:确认门(confirm gate)

- **契约要求(不变)**:任何写正式字段 / 不可逆删除前必须先产待确认项数据,未确认绝不写;删除非对称(高置信非医疗 no-confirm⇒删、borderline no-confirm⇒留);留 `update_log.json` ledger。
- **CC 填法**:**inline diff 卡**——同一会话即时往返。SKILL.md Step 9(强制显示 `review_summary.md`)→ Step 10(surface `review_flags`)→ Step 11(profile card 的"🔍 待人工确认"段)→ Step 14(段E `99_无关文件/` 处置通知)都把待确认项**直接渲染进当前对话**,用户当场答复,binding 当场落地或不落地。段C / upload-reconciliation 的 diff 卡同此 inline 往返。
- **为什么这样满足契约**:契约把"确认门"定义为产待确认项数据 + 不变量,**不规定呈现方式**。CC 因为是交互式宿主,可以 inline 即时往返,省去落盘-回灌两轮。
- **CC-specific,可被替换的部分**:inline 即时往返(同会话渲染 + 当场收答复)。headless 宿主走 **confirm-as-product + 宿主 UI 两轮往返**(`headless-codex.md` §4):第一轮把同样的待确认项数据落盘成 JSON,平台 UI 收用户决定,第二轮回灌已确认决定再落地。两种呈现皆合规。
- **不变量(load-bearing,CC 实现照样守)**:沉默/推迟/"随便"/关闭会话 = no-confirm;高置信非医疗 no-confirm⇒删(删前必告知"沉默=删")、borderline no-confirm⇒留永不自动删;矛盾两值并陈交用户裁、关键字段绝不既成事实;每次 gated 动作在 `update_log.json` 留一条。

## 5. 接缝:存储(storage)

- **契约要求(不变)**:结构化产物 + 桶 + manifest 为 canonical 输出集,落在 §2.2 的产物结构里。
- **CC 填法**:Phase2 的 `Agent` **直接写 `patient_dir`**——本地文件系统即 canonical 存储。canonical 改名 / 原子 mv / co-locate MD / 排空暂存区 / 生成 `redaction_manifest.json` 全由 Phase2 worker 在 agent 上下文内做(语义判定 + 机械搬运都在同一 agent)。`<alias>/` symlink(或退化 `alias_map.json`)也由该 worker 建。
- **CC-specific,可被替换的部分**:agent 直接写本地 `patient_dir`,且**语义判定与机械搬运同一 agent 完成**。headless 宿主把"语义判定(出 `.rename_plan.json`)"留给 LLM、把"机械 mv/persist"交给宿主 bash,并把选定文件 persist 到对象存储/库(`headless-codex.md` §5);只要结果落在 §2.2 产物结构里即等价。
- **段B 在存储侧的体现**:CC 用 `Bash` 拉起 `run_redaction_job.py`(`~/.venvs/mtb-ocr/bin/python`)——这一步**本就 runtime-neutral**(契约 §4),CC 与任何宿主用同一脚本同一 manifest/status 契约,只是"谁触发、何时触发"是宿主生命周期编排。CC 不阻塞在此 job 上(SKILL.md Step 13)。
- **不变量**:sidecar 是唯一明文边界(段D/段B 只读脱敏 MD 不回读原图);进桶 + 段B 打码留可浏览版不退化;桶 `NN_` 数字前缀稳定 key、localize slug 不破坏锚点解析;暂存区综合后必须排空;manifest 必产;schema 不过的 JSON 不写、dangling 锚点的 case_text 不写。

---

## 6. CC 不退化保证(PRD §8)

本 binding **就是现状的登记**,不是新机制。验收 §11.3 的"CC 路径回归"= 跑一遍现 organize,产物与加中立层之前逐字节相同。中立契约层加在 CC 机制**之上**:SKILL.md 的 `Agent`/`Read`/`sips`/inline 原样留作本文件描述的填法,只是现在有了"契约 → 接缝 → binding"的三层结构,让 `headless-codex.md` 与 `_template.md` 能在不碰 CC 路径的前提下换填法。CC 用户感知不到任何变化。

## 7. 相关文件

- `organize-contract.md` — 运行时中立契约(本 binding 的分母)。
- `runtime-bindings/headless-codex.md` — codex 单进程驱动草案(同 5 接缝的另一组填法)。
- `runtime-bindings/_template.md` — 第三方 host 照填的空模板。
- `../../SKILL.md` + `phase1-ocr.md` / `phase2-synthesis.md` / `confirm-gate.md` / `relevance-gate.md` / `upload-reconciliation.md` / `redaction-job.md` — 本 binding 各原语的字段级真值出处。
