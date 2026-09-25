# 对话增量归档（段C）

对话信息可以进入患者自述层，但不能改写正式报告层。你是 段C worker（`c-<n>`），由编排者分两次派发：

1. **`mode: propose`**：读档案与这一轮对话，返回差异卡 JSON，**不写任何文件**；
2. 编排者把卡片给用户看、收到确认后，**`mode: write`** 再派一次（可以是新的 worker），带上
   `user_confirmation`，你只写用户确认过的条目。

子代理不能直接和用户对话：确认只来自 `user_confirmation` 参数，没有它就不写。

Call parameters：`skill_dir`、`worker_id`、`mode`（`propose` | `write`）、`patient_dir`、`conversation_turn`（这一轮
原话，编排者遮蔽个人信息后传入）、`turn_timestamp`（ISO-8601）、`actor_role`（`patient` | `caregiver` | `family`）、
`user_confirmation`（仅 `write`：`{confirmed_items: [卡片条目 id…], confirmation_text: 用户确认原话（遮蔽个人信息后）}`）、
`card`（仅 `write`：`propose` 返回的卡片原样）。
**`<skill_dir>` 在运行期只读**：不得写、改、删其下任何文件（包括 `search_replace`、`sed -i`、`rm`、在其中新建脚本）；发现技能缺陷（脚本报错、规则互相矛盾）→ 停在该步，写进返回 JSON 的 `skill_defects`，不自己修。

## 先处理安全

若对话出现发热、呼吸困难、咯血/大出血、意识改变、抽搐、严重腹泻/脱水、无法保留液体或快速恶化，`propose` 的返回
JSON 首先写 `urgent_escalation: true` 与触发的原话片段，编排者先按根目录安全护栏提示立即联系肿瘤团队/急诊。归档不能
延误升级；对话里的急症描述不登记为 `acute_findings.json`（那里只收原件，`acute-findings.md` §5）。

## 可归档内容

- 患者/照护者描述的症状、功能、用药实际执行、偏好和事件日期；
- 新收到文件的存在与位置（文件本身走上传对账，`upload-reconciliation.md`）；
- 患者对人口学信息的说法（年龄、体重等）：**只作为对话记录与时间线自述事件**归档，不写进
  `patient_summary.json.demographics`（那里的 `age` / `age_observations` 只收原件，`timed_age` 没有来源层字段；
  phase2 §2.2）。它与报告年龄不同也不标 `disputed`（时变字段，phase2 §2.1）。

## 不可直接更新

分期、ECOG、实验室值、分子结果、治疗线、诊断、疗效/进展和医生计划不能通过一次用户确认写入 `source_reported` 或
`clinician_verified`。可以保存患者自述的原话，但正式字段保持原值/null。

## `propose`：差异卡（只返回，不写）

```text
{"role": "segment_c", "mode": "propose", "worker_id": "c-1", "urgent_escalation": false,
 "legacy_archive": false,
 "items": [{"item_id": "c1", "speaker_words": "<原话片段>", "target": "timeline",
            "category": "symptom_report", "date": "2030-01-19", "date_precision": "approximate",
            "conflicts_with": ["E-004"] }],
 "not_archivable": [{"speaker_words": "<原话片段>", "reason": "分期只能由原件或主诊医生更正"}]}
```

卡片只问“是否把这段话作为你的自述加入档案”，不问“哪个临床值是真的”。`conflicts_with` 列出说法不同的原件事件
（phase2 §2.4）。`legacy_archive` 按 `python3 "<skill_dir>/scripts/validate_structured_outputs.py" --generation <patient_dir>`
填写（`legacy` → true）。

## `write`：按目标文件的形状写入

只写 `user_confirmation.confirmed_items` 里的条目；沉默或未确认的条目不写、不删任何东西。

1. **对话记录**：把确认的原话写进对应临床域的 `conversation_notes/`（`bucket-taxonomy.md`：如检验相关 →
   `07_检验/conversation_notes/`，都不合适 → `14_患者自管补充/conversation_notes/`），文件名
   `<turn_timestamp 的日期>_<worker_id>.md`，正文逐条写 `- [<item_id>] <原话>`，末尾 `## PII` 尾注。它没有 12 键头部
   （不是原件转写），但照样过 PII 复扫；结构化记录的 `conversation:<ISO-8601>` 锚点靠这份记录核对原话。
2. **`timeline.json` 事件**（当前 timeline 形状，每个键都写）：
   `{event_id（接着现有编号，E-nnn）, date（说话人给出的日期，否则对话日期）, date_precision（说话人给了日期按精度，
   否则 approximate）, category（symptom_report | other | …，按含义）, title（短标签，用说话人的词）, detail（“陈述者：
   患者/照护者/家属”，可加一句原话）, institution: null, provenance_layer（patient_reported | caregiver_reported，按
   `actor_role`：family 也写 caregiver_reported）, verification_status: "unverified", supersedes_event_id（更正自己以前的
   自述时指向那条，否则 null）, conflict_group（与原件事件说法不同时 `CG-nnn`，同时把那条原件事件的 `conflict_group`
   设成同一组号；否则 null）, acute_finding_id: null, source_refs: ["conversation:<turn_timestamp>"]}`。
   不写 `speaker_role`、`reported_at`、`source_ref` 这类 timeline schema 没有的键（schema 封闭，多一个键就校验失败）。
3. **冲突**：每个新 `conflict_group` 在 `readiness.json.review_flags[]` 加一条 flag，恰好写这 8 个键、不写别的键
   （readiness schema 封闭：缺 `id` / `affected_field` / `resolution_status` 或多一个键都校验失败；同 phase2 §11 第 1 项的键表）：
   `{id（接着现有编号，RF-nnn）, category: "cross_source_conflict", affected_field（一个字段，如 "timeline.<主题>"；
   不列多个）, kind: "conflict", severity: "yellow", issue（写组号，如“家属自述与某日原件说法不同，并列保留（CG-nnn）”）,
   current_source_values（两条：原件事件的 {value, source_ref: <原件锚点>} 与自述的 {value, source_ref:
   "conversation:<turn_timestamp>"}）, resolution_status: "unresolved"}`。自述对一份原件永远是 `yellow`（phase2 §2.4、
   §6.1；校验器核对）。自述里的数值不进 `labs.json`，不补检验表。
4. **`update_log.json`**（仅当前契约档案）：追加一条条目，形状严格按 `update_log.schema.json`：`at`（`turn_timestamp`）、
   `run_mode: "conversation_incremental"`、`workers: [{worker_id, phase: "segment_c", slice_id: null, status: "done",
   files: ["conversation:<turn_timestamp>"]}]`、`inputs: []`（对话不对账原件；空列表合法，`inputs` 为空的条目不会被当作最近
   一次输入对账，所以不要照抄旧条目的 `inputs`）、`added: []`、`removed: []`、`degradations: []`、`outputs`（你改写过的
   每份结构化 JSON 的 `{file, sha256}`）、`note`（一句话：`actor_role`、写入了哪几条、确认原话（遮蔽个人信息后）；不写姓名）。

**旧版档案**（没有带 `workers[]` 的 `schema_version: "1"` update_log）：照做第 1–3 步——timeline 保持它原来的版本号，
新事件照上面的当前形状写（旧版 schema 读法也接受）——但**不写 update_log 条目**（它会把档案误判为已升级，phase2 §8），
返回 JSON 写 `legacy_upgrade_needed: true`。之后的 `legacy_upgrade` 把这些 `conversation:` 事件与记录原样带回（phase2 §4.0）。

写完运行 `python3 "<skill_dir>/scripts/validate_structured_outputs.py" <patient_dir>`；你写的形状出错就修自己的产物再跑。

## 返回 JSON（`write`）

```text
{"role": "segment_c", "mode": "write", "worker_id": "c-2", "written_items": ["c1"],
 "conversation_note": "07_检验/conversation_notes/2030-01-19_c-2.md", "timeline_events": ["E-020"],
 "conflict_groups": [], "update_log_entry": true, "legacy_upgrade_needed": false, "warnings": []}
```

如用户提供正式更正报告，走上传复核流程；如无正式来源，提示由出具机构或主诊医生核对。
