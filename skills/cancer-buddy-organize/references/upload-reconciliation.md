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

## 临床字段更新

`formal_amendment` 可由确定性规则链接，但仍保留原值和更正链。`conflict` 必须保持 `disputed`；只有出具机构的正式更正或授权临床人员签认才可指定当前值。患者选择“以新图为准”只记录偏好，不迁移锚点、不删除旧值。

**时变字段先走 time-varying 例外，再判 `conflict`。** 新上传文档与既有文档在年龄、体重、身高、ECOG、`current_status.*`、labs 上取值不同，且两份文档的报告日期不同、差异与时间跨度自洽（判据见 `organizer-prompt-phase2-synthesis.md` §2.1）→ 关系是 `unrelated`（各自独立时点观测）或 `later_version`，**不是 `conflict`，不进 diff card 的冲突分支，不标 `disputed`**。只有同一报告日期内取值不同、或差异与时间跨度矛盾（年龄倒退等）才升级为 `conflict`。时不变字段（性别、诊断、出生年、既往治疗线历史）不适用本例外。

## 同检验判重（先于 conflict 判定）

同一张检验报告的两个载体（纸质拍照 / App 截图 / PDF）不构成"档案事实矛盾"。关系判定时**先做同检验判重**：新文件与对照文件的检验编号一致（脱敏形态下取可见尾数重叠，最小 ≥3 位；脱敏形态不统一，绝不假设固定位数）、且采样时间戳与报告时间戳双双一致 → 关系是 `duplicate`（同检验双载体），**不进 conflict 分支、不出冲突卡**。此时若两侧读出的值不一致，那是读取环节的问题（internal_read_discrepancy）——触发独立复读，不抛给用户裁决。同批多管标本采样时间秒级连号、编号相邻，任何单键匹配都会误判：必须编号+双时间戳同时成立。宿主必须在出卡前执行 `scripts/gates/gate_same_test.py`（见 organize-contract.md §Executable gates）。

## 值-源绑定（出卡前提）

冲突/替换卡上出示给患者的每个数值都必须先证明来源绑定：`old_value` 能在对照文件 sidecar 逐字定位**且不带 needs_human_review 复核标记**（未经独立复读的档案值不得充当"档案现有事实"）；`new_value` 能在新文件的**独立第二次读取**产物中逐字定位（第二读必须与关系判定调用隔离：原生文本 / 本地 OCR / 隔离转录调用）。任一失败 → 该候选降级为「数值待核对」，UI 附上原图证据，禁止渲染成确定语气的二选一。宿主必须在出卡前执行 `scripts/gates/gate_candidate_binding.py`。

## Round-1 执行规范（headless confirm-as-product 第一轮）

对账分两轮：round-1 只做关系判定与候选产出，round-2 才在用户确认后执行处置。round-1 硬规则：

1. 对每个新文件做关系判定（LLM 语义判定，非关键词）：`new` / `supersede` / `conflict`。判定前先过同检验判重（本文件上节）与相关性闸（高置信非医疗交段E，不进对账）。
2. **new**：正常并入既有桶（canonical 改名 + co-locate 脱敏 MD + 更新 INDEX/timeline/case_text/结构化 JSON）。
3. **supersede / conflict**：**绝不**写正式字段、不删、不替换——只作为候选数据输出，交宿主 UI 事后问用户 替换/并存/忽略。
4. demographics.age 与现有值不同时先走时变字段例外（见上文）；仍属 conflict 的必须上确认卡，不能静默覆盖。DOB 为 [PII_MASKED] 时绝不推算年龄。
5. update_log.json 追加 `run_mode:"upload_reconciliation"`（本轮 resolutions 里 supersede/conflict 标 pending）。alias 黏住不改。
6. 输出候选 JSON schema（单个 ```json 块，无其它散文）：

```json
{"candidates":[{"source_id":"<稳定 source_id，必填>","upload":"<新文件原名>","relation":"supersede|conflict","target_doc":"<被对照的桶内相对路径>","evidence":"<可核对依据>","confidence":"high|low","new_field":"<涉及的结构化字段名,可空>","new_value":"<新值,可空>","old_value":"<档案现值,可空>"}],"new_organized":<int>}
```

候选产出后、写盘/出卡前，宿主依次执行 G3（同检验判重）与 G2（值-源绑定）两道确定性门；门写入的 `relation_override` / `binding` 字段是门的产物，模型不自填。

## 删除

无论模型置信度高低，沉默都不删除。明确非医疗文件先隔离并提供预览，只有用户逐项明确确认后才删除，并写不可逆审计记录。
