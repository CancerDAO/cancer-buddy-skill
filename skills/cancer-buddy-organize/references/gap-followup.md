# 既有文档补充询问

`missing_items.json` 的兼容文件名不代表患者“缺检查”。它只描述当前档案中未找到的既有
文档，结构见 `schemas/missing_items.schema.json`。

## 可问

> 为了把这份资料整理完整，我在当前上传内容中没有找到 `<document category>`。如果医院已经出具过这类报告，你愿意把现有文件加入档案吗？没有或不确定都可以，不代表需要补做检查。

## 不可问

- “这是 P0，必须补齐”；
- “补做后才能判断有没有靶向药”；
- “指南要求你做”；
- “缺这项就不能继续帮助”；
- 任何检查、影像、分子检测、随访或治疗建议。

## 状态

- `not_in_archive`: 当前档案未找到；
- `unknown`: 不知道是否存在；
- `requested_by_clinician`: 正式医嘱/转诊材料明确要求，需附来源；
- `patient_declined_to_add`: 患者不希望加入档案；
- `missing_pages`: 同一份文书的页码不连续（如“第1页，共3页”“第2页，共3页”在档，第3页不在）。
  由 `scripts/page_completeness.py` 按“日期 + 桶内文书类型目录 + 文件名中的机构段 + 印刷总页数”分组机械判定
  （phase2 §5.8），记录 `pages_present`、`pages_missing`、`page_total`。

仅 `requested_by_clinician` 可显示临床人员已要求，且必须逐字引用。其他状态只影响资料
整理，不影响临床建议和一般教育。

`missing_items.json` 条目上的 `severity`（缺页为 `red`）只描述档案完整性，**不改变上面的询问话术**：
缺页仍用“可问”模板，`<document category>` 填成“某日期某文书的第 N 页”；“不可问”清单同样适用，
不说“必须补齐”，不暗示缺的那一页里有什么结论。

## 只问一次（`gap_asks.json`）

每一次真正递出的具体邀请都记进 `gap_asks.json`（`schemas/gap_asks.schema.json`），它是“问过没有”的账本，不是
临床优先级，也不代表需要做检查。唯一写入者是 `scripts/record_gap_ask.py`（编排者白名单里的固定动作，SKILL.md 不变量 3）：

- 问之前：`record_gap_ask.py <patient_dir> check --item-key <K>`，返回 `allowed` 才问；
- 问了之后：`record_gap_ask.py <patient_dir> ask --item-key <K> --category "<document category>" --trigger step_11_4`；
- 用户补来了或说不要：`record_gap_ask.py <patient_dir> status --item-key <K> --status provided|declined`。

`<K>` 取 `missing_items.json` 该条缺口的 `group_key`（缺页），没有就取它的 `document_category`。脚本钉死的规则：同一项
一天只问一次；`declined` 永不再问（用户自己提起除外）；`provided` 即结束；`pending` 至少隔 30 天才可再问一次，总共
最多两次。整理结束时没有递出具体邀请就不写这个文件。
