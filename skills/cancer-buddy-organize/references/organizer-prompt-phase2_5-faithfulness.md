# Phase 2.5：忠实度验证

验证目标是“结构化值是否能在来源中复现”，不是判断医学上是否合理。你只报告，不改任何文件（Call parameters 的 `skill_dir` 是本 skill 目录的绝对路径，文中提到的 `scripts/…`、`references/…` 都在它下面）；
flag 与摘要中的处理由编排者派 Phase 2 worker（`run_mode: faithfulness_patch`）和段D worker 完成。

## 独立性

“独立”与 phase1 提示词 §2 的定义相同：两次读取的**通道类别不同**，且**都不是 `llm_vision`**。
大模型再读一遍 sidecar 或再看一遍原图都不是独立证据；它只能发现问题，不能为另一次大模型转录背书。
能回到原件的确定性通道（原生文本层、表格解析、OCR 原始输出 `raw/_extract/…`、人工）时优先使用；
只能读 sidecar 时，在结果里写明 `method: sidecar_reread`，该结果不得作为独立复读依据。

## 方法

1. 确定性检查：hash、锚点、schema、数字/单位、日期、重复和跨患者标识。
2. 对药名、剂量、日期、实验室值/单位/参考范围、分期、变异/VAF、免疫组化标志物、淋巴结站别和
   疗效原文执行第二次读取：先按 sidecar 头部与 `source_inventory.json` 找到原件与引擎原始输出，
   尽可能使用与 sidecar 主通道**不同类别**的通道核对。
3. 按被引用的 sidecar 分批：每个 sidecar 只打开一次，核对引用它的全部值；读被引用行的前后若干行，
   单行窗口看不出串行错位。
4. 只接受可定位的 source span；找不到精确位置则 `not_faithful`。
5. 肿瘤标志物不因可能影响治疗而自动成为“load-bearing”；其临床意义不在本阶段判断。
6. 检验值按 `pairing_method` 区分：`linear_position` 得到的 `candidate_value` 不是确认值，本阶段只核对
   它与 `## 列配对` 记录一致，不把它升格为 `value`；拒绝配对的项目核对“确实计数不等”。
7. 疗效原文（CR/PR/SD/PD、“部分缓解”等）只核对是否逐字来自医生来源，不从影像描述推导。

## 结果与分级映射

| 结果 | 含义 | 对应 flag 的 `kind` / `severity` |
|---|---|---|
| `faithful` | 值、单位、限定词和上下文可复现 | 不写 flag |
| `not_faithful` | 不一致或无法定位，患者摘要置 null | `other` / 高风险字段 `red`，其余 `yellow`（`category: source_faithfulness`） |
| `needs_human_review` | 图像质量、手写、表格错位或方法冲突 | 字迹问题 `legibility`、版面或表格错位 `artifact`；高风险字段 `red`，其余 `yellow` |
| `disputed` | 两个有效来源不同，保留两者 | `conflict` / 按 Phase 2 §6.1 |

`severity` 是抽取不确定程度，不是临床严重度。sidecar `## 不确定字段` 里的词表候选是**读数记录**，
不是正确值：不得用候选判定 `faithful`，也不得把候选写进任何结构化字段。

## 返回 JSON

最后一条消息只输出 JSON，每个被核对的值一条：

```text
{
  "role": "phase2_5_worker", "worker_id": "p25-1", "values_checked": 47, "sidecars_read": 9,
  "counts": {"faithful": 41, "not_faithful": 2, "needs_human_review": 3, "disputed": 1},
  "results": [
    {"file": "labs.json", "json_path": "$.panels[3].values[2].value", "value": 4.68,
     "verdict": "not_faithful", "severity": "red", "kind": "other", "method": "raw_output_recheck",
     "evidence": "<bucket 相对路径>#L11-L12：逐字引用被核对的行及相邻行",
     "issue": "JSON 中的数值与该项目所在行不一致，疑似取自相邻行"}
  ]
}
```

`evidence` 必须逐字引用所依据的行；没有可引用的行时结论只能是 `needs_human_review`。`issue` 只描述
不一致之处，不写“正确值应为 X”。

本阶段不得提出“正确值”，不得让患者一键接受模型建议来清除 flag。
