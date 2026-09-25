# 病情资料摘要 HTML 数据生成合同（段 D）

本步骤只组织来源，不作临床判断。先生成 `case_summary_data.json`，再由
`scripts/render_html_template.py` 确定性渲染，并运行现有 schema、来源锚点、PII 和 HTML
验证。验证失败则不交付。

## 只读输入

读取脱敏后的 `profile.json`、结构化 JSON（含 `acute_findings.json`）、`case_text.md` 和模板。不得读取
未授权明文 PII，不得从原图重新解释临床内容。任何存在忠实度、OCR（含 `[OCR_UNCERTAIN:U-nnn]`）、
未确认的 `document_intent`、身份或来源冲突的值不得作为确定值显示，并列入 caveats；原始分层数据保留
以供复核。显示方式分两种：

- **核心单值字段**（`stage`）：不置 null（来源里有分期、摘要里却空着，会被核心完整性检查判为丢失），
  而是写成待核对字样：OCR 不确定或未确认的 `document_intent` → `待核对（字面读作 X）`，X 是去掉
  `[OCR_UNCERTAIN:U-nnn]` 标记后的字面读数；`unfaithful_values` 中的值 → `待核对（整理值与原件不一致，
  请以原件为准）`，不复述该值。分子与治疗数组照下文“段D 管线”第 1 步保留元素、只清空值字段。
- **其他字段**：置 `null`（模板显示“资料缺失”）。

Call parameters 中的 `unfaithful_values` 逐项按上面两种方式处理（见下文“段D 管线”）。

## 临床真值红线

- `stage`、诊断、方案、分子结果、实验室值只复制来源，并显示来源层级和验证状态。
- `response`、CR/PR/SD/PD 和 ECOG 只在医生来源明确写出时复制；不得从影像、症状或功能描述推断。
- 不生成“当前治疗路径”、治疗建议、器官限制、严重度或下一步检查。
- 不使用通用 `3×参考上限` 或任何跨检验项目阈值分级。只显示原报告 flag/危急值标记及其来源。
- 肿瘤标志物、实验室、症状、可穿戴和病灶描述趋势均为观察事实，不是疗效。
- 冲突不裁决胜者。并列显示来源并标 `disputed`，直到更正报告或授权临床人员签认。
- 患者确认只能创建 `patient_reported` 层，不能修正或覆盖来源层。

## 趋势

按 `cancer-trend-markers.md` 选择。每个点逐字来自结构化数据，保留 raw value、单位、日期、
方法和 source_ref。`interpretation` 只能是中性的数值/日期描述；不解释原因或临床意义。
SVG 坐标仍由确定性脚本生成，模型不得造点或手算坐标。

## 数据映射

- 患者标识：只显示最小必要字段；`patient_code` 不是身份认证。
- 年龄/体重/身高：**必须连同其 `_as_of` 日期一起显示**（"52 岁（2024-03-11 报告）"），裸数字等于把旧快照当现况。`birth_year` 非空时可在旁边补一个明确标注"约"的现龄，不替换带日期的快照。跨年份的取值差异是时间演变，**不置 null、不进 caveats、不标 `disputed`**（见 `organizer-prompt-phase2-synthesis.md` §2.1）；只有同日期矛盾或与时间跨度冲突才按 §上文冲突规则处理。
- 诊断/分期：原文 + source_ref + verification_status；缺失为 null。
- ECOG：clinician-reported only；否则显示患者功能描述，不转成分数。医生书写的体能状态原文（`performance_status_verbatim`，
  如“PS=2”）不填进 ECOG 栏，写进 caveats：“体能状态原文：PS=2（2030-01-05 报告，原文未注明量表），未换算为 ECOG”。
- 病灶：逐份报告的描述与日期；不合成 progression/response。
- 分子：精确变异、方法、样本、日期、质量/限制；不连接药物。
- 治疗史：按事件和来源列出；不自动计算“线”，维持/巩固/围手术期保留原标签；同一方案的各周期是一个事件，
  周期写法（`cycle_label_verbatim`，如“第4程”）照原文附在方案旁，不写成线次。
- 当前治疗：取 `status: ongoing` 的事件，连同依据写出（如“2030-01-05 门诊记录：继续原方案”“影像申请单写明正在
  使用 X”）；`status_as_of_precision: "undated_self_report"` 时写“家属陈述（未注明日期）正在接受 X”，不配日期。
- 实验室：每个结果自己的单位、参考范围、报告 flag 和 source_ref。只用 `value` 非 null 的结果；
  `candidate_value`（按位置配对、未核实）和拒绝配对的项目不显示为数值、不进入趋势，只在 caveats 说明
  “该日检验单的数值未能可靠对应到项目，请以原件为准”。
- 急性/附带发现：模板没有专门区块，而 caveats 渲染在页面最底部的脚注里，不够醒目。因此：
  - 有 emergent/urgent 发现时，`case_summary_narrative`（页面上方的“病情概要”）**第一句**写：
    “资料中有报告写到需要尽快告知治疗团队的发现：<label>（<日期>）；<label>（<日期>）。”
    这句前缀是中性的（“报告写到”，不写“报告原文写到”），因为外文报告只有中文转述的发现也在其中：
    `verbatim_is_translation: true` 的发现在日期括号里标明，写成“<label>（<日期>，中文转述）”（没有日期时写
    “<label>（中文转述）”）。只用 `label` 与日期，不加判断词，不写 `finding_class` 的类名（它是路由桶，不是报告的话，
    如 `pneumonitis_ild_suspected` 不能写成“疑似药物性肺炎”）；几份报告各登记的同一个 `label` 合写一次、列出全部日期
    （“<label>（<日期1>、<日期2>）”）——转述的与原句的不合写，几条转述的同名发现合写成“<label>（<日期1>、<日期2>，
    中文转述）”；其后才是原有的病情概要句子（验收门检查这一句：以该前缀开头，逐条含每个 emergent/urgent 发现的
    `label` 与日期，转述的发现其 `label` 紧跟的括号里有“中文转述”）；
  - caveats 最前面逐条写完整原文：“报告原文：<verbatim_text>（<日期>，<来源文书>）——请尽快告知治疗
    团队”；`verbatim_is_translation: true` 的发现是外文报告的中文转述，写成“报告（外文）中文转述，非报告原句：
    <verbatim_text>（<日期>，<来源文书>）——请尽快告知治疗团队”，不称“报告原文”（`acute-findings.md` §2.4）；
    incidental 发现只在 caveats 写原文与日期（转述同样标明），不进病情概要。验收门（`validate_structured_outputs.py`
    的 段D 检查；`validate_case_summary_html.py` 只查页面形状）核对：转述发现的 `verbatim_text` 出现在
    引文位置（冒号或开引号之后，其后紧接“（”“；”“——”“。”或该条结尾；按占满这个位置的最长一条发现原句计）时，
    它前面紧挨着“中文转述，非报告原句：”（中间可隔一个开引号），不论引导语写的是“报告原文：”还是别的说法；
    别的发现的原句里恰好含有这几个字、或句中顺带提到它们，不算引用它。两条发现原句一字不差时，按引文后括号里的
    日期区分，所以括号里照写该发现自己的日期。
  - 不解释病因、不评估严重程度、不给处理建议。不改 `one_line_condition`（它会被复制进 `AGENTS.md`）。
- 旧档案摘录（`provenance_layer: prior_archive`）的事实只可出现在既往史相关内容中，并逐项标注
  “来自既往摘要，原件未在本次资料中”（与 `PATIENT_DIR_CONTRACT.md` §5 (e) 同一句）；不得出现在当前方案、当前
  状态或病情概要的现况描述里。
- caveats：缺失、缺页、资料时效（`days_since_latest` 超过 14 天时照抄 `readiness.json.warnings[]` 中
  `source_freshness.py` 写的那一句，不改写）、
  来源冲突、OCR、单位/方法不兼容、患者自述与正式报告差异。

## i18n 与术语

按根目录 `i18n.md` 保留来源原文，同时允许验证后的标准化字段和患者语言解释。不能根据
研发代号猜通用名；只有权威来源完成映射时才添加 normalized name。

## 页脚

显示生成时间、工具版本、输入 hash、来源清单和：

> 本页是资料索引，不替代主诊医生的判断，不包含疗效、分期重判或治疗建议。冲突与缺失项需由原报告机构或主诊团队核对。

## 段D 管线（段D worker 在自己的上下文内完成，返回 `template_sha`）

下面的命令都相对本 skill 目录：Call parameters 的 `skill_dir` 是它的绝对路径（你的工作目录不是它）。先 `cd "<skill_dir>"` 再运行；脚本一律写成 `"<skill_dir>/scripts/…"`，图表脚本写成 `"<skill_dir>/../cancer-buddy-charts/scripts/…"`（同级 skill，不依赖工作目录）。

段D worker 拥有整条管线，返回值只能是 `{status:"ok", template_sha:"<64-hex>"}`（验证通过）或
`{status:"failed", reason, exit_code}`，永不返回内联 HTML。它是 `.case_summary_data.json` 的唯一写入者。

1. **组装数据**：按上文“数据映射”生成 `<patient_dir>/.case_summary_data.json`。`unfaithful_values`
   中的每个值按“只读输入”一节处理（`stage` 写待核对字样，其余置 null，模板显示“资料缺失”），病情概要
   里也不得复述；数组元素（`labs[]` /
   `molecular_rows[]` / `treatment_lines[]`）只置空值字段、保留元素，并把同级 `*_class`
   字段（`lab_class` / `line_marker_class` / `line_badge_class`）写成显式 `""`，不得省略。
2. **富化**：

```bash
mkdir -p "<patient_dir>/case_summary_versions"
prev=$(ls -1 "<patient_dir>/case_summary_versions/case_summary_data_"*.json 2>/dev/null | sort | tail -1)
if [ -n "$prev" ]; then
  python3 "<skill_dir>/scripts/compute_version_delta.py" --data "<patient_dir>/.case_summary_data.json" --prev "$prev"
else
  python3 "<skill_dir>/scripts/compute_version_delta.py" --data "<patient_dir>/.case_summary_data.json"
fi
python3 "<skill_dir>/scripts/backfill_lab_trends.py" \
  --data "<patient_dir>/.case_summary_data.json" --labs "<patient_dir>/labs.json" --profile "<patient_dir>/profile.json"
long_arg=""; [ -f "<patient_dir>/longitudinal_observations.json" ] && long_arg="--longitudinal <patient_dir>/longitudinal_observations.json"
python3 "<skill_dir>/../cancer-buddy-charts/scripts/render_chart.py" \
  --data "<patient_dir>/.case_summary_data.json" $long_arg --labs "<patient_dir>/labs.json"
# exit 3 = 画出的点在源库查无 → 修数据后重跑，绝不绕过；exit 4 = 读图说明含疗效/病情判决词 → 改写成读图指引。
# 未随包安装 cancer-buddy-charts 时退回 scripts/compute_sparklines.py（功能等价，无参考区间带）。
```

3. **盖戳、渲染与验证**：先给渲染数据盖上它读到的急性发现版本（`acute_findings_sha256` = 此刻 `acute_findings.json`
   的 sha256，脚本写入；不要手填）。之后的运行改了急性发现而没有重渲染时，校验器靠它把“过期”（有 Phase 2 的过期提示时 WARN）与
   “读到了却没写进首句”（ERROR）分开，终态门 `--final` 也要求它存在。新登记或改动了 emergent/urgent 发现后，编排者
   必派你重新渲染（旧版档案同样：你照读现有 JSON，不升级档案）。

```bash
python3 "<skill_dir>/scripts/stamp_case_summary_sources.py" "<patient_dir>"
python3 "<skill_dir>/scripts/render_html_template.py" \
  --template references/templates/case-summary.template.html \
  --data <patient_dir>/.case_summary_data.json --out <patient_dir>/病情简要总结.html
python3 "<skill_dir>/scripts/validate_case_summary_html.py" --html <patient_dir>/病情简要总结.html \
  --template references/templates/case-summary.template.html \
  --profile <patient_dir>/profile.json --data <patient_dir>/.case_summary_data.json
```

验证通过（exit 0，含核心完整性检查：来源中存在的分期、驱动基因、当前方案不得在摘要中丢失），并且
`python3 "<skill_dir>/scripts/validate_structured_outputs.py" <patient_dir> --readonly` 的输出里没有以
`ERROR: .case_summary_data.json` 开头的行（盖戳后首句漏写 emergent/urgent 发现、首句仍是旧写法“资料中有报告原文写到…”、转述的发现没标“中文转述”或 caveats 在引文位置把转述当作报告原句，都在这里报错；其他文件的错误不归你），才返回
`template_sha`。趋势图只填该次报告自带的参考区间，禁止套用通用参考值。

4. **版本快照**（编排者在收到通过的 `template_sha` 后执行，不属于段D worker）：把根目录
   `病情简要总结.html` 与 `.case_summary_data.json` 复制为 `case_summary_versions/病情简要总结_<日期>.html`
   与 `case_summary_data_<日期>.json`（同日重复生成加 `_2`、`_3`）；根目录文件始终是最新版，旧快照不可改。
