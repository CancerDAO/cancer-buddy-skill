# Changelog

All notable changes to `cancer-buddy-skill` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — organize 审计日志防篡改：派发日志与运行账本交叉核对、账本哈希链、worker 提示词哈希 (2026-09-26)

case3 把一次 kill 改写成 `retried` 并删掉对应的 degradation；Phase 2 被派了 3 次；p2-2 / p2-3 的提示词被编排者改写成“只读这几段”，
pii-2 的提示词里预先写好了裁决。合成数据，无真实病例内容。

- **派发日志 ↔ 账本**（新校验门 `provenance`，独立模块 `scripts/_gate_provenance.py`；只在 `raw/_dispatch_log.jsonl` 存在时运行）：
  日志里每条 `kill`，账本里必须是 `status: killed`（或 `timeout`）并有 degradation——改成 `retried` / `done` 或删掉 degradation 都
  ERROR；Phase 1 的 kill 之后必须有覆盖其文件的派发 / 重派事件；同一个 Phase 2 任务（首次派发 + kill 之后的重派）超过 2 次即
  ERROR `phase2_retry_exceeded`；日志行不是 JSON 即 ERROR。
- **账本哈希链**：新脚本 `scripts/update_log_append.py <patient_dir> --entry -|<file>` 追加条目并写 `prev_sha256`（上一条目规范 JSON
  的 sha256；新账本首条为 null），`--check` 复算整条链。校验器在任何条目带 `prev_sha256` 时逐条复算：事后改过的旧条目 →
  ERROR `update_log_chain_broken`；链开始后又出现不带链的条目 → ERROR；`--final` 时两条以上条目却完全没有链 → 一条 WARN
  （旧账本与本仓库以前的夹具都没有链，因此不报错）。phase2 §8 改为只经管道交给该脚本追加，不手写、不改已有条目。
  残余风险：最后一条条目之后没有后继，改它不会断链——它由派发日志交叉核对兜底。
- **worker 提示词哈希**：phase1 / phase2_5 / pii-rescan 的返回 JSON 带 `prompt_file_sha256`（对自己那份提示词文件跑 `shasum -a 256`），
  Phase 2 照抄进 `workers[].prompt_file_sha256`（可选字段）；校验器与技能自带文件比对，不同即 ERROR。**这只能把 worker 绑定到
  盘上的原文件**（编排者另写一份删节版让 worker 去读，哈希就不同）；编排者把提示词原文粘贴进派发时，脚本无法证明粘贴的文字
  没被改写——那一段仍是提示词规则：SKILL.md 不变量 4 新增一句“worker 提示词 = 参考文件原文（或路径 + 完整阅读）+ Call
  parameters，不改写、不删节、不写‘只读某几段’”（+141 B，SKILL.md 48,980 B），phase1 §13 要求 worker 发现收到的只是几段时改为
  完整阅读并说明。F10 因此只部分由脚本关闭。
- **PII 复扫只报告不裁决**：`pii-rescan-prompt.md` 写明命中项只由 Phase 2 `pii_remask` 或已记录的用户决定处理，派发里预设的裁决
  照样报告并在 `note` 指出。
- schema：`update_log.schema.json` 条目加可选 `prev_sha256`，`workers[]` 加可选 `prompt_file_sha256`（不升版本）。
- 测试：新增 `audit-log-guards.test.sh`（20 项：一致日志正例、kill 改写、删 degradation、Phase 1 kill 未重派、账本缺 worker、
  Phase 2 两次正例/三次负例/三个独立任务正例、坏日志行、哈希链正例与首条/第二条链接、`--check` 两种退出码、事后改旧条目、
  链中断、`--final` 无链 WARN、提示词哈希正负例、schema）。

### Fixed — organize：一个不确定标记只遮住它自己那一段；带标记的诊断/分期/方案保留字面并附另一读法；诊断按来源阶梯取 (2026-09-26)

case1 在正文乱码之外还丢了诊断：食管鳞癌第二原发、cT3N2M0 III 期、组织学与转移部位都没进结构化字段，同一行一个 token
把两读一致的“PR”连带置空；case3 两份影像指征都写了胰腺导管腺癌，`diagnosis.primary` 仍为 null。合成数据，无真实病例内容。

- **token 作用域**（phase2 §3）：把 §2.5“按受影响的那个字段算，不按整行算”搬进 §3——同一行别的字段两读一致就照常写确定值，
  不连带置 null。`diagnosis.primary / histology / stage` 与 episode 的 `regimen` 带 token 时保留“字面 + 它自己的 token”，另写
  新的可选数组 `alt_readings[]`（`{field, uncertain_id, source_ref, channel, text}`：另一通道读数与词表 high 候选），永远不升格。
  新校验门 `readings`（独立模块 `scripts/_gate_readings.py`）：`alt_readings` 所指字段为 null → ERROR（被 token 连带置空）、字段
  不带该 token → ERROR（另一读法被升格）、`source_ref` 所指行没有该 token → ERROR、指向非文本字段 → ERROR。
- **诊断来源阶梯**（判断写在 phase2 §5.7，脚本只核结果）：病理 > 出院/门诊诊断 > 申请单或影像指征 > NGS“临床诊断”栏 >
  自述（只进自述层）；`primary` 逐字照抄，所取层级写进新的可选枚举 `diagnosis_basis`。校验器：`primary` 有值而无
  `diagnosis_basis` → WARN；`profile.summary.one_line_condition` 必须带上 `primary`（去 token 后的字面），`primary` 为 null 时须写
  “诊断资料缺失” → 否则 ERROR（当前契约档案；旧版 WARN）；复读表里两读一致的诊断（“是”行）而 `primary` 为 null → WARN；两读
  一致的诊断或分期在任何结构化字段都找不到 → 完整性 WARN（phase2 同步要求在 `readiness.warnings` 写一句）。
- 段D（`case-summary-html-prompt.md`）：分期带另一读法时写“待核对（字面读作 X；另一读法 Y）”，两通道不同不再是渲染失败。
- schema：`patient_summary.diagnosis.diagnosis_basis`、`diagnosis.alt_readings[]`、`treatment_lines.episodes[].alt_readings[]` 均为
  可选（不升版本：新必填字段会把 patient_summary 推到 2.3，并牵动旧版读取路径与 SMTB 读取）。合成夹具的诊断补上
  `diagnosis_basis: discharge_or_clinic_diagnosis`。
- 测试：新增 `diagnosis-readings.test.sh`（17 项：alt_readings 四个负例与正例、episode 置空、one_line_condition 三例、三类 WARN、
  schema 四例）。段D 的“另一读法”渲染是 LLM 步骤，没有确定性测试。

### Added — organize 编排纪律：`--can-stop` 回合闸、技能目录运行期只读并在终态门复核、grok 运行时绑定 (2026-09-25)

三例 grok E2E：2/3 例在 headless 下用“阶段小结”结束回合，整个进程随之退出（case1 停在 SMTB 3.5、case3 停在 plan）；
3 例里有 3 起运行期改技能代码（case3 改 `inventory_hash.py`、case1 改 `facts.py`、case1 在技能根目录写又删了一个脚本），
而 organize_meta 仍记 `skill_dirty: false`；case1 的 段D 子代理按提示词 `cd "<skill_dir>"` 在技能目录里工作。

- **`validate_structured_outputs.py --can-stop <patient_dir>`**（X-P0-05 organize 半）：无状态——当前契约档案上
  `organize_meta.json` 不存在 → exit 5 并打印下一步（Step 17）；存在则以 `--final --readonly` 跑全部门，有错 → exit 5 并列出
  前 3 处；全绿 → exit 0。只读，不写任何文件。旧版档案（`legacy_phase2_only` 不写 meta）按门的结果放行并提示仍需升级。
  SKILL.md 抗压缩不变量新增第 6 条“回合纪律”（发出不带工具调用的消息前先跑 `--can-stop`；给用户的内容与下一次工具调用
  同条发出；后台 worker 只阻塞等待），Steps 7.5–11.4 前加一句同条输出；细则进 runtime-bindings 新的“回合纪律”一节
  （claude-code / headless-codex / _template）。D3（上游运行时展示是否延后）待用户拍板，本节**未**实现延后。
- **技能目录运行期只读并在终态门复核**（X-P1-01 organize 半）：SKILL.md 不变量第 7 条；phase1 / phase2 / phase2_5 /
  pii-rescan / case-summary-html / conversation-incremental 六份 worker 提示词各加同一句“`<skill_dir>` 在运行期只读……发现
  技能缺陷写进 `skill_defects`，不自己修”；段D 提示词不再 `cd "<skill_dir>"`（模板路径改为 `<skill_dir>/references/…`）。
  `--final` 重算 `skill_fingerprint` 与 `skill_commit` / dirty，与 `organize_meta.json` 记录的不一致即 ERROR
  `skill_changed_since_meta`。**收尾顺序保持“先写 meta、再跑 `--final`”**：计划原写“先 --final 再写 meta”，但终态门要读
  meta 里的 `pii_layer1_scan`（DoD 3）且当前契约档案缺 meta 即失败，倒序是循环依赖；这一检查比对的是“写 meta 时”与“跑门时”两个时刻：
  写 meta 之后的改动一定被抓；写 meta **之前**的改动会被 meta 如实记成改动后的指纹，本检查抓不到——那一段靠不变量 7 与
  提示词约束，是残余风险（git 检出时 `skill_dirty` 会如实为 true）。
- **grok 运行时绑定**（X-P1-03 organize 半）：新增 `references/runtime-bindings/grok-build.md`，按 `_template.md` 的段落写
  `spawn_subagent(background=true)` + `get_command_or_subagent_output(task_ids, timeout_ms=900000)` 循环阻塞等待、`monitor`
  按写入监测存活、`kill_command_or_subagent` 重派、没有 cwd 参数时一律绝对路径、临时文件放 `raw/_extract/`，以及“headless 下
  回合结束就等于进程退出、没有唤醒”。SKILL.md 运行时一段列出该文件。
- lint 13 新增 P 组：六份 worker 提示词都有只读句、SKILL.md 有回合纪律 + `--can-stop` 与只读句、grok 绑定存在且含模板全部
  段落与四个要点；`organize-contract-lints.test.sh` 新增 6 个负例。`organize-meta.test.sh` 新增 7 项：无 meta → 5、完成档案
  → 0、缺 INDEX.md → 5、未改技能 `--final` rc 0、在技能目录写入一个脚本 → `skill_changed_since_meta`（`--can-stop` 同样
  拒绝）、改一个提示词文件 → 同上（负例在复制出的技能目录上跑，不依赖本仓库工作区是否干净）。`synlib.finish_final` 复用
  Step 12–17 的收尾形状。SKILL.md 48,166 → 48,839 B（回合 427 B、只读 176 B、Step 4 幂等补第五条 47 B、绑定列表 16 B）。
- 另：Step 4 的幂等条件补上第五条（已有脚本写的 `## 高风险字段复读` 块）；`_high_risk_spans.py` 的 TNM 允许省略 M（`pT2N0`）。

### Changed — organize 读取通道：照片与扫描页由模型整页转写为正文，确定性引擎作脚本第二读（一致 / 无信号 / 冲突）；born-digital 页不再跑 OCR (2026-09-25)

三例 grok E2E 暴露：本分支让 tesseract 当像素页主通道，case1 的 21 份照片正文成了乱码（日期、分期、组织学整行读坏），
606 个不确定标记、431 条红旗；case3 在 born-digital PDF 上跑了 50 次 tesseract，118 条红旗全部是渲染页读空或读错。
本节回到 organize v3 已验证的原则（**像素页字符真值 = 多模态转写**），并把“模型不是唯一读数”落到脚本上。合成数据，无真实病例内容。

- **与 v3 的对应关系：像素页通道切换**。照片、无文本层的扫描页：`PRIMARY_CHANNEL: llm_vision`，新 `READ_MODE:
  model_vision_primary`，正文 = 模型整页转写（`[不可读]` / `?` 不猜）；写正文前不运行任何 OCR、不看引擎输出。正文写完、
  遮蔽、落盘后，**只由** `scripts/second_read_align.py --apply` 调用引擎（每页一次，之后的重跑只重放已存读数），做整页字符级
  对齐（`SequenceMatcher`、按位置映射、不做全局搜索），逐个高风险 span 判三态，并**自己写** token、`## 高风险字段复读`
  （`engine:` / `body_sha256:` / `record:` + 表格，“一致”列 `是 / 否 / 无信号`）、`## 不确定字段` 条目（转写读数 + 引擎原串与
  置信度，先过身份词表与 PII 形状遮蔽；候选照旧由 `lexicon_candidates.py` 算）以及头部 `SECOND_READ_CHANNEL /
  INDEPENDENT_REREAD / CONFIDENCE`。分母由新脚本 `scripts/_high_risk_spans.py` 从正文推出（日期、数字+单位、表格数值/参考范围/
  单位、TNM 与分期、周期号、药名/免疫组化/淋巴结站别词表命中、药名间连接符；范围条刻度行不算），worker 只能用
  `raw/_extract/<stem>.declared.json` **补报**（诊断、机构、词表外药名、`[不可读]`、版面异常）。
- **三态**（阈值写成常量：tesseract < 50、Apple Vision < 0.5，重跑后再调）：一致 → 无 token；**无信号**（没读出、低置信、
  相似度 < 0.5、不合该类语法如 `CT3M2M0` / `111期`、只丢了非数字字形、转写是词表条目而引擎差 1 字如 `INSM1`/`INSMI`、对不上
  周围已对齐文字）→ 无 token、无条目、无 flag，Phase 2 每份 sidecar 在 `readiness.warnings` 只汇总一句“N 个高风险字段中
  M 个只有单通道读取”；**冲突**（过阈值、合语法、不同：`2030-01-08`/`2030-01-03`、`顺铂`/`卡铂`、`11.5`/`115`）→ token。
  规整按类别：日期比 YYYY-MM-DD（`2026-0707` = `2026-07-07`），数字保留小数点（`11.5` ≠ `115`），`×10⁹/L` = `10°9/L` =
  `x109/L`，正文类只比字与数字不比标点（`（CT）`/`〈CT)`）。
- **防锚定**（F2/F3）：`body_sha256` = 去掉 token 的正文哈希；第二读记录 `raw/_extract/<stem>.second_read.json` 保存引擎
  当时比对的那份正文——同一 worker 之后的 `--apply` 若发现正文除 PII 遮蔽外有改动即 exit 4，校验器同样报错；第一次 `--apply`
  之后引擎读数固定，换 `--engine none` 或换引擎输出都不能让冲突消失。残余风险：宿主若在写正文前把引擎输出塞给模型，脚本
  无从得知——提示词禁止，顺序（引擎输出在正文落盘后才生成）使它很难发生。
- **`INDEPENDENT_REREAD` 语义变更（改了钉住的行为）**：`true` 当且仅当两通道类别不同、第二读不是 `none` 也不是 `llm_vision`、
  且复读表至少 1 行不是“无信号”。**引擎读独立于模型**——`llm_vision` 主读 + `deterministic_ocr` 第二读现在记 `true`（此前一律
  `false`）；模型重看自己的图 / 裁剪放大 / 换会话仍然不独立。校验器：第二读为 `llm_vision` 且写 true → ERROR（不变）；主读
  `llm_vision` 不再 ERROR；有信号行却写 false、全部无信号却写 true → ERROR；`READ_MODE model_vision_primary` 必须主读
  `llm_vision`，主读 `llm_vision` 只能配 `model_vision_primary` / `model_vision_assist` / `stub_unreadable`。
  `CONFIDENCE`：有 token 或 stub → low；独立、无 token、无“无信号”行 → high；有“无信号”行时 high → ERROR、medium 合法；
  born-digital `native_text` 固定 medium（high → ERROR）。`high_risk_review_status`：像素页只有独立且每行“是”才是
  `passed_independent_reread`，否则 `needs_human_review`（状态，不是 flag）。文书意图门不放宽：像素页上唯一的非模型读数是
  引擎，所以像素页永远只记 `layout`；只有 born-digital 页的版面异常区域可补一次 `run_ocr_engine.py read`（300 DPI）作第二个
  非模型读数。
- **born-digital 页不跑 OCR**：新脚本 `scripts/text_layer_kind.py` 逐页判 `born_digital / embedded_ocr / absent`（PyMuPDF：
  整页图覆盖 ≥ 0.85、隐形文字或 OCR 字体 → embedded_ocr；无 PyMuPDF 时退回 poppler；**不用** `pdffonts uni:no`），并列出
  `glyph_anomaly_lines`（`le!t`、夹在拉丁字母里的 `İ`）。born-digital 页正文逐行照抄文本层，`second_read_align.py --text-layer`
  只做同一性核对（`identity: n/m`，未对上的行交 Phase 2.5），`not_applicable`；字形损坏行正文不改，看图补读一次写进
  `## 文本层字形异常`。内嵌 OCR 层与 `absent` 都按像素页处理；同一原件两种页类型并存时按页类型拆 content unit。
- **Apple Vision 第二读引擎随技能附带**：`scripts/vision_ocr.swift`（`VNRecognizeTextRequest`，accurate、zh-Hans+en-US、关闭
  语言纠正；输出每行文本、置信度、bbox、前 3 个候选，键排序、数值取整，同图两次输出逐字节相同），由新脚本
  `scripts/run_ocr_engine.py` 按源码哈希编译缓存到 `~/.cache/cancer-buddy-organize/`（`CB_ORGANIZE_CACHE_DIR` 可改）；`auto`
  顺序 apple_vision → tesseract → none（`which` exit 3；只有 tesseract 时 WARN）。**方向统一**：`run_ocr_engine.py orient` 先按
  EXIF，再按引擎的文字基线方向（Vision 观测四角 / `tesseract --psm 0`）写出正向副本到 `raw/_extract/`，只打印角度、不输出文字；
  模型与引擎都看这份副本。实测 Vision 在朝向提示错误时也会读出旋转文字，按“读出字数×置信度”选方向不可靠，故改为按基线方向投票。
- **分级**（phase2 §6.1）：值类（date / number / unit / stage / drug_name / ihc_marker / ln_station / variant /
  regimen_connector / cycle_number）冲突 `legibility / red`；`diagnosis_text` 冲突 `yellow`（校验器不再强制 red）；有他页清楚
  读数支持时降一级；删除“不按‘明显是某个引擎的误识’自行排除”一句——该判断已由脚本三态完成。
- 文件：phase1 §0–§6、§13–§14 重写（§7 检验配对不在本节范围，未改）；phase2_5 独立性一段；runtime-bindings `claude-code.md`
  （L39-40 “原生文本层 + OCR 是真正独立的组合”删去）、`headless-codex.md`、`_template.md`；`organize-contract.md` Extract；
  `source_inventory.schema.json`（`read_mode` 加 `model_vision_primary`，可选 `second_read_summary`，描述改写；加值不升版本）；
  `schemas/README.md`；`SKILL.md` Step 3 与运行时一段（+273 B，现 48,166 B）；`INSTALL.md` 引擎自检；CI 安装 PyMuPDF。
  校验器新门 `second_read`（独立模块 `scripts/_gate_second_read.py`）：复读表覆盖全部推出的 span、三态可由存档引擎输出重算、
  一致/无信号处无 token 且冲突/补报处有、表与条目里的引擎读数等于引擎原串（遮蔽除外）、`body_sha256` 与正文一致且正文就是
  引擎比对过的那份；没有 `raw/` 的副本只核哈希、其余一条 WARN；词表在第二读之后改过时按记录里的 span 重算（只增不减）并 WARN。
- lint：13 新增 O 组（phase1 调 `second_read_align.py --apply`、§5.1 三态与“无信号不出 flag”、§4 D 防锚定句、schema 的
  `read_mode` 枚举 = `SIDECAR_READ_MODES` = phase1 §3 行）；**07 的 I-07 检查改写**：原来要求 phase1 写“不是唯一字符真值”，
  现在要求写明“模型转写不是唯一读数”并调用 `second_read_align.py`（`_common.sh` 的 `SKILLS_DIR` 可由 `CB_SKILLS_DIR` 覆盖，
  以便在副本上验证它会失败）。评测场景 org-07 / 08 / 21 / 22 按新通道改写。
- 测试：新增 `second-read-align.test.sh`（68 项，纯 stdlib，CI 可跑：三态、规整、词表近似、刻度行、无引擎、遮蔽、补报、
  `--check` 的 7 个负例、重放与 exit 4、TSV 归一）、`text-layer-kind.test.sh`（17 项：四类合成 PDF、坏 PDF、同一性核对、
  poppler 退路）、`vision-ocr-helper.test.sh`（21 项，仅 macOS：两次读逐字节相同、结构、三个旋转角）；`sidecar-header-gate`
  原“主读 llm_vision + true → ERROR”翻转为通过，新增无信号/有信号/READ_MODE/CONFIDENCE/born-digital 与 second_read 门 11 个负例；
  `organize-review-fixes` 加 diagnosis_text yellow 正例；`organize-contract-lints` 新增 O 组 5 例与 lint 07 三例。合成夹具新增一张
  拍照医嘱单 sidecar（`08_治疗/处方医嘱/…`，其第二读由 `second_read_align.apply` 生成，引擎输出与记录经 `synlib.make` 写入
  测试副本），因此 `organize-replay-fixes` 的两处计数由 4/5、5/5 改为 5/6、6/6。
- 在 case1 上的验证（只读归档、脚本在副本上跑、报告只给计数）：把原运行记下的 606 对读数（tesseract 原串+置信度 vs 模型读数）
  按新规则重判：一致 11、无信号 530、冲突 45（值类 10 条红、诊断/其他 35 条黄），加上原来的版面异常 19、不可读 1，合计 65 个
  token（原 606）、红旗 10。3 张照片（门诊、PET-CT、病理）按新流程完整跑一遍（模型转写 + 引擎第二读 + `--check`）：原运行这
  3 页共 64 个 token，新流程用原 tesseract TSV 为 2 个、用 Apple Vision 为 1 个，`--check` 全部通过。

### Fixed — organize 第三轮复核：转述引文按条核对，冒号或引号既不能绕过也不再误报；自述前缀、缺失的 summary 与 latest_status 类型如文档所述核对 (2026-09-25)

独立复核上一节后指出的 5 项逐条收口（合成数据，无真实病例内容）。

- **转述引文改为按条核对**（P2 回归 + P2 误报，取代上一节的“引文位置”）：上一节的引文位置解析只看冒号或开引号之后的
  位置，于是明着把转述当原文的写法——“报告原文写明充盈缺损（2030-01-05，外院胸部CT报告）”“外院报告原文提示充盈缺损
  （2030-01-05）”“报告原文：<AF1 原句>（2030-01-12，…）充盈缺损”——全部静默通过（在 93869c1 上都报 ERROR）；反过来，
  原句发现的 `verbatim_text` 自己在转述文字前带冒号或引号时（“诊断意见：充盈缺损（考虑肺栓塞）”“印象：充盈缺损。请结合
  临床”“结论：充盈缺损；建议复查”“提示“充盈缺损”。请结合临床”），按提示词原样写的“报告原文：<原句>（日期，来源）”
  也被判成引用了转述，正确的渲染过不了。现在 `translated_caveat_problems` 不再解析位置，而是**按条**核对（常量
  `ACUTE_CAVEAT_ITEM_RULE` / `ACUTE_CAVEAT_ORIGINAL_CLAIMS`）：一条 caveat 只要含有某条转述发现的 `verbatim_text`，这一条就
  必须写有“中文转述，非报告原句：”，并且除这句前缀外不得出现“报告原文”“原文写”“报告写道”“报告写明”“报告原句”。
  两处例外都只关于**别的**发现的字：嵌在另一条发现更长原句里的出现属于那条（先把这些出现抹掉再查，所以
  “<AF1>…<AF2>”里另写的一遍仍会被查到）；原句一字不差的原件发现（孪生）拥有写了它的日期、没写转述日期的那一条；
  日期也相同、无法区分时，每条孪生可认领一条不带前缀的条目，多出一条即报错（只按日期例外会让这种正确渲染无法通过）。
  `case-summary-html-prompt.md` 要求**一条发现单独一条 caveat**、转述那条不与别的发现合写，逐字写出该规则句，并写明别的
  caveat 不复述转述原句（要提到就写“<日期>外文报告的那条转述发现”）；phase2 §7、acute-findings.md §2.4、README 同步。
  取舍：句中顺带复述转述原句（上一节 TL2 当作正例的“来源冲突：两份报告对充盈缺损的范围写法不同”）现在报错——按条核对
  下它与“报告原文写明…”无从区分，提示词已要求别的条目不复述；该用例改为负例，另加按日期指称的正例。
  `validate_case_summary_html.py` 核实不重复这条规则（只查页面形状，不读急性发现），未改。
- **lint 13 N 跟随改写**：提示词须逐字（不计空白）含 `ACUTE_CAVEAT_ITEM_RULE`（它由 `ACUTE_CAVEAT_ORIGINAL_CLAIMS` 拼成，
  两侧名单不一致即失败）、须写“一条发现单独一条 caveat”、不得再写旧的引文位置规则；除原有三个实例化探针外，新增四个
  “原句自带冒号/引号”的正向探针与八个绕过写法（上面三种 + 五个称原文短语各自紧挨前缀）的负向探针。
  `organize-contract-lints.test.sh`：n6 改为“提示词退回引文位置写法”，新增 n16（校验器退回引文位置式读法）、n17（校验器
  不再拒绝前缀旁的称原文短语）、n18（提示词少列一个短语）、n19（提示词不再要求一条一发现），n8 随提示词改行。
- **自述前缀的缺失检查不再看 `summary` 块的层**（P3，文档与代码不符）：phase2 §5.7 与 `patient-profile-schema.md` 写的是
  “按该 episode 自己的说话人，与 summary 块是哪一层无关”，但缺前缀检查只在 `summary.provenance_layer` 不是自述层时才跑，
  `patient_reported` / `caregiver_reported` 块里不带前缀的自述方案整个校验 rc 0。现在去掉该条件（写错前缀仍由说话人检查
  报一次，不重复报）。
- **缺失或为 null 的 `profile.summary` 必填，且按 current_regimen null 核对**（P2/P3）：此前 `summary` 不是对象时相等关系与
  全部前缀检查静默跳过，只有流程不调用的 `validate-profile-schema.sh` 会发现。现在与 `latest_status` 对称：缺失 / null
  在当前契约档案上 ERROR（旧版 WARN），并读作 `{}`，在治 episode 存在时另报 “summary.current_regimen None ≠
  latest_status.regimen”；字符串、数组等非对象在任何档案上都是类型错误。phase2 §5.7 与 `patient-profile-schema.md` 写明。
- **`latest_status` 的类型提示两个校验器一致**（P3）：字符串或 `[]` 此前被两处都报成 “latest_status is null”，
  `validate-profile-schema.sh` 还先后打印 “must be object or null” 与 “is null — required” 两句矛盾的话；`{}` 在该脚本里
  直接 “profile schema OK”。现在两处用同一组措辞（`is missing` / `is null` / `is a JSON string|array, not an object`，
  各一行），非对象在任何档案上都是错误；`{}` 与缺 `regimen` 键的对象报 “latest_status.regimen is missing”（当前契约
  ERROR、旧版 WARN），并按 regimen null 继续核对。旧的 “latest_status missing” 措辞随之改为 “latest_status is missing”。
- 测试：`acute-findings-gate.test.sh` 新增 TL3 组（五种绕过写法、四种自带冒号/引号的原句、自带冒号的转述原句正负各一）与
  TL2 的同日孪生正负、无日期孪生正例、按日期指称正例，句中复述改为负例；`organize-provenance-guards.test.sh` 新增 R4（三种
  块层 × 说话人组合的缺前缀，各含整个校验 rc 1；正例 rc 0；错前缀只报一次）、R5（summary 缺失/null/旧版/无在治/字符串）、
  R6（latest_status 字符串/数组/`{}`）；`validate-profile-schema.test.sh` 新增类型措辞、`{}`（当前/旧版）、summary 缺失/null
  共 13 项。在上一提交（4b97bc2）的代码上实测：TL2/TL3 11 项、R4–R6 15 项、profile 10 项（其中 2 项为措辞改名）失败；
  把两个新常量补进旧校验器后，新 lint 在旧的引文位置实现上报 12 处违规（4 个冒号/引号探针 + 8 个绕过探针）。同日孪生正例
  已核实：去掉计数、只按日期例外时它会报错。

### Fixed — organize 第二轮复核：正确的渲染不再被转述检查卡死，缺失的 latest_status 不再让在治快照核对整体跳过 (2026-09-25)

独立复核上一节后指出的 5 项逐条收口（合成数据，无真实病例内容）。

- **转述引文只在引文位置核对**（P2，上一节引入的误报；已由「第三轮复核」一节改为按条核对——引文位置可被“报告原文写明…”绕过，也会被原句里的冒号误触发）：上一节的检查把转述发现的 `verbatim_text` 在全部 caveats 里做
  子串计数，转述文字恰好是另一条原句发现正确写出的“报告原文：…”的一部分时（“充盈缺损”“胸腔积液”这类短语，同一档案
  既有旧转述 sidecar 又有中文原件时就会发生），完全正确的新鲜渲染也被判 ERROR，没有任何写法能通过，段D 拿不到
  `template_sha`。现在只看**引文位置**（常量 `ACUTE_CAVEAT_QUOTE_SLOT_RULE`：冒号或开引号之后，其后紧接“（”“；”“——”
  “。”或该条结尾；按占满这个位置的最长一条发现原句计）：别的发现原句里含有这几个字、或句中顺带提到，不算引用；两条发现
  原句一字不差时按引文后括号里的日期区分。引文位置上的转述前面必须紧挨着“中文转述，非报告原句：”（可隔一个开引号），
  不论引导语是“报告原文：”“外院报告写道：”还是没有引导语——原有负例（“报告原文：”引转述、同一条既标转述又称原文、附带
  发现）照旧报错；不再核对的只有引文位置之外的顺带提及。`case-summary-html-prompt.md` 与 phase2 §7 同步收窄。lint 13 N
  不再只钉字符串：提示里须逐字（不计空白）含该规则句、不得再写“caveat 里出现转述发现的 verbatim_text 时”，并把提示自己的
  两种 caveat 写法实例化后跑 `translated_caveat_problems`——转述写法通过、“报告原文”写法引转述被拒、转述文字嵌在另一条
  原句里不算引用；提示与校验器任一侧漂移（含校验器退回子串计数）lint 即失败。
- **缺失或为 null 的 `latest_status` 按 regimen null 核对，且为必填**（P2，早已存在）：上一节的相等关系和更早的在治快照
  检查都只在 `latest_status` 是对象时才跑，删掉它就整体跳过——`current_regimen` 写成别的方案、另有在治 episode 也照样通过。
  现在两者对称：缺失/null 的 `latest_status` 读作 `{regimen: null}`（在治 episode 存在时报“regimen null although … ongoing”，
  `current_regimen` 非 null 时报 ≠），它本身在当前契约档案上报 ERROR（旧版档案 WARN）；`scripts/validate-profile-schema.sh`
  同样要求它（当前契约档案缺失或 null 即失败，旧版 WARN）。`patient-profile-schema.md` 与 phase2 §5.7 写明；上一节“缺这个键
  按 null 算”现在对两个键都成立。`validate-profile-schema.test.sh` 里当前契约档案的正例补上 `{"regimen": null, …}`。
- **自述前缀按 episode 自己的说话人核对，单独的前缀不是 null**（P3）：`summary` 块本身是自述层时，写错说话人的前缀
  （家属陈述的 episode 写“患者自述：…”）此前能通过；现在前缀必须对应在治 episode 的 `provenance_layer`，与 `summary`
  块是哪一层无关。只有一个“患者自述：”、去掉后为空的 `current_regimen` 不再等同于 null，报错。
- **资料卡同样标注转述**（P3）：`profile-card.md` 的急性/附带发现一条不再统称“报告原文写明的”，`verbatim_is_translation:
  true` 的条目标“中文转述，非报告原句”；`acute-findings.md` §2.4 的展示面清单加上 Step 11 Profile Card。lint 13 N 钉住两处。
- **按旧契约写成的渲染在流程内重渲染**（P3，迁移路径）：旧首句“资料中有报告原文写到…”的渲染带着仍然匹配的
  `acute_findings_sha256` 戳会被判为新鲜渲染并报 ERROR，而此前只有新增/改动急性发现才强制 Step 12，增量或
  `legacy_phase2_only` 运行会带着自己修不了的 ERROR 结束。现在：SKILL.md Step 12 在任何校验输出含
  `ERROR: .case_summary_data.json` 时必做（不询问，新鲜度提问的安全例外同样覆盖）；phase2 §9 允许留下这类行（除了
  “the pinned stale notice … is missing”——那是 Phase 2 自己的 §7 过期提示，必须补上），§10 此时返回
  `case_summary_rerender_required: true`；`acute-findings.md` §11 同步。校验器对旧首句的 ERROR 写明“渲染早于当前 段D
  契约，戳只证明数据不证明契约”（常量 `RETIRED_ACUTE_SUMMARY_LEAD`）。lint 13 N 钉住 Step 12 / §9（含例外）/ §10 三处。
- 测试：`acute-findings-gate.test.sh` 新增 TL2 组（复核探针、只嵌在原句里、句中顺带提及、原句以转述文字加“（”开头、
  开引号内的带前缀转述、原句与转述一字不差各 1 正 1 负，以及“报告原文：”“外院报告写道：“…””、句首裸引、无括号、转述自带
  “（”等保留负例），`organize-provenance-guards.test.sh` 新增 R3 组（`latest_status` 缺失/null/旧版/无在治、说话人错配两向、
  单独前缀两例），`validate-profile-schema.test.sh` 新增缺失/null 与旧版 WARN 三例，`organize-contract-lints.test.sh` 新增
  n6–n15。在上一提交（93869c1）的代码上实测：TL2 的 6 个“此前被误报”的正例、R3 的 8 项、profile 的 4 项全部失败，
  n6–n14 的 9 个 lint 负例在旧 lint 上失败（n15 针对本节新增的例外句）；保留负例在新旧代码上都报错。

### Fixed — organize 复核遗留：转述的急性发现不再被称为“报告原文”，自述与摘录的层级规则由校验器兑现 (2026-09-25)

独立复核上一节后留下的矛盾与漏洞逐条收口（合成数据，无真实病例内容）。

- **病情概要首句改为中性写法**（P1）：固定前缀由“资料中有报告原文写到需要尽快告知治疗团队的发现：”改为
  “资料中有报告写到需要尽快告知治疗团队的发现：”——`verbatim_is_translation: true` 的发现也在这个列表里，不能说成
  “报告原文”。转述的那一条写“<label>（<日期>，中文转述）”（无日期写“<label>（中文转述）”，不与原句登记的同名发现合写）；
  caveats 里含它原句的那一条写有“中文转述，非报告原句：”（按条核对，见「第三轮复核」一节）。校验器 `validate_structured_outputs.py` 的 段D 检查同时核对两处
  （常量 `ACUTE_SUMMARY_LEAD` / `ACUTE_LEAD_TRANSLATION_MARK` / `ACUTE_CAVEAT_TRANSLATION_PREFIX`）：新鲜渲染出错即
  ERROR；过期渲染里的紧急发现走原有过期提示路径（没有提示 ERROR、有提示 WARN、`--final` ERROR），附带发现的转述标注在过期
  渲染上只 WARN（它不强制重渲染）。`validate_case_summary_html.py` 仍只查页面形状，不读急性发现。旧写法的首句在盖了新戳的
  渲染上现在报错（“must start …”），Step 12 据此在流程内重渲染（见「第二轮复核」一节）；Phase 2 的过期提示把旧前缀的首句视为全部未写入。lint 13 新增 N：
  `case-summary-html-prompt.md` 逐字含这三个常量、且不再教旧前缀，phase2 §7 引用的也是同一前缀。
- **`current_regimen` 与 `latest_status.regimen` 的相等关系真正核对**：去掉“患者自述：/家属自述：”前缀后必须等于
  `latest_status.regimen`（没有在治 episode 时两者都为 null；缺这个键按 null 算，缺 `latest_status` 同样按 regimen null 算，见「第二轮复核」一节），不论 `summary` 块是哪一层；此前只在两者
  恰好相同时才查前缀，措辞不同或干脆缺键的 `current_regimen` 都可以通过。反方向也核对：在治 episode 是原件时
  `current_regimen` 不带自述前缀。合成夹具的 `profile.summary` 补上 `current_regimen`（生成器与提交产物同步）。
- **领域桶里的对话记录不算原件**：`03_病程与叙事文书/conversation_notes/…` 这类路径此前被当成原件——
  `function_description` 可以只凭一段对话通过，自述与原件冲突的 flag 也不按 yellow 核对。现在任何含 `conversation_notes`
  段的路径都按对话记录处理（两处共用一个判定）；phase2 §5.7 / §6.1 与 schema 描述同步。
- **资料时效与校验器认同一批摘录**：`source_freshness.py` 原来只认子桶与清单 `source_kind`，头部 `SOURCE:
  prior_archive_digest` 的摘录和被标 `prior_archive_digest_unrecognised` 的未标记摘录仍按文件名日期算进“最新资料日期”。
  现在四种都排除（头部用校验器同一个解析器读）。
- **摘录放错位置的提示不再误导**：头部已标明是摘录、却不在子桶也没有清单行时，提示原来说“它的事实不会被认作既往史”，
  而校验器早已凭头部认出它；现改为“凭头部已按摘录核对，但三种标记不一致，`legacy_upgrade` 会重新归档”。
- **规则优先级写死**：
  - 检验表的 `lab_column_pairing` flag 一律按 phase2 §5.1 分级（有候选值 legibility/yellow，全部拒配 artifact/red）；
    旧 sidecar 自己写的“列错位”只逐字进这条 flag 的 `issue`，不改 `kind`、不另写 artifact flag——§5.1 优先于 §4.0 的
    旧 flag 版面分级（后者只管某个字段读数的不确定）。
  - 旧结构化文件里已有、本次只有未标记摘录支持的值（分子结果尤其）按 `legacy_value_unsupported` **保留**：值与旧
    `source_refs` 照旧，flag 引该摘录行；`prior_archive_digest_unrecognised` 的“不写进结构化记录”只约束新取的事实。校验器
    在旧版档案上对这种引用报 WARN，有 `legacy_value_unsupported` flag 时说明是保留的旧值，没有时说明缺这条 flag。
- **日期借用只有一个口径**：acute-findings §5 的 `exam_date` / `report_date`、§6 的 `prior_date_stated`、§7 的时间线日期都直接
  指向 §2.2「日期借用」（同目录、同文件名日期、同机构段的另一页），不再写宽泛的“同一份报告的另一页”。
- 测试：`acute-findings-gate.test.sh` 新增 TL 组（旧前缀、未标转述、标在别的条目上、caveat 称“报告原文”、过期与
  `--final`、附带发现、无日期、同一 caveat 既标转述又称原文），`organize-provenance-guards.test.sh` 新增 D2 / U2 / R2 / F2 / C3 组，并把上一节两个
  不能区分新旧代码的负例改为核对错误内容（`P` 查 JSON 解析报错而非找不到文件 `-`，`T schema` 查类型错误而非未知键），
  `source-freshness.test.sh` 新增头部摘录与未标记摘录各一对正负例，`organize-contract-lints.test.sh` 新增 N 组；
  `organize-replay-fixes`（B3 未注明日期的家属自述）与 `organize-v21-links`（无在治 episode）两个正例场景补上与之相符的
  `current_regimen`（“家属自述：示例方案B” / null）。
  在上一提交（6c69146）的代码上实测：本节新增的 25 项校验器/脚本检查全部失败（18 个负例、4 条提示措辞检查、2 条过期路由
  检查、1 条前缀常量检查；测试与合成夹具取本节版本），新增正例全部通过；lint N 的 4 个负例在旧 lint 上失败、正例通过；改写的两个旧负例在 8626e44 上失败。

### Fixed — organize 旧档案只重跑综合：新急性发现必然进入病情简要总结，来源层不再混用 (2026-09-25)

旧版档案只重跑 Phase 2 时暴露的矛盾与缺口逐条定死（合成数据，无真实病例内容）。

- **新的紧急发现必做重渲染**（覆盖上一条“由新鲜度提问决定”）：新登记或改动了 emergent/urgent 发现后，Step 12 直接
  重新生成 段D，不询问；非交互宿主与旧版档案同样（段D 照读现有 JSON，不升级档案）。渲染之前，Phase 2 在
  `review_summary.md` 开头与 `readiness.json.warnings[]` 各写一条固定过期提示（phase2 §7，校验器常量
  `CASE_SUMMARY_STALE_NOTICE`，逐条列出总结里还没有的发现）；这句话在重渲染后仍属实，不必回删。校验器：渲染过期
  （戳不同、没有戳，或只有 HTML 没有渲染数据）而任一处缺提示 → ERROR（旧版档案同样，它是安全面）；两处都有 → WARN；
  `--final` 上任何过期首句都是 ERROR（增量、上传对账、段E 移回之后同样，移回返回 `case_summary_rerender_required`
  时回到 Step 12）；在旧版档案上重渲染后仍漏写 → ERROR。lint 13 新增 M：phase2 §7 的 ```text 块逐字含该常量。
- **旧档案只重跑综合有了名字** `run_mode: legacy_phase2_only`（SKILL.md Step 1/5/17、phase2 §0/§4.0/§10）：只在旧版档案、
  没有新文件、用户暂不做一次性重新转写时选；明确 §4.6 清单与 `INDEX.md` 不重写，§5 各领域、§6、`case_text.md` /
  `timeline.md` / `review_*.md` 重写；`timeline.json` 带 `conflict_group` / `acute_finding_id` 键，影像事件的 `detail` 必须
  写出急性发现（没有独立事件，`timeline.md` 也不加行）；`longitudinal_observations.json` 用当前版本号；旧 sidecar 没有
  `PAGE_LABEL` 时缺页是“无法检查”（返回 `missing_pages_groups: null`、`page_continuity_checked: false`）；放错来源层的
  旧值按层规则移位，找不到原文的旧值 `legacy_value_unsupported` 引旧记录所引的 sidecar 行；旧 flag 改成说明时保留旧编号；
  旧 flag 文字或 sidecar 自己的说明写了版面观察即按 `artifact` 分级（检验表的 `lab_column_pairing` flag 除外，见下一节）。
- **旧档案摘录只凭三种标记使用**：子桶、清单 `source_kind`、头部 `SOURCE: prior_archive_digest`。校验器的用途检查补上
  头部标记（此前只认前两种，导致正确的 `prior_archive` 标注报“无摘录来源”、错误的 `source_reported` 漏检）。没有任何
  标记、内容像摘录的 sidecar 写 `prior_archive_digest_unrecognised`（other/yellow，仅旧版档案）并要求 `legacy_upgrade`，
  不从它新取事实（旧结构化文件里已有、只有它支持的值按 `legacy_value_unsupported` 保留，见下一节）；校验器报出任何引它的
  记录（旧版档案上为 WARN）。
- **一条记录一个来源层**：引了摘录的记录必须是 `prior_archive`，不能与本次原件同块（此前只查“只引摘录”的记录，
  `diagnosis`、`demographics`、`profile.summary` 混引摘录可以通过）；`one_line_condition` 只由本次原件拼成。
  `prior_archive` 或 `as_of: null` 的体能条目不进 `longitudinal_observations.json`（校验器核对不引摘录）。
- **自述不以原件面目出现**：`profile.summary.current_regimen` 等于 `latest_status.regimen`，在治依据是自述时保留
  “患者自述：/家属自述：”前缀（校验器核对——相等关系到下一节才真正核对；`treatment_lines` 不加前缀）；
  `demographics.function_description` 只收医生文书原文，schema 描述改为同一口径，校验器核对它出现在所引原件（不含对话记录、
  `14_患者自管补充/`；领域桶里的 `conversation_notes/` 到下一节才排除）里。
- **外文转述标明是转述**：`acute_findings.json` 新增可选 `verbatim_is_translation`，与该 sidecar 的
  `foreign_language_paraphrase` flag 双向绑定（校验器，所有档案）；Step 7.5、acute-findings §11、段D caveats、
  `safety-guardrails.md` 一律标“中文转述，非报告原句”。这条 flag 覆盖所有只有中文转述的外文 sidecar（检验、HLA 等）。
  Phase 2 返回的 `acute_findings_urgent[]` 带 `verbatim_text` 与 `verbatim_is_translation`，Step 5 列出它。
- **同一份报告按检查身份判定**（acute-findings §2.2，phase2 §2.5 用同一定义）：同一模态、同一次检查（检查号/申请号或
  检查项目与日期）、同一机构，或 sidecar 写明同属一份；以不同日期命名的图像所见页与印象页仍是一份报告，每个发现只
  登记一次。日期借用仍只限同目录、同文件名日期、同机构段的另一页（校验器可核对）；跨页的危急值说明单独登记为
  `critical_result_flag`。
- **连写印象**：“请结合临床/建议复查”归属读不出时两种读法各推一遍，类别相同才并入最近的可登记所见，否则单独登记
  一条引整行的 `clinical_correlation_requested`。另定：结节（含“考虑炎性结节”）不入肺部炎症类；病理/细胞病理的
  “请结合临床”不登记；影像印象的诊断性用语（“考虑转移”）按诊断名进 phase1 高风险清单。
- **旧 flag 拆分**：高风险字段（免疫组化、药名、日期、诊断、站别等）只要在 sidecar 里能定位就一律单独成 flag；只有
  “顺带提到”且“定位不到”两条同时成立才进 `warnings[]`。
- **检验旧表**：没有 `## 列配对` 的旧 sidecar 经标准输入交给 `pair_lab_columns.py`（`--text -`，新增 `--columns -`），
  Phase 2 不在 `raw/` 下写任何中间文件（旧档案可能没有 `raw/`）；sidecar 里“列错位”之类的记录逐字写进 flag 的 `issue`。
  写入者白名单写明 Phase 2 在 `raw/` 下只写 `_SIDECAR_MAP.md`、只把旧产物移入 `_legacy_<ts>/`。
- **其他口径**：影像申请单指征“on X”的用药行 `use_status: active_reported`（schema 描述同步）；“某科日间化疗”算日间单元；
  同页重复照片的年龄与体能同一口径（算一处）；“截止现在已经 N 个周期”按累计次数写 `unknown`；医生嘱托过、档案里没有
  结果的检查是 `requested_by_clinician`（yellow）；“清楚读数”按受影响的字段算而非整行；锚点行号按 `splitlines()` 计，
  含换页符的旧 sidecar 给出读行号的命令；除终态门外，Phase 2 §9 自己的校验是唯一不带 `--readonly` 的一次。
- 测试：新增 `tests/unit/organize-provenance-guards.test.sh`（译文绑定、摘录三种标记与单层记录、时序、未标记摘录、
  自述方案前缀、功能描述、脚本标准输入；16 个负例中有 14 个在旧校验器上失败，另两个——`T schema` 只查“被拒”、
  `P --columns -` 畸形输入只查退出码——在旧代码上也会通过，下一节改为核对错误内容后 16 个全部在旧校验器上失败）；`acute-findings-gate.test.sh` 的过期组按新规则
  重写（无提示 ERROR、有提示 WARN、只有一处或不点名 ERROR、`--final` 一律 ERROR、只有 HTML 的旧档案）；
  `organize-contract-lints.test.sh` 新增 M 组。

### Fixed — organize 收尾不再删除患者原件；段D 过期与漏写分开；终态门与 段C 形状补齐 (2026-09-25)

- **收尾删除范围**（P0）：此前 Step 17 的 `rm -rf "$src"` 在普通文件夹输入时会删掉用户自己的输入文件夹，在
  `legacy_upgrade` 时会删掉档案的原件库 `raw/`，而且发生在终态门之前。现在 Step 1 只在解压压缩包时建
  `unpack_dir=$(mktemp -d)`（并记下路径），Step 17 在 `--final` 之后只删这个目录，且只在它位于 `$TMPDIR`（或 `/tmp`）
  下时删；路径丢了就留给系统清理，不猜、不通配。lint 13 新增 L：SKILL.md、`references/*.md` 与运行时绑定里任何
  递归 `rm` 的参数含 `$src`、`raw` 路径或患者目录即失败（`organize-contract-lints.test.sh` 各配变异测试与正向对照）。
- **段D 过期 vs 漏写**：段D 渲染前由新脚本 `stamp_case_summary_sources.py` 在 `.case_summary_data.json` 写入它读到的
  `acute_findings.json` 的 sha256（`acute_findings_sha256`，schema 新增可选字段）。校验器据此区分：戳与当前文件一致而
  病情概要首句漏写 emergent/urgent 发现 → ERROR（读到了却没写）；戳不同或没有戳 → WARN「段D stale」，由新鲜度提问决定
  是否重渲染（非交互宿主不重渲染的规则不变）。`--final` 在没有戳、或最后一次改写急性发现的运行是 `full` / `legacy_upgrade`（这两种
  运行的 Step 12 在 Phase 2 之后渲染）时仍报 ERROR，并要求渲染数据带戳。此前增量、上传对账、移回运行新增急性发现后，
  Phase 2 §9 与终态门都无法通过。“最后一次改写急性发现的运行”把 段E 的移回（`relevance_disposition`，Step 14，在 Step 12
  之后）也算在内：整理收尾时移回一份含紧急发现的报告，同样只报 WARN、等新鲜度提问。段D 管线第 3 步另跑一次 `--readonly`
  校验，渲染自己的首句错误当场修。一次性代价：本契约下、盖戳之前渲染的档案，下次 `--final` 会因缺戳报错，重跑一次 段D 即可
  （这类档案只来自本分支的开发运行）。
- **终态门**：`--final` 另要求 `timeline.md` 与 `case_text.md`（phase2 §0 每次都写）；合成夹具补上这两份文件。
- **段C 冲突 flag**：第 3 步逐键列出 readiness schema 要求的 8 个键（`id`、`category`、`affected_field`、`kind`、
  `severity`、`issue`、`current_source_values`、`resolution_status`），不写其他键。校验器新增一行：一边是患者/照护者
  自述（`conversation:` 锚点或 `SOURCE: patient_supplement` / `14_患者自管补充/` 的 sidecar）、另一边只有一份原件的
  `conflict` flag 必须是 `yellow`；合成夹具里家属自述对 CT 的 flag 由 red 改为 yellow。
- **写入者白名单**：不变量 3 与 `organize-contract.md` 写明 段C 另写 `<桶>/conversation_notes/*.md`；phase2 §0 改为
  “结构化 JSON 只能由 Phase 2 与 段C worker 写”。
- **图表脚本路径**：编排者与 段D 调用写成 `python3 "<skill_dir>/../cancer-buddy-charts/scripts/render_chart.py"`；lint 13 J
  不再豁免 `../cancer-buddy-charts/`，只接受 `<skill_dir>/scripts/` 与 `<skill_dir>/../cancer-buddy-charts/scripts/`。
- **评测场景** org-09 / org-21：写明页 B 先处理（Phase 1 在 sidecar 条目里引 `ocr/` 路径，Phase 2 的 flag 引桶内
  sidecar），并接受页 B 后处理时只由 Phase 2 flag 记录旁证。
- **公开仓卫生**：一条测试日志条目里的运行时间换成虚构值；`.gitignore` 忽略本机的 `tests/fixtures/organize-gold/`；
  新增本地 pre-push 钩子 `tests/eval/hooks/pre-push-real-phrases.sh`（安装见 CONTRIBUTING.md）：推送前逐个检查尚未
  发布的提交的新增内容与提交说明是否含私有短语清单里的短语，某次提交加入、后续提交删掉的短语同样拒绝；只报提交、
  文件、行号与清单序号。测试：`tests/unit/pre-push-real-phrases.test.sh`、`acute-findings-gate.test.sh`（S1 组）、
  `organize-round2-guards.test.sh`（Z1、C2 组）。

### Changed — organize 提示词与流程：第二轮审查与三例回放的矛盾逐条定死 (2026-09-25)

- **路径**：所有 worker 提示词、SKILL.md 与运行时绑定里的脚本一律写成 `python3 "<skill_dir>/scripts/…"`（子代理的
  工作目录不是 skill 目录）；lint 13 新增 J（相对路径或绑定自带的基路径即失败）与 K（不可信内容 flag 的分级行与
  `scan_untrusted_markers.py` 一致），`organize-contract-lints.test.sh` 各配变异测试。
- **写入者白名单**（SKILL.md 不变量 3、`organize-contract.md`、`claude-code.md`）：Phase 1 / Phase 2 / 段C / 段D 各写
  自己的产物；编排者只经固定动作写（清单脚本、`library/index.json` 初值、`raw/_dispatch_log.jsonl`、
  `record_gap_ask.py`、`fill_agents_md.py`、`write_organize_meta.py`、终态门、段D 快照、收尾清理）。派发记录落盘到
  `raw/_dispatch_log.jsonl`，上下文压缩后 Phase 2 仍能认出被终止 worker 的完整 sidecar。
- **段C**：两次派发（`propose` 只返回差异卡、`write` 凭 `user_confirmation` 写入）；时间线事件按当前封闭形状写
  （`conflict_group` / `acute_finding_id` 必写，不写 `speaker_role` 等），冲突用 `conflict_group` + conflict/yellow flag；
  自述年龄不进 `age_observations`；旧版档案上只写记录与事件、不写日志条目。`legacy_upgrade` 带回的对话事件同样规整。
- **上传对账“替换”**：旧 sidecar 与锚点原地不动，清单行写新增可选字段 `superseded_by`（校验器核对它指向另一行），
  新事件写 `supersedes_event_id`，随后对新来源增量综合；`user_decisions` 增加 `replace` / `coexist` / `ignore`。
- **段E 移回**：`restore` / `reclassify` 之后对移回的来源做增量综合（清单、各领域、急性发现、缺页、时效）。
- **只问一次**：`gap_asks.json` 恢复为账本，新增 `gap_asks.schema.json` 与唯一写入者 `scripts/record_gap_ask.py`
  （同日一次、拒绝后不再问、`pending` 隔 30 天最多再问一次）。
- **存活**：定义“只读调用”；Phase 2 批量复核并写回 `reviewed: true`，每完成一个领域就写出；Phase 1 长文书分段写出，
  缺 `## PII` 尾注的半成品由单文件 worker 续写。Phase 1 的他页候选只看本切片已写出的文件，PII 复扫只扫自己的 sidecar。
- **旧版档案上只重跑 Phase 2**：不做头部检查与搬迁，无头部的旧摘录原地保留、事实标 `prior_archive`；按周期拆开的旧
  episode 合并、方案名逐字重取；时效三字段照写（校验器旧版分支按 `as_of_run_date` 复算，不一致只 WARN）；旧值找不到
  原文支持时保留并标 `legacy_value_unsupported`。旧版 `patient_summary` 的提示只列真正缺的时间锚字段。
- **回放中两种读法的规则**（急性发现、分级、用药、治疗事件）：同一份报告的定义（同目录、同文件名日期、同机构段）；
  每份原报告各自登记；连写印象不按位置猜归属；压缩性/非阻塞性肺不张、骨病灶描述、血管狭窄包绕、小叶间隔增厚不登记；
  影像/检验报告针对所见的检查建议登记为 incidental，病理/分子的后续检测说明不登记；类名是路由桶，下游只展示
  `label` / `verbatim_text`；不在比较表里的用语照写进 `verbatim`；侧别是时不变字段；高风险字段不按多数投票；原文用字
  反常但各通道一致不算不确定；“他页”只算同一文书或同一标本；拆分旧 flag 的编号；“出院带药”嘱托句不是标题；
  `order_role` 的支持用药范围；同日多张申请单各一行；照抄句先剔除再判同日冲突；手术与单纯放疗不成 episode；
  月份精度的自述日期不进 `started_at`。
- **其他**：只有压缩包解到 0700 的临时目录 `unpack_dir=$(mktemp -d)`，Step 17 在终态门之后只删这一个目录（`$src`、`raw/` 与用户的输入文件夹永不删除，见下节）；资料卡在 Phase 2.5 之后展示；新患者先建目录、再做
  输入清单、再切片，旧档案摘录的 `source_id` 接在句柄之后；段D 的急性发现首句同一 label 合写全部日期；非交互宿主不
  自动重渲染病情简要总结；公开代码与测试注释不再引用仓库外的设计文档；回放脚本跳过真实档案时不打印路径。
  新测试：`organize-round2-flows.test.sh`、`regress-path-withheld.test.sh`；评测场景 org-23…org-25。

### Fixed — organize 第二轮审查与回放：新增的机读守卫 (2026-09-25)

每条都配“不加这道门就失败”的负向测试与正向对照（`tests/unit/organize-round2-guards.test.sh`，另见各门原有测试）：

- **检验候选**：`labs.schema.json` 规定有 `candidate_value` 的行只能是 `linear_position` 或新增的 `llm_row_read`
  （模型按行读表、没有确定性坐标：`value` 为 null、`pairing_confidence: low`）；`bbox` / `native_table` /
  `single_value` 行不能带候选。`## 列配对` 记录写 `native_table` / `table_parser` 时 sidecar 头部必须有
  `text_layer` / `table_parser` 通道，写 `llm_row_read` 时必须有 `llm_vision` 通道且全部 `value` 为 null，并配
  legibility/yellow flag。旧 sidecar 的按行 Markdown 表改走 `pair_lab_columns.py --columns`，只出候选。
- **未注明日期的自述**：`status_as_of_precision: undated_self_report` 时 `provenance_layer` 必须是
  `patient_reported` / `caregiver_reported`（schema）；过去式、没写停或换的自述写 `status: unknown` 并同样标
  `undated_self_report`；累计周期数不写 `cycle_label_verbatim`。
- **HLA 分型日期**：`hla_typing[]` 新增可选 `report_date`（分型报告自己的日期，校验器核对它是所引报告的文件名日期
  或印在报告上）。可选字段，不升版本。
- **急性发现**：`provenance_layer` 只能是 `source_reported`，`source_ref` 不得指向旧档案摘录；
  `change_vs_prior.prior_date_stated` 必须印在所引报告（任一行或同一份报告的另一页）上；紧急用词上调只沿 §3
  写明的去向：`thrombus_embolism`（大面积/骑跨 → emergent）与 `other_source_flagged`（尽快/立即/急诊 → urgent；
  “新发/较前加重”只对继发阻塞性改变）。`pneumonitis_ild_suspected` 等没有上调，“新发”只进
  `change_vs_prior.direction`。`acute-findings.md` §4.1 的固定用词块改为逐类的上调路线，lint 13 同步核对。
- **flag 类别**：`foreign_language_paraphrase`（外文报告只有中文转述，每份 sidecar 一条，other/yellow）；
  `legacy_value_unsupported`（旧版档案里 sidecar 找不到原文支持的旧值，保留并标 other/yellow；当前契约档案上出现即
  ERROR，那里是锚点缺口 other/red）。不可信内容标记的分级表按脚本写（最高命中 high → yellow，其余 info），
  Phase 2 在校验器并入 `UNTRUSTED-*` 之后再写 `review_flags.md` 与计数。
- **终态门 `--final`**（SKILL.md Step 17）：当前契约档案必须有 `organize_meta.json`、`INDEX.md`、`review_summary.md`、
  AGENTS.md、`病情简要总结.html`，`ocr/` 为空，且最后一次入档运行之后的日志条目里有 `phase2_5` worker；OK 行回显
  HTML 的 `template_sha256`。Phase 2 §9 仍不带 `--final`。
- **Phase 2.5 留痕**：Step 11.5 每次都接一个 `faithfulness_patch`，它追加自己的日志条目（不再改写以前的条目），
  `workers[]` 记 Phase 2.5 worker（`phase2_5`）与自己；旧版档案上不写条目，返回 warning。
- **patient_code**：SKILL.md Step 2 钉死 `"PT-" + secrets.token_hex(5).upper()`（各 schema 只收大写十六进制）。

### Changed — organize 急性发现是安全面，每次运行都写，旧版档案也写 (2026-09-25)

- `acute_findings.json` 不再是当前契约的标记：旧版档案上只重跑 Phase 2 的运行同样写它（`timeline_event_id` 为
  null，不往旧 timeline 加事件，事件随 `legacy_upgrade` 补上），写了也不会把档案判成当前契约。校验器对它的 schema、
  固定 acuity 表、引文逐行绑定与日期在任何档案上都报 ERROR；只有“缺文件”（旧版 WARN）与“每条发现恰有一条
  `acute_finding` 时间线事件”（只在当前契约档案上要求）随档案代际变化。旧版档案上 段D 叙述没有以急性发现开头
  记 WARN（由新鲜度提问触发重渲染），当前契约档案上仍是 ERROR。
- Phase 2 返回 JSON 增加 `acute_findings_urgent[]`；SKILL.md Step 7.5 在每种运行方式下（含旧版档案上只重跑
  Phase 2）都先展示 emergent/urgent 发现。测试见 `tests/unit/acute-findings-gate.test.sh`（R1 组）。

### Fixed — organize 公开仓只留虚构内容 (2026-09-25)

公开仓里标为“合成”的评测场景、参考示例与夹具中，有若干句子和一张检验表是按真实病例原句照抄或只改了个别字、
个别数字写成的（不含直接标识，但合在一起可被认出）。本节把它们全部换成新编的内容，语义与测试断言不变：

- `tests/eval/scenarios/cancer-buddy-organize.md` org-07…org-22 的输入句（影像印象、病理签发语、NGS 免责句、
  周期计划句、家属自述、免疫组化误读、淋巴结站别、HLA 行、剂量阴影）全部重写，部位、数字、日期与措辞均为新编；
- `references/acute-findings.md` §2.1/§2.2/§5/§9 的示例、`treatment_lines.schema.json` 的自述示例、phase1/phase2
  提示词里的若干示例改为新编写法；
- 合成夹具的检验表换成另一组项目、顺序、参考范围、数值与版面（`make_syn_current.py` 重新生成 `syn-current/`，
  `syn-lab-columns/src/linear.txt` 同步），门诊、CT、家属自述 sidecar 的句子重写；相关测试的期望值同步；
- 新增 `tests/eval/lint/14-real-phrase-denylist.sh`：维护者把真实病例短语清单放在仓库之外，用 `CB_REAL_PHRASES_FILE`
  指向它，lint 在 `skills/`、`references/`、`tests/` 与根目录文档中发现清单短语即失败（只报文件、行号与清单序号，
  不回显短语）；未设置时 SKIP。`tests/unit/real-phrase-denylist.test.sh` 覆盖命中、未命中、空清单与缺文件。

### Fixed — organize 三例迭代的独立审查：验收门不再能被降级、改写或绕过 (2026-09-25)

独立审查（完整性 / 正确性 / 提示词三个视角）对本轮 organize 实现做对抗式探测，找到一批“写出来就能过门”的路径。
逐条收紧，每条都配一个不加这道门就会失败的负向测试和一个正向对照（`tests/unit/organize-review-fixes.test.sh`
100 例，另在各门原有测试中增补）。**三个真实病例的 O-01…O-08 验收仍待 E2E 重跑**——本节只在合成夹具与三份旧档案
只读副本上验证过。

- **当前/旧版判定**：`validate_structured_outputs.py` 只要看到任一当前契约标记——`organize_meta.json`、
  `readiness.json` ≥ 2.1、任一结构化文件处于当前版本号、带 `workers[]` 的日志条目、带
  `EXTRACTOR` 的 sidecar 头部——就按当前契约校验；写一个旧版本号或不写 `organize_meta.json` 不再能把全部 v2.1 门
  降成 WARN。`--generation <dir>` 打印判定结果与所见标记，SKILL.md Step 1 用它决定“增量更新”还是 `legacy_upgrade`
  （只含旧形状条目的 `schema_version: "1"` 日志仍判旧版）。三份真实旧档案副本仍判旧版、exit 0。
- **终态门失败即关闭**：当前契约档案缺 `profile.json` / `readiness.json` / `patient_summary.json` / `timeline.json` /
  `molecular.json` / `treatment_lines.json` / `labs.json` / `comorbidities.json` / `missing_items.json` 任一个即
  ERROR（空领域写空数组）；缺 `jsonschema` 即 ERROR（此前只 WARN 并打印“all pass”）；每道门崩溃只记一条 ERROR、
  其余门照常报告。
- **AGENTS.md**：本仓库发布过的旧模板（`KNOWN_PRIOR_TEMPLATE_SHAS`）填出的 AGENTS.md 只差模板戳和后加的路由锚点时
  记 WARN；旧版档案同理。此前三份真实旧档案因模板改动全部 exit 1。未知模板戳、stub、缺红线仍是 ERROR。
- **引文绑定**：只含省略号的引文（`……` / `...`）不再能通过任何“逐段出现在原文”的检查（脚本 + schema pattern）。
  `acuity_basis_text` 与 `change_vs_prior.verbatim` 绑定到发现所引的那几行（同一报告另一行用新增的可选
  `acuity_basis_ref`），并须含 `acute-findings.md` 新增 §4.1 固定用词：“较前无显著变化”不能把血栓下调为 incidental，
  血栓下调须“陈旧/慢性”加“较前无变化”，§3 表没有下调的类别不能用 `source_wording_chronic`。`exam_date` /
  `report_date`、`treatment_lines` 的 `status_basis_text`、用药的 `setting_basis`（逐段）都须出现在所引来源里。
  lint 13 新增 H（§4.1 块 ↔ 校验器常量）。
- **sidecar**：没有 inventory 行的桶内 sidecar 即 ERROR（其头部值此前既不绑定也不扫 PII）；`READ_MODE` / `ADAPTER` /
  `MODALITY` 与 `SHA256` 不依赖 inventory 行也校验（lint 13 新增 I）；`EXTRACTOR` 须是被派到该来源的 Phase 1 /
  重派 / 摘录 / stub worker；`## PII` 恰好一个且是最后一节；正文印着页码而 `PAGE_LABEL` 写 null 即 ERROR。
- **PII**：`pii_rescan.py` 扫头部的值（只豁免十六进制 `SHA256`）与 `## PII` 尾注，提前出现的 `## PII` 不再让其后
  正文免扫；身份词表改为每个 Phase 1 worker 一份 `raw/_identity_denylist/<worker_id>.json`（整份写，不追加共享文件），
  任一份无法解析即 ERROR（此前静默失效）；报错行只打印类别与遮蔽后的片段，不再回显号码或姓名。SKILL.md 新增
  **Step 12.5**：整理收尾前派 `pii-rescan-prompt.md` 语义复扫（sidecar + 合成面 + 交付面），发现交 Phase 1 单文件重派或
  Phase 2 新的 `run_mode: pii_remask`（phase2 §13），干净后由 `write_organize_meta.py --pii-layer1 <worker_id>` 记入
  `organize_meta.json.pii_layer1_scan`，验收门检查它（DoD 3 可在磁盘上核对）。
- **不确定字段**：`## 不确定字段` 条目 8 个键全写；`cross_doc_supported` 形状与 refs 一致；读数通道须是头部的通道；
  候选列表由新脚本 `scripts/lexicon_candidates.py`（phase1 §5 规则 1–5）算出，校验器重算比对，规则 6 只许一个替换/追加
  且须由 `cross_doc_supported` 所引的行支撑（此前部分读数的 `high` 上限 `medium` 也未执行）；每个
  `[OCR_UNCERTAIN:U-nnn]` 都须有 flag 引用；高风险字段（`field_class` 非 `other`）的 legibility flag 没有他页支撑即须
  red；schema 钉死 contradicted → red、`missing_pages` → completeness/red、`source_recency` → completeness/yellow；
  一条 flag 只写一个字段。合成夹具的 U-001 改为 `stage`、RF-001 改为 red。
- **检验列配对**：`pair_lab_columns.py` v2——`--tsv` 由脚本按词框坐标聚行、按表头定列（`bbox` 值只来自脚本）；带
  ↑↓/H/L 的结果、滴度、阴性/阳性/2+、中文单位（个/HP、秒）可识别，印刷标记记为 `flag_glyph`、不进 `report_flag`；
  数值区有无法归类的串即拒配；跨行项目名只在括号未闭合或下一行以括号/“数字（”开头时合并，单值只给一行未合并的项目；
  合并改为线性（4 万行 0.1 秒）。新门 `gate_lab_pairing`：labs.json 逐项等于 sidecar `## 列配对` 记录（```json，脚本
  输出 + `input`），`raw/` 在场时用脚本重算 `input`；位置配对须有 legibility/yellow flag、拒配须有 artifact/red flag。
  合成夹具的检验 sidecar 补上记录与 flag（`raw/_extract` 输入由 `synlib.make` 写进测试副本，仓库忽略 `raw/`）。
- **缺页、时效、日志、清单**：同一组内份数不均（第 1 页两份、第 2 页一份）报为缺页并说明可能是重复拍摄；页码语法
  补上括号、頁、`x/y页`、`P x/y`、`页码：x/y`、无分号的多页标签；机构段去掉 `s004-1` / `in-003` / 行自身的 source_id；
  每个缺页组须有 completeness/red flag，`pages_present` 一并核对。`as_of_run_date` 只能是本次（最后一次对账输入的）
  运行日期，来源日期晚于它即 ERROR；超 14 天的提示须是整句原文并配 completeness/yellow flag。超时的 Phase 1 worker
  须逐文件单独重派（夹具改为单文件 retry worker）。`skipped_inputs[].input_ref` 只收 `skip-` / `in-` 句柄或 `sNNN`，
  `digest_of.archive_ref` 只收 `PT-` 代码；`inventory_hash.py` 只忽略钉死的 `raw/` 基础设施名、符号链接记为
  `symlink` 跳过而不跟随、`.nii.gz` 等单文件压缩照常入库。桶白名单不再接受临床域下的 `raw/` `ocr/`、深于两级的目录
  与桶内原件。
- **文档**：phase1/phase2/段D/PII 提示词写入以上规则与 `skill_dir` 参数（worker 的工作目录不是 skill 目录）；
  phase2 §4.0 写明旧版档案上的非升级运行不新建 `acute_findings.json`、v1 日志条目或 `organize_meta.json`；
  `molecular.schema.json` 的 HLA 示例、phase2 的检验示例值、评测场景 org-09/org-10/org-12 改用虚构值与部位；段D
  “病情概要首句列出 emergent/urgent 发现”现由校验器检查。

### Changed — organize 三例回归迭代：不确定度分级、急性发现、检验列配对、缺页与资料时效、给药场景、旧档案摘录、执行纪律 (2026-09-25)

三例真实病例回归暴露的共同根因不在措辞，而在数据模型与执行纪律：整理层只标“不确定”、不分类型、
不给读数；急性/附带发现只留在 sidecar 正文；检验表一旦疑似错位就整表丢弃；缺页与资料时效没人检查；
用药没有给药场景；更新型病例没有正式的旧档案入口；worker 卡住后编排者自己动手写 sidecar 和 JSON。
本条目同时记录提示词、契约与文档侧，以及 schema、确定性脚本、验收门与测试侧。

- **O-01 不确定度分级**：review flag 新增必填 `kind`（`legibility|artifact|document_intent|conflict|completeness|other`）
  与 `severity`（`red|yellow|info`），可选 `cross_doc_supported`、`uncertain_ids`。**`severity` 是抽取与档案
  完整性的不确定程度，不是临床严重度**（`profile-card.md`、`organize-contract.md`、`patient-profile-schema.md`
  同步写明）。独立复读的定义钉死：两次读取的通道类别不同且都不是 `llm_vision`——大模型看图永远记
  `INDEPENDENT_REREAD: false`，两个 OCR 引擎同类也不算独立。不确定字段写成 `字面读数[OCR_UNCERTAIN:U-nnn]`，
  sidecar 的 `## 不确定字段` 块（位于 `## PII` 之前）记录各通道原始读数、只取自
  `references/lexicons/*.txt` 的候选及其机械置信度、`cross_doc_supported`、`layout` / `layout_intent`；
  候选是读数不是更正值，永不进结构化值位；个人信息字段不建条目。删除线等版面观察只有两次独立读取
  一致才可记为 `document_intent`，否则降为 `artifact`：“版面异常，字面读作 X”。下游契约：未确认的
  `document_intent` 与含 `[OCR_UNCERTAIN:*]` 的字段不得作为分期、病理、治疗推理的前提
  （`PATIENT_DIR_CONTRACT.md` §5 (c)）。
- **Sidecar 头部契约**：恰好 12 个键，按序 `SOURCE, FILE_ID, EXTRACTOR, PRIMARY_CHANNEL, SECOND_READ_CHANNEL,
  INDEPENDENT_REREAD, READ_MODE, ADAPTER, CONFIDENCE, SHA256, PAGE_LABEL, MODALITY`；`EXTRACTOR` 是 worker
  标识而不是引擎名；`CONFIDENCE` 按规则判定。原件路径与适配器临时文件不再写进头部。
- **O-02 急性与附带发现**：新增 `references/acute-findings.md`（`finding_class` → 默认 `acuity` 固定表，只允许
  三种来源用词调整：危急值标记上调、原文紧急用词上调、原文“陈旧/慢性”下调；单独的“无显著变化”不下调）。
  `acute_findings.json` 每次运行都写（无发现为 `findings: []`），每条发现在 timeline 有一条
  `category: "acute_finding"` 事件并双向链接；`change_vs_prior` 只做逐字映射，不归纳为进展或好转。
  登记单位是“一个病灶/部位/血管的一个发现”：一句话写了两处血栓就登记两条，各自映射比较用语。
  编排者在展示速查清单之前先展示 emergent/urgent 发现；段D 在页面上方“病情概要”首句列出它们
  （只用标签与日期），完整原文放在 caveats 最前面。
- **O-03 检验列配对（逐列解释）**：优先坐标或表格结构；只有线性文本时交给 `scripts/pair_lab_columns.py`，
  规则按**逐列**解释：**项目数 = 数值数 → 数值按位置配对为 `candidate_value`（`pairing_method:
  linear_position`，`value` 必须为 null）；单位、参考范围、标记三列各自计数，只有等于项目数才配，否则
  该列整列置空并记录计数；项目数 ≠ 数值数 → 全部拒配。** 迭代文档原文“四列计数一致才配”若按四列
  全等实现，会把“数值齐全、只少印一个单位”的检验单整表拒配，与迭代文档对这类检验单的验收期望（数值
  全部给出）矛盾，因此采用逐列解释。对应的两条负向样本：缺一个数值（8/7）→ 全部拒配（即迭代文档“缺一列必须拒绝
  配对”）；缺一个单位 → 数值照配、单位列置空并记计数。箭头误识字形不计入数值列；`raw_value` 只放原串，
  说明写 `pairing_note`；候选值不进入趋势和患者摘要。
- **O-04 缺页与资料时效**：`PAGE_LABEL` 逐字抄写（一份 sidecar 含多页时每页一条、以“；”分隔），Phase 2
  在搬迁之后运行 `scripts/page_completeness.py <patient_dir>`，按“日期 + 文书类型目录 + 机构 + 印刷总页数”分组
  检查印刷页码的连续性（同名 sidecar 以 `_<file_id>` 区分，不再用 `_2`，否则同一文书的几页会被拆成不同组），缺页写 `missing_items.json` `gap_type: missing_pages`（`severity: red`，`pages_present`、
  `pages_missing`、`page_total`）并加 `completeness` flag；同页号重复是重复件不是缺页。`scripts/source_freshness.py`
  以原件报告日期写 `latest_source_date` / `days_since_latest` / `as_of_run_date`，**超过 14 天**（恰好 14 天
  不告警）写 warning 与 flag。开跑前必问“是否已有比本次更新的资料”，更新型病例按 sha256 与上一版输入
  清单比对。询问话术仍按 `gap-followup.md`，不因 `severity` 改变。
- **O-05 给药场景**：用药新增必填 `administration_setting`，本版只有两条判定规则——日间单元且静脉/肌注或
  带“配”标记 → `day_ward`；“出院带药”标题之下 → `discharge`；其余一律 `unknown`（`inpatient` / `long_term`
  为预留值）。`setting_basis` 逐字写依据，可选 `order_role`；抗肿瘤药同时写进 `treatment_lines`，不产生线次。
  治疗事件新增 `status` / `status_basis` / `status_basis_text` / `status_as_of`，只按来源用语登记；`line_number`
  只在原文写明线次时填写。
- **O-06 旧档案摘录**：仅在用户明确授权后，由 Phase 1 摘录 worker 从旧档案已脱敏 sidecar 写一份摘录，
  归入新 pinned 子桶 `03_病程与叙事文书/既往档案摘录`（en `prior-archive-digest`），`source_kind:
  prior_archive_digest`、`raw_path: null`、`digest_of` 必填，事实层为 `prior_archive`，只作既往史，
  不进当前状态、不作建议依据；摘录不是上传，不参与上传对账。
- **O-07 输入清单与自述并列**：`source_inventory.json` 记录 sha256、字节数、页数、`page_label` 与
  `skipped_inputs[]`（去标识句柄 + 原因）；患者自述与原件在时间线并列，共享 `conflict_group`，自述数值
  不写进检验单。
- **O-08 人口学**：`profile.json.demographics`（`sex`、`age`、`age_as_of`、`performance_status_verbatim[]`）
  从 `patient_summary.json` 复制；体能状态逐字保留、按原文标签填 `scale_label`，不换算量表。
  HLA 分型写入 `molecular.json.hla_typing[]`。
- **O-09 执行纪律**：抗压缩不变量写明只有 Phase 1 worker 写 sidecar、只有 Phase 2 worker 写结构化 JSON，
  编排者任何情况下不手写、不脚本批写；存活规则为 10 分钟无新产物写入或连续 30 次只读工具调用即终止，
  Phase 1 改派单文件 worker、Phase 2 重派一次（从 `.rename_plan.json` 续做），再失败由 stub worker 写
  `[INGESTION_BLOCKED: timeout]` 并停下报告，全部记入 `update_log.json` 的 `workers[]` / `degradations[]`。所有 stub
  都以 `## PII` 尾注结束；worker 主动让出的 `in_progress_timeout_risk` stub 不算完成，一定改派单文件 worker；
  头部不合规的 sidecar 不算完成，由 Phase 1 重新转写。扫描件的默认确定性通道为 tesseract TSV（本 skill 不附带
  其他 OCR 脚本）。Phase 2 先写 `.rename_plan.json`，每条
  路径经 `scripts/check_bucket_path.py` 预检后才 `mkdir`/`mv`。忠实度复核后的 flag 与摘要修订改由
  Phase 2 `faithfulness_patch` 模式完成。收尾调用 `scripts/write_organize_meta.py` 写 `organize_meta.json`，
  供 SMTB 记录上游版本。
- **update_log 与确认门**：`update_log.json` 只有 `update_log.schema.json` 的条目形状；段C、段E、上传对账等确认门
  的记录改由执行写入的 worker 追加（`at` 取代 `ts`，`note` 记 actor 与用户逐项确认的原话），编排者不写
  update_log；段E 的删除与移回由新的 Phase 2 `relevance_disposition` 模式执行；“暂不重新生成病情简要总结”
  不再写 `case_summary_stale`，下次会话按同一检测规则再问（`references/confirm-gate.md` 同步）。
- **旧档案升级**：本轮之前整理的档案没有 v1 update_log，sidecar 也没有新头部。第一次更新时以 `run_mode: legacy_upgrade`
  （最初写作 `run_mode: full` + 布尔参数 `legacy_upgrade`，见下方回放修复）从档案自己的 `raw/` 重新转写全部原件，旧桶、旧 update_log 与被重写的根目录产物整体移到
  `raw/_legacy_<ts>/`（保留不删；放进受控的 `raw/`，因为旧的清单、日志与旧 sidecar 头部可能带原上传文件名），`conversation_notes/`、`alias` 与对话自述记录带回；此后按 sha256 做增量比对。
  `source_inventory.json` 的版本键 `schema` 必须写 `source_inventory_v2.1`；当前契约档案里写成旧值是“混合版本档案”错误（不再是宽松读取）。
- **分级细则**：sidecar 不确定条目带版面异常（`layout` 非 `none`）时，flag 只能是 `artifact` 或（两次独立读取一致时）
  `document_intent`，不归入 `legibility`；词表候选改为规整后编辑距离（≤ 3 字符的条目阈值 1，其余 2）、按距离与
  命中读数个数排序取前 3 的机械规则。段D 中带不确定标记的分期不再置空（否则核心完整性检查判为丢失），改写
  “待核对（字面读作 X）”。用药行必填 `medication_id`（`MED-001` 起），普通文书缺口的 `severity` 为 `info`。
- **契约与文档**：`PATIENT_DIR_CONTRACT.md` 把 smtb-skill 列为消费方并删去不存在的 vmtb 镜像声明，新增
  消费方必须遵守的七条规则（§5 (c)–(i)）；三个阶段提示词写回被掏空的操作细则（恢复的只有与“确定性优先”一致的
  部分：表格一行一绑定、剂量二读、规则化 CONFIDENCE、返回 JSON、覆盖检查、写前分桶计划、update_log；
  “大模型是唯一字符来源”“按来源优先级裁决”“建议值/用户确认”等旧段落不恢复）。`SKILL.md`
  68.6 KB → 40.4 KB（≤ 50 KiB；两轮审查修复后 44,717 字节，约 43.7 KiB），删去 11 处悬空引用。`CONTRIBUTING.md` 的一键测试循环不再无参调用
  `scripts/validate-profile-schema.sh`。
- **版本策略**：获得必填新字段的 schema 升为 `"2.1"`（`patient_summary` 为 `"2.2"`），新字段只对新版本必填；
  旧版本号的档案校验只给 warning，不再判失败。
- **Schema 版本清单**：`readiness` / `timeline` / `labs` / `comorbidities` / `treatment_lines` / `missing_items` /
  `molecular` `"2"` → `"2.1"`；`patient_summary` `"2.1"` → `"2.2"`；`source_inventory` 的 `schema`
  `source_inventory_v2` → `source_inventory_v2.1`；新增 `acute_findings.schema.json`（`"1"`）、封闭的
  `update_log.schema.json`（`"1"`，可选顶层 `patient_code` 与条目 `outputs[{file, sha256}]`）、
  `organize_meta.schema.json`；七个带来源层的 schema 的 `provenance_layer` 枚举加 `prior_archive`（加值不升版）。
  旧版本号经 `validate_structured_outputs.LEGACY_SCHEMA_VERSIONS` 用内存中放宽的 schema 读取（只去掉后加的必填
  字段，封闭形状、类型与枚举照旧），只报 WARN。档案一旦属于当前契约（`readiness.json` 为 `2.1`，或存在
  `organize_meta.json`），v2.1 各项检查从 WARN 变为 FAIL，任何结构化文件残留旧版本号都是“混合版本档案”错误，
  按新 schema 严格校验——不能靠写旧版本号绕过新必填字段。
- **确定性脚本与验收门**：新增 `scripts/inventory_hash.py`（sha256 / 字节数 / 页数 / `skipped_inputs[]`，stdout 只有
  `in-NNN` / `skip-NNN` 句柄，原名映射只写进 `--mapping-out` 指定的 `raw/_…` 文件）、`pair_lab_columns.py`（逐列
  配对）、`page_completeness.py`（印刷页码分组与缺页）、`source_freshness.py`（资料时效）、`check_bucket_path.py`
  （写前桶白名单，终态门导入同一函数）、`write_organize_meta.py`。`validate_structured_outputs.py` 新增 v2.1 门：
  急性发现 ↔ timeline 事件一一对应、`source_ref` 行锚点逐字绑定、固定表核对 `acuity`；sidecar 头部封闭 12 键块、
  `EXTRACTOR` 必须是 `update_log` 中的 worker 且不得是编排者保留名、`llm_vision` 复读永不独立、头部与 inventory
  行一致；不确定度记账（`[OCR_UNCERTAIN:U-nnn]` ↔ `## 不确定字段` 条目、候选必须是词表整行、`document_intent`
  须有两次一致的独立读取）；缺页全部登记；时效三字段按真实运行日期重算；每个原件入账或有跳过理由；旧档案摘录
  不进当前状态；`update_log` 形状与超时/终止 worker 的降级记录；`conflict_group` 至少两个事件、
  `medication_refs` 可解析、抗肿瘤用药同时是治疗事件；`profile.json.demographics` 与 `patient_summary` 一致。
  新增 `--readonly`：非 organize 本身的检查（下游、审计、回放）不写档案。合成夹具在
  `tests/fixtures/organize-regress/`（数值、日期、机构全部虚构），每个新门都有正向对照与单点突变的负向测试。
- **经批准的行为变化**（相关旧测试随之调整）：`update_log` 新鲜度检查从文件 mtime 改为 sha256（`inputs[]` 对
  `source_inventory.json`，可选 `outputs[]` 对产物），没有哈希的旧日志只 WARN；lint 07 钉死的 readiness 版本
  字面量 `"2"` → `"2.1"`，并要求旧版读取路径仍然注册；不可信内容扫描门此前传错参数、实际从未运行，现在真正
  运行并把命中合并进 `readiness.json.review_flags[]`（按 `category` + `affected_field` 去重，写前先过 schema）；
  PII 形状复扫跳过 sidecar 头块（只认已知键，未知的 `KEY:` 行照正文扫描），扫描前遮蔽十六进制摘要（sha256
  等），不再把哈希误报为长数字编号。
- **集成期对齐（提示词与共享文档对照合并后的脚本复核）**：`PAGE_LABEL` 无页码统一写 `null`（多页 sidecar 中无
  页码的那一段同样写 `null`，缺页检查记为部分无页码）；编排者用 `inventory_hash.py --mapping-out
  <patient_dir>/raw/_INPUT_HANDLES_<ts>.json` 固定句柄表并作为 `input_handles` 交给 Phase 1（句柄按整次扫描编号，
  worker 不再自行重跑对句柄）；`update_log` 条目的 `workers[].files` 只列该 worker 被派到或写出的来源（Phase 2
  综合 worker 为 `[]`），`status: timeout|killed` 必有 degradation，建议记录 `outputs[]`；段C 对话条目写
  `inputs: []`（不再照抄旧条目），比对“上一版输入”一律取最后一个 `inputs` 非空的条目；`source_freshness.py`
  必须显式传 `--as-of <as_of_run_date>`，`as_of_run_date` 与本次条目 `at` 同日，超 14 天的 warning 原样照抄脚本
  文字；治疗事件写明 schema 钉死的组合（`ongoing` ⇒ `status_as_of` 非空且依据不是 `none`；依据 `none` ⇒
  `unknown`；四类依据须有原文），家属/本人陈述以陈述提交日期为 `status_as_of`；`document_intent` flag 的机械
  条件（所引 sidecar 全部 `INDEPENDENT_REREAD: true`，`uncertain_ids` 指向有两次一致独立读取的条目）；增量运行
  也要把残留旧版本号的结构化文件按当前 schema 重写；收尾先写 `organize_meta.json` 再跑终态验收门，终态门不加
  `--readonly`，其余检查一律加；DoD 的 `template_sha` 改为取自段D 返回值（验收门本身不回显它）；根目录
  `references/preflight.md` §4 写明未确认 `document_intent` / `[OCR_UNCERTAIN:U-nnn]` 字段不作推理前提、
  `prior_archive` 只作既往史、flag `severity` 不是临床严重度，§5 把 `acute_findings.json` 的 emergent/urgent
  行接到急症路由；`safety-guardrails.md` 同步急性发现的展示口径并更正失效的章节引用；
  `patient-profile-schema.md` 写明 `demographics` 在当前契约档案上必填（两道门都会拒绝缺失或与
  `patient_summary` 不一致）、`patient_summary` 版本为 `2.2`；`PATIENT_DIR_CONTRACT.md` §6 要求消费方以
  `--readonly` 调用验收门。

- **sidecar 头部门钉死取值（验收门）**：`validate_structured_outputs.py` 的 sidecar 头部门要求恰好 12 个钉死键、按序、
  不重复、不混入旧键（`ADAPTER_PROVENANCE`、`ORIGINAL…` 等）；`SOURCE` 必须是 18 种文书类型之一；
  `PRIMARY_CHANNEL` / `SECOND_READ_CHANNEL` 只能是 `text_layer|table_parser|deterministic_ocr:<engine>|barcode|human|
  llm_vision|prior_archive_sidecar|none`；`INDEPENDENT_REREAD` 两个方向都按机械规则校验（该写 true 却写 false 同样报错）；
  `CONFIDENCE` 只能是 `low|medium|high` 且按规则推导（有不确定字段或 stub → `low`；有独立复读 → 不得写 `medium`；
  没有独立复读 → 不得写 `high`）；`READ_MODE: hybrid_verified` 必须有独立复读；`FILE_ID` 等于清单 `source_id`，
  `READ_MODE` / `ADAPTER` / `MODALITY` / `PAGE_LABEL` 等于清单行（`PAGE_LABEL` 的 `none` ↔ `null`）；旧档案摘录行
  `SOURCE` 为 `prior_archive_digest`、主通道为 `prior_archive_sidecar`，也只有摘录行可以这样写。`source_inventory.schema.json`
  的描述同步写明这些头部 ↔ 清单绑定。
- **`profile.latest_status` 绑定在治疗程**：必须等于 `status: ongoing` 疗程的 `regimen` + `status_as_of`，没有在治
  疗程时为 null（`validate-profile-schema.sh` 同步钉死形状）。
- **确定性脚本输出**：`pair_lab_columns.py` 新增 `single_value`（一个项目一个数值时直接给出 `value`）、顶层
  `pairing_method` / `pairing_confidence`、`counts.results` 与逐列结论 `column_decisions`（`paired` /
  `null_count_mismatch` / `refused_all`），sidecar 的 `## 列配对` 块照抄这些取值；`inventory_hash.py` 可以直接接收文件
  列表（worker 的切片文件、旧档案的单个文件）。
- **提示词契约 lint**：新增 `tests/eval/lint/13-organize-prompt-contracts.sh`（SKILL.md 体量 ≤ 50 KiB、词表每行一个
  词、phase1 §3 头部 12 键顺序与 `SOURCE` 列表等于校验器、`acute-findings.md` §3 表 ↔ schema 枚举 ↔ 校验器固定表）
  及其变异测试 `tests/unit/organize-contract-lints.test.sh`；评测场景 org-07…org-12；`tests/eval/README.md` 列出
  lint 10/12/13。合成夹具的 sidecar 头部改写为钉死值并重新生成。以上新门只对当前契约档案生效，旧档案只 WARN。
- **回放修复（LLM 回放暴露的提示词与契约缺口；organize 提示词与文档侧）**：三例 organize Phase 2 部分回放显示，同一份
  提示词在几处可以被读成两种结果。逐条收紧（schema 与校验器侧的对应字段由同轮 schema/脚本改动提供，字段名与之
  逐字一致）：
  - **急性发现分类**（`acute-findings.md`）：内镜/活检中的“接触性出血”不登记；“梗阻/闭塞/完全阻塞”才是
    `obstruction`，“阻塞性炎症/阻塞性肺不张”登记为 `other_source_flagged`（incidental，原文写新发或较前加重时按
    `source_wording_escalation` 升为 urgent），食管/支气管“狭窄”未写梗阻不登记；积液写“大量”或“较前增多”才是
    `effusion_large_or_increasing`，没写量也没比较、少量且稳定或较前减少的积液改为登记成 `other_source_flagged`
    （**行为变化**：此前不登记，现在保证可见但不升级）；间质性改变、药物/免疫/放射相关肺炎、未写病原的双肺或多发
    炎症 → `pneumonitis_ild_suspected`；“骨皮质扭曲”未写骨折 → `other_source_flagged`，“陈旧性”骨折按
    `source_wording_chronic` 下调；“请结合临床”只登记影像/检验中依附于具体所见的那句，病理签发套话与胚系检测免责
    建议不登记；“建议随访/复查/超声/CTA” → `other_source_flagged`；病历复述的报告结论只在原报告不在档案中时以病历为
    来源登记一次（timeline 取病历日期、`date_precision: approximate`）；同一报告拆成几个 sidecar 算一份，复合部位
    列举登记一条；病理只印收到/签发日期时 `exam_date` 为 null；单独登记的危急值/临床重要结果通知写
    `acuity_basis: source_critical_flag`，不抄通知人姓名与电话；外文报告的 `verbatim_text` 取外文原句；比较用语表
    `stable` 行补“无明显变化 / 未见明显变化 / 较前变化不大”。`finding_class` 枚举、默认 acuity 与 `acuity_basis` 枚举
    不变。
  - **治疗与用药**（phase2 §5.2/§5.3/§5.7）：周期不是线——同一方案的各周期合并为**一个** episode（`started_at` 取首程），
    周期写法进可选 `cycle_label_verbatim`，`documented_line_label` 只收带“线”字的原文；在治判定只用当次就诊记录的
    现病史/诊疗计划，不用后续病历照抄的旧句；同日几页周期序号矛盾写 conflict flag，状态仍可为 ongoing。**行为变化**：
    没有落款日期的家属/本人自述（“这个方案现在还在用”）不再借用本次运行日期，改写 `status_as_of: null` +
    `status_as_of_precision: "undated_self_report"`（`status_basis: patient_reported`）。叙述里提到、没有医嘱行的抗肿瘤药
    只进 treatment_lines，不进 `medications[]`；影像申请单指征里的在用药照写用药行并链接疗程；`order_role` 给出判别
    （冲管/溶媒 → `diluent`，输注前抗过敏/止吐 → `premedication`，“必要时”口服止吐/护胃 → `supportive`）；
    `profile.json.latest_status` 新增 `status_basis`（原样复制在治疗程的 `status_basis`），只读 profile 的下游不会把
    申请单指征当成给药记录。
  - **不确定度与 flag**（phase1 §2/§5/§6，phase2 §2/§6.1）：`layout` 加 `shadow_stain_fold`（阴影/污迹/折痕/纸面弯曲，
    归 `artifact`）；`field_class` 加 `diagnosis_text` / `regimen_connector` / `cycle_number`（都不给词表候选）；只读出
    部分字符的读数写 `?`（如 `4L?`），此时候选置信度最高 `medium`；本切片他页的清楚读法若是词表条目必须进候选；
    `cross_doc_supported` 以本处任一通道读数或候选为准判 supported，与全部读数和候选都不相容判 contradicted（red）；
    一条 flag 只对应一个字段；`current_source_values[]` 的逐通道读数带可选 `channel`；高风险字段补方案连接符、周期
    序号与病理申请单上的临床诊断；§6.1 补行——高风险字段只有自述来源 → `other`/yellow，不同日期原件对时不变字段
    矛盾 → `conflict`/red，报告写明的对照检查不在档案 → `completeness`/info，方法学或护栏说明不写 flag、写进
    `warnings[]`；`conflict_group` 也可用于原件对原件；**锚点缺口改为 `other`/red**（此前与机构待核实同为 yellow：
    没有锚点的事实不能当作已确认值使用）。行号一律按 `str.splitlines()` 计，Phase 1 把换页符等断行字符写成换行；
    外文原件按原文语言转写，正文不写 worker 评论。
  - **运行模式与版本**：新 `run_mode: legacy_upgrade` 取代 `run_mode: full` + 布尔参数 `legacy_upgrade`（**行为变化**），
    总是 Phase 1 全部重新转写 + Phase 2 全量运行；旧版档案上只重跑 Phase 2 时保持旧版本号、不转换旧日志、不写
    `organize_meta.json`，不存在“只升一部分”的升级。旧版检验 sidecar 没有 `## 列配对` 块时，Phase 2 可对其线性
    文本运行 `pair_lab_columns.py` 写候选值；sidecar 里编排者写的“不要配对”之类注释不是本 skill 的规则。资料时效
    警示全仓只有一种写法：`source_freshness.py` 的 `STALE_WARNING_TEMPLATE`（phase2 §6.2、SKILL.md Step 8、段D caveat、
    `patient-profile-schema.md` 示例同步）；`as_of_run_date` 是运行的本地日期，`update_log` 的 `at` 是 UTC，校验器容许
    ±1 天。HLA 的 `locus` 一律写裸位点字母，报告只写“杂合/纯合”时写 `allele: null` + 逐字 `zygosity`（不参与试验
    匹配）；体能状态条目可选 `provenance_layer`，旧档案摘录中的 ECOG 陈述登记为 `prior_archive`、永不作为当前体能；
    旧档案摘录必须在 `既往档案摘录` 子桶且 `source_kind: prior_archive_digest`，头部 `SHA256` 一律写 `none`，无头部
    的摘录按旧版 sidecar 重写；phase2 §4.6 写明头部 ↔ 清单逐项相同的全部字段。段D 与契约的旧档案引用标注统一为
    “来自既往摘要，原件未在本次资料中”；Phase 1 §7 的 `## 列配对` 块改用脚本的 `column_decisions` 取值与
    `counts.*` 计数。
- **回放修复（schema 与校验器侧）**：上一条提示词侧字段的机读对应，只对当前契约档案报 ERROR，旧档案只 WARN。
  - **schema 可选字段（不升版）**：`treatment_lines` 的 `cycle_label_verbatim`，以及 `status_as_of_precision`
    （`day` | `undated_self_report`）——`status: ongoing` 且 `status_as_of: null` 只允许 `status_basis: patient_reported`
    + `undated_self_report` 这一种组合，写了这个标记就必须是 null + `patient_reported`；`molecular.hla_typing[]` 的
    `locus` 为裸位点字母（`A`、`DRB1`），`allele: null` 只能与逐字 `zygosity` 同时出现，`resolution` 按字段数机械填写；
    `performance_status_verbatim[]` 条目可选 `provenance_layer`；readiness `current_source_values[]` 可选 `channel`
    （钉死的读取通道取值）；`update_log` 的 `run_mode` 写明 `legacy_upgrade`；`comorbidities` 的 `inpatient` /
    `long_term` 标为保留值。
  - **不确定条目词表**：`field_class`（新增 `diagnosis_text` / `regimen_connector` / `cycle_number`）、`layout`（新增
    `shadow_stain_fold`）、`layout_intent` 只能取钉死值；只有 `drug_name` / `ihc_marker` / `ln_station` 有候选，且只从
    各自的词表取；`high` 候选必须等于某个**完整**读数（距离 0）且与其余每个读数相差 ≤ 1，只读出部分字符的读数
    （`4L?`，也识别 `[?]` / ？ / □ / U+FFFD）不能让候选成为 `high`，`text: null` 的通道不算读数；`kind: legibility` 只用于
    `layout: none` 的条目。
  - **行号口径**（`line_breaks:`）：本契约写出的 sidecar 不得残留换页符 `\f` 等只有 `str.splitlines()` 才断行的字符
    （否则 `#L` 锚点与 `cat -n` 行号错位）。
  - **运行模式**：`run_mode: legacy_upgrade` 与 `full` 一样把全部 sidecar 纳入头部检查；混合版本与旧档案提示都指向
    `legacy_upgrade`；旧版档案上只重跑 Phase 2、保留旧版本号的档案仍走旧档案 WARN。
  - **旧档案摘录**：只引用摘录的体能陈述必须是 `provenance_layer: prior_archive`；`source_kind`、`既往档案摘录`
    子桶与头部 `SOURCE` 三处标记必须一致；无头部的摘录按旧版 sidecar 给 WARN。
  - **在治快照**：`profile.latest_status.status_basis` 必须等于在治疗程的 `status_basis`；`as_of` 只有未注明日期的
    自述形态才可为 null（`scripts/validate-profile-schema.sh` 同步）。
  - **update_log 新鲜度**：每个产物与**所有条目中最近一次记录它的** `outputs[]` 哈希比对（段C 条目不再引发“档案外改动”
    误报）；不可信内容 flag 回写后同步更新那一条的哈希。
  - **资料时效**：`STALE_WARNING_TEMPLATE` 是唯一的告警句，脚本回退日期取本地日期，时效 ERROR 引用这句话并说明
    ±1 天容差。
  - **AGENTS.md**：`acute_findings.json` 的阅读顺序行与领域表行成为 `fill_agents_md.py` 的必需锚点（改模板这两行
    必须同步改脚本）。
- **第三轮收尾（跨包请求核对后落地）**：
  - **摘录头部 `SHA256` 只能是 `none`**：当前契约档案里旧档案摘录 sidecar 的头部 `SHA256` 写成任何哈希（包括“被摘录
    档案的哈希”）或占位值都是 ERROR（**行为变化**：此前也接受 64 位十六进制）；旧档案不检查。
  - **锚点缺口的分级**：`category: anchor_coverage_gap` 的 flag 必须是 `kind: other`、`severity: red`（phase2 §6.1）；
    `schemas/anchor-contract.md` 改为直接写 `red`（§6.1 现在有两行 `other`）。
  - **半升级陷阱**：`update_log.json` 为 `schema_version "1"`、没有任何 `full` / `legacy_upgrade` 条目，而桶内有不带
    钉死头部（无 `EXTRACTOR`）的 sidecar——说明只重跑了 Phase 2 却写了 v1 日志，下一次 Step 1 会误以为已经升级、跳过
    `legacy_upgrade`。旧档案给一条 WARN；当前契约档案里**没有任何** sidecar 是本契约写出的则为 ERROR（部分 sidecar
    沿用旧转写的情形仍是原有的 carried-over WARN）。
  - **SKILL.md Step 17**：旧版档案上只重跑 Phase 2 的运行不调用 `write_organize_meta.py`（该文件一出现档案就被判为
    当前契约），DoD 第 6 项同步写明例外；phase2 §5.3 写明未注明日期的自述形态下 `patient_summary.current_status.as_of`
    同样为 null。
  - **提示词契约 lint 13 新增 F/G**：F——SKILL.md 也纳入逐行扫描，phase2 §6.2 的 ```text 块与 SKILL.md Step 8 必须原样
    含 `STALE_WARNING_TEMPLATE`（带 `{latest}` / `{days}` 占位），根目录 `patient-profile-schema.md` readiness 示例的
    `warnings[0]` 必须是用该示例自己的日期与天数填好的模板；G——phase2 §0 的 `run_mode` 列表必须含
    `FULL_RUN_MODES` 的全部取值，SKILL.md 与 `references/**/*.md` 不得再写已废弃的布尔参数
    （`` `legacy_upgrade`（布尔 `` / `legacy_upgrade: true`）。变异测试同步：E 组改用当前提示词的注释行（此前两条变异
    因提示词措辞变化而落空，检查实际没被触发）。
  - **测试**：`organize-replay-fixes.test.sh` 增加锚点缺口、半升级陷阱、B7 反方向绑定，以及体能条目
    `provenance_layer: prior_archive` 与逐通道 `channel` 在完整校验器和 `validate-profile-schema.sh` 上端到端通过
    （profile 与 patient_summary 仍逐项相等）；评测场景 org-13…org-22（合成输入）覆盖本轮回放修复的判读边界：
    接触性出血、阻塞性炎症、未定量积液、签发套话与胚系免责、病历复述去重、周期与照抄句、未注明日期的家属陈述、
    HLA 只有杂合、部分读数与他页清楚读数、折痕阴影压住剂量。

#### 与 `feat/organize-v3-multimodal-transcribe` 的对应关系（Relation to feat/organize-v3-multimodal-transcribe）

本轮以 `main` 为基线，未合并 v3 分支（v3 未跑端到端验证）。两者重叠处的对应与合并代价：

| 主题 | 本轮 | v3 分支 | 合并时怎么处理 |
|---|---|---|---|
| flag 分类 | `kind`：`legibility` / `artifact` / `document_intent` / `conflict` / `completeness` / `other`，加 `severity` | 封闭 `category`：`transcription_disagreement` / `ocr_artifact` / `source_conflict` / `coverage_gap` / `untrusted_content_marker` / `pii_semantic_deferred` / `source_faithfulness` / `other`，加必填 `audience` | `legibility`≈`transcription_disagreement`，`artifact`≈`ocr_artifact`，`conflict`≈`source_conflict`，`completeness`≈`coverage_gap`，`other`≈`untrusted_content_marker` / `pii_semantic_deferred` / `source_faithfulness`；`document_intent` 是本轮新增，v3 无对应。`audience` 与 `severity` 正交，可并存 |
| update_log | `{schema_version:"1", entries:[{at, run_mode, workers[], inputs[{source_id, sha256}], added[], removed[], degradations[], note}]}` | `{runs:[{run_id, run_mode, started_at, added_sources[{source_id, read_mode}], pii_semantic, faithfulness_method}]}` | 两者记录的是不同维度（本轮：新鲜度按输入 sha256 判断，sidecar 来源按 worker 标识核对，另记 worker 降级；v3：语义 PII 与忠实度方法）。合并需要统一成一个条目形状，并迁移已有档案 |
| 页完整性 | 读页面上**印刷的**“第 x 页，共 y 页”，按日期 + 文书类型目录 + 机构 + 总页数分组找缺页（档案缺了原件的某一页） | 按渲染页计：每个可读渲染页都必须有转写（转写流程丢页） | 两者互补，不互相替代，合并时应同时保留 |
| 第二读取独立性 | 通道类别不同且都不是 `llm_vision` | “不同模型”也可算独立通道 | 口径冲突，合并前需要决定是否承认“另一个模型”为独立通道 |
| 未覆盖 | — | v3 不含急性发现、检验列配对、给药场景、旧档案摘录、人口学、worker 超时降级 | 这些只在本轮 |

### Fixed — 年龄/体重/ECOG 是时点观测，跨年份取值不同不再被判成来源冲突 (2026-08-05)

用户反馈：同一患者跨年份的多份报告一起 organize 时，年龄"没法自动随年份变化，会自动判别冲突"。

**根因（结构层，不是判断层）**：`patient_summary.schema.json` 把 `age` 建成一个**无时间锚的裸标量**，
和真正时不变的 `sex` 并排放在 `demographics` 里。于是 2023 年报告的 52 岁和 2026 年报告的 55 岁被
映射进同一个槽 → `organizer-prompt-phase2-synthesis.md` §2 的"不同来源冲突并列保留、不按最新优先裁决"
命中 → 标 `disputed`。而 `disputed` 的唯一解除路径是"出具机构的正式更正或授权临床人员签认"
（`upload-reconciliation.md`），**年龄永远拿不到这种签认，所以永久挂冲突**，下游
`case_summary_data.age`、病情简要总结 HTML、Profile Card 冲突卡跟着报冲突或置空。
同一份 schema 的 `current_status` 有 `as_of`、`longitudinal_observations` 每条观测有 `timestamp`
——契约本身懂"时点观测"，唯独 `demographics` 整块漏了，所以 `height_cm` / `weight_kg` / `ecog`
同样中招（只修 age 是症状层修复，下一次就轮到体重）。

- **schema v2 → v2.1**（`patient_summary.schema.json`）：`demographics` 里只有 `sex` 是时不变的。
  `age` / `height_cm` / `weight_kg` / `ecog` 各自新增 `_as_of` 来源日期（required，可 null）；
  `age` 另加 `age_observations[]` 全时点序列（`{value, as_of, source_ref, age_basis?}`，`age_basis`
  enum 锁 `completed_years|nominal_years|unspecified`，只有来源明说周岁/虚岁才填）；新增粗粒度
  `birth_year`（仅 YYYY）。`age` 明确定义为**最近一次来源快照，永不推算到今天**。
- **时变字段例外**（`organizer-prompt-phase2-synthesis.md` 新增 §2.1/§2.2，先于 §2 判定）：
  冲突 = 同一时点的两个来源不相容；不同时点说了不同的话是时间演变。给出字段分类表（时变 vs 时不变）
  与年龄自洽判据 `a₂ − a₁ ∈ [⌊Δ⌋−1, ⌈Δ⌉+1]`，**±1 容差不可收紧**（吸收生日是否已过 / 周岁虚岁 /
  报告写就诊时年龄这三种正常差异）。仍判 `disputed` 的只有三种：同 `as_of` 内矛盾、与时间跨度矛盾
  （年龄倒退）、值本身可疑（走忠实度 flag）。
- **禁止伪精度的 `birth_year` 推算**：单条 `(age, as_of)` 只能推出两个候选年份，**禁止直接相减**；
  只有来源含完整 DOB（取年份，其余不落盘）或 ≥2 条不同月份快照交集唯一时才写，否则 `null`。
- **隐私边界**（`pii-rescan-prompt.md`）：`birth_year` 三条件豁免（只 4 位年份 / 只在
  `patient_summary.json` 一个面 / 月日不以任何形式落盘），缺一即按 DOB 处理并标记。
- **一并修的下游面**：`upload-reconciliation.md`（re-upload 的时变差异不进 `conflict` 分支）、
  `patient-profile-schema.md`（`cross_source_conflict` 不因正常演变触发）、`profile-card.md`
  （时变字段不进冲突卡）、`conversation-incremental-prompt.md`（患者自报年龄按时点归档，
  不晋升为 `age` 快照）、`case_summary_data.schema.json` + `case-summary-html-prompt.md`
  （年龄必须带 as-of 日期渲染，"52 岁（2024-03-11 报告）"；`birth_year` 非空时可在旁标"约"的现龄，
  不替换带日期的快照）、`organize SKILL.md` Step 10 + 输出清单。
  顺带修文档漂移：SKILL.md 把 `longitudinal_observations_v1` 更正为 schema 实际的 `v2`。

**破坏性变更**：`schema_version` const 为 `"2.1"`，v2 存档（无时间锚）不再通过校验，需重跑 organize。
下游 `smtb-skill/scripts/facts.py` 按顶层容器键名通用遍历、不硬编码 `age`，新增子字段不破坏它
（未改动该仓）。

验证：新增 `tests/unit/demographics-time-anchor.test.sh` **17/17**（跨年年龄序列可表达为合法文档；
6 个 `_as_of`/序列字段缺失逐一 reject；无日期的 age 观测 reject；`date_of_birth` 走私 reject；
`birth_year` 写成日期串 / 1750 reject、null 合法；全 null 无年龄合法；`age_basis` enum 正负例；
`schema_version: "2"` reject；小数年龄 reject）。**负向控制**：把 `age_as_of`/`age_observations`
移出 required 后测试立刻转红 2 项（15/17），恢复后 17/17 —— 证明它守的是真东西。
判断层（自然增龄不判冲突 / 真矛盾仍 fail-closed）不可确定性测试，写成
`tests/eval/scenarios/cancer-buddy-organize.md` 的 **org-05 + org-06**（含"禁止用单条快照反推
`birth_year`"和"同日矛盾 + 年龄倒退双 flag"）。
全量回归：unit 14/14 文件全绿（含既有 agents-md-fill 37、bucket-taxonomy 18、case-summary-trend 34、
organize-fidelity 11、untrusted-scan 32）、integration 6/6 全绿、`tests/eval/run.sh` 8 lint 组全绿。

### Added — 三层参考文献库 + 全局引用规范 + 注入隔离 (2026-08-03)

回答任何问题前先查一条固定的本地检索链，命中内容作为回答骨架与引用锚：
① 患者档案 → ② 主诊团队对本人的交代 → ③ L3 患者专属资料 → ④ L2 用户全局资料 →
⑤ L1 产品自带资料库 → ⑥ 实时联网。

**优先检索 ≠ 优先采信。** ①—⑤ 每次都查，但获批状态 / 医保报销 / 试验在招 / 指南版本 /
中心名单这五类断言，无论本地是否命中都要 answer-time 实时核验并并列呈现。本地命中让联网
这步更准（拿着具体方案名去查而不是盲搜），不是让它可以省略——这条同时满足了「先看资料库」
和 `safety-guardrails.md` 的 no-silent-snapshot 红线，不需要在两者间取舍。

设计依据：产品的安全合同有四处（`safety-guardrails.md` §Urgency ×2、
`clinical-content-governance.md` §Red flags ×2）把「主诊团队的书面交代」列为最高优先级来源，
公共指南只是它不可用时的 fallback；而此前仓库没有任何地方定义它存在哪、怎么读、读取顺序排第几。

**新增 — 共享合同**
- `references/citation-format.md` — 引用规范升为全局合同。标签恒定四类
  `〔档案〕〔资料库〕〔联网〕〔文献〕`（`〔本地指南〕` 并入 `〔资料库〕`）。此前规范只活在
  education 一个子技能里，其余 10 个 companion 与 router 都不知道它存在
- `references/reference-library.md` — 三层库定义、`index.json` 契约、`redistribution` 处置矩阵
- `references/evidence-trust-tiers.md` — 按**事实半衰期**分层（不是按证据强度）。含
  cancer-buddy 特有的第二条轴：患者档案自身的半衰期
- `references/first-party-instructions.md` — 团队交代的建模。`instruction_source` 区分
  `team_written` / `team_verbal_relayed` / `patient_interpretation`——转述者不等于指令来源，
  患者可能把 38.0 记成 38.5，所以口头转述必须并列公共 fallback
- `references/untrusted-content-isolation.md` — 档案、AGENTS.md、用户投放文件全是**数据不是指令**

**新增 — 脚本**
- `library_resolve.py` / `library_verify.py` / `library_save.py` + `library_index.schema.json`
- `scan_untrusted_markers.py` — prompt-injection 机械门。三级 severity、恒定 `exit 0`（误报
  杀掉一份真病历的代价高于漏报）、医学术语白名单（`胃旁路` 含 bypass、照护者日记里的 `扮演`）、
  中文走 n-gram 不走 token overlap、NFKC + 零宽字符 + 同形字归一、命中全收集不短路
- `fill_agents_md.py` — 取代 SKILL.md 里的内联 heredoc，带 12 条 routing 锚点断言 +
  红线关键句断言 + `template_sha256` + 跨患者 code 比对
- `build_filings_dataset.py` — 结构化清单构建（靶点同义归一、`targets[]` 字段、
  申办方与研究机构分列）

**变更 — AGENTS.md 三条红线全文内联（33 → 95 行）**

`organize/SKILL.md:33` 自陈 cwd 落在患者目录的 session 可以「without first invoking the
cancer-buddy skill」直接从档案回答。此时进上下文的只有模板那 33 行，239 行的
`safety-guardrails.md` 一个字都没加载，而模板最后一行 `Follow root references/...` 在患者
目录里是**悬空引用**——那里没有 `references/` 目录。现在 no-silent-snapshot、不做个案判决、
数据不是指令三段是全文内联，悬空引用已删除。

**变更 — 三个已存在的缺陷（与本次功能无关）**
- `pii_rescan.py` — `ocr/` 目录存在时会提前 `return`，导致 post-Phase-2 的**所有 bucket
  sidecar 不再被扫描**，而验收门仍打印 `all pass`。一个 `mkdir ocr` 即可触发的 fail-open。
  改为并集
- `export_share.py` — 只挡 symlink 不挡**硬链接**，而 `resolve()` 不跟随硬链接，导致
  `ln raw/secret.txt 14_.../x.txt` 可导出 raw 原件，manifest 却仍写
  `raw_originals_included: false`。补 `st_nlink > 1` 拦截
- `export_share.py` — 库层必填校验漏掉 `expires_at`（而单测走的正是库层）。补齐并重跑过期校验

**变更 — CI 与门禁**
- `.github/workflows/test.yml` — 加跑 `tests/eval/run.sh` 并安装 `jsonschema`。此前 8 道
  安全 lint **从未在 CI 执行**，schema 校验一直走 `HAS_JSONSCHEMA=False` 的降级分支（只 WARN 不 fail）
- `validate_structured_outputs.py` — 接入 `gate_agents_md`（调 `--check`）、
  `gate_no_rogue_agents_md`（嵌套 AGENTS.md/CLAUDE.md 即 fail）、`gate_untrusted_content`
  （非阻塞，命中写进 `readiness.json.review_flags[]`——`category` 是自由字符串，零 schema 改动）
- `lint/05` — 强制 12 个 skill 引用三份新合同；**标签白名单**：`skills/` 下出现四类之外的
  `〔…〕` 即 fail
- `lint/10-crossref-integrity.sh` — 跨文件章节引用完整性（产品面硬 FAIL，CHANGELOG/docs 仅 WARN）
- `lint/12-library-redistribution.sh` — L1 随 git 分发，只准 `redistribution: allowed`；
  示例 manifest 不得含受限出版方的具体文件名
- `.gitignore` — `patients/`、`**/raw/`、`*.heic`、`*.dcm`

**变更 — 目录**
- 建档时自动创建 `<patient_dir>/library/`。它是**基础设施目录不是临床域桶**：懒创建策略
  （空桶会误读成"无此记录"）不适用；它在 `[0-9][0-9]_*` glob 之外所以 gate 不管辖，用户可自建
  子目录；且 `anchor-contract.md` 限定锚点前缀为 `01_…14_`，**参考资料在语法层面就无法冒充
  患者自己的临床记录**被引用
- `10_随访与监测/` 新增 typed 子桶 `团队交代` / `team_instructions`（`scheme_version` 保持 3，
  子桶追加非破坏性变更）

**验证**：8 lint 组 0 失败、12 单测全过、6 integration 全过。负向验证：注入非法标签 → lint FAIL；
删除任一新合同引用 → lint FAIL；`"file": "../../../etc/passwd"` → 非 0 退出；硬链接导出 → rc=2；
空/过期 `expires_at` → rc=2；含住院号文件拒进 L2 → rc=2；injection 误报门（`胃旁路` / `扮演`）
零命中且白名单确实被触发后抑制。


### Added — `cancer-buddy-charts`：临床可视化 subskill (2026-07-26)

原命题是"cancer-buddy 画不出好看的图表"。**实测不成立**——`cancer-buddy-organize` 早有一条确定性
图表管线（`compute_sparklines.py` 394 行 + `validate_case_summary_html.py` 453 行 +
`cancer-trend-markers.md` 32 行资格门）。真实瓶颈是**图型词汇表只有 2 个**（hero 折线、spark 迷你
折线），而 organize 产出 8 类数据形状，其中 6 类无图可用。缺的不是绘图能力，是图型库。

设计法典参考 `larashero3-dotcom/lieflat-charts`（PolyForm Noncommercial 1.0.0）。**代码零引入**：
该许可证禁止 sublicense，与本仓 MIT 冲突；且换主题色要替掉整个 Mono 灰阶编码体系、满足 print-safe
要替掉运行时 `createElementNS`、临床语义要重写选型逻辑——改完本就不剩原始代码，法务约束与工程最优
解在此重合。取其设计规则（不断轴、面积 sqrt、卡片四件套、密度靠"家具"而非数据、库外图型翻译流程），
代码 100% 自写。48 张图里临床可用不足 1/4。

**新增**
- `skills/cancer-buddy-charts/` — SKILL.md + 3 份 references + 3 个 stdlib 脚本
- 两层架构：`chart_core.py` 几何原语（轴/参考区间带/标签避让/家具/token）+ `render_chart.py`
  图型配方。**清单外的图是新配方，不是新引擎**——这是泛化能力的来源，而非一张 8 图查表
- 8 个配方：`trend`（+参考区间带）`swimlane` `panel` `timeline` `vaf` `coverage` `dumbbell`
  `medications`
- `validate_chart_svg.py` — 对抗式验证器 9 项（print-safe / 零外链 / 8pt 地板 / 色板锁定 /
  红色克制 / 无绿色 / 卡片四件套 / 判决词地板 / XML 良构）
- 路径 C **主动识别**：用户问某个具体指标时，回答前先查该指标点数，≥2 个可比点自动附图，
  不足则说明原因。落地到全部 11 个子技能 + 主 router

**变更**
- `render_chart.py --data` 是 `compute_sparklines.py` 的向后兼容替代，既有字段**逐字节相同**
  （E2E 断言），新增 `has_band` / `band_y` / `band_h` / `reference_range_text` 与
  `dots[].stroke/fill`
- `case_summary_data.schema.json` — 新增上述字段 + `reference_range` + `reading_note`
- `case-summary.template.html` — 参考区间带（画在 area 之上的虚线框，实心带会被 area 完全遮住）；
  marker badge 字号 9.5→11.5（原值在 ~260pt 容器里约 6.8pt，低于 8pt 地板）；
  **趋势方向箭头停用**（向下箭头对患者天然读作"好转"，是无权给出的判断）；
  `{{interpretation}}` → `{{reading_note}}`
- `cancer-buddy-organize/SKILL.md` Step 12 改调 `render_chart.py`

**三层标题规则**（本次最实质的设计决策）。`interpretation` 字段此前 schema 为 `const: null`
——caption 被整个关掉了。合规但没用。改为标题写**读图指引**：不写结论，也不复读图上已有的数字，
而是回答"这张图该怎么看、数据能不能信"——「CA19-9 四次测量 · 第 3 次起检测方法变更，前后不可
直接比较」。这是患者自己看不出、却决定图表可信度的信息，也把图从"给患者看的"变成"患者带去问医生
的工具"。判决词黑名单只作用于 **authored text**（`--title`、spec caption、LLM 填写的字段），
不作用于确定性代码生成的免责注记（正则读不出否定语境，会误杀 G-CHART-5 要求的
"时间对齐不表示疗效或因果"），也不作用于病历转录的临床名词（"缓解"在"诱导缓解方案"里是方案名）。

**临床保真**
- 参考区间只用该次报告自带值，**禁止套用通用参考值**；性别/年龄分段等歧义区间一律拒绝解析而非猜测
- `method_or_device` 变化 → 序列断开分段，接缝虚线
- 检测限读数（`<5.0`）用空心方块 + 方向短须绘制，不当作 5.0 的实测值（伪精度＝捏造的近亲）
- 红色仅用于源报告自身标注的危急值；超区间用琥珀描边不填充（满屏标红对患者是真实伤害）
- 跨量纲对照图每行独立缩放并声明行间不可比（共轴会把 68 kg 和 132 g/L 放到同一尺度）

**边界**：只画用户问的那一个指标，严禁主动扩展——那正是 `CHANGELOG.md:165` 记录的、后来被整体
撤回的"全 69 NCCN 癌种 → 疗效监测标志物"对照表。拒绝清单：RECIST 瀑布图、针对本人的生存曲线、
风险评分仪表盘、断轴柱状图、无数据示意图、地图类。

**未实现**：靶病灶径线之和（`lesions[]` 只有自由文本影像描述，无结构化径线与日期，无数据基础；
且距 RECIST 判读仅一步，单开 PRD）。

**测试**：`tests/unit/charts-primitives.test.sh`（参考区间/状态/检测限解析）、
`tests/integration/charts-e2e.sh`（2 患者 × 2 癌种 × 8 配方 + 5 项 gate 负向 + 8 项注入拦截 +
向后兼容逐字节断言，27 项）。


### Changed — 对症支持用药：把闸门从"整块甩墙"重画到"一般 vs 个案"两轴 (2026-07-21)

用户反馈"胃反酸想吐有什么药干预吗"被回避、既不敢报药名也不带 reference，而通用助手能给带源的
OTC/PPI 一般处理。根因：`cancer-buddy/SKILL.md` 把「症状用药」整块塞进个案拒答桶
（与虚拟 MTB/换线/试验资格并列），违反 `safety-guardrails.md` §Conditional education (b) ——
对症支持的**一般用药教育**本属放开轴、应带源转述含药名的一般推荐。

- **`cancer-buddy/SKILL.md`**：路由表新增「对症/支持治疗一般用药 → cancer-buddy-education」行；把
  第 42 段拆成两轴——一般对症用药教育（反酸/恶心/便秘/发热/疼痛的常用/OTC 药物类别、指南一般处理）
  路由 education、带编号引用给一般格局，只有"在我这个具体方案/在用药下我该加/调哪种药"的个案决定收口
  主诊团队；并要求**简短对话式答复**含版本敏感断言时也必须内联出示编号来源，不得因"只是短答"省略。
- **`cancer-buddy-education/SKILL.md`** Medication 段：新增"对症支持一般用药教育（放开轴）"条目，
  answer-time 核验一手源后带源给一般药物类别，叠加**肿瘤特有护栏**（症状可能是 CINV 等治疗副作用；
  PPI/止吐/抗酸药与某些口服 TKI/靶向药相互作用需药师核；化疗期发热按团队阈值当急症）。
- **`expanded-faq.md`**：新增"对症支持与自我照护用药"结构化模板（共情+鉴别 → 带源一般处理 →
  肿瘤护栏 → red-flag 收口），并重申无相互作用结论须实时核验、禁模型记忆兜底。

红线未松：对本人的分期/疗效/预后/换线/个体剂量判决仍收紧；放开的只是"一般规律、带源、条件式"教育。

### Added — 检索能力显式化 + 可选本地指南库 (2026-07-17)

- **A · capability-agnostic 检索**：`guideline-lookup.md` §1、`find-care/references/data-sources.md`、
  governance §2 显式写明 answer-time 检索使用宿主**当前可用的任意联网/数据能力**（已装 `web-access`、
  宿主 WebSearch/WebFetch、或任何相关已装 MCP）——**use-if-present，不硬依赖任何特定工具/MCP**，
  都不可用则 fail-closed。不在 skill 里写死或绑定任何 MCP。
- **B · 可选本地指南库**（`guideline-lookup.md` §1.5，默认关闭）：环境变量 `CANCER_BUDDY_GUIDELINES`
  指向用户掌控、合法持有的指南目录 + `index.json` 清单（publisher/title/version/date/jurisdiction/
  cancer_types/license）。answer-time 顺序：本地清单可核验条目 → 联网官方源 → fail-closed。无清单
  条目或版本不清/过期的文件不作当前来源。隐私硬边界：只读该目录内文件、拒符号链接越界/`..` 穿越、
  绝不扫主目录/患者目录、只读不写、患者输出不露主机绝对路径。附 `guideline-pack.example.json` 模板。
  未配置时行为与之前完全一致。

### Changed — 放宽后的口径一致性整改：消除跨文件残留矛盾 (2026-07-17)

三个独立第三方 subagent 并行审全仓（SKILL.md 层 / 顶层 references / 子 references+README），去重后
1 P0 + 4 P1 + 7 P2 全部修复，红线仍严格切在“一般 vs 个案”：

- **P0** `clinical-content-governance.md`：§1「每条版本敏感 claim 必须具名人工复审」+§0「冲突取更严」
  原本会把放宽（answer-time 带源转述指南）整个废掉。新增 scope 豁免——**忠实、带源、非个案化地
  转述指南/标签自身已陈述的一般推荐属 §2 answer-time 核验，不触发 §1 全生命周期与具名人工复审**；
  §1 lifecycle 与 stricter-wins 仅约束产品**自己合成/断言**的 claim 及一切个案判决。
- **P1**：`terminology.md` 禁“推荐”豁免扩到“忠实署名转述指南推荐”；`education/SKILL.md` 删“FAQ/癌种模块
  只提供提问框架”改为“一般指南答案走 guideline-lookup 实时核验带引用”；`find-care/SKILL.md`「不解释
  分子结果」收窄为「不做个案临床判读（一般概念转 education）」；`web-access/SKILL.md` 顶部前置 Cancer
  Buddy 临床检索**严格只读**铁律（禁上传患者文件/表单/状态变更）。
- **P2**：`safety-guardrails.md` (a) 预后一般规律改为与 (b) 对称的正向授权；入口补预后/严重度一般教育
  豁免；`education` description 补“可给带源方案/线次名称”；入口路由 visit-prep「questions only」改为准确
  范围；`disclosure-behavior.md` 区分“一般教育无需授权 / 仅个案细节受限”；`preflight.md` 区分“缺个案资料
  仍可条件式教育”与“查源失败降概念层”；README/README_EN 首句对齐“查指南”能力（保留全部免责）。

### Changed — 放宽指南级闸门：入口继承 §Conditional education (2026-07-17)

修一个“上紧下松”的自相矛盾：`safety-guardrails.md` 早已有 §Conditional education（放开一般规律、
允许 answer-time 查证指南），但旗舰 `cancer-buddy/SKILL.md` 入口只留了光秃秃的禁令，与 education
子 skill 宣传的“实时查指南（NCCN/CSCO/ESMO）”顶撞。把已认可的 nuance 提升到入口：

- `cancer-buddy/SKILL.md`：description、Hard boundaries、路由收口三处重写——明确 cancer-buddy **可实时
  联网查证并解释指南/标准治疗的一般情况（含具体方案/线次名称，带编号来源）**，讲“一般怎么治 / 接下来
  评估什么”。
- 红线切在“一般 vs 你个人”，不切在“指南能不能碰”：仍**不**替本人做诊断、分期/ECOG/疗效/进展/预后判决
  与治疗/换线/用药调整决策，不判个体试验资格——这些整理成带去问主诊团队的问题。
- `safety-guardrails.md` (b) 指南级：补一句“可如实转述指南对‘这类情况’的一般推荐，但不等于替患者选定
  方案”以消歧义。README 对外担责声明保持不变。

### Changed — 全量临床安全整改与来源治理 (2026-07-17)

- 审阅并修订全部 99 个 reference：删除跨方案器官阈值、跨癌种固定随访/检查建议、
  模型记忆兜底、肿瘤标志物疗效推断、家庭能力打分、病例幸存者偏倚和伪精确资源排名。
- 新增 `clinical-content-governance.md`：版本敏感主张必须具备适用人群、法域、现行一手
  来源、版本、到期日与相应专业角色的人类签审；无法核验时失败关闭。
- 病历整理改为原生/确定性抽取优先、LLM 仅作可审计辅助；患者/照护者自述与来源事实
  分层，不能凭一次确认改写分期、ECOG、疗效、治疗线或分子结果。
- 19 份癌种 checklist 降级为“既有文档盘点”，不再生成检查建议；趋势仅展示来源数值和
  报告原始 flag，不自行判断疗效、进展或严重度。
- 患者知情、代理权限、跨境标本、营养/药食相互作用、数据导出和中国法域隐私规则均改为
  授权、版本和场景约束；导出使用逐文件白名单并拒绝 `raw/`、目录和符号链接。
- 新增临床治理 lint、导出反例测试与行为场景；全部静态、单元、集成和 schema 测试通过。

### Changed — 指南源面重构：answer-time 真实来源 + licensing 边界 (2026-07-17)

真机测试发现本地现行指南可作为真实来源，但必须与模型记忆、未标版本缓存和未经授权的
私人文件区分。重构 `guideline-lookup.md` 的 answer-time 来源与 licensing 边界：

- **本地来源可用但不自动搜集**：仅使用用户/宿主明确提供、访问获授权且发布者、版本和页码
  可核验的对口现行指南；否则查当前官方来源。患者输出不暴露主机绝对路径。
- **licensing 边界**：按实际来源条款、引用范围、使用目的和是否再分发判断；默认只输出完成
  本次解释所需的最小内容，不把付费指南表格打包给第三方。
- **恒定不变**：真实来源接地 + 禁凭模型记忆合成；本地与联网来源均标版本和引用位置。
- 同步 `safety-guardrails.md`、`education/SKILL.md`（description + Safety）至同一口径。

### Fixed — 指南级回答的编号脚注列表必须出现在回复里（不止落盘）(2026-07-17)

E2E 合成案例测试发现：(b) 指南级路径接地扎实（每个 OS/HR 数字都有逐字 quote + 真 PMID、无个案判决），但**内联 `[1]…[14]` 的编号脚注映射被写进了 `SYNTHESIS.md` 文件、没渲染在给患者的那条回复里**——患者只看到内联数字、查不到源，恰是本功能最初要修的毛病的变体。

- `guideline-lookup.md` 呈现步:新增硬要求——`[n] → 源` 脚注列表**必须直接出现在面向用户的回复末尾**,`SYNTHESIS.md` 只作可另附的落盘记录;回复必须自包含。
- 同增**出稿前自洽检查**:计数措辞("三条/四项")须与实际条目数一致(修真机里"三条"却列 4 条的笔误);内联最大 `[n]` = 列表长度、两边一一对应。
- `cancer-buddy/SKILL.md`「来源引用」补通用规则:脚注列表必须在回答本身里(防同类退化扩散到 find-care 等)。
- 出稿前自洽检查再收紧(4 面对抗验证独立揪出的 P2):脚注编号**连续无缺口**(别 `[10]→[13]`);**每一条**脚注都带来源类型标签(〔联网〕/〔文献〕/〔档案〕),不是只给个别条目带(真机产物里标签覆盖只有 2/12)。

### Added — 指南级证据实时联网并入 education 条件式教育分支 (2026-07-17)

此前"基于我的病情，NCCN 指南建议是什么 / 标准治疗是什么"这类**指南级**问法，条件式教育靠 LLM 记忆 + 静态 `cancer-type-modules.md` 回答——而版本敏感内容必须核验现行来源、禁止 LLM 合成。本次把条件式教育拆成两种子问法，并为 (b) 增加 answer-time 来源核验：

- **(a) 严重度/预后**（严不严重 / 能治好吗 / 是不是晚期 / 会不会复发）可解释稳定概念；任何具体数字、分层或治愈判断仍须核验当前适用来源。
- **(b) 指南级**（NCCN/CSCO/ESMO 建议 / 标准治疗 / 一线二线方案 / 我这类一般用什么药）＝版本敏感事实 → 使用版本可核验的授权本地一手来源或当前官方在线来源，并带连续编号引用；均不可用时失败关闭，不以模型知识补具体内容。
- **源面与 licensing**：按主张选择当前监管标签、专业指南、法律或试验注册等最直接来源；受许可/付费指南仅输出完成本次解释所需的最小内容，遵守实际条款和再分发限制。
- **边界重构（router「我不做的事」）**：换线/诊断路径的**个案判决**仍归主诊医生，但删掉"一律甩回医生"的反射开场——先给一般条件图（指南级走实时检索），"要不要换由医生定"降为收口 footer。**"不做个案判决" ≠ "什么都不讲"。**
- 安全门：G-SOURCE / G-NO-MEMORY / G-NO-VERDICT / G-COPYRIGHT / G-CITE / G-EXPIRY；无法核验时只保留稳定概念教育。
- 文件：新增 `guideline-lookup.md`；改 `cancer-buddy-education/SKILL.md`（含 description）、`cancer-buddy/SKILL.md`、`references/safety-guardrails.md`、`cancer-type-modules.md`；`tests/eval/scenarios/cancer-buddy-conditional-education.md` 加 ce-04（正向）+ ce-05（负向 no-overfetch）。PRD：`docs/prd/education-guideline-lookup.md`。

### Changed — 来源引用扩到联网/文献来源，与档案锚共用同一编号序列 (2026-07-17)

此前 `cancer-buddy/SKILL.md` 的「来源引用」节只给**档案里的事实**编 `<sup>[n]</sup>` 角标，联网检索来的内容（find-care 的 URL 列表、case-precedent 的 PMID）各用各的格式、不带内联编号，两套溯源体系割裂。本次把该节（引用渲染的 single source of truth）扩成两条溯源通道、**共用一条全局递增编号序列**：

- **档案锚**：事实取自 `patients/<patient_code>/` 结构化 JSON → 复用 `source_refs[]`（不变）。
- **联网锚**（新增）：事实取自当场联网检索（`web-access` / WebSearch / 本地联网 MCP / PubMed·EPMC）→ 锚到真实抓取的 URL 或 PMID。角标与档案锚**混排连续编号**。
- 脚注前缀来源类型标签 〔档案〕/〔联网〕/〔文献〕，一眼分清；标签与脚手架按 `locale` 渲染，URL/PMID/期刊名/抓取日期逐字保留。
- **反幻觉硬门**：只有**真检索到、能逐字回溯原文**的事实才配联网角标；LLM 记忆里的"我记得指南大概这么写"不算来源、不得凭空挂角标（no-silent-snapshot / 反幻觉）；联网不可达标"需现场核实"，不静默降级到模型记忆。PMID 类须过撤稿检查。

### Removed — 下线心理筛查与危机干预（mental-health screening + crisis intervention）(2026-07-16)

产品决策：抗癌搭子不再提供心理评估、精神科筛查或心理危机干预——这类功能涉及精神卫生监管、量表商用授权与"答错即高风险"的责任敞口，改由用户寻求精神卫生专业人员或当地急救/急诊。本次为**破坏性变更**（BREAKING）：删除整个 `cancer-buddy-mind` 子技能、照护者 Zarit 负担自评，以及贯穿路由与安全护栏的危机检测/热线机制。

- **删除** `skills/cancer-buddy-mind/`（PHQ-9 / GAD-7 / NCCN 距离温度计 / C-SSRS Lite / `crisis-resources.md` 热线表）。公开陪伴模块由 11 个减为 **10 个**。
- **删除**照护者 `zarit-burden.md`；`cancer-buddy-caregiver` 不再做负担自评或危机路由，仅保留分工 / 陪诊 / 喘口气 / 告知框架等非筛查支持；严重困扰改为"接住 + 转介专业帮助"。
- **移除**主入口 `cancer-buddy/SKILL.md` 的"进门前：危机检测"整节、相关触发词（睡不着 / 焦虑 / 抑郁）与路由表行；`safety-guardrails.md` 的角色危机规则与"想不治了"C-SSRS 闸门改写为"不自行评估、转介主诊医生 / 精神卫生专业人员"。
- **清理**所有对 mind / 危机 / 热线的悬空引用：`roles.md`、`disclosure-behavior.md`、`case-precedent` / `disclosure` / `education` / `organize` 等子技能、README / README_EN、插件清单、CONTRIBUTING，以及测试（删除 `mind-crisis.sh`、`02-crisis-path.sh`、`scenarios/cancer-buddy-mind.md`，更新 EVAL / journey / trigger-words / eval 维度）。
- **患者可见变更**：所有患者朝向文案统一声明"本工具不提供心理筛查、精神科诊断或心理危机干预；如有情绪困扰或危机，请寻求精神卫生专业人员或当地急救/急诊"。

### Changed — 三块迭代：case-precedent 自然触发+可点 PMID / organize 段D 抗压缩 / 补料邀请体验重做 (2026-07-10)

一次迭代覆盖三处：让 case-precedent 更自然可触发且可核验、修 organize 段D HTML 在上下文压缩下不走模板的问题、把"补料邀请"从"整理完就推、错过即永久沉默"重做成"挑对时机 + 冷却期 + 有回声"。

**A. case-precedent — 自然触发 + 每方向一条可点 PMID**
- `SKILL.md` `description` 增加**软触发词**（"还有没有别的办法""是不是只有我这样""换了方案不知道往哪走"等"找别人/找方向"形状的弱信号）；纯绝望/自伤语明确不归本 skill（走危机 + mind）。
- `SKILL.md` Step 0 增加**软信号分支**：弱触发/主动提及先给"共情一句 + 情绪 vs 方向二选一问句"，**不自动检索**；主动提及**同会话最多一次**。
- `organize/SKILL.md` Next-step guidance 增加 **case-precedent 出口**：整理完顺势**只提一句**（相似度画像字段此刻最全），ask-once。
- **患者版 §A 改聊天优先 + 放宽 PMID 口径**：从"患者版零 PMID"改为**每个治疗方向挂一条可点 PMID 超链接**（可核验、可带去问医生），逐例结局/6 维表/偏倚横条仍只在 §B（"展开详细版"后）。更新 `output-template.md` §A 模板+示例、`bias-disclosure.md` §2a、G-PATIENT-FIRST 门。

**B. organize 段D — 模板管线抗上下文压缩**
- 根因：18 步长流程里段D 生成在很靠后，压缩后"产出 HTML"目标存活、"走模板渲染"机制被摘掉 → 易手写非法 HTML；且校验是君子协定、渲染/校验职责在编排器与子代理间模糊。
- `SKILL.md` 顶部新增 **🔴 抗压缩不变量块**（provenance-first：无 `template_sha256` 注释即非法交付；段D 全管线在自包含子代理内完成并返回 template_sha；终态硬门）。
- **重构 Step 12**：段D 子代理**独占** data→enrich→render→validate 并**返回 `{status, template_sha}` 或 `{status:"failed",…}`**（永不返回 HTML）；编排器只校验 template_sha + 做 dated 快照，消除职责模糊。
- 新增**统一「Definition of Done」终态硬门**：`validate_structured_outputs.py` exit 0 + 贴出 template_sha + PII clean + 忠实度无未决 CRITICAL + AGENTS.md 非 stub，全绿才算完成。
- `case-summary-html-prompt.md` 增加**返回契约**段（返回 template_sha 或硬失败，绝不返回 HTML 正文）。

**C. 补料邀请 — 体验重做**
- 复盘：旧版把补料**堆在 organize 刚结束（认知过载）**，profile card 又先铺一遍冷缺口清单（重复），ask-once 是**永久 pending**（错过即永久沉默），分不清"没做 vs 做了没上传"，补完无回声。
- `profile-card.md` 信息缺口**降级为覆盖度分级 + 一句话**，具体缺哪几样交给补料出口（同一时刻只一个地方谈缺失）。
- `gap-followup.md` 重做：**post-organize 降为一句极短信号**（§5）、**主力改时机触发**（visit-prep / 路由 / 被问题限制，§5.5）、**ask-once 改冷却期 + 硬上限**（§7，废弃永久沉默）、新增**"没做 vs 做了没上传"分叉**（§4，含 `not_done` 状态）、新增**补料成功即时正反馈闭环**（§9）。
- `organize/SKILL.md` Step 11.4 与 `cancer-buddy/SKILL.md` 补料邀请节对齐（时机 + 冷却期 + 分叉 + 正反馈）。

### Changed — 段D 病情简要总结「关键趋势」hero 指标选取：从纯 LLM 判断改为「癌种标志物表 + 分层规则」 (2026-07-08)

段D「关键趋势」`trend_charts[]`（拎成 hero 大图的指标）此前完全靠子代理散文式临床判断，无锚、不可复现，易出现"谁时间点多谁上"——无关常规检验挤掉该癌种真正的疗效标志物。改为决策相关性驱动的分层选取：

- **新增参考表** `references/cancer-trend-markers.md`：全 69 NCCN 癌种 → 疗效监测血清标志物（子代理据指南知识生成 + 本地 OncoEvidence 交叉核对；27 癌种有公认标志物，42 个显式标 `—`，4 个语料支撑薄的标 `存疑`）。行脊柱取自 `cancer_therapy_corpus/landscapes` 的 69 slug。这是**血清疗效标志物**，不含预测性/分子 biomarker。
- **重写** `case-summary-html-prompt.md` §关键趋势 选取规则：Tier1（癌种 primary 标志物，≥2 时间点，同癌种 ≤2 张）/ Tier2（患者特异动态指标）/ 降级（平稳·非疗效·单点 → 落「实验室指标」sparkline 行）/ 克制（hero 总数 2–4）/ 无标志物不硬凑 → `[]` / 先验服从个案（读 caveat，组织学依赖 marker 如甲状腺 Tg vs 髓样降钙素按实际组织学选）。
- **新增结构校验器** `scripts/validate_cancer_trend_markers.py`（纯结构，无医学 keyword）+ 单测；E2E 覆盖 PDAC→CA19-9 进 hero（无关 ALT 降级）、黑色素瘤→`[]` 不硬凑、4 图上界渲染。
- **零改动** 模板 / validator / schema / compute_sparklines（选取全在 data 层）。

### Changed — case-precedent 输出层重构：从"研究综述"改成"陪伴 + 一个下一步" (2026-07-07)

首个真实 E2E 后复盘发现：产物虽真实、接地、无偏，但**交互层是给研究者看的、冰冷**——454 行 PMID/6 维表/开场偏倚墙，回答的是"研究者的问题"，不是一个害怕的家属真正想知道的（"我是不是孤单？有没有希望？下一步做什么？"）。重构输出层（不动检索/接地内核）：

- **Step 0 先接住 + 厘清意图**：先认情绪，再问一句"想看别人试过哪些方案（带去问医生），还是求希望/求人听（→ 路由 `cancer-buddy-mind`）"。别用 25 分钟综述回答一个求安慰的问题。
- **两层输出**：**患者版 brief**（`相似病例_我可以问医生的.md`，主体）只给**按类别归并的治疗方向 + 一个具体下一步**（推向医生 / visit-prep / second-opinion），偏倚**轻编织进一句**不砌墙，**不摊死亡结局卡片**；**医生版临床附录**（`PRECEDENTS_临床附录.md`）承载完整 6 维/PMID/结局（含死亡）/证据分级/审计 footer，默认不主动展开。
- **新增 G-PATIENT-FIRST 安全门**：先厘清再检索、患者版先接情绪只给方向不摊死亡结局、偏倚轻编织、结尾一个下一步。
- 更新 `output-template.md`（§A 患者版 + §B 医生版）、`bias-disclosure.md`（患者版轻编织 vs 医生版横条两种形态）。

### Added — cancer-buddy-case-precedent 子技能：真实病例先例探索 (2026-07-06)

新增第 11 个 companion 子技能 `cancer-buddy-case-precedent`。患者用已 organize 的病历档案，去 PubMed / Europe PMC 检索 **publication type = Case Reports** 的相似真实病例，逐病例返回治疗路径 + 结局，作为**研究与就诊讨论的线索**——**不是预后预测、不是治疗建议**。

- **检索**：派 subagent 加载 `web-access` 直连 PubMed E-utilities（`"Case Reports"[Publication Type]`）+ Europe PMC REST（`PUB_TYPE:"Case Reports"`），keyless；去重 + 撤稿检查（`"Retracted Publication"[pt]` / EPMC 标记）在主 agent 汇总时做。自包含，不依赖 vMTB 生态的 `vmtb-literature`。
- **逐病例抽取**优先 OA 全文，逐字接地（临床值带 verbatim 引文 + PMID），抽不到标 `未报告`，禁 LLM 合成结局。
- **相似度** 6 维（primary/histology/stage/key_driver/treatment_line/key_comorbidity）逐维 match/mismatch，**分歧维必列**；LLM sub-prompt 判定，不写硬编码打分表。
- **8 道 P0 安全门**：强制发表/幸存者偏倚披露 + 显式 N + **绝不聚合成率** + 无治疗推荐/无本人预后 + 标注最弱证据(C→D) + live lookup + 临床实体逐字禁译 + 相似度分歧透明。
- **工程硬化**（首个真实病例 E2E 复盘后）：检索 subagent **硬时限 ≤5 分钟** + OA 全文只抓 top ≤15 + 展开 ≤10 例（治首次跑 25 分钟的拖尾）；**去重显式计数**——必须真算两源交集并写出重叠数（`PubMed X + EPMC Y，去重 Z 重叠 → N 唯一`），禁止未算就断言"均无重复"（EPMC 镜像 PubMed，零重叠是异常信号）。
- 文件：SKILL.md + 5 references；登记进 meta router 路由表；新增 `tests/eval/scenarios/cancer-buddy-case-precedent.md`（4 case）。首次真实 GEJ 印戒细胞癌 E2E 已验证 4/4 PMID 真实、8 门守住。
### Added — SHARED-1 patient_dir contract (cross-repo source of truth) (2026-07-08)

- **SHARED-1 `PATIENT_DIR_CONTRACT.md`.** New single cross-repo source of truth for the on-disk patient archive that `cancer-buddy-organize` PRODUCES and `vmtb-skill` CONSUMES (skip-organize mode), placed at `skills/cancer-buddy-organize/references/PATIENT_DIR_CONTRACT.md` and duplicated identically in vmtb-skill (`skills/cancerdao-vmtb/PATIENT_DIR_CONTRACT.md`) — any edit MUST be mirrored to the other repo. Documents: configurable `patient_data_root` (`$CANCER_BUDDY_PATIENTS_DIR → $VMTB_PATIENT_DATA_ROOT → $HOME/CancerDAO/patients`) with a FIXED internal layout (`patients/<patient_code>/…`, vMTB `runs/<run_id>/` with `run_id=YYYYMMDD_HHMMSS`, delivery `reports/mtb-full/delivery/`); `patient_code` de-identification/slugification + the consumer rule to accept either `PT-` or caller codes; the v3 (`scheme_version 3`) bucket taxonomy `NN_` stable-key rule (localized slug NOT stable) referencing `bucket_taxonomy.json`; the canonical file set; the profile.json **interop surface** (branch on `schema` family `cancer_buddy_profile_v*`, nested `summary.primary/histology/stage`, tolerate looser `*_v1` real-archive shapes, minimum-fields → re-organize never crash); and the producer/consumer boundary (vMTB writes only `runs/`+`reports/`, corrections via `chair_corrections.json` overlay, flat projection via `profile_resolved.json`, never mutates organize output). Added a pointer to the contract at the top of `references/patient-profile-schema.md`.

### Added — organize P1/P2 fixes: session-bleed scope guard + update_log freshness gate + tumor-marker label guard (2026-07-07)

Three follow-on fixes for `cancer-buddy-organize`, building on the same day's P0 fidelity gates. All under `skills/cancer-buddy-organize/`.

- **CB-P1-1 Session-bleed scope guard (prompt-level).** Observed real drift: when organize ran in the same Claude session AFTER a vMTB committee run, its `molecular.json` got enriched with committee-derived knowledge (CIViC/ClinGen evidence tiers, "committee-priority drugs", family-screening framing) — content the pure-archival organize layer must never produce, which makes its output non-reproducible and violates layer separation. `organizer-prompt-phase2-synthesis.md` gains an explicit scope constraint in two places (a new `## Scope (archival-only — NO cross-session bleed)` block right after the synthesis intro, and a first bullet in the `molecular.json` §2.6 fidelity rules): "Derive EVERY value ONLY from files under `patient_dir`; IGNORE any prior conversation context, committee/MTB conclusions, or evidence research from earlier in this session. `molecular.json` records ONLY raw findings transcribed from the patient's own reports (gene/variant/VAF/zygosity/IHC/MSI) — it must NOT carry evidence tiers (CIViC/OncoKB/ClinGen levels), treatment-priority conclusions, or clinical-trial/family-screening interpretation. Those belong to the MTB/committee layer, never to organize." Prompt-level (constrains LLM output; inspection-verified, not deterministically tested).
- **CB-P2-1 update_log edit-trail freshness gate (deterministically tested).** `update_log.json` is written only by the Phase-2 LLM step, so a manual edit to `profile.json` bypasses it and the changelog silently goes stale (archive no longer reproducible from the flow). New deterministic **WARN-only** gate `gate_update_log_freshness(patient_dir)` in `validate_structured_outputs.py`: if `update_log.json` exists AND `profile.json`'s mtime is newer than `update_log.json`'s own mtime (mtime-vs-mtime is the robust comparison — no per-entry timestamp parsing), it warns "profile.json edited outside the organize flow — no changelog entry; re-run organize or append an update_log entry." Advisory only (never flips the exit code); no `update_log.json` present → skips silently. Wired into the entrypoint alongside the NGS floor.
- **CB-P2-2 Defensive tumor-marker label guard (prompt-level).** So the same "best-controlled → most-sensitive" class of diagnostic-performance drift cannot originate in the 段D producer either, `case-summary-html-prompt.md` gains one line at the 关键趋势 `interpretation` rule (~line 112): "对肿标：只陈述该指标的趋势方向；不得给任何标志物贴'最敏感/最特异/最可靠/金标准'等诊断性能标签（那是 MTB 层的解读，不在本层）。" Prompt-level (inspection-verified).

Verification: new `tests/unit/update-log-freshness-gate.test.sh` (8/8) — stale fixture (profile.json touched newer than update_log.json via `touch -t`) WARNs and names the edit-outside-flow cause; fresh fixture (update_log newer) + equal-mtime fixture stay silent; no-update_log and no-profile fixtures skip silently; full-entrypoint wiring prints the gate as `WARN:` (never `ERROR:`). Full existing unit suite still green (bucket-taxonomy-gate 18/18, case-summary-trend 34/34, organize-fidelity-gates 11/11, validate-profile-schema 21/21). CB-P1-1 and CB-P2-2 are prompt-level (inspection-verified — they constrain LLM output, not deterministically testable).

### Added — organize P0 fidelity gates: bucket-taxonomy enforcement + NGS completeness floor + staging verbatim-only (2026-07-07)

Three P0 fixes for `cancer-buddy-organize`, reproduced in a synthetic drift fixture. All under `skills/cancer-buddy-organize/`.

- **CB-P0-1 Bucket-taxonomy enforcement (deterministically tested).** The v3 taxonomy (`references/bucket-taxonomy.md` §1.1/§1.1a) was declared authoritative but nothing enforced it at mkdir time, so the Phase-2 classifier could echo incoming source-folder numbering (`06_分子与组学/基因检测`, `11_不良反应`, `13_其他专科检查`, `04_诊断与分期/影像报告`). New machine-readable mirror `references/bucket_taxonomy.json` (14 domains × zh+en full slugs + pinned typed sub-buckets + infra buckets) is the single source a new deterministic gate `gate_bucket_taxonomy(patient_dir)` reads: it scans every top-level `NN_` domain dir + each typed sub-bucket one level down, asserts each is a pinned slug (zh or en; ASCII infra `high_confidence/uncertain/conversation_notes/raw/ocr/` + the `其他/other` fallback + `99_` quarantine allowed), and FAILs (nonzero exit) printing each offending path + the pinned slug expected for its NN prefix. Wired into the `validate_structured_outputs.py` entrypoint. Prompt-level: `organizer-prompt-phase2-synthesis.md` Step 1a gains an explicit "IGNORE the source folder's own numbering/naming — never echo an incoming folder name" rule with synthetic worked examples; `bucket-taxonomy.md` §1.3 gains an imaging HARD RULE (CT/MRI/PET-CT/超声/X光/内镜影像 → `05_影像`, NEVER `04_诊断与分期`).
- **CB-P0-2 NGS targeted-exhaustive transcription + completeness floor.** NGS PDFs were being summarized down to their front-page P/LP list (losing germline VUS / pharmacogenomics / full somatic table / VAF). `organizer-prompt-phase1-ocr.md` gains an NGS/genetics-report clause (full somatic variant table one row/variant with VAF+zygosity+consequence; germline INCLUDING VUS; the PGx/drug-metabolism chapter DPYD/UGT1A1/ERCC1/… every locus; VAF verbatim; negative rule against collapsing to the front-page P/LP summary), mirroring the `ingest-adapters.md` omics_raw discipline for text/image-modality NGS PDFs. `molecular.schema.json` gains optional `germline[]` + `pharmacogenomics[]` arrays so the transcribed data has a structured home (phase2 spec updated to populate them). New deterministic **WARN-only** floor `gate_ngs_completeness`: if an NGS source exists (sidecar under `06_分子与组学/NGS报告` or an NGS entry in `source_inventory.json`) but molecular.json's `variants`/`germline`/`pharmacogenomics` are empty, it warns (WARN not FAIL — a report can legitimately lack a germline/PGx chapter, so a hard block would false-fire).
- **CB-P0-3 Staging verbatim-only (prompt-level).** organize was over-reaching by synthesizing wrong staging judgments. `organizer-prompt-phase2-synthesis.md` `summary.stage` (profile.json), `patient_summary.json.diagnosis.stage`, and `case_text.md` 诊断与分期 all gain a "verbatim TNM/stage string from source ONLY — do NOT synthesize a stage interpretation (no assembling a group from bare T/N/M, no M1/N3 labeling, no 区域外/M1范畴 qualifiers); if no clean overall stage, record components verbatim + write a `review_flags.md` entry for MTB" rule, keeping the existing verbatim/NEVER-normalize mandate.

Verification: new `tests/unit/bucket-taxonomy-gate.test.sh` (18/18) — fully synthetic drift fixtures FAIL on off-taxonomy paths and name the expected pinned slug; clean zh + en fixtures pass. The NGS floor remains WARN-only and checks only the source report's own section inventory. CB-P0-3 is prompt-level and supplemented by current source-fidelity tests.

### Changed — case-summary 段D 关键趋势 becomes N charts + chart-readout layout + interactive markers (2026-07-03)

Visual + architecture iteration of the 关键趋势 section, verified with a synthetic E2E fixture:

- **`trend_hero` (single) → `trend_charts[]` (0..N).** How many featured trend charts is now a **clinical judgement the LLM makes** (treating-physician view): one dominant marker → 1 chart, several drivers → 2–3, nothing trending → []. The count is NOT hardcoded. This required the deterministic renderer (`render_html_template.py`) to support **loops nested inside loops** (each chart iterates its own `treatment_markers`/`dots`), resolving arrays local-scope-first then root — mirroring how placeholders/RENDER_IF already resolve. Division of labour is now explicit: the LLM owns all clinical generalization (which/how-many metrics, interpretation, which treatment markers); the deterministic scripts own only the faithful pixel projection + the anti-fabrication gate (a chart must never misrepresent a real value — an LLM-drawn chart would be 伪精度).
- **Chart + readout layout.** Each chart is a two-column [chart | readout] card — chart left (moderate 3:1 aspect, not stretched), readout right (metric name, big current value, one-line interpretation). Fills the width densely with no wasted whitespace (the earlier full-width-single-chart / centered-small-chart attempts both looked sparse on a one-pager). Responsive grid: 1 chart full width, 2 side-by-side, 3 → 2+1, capped at 2 per row so cells stay ≥~320px.
- **Interactive treatment markers, print-safe.** Numbered ①② badges on each chart at the treatment-change dates + an always-visible numbered legend below (readable on paper). Hover shows a **fixed-size HTML pill tooltip** (date + event, no redundant index) that does NOT shrink with the chart — replacing the old SVG `<title>`/SVG-text tooltip that became illegible on small multiples. **Badge de-collision**: markers whose x fall within ~26 viewBox units stagger onto stacked rows so the numbers never overlap. Still zero `<script>` — survives the validator's no-JS gate and the PDF print path.
- **Density + header dedup.** Tighter vertical rhythm (padding/line-height/3-col identity); `@page` margin no longer double-counts with body padding; `one_line_condition` constrained to a ≤~35-char headline that must not restate the 病情概要 or carry marker trends; `lab_trends[].current_value` must be just the value (keeps the delta strip terse).
- Schema/prompt/SKILL updated (`trend_charts` array + "count is a clinical judgement" guidance); `compute_sparklines.py` injects per-marker `idx`/`marker_date`/`badge_cy`/`badge_pct` + `last_value`/`first_value` for the readout.

Verification: `tests/unit/case-summary-trend.test.sh` 34/34 (adds marker idx/date, badge de-collision stagger-vs-share-row, HTML-tooltip `badge_pct` presence) + `tests/integration/case-summary-trend-e2e.sh` 11/11 (adds a 2-chart multi case); nested-loop rendering verified (2/3-chart fixtures, per-chart markers resolve to the right chart); full suite green (unit 3/3 files, integration 6/6, py_compile + all-JSON-parse). Visual review across single / 2-chart / 3-chart / markers-per-chart via headless-Chrome screenshots.

### Added — case-summary 段D trend visualization + version comparison (2026-07-02)

The 病情简要总结 (段D) now shows **病情变化趋势** instead of a static snapshot, so a patient who keeps supplementing records sees their trajectory and what changed since the last summary. Full restyle to the brand purple patient-facing card aesthetic (`#e7d1ff` / `#c9a4ff`; deeper `#7c5cff` for the data line).

- **关键趋势 hero card** — the most clinically meaningful trending metric (usually the primary tumor marker) as a multi-point area+line chart, with **treatment-line start dates overlaid on the same time axis** (the 指标↔治疗方案 correspondence) + one plain-language interpretation sentence.
- **实验室指标 trend rows** — replaces the old flat 4-column latest-value grid: each key lab = name + inline sparkline + current value + status badge (正常/偏低/偏高/异常/严重).
- **自上次总结的变化 delta strip** — diffs the current render data against the previous snapshot (lab moves / new treatment lines / ECOG). First-ever summary → hidden. Every 段D generation now snapshots BOTH `病情简要总结_<date>.html` AND `case_summary_data_<date>.json` (the diff base for the next generation).
- **Data source is already-captured `longitudinal_observations.json`** (multi-point series) — this is data plumbing, not new collection. `case_summary_data.labs[]` → `lab_trends[]` (series-carrying); `trend_hero` + `version_delta` added to `case_summary_data.schema.json`.
- **Charts are inline SVG only** (canvas drops out of the Chrome→PDF print path). New deterministic zero-medical helpers: `scripts/compute_sparklines.py` (series → SVG polyline/area/dots + treatment-marker x, **plus an anti-fabrication gate — every plotted point must exist in `longitudinal_observations.json`/`labs.json`, else exit 3**) and `scripts/compute_version_delta.py` (current vs previous snapshot → `version_delta`). The renderer stays a dumb substitutor; the subagent computes no geometry and invents no number.
- **Validator hardened** (`validate_case_summary_html.py`): new gate (h) forbids `<script>`/`<canvas>`/`<foreignObject>`/`<iframe>`/`<object>`/`<embed>` + inline `on*=` event handlers, gate (i) allowlists SVG child elements. Existing style-identity / class-subset / PII / provenance / h2-skeleton gates unchanged — the new 关键趋势 section always renders (placeholder when empty) so the `<h2>` count stays stable.
- **Freshness gate** now treats `longitudinal_observations.json` mtime as a summary source (a new follow-up lab changes the curve even when no scalar field moved).

**Post-test fixes (synthetic E2E run):**
- **`lab_trends` empty → "资料缺失" even with rich labs.** The LLM producer built the hero but left the lab rows empty. Added `scripts/backfill_lab_trends.py` — a deterministic floor that, **only when `lab_trends` is empty AND `labs.json` has panels**, builds one row per panel from the structured data (name / dated series / current value / status from flag-or-range). No-op when the producer already populated it (LLM's condition-aware selection wins). Wired into SKILL Step 12 before compute_sparklines. Prompt also strengthened: `lab_trends` is now imperative (non-empty whenever any lab exists).
- **Low information density / heavy repetition.** In the real run the CEA trend repeated 5×, the OCR caveat 5×, diagnosis/regimens 3× each. Added a "信息密度与去重" contract to `case-summary-html-prompt.md`: each fact lives in exactly one 主段 — the 病情概要 narrative is now capped at 3–4 sentences / ≤120 chars and must NOT restate trend values (hero owns them), regimens/doses (治疗史 owns them), or OCR/source caveats (数据说明 owns them); the hero `interpretation` is one sentence with no inline caveat. (Prompt-level; takes effect on the next skill run.)
- **Fragile bash in the docs.** `${prev:+--prev "$prev"}` mis-parsed (literal quotes) and broke the version_delta step; replaced with an explicit `if [ -n "$prev" ]` in both SKILL.md Step 12 and the producer prompt.

Verification: `tests/unit/case-summary-trend.test.sh` (31/31 — sparkline geometry incl. 1-pt/flat/gap/min==max, anti-fabrication rejection incl. `panels[]` labs shape, version-delta, backfill from panels + no-op-when-populated + source flag status) + `tests/integration/case-summary-trend-e2e.sh` (9/9 synthetic fixtures); validator hardening gates negative-tested (canvas/script/onclick/foreignObject all rejected). Current clinical governance supersedes the older interpretation/range-grading behavior described in this historical entry.

### Changed — case-summary 段D fidelity fixes + PII gate made two-layer (prompt-primary + shape floor) (2026-06-15)

Three patient-reported 病情简要总结.html defects + a generalization fix to the PII gate.

- **Age and quasi-identifiers are context-dependent.** Current policy includes age, dates, institution and similar fields only when necessary and authorized for the stated artifact; no regex result proves that a combination is anonymous. Clinical-trial eligibility matching is outside this repository.
- **IHC parentheses preserved.** Pathology IHC was rendered `HER2 0` (parens dropped → ambiguous in `EGFR 2+; HER2 0; …`). Now rendered with the standard pathology notation `marker（value）` → `HER2（0）；EGFR（2+）；Ki-67（约5%+）` (full-width 括号 for zh). `case-summary-html-prompt.md` §核心分子检测.
- **Treatment-line labels use clinical INTENT, not auto-ordinals.** `line_label` was auto-numbered 一线/二线/三线 from the `line` integer — clinically wrong (perioperative therapy is itself first-line). Now mapped from `treatment_lines.json` `intent` → 新辅助/术后辅助/围手术期/姑息治疗/维持治疗/根治/巩固; neutral 第 N 段 fallback by `started_at` when intent is absent; verbatim-copy an explicitly documented line wording. Schema `line_label` description updated.
- **PII gate is now two independent layers (trust-but-verify).** Root cause of the birthplace/occupation leak: the regex floor could only catch pre-coded label categories — it structurally missed 出生地/籍贯/职业/家属姓名/民族 (a real run leaked all of these into `case_text.md` AND `profile.json`'s mis-named `name_redacted: <real name>` field, neither of which the gate even scanned). **Layer 1 (new, primary):** `references/pii-rescan-prompt.md` — a semantic agent scan that flags ANY identifying category by meaning over sidecar bodies + **synthesized downstream surfaces** (`case_text.md`/`profile.json`/`patient_summary.json`/…) + delivered surfaces; dispatched at Phase-1 §2.5, the Phase-2 acceptance gate (SKILL.md Step 11.5), 段C, and export. **Layer 2 (trimmed):** `scripts/pii_rescan.py` 收敛为纯 SHAPE floor (身份证18位/手机/座机/email/SSN/E.164/≥11位数字/绝对路径/云账号/denylist) — the brittle `_PII_LABEL_PATTERNS`/`_PII_LABEL_TAIL`/cross-line label arms (which couldn't generalize and historically false-fired) were removed; label/semantic detection moved to Layer 1. Either layer's finding fails the gate. Wired through phase1-ocr §2.5, conversation-incremental §段C, organize-contract §§63/185, SKILL.md, validate_structured_outputs docstring. Test 3 in `tests/unit/organize-fidelity-gates.test.sh` migrated (deterministic floor now asserts only the bare ≥11-digit shape + a negative assertion that label categories do NOT fire it); eval scenarios org-03 updated (precise age) + org-04 added (Layer-1 semantic catch). PRD: `tasks/prd-pii-rescan-prompt-hybrid.md`.

Verification: render+validate exit 0/0 with synthetic age and marker/intent fixtures; shape-floor unit checks (身份证/手机/email/≥11-digit fire; semantic categories require Layer 1); `tests/unit/organize-fidelity-gates.test.sh` and `tests/eval/lint/04-pii-desensitization.sh` pass. Historical real-patient identifiers have been removed from this changelog; regression fixtures must remain fully synthetic.

### Fixed — disclosure-gate consistency check redesigned to behavior-direction tokens (2026-06-14, round 16)

Round-4 re-audit: 1 confirmed fatal, 3 sound refutations (education's "v2 nutrition skill" content note = not a routing instruction; `latest_status.ecog=5` rejected by the profile validator while `patient_summary` allows it = unrealistic for an active patient's snapshot; vault antonym = a contrived flip — closed anyway, below).

- **disclosure-gate.sh passed-on-wrong-state for 3 companions (D11-01).** The **third** weakness the adversarial re-audit found in the round-13/14/15 disclosure-gate hardening — so instead of patching one more keyword, the consistency check was **redesigned**. The earlier keyword approach failed whenever the per-skill keyword was a token co-present in BOTH the correct and the flipped cell: a subject noun (`nutrition` → `cancer-type`, present in both "cancer-type not surfaced" and a flipped "cancer-type surfaced"), a forbidden staging word the cell tells the agent to AVOID (`find-care`/`visit-prep` → `晚期|进展后`, present whether the cell avoids OR surfaces it), a generic word (`normal`), and — refuted but real — an antonym substring (`redact` ⊂ `unredacted`). The check now asserts a behavior-**DIRECTION** token (a verb/negation a flip destroys), implemented in Python for reliable `\b` word boundaries: `organize`→`\bwarn`, `vault`→`\bredacted\b|\bmasked\b` (excludes unredacted/unmasked), `education`/`second-opinion`→`\brefuse`, `mind`→`\bcontinue`, `nutrition`→`not\s+surfaced`, `find-care`→`避免`, `visit-prep`→`\bavoid`, `disclosure`→presence-only. **Exhaustively mutation-tested: each of the 8 direction-checked companions now FAILS the guard on a realistic flipped cell** (the verification missing the previous three times), and all pass on correct content. The rule (a keyword must be a direction token, never a subject noun / trigger condition / forbidden word / generic word / antonym substring) is documented in the script header.

### Fixed — round-3 re-audit stragglers (2026-06-14, round 15)

Round-3 workflow re-audit (post-round-14): 3 confirmed fatal, 7 refuted (all sound: an unreachable gate-guaranteed legacy fallback, frontmatter-description-not-a-read, example-string-not-a-read, stale manual-smoke-test refs). Two of the three confirmed were further weaknesses the adversarial re-audit found in the round-13/14 guard hardening itself.

- **vault `data-vault.md` defined the RETIRED flat `timeline.json` shape (D2-01).** A block titled `## JSON Schema: timeline.json` documented `{version, patient_id, events[].{type,outcome,description,documents[]}}` — contradicting the canonical `timeline.schema.json` (`{patient_code, schema_version:"1", events[].{date, category(enum), title, detail, hospital, source_refs[]}}`) that `validate_structured_outputs.py` enforces, and even self-contradicting the file's own L61 prohibition. An agent taking it as authority would, on export, emit a shape that fails the gate, or on read dereference `patient_id`→null and resolve flat `documents[]` paths to dead links. Replaced the block with the canonical shape + a pointer to `timeline.schema.json` as the authority (the field names `version`/`patient_id`/`documents` are outside the round-14b flat-PROFILE-field sweep vocabulary — this was a distinct flat-TIMELINE-shape straggler).
- **case-summary precise-age de-id guard had a colon-mandatory hole (D5-1).** `validate_case_summary_html.py:_AGE_RE` required a colon in the `aged?` arm, so bare en forms `aged 63` / `Age 55` false-passed the fail-closed segment-D HTML gate, while the sibling `validate_visit_prep_html.py` caught them — a real PII-age-leak divergence between two sibling guards. Made the colon optional with the locked decade-band carve-out `(?!\s*\+)`, and added the hyphenated `63-year-old` form to **both** guards so the two siblings now have identical en precise-age coverage. Verified: `aged 63`/`Age 55`/`63-year-old`/`63 years old`/`63岁`/`63 yo` all caught; `50+`/`60+` decade bands still allowed. *(Superseded 2026-06-15: both age guards were subsequently REMOVED — precise age is now retained for clinical-trial matching; DOB still barred.)*
- **disclosure-gate.sh organize keyword collided with the trigger condition (D8-1).** The round-13/14 hardened check used keyword `suppress` for organize, but every Disclosure cell contains the trigger condition `disclosure_state=suppressed` — so the keyword was satisfied by the condition, not the behavior, making organize's assertion an always-pass (proven by mutation: flipping organize's behavior to "surface the full diagnosis" still passed). Changed organize's keyword to `warn` (unique to the behavior) and documented the rule that keywords must never be a substring of the trigger condition. Verified: organize behavior flip now FAILS the guard; all 9 companions still pass on correct content.

Verification: `tests/eval/run.sh` 5/5; integration 4/4; unit 21/21; py_compile + all-JSON-parse clean; both age guards + the disclosure-gate organize cell mutation-tested.

### Added — deterministic structured-JSON-shape guard (2026-06-14, round 15b)

The "a consumer doc shows a structured-JSON file with a retired/non-canonical SHAPE that contradicts its schema" class recurred three times (round-14 find-care fields, round-14b visit-prep template comment, round-15 vault timeline block). Per the no-sampling-for-recurring-classes discipline, added a deterministic exhaustive guard rather than picking them off one audit at a time:

- **`tests/integration/structured-json-shape.sh`** — for every `schemas/*.schema.json` with `additionalProperties:false` (a CLOSED shape), it finds ` ```json ` blocks across `skills/**.md` + `references/*.md` + `*.html` that sit under a heading naming that file, and asserts the block's top-level keys are all allowed by the schema. Heading-anchored association keeps it high-precision (no false failures on correct examples under other headings); it only flags forbidden EXTRA keys (partial examples and `//`-commented snippets are skipped), so it cannot false-fail a legitimate doc. Verified: green on the current tree (9 blocks associated, 0 violations) AND catches a planted retired-timeline block. This guard would have caught the round-15 vault timeline straggler at commit time.

### Fixed — round-2 re-audit stragglers (2026-06-14, round 14)

Round-2 workflow re-audit of the post-round-13 tree: 3 confirmed fatal (2 v3-taxonomy stragglers round-1's finders missed because the offenders use non-canonical field names, + 1 weakness the round-13 disclosure-gate hardening itself introduced). 2 refuted (a `disclosure_state="unknown"` enum mention no workflow ever produces; a duplicate framing of the find-care finding).

- **find-care "Profile completeness" table read FLAT profile.json fields (D1-1).** `skills/cancer-buddy-find-care/SKILL.md` told the agent to read `cancer_type` / `stage` / `molecular_profile` from `profile.json` — none exist in `cancer_buddy_profile_v3` (`molecular_profile` was the *only* occurrence of that key repo-wide; drivers live in the sibling `molecular.json`). A patient whose `molecular.json` was fully populated would be told "没有就先去做 NGS" or blocked on phantom-missing fields. Rewrote the table to the v3 + structured-JSON taxonomy (`summary.primary` / `summary.stage` / drivers from `molecular.json`, aligning with `preflight.md:73`) and split out the `geo`/budget/insurance rows as **query-side** fields gathered into Step-1 `QUERY.md` (not profile.json reads), so the agent no longer blocks on their absence from profile.json.
- **mind read `patient_location_hint` from the wrong file (D10-1).** `skills/cancer-buddy-mind/SKILL.md:20,55` read the patient's region from `profile.json`, but the field is defined only in `patient_summary.json` (`patient_summary.schema.json:74`) and every other consumer (nutrition, case-summary prompt) reads it there — so mind's region-specific crisis hotlines / local mental-health resources silently never surfaced. Repointed both reads to `patient_summary.json.patient_location_hint`.
- **disclosure-gate.sh round-13 consistency check was leaky (D11-1).** The hardened keyword scan used a fixed 6-line window after any line mentioning "disclosure", so an unrelated `refuse` near second-opinion's Disclosure cell (a preflight role-gate + a Role-behavior family-refuse rule) survived a flip of the real cell → false-pass. Replaced the line-window with **marker-based cell extraction** (the inline `*Disclosure*:` / `**Disclosure**` declaration line, or a `## Disclosure` section body) and skipped the disclosure skill itself (it IS the workflow, no cell keyword to assert). Verified: passes on correct content AND now catches a flipped cell for all 8 keyword-checked companions (incl. second-opinion + section-style find-care).

Verification: `tests/eval/run.sh` 5/5; integration 4/4; unit 21/21; py_compile + all-JSON-parse clean; the disclosure-gate fix negative-tested per-skill.

### Fixed — broken deterministic guards & validator v3 migration (2026-06-14, round 13)

Workflow audit (11 finder dimensions + adversarial per-finding verify) on `feat/generalized-data-taxonomy`: 11 confirmed fatal findings → 4 equivalence classes. Recurring theme: the v3 data-taxonomy migration and the `visit-prep` companion landed in skills/refs, but the **deterministic guards** (profile validator, integration tests, lint scope) were left on the old contract — several were silently broken (always-fail or green-on-wrong-shape), so they could no longer catch a real regression of the patient-facing class they guard.

**P0 — `scripts/validate-profile-schema.sh` enforced the RETIRED flat profile shape (D1-1 / D8-3 / D10-1 / D10-2 / D11-3)**
- The shipped profile validator still required flat top-level `schema_version` + `diagnosis.{primary_site,histology,stage}` + `basics.{ecog,sex}`, so it **false-rejected every conformant `cancer_buddy_profile_v3` profile** (empirically: the schema doc's own canonical v3 example exited 1 with `missing required field: schema_version`). It is invoked by `cancer-buddy-disclosure` Preflight + the shared `preflight.md` Step-3 gate (education/nutrition/second-opinion/organize), so a correctly-organized patient was blocked with a bogus "missing fields" error. Its 17 unit fixtures all used the flat shape, so 17/17-green hid the bug (green-on-wrong-schema → it could never catch a real v3 violation either).
- **Rewrote the profile.json block to v3**: require `schema == "cancer_buddy_profile_v3"`, `patient_code` (`^PT-`), `summary.{primary,histology,stage}`; ECOG validated under `latest_status`; demographics/drivers/treatment-lines validated in their own structured JSONs, not here. Kept the `disclosure_state` enum + the (already-correct) readiness.json/role.json blocks; dropped the retired `diagnosis`/`basics`/`acp_status`/`surveillance_schedule_anchor`/`treatment_history` checks.
- **Expanded the `review_flags` `allowed_category` whitelist 5 → 9** (added `cross_patient_name_collision` / `anchor_coverage_gap` / `relevance_uncertain` / `filename_content_mismatch`) to match the authoritative roster in `organizer-prompt-phase2-synthesis.md` Step 3 / `organize-contract.md` §2.4 — the 5-category list false-rejected correct organize output.
- **Rewrote all unit fixtures to v3 (21/21)** + added regression cases: legacy-flat → reject, v3-missing-`summary.stage` → reject, wrong-schema-literal → reject, the 4 newly-rostered categories → accept. Repointed the DRAFT `tasks/prd-validator-declarative-schema.md` to the v3 contract (it specified the flat shape + "preserve 100% current behavior", which would have perpetuated the bug). Verified: valid v3 accepted, the 3 regression shapes rejected; embedded python `py_compile` clean.

**P0(b) — `tests/integration/trigger-words.sh` always-failed on correct content (D11-1)**
- Its awk extracted the meta description with a single-line matcher, but the meta SKILL uses a YAML **block scalar** (`description: |`), so it captured just `|` and reported all 20 triggers MISSING on a perfectly correct SKILL.md — the trigger-routing-regression guard was dead (could never pass, so a real dropped trigger like `刚确诊` was indistinguishable from the standing false failure). **Made the awk block-scalar-aware** (append indented continuation lines until the next top-level key / closing `---`; still handles single-line descriptions). Re-synced two drifted array entries (`要不要告诉`→`告不告诉`, `不想让 Ta 知道`→`不想让对方知道`) to the meta's actual wording. Verified: passes on correct content AND fails when a trigger is removed.

**P0(b) — `tests/integration/role-matrix.sh` false-failed on find-care (D6-1 / D11-2)**
- The role-token regex required spaces around `=` (`role = patient`), but `cancer-buddy-find-care`'s `## Role behavior` used the unspaced `role=patient`, so the guard reported find-care missing all three role branches on correct content (the authority-table↔skill consistency check was permanently red). **Made the regex spacing/case-tolerant** and switched the section capture to a flag-based awk that stops at the next `## ` header (was over-running past `## References`). Normalized find-care's tokens to the spaced `**Role = …**` house style (matching the other 9 companions). Verified: passes AND catches a dropped role branch.

**P0(b) — `cancer-buddy-visit-prep` (the 10th companion) was invisible to guards & docs (D11-4 / D8-2 / D9-1)**
- `tests/eval/lint/_common.sh`'s `PATIENT_VISIBLE_SKILLS` listed only 9 companions (the comment even said "(8)"), omitting visit-prep, so lints 01 (no-clinical-translation) and 05 (citation-hygiene) never scanned it — a future drop of its verbatim-clinical rule or its i18n/safety-guardrails citation would ship undetected. **Replaced the hand-maintained list with a disk-derived `skills/cancer-buddy-*/` glob** so the lints can never drift behind a new companion again.
- `tests/integration/disclosure-gate.sh`'s `affected` array omitted find-care + visit-prep (both have real suppression-aware behavior) and only checked that the word "Disclosure" appeared anywhere. **Added both, and hardened the check** to assert each skill's disclosure declaration is consistent with its `disclosure-behavior.md` matrix cell (keyword scoped to the disclosure-declaration region so unrelated prose — e.g. an example "晚期" query — can't false-pass). Verified: passes AND catches a flipped matrix cell.
- README.md / README_EN.md / tests/eval/README.md documented a 9-companion package; added visit-prep to the module list + project tree + corrected the counts (10 companions, 12 sub-skills). Added the missing `tests/eval/scenarios/cancer-buddy-visit-prep.md`.

Verification: `tests/eval/run.sh` 5/5 green; all 4 integration tests PASS (trigger-words + role-matrix were previously failing); unit 21/21; `py_compile` + all-JSON-parse clean.

**Follow-up — complete the P2-8 i18n sweep + PII passport (regression fixes from the audit's re-run)**
- The P2-8 i18n.md §2 edit added `second-opinion` / `vault` to the "record-consuming generative" row (records-first fallback) but left their own SKILL.md `locale` step still saying "detect from the conversation language" — a new divergence. Aligned both to records-first (tie-break to conversation), matching education/nutrition/visit-prep.
- `i18n.md` §1 family enumeration omitted `visit-prep` while §2's table (post-edit) lists it. Added `visit-prep` to §1.
- `pii_rescan.py`: passport had zero coverage even within the agreed zh+en scope. Added `护照号` / `passport (no/number)` to the `id_number` label set (all 4 sites). Verified caught.

### Fixed — cross-file consistency & multi-language audit (2026-06-13)

Two-round workflow audit (8 consistency axes + 6 residual axes + 5 Python scripts). PRD: `docs/superpowers/plans/2026-06-13-taxonomy-consistency-fixes-PRD.md`.

**P0 — PII residue gate was Chinese-only (non-zh PII passed acceptance)**
- **`scripts/pii_rescan.py` now runs an unconditional zh∪en∪locale-agnostic union.** Empirically reproduced before the fix: an English discharge sidecar with 8 PII fields passed the gate with `findings=0`. Added English/Latin field labels (`patient name`/`MRN`/`SSN`/`patient id`/`phone`/`DOB`/…, colon-mandatory to avoid false-firing on prose like "cell count"/"bed rest") plus locale-agnostic standalone shapes (email, US-SSN `\d{3}-\d{2}-\d{4}`, E.164/international phone, US 10-digit). Cross-line straddle now also catches capitalised Latin names + emails. Verified: EN `Name:`/`MRN:`/`SSN`/`+1…`/email + ZH 身份证/手机/住院号 all caught; clean EN clinical prose ("cell count", "born in 1950", "bed rest", "Ki-67 63%") not flagged.
- **`scripts/validate_structured_outputs.py` inherits the fix** (it invokes `pii_rescan.scan_sidecar`), so the acceptance gate now blocks English PII too.
- **`scripts/validate_case_summary_html.py`** (segment-D HTML PII safety-net) and **`cancer-buddy-visit-prep/scripts/validate_visit_prep_html.py`** extended the same way: PII checks gained en labels + email/SSN/intl+US phone; precise-age check gained `<n> years old` / `<n> yo` / `Age: <n>` (decade bands like `50+` still allowed). `render_html_template.py` was already fully locale-agnostic — left unchanged (reference pattern).
- The case-summary deliverable filename stays the single language-independent key `病情简要总结.html` across all locales (matches the `NN_` bucket-prefix policy, SKILL.md:78); documented in the gate so it isn't re-flagged.

**P0 — profile.json half-migrated to `cancer_buddy_profile_v3` (a conformant v3 file would FAIL the verify gate)**
- The schema authority (`references/patient-profile-schema.md`) declares the nested `cancer_buddy_profile_v3` shape, but the writer, the verify gate, and ~10 downstream consumers still read the retired flat top-level fields. A v3 `profile.json` has `null`/absent top-level `primary_cancer`/`histology`/`stage`, so SKILL.md Step 7 would have falsely blocked **every** conformant profile.
- **Writer** (`organizer-prompt-phase2-synthesis.md` §2.4) now emits the v3 nested shape (`schema`/`summary{}`/`latest_status{}`/`privacy{}`/`anthropometrics{}`/top-level `source_refs`). Molecular drivers / treatment lines / demographics are NOT duplicated into profile — they live in `molecular.json` / `treatment_lines.json` / `patient_summary.json` (D2b). The `missing_items` mapping, stage-context resolver, and Step-3 review-flags field list repathed to the v3 + structured-JSON locations.
- **Verify gate** (`SKILL.md` Step 7) now checks `patient_code` / `summary.primary` / `summary.histology` / `summary.stage`; `data_sources[]`→`source_refs[]`.
- **Consumer sweep** (~10 files) repathed: `preflight.md`, `organize-contract.md`, `checklists/README.md`, `conversation-incremental-prompt.md`, education (`SKILL.md` + `cancer-type-modules.md` + `mechanism-diagrams.md`), nutrition (`SKILL.md` + `drug-food-interactions.md`), second-opinion `SKILL.md`, visit-prep `visit-prep-html-prompt.md`. `current_therapy`→`summary.current_regimen`; `molecular_drivers_known`→`molecular.json`; `treatment_history`→`treatment_lines.json`; `demographics`→`patient_summary.json`. Reply-template `<current_therapy>` render placeholders left verbatim. Verified: zero residual flat reads; v3 example parses; writer→gate→consumer trace consistent.

**P0 — patient-facing routing dead-end + scope-boundary drift**
- **organize's "Next-step guidance" routed every patient (the most common entry point) to `cancer-buddy-explore` / `cancer-buddy-mtb-lite` / `cancer-buddy-trial-match`** — three clinical skills that ship in **neither** the public package nor as installable pro-skills (they moved to the private `cancer-buddy-pro-skill` per `roles.md` / `disclosure-behavior.md`). A public patient following the routing hit a dead end. Rewrote it to route only to shipped companions (`education` / `find-care` / `visit-prep`) + the meta router's conditional vMTB detection (mirrors `cancer-buddy/SKILL.md` 「MTB 路由」). The two cautionary "do-NOT-route-while-red-flags" mentions of mtb-lite/trial-match now carry a `(pro-skill)` qualifier.
- **`cancer-buddy-education` hard-required an MTB report** (a pro-skill/vmtb output) and referenced `cancer-buddy-manage` + a **broken** `cancer-buddy-access/references/access-pathways.md` link. Softened: the handbook now works from organize's `profile.json` + structured JSONs alone (MTB report optional enrichment); manage/access are noted as pro-skill-when-available; broken ref removed.
- **`tests/integration/journey.md`** (pre-split smoke test) flagged with a public/pro scope banner — Steps 2–4 (explore/mtb-lite/trial-match) only run when the pro-skill is installed.
- **Crisis-hotline list diverged** — the national 国家卫健委 line `12356` was in the meta SKILL crisis block but absent from `crisis-resources.md` (the SoT) and `safety-guardrails.md`. Added `12356` to the SoT table, aligned `safety-guardrails.md` to the canonical set (`12356` / `400-161-9995` / `010-82951332` / `021-64383562` / `120`, fixing a duplicate-number listing) and pointed it at the authoritative table.

**P1 — `longitudinal_observations.json` declared but never actually produced or validated**
- The schema authority + `schemas/README.md` + SKILL.md Outputs list `longitudinal_observations.json`, but the Phase-2 worker had no step that wrote it (only a passing mention), it was missing from the worker's own canonical-output recap, and the acceptance gate never validated it. Per D3 (real output): added an explicit conditional production sub-section (`organizer-prompt-phase2-synthesis.md` §2.6a) — write it when timeseries/trended data exists, schema-validate before writing, omit when absent. Added to the worker's two output recaps.
- `validate_structured_outputs.py`: added `longitudinal_observations.json` to the validated set (missing-tolerant → only validated when present), and extended `collect_source_refs` to also walk the singular `source_ref` field (longitudinal carries one per observation) so its anchors validate too. Verified: compiles; singular + plural anchors both collected.
- Runtime-parity recap (`SKILL.md` §Runtime adaptation) and the incremental rewrite-eligibility list (`SKILL.md` §Incremental mode) now include `longitudinal_observations.json` (+ `source_inventory.json` / `review_summary.md`), closing the producer-coverage holes the audit found in the incremental path.

**P1 — `AGENTS.md` producer attribution drift**
- `organize-contract.md` §2 overview listed `AGENTS.md` inside Phase-2's output set, and SKILL.md:71 said "Phase 2 writes everything except the 段D HTML" — but `AGENTS.md` is actually written by orchestrator Step 13, *after* the confirm gate, because it copies the **user-corrected** `profile.json` (the Phase-2 worker prompt never references it — `grep AGENTS` = 0). Moved it to a distinct post-Phase-2 contract step (Step 5, alongside 段D), annotated the §2.2 detail row, and carved it out of SKILL.md:71's Phase-2 statement.

**P1 — `modality` enum example drift (BAM/FASTQ mis-classed)**
- `bucket-taxonomy.md` §2 and `source_inventory.schema.json` listed `VCF/BAM/FASTQ/expression matrix` as `omics_raw` examples, but `ingest-adapters.md` (the dispatch authority) routes BAM/FASTQ to `binary_other` (not LLM-readable → `[INGESTION_BLOCKED]`), reserving `omics_raw` for parseable payloads (VCF / annotated TSV / expression-methylation matrix). A reader trusting the stale examples would expect an omics parser to run on a BAM. Corrected both stale example lists to match the authority; BAM/FASTQ now shown under `binary_other` everywhere.

**P2 — checklist YAML schema non-uniformity**
- **`reason` field**: `checklists/README.md` said every item needs `priority` + `category` + `reason`, but many shipped items (and the whole `followup` block) omit `reason`, and neither the worker nor `missing_items.schema.json` enforces it. Relaxed the README to "`priority` + `category` required; `reason` recommended".
- **Surveillance block name unified**: the top-level forward-looking block shipped under three names (`postoperative_followup` ×13, `response_followup` DLBCL, `posttreatment_followup` HNSCC) and was undocumented in the README schema. Renamed all 15 to a single `followup:` key and documented the block (forward-looking; not unioned into the missing-now diff). All 19 YAMLs still parse.
- **Stage-context resolution** (`organizer-prompt-phase2-synthesis.md` §2.7) only mapped TNM keys (I/II/III/IV + BCLC) and silently ignored the non-TNM keys actually shipped (THCA histology `DTC`/`MTC`/`ATC`, UCEC `early`/`advanced`). Extended the resolver to those keys + a general non-TNM fallback (`stages.all` is always the floor).

**P2 — pipeline / i18n documentation hygiene**
- **Locale fallback** for the record-consuming generative sub-skills (`education` / `nutrition` / …) detected from records-first, but `i18n.md` §2's table only had rows for organize (records) and chat sub-skills (conversation) — leaving these uncategorised. Added a third row naming the record-consuming generative skills (reuse `profile.json.locale`; fallback = records, tie-break to conversation) and aligned education's wording to it.
- **Single-pass threshold** (`SKILL.md` §Why fan-out) said `< 30 files OR no subdirs`, contradicting the governing Step-2 slicing rule (`≤ 15 files`). Reconciled to `≤ 15 files and no actionable sub-directory split`.
- **Stale section number**: SKILL.md ×2 + phase1-ocr.md called the review_flags audit `§4.6`; the authoritative phase-2 prompt numbers it `Step 3`. All repointed to `Step 3`.
- **Dangling cross-reference**: the phase-2 prompt cited `legacy organizer-prompt.md §4.6b` (a file deleted in the prompt split) for the `review_flags.md` template. Repointed to the authoritative format contract in `patient-profile-schema.md` § review_flags.

### Fixed — pre-live-testing review (adversarial multi-dimension bug sweep)

10 confirmed bugs (none in the AGENTS.md feature) fixed before live testing; no P0.

**P1**
- **PII gate false-positives on clean Chinese records** (`scripts/pii_rescan.py`) — `_TAIL_SEP` made the colon optional and `_PII_LABEL_TAIL`/`_PII_LABEL_PATTERNS` included bare `患者`/`病人`, so any clinical line ending in "患者"/"病人" followed by a 2–4 字 line was mis-flagged as a name straddle → `validate_structured_outputs` PII gate failed on clean records. Now the cross-line label requires a trailing colon and only the unambiguous field labels `患者姓名`/`姓名` count. Verified: clean clinical text passes, real `姓名：`/`身份证：`/手机 still caught.
- **Spurious coverage-gap retry on every re-run** (`organizer-prompt-phase2-synthesis.md` Step 0) — `raw/_FILENAME_MAPPING.md` (audit artifact, no sidecar) was counted as an uncovered source. Step 0 now excludes `_FILENAME_MAPPING.md` / `_*.md` from the count and diff.
- **conversation-incremental hardcoded zh bucket slugs** (`conversation-incremental-prompt.md` Step 4a) — `mkdir`'d a phantom Chinese `07_检验/…` tree on non-zh archives. Now resolves `$domain_dir` by the stable `NN_` prefix against the existing (locale-localized) bucket; never hardcodes the zh slug.

**P2**
- **Checklist coverage expanded + runtime fallback** — shipped YAMLs went from 5 → **19** common cancer types (added SCLC, EC, PDAC, OC, CCA, PC, CC, UCEC, THCA, NPC, RCC, BLCA, DLBCL, HNSCC; NCCN/CSCO/ESMO 2024-grounded). `missing_items.json` §2.7 no longer `Load`s a non-existent YAML for an unshipped code — it **generates the checklist in-session** (marked `checklist_version: <code>-rt<date>` + `checklist_generated_runtime` warning), never silently emitting an empty checklist.
- **review_flag `category` template said `<one of the 8>` but the audit has 9** (`phase2-synthesis.md` L516) → `<one of the 9 …>` (dropped category `filename_content_mismatch`). L89's "8th category" for `relevance_uncertain` is correct and left as-is.
- **Checklist README field path** `profile.json.diagnosis.stage` (nested) → `profile.json.stage` (flat).
- **Two off-by-one repo-root relative links** — `conversation-incremental-prompt.md` L55 and `bucket-taxonomy.md` i18n references (`../../` / bare → `../../../references/…`).
- **Patient-facing HTML summary now has dated version control** (`SKILL.md` Step 12) — every (re)generation snapshots to `case_summary_versions/病情简要总结_<date>.html` while the root file stays the latest, so a re-render never destroys the version a patient already shared. The freshness-gate trigger list now also includes a full-run 段E `回收` reclassify (previously could leave the summary silently stale).
- **bucket-taxonomy §1.2 raw/ naming** said `<source_id>__<basename>` but Phase-1 cp / §4 / Phase-2 `raw_path` all use the plain `<original_subdir>/<basename>` → reconciled to the plain form (the `file_id`↔`raw_path` link lives in `source_inventory.json`, not the filename).

### Changed — `feat/generalized-data-taxonomy` (organize iteration: raw vault, citations, classification correctness)

An 8-item iteration on top of the v3 taxonomy. Originals are now kept verbatim, the patient-facing Q&A
cites its sources, classification is double-checked, and the archive now self-describes so any later
session can find and read it.

- **Image-level redaction (段B) removed; `raw/` vault added.** The pixel-redaction subsystem is gone
  (`redaction-job.md`, `run_redaction_job.py`, and the `redaction_manifest`/`redaction_status`/
  `source_redaction_status` schemas + their unit tests were deleted). Uploaded originals are now kept
  **verbatim** in `raw/` (renamed from `90_原始文件镜像`), never pixel-redacted, never deleted.
  **Sidecar text PII masking stays** (`phase1-ocr.md §2.4` + `pii_rescan.py`) — desensitization is
  text-only, so every downstream JSON / patient answer remains de-identified while the patient keeps
  their raw record. `safety-guardrails.md` rewritten accordingly; 段E unrelated-file deletion unchanged.
- **Source ↔ sidecar deep-link mapping.** `source_inventory.json` now carries `file_id` (1:1 with a
  sidecar), `raw_path` (→ the verbatim original in `raw/`), and `page_range`; `INDEX.md` gains
  `file_id` / `Raw Original` / `Pages` columns. A multi-document upload (one PDF = discharge + labs +
  pathology) becomes several sidecars sharing one `raw_path` with distinct `file_id` + `page_range`,
  so a frontend can render a `.md` and deep-link "view original" to the right pages.
- **Patient supplements route to the real domain.** Conversation-incremental notes now file into the
  corresponding clinical domain's `conversation_notes/` (e.g. a lab value → `07_检验/`), not always
  `14_患者自管补充/` (now the no-domain fallback).
- **filename↔content second-check (9th review_flag).** New mandatory Phase-2 Step 1b·5 re-reads each
  `.rename_plan.json` entry against its sidecar content and corrects/ flags a wrong `doc_type`/bucket
  (the "肿瘤标志物 file that isn't tumor-marker content" bug) → `filename_content_mismatch`.
- **Patient-facing source citations.** `cancer-buddy` answers that draw on the archive now append
  `<sup>[n]</sup>` markers + a footnote list (date · doc_type · hospital — bucket-relative path) reusing
  each fact's `source_refs[]`. A documented **Archive Read Protocol** (profile → readiness → INDEX →
  targeted JSON → anchored md; selective, never whole-folder, never `raw/`).
- **Per-patient `AGENTS.md` recall pointer (cross-session discovery).** `organize` now writes an
  agent-facing `AGENTS.md` into `patients/<code>/` (Step 13, always on a `full` build, filled from the
  organize-owned template
  [skills/cancer-buddy-organize/references/templates/agents-md.template.md](skills/cancer-buddy-organize/references/templates/agents-md.template.md)).
  A pre-existing archive lacking `AGENTS.md` is backfilled on next read.
  Harnesses that auto-load `AGENTS.md` from the cwd (pi, Claude Code) then get — in **every session
  whose cwd is in the patient dir** — the patient identity + a routing table (which structured file
  answers which question) + a **two-layer drill-down** rule (top-level JSON → `source_refs` /
  `source_inventory.json` sidecars) + the verbatim-citation / no-fabrication floor. This fixes "patient
  organized records but a later session can't find/read them" without the cancer-buddy skill having to
  be invoked first (the floor holds skill-less; the skill adds the full citation rendering on top). Only
  `{{patient_code}}` + `{{one_line_condition}}` are injected, **copied verbatim from `profile.json` (no
  LLM synthesis)**; idempotently re-filled on incremental / reconciliation runs. The template is
  **locale-agnostic**: an English agent-facing scaffold (the repo convention) that hardcodes no
  localized bucket slugs — drill-down follows each fact's `source_refs[]` / `source_inventory.json`
  (already this archive's real, locale-correct paths), buckets keyed by stable `NN_` prefix — plus a
  floor rule to **answer the patient in `profile.json.locale`** (clinical entities verbatim). One
  template serves zh / en / fr archives correctly.
- **Case-summary freshness gate.** Incremental / upload / conversation runs that change a summary-source
  field now detect staleness and **prompt** the user to regenerate `病情简要总结.html` (rendered per
  `profile.json.locale` — the summary template is already fully localized), instead of silently
  re-rendering or going stale.

### Changed — `feat/generalized-data-taxonomy` (bucket taxonomy v3: longitudinal multi-modal data layer)

Generalizes the organize bucket scheme from a tumor-document-centric layout into a longitudinal,
multi-modal, multi-disease data layer (oncology + rare-disease + chronic + healthy-baseline). **Clean
replacement — no migration of existing patient directories, no backward-compatibility layer**; a dir
under the old scheme is simply re-run through `organize`. Authoritative definition:
[skills/cancer-buddy-organize/references/bucket-taxonomy.md](skills/cancer-buddy-organize/references/bucket-taxonomy.md)
(`scheme_version: 3`) — every other reference now defers to it.

- **One classification axis = clinical domain.** Replaces the prior axis-mixing (document-type +
  synthesized-state `00_当前状态` + provenance `09_患者补充` + infra `10_原始文件`) with **14 visible
  clinical domains** `01_身份与基础信息 … 14_患者自管补充` plus 2 hidden infra buckets. `00_当前状态` is
  **removed** (it was synthesized output already in `profile.json`/`case_text.md`, never raw uploads).
- **New domains** filling prior coverage holes: `02_既往史与家族史`, `03_病程与叙事文书` (admission/
  discharge/progress notes), `09_手术与操作` (split from treatment), `10_随访与监测` (wearable/PRO/home
  monitoring), `12_心理社会与支持`, `13_行政与财务` (consent/bills/insurance). `06_分子与组学` expands to
  WES-WGS / 转录组 / 甲基化 / 蛋白-代谢 / 微生物组; `11_诊断证明` folds into `04_诊断与分期/诊断证明`.
- **Original mirror `10_原始文件` → `90_原始文件镜像`** — moved out of the clinical band into the infra
  band (never anchored, so no patient anchors migrate; prose/script mentions only).
- **Modality tag** (orthogonal to domain): every filed source records `modality` ∈
  {`text`,`image`,`structured`,`omics_raw`,`timeseries`,`binary_other`} in `source_inventory.json` and
  the sidecar header; it drives ingest-parser dispatch. New
  [references/ingest-adapters.md](skills/cancer-buddy-organize/references/ingest-adapters.md) defines
  per-modality ingestion (omics → `molecular.json`; timeseries → longitudinal store).
- **Longitudinal store** — `timeseries`/trended `structured` sources parse into a new
  `longitudinal_observations.json` (`schemas/longitudinal_observations.schema.json`,
  `longitudinal_observations_v1`); the raw export is filed in `10_随访与监测`. `profile.json` gains a
  `longitudinal_observations_ref` + `latest_status` snapshot. This is the substrate for
  单时间点 → 多时间点 → 纵向曲线 → 治疗反应轨迹.
- **Propagated** to: `organize-contract.md`, phase1/phase2 prompts, `i18n.md §6`, `anchor-contract.md`,
  `SKILL.md`, `patient-profile-schema.md`, `safety-guardrails.md`, redaction-job + runtime bindings,
  the schemas (`source_inventory`/`patient_summary`/`redaction_manifest` + new `longitudinal_observations`),
  the downstream `cancer-buddy-visit-prep` skill, and the lint/unit tests. Anchor regex `^[0-9]{2}_…`
  unchanged (already matches the new prefixes). ⚠️ Twin repo `cancer-buddy-organize-local-skill` must
  receive the same structural change (dual-repo sync rule).

### Added — `feat/cancerdao-platform-organize` (海外站病历整理新时序, single-repo)

The cancerdao-platform overseas站 runs the two existing pipelines as **one new 5-segment sequence**, all landing in `cancer-buddy-skill` on one branch. The PaddleOCR redaction engine is vendored in from `cancer-buddy-organize-local-skill` so the platform runs the whole flow from a single repo. Spec: `docs/superpowers/specs/2026-06-07-overseas-platform-organize-design.md`.

- **段A — central `ocr/` deprecated; MD co-located in buckets with mandatory PII desensitization.** Phase 1 now masks PII at the text level by force (no env switch) — the MD is the downstream-only read source and may carry no plaintext PII; desensitization touches PII only, never clinical characters. Phase 2 makes the LLM canonical-rename judgment (`.rename_plan.json`, not regex), moves each source file **and** its desensitized MD into the same bucket subdirectory (`<bucket>/<canonical>.<ext>` + `<bucket>/<canonical>.md`), migrates every anchor to the bucket-relative path, drains and deletes the temporary central `ocr/` staging dir, and emits `redaction_manifest.json`.
- **段D — `病情简要总结.html`** ([references/case-summary-html-prompt.md](skills/cancer-buddy-organize/references/case-summary-html-prompt.md) + [references/templates/case-summary.template.html](skills/cancer-buddy-organize/references/templates/case-summary.template.html)). Auto-generated after the Profile Card from desensitized JSONs only (never raw images): a 1:1 reproduction of the gold-standard template. The 病情概要 narrative is subagent-generated (no hardcoded keyword/template stitching); all other sections are field-mapping; identity stays coarse-grained (女 / 50+ / 海外), `null` → 待主治医师补充. *(Superseded 2026-06-15 — see top [Unreleased] entry: precise age is now retained for clinical-trial matching; name/DOB/birthplace/occupation masked.)*
- **段B — async PaddleOCR pixel-redaction job** ([scripts/redact_ocr.py](skills/cancer-buddy-organize/scripts/redact_ocr.py) vendored + [scripts/run_redaction_job.py](skills/cancer-buddy-organize/scripts/run_redaction_job.py) + [references/redaction-job.md](skills/cancer-buddy-organize/references/redaction-job.md)). organize does not block on it; the platform worker picks up `redaction_manifest.json` and runs the job with `~/.venvs/mtb-ocr`. Per-file QA gate re-scans for residual PII before the **irreversible** original delete — bucket copy + `10_原始文件/` mirror are replaced with the redacted version and the pre-redaction original is deleted **only when `qa_passed: true`**; QA failure keeps the original and marks `failed`. Idempotent/retryable via `redaction_status.json`; missing venv → all `blocked`. Contracts: `redaction_manifest.schema.json` (`redaction_manifest_v1`) + `redaction_status.schema.json` (`redaction_status_v1`).
- **段C — conversation-incremental mode** (`run_mode: "conversation_incremental"`, [references/conversation-incremental-prompt.md](skills/cancer-buddy-organize/references/conversation-incremental-prompt.md)). Captures archivable facts surfaced while *chatting* (new diagnosis/lab/treatment/symptom/ECOG) → maps to a profile field / timeline row → diff card → user confirmation → write. Provenance uses the new `[[src:conversation:<ISO8601>]]` anchor; confirmed facts land in `09_患者补充/conversation_notes/` tagged `patient_curated`. **Unconfirmed talk never touches formal fields**, so a mis-spoken value can't poison downstream reports. Does not re-OCR or re-run synthesis.
- **Anchor contract + safety guardrails extended** ([references/schemas/anchor-contract.md](skills/cancer-buddy-organize/references/schemas/anchor-contract.md) + [../../references/safety-guardrails.md](references/safety-guardrails.md)). File anchors are now bucket-relative (`ocr/` and `02_脱敏病历/` prefixes deprecated/rejected); conversation anchors added. New "platform redact-then-delete" carve-out gates the original delete behind `qa_passed: true`; the `10_原始文件/` mirror keeps the **redacted** version (the audit chain itself is desensitized). 不捏造 / 脱敏只遮 PII 不改临床字符 red lines unchanged.
- **段E — medical-relevance gate + 无关文件处置门** ([references/relevance-gate.md](skills/cancer-buddy-organize/references/relevance-gate.md); Phase 2 Step 1·0 triage + Step 3b `relevance_uncertain` flag; SKILL.md disposition门). Phase 2 triages every uploaded file by **LLM judgment (not a keyword list)** into medical (→ 11 buckets) / non-medical-high-confidence / borderline before classification. Non-medical files are quarantined to `99_无关文件/` (`high_confidence/` vs `uncertain/`) — never bucketed, OCR'd, or anchored. After organize a disposition notice surfaces with the **mandatory privacy-floor sentence** "我们不保存你的原始无关文件 —— 你不确认，我也会自动删除". Resolution: high-confidence non-medical **auto-deletes on no-confirm** (silence ⇒ delete, by design); "X 其实有用" reclassifies a file back into its bucket (late-arriving medical record); **borderline `relevance_uncertain` files are NEVER auto-deleted** — held in `99_无关文件/uncertain/` until the user explicitly chooses 删/留 (8th review_flag category). This is the **second** controlled irreversible-deletion exemption in `safety-guardrails.md` (after 段B). Every action logged in `update_log.json.relevance` (`auto_deleted[]` ledger).
- **扩段C — upload reconciliation** (`run_mode: "upload_reconciliation"`, [references/upload-reconciliation.md](skills/cancer-buddy-organize/references/upload-reconciliation.md)). Re-uploading files onto an existing `patient_dir` runs the 段E relevance gate, then an **LLM new/supersede/conflict relation判断 (not a hardcoded same-name-same-date Python check)** → a diff card asking 替换? 并存? 忽略?, **reusing段C's single "先确认" gate (no second gate)**. 替换 archives the superseded doc to `_superseded_<ts>/` (**archived, not deleted**) + remaps anchors; 并存 keeps both + adds a second timeline row; 忽略 / 未确认 writes no formal field; conflict is shown side-by-side and never silently overwritten (关键字段 conflicts require explicit confirmation). Introduces **no new auto-deletion** — the only auto-delete remains 段E's high-confidence non-medical path. `update_log.json` gets a `run_mode: "upload_reconciliation"` entry.
- **段E2 — shared confirm-gate (消除确认门漂移)** ([references/confirm-gate.md](references/confirm-gate.md)). The "nothing formal without confirmation" floor is now a **single shared authority** instead of being re-stated per caller: every companion run that would write a formal artifact (`profile.json` field / `timeline` row / structured JSON) or irreversibly remove a file passes through **one** gate — plain-language diff card + explicit confirmation. 段C (conversation-incremental), 段E (relevance-gate), and upload-reconciliation now **cite** this gate and keep only their own specialization (archivable-fact categories / relevance classes / new-supersede-conflict relations); they no longer re-define the confirmation rule. The reason for sharing rather than re-implementing: a confirmation rule that drifts per skill is worse than none — a mis-spoken value, a stray upload, a contradicting re-upload must all hit the *same* floor. Owns the load-bearing **irreversible-delete asymmetry** (high-confidence non-medical: silence ⇒ delete by design; borderline `relevance_uncertain`: silence ⇒ hold, never auto-delete), the universal diff-card contract, and the `update_log.json` "no gated write/delete without a matching entry" requirement. Candidate detection/classification stays **LLM judgment**, not a hardcoded keyword/same-name-date comparator. Diff card is patient-facing scaffold → localized per [references/i18n.md](references/i18n.md); clinical entities inside the card stay verbatim.
- **段E3 — companion safety eval framework (4 安全维度: static lint + LLM-judge scenario)** ([tests/eval/](tests/eval/) — `run.sh` + `lint/` + `scenarios/` + `README.md`). A safety-focused behavior-regression harness for the 9 companion skills (8 patient-visible + meta router), guarding four dimensions that route a patient wrong if they regress silently: (1) clinical entities never translated, (2) C-SSRS crisis path exists and is non-overridable, (3) never recommend a treatment / make a clinical decision, (4) PII desensitization mandatory. Each dimension has a **static lint** (`lint/01..04`, runs now, no deps, exit-code convention) asserting the *guardrail wiring* — that the rule is present, cited by the skills that must obey it, and backed by its scripts/schemas; a cross-cutting `lint/05-citation-hygiene.sh` enforces the citation graph (every patient-visible skill cites guardrails + i18n; the data-writing skill cites `confirm-gate.md`; no dangling shared-doc refs). Each lint was negative-control tested (goes red when its guarded property is removed). The *behavioral* half — that a live turn actually kept `osimertinib` verbatim, actually interrupted on passive ideation, actually refused to rank a regimen, actually produced a PII-free sidecar — is **specced in `scenarios/`** (one per companion) and **honestly gated on a future LLM-judge harness** (`run.sh` runs ONLY the static lints and does not claim the scenarios passed). The judge must be an **LLM-judge reading the rubric**, not a hardcoded keyword pass/fail list. Complements the existing `tests/unit/` (schema) + `tests/integration/` (journey/crisis/role/trigger/disclosure) suites.
- **段E5 — second-opinion freshness + verify-before-send** ([skills/cancer-buddy-second-opinion/SKILL.md](skills/cancer-buddy-second-opinion/SKILL.md) §1.5 + Safety). `top-centers.md` / `cross-border-shipping.md` are now treated as **routing hints, not a current source of intake/contact truth**. Before any target center's contact / intake process / shipping address / program status is quoted into **any** artifact (cover letter, shipping instructions, records-index destination), a **live web check via `web-access`** against the center's official international-patient page confirms the current international-office contact, second-opinion intake + required materials, eligibility, and **whether the program is still open**. **Live result wins** over the catalogue; unreachable / unconfirmable items are marked `需用户自行向中心确认 / to be confirmed by the patient directly with the center` — **no silent fallback to the stale static value** (the medical-agent no-silent-snapshot red line in [references/safety-guardrails.md](references/safety-guardrails.md)). This is **routing/logistics fidelity (where + how to send), never evidence synthesis** — clinical entities stay verbatim; the check never edits the patient's clinical content. The reconcile step is **LLM-driven over the live page**, not a hardcoded "what changed" keyword list. Rationale: a stale contact packaged as if current sends irreplaceable pathology blocks to a dead address and burns a scarce one-shot cross-border slot.
- **organize 运行时解耦 — agent-agnostic 契约 + binding 矩阵** ([skills/cancer-buddy-organize/references/organize-contract.md](skills/cancer-buddy-organize/references/organize-contract.md) + [references/runtime-bindings/](skills/cancer-buddy-organize/references/runtime-bindings/) `claude-code.md` / `headless-codex.md` / `_template.md`; each prompt gains a `Runtime adaptation` section). The two-phase organize was deeply bound to **Claude Code-only mechanisms** (`Agent` fan-out + reduce, path-based `Read`, `sips` HEIC decode, the ≤15-image-per-worker multi-image budget, inline diff-card confirmation), so a non-CC host (the cancerdao-platform's headless codex GPT-5.5 单进程 sandbox) couldn't drive the new sequence and fell back to the old organize — losing 进桶 + 段B, so all 77 原图 were dropped and the archive wasn't browsable. This release splits organize's **behavior contract** from its **runtime mechanism**: `organize-contract.md` defines the four steps (Phase1 per-file 脱敏 OCR / Phase2 综合 / 确认门 / 段B 像素打码) as pure inputs→outputs with **zero tool names**, so any agent system (Claude Code / codex / workbuddy / OpenCode / Cursor / …) drives the **same contract** with a thin adapter. The 5-seam matrix (编排 / OCR 源 / 图像解码 / 确认门 / 存储) is host-fillable; `runtime-bindings/` ships the **Claude Code binding as the reference implementation** (the existing `Agent`/`Read`/`sips`/inline mechanism kept verbatim — CC path 零退化、行为/产物零变化), a `headless-codex.md` draft (codex `-i`/PaddleOCR OCR, 单进程顺序, confirm-as-product+UI, heif-convert, host-assigned file_id + 机械 mv/persist), and a `_template.md` for third parties. Same nature as 段C/PR #12: the **contract is unchanged — only "谁执行机制" is now swappable**. **Logic / schema / 产物结构 are untouched** (脱敏 MD、进桶、canonical 改名、`redaction_manifest.json`、review_flags、6 结构化 JSON 全不变); no Python script changed (`redact_ocr.py` / `run_redaction_job.py` / `validate_structured_outputs.py`). HEIC `sips` and ≤15-image slicing are re-labelled host-tunable seams rather than written-in CC primitives. Rationale: one contract + N thin bindings prevents per-host fork drift (a fork of the whole pipeline per host). Spec: [docs/superpowers/specs/2026-06-08-organize-agent-agnostic-contract-prd.md](docs/superpowers/specs/2026-06-08-organize-agent-agnostic-contract-prd.md); closes the issue #13 思路 (平台 codex headless 驱动不了新两阶段 organize).
- **i18n — whole-skill locale auto-detection + scaffold localization** ([references/i18n.md](references/i18n.md); applies to **every patient-facing sub-skill**, not just organize). cancer-buddy now auto-detects the patient's `locale` (organize from the medical-records' main language; chat sub-skills — mind/caregiver/disclosure/… — from the conversation language) and **persists it to `profile.json.locale`** (BCP-47: `en` / `fr` / `es` / `zh`); detect-once, reuse-everywhere keeps the whole patient journey in one language. Mixed-language records take the patient-facing main language (tie-break to the patient's own spoken/written language). All patient-facing output (reports / handbooks / screeners / diff cards / routing copy) localizes the **scaffold only** — section titles, narrative connectors, field labels, user copy, date format — via locale string tables (templates) or `output in <locale>` prompt instructions, never a hardcoded single-language string. **Clinical entities stay verbatim**: drug names / genes / variants / TNM / numeric values & units are never translated (mistranslation = medical risk) — a new red line in [references/safety-guardrails.md](references/safety-guardrails.md). organize specifics: bucket folder names are localized (`02_diagnosis_staging` / `02_diagnostic_stadification`) while the **`NN_` numeric prefix stays a language-agnostic stable key** so anchor regex `[0-9]{2}_…` and downstream numeric-prefix matching keep working; the 段D HTML pulls section titles / disclaimer / 待补充 placeholders from a locale→string table with CSS+structure 1:1 unchanged. `patient-profile-schema.md` gains the `locale` field; `terminology.md` generalizes from fixed 中英 → locale-aware (clinical term verbatim + locale plain-language gloss).
- **E6 — E2E fixes (确定性渲染 + OCR 归位 + 验收硬门)** ([skills/cancer-buddy-organize/scripts/render_html_template.py](skills/cancer-buddy-organize/scripts/render_html_template.py) 355 行 + [scripts/validate_case_summary_html.py](skills/cancer-buddy-organize/scripts/validate_case_summary_html.py) 246 行 + [scripts/pii_rescan.py](skills/cancer-buddy-organize/scripts/pii_rescan.py) 273 行 + [skills/cancer-buddy-visit-prep/scripts/validate_visit_prep_html.py](skills/cancer-buddy-visit-prep/scripts/validate_visit_prep_html.py) 193 行; SKILL.md Step 12 + 各 prompt/契约). An end-to-end pass surfaced four 失真 points where a subagent could *say* it produced the 段D/F1 HTML while actually hand-stitching markup, drifting CSS, or leaking PII — so this release makes the load-bearing产出 **deterministic and gated**, with the **防过拟合** invariant that renderer/validator carry **zero medical or case logic**.
  - **段D / F1 HTML 走确定性渲染,禁手写。** A new generic, **stdlib-only (no jinja2 — runs in any Claude Code / codex sandbox / host)** template engine `render_html_template.py` substitutes `{{key}}` and expands `<!-- LOOP -->` / `<!-- RENDER_IF -->` / `<!-- RENDER_IF_NOT -->` purely from a data JSON — it is **data-driven 0..N** (几个 lab/lesion/治疗线就渲几个; 空 section → `资料缺失` 占位,**section 不删**), so the same engine serves a patient with 12 labs and a patient with none without a code path per case. The subagent's only legal output is a `*_data.json`; it **never writes/edits HTML/CSS/DOM**. The engine stamps a `template_sha256:` provenance comment proving the HTML came from the template. Both 段D (`病情简要总结.html`) and **visit-prep F1 (`就诊准备包.html`) share the one engine** (visit-prep calls into the organize skill's copy).
  - **form-validators 只查"形"不变量,不断言内容。** `validate_case_summary_html.py` / `validate_visit_prep_html.py` assert **only template-fixed, patient-independent invariants** — byte-identical `<style>` block, used-classes ⊆ template classes, no residual `{{…}}` markers, no PII / no precise age, full section skeleton, and `template_sha` == the template's SHA-256. *(Superseded 2026-06-15: precise age is now ALLOWED — the `_AGE_RE`/`EXACT_AGE_PATTERNS` guards were removed from both validators; DOB still barred.)* They **deliberately never assert specific clinical content exists** (e.g. no "must contain `.lab-grid`" — that would false-positive a无化验 patient and 误杀). Shape break (hand-written HTML / 漏渲染 / 越界 class / 泄 PII) ⇒ exit 1, fail-closed.
  - **OCR = 原生视觉读图;PaddleOCR 只在段B.** 段A 文本抽取走原生视觉模型读图(叙事/分类/抽取仍是 LLM 判断,临床实体 verbatim),不再把 PaddleOCR 拉进文本管线;PaddleOCR 仅用于段B 的异步像素打码作业,职责单一。
  - **PII 复扫门 (`pii_rescan.py`).** A deterministic PII-residue门 on the desensitized MD sidecars — the single downstream plaintext boundary. Re-scans sidecar bodies with `redact_ocr.py`'s regex family (text-only, **no OCR/image deps**), skips already-`[PII_MASKED]` values + the `## PII` trailer, flags any surviving label+value or standalone 身份证/手机/座机. It is a **detector, not an auto-rewriter** (re-masking is a judgement task left to the LLM).
  - **SKILL Step 12 硬 gate + 总验收门.** organize SKILL.md Step 12 is now a hard gate: organize is "complete" only after (1) `病情简要总结.html` was produced by `render_html_template.py` (a subagent pasting inline HTML fails here), (2) `validate_case_summary_html.py` exits 0, with the **`template_sha`** echoed back into the final user report as the proof-of-template. `validate_structured_outputs.py` becomes the **total acceptance门** — one entry, aggregated exit code — folding the original 6-output schema + anchor validation **plus** `pii_rescan`, a redaction-manifest non-empty-if-images check, and the case-summary HTML shape+provenance check. Missing *optional* artifacts are not errors (validates what exists, not what a 模板 patient would have). visit-prep gets the **same** rendered-then-validated floor (`render_html_template.py` → `validate_visit_prep_html.py` exit 0, hand-editing forbidden).
- **F1 — visit-prep 就诊准备 companion** ([skills/cancer-buddy-visit-prep/](skills/cancer-buddy-visit-prep/) — SKILL.md + references/visit-prep-html-prompt.md + question-frameworks.md + templates/visit-prep.template.html). A new patient-facing companion that assembles the organize archive into a one-page `就诊准备包.html` (locale-aware, reusing the 段D CSS aesthetic + a locale string table) with four blocks: **医生速览** (field-mapped from the structured JSONs, clinical entities verbatim), **我要问医生的** (the core block — **subagent-derived, not a hardcoded keyword list** — turning `review_flags` → 请医生确认, `missing_items` → 能否补做, `timeline` 进展 → 下一步, layered with a `visit_type` 初诊/复诊/换线决策 scaffold from `question-frameworks.md`), **带什么** (records to bring), and **上次→这次的变化** (follow-up only, diffed from timeline/labs). Hard guardrails: `review_flags` render as 待医生确认项 in a contrast box, **never adjudicated into facts**; **no treatment recommendation / no result interpretation / no clinical judgment / no ranking** — visit-prep only assembles existing data + organizes questions; `null` → 资料缺失/待补充; read-only over the desensitized archive (never the `10_原始文件/` originals, no formal-field writes). Locale follows `profile.json.locale`; routed from the meta cancer-buddy skill ("明天看医生 / 复诊准备 / 该问医生什么"), with organize as a prerequisite. Rationale: the gap review's only top-patient-value + clean-lane feature — turns the archive into something a doctor reads in 30 seconds and gives the patient the right questions, without crossing into clinical advice.

### Added — organize v2 contract (病历整理 PRD v2.0 alignment)

- **Anchor token contract `[[src:...]]`** ([references/schemas/anchor-contract.md](references/schemas/anchor-contract.md)).
  Every factual sentence in `case_text.md` / `timeline.md` and every fact in the structured JSONs now carries a normalized anchor pointing back to its OCR sidecar (`ocr/<file>.md#L<a>-L<b>`) or the desensitized source (`02_脱敏病历/...`). Phase 2 worker validates every anchor's target exists before writing; dangling anchors surface as `anchor_dangling: <path>` warnings.
- **6 schema-validated structured JSON outputs** (Draft 2020-12, under [references/schemas/](references/schemas/)):
  - `patient_summary.json` (`patient_summary.schema.json`)
  - `timeline.json` (`timeline.schema.json`)
  - `molecular.json` (`molecular.schema.json`)
  - `treatment_lines.json` (`treatment_lines.schema.json`)
  - `labs.json` (`labs.schema.json`)
  - `comorbidities.json` (`comorbidities.schema.json`)
  Every schema requires `source_refs[]` arrays matching the anchor contract regex. Phase 2 validates each file before writing — failures surface as `schema_validation_failed` warnings, the file is not written.
- **Cancer-checklist driven `missing_items.json`** ([references/checklists/](references/checklists/)).
  5 cancer-type YAMLs land in this release: CRC, NSCLC, BC, GC, HCC. Phase 2 maps `profile.json.primary_cancer` + `stage` to the closest checklist, diffs against extracted findings, and emits residual items by priority. Schema: `missing_items.schema.json`.
- **Business-readable alias `{patient_id}_{cancer_type}_{year}`** at the patients-root level.
  Internal `PT-<hex>` identity is preserved. Phase 2 creates a symlink `<patients_root>/<alias>/ → <patient_code>/`, or merges into `<patients_root>/alias_map.json` when symlinks aren't supported. Sticky across incremental runs.
- **`update_log.json` audit trail** per patient. Append-only log with `timestamp / run_mode / added_files / removed_files / affected_summaries / triggered_by / reason / readiness_grade / readiness_score / review_flags_*` per run.
- **Incremental mode** (`run_mode: "incremental"`). Phase 1 only re-OCRs new/changed files; Phase 2 only rewrites affected top-level artifacts. Use full mode for first organize or major regimen changes.
- **2 new review_flags checks** (total 7, up from 5):
  - `cross_patient_name_collision` (🔴 P0 per PRD §5.4): grep `demographics.name` + `dob` year across all sibling `patients_root/PT-*/profile.json` — collision = possible串号 / duplicate enrollment.
  - `anchor_coverage_gap`: factual content without a resolvable anchor.
- **File naming `<YYYY-MM-DD>_<doc_type>_<hospital>.<ext>`** with 4-level hospital fallback: report body → file metadata → `caller_default_hospital` → `unknown-org`.
- **`scripts/validate_structured_outputs.py`** — independent validator combining Draft 2020-12 schema validation + anchor regex check + anchor target-file existence. Falls back to a lightweight check when `jsonschema` is not installed.

### Changed

- `cancer-buddy-organize` SKILL.md frontmatter `description` updated to surface the new outputs and incremental mode.
- `organizer-prompt-phase2-synthesis.md` extended with §2.6 (structured JSONs) / §2.7 (`missing_items.json`) / §2.8 (alias) / Step 3a (cross-patient name check) / Step 5 (update_log) / Step 6 return JSON includes new fields.
- `profile.json` now carries an optional `alias` field.

### Migration

- Existing patient directories (`PT-<hex>/`) continue to work unchanged. The 6 new structured JSONs + `missing_items.json` + `update_log.json` are written on the next organize run for that patient.
- Anchors are emitted from this release forward. Existing `case_text.md` files do not need to be retrofitted; running organize again will rewrite them with anchors.
- To trigger the alias for an existing patient, re-run organize once. Internal `PT-<hex>` directory name is never renamed.

### Source mapping (PRD v2.0 §)

| PRD § | Implementation |
|---|---|
| §5.4 跨病例姓名一致性 (P0) | review_flags Check 6 `cross_patient_name_collision` |
| §6.B 文件命名 `日期_类型_机构` + 4 级回退 | Phase 2 §1 |
| §6.C `update_log.json` + 增量更新 | Phase 2 Step 5 + incremental mode |
| §7.2 病情总结 md 八节结构 | (deferred — see follow-up) |
| §7.3 锚点 token 契约 | references/schemas/anchor-contract.md + Phase 2 §2.3 |
| §10.3 结构化 JSON Schema | references/schemas/*.schema.json |
| §10.4 缺失资料清单 (癌种 checklist) | references/checklists/*.yaml + Phase 2 §2.7 |

### Deferred (architecture-level, out of scope for this release)

- API-first HTTP layer (PRD §1, §10.1) — strategic decision pending.
- MTB `MtbState` dataclass + `SourceDocTool` (PRD §10.1, §10.2) — depends on the API layer.
- Five fixed second-level directories (`00_索引与摘要 / 01_原始病历 / 02_脱敏病历 / 03_结构化输出 / 04_沟通与补充材料`) (PRD §6.A) — incompatible with the existing 11-bucket medical-type taxonomy that downstream sub-skills rely on; would require a separate migration plan.
- Strict desensitization layer (PRD §5.4 红线) — `02_脱敏病历/` path is reserved in the anchor contract; the actual desensitization pipeline (irreversible PII strip + path whitelist enforcement) is a separate workstream.
