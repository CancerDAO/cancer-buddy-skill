# 急性与附带发现登记（acute_findings.json）

本文件是 Phase 2 登记急性/附带发现的唯一规则来源。登记的是**来源原文写了什么**，不是临床分诊：
organize 不判断病情轻重、不决定是否处理、不替代主诊团队。`acuity` 只能由本文件 §3 的固定表加
§4 列出的三种来源用词调整得出，模型不另行分级。

## 1. 为什么必须登记

影像、检验或病历里的血栓、骨折、积液增多、疑似药物性肺炎等发现，过去只留在 sidecar 正文或
HTML 里，结构化 JSON 与 timeline 都没有，下游读不到就当作不存在。登记的目的只有一个：让这些
原文句子**以结构化形式可被下游看见**，并由下游交给治疗团队判断。

## 2. 哪些句子要登记（语义判断，Phase 2 逐份报告读）

凡影像、检验、病理或病历原文中含下列语义的句子，都要登记，不论它是否与肿瘤直接相关（括号内是
登记的类别；§2.1 列出不登记的写法）：

- 血栓、栓塞、充盈缺损、瘤栓待排（`thrombus_embolism`）；
- 骨：骨折、骨质中断、骨皮质中断、骨皮质不连续（`fracture_cortical_break`；原文写“陈旧性”骨折同样登记为
  这一类，按 §4 下调）；只写“骨皮质扭曲”“骨质形态不规则”“椎体变扁/塌陷”等、没写骨折或中断的**结构**改变 →
  `other_source_flagged`（incidental）；成骨性/溶骨性/硬化灶、骨转移灶、“与前相仿”之类的**病灶描述**不登记；
- 穿孔、游离气体（`perforation_free_air`）；
- 梗阻：肠、胆道、尿路、气道原文写“梗阻”“闭塞”“完全阻塞”（`obstruction`）；“阻塞性炎症”“阻塞性肺不张”
  等**继发改变** → `other_source_flagged`（incidental），原文写它“新发”或“较前加重”时按 §4
  `source_wording_escalation` 上调为 urgent；食管、支气管的“狭窄”“管腔变窄”不单独登记，除非原文写了梗阻；
  与积液同写的“压缩性肺不张”留在那条积液的 `verbatim_text` 里，不另登记；单独写的非阻塞性肺不张不登记；
  血管的“狭窄”“包绕”“受侵”不登记（写了血栓/栓塞按上面第一类，写了“闭塞”→ `other_source_flagged`）；
- 出血：影像或病历写明的活动性出血、新发血肿、消化道出血症状（呕血、黑便、便血）（`hemorrhage`）；
- 积液（心包、胸腔、腹腔）：原文写“大量”或“较前增多/增加”→ `effusion_large_or_increasing`；其余积液
  （没写量也没与既往比较、少量且稳定、较前减少）→ `other_source_flagged`（incidental）——保证下游看得见，
  但不升级；
- 肺部炎症：原文写间质性改变、间质性肺炎/肺病、药物相关/免疫相关/放射性肺炎，或写“双肺/双侧/多发”
  的炎症（肺炎）且没写感染病原 → `pneumonitis_ild_suspected`（按原文用词分类，不判断病因）；“小叶间隔增厚”
  “淋巴管播散”之类肿瘤性描述不是间质性改变的原文用词，不入本类、不登记；
- 报告自带的危急值、critical result、clinically significant result 标记、临床重要结果通知
  （`critical_result_flag`）；
- 影像或检验报告里**依附于某个具体异常所见**的“请结合病史/请结合临床”（所见本身已属上面某类时按那一类
  登记一次，否则 `clinical_correlation_requested`）；
- **影像、检验报告**针对某个具体所见写的“建议进一步检查/复查/随访/超声/CTA/增强扫描”等（`other_source_flagged`，
  incidental；登记单位是那个所见，`verbatim_text` 含所见与建议；写“尽快/立即/急诊”时按 §4 上调为 urgent）。
  **病理、NGS/分子报告**里的“建议加做免疫组化/分子检测/胚系检测”等后续检测说明一律不登记（§2.1）。incidental
  行只为让下游看得见，不表示需要处理；原发肿瘤本身的检查建议（如“占位性质待定，建议进一步检查”）同样按这一条登记。

判断是按含义读原文，不是关键词匹配；同义的英文、缩写与中文都算。

### 2.1 不登记的写法

- 内镜或活检操作中的“接触性出血”“触之易出血”：它描述的是组织质地，不是出血事件；
- 病理报告的签发套话，如“本报告仅对所送标本负责”“诊断请结合临床资料综合分析”——不针对某个具体所见的
  通用句；
- NGS/胚系检测的免责或条件建议，如“检出变异无法区分体细胞或胚系来源，必要时可另行胚系检测”，以及病理报告
  “建议加做免疫组化/分子检测”之类的后续检测说明：登记它等于替报告下检测指征；
- 食管、支气管“狭窄”而原文没写梗阻（见上）；
- 旧档案摘录与患者/照护者自述中的同类描述（见 §5 末段）。

### 2.2 登记单位

**登记单位是“一个病灶/部位/血管的一个发现”，不是一句话。**

- 一句话写了两个及以上不同的病灶、部位或血管，且**各有各的描述或比较用语**（如“右髂外静脉血栓较前延伸，
  右股浅静脉血栓大致同前”），每个各登记一条：各自的 `label`、各自的 `change_vs_prior`（分别映射各自的
  比较用语）、各自的 timeline 事件；`verbatim_text` 各取与本条有关的部分，其余用“……”省略（省略号两侧的
  文字必须与原文逐字一致）；`source_ref` 可以指向同一行。
- **复合部位列举**：一个所见列举几个部位、共用同一描述与同一比较用语（如“L3、L4 椎体压缩性骨折”“肝 S6、S7
  段低密度灶，建议进一步检查”）登记**一条**，不按部位拆开。
- 同一个病灶的描述同时命中多类（如“骨折”又写“请结合临床”）时，按 §3 选最具体的一类登记**一次**，
  其余用词保留在 `verbatim_text` 中，不重复登记。
- 同一份报告的“所见”与“印象/诊断”重复描述同一个发现时登记一次；`verbatim_text`、`source_ref` 与
  `change_vs_prior` 取自同一处：只有一处写了比较用语时取那一处，否则取“印象/诊断”中的那一行。
- 同一份报告被拆成几个 sidecar（如同一次检查的图像所见页与印象页各一份）仍是**一份报告**：登记一次；
  本页没印日期时，可以取同一份报告另一页 sidecar 上的日期。“同一份报告”在机械上是：同一桶目录、同一文件名
  日期、同一机构段（phase2 §4.2 按出具日期命名）；旧档案里同一次检查的几页若以不同日期命名，就不借另一页的日期，
  该日期写 null。
- **每份原报告各自登记**：同一个发现在几份原报告里各写一次（首次检查、后续复查、另一种检查），每份各登记
  一条——它们是不同时点的观察，各带自己的日期与比较用语；不跨报告合并，也不因为“已登记过”而省略。
- **连写的印象**：印象连成一句、没有编号或分隔，“请结合临床”“建议复查”该归哪一个所见读不出来时，不按位置
  猜：把它与可能归属的所见作为原文连续片段写进同一条的 `verbatim_text`，不单独登记，也不拆开。

### 2.3 病历中复述的报告结论

门诊、住院病历常把影像或病理结论照抄进现病史（后续多次就诊还会反复照抄）。

- 被复述的原报告**在档案中** → 只按原报告登记，复述句不再登记；
- 原报告**不在档案中** → 以病历为来源登记**一次**（多份病历复述同一份报告时取最早复述它的那份）：
  `source_ref` 指病历中复述的那一行，`exam_date` / `report_date` 只在复述句写明时填、否则 null；timeline
  事件日期取该病历的就诊日期，`date_precision: approximate`（它是复述的时点，不是检查日期）。

### 2.4 外文报告

外文原件的 sidecar 按原文语言保留原句（phase1 §4.1，中文说明另起一行）。`verbatim_text` 就是 sidecar 里的
**原文语言句子**，`label` 用原文词语；需要中文说明时写在 `timeline.md` 该行（标“中文说明”），不写进
`verbatim_text`。sidecar 只有中文转述、没有原句时（旧 sidecar），按转述登记，并为**这份 sidecar**写**一条**
`category: foreign_language_paraphrase`、`kind: other`、`severity: yellow` 的 flag（不是每条发现一条；
`current_source_values` 引该 sidecar），说明原文取自转述、需要按原文语言重新转写；旧版档案上它与
`legacy_upgrade` 提示并存。校验器核对每份 sidecar 至多一条、且为 other/yellow。

## 3. finding_class 与默认 acuity（固定表）

`finding_class` 枚举：`thrombus_embolism` `fracture_cortical_break` `perforation_free_air`
`obstruction` `hemorrhage` `effusion_large_or_increasing` `pneumonitis_ild_suspected`
`critical_result_flag` `clinical_correlation_requested` `other_source_flagged`。

| finding_class | 默认 acuity | 固定调整 |
|---|---|---|
| `thrombus_embolism`（肺栓塞/静脉血栓/充盈缺损/瘤栓待排） | urgent | 来源写“大面积/骑跨” → emergent（上调）；来源标危急值 → emergent（`source_critical_flag`）；来源写“陈旧/慢性”且“较前无变化” → incidental |
| `perforation_free_air` | emergent | — |
| `hemorrhage`（活动性出血/新发血肿/消化道出血症状） | emergent | 来源写“陈旧” → incidental；内镜/活检中的接触性出血不登记（§2.1） |
| `obstruction`（肠/胆/尿路/气道梗阻） | urgent | 原文写“梗阻/闭塞/完全阻塞”才入本类；“阻塞性炎症/阻塞性肺不张”等继发改变不入本类，登记为 `other_source_flagged`（§2）；食管/支气管“狭窄”未写梗阻不登记 |
| `effusion_large_or_increasing`（心包/胸腔/腹腔 大量或较前增多） | urgent | 没写量也没比较、少量且稳定或较前减少 → 不入本类，登记为 `other_source_flagged`（incidental） |
| `pneumonitis_ild_suspected`（间质性改变/间质性肺炎、药物/免疫/放射相关肺炎、未写病原的双肺或多发炎症） | urgent | 没有上调：原文写“新发”只映射 `change_vs_prior.direction: new`，仍为 urgent |
| `fracture_cortical_break`（骨折/骨质中断/骨皮质中断或不连续） | urgent | 来源写“陈旧性” → incidental；“骨皮质扭曲/形态不规则”未写骨折 → 不入本类，登记为 `other_source_flagged` |
| `critical_result_flag`（报告危急值标记、临床重要结果通知） | emergent | 单独登记时 `acuity_basis: source_critical_flag`（§4） |
| `clinical_correlation_requested`（影像/检验中依附于具体所见的“请结合病史/临床”） | incidental | 依附于别的类别时按那个类别登记；病理签发套话、检测免责建议不登记（§2.1） |
| `other_source_flagged`（报告自身写“建议进一步检查/复查/随访/超声/CTA”；§2 转入本类的所见） | incidental | 来源写“尽快/立即/急诊” → urgent；继发阻塞性改变（阻塞性炎症/阻塞性肺不张）写“新发/较前加重” → urgent |

`acuity` 枚举：`emergent | urgent | incidental`。表里写“—”或“没有上调”的类别**没有任何上调**：报告的紧急用词
或“新发”不改变它们的 acuity。

`finding_class` 只是路由桶，不是报告的话：下游（段D、SMTB、编排者的 Step 7.5）展示 `label` 与 `verbatim_text`，
不把类名（如 `pneumonitis_ild_suspected` 的“疑似药物性肺炎/间质性肺病”）当作诊断或原文展示。

## 4. 允许的调整（只有这三种，逐字依据写入 `acuity_basis_text`）

`acuity_basis` 枚举：`class_default | source_critical_flag | source_wording_escalation | source_wording_chronic`。

1. `class_default`：按 §3 默认值，`acuity_basis_text: null`。
2. `source_critical_flag`（上调为 emergent）：报告自带的危急值 / critical / clinically significant
   result 标记，且原文能明确对应到这条发现（同句、同一编号条目，或报告写明针对该发现）。对应
   不明确时不上调任何发现，而是把标记本身单独登记为一条 `critical_result_flag`，同样写
   `acuity_basis: source_critical_flag`（`acuity_basis_text` 抄标记原文），`verbatim_text` 只抄标记原文，
   不猜它指哪条；通知日期与时间可以保留，通知人或接收人的姓名、电话、消息编号一律不抄。检验单上印有
   危急值标记的结果同样单独登记为 `critical_result_flag`。
3. `source_wording_escalation`（上调）：**只有 §3 写了上调去向的两类**可以用，且只上调到该去向：
   `thrombus_embolism` 写“大面积/骑跨” → emergent；`other_source_flagged` 写“尽快/立即/急诊” → urgent，
   其中的继发阻塞性改变（`verbatim_text` 含“阻塞”）写“新发”“较前加重” → urgent。其余类别（如
   `pneumonitis_ild_suspected`、`effusion_large_or_increasing`、`fracture_cortical_break`）没有上调，
   “新发”只进 `change_vs_prior.direction`。
4. `source_wording_chronic`（下调为 incidental）：来源**逐字**写“陈旧/陈旧性/慢性/old/chronic”，
   且满足 §3 该行的附加条件（血栓还须写“较前无变化”）。单独的“无显著变化/大致同前/stable”
   **不构成下调依据**——它只说明与上次相比没变，不说明是既往已知的陈旧病变。

除此之外不得调整：不能因为“患者无症状”“看起来不严重”“已经在治疗”而下调，也不能因为“肿瘤
患者风险高”而上调。

### 4.1 调整依据的固定用词（校验器按此核对）

`acuity_basis_text` 抄的是**这条发现所引的行**（`source_ref` 的 `#L` 范围）上的原文；调整用语印在同一份报告的
另一行（如报告末尾写“上述第2条为危急值”）时，把那一行写进可选字段 `acuity_basis_ref`
（`<同一份 sidecar>.md#L<n>`），`acuity_basis_text` 按那一行核对。原文还必须含下表该调整的固定用词之一（NFKC、
不分大小写；英文按整词）：

```text
source_wording_chronic: 陈旧 | 慢性 | old | chronic
chronic_classes: thrombus_embolism | hemorrhage | fracture_cortical_break
thrombus_unchanged: 无变化 | 无显著变化 | 无明显变化 | 未见明显变化 | 变化不大 | 大致同前 | 相仿 | stable | unchanged | similar
source_critical_flag: 危急 | 临床重要 | critical | clinically significant
escalation_thrombus_embolism: emergent | 大面积 | 骑跨 | massive | saddle
escalation_other_source_flagged: urgent | 尽快 | 立即 | 急诊 | urgent | urgently | immediate | immediately | emergency | emergent | 新发 | 较前加重 | new | worsened | worsening
escalation_obstructive_only: 新发 | 较前加重 | new | worsened | worsening
obstructive_words: 阻塞 | obstructive
```

- `escalation_<class>:`：第一个值是上调去向，其后是该类的固定用词；没有这一行的类别不能用
  `source_wording_escalation`。`escalation_obstructive_only` 里的词只对 `verbatim_text` 含 `obstructive_words`
  之一的 `other_source_flagged` 发现有效。

- `chronic_classes`：只有 §3 该行写了下调的类别可以用 `source_wording_chronic`；其余类别没有下调，保持默认值。
- `thrombus_unchanged`：血栓/栓塞下调时，`acuity_basis_text` 还必须含“较前无变化”一类用语（§3 该行的附加条件）。
  反过来，只有“较前无显著变化”而没有陈旧/慢性字样，**不是**下调依据。
- 只含省略号（“……”）的引文不算引文。

校验器（`validate_structured_outputs.py`）按同一张表机械核对：`class_default` 必须等于 §3 默认值；
`source_critical_flag` 必须是 `emergent`；`source_wording_escalation` 只用于有 `escalation_<class>` 行的类别、
且必须等于该行的去向；`source_wording_chronic` 必须是 `incidental`、只用于 `chronic_classes`；后三种的
`acuity_basis_text` 必须逐字出现在所引的行上（或 `acuity_basis_ref` 所指的同一报告的行上），并含上面的固定用词。
`tests/eval/lint/13-organize-prompt-contracts.sh` 检查本节 ```text 块与校验器常量一致。

## 5. 每条记录的形状

每条 finding 的字段（`acute_findings.json.findings[]`）：

- `finding_id`：`AF-001` 起顺序编号；
- `finding_class`、`acuity`、`acuity_basis`、`acuity_basis_text`：见 §3–§4；可选 `acuity_basis_ref`（§4.1）；
- `label`：短标签，只能由原文词语组成（如“L2 椎体骨折”），不添加原文没有的判断词
  （不写“病理性”“转移性”“进展”）；
- `verbatim_text`：原文句子逐字（来自已脱敏 sidecar；可用“……”省略与本发现无关的前后文，
  不得改写保留部分）；
- `exam_date`（检查/采样日期）、`report_date`（报告日期）：来源写了才填，`YYYY-MM-DD` 或 null；校验器要求它是
  所引 sidecar 的文件名日期，或印在该 sidecar（或同一份报告的另一页 sidecar，§2.2）上。病理报告只印
  收到日期或签发日期时，`exam_date` 为 null（收到日期不是采样日期），签发日期写 `report_date`；影像报告只印
  一个日期、没写明是检查还是报告日期时，写 `exam_date`，`report_date` 为 null；
- `source_ref`：`<bucket>/<canonical>.md#L<n>`，句子跨行时 `#L<n>-L<m>`（必须带行号）；`verbatim_text` 按
  “……”切开后的每一段都必须逐字出现在这几行上（空白与全半角不计），校验器按行核对；
- `change_vs_prior`：`{verbatim, direction, prior_date_stated}`，见 §6；
- `timeline_event_id`：对应 timeline 事件的 `event_id`；
- `provenance_layer`：一律 `source_reported`（校验器核对；`source_ref` 也不得指向旧档案摘录 sidecar）；
- `verification_status`：`unverified`。

只从本次原件（`source_reported`）登记。旧档案摘录（`prior_archive`）与患者/照护者自述中的同类
描述不登记为急性发现：前者按既往史进入 timeline，后者若描述正在发生的急症症状，按根目录
`safety-guardrails.md` 先提示联系治疗团队或急诊。

## 6. 与既往比较（只能逐字映射）

- `verbatim`：原文中的比较用语逐字，如“较前增多”“边缘较前清晰”“无显著变化”；原文没有比较
  用语则为 null。`direction` 不是 `not_stated` 时，`verbatim` 必须逐字出现在这条发现所引的行上（§2.2：
  `verbatim_text`、`source_ref` 与 `change_vs_prior` 取自同一处）。
- `direction`：只按下表把原文用语机械映射，不归纳为“进展/好转/缓解”：

| 原文用语（含同义英文） | direction |
|---|---|
| 新发、新出现、new | `new` |
| 增多、增加、增大、加重、扩大、延伸、propagation、increased | `increased` |
| 无显著变化、无明显变化、未见明显变化、较前变化不大、大致同前、相仿、stable、unchanged、similar | `stable` |
| 减少、缩小、减轻、decreased | `decreased` |
| 消失、吸收、resolved | `resolved` |
| 无比较用语，或用语不在上表（如“边缘较前清晰”“较前明显”） | `not_stated`（用语不在上表时 `verbatim` 仍逐字写它；没有比较用语时 null） |

- `prior_date_stated`：原文写明对照检查日期时才填，按原文日期照录为 `YYYY-MM-DD`，否则 null。日期可以
  取自**同一份报告**的任一行（如开头的对照行“与 2030-01-02 片比较”，或同一份报告的另一页），前提是这个对照
  覆盖本条所见；报告把对照日期明确挂在另一条所见上时不借给本条。不从档案里另找一份“上次检查”去补。
  校验器核对这个日期印在所引报告（或同一份报告的另一页）上。

## 7. 与 timeline 的双向链接

每条 finding 必须在 `timeline.json` 有一条独立事件：`category: "acute_finding"`，
`acute_finding_id` 等于 `finding_id`，`title` 用 `label`，`detail` 用 `verbatim_text`，`institution` 取所引报告正文
逐字印的机构名（与该报告的影像/检验事件相同；正文没有就 null，不从文件名取），
`source_refs` 含该 finding 的 `source_ref`，日期取 `exam_date`（缺失时取 `report_date`）。两者都为 null
时：病历复述登记的发现（§2.3）取该病历的就诊日期、`date_precision: approximate`；其余写来源上可见的日期
原文（如“2030年1月”，并按精度填 `date_precision`），同一份报告拆成几个 sidecar 时可取另一页上的日期
（§2.2），来源上完全没有日期则 `date: "unknown"`、`date_precision: "unknown"`；不从文件名、上传时间或
其他文书借日期。
finding 的 `timeline_event_id` 反向指向这条事件（旧版档案上只重跑 Phase 2 时不加这条事件、`timeline_event_id` 写 null，
事件随 `legacy_upgrade` 补上；phase2 §4.0）。原影像/检验事件（`category: imaging|lab`）照常保留。
`timeline.md` 同步写一行，并带 `[[src:…]]` 锚点。

## 8. 文件总是写

`acute_findings.json` **每次运行都写**，旧版档案上只重跑 Phase 2 的运行也写（它是安全面，不是当前契约的标记，
写了不会把旧档案切换成当前契约）；没有发现时写 `findings: []`。文件缺失表示“没有检查过”，与“检查过、没有发现”
必须能区分。

## 9. acute_findings.json 示例（合成数据）

```json
{
  "patient_code": "PT-A1B2C3D4E5",
  "schema_version": "1",
  "generated_at": "2030-01-20T09:00:00Z",
  "findings": [
    {
      "finding_id": "AF-001",
      "finding_class": "thrombus_embolism",
      "label": "右下肺动脉分支充盈缺损",
      "verbatim_text": "右下肺动脉分支内见充盈缺损，考虑肺栓塞可能",
      "exam_date": "2030-01-12",
      "report_date": "2030-01-12",
      "source_ref": "05_影像/CT/2030-01-12_胸部CT_示例医院.md#L14",
      "acuity": "urgent",
      "acuity_basis": "class_default",
      "acuity_basis_text": null,
      "change_vs_prior": {"verbatim": null, "direction": "not_stated", "prior_date_stated": null},
      "timeline_event_id": "E-012",
      "provenance_layer": "source_reported",
      "verification_status": "unverified"
    },
    {
      "finding_id": "AF-002",
      "finding_class": "effusion_large_or_increasing",
      "label": "盆腔积液范围较前扩大",
      "verbatim_text": "盆腔积液，范围较前扩大",
      "exam_date": "2030-01-12",
      "report_date": "2030-01-12",
      "source_ref": "05_影像/CT/2030-01-12_胸部CT_示例医院.md#L17",
      "acuity": "urgent",
      "acuity_basis": "class_default",
      "acuity_basis_text": null,
      "change_vs_prior": {"verbatim": "较前扩大", "direction": "increased", "prior_date_stated": null},
      "timeline_event_id": "E-013",
      "provenance_layer": "source_reported",
      "verification_status": "unverified"
    }
  ]
}
```

## 10. 不得出现的写法

- 由发现推断诊断、分期或疗效：“提示骨转移”“肿瘤进展所致”“治疗有效”；
- 给出处理结论：“需要抗凝”“无需处理”“可暂不处理”；
- 替原文补齐：原文只写“充盈缺损”，`label` 不写成“肺栓塞”；原文写“血栓或瘤栓待鉴别”，
  两种可能都保留；
- 把 `[OCR_UNCERTAIN:U-nnn]` 所在字段当作已确认文字登记：该句仍登记，但 `verbatim_text` 保留
  不确定 token，并在 `readiness.json` 有对应 flag。

## 11. 展示

编排者在整理结束后先于速查清单展示 emergent/urgent 发现：逐条给出原文、日期和来源，说明“这些
是报告原文写到的发现，按整理规则属于需要尽快告知治疗团队的类别”，并按 `safety-guardrails.md`
提示联系治疗团队；不解释病因、不评估严重程度、不给处理建议。
