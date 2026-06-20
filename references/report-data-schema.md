# report_data.json Schema — Phase 2 输出规范

> Phase 2 Synthesis Worker Step 6 生成此文件，`report_template.py` 消费此文件。
> 所有字段必须严格遵循本 schema，不允许额外嵌套 HTML/markdown 标记。
> **示例值均为占位符（`<...>` 格式），绝不使用真实患者数据。**

---

## 顶层结构

```json
{
  "patient":        { ... },      // 患者基本信息
  "diagnosis":      { ... },      // 诊断信息
  "labs":           [ ... ],      // 实验室检验列表
  "molecular":      [ ... ],      // 分子检测列表
  "imaging":        { ... },      // 影像学摘要
  "treatment":      { ... },      // 治疗史
  "pathway":        { ... },      // 治疗路径总结
  "gaps":           { ... },      // 建议补充记录
  "review_flags":   [ ... ],      // 待确认项列表
  "sources":        [ ... ],      // 信息来源索引（详细版用）
  "trend_events":   [ ... ],      // 【可选】趋势图治疗干预标注（只写手术/化疗/方案调整等干预，不写复查/检验日）
  "generated_at":   "ISO8601",    // 生成时间
  "files_analyzed": 0,            // 分析文件数
  "review_flags_red":    0,       // review_flags 各级数量
  "review_flags_yellow": 0,
  "review_flags_green":  0
}
```

---

## patient（患者信息）

```json
"patient": {
  "name":         "<患者姓名>",                  // 姓名；未知 → "未取得"
  "age":          "<NN岁>",                      // 年龄；未知 → "未取得"
  "sex":          "<男|女>",                     // 性别；未知 → "未取得"
  "ecog":         "<0–4 或 待医生评估>",         // ECOG评分；有值则填数字+来源注释
  "hospital":     "<就诊医院全称>",              // 就诊医院
  "diagnosis":    "<临床诊断>",                  // 临床诊断
  "report_date":  "YYYY-MM-DD",                  // 报告/采样日期
  "patient_id":   "<病员号>",                    // 病员号
  "patient_code": "PT-<8位十六进制>",            // Cancer Buddy 内部编号
  "admission_no": "<住院号>",                    // 住院号；有歧义加括号说明
  "doctor":       "<申请/主管医生姓名>"          // 申请/主管医生
}
```

所有字段必填。找不到的值填 `"未取得"` 或 `"待医生评估"`，**不填 `null`**。

---

## diagnosis（诊断信息）

```json
"diagnosis": {
  "date":                  "YYYY-MM",               // 确诊时间
  "primary_site":          "<原发部位，如：右肺上叶>",
  "histology":             "<组织学类型，如：腺癌|鳞癌|小细胞癌>",
  "differentiation":       "<G1|G2|G3 或 未取得（来源：...）>",
  "stage":                 "<分期系统名称 + 具体分期，如：AJCC 8版 pT2N1M0>",
  "initial_or_recurrence": "<初诊|复发|待确认>",
  "metastasis":            "<部位列表 或 无远处转移 或 未取得（影像报告）>",
  "current_status":        "<一线/二线/N线 方案名 第X周期 或 待确认>"
}
```

**缺失值写法**（严格按 case-summary-template §三 规则）：

| 缺失类型 | 写法 |
|---------|------|
| 已送检待回报 | `"Pending（已送检，待回报）"` |
| 应做未做 | `"未检测，建议完善"` |
| 客观未取得 | `"未取得（原就诊医院：<医院名>）"` |
| OCR提取失败 | `"见原始报告 <文件名>"` |

---

## labs（实验室检验列表）

每个元素代表**一行**检验结果：

```json
"labs": [
  {
    "date":      "YYYY-MM-DD",
    "category":  "<类别>",            // 血常规|肿瘤标志物|凝血|感染筛查|血型|甲状腺|心功能|血糖|性激素
    "item":      "<检验项目全称，可含时间语境，如：癌胚抗原（CEA）—— 化疗前>",
    "base_item": "<标准化指标名，不含时间/阶段后缀，如：癌胚抗原（CEA）>",
    "value":     "<数值> <单位>",     // 数值+单位连写，如 "3.5 g/dL"
    "reference": "<参考区间>",        // 从报告原文提取，如 "3.5–5.0 g/dL"
    "flag":      "<high|low|normal|pending>",
    "note":      "<一句话临床意义>"
  }
]
```

**flag 规则**：
- `"high"` → 高于参考上限 → 红色加粗 + +
- `"low"` → 低于参考下限 → 红色加粗 + -
- `"normal"` → 正常范围内
- `"pending"` → 结果未回（灰色）

**base_item 规则**（用于趋势图自动分组）：
- 同一患者对同一检验项目的**所有次**记录，`base_item` 值必须完全一致
- 只写指标名称本身，不含"基线/化疗前/化疗后/复查/术后"等时间修饰词
- 例：`item` = `"癌胚抗原（CEA）—— 化疗前"` → `base_item` = `"癌胚抗原（CEA）"`
- 若指标仅出现一次，`base_item` 可与 `item` 相同或省略

**只列有临床意义的项目**：异常值全部列出；正常值只列影响治疗决策的关键项（如凝血全套正常可合并一行）。

---

## molecular（分子检测列表）

```json
"molecular": [
  {
    "item":     "<检测项目名称，如：EGFR L858R>",
    "status":   "<阳性（VAF XX%）|阴性|未检测，建议完善|Pending（已送检，待回报）|未取得（原就诊医院：...）>",
    "priority": "<high|medium|low>",
    "note":     "<一句话说明该指标的治疗决策相关性>"
  }
]
```

**priority 规则**：
- `"high"` → 直接影响一线治疗方案选择（红色行）
- `"medium"` → 影响预后评估或辅助决策（橙色行）
- `"low"` → 研究性价值或参考意义（绿色标注）

---

## imaging（影像学摘要）

无影像报告时（使用 note 字段）：
```json
"imaging": {
  "note": "本批资料无影像学报告，建议补充相应影像检查（见建议补充记录）。"
}
```

有影像数据时（使用 items 字段，note 设为 null）：
```json
"imaging": {
  "note": null,
  "items": [
    {
      "date_type": "YYYY-MM-DD <影像类型>（<医院>）",
      "summary": "<原发灶大小>；<淋巴结>；<转移情况>；<趋势对比>；<整体评估>"
    }
  ]
}
```

`note` 非空时，`items` 可省略。

---

## treatment（治疗史）

无治疗记录时：
```json
"treatment": {
  "current": "未取得（治疗记录，本批未提供）",
  "lines": [],
  "note": "本批资料无治疗记录，建议补充出院小结或化疗医嘱单。"
}
```

有治疗记录时（note 设为 null）：
```json
"treatment": {
  "current": "<当前治疗状态，如：一线含铂化疗第2周期>",
  "note": null,
  "lines": [
    {
      "line": "<一|二|三+>",
      "period": "YYYY-MM → YYYY-MM（或 至今）",
      "regimen": "<方案名+剂量，如：奥希替尼 80mg QD>",
      "efficacy": "<CR|PR|SD|PD 或 疗效描述>",
      "stop_reason": "<进展|毒性|手术|患者意愿|其他>",
      "toxicity": "<Grade N <毒性名> 或 无明显毒副反应>"
    }
  ]
}
```

`note` 非空时，`current` 和 `lines` 可以省略。

---

## pathway（治疗路径总结）

```json
"pathway": {
  "pending_issues": [
    "<等待哪项检查结果或数据空白>",
    "<等待哪项检查结果或数据空白>"
  ],
  "next_steps": "<信息整理性描述，非临床推荐。须注明：须由主诊医生评估。>"
}
```

---

## gaps（建议补充记录）

```json
"gaps": {
  "critical": [
    {
      "item":            "<关键缺失记录名称（对应 tier1_gaps）>",
      "reason":          "<缺失后对分析的具体影响，不超过30字>",
      "action_category": "现医院补检 | 调阅历史档案 | 转诊专项检查 | 组织已不可及",
      "action_detail":   "<具体操作建议，如：可向现就诊医院申请补开血常规+肝肾功能>"
    }
  ],
  "recommended": [
    {
      "item":            "<建议补充的检测或文件（对应 tier2_gaps）>",
      "reason":          "<补充后可带来的精准度提升，不超过30字>",
      "action_category": "现医院补检 | 调阅历史档案 | 转诊专项检查 | 组织已不可及",
      "action_detail":   "<具体操作建议，如：KRAS/MSI可在华西医院病理科申请补做>"
    }
  ],
  "covered": [
    {
      "item":   "<已充分覆盖的检测或文件（对应 tier2_covered）>",
      "reason": "<已覆盖的依据说明，不超过30字>"
    }
  ]
}
```

- `critical` → 【紧急】对后续分析至关重要（对应 `tier1_gaps`）
- `recommended` → 【建议】有助于提升精准度（对应 `tier2_gaps`）
- `covered` → 【已覆盖】已充分覆盖（对应 `tier2_covered`）

`critical` 和 `recommended` 的每个元素必须有 `item`、`reason`、`action_category`、`action_detail` 四个字段。`action_category` 四选一，`action_detail` 写具体操作步骤（不超过40字），使患者/照护者知道下一步该联系谁、去哪里。

---

## review_flags（待确认项列表）

```json
"review_flags": [
  {
    "id":               "RF-001",           // 格式固定：RF-NNN，从001递增
    "severity":         "<red|yellow>",     // red=影响决策须确认；yellow=建议核对
    "issue":            "<具体描述发现了什么问题>",
    "suggested_action": "<建议用户采取的具体行动>",
    "user_confirmed":   false               // 用户确认后设为 true（默认 false）
  }
]
```

**severity 规则**：
- `"red"` → 影响治疗决策，必须在使用本报告前确认
- `"yellow"` → 建议核对，不影响报告生成
- green 级别不写入此列表（仅计入 `review_flags_green` 计数）

---

## sources（信息来源索引）

详细版（case_summary_detailed）专用，简要版可省略：

```json
"sources": [
  {
    "module": "<模块名称，如：肿瘤标志物>",
    "field":  "<数据点描述，如：AFP 基线值>",
    "file":   "YYYY-MM-DD_<类型>_<机构>.md"
  }
]
```

---

## trend_events（趋势图治疗干预标注，可选）

用于在趋势图上以**橙色竖虚线**标注关键**治疗干预节点**，帮助读者理解指标趋势变化的因果原因。

渲染规则：
- 每个干预在子图右上角单独图例中显示，标注"治疗事件"
- 仅在事件日期落在该指标 X 轴范围内时才显示（不在范围内的事件自动忽略）
- 无事件时不显示图例，子图保持整洁

```json
"trend_events": [
  {
    "date":  "YYYY-MM-DD",     // 干预执行日期（必须是确切日期）
    "label": "<干预名称≤8字>"  // 如：造瘘术、FOLFOX第1周期、三药方案、贝伐加用
  }
]
```

**允许写入 ✅（治疗干预）：** 手术、化疗周期开始、方案调整（换方案/加药/减药）、靶向药/免疫药启动、MTB决策执行、放疗开始/结束、停药事件

**禁止写入 ❌（诊断/随访事件）：** CT复查、PET/CT、血液检验日期、门诊就诊、住院非手术日、影像评估日

**示例：**
```json
"trend_events": [
  { "date": "2025-08-15", "label": "乙状结肠造瘘术" },
  { "date": "2025-09-18", "label": "FOLFOX第1周期" },
  { "date": "2025-11-20", "label": "三药方案" }
]
```

无法确定任何干预的具体日期时，写 `"trend_events": []`，**不用复查/检验日期凑数**。

---

## 完整示例结构验证

Phase 2 在写入 `report_data.json` 之前，必须验证：

1. `patient` 中 name/age/sex/ecog/hospital/diagnosis/report_date/patient_id/patient_code 全部存在（允许值为 "未取得"，不允许 `null`）
2. `labs` 中每个元素含 `date`, `category`, `item`, `value`, `reference`, `flag`, `note` 七个字段
3. `molecular` 中每个元素含 `item`, `status`, `priority`, `note` 四个字段
4. `gaps.critical/recommended/covered` 中每个元素含 `item`, `reason`
5. `review_flags` 中每个元素含 `id`, `severity`, `issue`
6. `generated_at` 格式为 `YYYY-MM-D