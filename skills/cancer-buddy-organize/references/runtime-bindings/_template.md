# Runtime Binding — `<HOST_NAME>`(模板 / template)

> 第三方 host 绑定模板,供 WorkBuddy / OpenClaw / OpenCode / Cursor 等照填。复制为 `runtime-bindings/<host>.md`,只替换“填法”;不得改“契约要求”。契约来源是 `organize-contract.md`。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | `<HOST_NAME>` 填法 |
|---|---|---|
| 编排 | Phase2 前所有 text-masked MD sidecars 就绪 | `<填法: 扇出 / 单进程顺序 / job 队列>` |
| 抽取输入源 | 像素页：模型整页转写 = 正文，确定性引擎第二读（脚本三态对齐）；born-digital：文本层 = 正文 | `<填法: 模型读图方式 + 本宿主的确定性引擎（run_ocr_engine.py auto 顺序）+ 原生文本层>` |
| 格式适配 | 只把源文件变成 LLM-readable input | `<填法: HEIC/PDF/DOCX/表格/archive 如何适配>` |
| 确认门 | 未确认不写正式字段/不可逆删除 | `<填法: inline 往返 / confirm-as-product 两轮>` |
| 存储 | canonical 输出集;原始件逐字保存进 `raw/` vault | `<填法: 写哪、`raw/` 如何保存、persist 到哪>` |

## 1. 编排

- **契约要求**:所有源文件/content unit 都有 sidecar 后才能进入 Phase2。
- **填法**:`<描述该 host 如何遍历、切片、重试、保证 coverage>`。
- **自检**:Phase1 只写 text-masked MD sidecar(`<patient_dir>/ocr/`)+ 逐字原件(`<patient_dir>/raw/`);不写全局产物。
- **worker 标识与存活**:`<填法: 如何生成 worker 标识；如何观测“10 分钟无新产物写入或连续 30 次只读工具调用”；如何终止并重派单文件 worker；stub worker 如何写 [INGESTION_BLOCKED: timeout]>`。契约要求：编排者/宿主管线从不自己写 sidecar 或结构化 JSON；每次派发、终止、重派都进入 `update_log.json` 的 `workers[]`/`degradations[]`。

## 2. 来源保真抽取

- **契约要求**:像素页（照片、无文本层的扫描页）的字符真值是模型整页多模态转写；正文定稿后由
  `second_read_align.py` 调用确定性 OCR 引擎做第二读并三态判定（一致 / 无信号 / 冲突，只有冲突出 token）。
  born-digital 页的文本层就是正文，不跑 OCR。保存引擎、版本、原始输出、`body_sha256` 和文件 hash。
- **填法**:`<本宿主模型如何看图；可用的确定性引擎（apple_vision / tesseract / none）；方向统一（run_ocr_engine.py orient）；通道值（text_layer / table_parser / deterministic_ocr:<engine> / barcode / human / llm_vision）>`。
- **独立性**:`INDEPENDENT_REREAD: true` 仅当两次读取的通道类别不同、第二读不是 `none` 也不是 `llm_vision`，且引擎至少读出一个高风险字段；模型再看一遍图（含裁剪放大、换会话换模型）永远不是独立复读。
- **禁止**:引擎文字进入正文；worker 在写正文前运行 OCR 或读引擎输出；手写 token / 复读表；为通过门换参数重跑引擎。
  冲突的高风险字段不得进入 settled-fact surface；“无信号”只记单通道读取，不出 flag。
- **`[HEADER]` sidecar 头字段集**:恰好 12 个键，按序 SOURCE / FILE_ID / EXTRACTOR / PRIMARY_CHANNEL / SECOND_READ_CHANNEL / INDEPENDENT_REREAD / READ_MODE / ADAPTER / CONFIDENCE / SHA256 / PAGE_LABEL / MODALITY（`organizer-prompt-phase1-ocr.md` §3）；头部块不做 PII 扫描，出现其他键即校验错误；`EXTRACTOR` 是 worker 标识，不能是 orchestrator/main/manual/host/self/user。

## 3. 格式适配

- **契约要求**:adapter 保留可审计的原生/OCR 字符层和 provenance；LLM 视图是辅助输入。
- **填法**:`<HEIC/HEIF → raster; scanned PDF → rendered pages; DOCX → payload; spreadsheet → table payload; archive → unpacked children>`。
- **自检**:`source_inventory.json.raw_path` 指向 `raw/` 下的逐字原件;临时 raster/page/payload 只记在 `adapter_provenance`。

## 4. 确认门

- **契约要求**:未确认不写正式字段;任何不可逆删除都必须逐项显式确认。沉默不删除。
- **填法**:`<inline card 或 confirm-as-product JSON + UI + 回灌>`。开跑前的“是否已有比本次更新的资料”也走这里；非交互宿主做成不阻塞的待确认项。
- **自检**:关键字段矛盾并列展示且保持 disputed；患者确认不晋升临床真值；所有 no-confirm 文件均保留/隔离。

## 5. 存储

- **契约要求**:组织期间在受控 `raw/` 中保存上传字节，不静默覆盖、变换或删除。保留/删除
  由宿主的认证、授权、审计和生命周期策略执行。
- **填法**:`<Phase2 产物写本地/对象存储/数据库;如何把原件逐字写进 raw/;如何生成 source_inventory(每条 content unit 带 raw_path + file_id + page_range);persist 到哪>`。
- **`raw/` vault**:每条 content unit 通过 `source_inventory.json.raw_path` deep-link 回到 `raw/`(多文档源带 `page_range`)。文本脱敏只发生在 sidecar 正文。
- **`[DEID]` raw/ 文件名**:使用与身份无关的文件名；原上传名作为受保护 provenance，不进入派生
  交付面。文件名去标识不等于文件内容匿名。

## 6. 填完自检

- sidecar(文本脱敏 MD)是下游唯一读取源。
- `source_inventory.json` 覆盖每个输入源,每条 content unit 带 `raw_path` + 文本脱敏 sidecar。
- HTML 在文本脱敏 MD/JSON 后生成。
- 来源临床字符串保留；派生翻译/规范化带标签且不覆盖来源；schema/anchor/PII gates 通过。
- **`[GATE]` 验收门**:`write_organize_meta.py` 之后运行 `validate_structured_outputs.py`（审计与下游检查加 `--readonly`），检查 schema、anchor、source-shape、sidecar 头部、inventory、
  PII shape 和 HTML form，不判断临床正常/异常。另需 Phase 2.5 来源忠实度与 PII 语义复扫。
  共享前还必须认证并确认 recipient/scope/purpose/expiry、执行最小化且排除 `raw/`；任一门不可用即
  fail closed。
