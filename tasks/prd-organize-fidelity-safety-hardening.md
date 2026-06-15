# PRD: cancer-buddy-organize 保真与安全加固（Fidelity & Safety Hardening）

> **目标分支**: `feat/generalized-data-taxonomy`（当前 HEAD `de3269f`，云端 `cancer-buddy-skill`，直接在此分支迭代，不另开 fix 分支）
> **OCR 基线**: LLM-vision（`codex_exec_image` / Phase-1 LLM 摄入）为唯一 OCR 引擎
> **范围**: 全量 P0 / P1 / P2 综合改造
> **仓库放置**: cancer-buddy-skill 为公开仓；本内部 PRD 提交前须将 `tasks/` 纳入 `.gitignore` 或迁至私有位置，不随公开仓发布。
> **证据基线**: 所有 file:line 均已对 `feat/generalized-data-taxonomy` HEAD `de3269f` 源码核实。

---

## 1. Introduction / Overview

cancer-buddy-organize 把一位癌症患者的原始病历（HEIC/jpg/pdf/docx/xlsx/zip）经 Phase-1 LLM-vision OCR 转成 sidecar `.md`，分入 `01–14`+`99` 编号桶，产出结构化 JSON（profile / patient_summary / labs / molecular / comorbidities / treatment_lines / timeline / readiness / missing_items / source_inventory）与叙事产物（INDEX.md / case_text.md / timeline.md / review_summary.md / review_flags.md / 病情简要总结.html / AGENTS.md）。

对两份真实产物的审查暴露**两类患者安全级缺陷 + 一类去标识失效**——错误数据/真实身份会静默流入患者可见交付物：

1. **数值保真**：肿瘤标志物列错位（CEA 真值 25.30↑ 被记成隔壁 CY211 的 4.68 并标记为正常，伪造"缓解"信号并污染纵向趋势）；肾功能（肌酐 135.5↑、尿酸 656↑）在 OCR 散乱后于落库阶段丢失。
2. **同档案冲突缺裁决与标注**：手术日期在同一档案两份 sidecar 冲突（`1月2日` vs `1月12日`），错值 `2023-01-02` 传播到 9 个 IHC 日期 + 治疗线 + 时间轴 + 患者可见 HTML。
3. **去标识跨 surface 失效**：真名 `王国洪`、上传者邮箱 `452858265@qq.com`、家属标识 `yosean 父亲` 泄漏进 `INDEX.md` / `source_inventory.json`（`original_path`）/ dotfiles。

### 实现基线（决定每个 story 是"扩展/验证"而非"重建"）

- `scripts/pii_rescan.py`：`collect_sidecars()`（:254-273）**只** glob `ocr/` 或 `NN_` 桶下 `*.md`；`scan_sidecar()`（:234）**显式跳过** `SOURCE:`/`ORIGINAL:` 头块 → `INDEX.md`/`source_inventory.json`/dotfiles/文件名**从未被扫**（US-001 根因）。
- `scripts/validate_structured_outputs.py`（:6-9）按设计**不做任何医学/内容判断** → CEA 列错位是 schema-valid 而放行（US-002 是**新增**形不变量层）。
- Phase-2 synthesis：`cross_doc_contradiction`（:475）已对跨 sidecar 冲突发红 flag；`cross_patient_name_collision`（:484-512）已是 P0 串号检测（US-004/US-010 仅补残差）。
- `references/templates/agents-md.template.md`（6.4KB）已含两层路由表+14 桶 key+硬规则，`SKILL.md` Step 13（:183-200）确定性填充（US-008 仅验证）。
- `references/organizer-prompt-phase1-ocr.md` §2.4（:103）已强制 mask 签名（US-007 仅补散乱兜底）。
- schema 既有约束：`molecular.schema.json` `evidence_tier∈{I,II,III,IV,null}`（:26）、`tmb.unit∈{mut/Mb,null}`（:68）；`treatment_lines.schema.json` `line minimum:0=新辅助/围手术期`（:20）；`labs.schema.json` `flag∈{H,L,HH,LL,null}`（:32）；`patient_summary.schema.json` `current_status`(rollup) 与 `latest_status`(含 ecog+longitudinal 快照) 有意拆分（:47-70）；`source_inventory.schema.json` `patient_dir` 绝对（:11）、`raw_path` 已相对 `^raw/`（:24）。
- 原则：语义判断一律走 **sub-skill prompt / Agent**；确定性脚本保持无关键词表。

---

## 2. Goals

- **G1（安全门）**：任何含 PII 的字符串都无法进入任何**已交付 surface**（sidecar 正文/头、`INDEX.md`、`source_inventory.json`、`timeline.*`、`case_text.md`、`病情简要总结.html`、dotfiles），含文件名/路径片段；验收门对 PII 残留**零容忍**。
- **G2（数值保真门）**：结构化数值（labs / molecular / treatment_lines）必须与其 `source_refs` sidecar 表格**逐值忠实**；异常值不得被静默标记正常、不得被丢弃；不一致即 **block**。
- **G3（冲突不静默）**：同一事实多 sidecar 冲突时按显式来源优先级裁决并**强制 review_flag**；患者可见层不得出现未标注的被裁决值。
- **G4（叙事诚实）**：来自照片 OCR 的定量趋势在 `case_text` / `review_summary` / HTML 中必须带 OCR 不确定性提示。
- **G5（版本/格式自证）**：当前 HEAD 在**全量多格式 + 含名输入**（HEIC/jpg/pdf/docx/xlsx/zip）上完整摄入并触发全部 P0 门，建立黄金回归基线（≥2 患者、≥2 癌种）。
- **G6（schema 一致与可复现）**：同 `schema_version` 键集统一；`patient_dir`/`original_path` 相对化；sidecar 头含重命名稳定 UID；构建记录 commit。

---

## 3. User Stories

> 优先级：**P0** = 安全/正确性致命，阻塞发版；**P1** = 正确性与安全卫生；**P2** = schema 一致性与打磨。每个 story 可在一个聚焦 session 内完成。

### —— P0 ——

#### US-001: PII 残留门覆盖 provenance / index / 路径 / 文件名 surface
**Description:** 作为患者数据守门人，我要堵住真名/邮箱/家属标识从文件名与索引层泄漏。

**Acceptance Criteria:**
- [ ] **扩展扫描入口（非替换）**：`validate_structured_outputs.py` 调 `pii_rescan` 时新增扫描 `INDEX.md`、`source_inventory.json`、`.rename_plan.json`、`.phase1_sources.json`、`update_log.json`、`病情简要总结.html`；`scan_sidecar` 增 `scan_header=True` 模式用于这些非 sidecar 文件（保留 `NN_` sidecar 仅扫正文的既有行为）
- [ ] **文件名/路径片段检测**：对 `original_path`/`bucket_path`/路径串 basename 做 PII 检测（中文姓名、邮箱、`<人名>-<报告名>` 模式）；`raw_path` 已相对仍扫 basename
- [ ] **身份 deny-list（解决 bootstrap）**：`patient_summary.name` 已被 null，故种子取自 Phase-1 mask 前捕获的原始姓名 + 源目录/文件名出现的家属标识（`yosean 父亲`）+ 上传账号（`*@qq.com`），跨所有 surface 确定性查杀
- [ ] `PT-78FBCE6E0F` 复现夹具：必扫出 `王国洪`（INDEX/source_inventory/dotfiles）、`452858265@qq.com`、`yosean 父亲`
- [ ] 退出码 1 → `validate_structured_outputs.py` 整体 FAIL（PII 零容忍）
- [ ] 既有"仅扫 sidecar 正文、不碰临床日期/检验值/药名/TNM/分子标记"反锚定行为不回归
- [ ] 单测：含名夹具 FAIL、纯净夹具（`PT-6969D8D0A8`）PASS

#### US-002: 数值完整性确定性门（flag / 参考区间 / 丢值）
**Description:** 作为审查者，我要在 `validate_structured_outputs.py` 增加**确定性、无医学判断**的数值不变量。

**Acceptance Criteria:**
- [ ] **零阈值发明**：只读 sidecar 表格 `↑/↓/H/L` 标记与 labs.json 自带 `reference_range`；`flag∈{H,L,HH,LL,null}`（labs.schema.json:32）；绝不内置疾病/药物/阈值表
- [ ] **block (a)**：labs.json 值落在 `reference_range` 外却 `flag=null` → block（命中 CEA 4.68 标记正常）
- [ ] **block (b)**：被 `source_refs` 引用的 sidecar 表格有带异常标记的数值行而 JSON 对应 panel 缺该值 → block（命中肌酐 135.5↑ / 尿酸 656↑ 丢失）
- [ ] **列错位启发式**：同行"项目↔值↔单位"在 JSON 错配 → WARN 并触发 US-003 语义复核
- [ ] 单测：`PT-78FBCE6E0F` 夹具，CEA 4.68 与缺失肾功能两处均 block

#### US-003: 抽取忠实度复核 sub-skill（Phase 2.5）+ 结果接入渲染
**Description:** 作为患者，我要每个结构化数值经一次"回看原 sidecar"语义复核，且复核结果真正阻断坏值进入患者可见层。

**Acceptance Criteria:**
- [ ] **【load-bearing，置顶】结果接入渲染**：CRITICAL verdict 必须传到段D 数据（`.case_summary_data.json`）/ `render_html_template.py`，使坏值在 `病情简要总结.html` 被抑制；附 top-down 走查 AC（user→json→sidecar→raw→HTML 连通），防"计算但断连"死代码
- [ ] 新增 `references/organizer-prompt-phase2_5-faithfulness.md`：对每个 labs/molecular/treatment 数值，给 JSON 条目 + 其 `source_refs` sidecar 片段，判"忠实/不忠实/无法判定"并给证据
- [ ] 由主流程 dispatch（Agent / sub-skill），**不**主线程内联硬编码；输出结构化 verdict；"不忠实"→ `review_flags.md` 记 **CRITICAL**
- [ ] `PT-78FBCE6E0F` 夹具：CEA 列错位与肾功能丢值被标 CRITICAL 且在 HTML 被抑制
- [ ] **成本可控**：按 sidecar 批量复核而非逐值起 agent；记录每次运行的 agent 数/token 量

#### US-004: 同档案冲突的来源优先级裁决 + 患者可见标注
**Description:** 作为临床读者，我要冲突被显式裁决并在患者可见层标注（检测已存在，补裁决与标注）。

**Acceptance Criteria:**
- [ ] **先校验**本例（手术日 `1月2日` vs `1月12日`）确实触发既有 `cross_doc_contradiction`（synthesis Step 3 #2，:475）；若漏触发则修检测覆盖
- [ ] 新增**来源优先级裁决规则**写入 `organizer-prompt-phase2-synthesis.md` Step 3：原始报告 > 病理/诊断证明 > 病程/入院记录转述；同级取信息更完整者
- [ ] 被裁决值在 `case_text.md` / `病情简要总结.html` 附"存在来源差异，已按 X 裁决"标注；既有红 flag 保留
- [ ] `PT-6969D8D0A8` 夹具：触发冲突 flag，且 `2023-01-02` 不再静默写入 timeline/molecular/HTML

#### US-005: 数值表 OCR 结构保真（行列对齐 + 分块置信 + 重读）
**Description:** 作为下游一切数据的源头，我要 Phase-1 OCR 对检验/医嘱表保持行列对齐（CEA 列错位的上游根因）。

**Acceptance Criteria:**
- [ ] `organizer-prompt-phase1-ocr.md` 强化数值表规则（§2.2a 仅禁平滑、未约束表结构）：**禁止**输出"项目名块 + 脱离数值块"；逐行 `项目 | 值 | 单位 | 参考 | 标记` 对齐
- [ ] **分块置信**：每个数值表块单独给置信（§2.3 当前为整文件统一）；低置信表触发一次结构化重读 pass
- [ ] 药物剂量/单位为高危字段重点重读（B 把 5ml→`6ml`、`0.6g 静脉滴注`→`0.68 前脉滴注`）
- [ ] 重叠数据上新版 OCR 不得出现"中国医𡦃科荸眈/林白鹅/ECFR/分期 IV→I"类破坏（回归夹具校验）

### —— P1 ——

#### US-006: 叙事层 OCR 不确定性披露
**Acceptance Criteria:**
- [ ] labs 趋势进入 `case_text.md` / `review_summary.md` / HTML 时自动附 OCR caveat
- [ ] `review_summary.md` 的"需复核"段含 lab-OCR 对齐类条目（不止"缺原始报告"类）
- [ ] `PT-6969D8D0A8` 夹具：CEA/CA19-9/VEGF/肌酐 趋势叙事旁出现 OCR caveat

#### US-007: 散乱 OCR 人名的确定性兜底
**Description:** 语义脱敏已存在（phase1-ocr §2.4），仅补 OCR 打散后漏网的确定性人名检测。

**Acceptance Criteria:**
- [ ] `pii_rescan.py` 新增"中文人名 + 医嘱/报告上下文（主诊/经治/审核/报告医师/护士/申请医生）"检测，命中 B 6 文件的 `荆碧聪` 等散乱签名
- [ ] `PT-6969D8D0A8` 残留的单处 `刘俊宝`（尿液分析）被捕获

#### US-008: 验证 AGENTS.md 运行期填充
**Description:** 6.4KB 模板（`agents-md.template.md`）+ `SKILL.md` Step 13 填充已存在；Output A 的 330B 是运行期产物，非代码缺陷。

**Acceptance Criteria:**
- [ ] 验证一次真实运行写出**完整填充**的 AGENTS.md；若产出桩，定位并修字段注入/运行顺序 bug
- [ ] **不**重写模板、**不**以 Output B 为对照

#### US-009: 空桶策略（根因在 setup mkdir）
**Acceptance Criteria:**
- [ ] 修 `SKILL.md:99`（`mkdir -p` 全 14 桶 = 10 个空脚手架桶来源）：**不预建空临床桶**，或在 `INDEX.md` 对每个保留空桶注"该桶为空：源材料未提供原始 X 报告"；同步 `bucket-taxonomy.md`
- [ ] `PT-6969D8D0A8`：空 `09_手术与操作` 与"已行切除"叙事不再矛盾无注解

#### US-010: 去标识一致性 + 数字模式
**Description:** 跨患者串号检测已存在（synthesis :484-512），补同类字段一致处理与数字型标识。

**Acceptance Criteria:**
- [ ] `标本编号` / 检验号 / 病案号 等同类字段**全有或全无**处理（消除 A 的 11 mask / 8 明文不一致）
- [ ] `pii_rescan.py _STANDALONE`（:137-145）新增模式：邮编（`046204`）、18 位医疗代码（`0039807110105111111`）、裸号检验号（label 被打散后单独成行的 `24080800634`）
- [ ] 两份夹具复扫无上述残留

#### US-011: 安全导出模式（排除 raw/ 原图）
**Acceptance Criteria:**
- [ ] 新增导出能力：产出 `patient_dir` 可分享副本，**排除 `raw/`**、去 `.DS_Store`/空 `ocr/`、`source_inventory` 路径相对化
- [ ] 导出包须先过 `validate_structured_outputs.py`（含扩展 PII 门）方可生成
- [ ] 不重新引入 raw 像素脱敏（见 Non-Goals）

### —— P2 ——

#### US-012: evidence_tier 语义对齐（schema 合法值 + 定位）
**Description:** `molecular.schema.json:26` 已固定 `evidence_tier∈{I,II,III,IV,null}`；`null` 即"未分级"。

**Acceptance Criteria:**
- [ ] **不**写 schema 外的值；保持 `null` 为显式"未分级"
- [ ] 分级填充**默认延后到 vMTB 阶段**（organize=整理非分析）；若确需 organize 标记"待分级状态"，须先在本 PRD 显式列出对 `molecular.schema.json` 的增字段（如 `tier_status`）修订再实现

#### US-013: 规整 patient_summary confidence 键集（不合并状态对象）
**Description:** `current_status`/`latest_status` 是 schema 有意拆分、下游依赖，**不合并**。

**Acceptance Criteria:**
- [ ] `confidence` map 采 schema 强制 canonical 键集（消除 A `lab_values` vs B `labs`、A 缺 `treatment_lines`）
- [ ] `diagnosis.confidence` 不再同时内嵌于 diagnosis 对象与顶层 map（去重）
- [ ] 保留两个 status 对象；如有键漂移用 schema 约束各自键集

#### US-014: `patient_dir`/`original_path` 相对化（连 schema 一起改）
**Acceptance Criteria:**
- [ ] 改 `source_inventory.schema.json:11`（`patient_dir` 绝对为现设计）允许/要求相对或占位；同步改 Phase-2 prompt 示例 `organizer-prompt-phase2-synthesis.md:250`（现写 `/abs/PT-XXXX`），生产端停写绝对路径
- [ ] `original_path` 相对化或仅保留 basename（去绝对云盘/邮箱/家属路径）
- [ ] 修正 `CancerDAO`→`cancerdao` 大小写

#### US-015: sidecar 头内嵌重命名稳定 UID
**Acceptance Criteria:**
- [ ] sidecar 头新增 `FILE_ID:`（与 `source_inventory` 的 `f0xx` 一致），重命名后仍可回链；非 HEIC（docx/pdf 同名对）唯一可寻

#### US-016: 固定 lab 日期语义（采集 vs 报告）
**Acceptance Criteria:**
- [ ] `labs.schema.json`（`values[]` 现仅 date/value/flag）新增 `date_kind`；抽取 prompt 明确 `date` 取采集日期（缺失才回退报告日期）；消除同次抽血两版差一天（A 取报告 08-09 / B 取采集 08-08）

#### US-017: 卫生与一致性打磨
**Acceptance Criteria:**
- [ ] 运行结束清理 `.DS_Store`、空 `ocr/` 暂存目录
- [ ] docx/pdf 同一逻辑源去重或加 `alias_of` 交叉链字段（消除 source_units 虚高 + 跨引用歧义）
- [ ] **HTML 去模板注释（cosmetic）**：`render_html_template.py` 渲染后剥离所有**非 provenance** HTML 注释（`<!-- LOOP/RENDER_IF/来源: ... -->`），**保留** `template_sha256` provenance 注释（:295）
- [ ] **TMB 单位不臆造**：schema 允许 `mut/Mb`，纪律在 synthesis prompt + US-003——源为 `79Muts`（计数）时写 `unit=null` + flag，**禁**写 `mut/Mb`

### —— 跨切（综合范围必做）——

#### US-018: 含名全格式受控再跑 + 黄金回归基线
**Description:** 本 story 是整份 PRD 的证明义务：当前 HEAD 仅在无名 HEIC 上被验证过。

**Acceptance Criteria:**
- [ ] 用当前 HEAD 喂**含名输入**（`王国洪-*.pdf` + ≥1 个 docx/xlsx/zip），先**实证复现** INDEX/source_inventory/dotfiles 的 `王国洪`/邮箱/yosean 泄漏（修复前），确认非 HEIC 格式完整摄入（否则记摄入回归补 US）
- [ ] 修复后重跑过全部 P0 门：PII 门泄漏归零、数值门拦 CEA/肾功能、冲突门报手术日
- [ ] 黄金回归 **≥2 患者、≥2 癌种**：夹具一 = `PT-78FBCE6E0F`（结直肠癌）；夹具二 = 从现有 17 份 `patients/` 档案选一**非结直肠癌**样本（候选 `PT-17CE02BC33` / `PT-2685BF971D` / `PT-48C5070065` / `PT-8D9D41FCFE` / `PT-9A576D14D8` / `PT-B7981F5800` / `PT-C3F78EBB84` / `PT-EE62321353` / `PT-RIAZ-R-001`，癌种待 1 行核实后选定），附验证矩阵
- [ ] 一条命令复跑全部门并出红绿（接入 `validate_structured_outputs.py`）

---

## 4. Functional Requirements

- **FR-1**（US-001）PII 残留门扫描全部已交付 surface（`INDEX.md`/`source_inventory.json`/dotfiles/HTML/sidecar 头/文件名·路径片段），以患者身份 token 为 deny-list；任一命中→验收门 FAIL；扩展 `collect_sidecars` 入口 + `scan_header` 模式，不破坏既有仅扫正文行为。
- **FR-2**（US-002）验收门新增确定性数值不变量：reference_range↔flag 一致性、被引用 sidecar 异常值丢失检测、列错位启发式；只读 `↑/↓/H/L` 与 `reference_range`，零阈值发明；致命项→block。
- **FR-3**（US-003）sub-skill 忠实度复核（Phase 2.5），CRITICAL→ 接入 `.case_summary_data.json`/渲染并抑制坏值入 HTML；语义判断不得硬编码；按 sidecar 批量以控成本。
- **FR-4**（US-004）复用既有 `cross_doc_contradiction`；新增来源优先级裁决规则 + 患者可见"已按 X 裁决"标注；校验本例触发。
- **FR-5**（US-005）Phase-1 OCR 数值表行列对齐 + 分块置信 + 低置信重读；禁脱离数值列。
- **FR-6**（US-006）照片 OCR 定量趋势在叙事/HTML 带 OCR caveat。
- **FR-7**（US-007）`pii_rescan.py` 增散乱中文人名兜底（语义脱敏已存在于 phase1-ocr §2.4）。
- **FR-8**（US-008）验证 `SKILL.md` Step 13 写出完整 `agents-md.template.md`；不重建模板。
- **FR-9**（US-009）修 `SKILL.md:99` 不预建空临床桶，或在 `INDEX.md` 注解空因。
- **FR-10**（US-010）同类标识一致处理；`pii_rescan _STANDALONE` 覆盖邮编/18 位医疗代码/裸号检验号（串号检测已存在）。
- **FR-11**（US-011）排除 `raw/` 的安全导出，导出前过验收门。
- **FR-12**（US-012）`evidence_tier` 用 schema 合法值（`null`=未分级）；分级默认延后 vMTB；如需状态字段须先列 schema 修订。
- **FR-13**（US-013）`confidence` map 键集 schema 统一 + `diagnosis.confidence` 去重；**不合并** `current_status`/`latest_status`。
- **FR-14**（US-014）改 `source_inventory.schema.json:11` + Phase-2 prompt:250，`patient_dir`/`original_path` 相对化 + 大小写修正。
- **FR-15**（US-015）sidecar 头内嵌 `FILE_ID`。
- **FR-16**（US-016）`labs` 新增 `date_kind`，`date` 采集优先。
- **FR-17**（US-017）清理 `.DS_Store`/空 `ocr/`；docx/pdf 去重或 `alias_of`；HTML 剥非 provenance 注释（留 template_sha256）；TMB 单位不臆造。
- **FR-18**（US-018）含名全格式受控再跑实证复现泄漏 + ≥2 患者≥2 癌种黄金回归 + 一键复跑。

---

## 5. Non-Goals（明确不做）

- **不做 raw/ 原图像素脱敏**：已被有意移除（`validate_structured_outputs.py:33` "former segment B is removed"）；安全分享靠 US-011 排除 raw/。
- **不合并 `current_status` / `latest_status`**：二者职责经 schema 有意拆分、下游依赖。
- **不写 schema 外的 `evidence_tier` 值**；不在 organize 阶段强制做证据分级（默认延后 vMTB）。
- **不把 `treatment_lines line:0` 当缺陷**：`line:0` = 新辅助/围手术期，schema 合法（如需仅"校验 line:0 确为新辅助，看 `intent` 字段"）。
- **不重写 AGENTS.md 模板**：模板与填充逻辑已存在，仅验证/修残留。
- **不动本地孪生仓 / 不提其他 OCR 引擎 / 不重构桶编号体系 / 不做 MTB·治疗推理 / 不另开 fix 分支**。

---

## 6. Design Considerations

- **门的位置**：确定性门保持"Phase 2 之后、交付之前"（`validate_structured_outputs.py` 为总验收门，已内含 `pii_rescan.py`）。US-001/002/010 扩展该总门；US-003 为 Phase 2.5 语义门，其 CRITICAL 必须反馈到渲染（防"计算但断连"）。
- **确定性 vs 语义分工**：PII 结构标识 / flag·区间·丢值 / 列错位 → 确定性脚本（无关键词表）；模糊人名 PII 与"转写是否忠实" → sub-skill/Agent。互为冗余安全网。
- **患者可见层是硬边界**：sidecar MD 是唯一下游明文边界（timeline/case_text/profile/HTML 只读 MD 不回读源）；坏值/PII 一旦入 MD/JSON 即全链泄漏，故门须前置且零容忍。

---

## 7. Technical Considerations

- **目标文件**（`skills/cancer-buddy-organize/`，附已核实 file:line）：
  - `scripts/pii_rescan.py`（330 行；`collect_sidecars:254-273` 仅 sidecar、`scan_sidecar:234` 跳头块、`_STANDALONE:137-145` 缺数字模式）→ US-001/007/010
  - `scripts/validate_structured_outputs.py`（450 行；:6-9 无医学判断）→ US-002 新增数值层 + US-001 PII 门 FAIL 传导
  - `scripts/render_html_template.py`（不剥注释；`find_unrendered:285-287` 仅检测；provenance 注释 :295 保留）→ US-017 注释剥离、US-003 坏值抑制
  - `references/organizer-prompt-phase1-ocr.md`（§2.2a 禁平滑未约束表结构；§2.3 整文件置信；§2.4 签名 mask）→ US-005/007
  - `references/organizer-prompt-phase2-synthesis.md`（706 行；`cross_doc_contradiction:475`；`cross_patient_name_collision:484-512`；patient_dir 示例 :250）→ US-004/006/012/014/016
  - `references/schemas/`：`molecular`（evidence_tier :26、tmb.unit :68）、`treatment_lines`（line minimum:0 :20）、`labs`（flag :32）、`patient_summary`（status 拆分 :47-70）、`source_inventory`（patient_dir :11、raw_path 相对 :24）→ US-012/013/014/016
  - `references/templates/agents-md.template.md`（6.4KB，已富）+ `SKILL.md` Step 13（:183-200）→ US-008；`SKILL.md:99`（mkdir 14 桶）→ US-009
  - 新增 `references/organizer-prompt-phase2_5-faithfulness.md`（US-003）
- **回归夹具**：`PT-6969D8D0A8`（手术日冲突、空手术桶、标本号不一致、OCR caveat 缺失）+ `PT-78FBCE6E0F`（CEA 列错位、肾功能丢失、王国洪/邮箱/yosean 泄漏、散乱签名未脱敏、TMB 单位臆造）作为门的负向测试夹具。`line:0` 不入缺陷清单（schema 合法）。
- **SKILL.md / 文档同步**：新增门/阶段时 SKILL.md 仅加操作化指令（重 LLM 步骤明确要求 sub-skill/Agent）；每个 PR 同步更新 README/CHANGELOG/SKILL.md。

---

## 8. Success Metrics

- **M1**：两份回归夹具经扩展验收门 PII 残留 = **0**（`王国洪`/`452858265@qq.com`/`yosean 父亲`/`刘俊宝` 全归零）。
- **M2**：CEA 列错位、肌酐/尿酸丢失在数值门 + 忠实度门 **100% 被拦截**，不进 `labs.json`/`longitudinal_observations.json`/HTML。
- **M3**：手术日冲突 100% 产 review_flag；患者可见层无未标注被裁决值；`2023-01-02` 不再出现。
- **M4**：当前 HEAD 在**含名 + 全格式**输入上：修复前**实证复现**跨 surface 泄漏，修复后归零；非 HEIC 0 丢档，P0 门全触发。
- **M5**：黄金回归覆盖 ≥2 患者 ≥2 癌种，一条命令复跑全绿。
- **M6**：同 schema_version 跨运行键集 100% 一致；`patient_dir`/`original_path` 0 绝对路径泄漏。

---

## 9. Decisions & Assumptions（默认决策，评审时可推翻）

- **D1**（US-003 后端）：忠实度复核用当前调用的 LLM 模型做二次校验（如在 codex 中即 GPT-5.5）。
- **D2**（US-012 证据分级）：默认**延后到 vMTB**；organize 仅保留 `evidence_tier=null` 的 schema 合法性卫生，不在 organize 阶段联网查 CIViC/OncoKB。
- **D3**（US-011 形态）：安全导出实现为 organize 主流程 `--export-share` 开关（单一入口，复用既有验收门）。
- **D4**（US-018 第二夹具）：从候选清单选一份非 CRC 档案；选定前先 1 行核实各候选癌种（唯一待定项，不阻塞 P0 开工）。
- **D5**（仓库放置）：提交前将 `tasks/` 纳入 `.gitignore` 或迁私有位置。

---

## 10. Execution Sequencing（建议执行顺序）

1. **US-005（Phase-1 表对齐 + 分块置信）先行**——CEA 列错位的上游根因；上游不修，US-002/003 只能追症状。
2. **US-001（跨 surface PII + deny-list）并行**——独立、患者安全最高杠杆。
3. **US-002（数值不变量）→ US-003（忠实度，结果接入渲染）**——US-003 依赖 US-002 结构 flag 与 US-005 对齐表。
4. **US-004（裁决 + 标注）**——依赖已存在的 review_flags 基建。
5. **P1**：US-006、US-007、US-009、US-010、US-011。
6. **P2**：US-008、US-012、US-013、US-014、US-015、US-016、US-017。
7. **US-018 作为跨切证明门最后跑**——但**含名夹具须早写**，以便在 US-001 落地前于 HEAD 上实证复现泄漏。
8. **提交前**：处理 `tasks/` 仓库放置（D5）。
