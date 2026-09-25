# Runtime Binding — grok（headless CLI / `grok --prompt-file` 与交互模式通用）

> grok 的编排工具是 `spawn_subagent`、`get_command_or_subagent_output`、`kill_command_or_subagent`、`monitor`、
> `run_terminal_command`、`read_file`、`write`、`search_replace`。本文件只写“填法”；契约来源是 `organize-contract.md`，
> 与 `claude-code.md` 同一组不变量。**headless 下没有唤醒机制：回合结束就等于进程退出**（§7）。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | grok 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | `spawn_subagent(background=true)` 并行派 Phase 1，`get_command_or_subagent_output` 循环阻塞等待；单个 Phase 2 subagent |
| 抽取输入源 | 像素页：模型整页转写 = 正文，确定性引擎第二读（脚本三态对齐）；born-digital：文本层 = 正文 | subagent 用 `read_file` 看正向副本转写；`second_read_align.py` 跑 Apple Vision / tesseract |
| 格式适配 | 只把源文件转成可读输入 | `sips` / `pdftoppm` / `run_ocr_engine.py orient`，临时文件放 `<patient_dir>/raw/_extract/` |
| 确认门 | 未确认不写正式字段/不可逆删除 | headless：confirm-as-product 待确认项；交互：`ask_user_question` |
| 存储 | canonical 输出集 | 本地 `patient_dir`；原件逐字进 `raw/` |

## 1. 编排

- **派发**：`spawn_subagent(description=…, prompt=…, background=true)`。`prompt` = 参考文件**原文**（或写明其绝对路径并要求
  完整阅读）+ `## Call parameters`；不改写、不删节、不写“只读某几段”。`spawn_subagent` 没有 cwd 参数：Call parameters 里给出
  `skill_dir` 与 `patient_dir` 的**绝对路径**，所有命令写成 `python3 "<skill_dir>/scripts/…"`；子代理在 `patient_dir` 下工作，
  **不要** `cd` 进 `<skill_dir>`（技能目录只读，见 §6）。
- **等待**：`get_command_or_subagent_output(task_ids=[…], timeout_ms=900000)` 循环调用，直到返回完成；两次调用之间不要发出
  不含工具调用的消息（§7）。
- **存活**：用 `monitor` 跑一个只打印新写入的命令（Phase 1 看 `<patient_dir>/ocr/` 的新文件与修改时间，Phase 2 看
  `<patient_dir>` 下 `.rename_plan.json` 与各 JSON）。**10 分钟无新产物写入，或连续 30 次只读工具调用**（读 worker 自己的提示词文件与被点名的参考文件不计入只读次数） →
  `kill_command_or_subagent(task_id=…)` → Phase 1 已写完的 sidecar 保留，其余每个文件派单文件 worker（`p1-<source_id>-<n>`）；
  再超时 → stub worker（`p1stub-<source_id>`）写 `[INGESTION_BLOCKED: timeout]`，然后停下报告。Phase 2 同一提示词重派一次，
  再失败即停下报告。每次派发、终止、重派都向 `<patient_dir>/raw/_dispatch_log.jsonl` 追加一行（`{at, event, worker_id, phase, files}`）。
- **自检**：编排者从不自己写 sidecar、结构化 JSON 或 HTML，也不用脚本代写。

## 2. 来源保真抽取

- **填法**：像素页（照片、`text_layer_kind.py` 判 `embedded_ocr` / `absent` 的 PDF 页）由 subagent 用 `read_file` 看
  `run_ocr_engine.py orient` 写出的正向副本做整页转写（`llm_vision`，`READ_MODE: model_vision_primary`）；正文遮蔽落盘后跑
  `second_read_align.py --apply`。本宿主的引擎按 `run_ocr_engine.py which`：macOS 有 `swiftc` → `apple_vision`，否则
  `tesseract`，都没有 → `none`（全部“无信号”）。born-digital 页用 `pdftotext -layout` 文本层做正文，`--text-layer` 只做同一性核对。
- **独立性**：引擎读独立于模型；subagent 再用 `read_file` 看一遍图（含裁剪放大）永远是 `llm_vision`，不是第二读。
- **禁止**：写正文前运行 OCR 或读 `raw/_extract/` 的引擎输出；手写 token 或复读表；为过门换参数重跑引擎。
- **`[HEADER]`**：恰好 12 个键（`organizer-prompt-phase1-ocr.md` §3）；`EXTRACTOR` 是 worker 标识。

## 3. 格式适配

- HEIC：`sips -s format jpeg <原件> --out <patient_dir>/raw/_extract/<stem>.jpg`；PDF 像素页：`pdftoppm -r 200`
  渲染到 `raw/_extract/`；再 `run_ocr_engine.py orient` 写正向副本（旋转角进 `adapter_provenance`）。
- 临时文件一律放在 `<patient_dir>/raw/_extract/`，不放全局可读的 `/tmp`。
- **自检**：`source_inventory.json.raw_path` 指向 `raw/` 下的逐字原件；临时图只记在 `adapter_provenance`。

## 4. 确认门

- headless（`--prompt-file` 单次运行）：开跑前的“是否已有比本次更新的资料”写成不阻塞的待确认项；没有用户回答就按“未确认”处理，
  不删除任何文件，不把自述升格为临床事实。
- 交互：`ask_user_question` 当场确认；沉默、推迟 = 未确认。

## 5. 存储

- Phase 2 写 canonical `patient_dir`；原件逐字进 `raw/`（去标识文件名）；`source_inventory.json` 每条 content unit 带 `raw_path`。
- 段D HTML 只由 `render_html_template.py` 渲染。

## 6. 填完自检

- 编排者与子代理都**不写** `<skill_dir>` 下任何文件（不用 `write` / `search_replace` / `run_terminal_command` 的 `sed -i`、`rm`
  改技能，也不在技能目录里新建辅助脚本）；发现技能缺陷 → 在该步停下，向 `raw/_dispatch_log.jsonl` 追加
  `{"event": "skill_defect", …}` 并写进最终报告。`--final` 会重算技能指纹，与 `organize_meta.json` 不一致即报
  `skill_changed_since_meta`。
- sidecar 是下游唯一读取源；HTML 在文本脱敏的 MD/JSON 之后生成；schema / anchor / PII 门全过。

## 7. 回合纪律（headless 下回合结束即进程退出）

- organize 是一次性长任务（约 1.5–2 小时）；终点是 Step 17 `validate_structured_outputs.py <patient_dir> --final` 打印 OK 行。
- **终点之前不得发出不含工具调用的消息。** grok headless 没有唤醒：一条不含工具调用的消息就结束回合、进程退出，后台 subagent
  随之丢失。发出前先跑 `python3 "<skill_dir>/scripts/validate_structured_outputs.py" <patient_dir> --can-stop`；退出码 5 就照它打印的
  下一步继续。
- 急症早报（Step 7.5）、review_summary、时效句、补料信号、进度，都与下一次工具调用放在**同一条消息**里输出，最终报告再汇总。
- 有后台 subagent 时只用 `get_command_or_subagent_output` 阻塞等待（或 `monitor` 轮询产物），不写“完成后我会继续”之类的结束语。
- 唯一合法的提前结束：真的被阻塞（缺凭据、需要用户决定、技能缺陷），并写明原因与恢复命令。
