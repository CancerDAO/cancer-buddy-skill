# Runtime Binding — `<HOST_NAME>`(模板 / template)

> 第三方 host 绑定模板,供 WorkBuddy / OpenClaw / OpenCode / Cursor 等照填。复制为 `runtime-bindings/<host>.md`,只替换“填法”;不得改“契约要求”。契约来源是 `organize-contract.md`。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | `<HOST_NAME>` 填法 |
|---|---|---|
| 编排 | Phase2 前所有 text-masked MD sidecars 就绪 | `<填法: 扇出 / 单进程顺序 / job 队列>` |
| 抽取输入源 | 确定性原始字符层 + provenance；LLM 只做版面、候选纠错、语义辅助 | `<填法: OCR/parser/原生文本 + 独立复读 + LLM review>` |
| 格式适配 | 只把源文件变成 LLM-readable input | `<填法: HEIC/PDF/DOCX/表格/archive 如何适配>` |
| 确认门 | 未确认不写正式字段/不可逆删除 | `<填法: inline 往返 / confirm-as-product 两轮>` |
| 存储 | canonical 输出集;原始件逐字保存进 `raw/` vault | `<填法: 写哪、`raw/` 如何保存、persist 到哪>` |

## 1. 编排

- **契约要求**:所有源文件/content unit 都有 sidecar 后才能进入 Phase2。
- **填法**:`<描述该 host 如何遍历、切片、重试、保证 coverage>`。
- **自检**:Phase1 只写 text-masked MD sidecar(`<patient_dir>/ocr/`)+ 逐字原件(`<patient_dir>/raw/`);不写全局产物。

## 2. 来源保真抽取

- **契约要求**:图片/扫描件使用适用的确定性 OCR/表格/条码抽取；born-digital 文件保留原生
  文本/单元格。保存引擎、版本、原始输出、source span 和文件 hash。
- **填法**:`<描述原始字符层、第二独立读取、LLM 版面/语义复核和人工复核如何衔接>`。
- **禁止**:LLM 不得成为唯一字符真值；候选纠错不得覆盖 `raw_text`。高风险字段两次读取不一致
  时必须 `needs_human_review`，不得进入 settled-fact surface。
- **`[HEADER]` sidecar 头字段集**:SOURCE / READ_MODE / ADAPTER / ADAPTER_PROVENANCE / CONFIDENCE / FILE_ID (stable source_id, rename-survivable) / optional MODALITY / ORIGINAL。

## 3. 格式适配

- **契约要求**:adapter 保留可审计的原生/OCR 字符层和 provenance；LLM 视图是辅助输入。
- **填法**:`<HEIC/HEIF → raster; scanned PDF → rendered pages; DOCX → payload; spreadsheet → table payload; archive → unpacked children>`。
- **自检**:sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件;临时 raster/page/payload 只写在 `ADAPTER_PROVENANCE`。

## 4. 确认门

- **契约要求**:未确认不写正式字段;任何不可逆删除都必须逐项显式确认。沉默不删除。
- **填法**:`<inline card 或 confirm-as-product JSON + UI + 回灌>`。
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
- **`[GATE]` 验收门**:`validate_structured_outputs.py` 检查 schema、anchor、source-shape、inventory、
  PII shape 和 HTML form，不判断临床正常/异常。另需 Phase 2.5 来源忠实度与 PII 语义复扫。
  共享前还必须认证并确认 recipient/scope/purpose/expiry、执行最小化且排除 `raw/`；任一门不可用即
  fail closed。
