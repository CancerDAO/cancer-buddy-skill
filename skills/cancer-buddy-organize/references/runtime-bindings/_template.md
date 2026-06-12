# Runtime Binding — `<HOST_NAME>`(模板 / template)

> 第三方 host 绑定模板,供 WorkBuddy / OpenClaw / OpenCode / Cursor 等照填。复制为 `runtime-bindings/<host>.md`,只替换“填法”;不得改“契约要求”。契约来源是 `organize-contract.md`。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | `<HOST_NAME>` 填法 |
|---|---|---|
| 编排 | Phase2 前所有 text-masked MD sidecars 就绪 | `<填法: 扇出 / 单进程顺序 / job 队列>` |
| LLM 输入源 | sidecar 正文和 PII locator 由 LLM 输出;纯 OCR/parser 不是临床正文或 PII 判断来源 | `<填法: 多模态视觉 / LLM file context / host file handoff>` |
| 格式适配 | 只把源文件变成 LLM-readable input | `<填法: HEIC/PDF/DOCX/表格/archive 如何适配>` |
| 确认门 | 未确认不写正式字段/不可逆删除 | `<填法: inline 往返 / confirm-as-product 两轮>` |
| 存储 | canonical 输出集;原始件逐字保存进 `raw/` vault | `<填法: 写哪、`raw/` 如何保存、persist 到哪>` |

## 1. 编排

- **契约要求**:所有源文件/content unit 都有 sidecar 后才能进入 Phase2。
- **填法**:`<描述该 host 如何遍历、切片、重试、保证 coverage>`。
- **自检**:Phase1 只写 text-masked MD sidecar(`<patient_dir>/ocr/`)+ 逐字原件(`<patient_dir>/raw/`);不写全局产物。

## 2. LLM 输入源

- **契约要求**:最终 sidecar Markdown 正文和 PII locator 必须由 LLM 生成。图片/扫描件由 LLM 视觉读;PDF/DOCX/表格/文本可先适配,但 LLM 负责最终转写、PII 判断、locator 和 Markdown 结构。
- **填法**:`<描述如何把 adapted input 交给 LLM,例如 codex -i、host file context、OpenClaw file tool>`。
- **禁止**:不得把纯 OCR/parser 的字符输出直接写成临床正文,也不得用它替代 LLM 做 PII locator 判断。它们只能做 adapter 或机械文件处理。

## 3. 格式适配

- **契约要求**:adapter 只产生 LLM-readable input 和 provenance,不是证据源。
- **填法**:`<HEIC/HEIF → raster; scanned PDF → rendered pages; DOCX → payload; spreadsheet → table payload; archive → unpacked children>`。
- **自检**:sidecar `ORIGINAL`/`raw_path` 指向 `raw/` 下的逐字原件;临时 raster/page/payload 只写在 `ADAPTER_PROVENANCE`。

## 4. 确认门

- **契约要求**:未确认不写正式字段;不可逆删除前必须有确认门或段E非对称规则。
- **填法**:`<inline card 或 confirm-as-product JSON + UI + 回灌>`。
- **自检**:关键字段矛盾并列展示;高置信非医疗 no-confirm 可删除;borderline no-confirm 保留。

## 5. 存储

- **契约要求**:输出 canonical patient_dir 产物;每个上传原件逐字保存进 `raw/` vault(按上传原样,永不像素脱敏、永不删除)。
- **填法**:`<Phase2 产物写本地/对象存储/数据库;如何把原件逐字写进 raw/;如何生成 source_inventory(每条 content unit 带 raw_path + file_id + page_range);persist 到哪>`。
- **`raw/` vault**:每条 content unit 通过 `source_inventory.json.raw_path` deep-link 回到 `raw/`(多文档源带 `page_range`)。文本脱敏只发生在 sidecar 正文。

## 6. 填完自检

- sidecar(文本脱敏 MD)是下游唯一读取源。
- `source_inventory.json` 覆盖每个输入源,每条 content unit 带 `raw_path` + 文本脱敏 sidecar。
- HTML 在文本脱敏 MD/JSON 后生成。
- 临床实体 verbatim;schema/anchor/PII gates 通过。
