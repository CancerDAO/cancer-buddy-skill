# 上传资料版本与冲突处理

## 原则

- 原始文件和来源锚点不可覆盖、重映射或删除。
- 内容哈希相同的重复上传可建立同一内容引用，但保留上传事件。
- 新版本、正式更正和冲突文件并列保存，并通过关系链接。
- 用户可说明“我认为新文件是更正”，但不能据此让系统把临床事实自动晋升为 canonical。

## 关系

- `duplicate`: 内容相同；
- `later_version`: 同一机构/报告的后续版本，是否正式更正需文件自身证明；
- `formal_amendment`: 文件明确标注更正/补充并能关联原 accession；
- `conflict`: 临床字段不同且无法由正式更正关系解决；
- `unrelated`: 不同检查/事件。

新上传与既有档案的比对以 `scripts/inventory_hash.py` 算出的 sha256 为准：与 `update_log.json`
（`schema_version: "1"`）最后一个 `inputs[]` 非空的条目（段C 对话条目的 `inputs` 为空，不算）中某个
sha256 相同，或与 `source_inventory.json.skipped_inputs[]` 中的 sha256 相同，即 `duplicate`，不重新转写；
其余才进入上面的关系判断。档案还没有 `schema_version: "1"` 的 update_log 时，它是本轮契约之前的旧档案，先按
`SKILL.md`「Incremental and update runs」做一次旧档案升级，再对账。

用户在差异卡上的逐项选择（替换 / 并存 / 忽略）由编排者作为 `user_decisions`（`replace` / `coexist` / `ignore`）交给
执行对账的 Phase 2 worker（`run_mode: upload_reconciliation`，phase2 §12）。**替换不移动旧文书**：旧 sidecar 留在原桶、
锚点不变，清单行写 `superseded_by: <新文件 file_id>`，新事件写 `supersedes_event_id`，摘要类字段改取新文件；worker 随后
对新来源做增量综合（清单、各领域、急性发现、缺页、资料时效），并在本次 `update_log.json` 条目的 `note` 中逐项记录选择、
句柄与确认原话（遮蔽个人信息后）。编排者不移动文件，也不写 update_log。

**旧档案摘录不是上传。** `source_kind: prior_archive_digest` 的 sidecar（`03_病程与叙事文书/既往档案摘录/`）
来自用户授权引用的既往整理档案，没有 `raw/` 原件，不参与 `duplicate` / `later_version` /
`formal_amendment` / `conflict` 判定，也不能被新上传“替换”。本次原件与摘录说法不同时，两者并列保留
（摘录一侧为 `provenance_layer: prior_archive`），不走本文件的替换流程。

## 临床字段更新

`formal_amendment` 可由确定性规则链接，但仍保留原值和更正链。`conflict` 必须保持 `disputed`；只有出具机构的正式更正或授权临床人员签认才可指定当前值。患者选择“以新图为准”只记录偏好，不迁移锚点、不删除旧值。

**时变字段先走 time-varying 例外，再判 `conflict`。** 新上传文档与既有文档在年龄、体重、身高、ECOG、`current_status.*`、labs 上取值不同，且两份文档的报告日期不同、差异与时间跨度自洽（判据见 `organizer-prompt-phase2-synthesis.md` §2.1）→ 关系是 `unrelated`（各自独立时点观测）或 `later_version`，**不是 `conflict`，不进 diff card 的冲突分支，不标 `disputed`**。只有同一报告日期内取值不同、或差异与时间跨度矛盾（年龄倒退等）才升级为 `conflict`。时不变字段（性别、诊断、出生年、既往治疗线历史）不适用本例外。

## 删除

无论模型置信度高低，沉默都不删除。明确非医疗文件先隔离并提供预览，只有用户逐项明确确认后才删除，并写不可逆审计记录。
