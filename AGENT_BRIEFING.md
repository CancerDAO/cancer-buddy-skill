# Cancer Buddy Skill — Agent Briefing

> 给下一个 agent 的完整交接文档。读完这份即可无缝接手。
> 最后更新：2026-06-20

---

## 一、这是什么

**Cancer Buddy** 是一套帮助癌症患者整理病历、理解病情、准备就医的 AI skill 集合。
核心 skill 是 `cancer-buddy-organize`，把患者提供的一堆原始文件（JPG/PDF/DOCX）整理成结构化数据，供下游 skill 消费。

**Skill 根目录**：`D:\Desktop\cancer-buddy-skill\`

```
cancer-buddy-skill/
├── skills/
│   ├── cancer-buddy-organize/      ← 核心，本次主要工作
│   │   ├── SKILL.md                ← 总调度流程（必读）
│   │   └── references/
│   │       ├── organizer-prompt-phase1-ocr.md
│   │       ├── organizer-prompt-phase2-synthesis.md
│   │       └── organizer-prompt-phase3-evaluation.md
│   ├── cancer-buddy-education/
│   ├── cancer-buddy-find-care/
│   ├── cancer-buddy-second-opinion/
│   └── ... (其他 companion skills)
├── references/                     ← 全局引用（schema、模板等）
│   ├── report-data-schema.md       ← report_data.json 的完整字段规范
│   ├── case-summary-template.md
│   ├── formatting-spec.md
│   └── patient-profile-schema.md
└── scripts/
    └── report_template.py          ← 生成 Word 报告的 Python 脚本
```

**患者数据根目录**：`C:\Users\傅天麟\CancerDAO\patients\`

已有患者目录：
- `宫颈癌_2026-01_db5b/` — 程红鲜（CHX），本次完整跑了三阶段
- `乙状结肠腺癌_2025-09_a444/`
- `HZB_CRC2025/`

---

## 二、cancer-buddy-organize 核心流程

### 整体架构：三阶段 fan-out/reduce

```
用户提供文件夹
    │
    ▼
[Step 1] 解析输入路径
[Step 1b] 语言检测（output_language）
[Step 2] 规划切片（≤15 文件/worker）
[Step 3] 并行 Phase 1 OCR Workers（subagent fan-out）
[Step 4] 续跑 loop（continuation_needed 为 true 时）
[Step 5] 询问格式 + 语言（语言未确定时合并询问）
[Step 5b] Phase 2 Synthesis Worker（单 subagent）
[Step 6] 覆盖率重试（coverage_complete: false 时）
[Step 7] 验证输出
[Step 8] 展示用途门控 + 行动指引
[Step 9] Phase 3 质量评审（必经，QA Worker）
[Step 10] 展示 review_summary.md（强制）
[Step 11] 展示 review_flags（强制）
[Step 12] 展示 profile card
```

### Phase 1 — OCR Worker（并行）

- Prompt：`references/organizer-prompt-phase1-ocr.md`
- 每 worker ≤15 文件；并行 dispatch（单条消息多 Agent tool call）
- 输出：`ocr/<文件名>.md`（含 SOURCE/CONFIDENCE 头）
- **严格不写** INDEX.md / profile.json 等（Phase 2 的责任）
- 反锚定原则：每个文件独立 OCR，不跨文件"平滑"数值

### Phase 2 — Synthesis Worker（单个）

- Prompt：`references/organizer-prompt-phase2-synthesis.md`
- 关键参数：`patient_dir`、`phase1_summary`、`output_format`、`output_language`
- 执行步骤（大）：
  1. 语义重命名文件（`.rename_plan.json` → bash 原子重命名）
  2. 重命名 patient_dir 为 `<cancer>_<YYYY-MM>_<hash4>`
  3. 写 INDEX.md / timeline.md / case_text.md / profile.json / readiness.json
  4. §4.6 review_flags 审计
  5. 写 review_flags.md（非空时）+ review_summary.md（始终）
  6. 生成 **report_data.json**（详见 §三）
  7. 调用 `report_template.py` 生成 `.docx`（docx 格式时）
  8. 写 `case_summary_brief.md` + `case_summary_detailed.md`
  9. 写 `report_data.json["ui"]`（本地化 UI 字符串，供 report_template.py 使用）
- 返回 JSON（含 patient_dir 重命名后路径）

### Phase 3 — 质量评审 Worker（必经）

- Prompt：`references/organizer-prompt-phase3-evaluation.md`
- **例外跳过**：`basic_summary == "not_ready"` 或本次是定向重合成后的 retry
- 双轨评审：
  - **Track A 完整度**：diagnosis.stage / histology / primary_site / molecular(high) / treatment / gaps.critical.action_detail
  - **Track B 可用度**：时间线合理 / 分期-转移一致 / next_steps >20字 / action_detail 含机构 / 叙述内部一致
- 根因分类：`doc_missing` → patient_action | `ocr_failure` → re_ocr | `synthesis_gap` → re_synthesis
- 输出：`qa_evaluation.json` + （可选）`待补充材料清单.md`
- **deliver_report 永远为 true**，不阻断报告交付
- re_synthesis_fields 去重（同字段只出现一次）

---

## 三、report_data.json 结构（关键字段）

```json
{
  "patient": { "name": "...", "age": ..., "sex": "..." },
  "diagnosis": {
    "date": "...", "primary_site": "...", "histology": "...",
    "stage": "...", "metastasis": "...", "initial_or_recurrence": "..."
  },
  "molecular": [{ "item": "...", "result": "...", "priority": "high/medium/low" }],
  "imaging": { "items": [...], "note": "..." },
  "labs": [{
    "date": "YYYY-MM-DD", "category": "...", "item": "...",
    "base_item": "...",        ← 趋势图分组用，不含时间修饰词
    "value": "...", "reference": "...", "flag": "normal/high/low", "note": "..."
  }],
  "trend_events": [{ "date": "...", "label": "..." }],  ← 治疗干预点（非诊断事件）
  "treatment": { "lines": [...], "note": "..." },
  "pathway": { "current": "...", "next_steps": "...", "rationale": "..." },
  "gaps": {
    "critical": [{ "item": "...", "action_detail": "去哪里/找谁/做什么" }],
    "recommended": [...], "covered": [...]
  },
  "review_flags": [{ "id": "RF-001", "severity": "red/yellow", ... }],
  "sources": [...],
  "ui": {                      ← 本地化 UI 字符串（Phase 2 按 output_language 生成）
    "cover_brief_title": "...", "h_patient_id": "...", "s1": "...",
    "kv_date": "...", "disclaimer": "...含{gen}/{fn}/{fr}/{fy}/{fg}占位符..."
  }
}
```

---

## 四、report_template.py 关键设计

**路径**：`D:\Desktop\cancer-buddy-skill\scripts\report_template.py`
**Bash 路径**：`/sessions/.../mnt/cancer-buddy-skill/scripts/report_template.py`

### 用法

```bash
python report_template.py <report_data.json> <output.docx> --type brief|detailed
python report_template.py <report_data.json> <output.docx> --type brief --md-patch <path/to/brief.md>
```

`--md-patch`：同时生成快照图 PNG（`charts/labs_snapshot_brief.png`）并插入 .md 文件。

### 关键函数

| 函数 | 作用 |
|------|------|
| `labs_trend_charts(doc, labs)` | 多时间点折线趋势图（≥2 个时间点才生成） |
| `labs_snapshot_chart(doc, labs, png_save_path=None)` | 单时间点快照横向点图（始终可生成） |
| `build_brief(data, path)` | 简版 Word 报告 |
| `build_detailed(data, path)` | 详版 Word 报告 |
| `_u(key)` | 读取 `data["ui"][key]`，fallback 中文默认值 |

### 趋势图 vs 快照图逻辑

- 同一 `base_item` 有 ≥2 个不同日期 → **趋势图**（折线，显示变化趋势）
- 所有指标都只有 1 个时间点 → **快照图**（横向点图，显示当前值 vs 参考区间）
- 两者不互斥：多时间点指标出趋势图，单点指标出快照图

### i18n 设计

**不用硬编码字典**，UI 字符串由 Phase 2 的 AI 按 `output_language` 生成后写入 `report_data.json["ui"]`。`report_template.py` 通过 `_u(key)` 读取，支持任意语言，代码零改动。

---

## 五、安全约束（必须遵守）

1. **不展示数字分数或字母等级**（A/B/C/D/F 或 0-100 分）给用户
2. **deliver_report 永远为 true**：无论评审结果如何，始终交付报告
3. **低覆盖度不降级**：缺失字段转化为具体行动指引，不拒绝生成报告
4. **medical 文档无 emoji**：用颜色/加粗/下划线代替
5. **泛化 skill 文件不含患者数据**：所有 `references/` 里的文件零患者信息
6. **anti-anchoring（Phase 1）**：每个 OCR worker 只看自己的切片，不跨文件平滑数值

---

## 六、本次会话主要改动

### 新增文件

| 文件 | 内容 |
|------|------|
| `skills/cancer-buddy-organize/references/organizer-prompt-phase3-evaluation.md` | Phase 3 双轨评审 worker prompt（v2.0，替换旧的 adversarial 版本） |

### 修改文件

#### `SKILL.md`
- Step 5：格式询问改为 docx/md/pdf 三选一
- Step 8：用途门控展示逻辑，禁止展示等级分数
- Step 9（重写）：Phase 3 改为**必经步骤**，不再条件触发；新增双轨流程、re_synthesis/re_ocr/patient_action 三路恢复；deliver_report 永远为 true；max retry = 1
- Step 1b（新增）：语言检测，`output_language` 传入 Phase 2

#### `references/organizer-prompt-phase2-synthesis.md`
- 新增 `output_language` 输入参数
- Step 6.0：按 `output_language` 写所有内容，同时输出 `report_data.json["ui"]` 本地化字段

#### `scripts/report_template.py`
- 新增 `labs_snapshot_chart()`：单时间点快照图
- `build_brief` / `build_detailed` 调用快照图
- 新增 `--md-patch` CLI：生成 PNG 并 patch .md 文件
- 新增 `_u()` 函数 + `_UI_DEFAULTS`：从 `data["ui"]` 读 UI 字符串，fallback 中文
- `build_brief` / `build_detailed` 所有章节标题改用 `_u()`

#### `references/report-data-schema.md`
- 新增 `base_item` 字段说明（趋势图分组键）
- 新增 `trend_events[]`（治疗干预点，仅限治疗类事件）
- 新增 `qa_evaluation.json` 输出格式（schema_version: "2"）
- 新增 `ui` 字段说明

### 已废弃（用户手动删除）

- `skills/cancer-buddy-organize/references/organizer-prompt-phase3-adversarial.md`
  → 被 `organizer-prompt-phase3-evaluation.md` 取代，需从 Windows 资源管理器手动删除

---

## 七、已运行的患者记录

### 程红鲜（CHX）— 宫颈癌_2026-01_db5b

**输入**：`D:\Desktop\Student Helper\0406-0412 OCR检测报告准确性\检查检验\病例检查检验-傅天麟\CHX`（5 张检验单 JPG）

**结果**：
- Phase 1：5 份 OCR sidecar（全为 2026-01-05 西北妇女儿童医院检验报告）
- Phase 2：report_data.json（12 labs，4 molecular），case_summary_brief/detailed .docx + .md
- Phase 3：Track A 3 个 gap（全为 doc_missing：无病理/影像/基因报告），Track B pass，已生成 待补充材料清单.md
- 关键发现：SCC 15.00 ng/mL（参考0-3，升高5倍）— RF-001 red flag

**文件位置**：`C:\Users\傅天麟\CancerDAO\patients\宫颈癌_2026-01_db5b\`

---

## 八、NTFS 挂载注意事项

在 bash 环境里操作 Windows 挂载文件时：

- **不要直接 `rm`**：NTFS 挂载的文件无法从 bash 侧删除（Operation not permitted）
- **大文件写入会截断**：直接通过 Edit/Write 工具写大型 Python 文件（>1000行）可能截断。**正确做法**：在 `/tmp/` 生成完整文件，验证语法后 `cp` 回挂载目录
- **路径映射**：
  - `D:\Desktop\cancer-buddy-skill\` → `/sessions/vibrant-blissful-pasteur/mnt/cancer-buddy-skill/`
  - `C:\Users\傅天麟\CancerDAO\` → `/sessions/vibrant-blissful-pasteur/mnt/CancerDAO/`

---

## 九、下一步可能的工作

1. **删除废弃文件**：从 Windows 删除 `organizer-prompt-phase3-adversarial.md`
2. **其他患者重跑**：ZXY 和 HZB 患者可以用更新后的 skill（含 Phase 3 + 快照图）重新生成报告
3. **report-data-schema.md 更新**：加入 `ui` 字段的正式 schema 文档
4. **测试 fixture 更新**：3 个 fixture（A/B/C）是在 Phase 3 改动前创建的，可以重跑验证新版 Phase 3
