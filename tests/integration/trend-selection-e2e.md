# 段D「关键趋势」选取 — LLM-in-the-loop E2E 记录

验证 `references/cancer-trend-markers.md`（69 癌种表）+ `case-summary-html-prompt.md` §关键趋势
分层规则在真实脚本链上的端到端效果。选取由 LLM（段D 数据产出者）依规则执行——本记录中由
执行者充当该产出者，**据实按规则应用、未为通过断言反推 fixture**。

- 分支：`feat/trend-marker-selection`
- 脚本链（每 case 全 exit 0）：`compute_version_delta.py` → `compute_sparklines.py --data … --longitudinal … --labs …` → `render_html_template.py` → `validate_case_summary_html.py`
- 反造假门：`compute_sparklines.py` 校验每个画出的 (metric,value) 在 longitudinal/labs 有同值背书（exit 3 拦造假点）。

---

## Layer 1 — 确定性渲染回归（既有 e2e + 新增 4 图上界）

`bash tests/integration/case-summary-trend-e2e.sh` → **13 passed, 0 failed, exit 0**，wall-time ≈ 1.0s。

- Case A/B/C/D 既有：CRC 3 点 CEA hero+delta、NSCLC 首版无 delta、空数据占位、卵巢双图（2 图并排）。
- **新增 Case E（本任务）**：卵巢铂耐药 4 图（CA-125 / HE4 / CEA / LDH），每点由 longitudinal 背书，
  过完整脚本链渲染 **4 张 `trend-hero` 并排 + 全部 shape/print 不变量**（exit 0）。证明模板/校验器在
  新上界（2–4 图，旧为 1–3）不崩。脚本层对图数**无硬 cap**（2–4 是 LLM 软规则），模板按 LOOP 渲染任意张数。

---

## Layer 2 — 分层选取（充当段D产出者，2 癌种）

### Case A — PDAC（有规范标志物）

- **输入摘要**：胰腺导管腺癌 IV 期、肝转移、分泌型（CA19-9 阳性）；一线 GnP 进展→二线 mFOLFIRINOX。
  - `longitudinal`：**CA19-9 4 时间点**（620→850→380→120，跨 2026-01 二线切换）+ **ALT 6 时间点**（稳定正常 ~26–33，故意比 CA19-9 时间点**更多**，测「时间点多者胜」不得压过癌种规范标志物）。
  - `labs`：CA19-9(H)、ALT(正常)、HGB(L)。
- **规则应用**：PDAC 表 primary=CA19-9；患者为分泌型（caveat「Lewis 阴性者不表达→据个案不选」不触发）→
  Tier1 CA19-9 有 ≥2 点 → **必选 hero**。ALT 虽时间点更多，但平稳/正常/非疗效相关 → **降级**至 lab_trends，不进 hero。
- **结果 `trend_charts[].metric`** = `['CA19-9']`（hero 计 1；ALT/HGB 落 lab_trends）。
- **产物**：`病情简要总结.html`（14534 bytes），链 wall-time ≈ 0.20s，全 exit 0（trend charts=1, lab_trend rows=3）。
- **断言**：`A OK ['CA19-9']` ✅ — 癌种规范 marker 被选为 hero，未被更高时间点的旁路 lab 挤掉。

### Case B — 皮肤黑色素瘤（无规范标志物）

- **输入摘要**：皮肤黑色素瘤 IV 期(M1c)、BRAF V600E、一线免疫治疗中。
  - `longitudinal`：LDH 3 点（210/225/205，**参考区间 120–250 内、平稳**）+ ALT 2 点（正常）。
  - `labs`：LDH(正常)、ALT(正常)。**无任何规范血清疗效标志物**。
- **规则应用**：melanoma-cutaneous 表 primary=`—`（caveat「无公认血清疗效标志物；LDH 仅 M1 分期/预后」）→
  **不硬凑 hero**。LDH 依 caveat 属分期/预后指标而非疗效标志物，且本例平稳正常、未驱动任何决策 →
  按「平稳/非疗效相关 → 不进 hero，落 lab_trends」降级。无其它 Tier2 决策驱动指标 → `trend_charts=[]`。
- **结果 `trend_charts[].metric`** = `[]`（LDH、ALT 落 lab_trends；`关键趋势`段占位 `trend-none` 正常渲染，段未删）。
- **产物**：`病情简要总结.html`（11891 bytes），链 wall-time ≈ 0.19s，全 exit 0（trend charts=0, lab_trend rows=2）；
  `trend-none` 占位出现 1 次、`关键趋势` h2 出现（段保留）。
- **断言**：`B OK []` ✅ — 规则未为 `—` 癌种硬凑 CA19-9/CEA/AFP/PSA/CA-125 等规范 marker。

> 说明（据实标注）：Case B 本可走「仅 Tier2 患者特异指标」路径（如 LDH 升逼近决策阈值时画一张 Tier2 图）。
> 本例 LDH 平稳且在正常区间、未驱动决策，故据实降级为 `[]`——这是对「反滥用/无标志物 fallback」
> 更强的证明（连 Tier2 都不牵强凑）。

---

## 产物路径（实际）

- Layer 1 测试：`tests/integration/case-summary-trend-e2e.sh`（新增 Case E 4 图）
- Case A HTML：`<scratchpad>/caseA/病情简要总结.html`（14534 bytes）+ 输入 profile/longitudinal/labs + `.case_summary_data.json`
- Case B HTML：`<scratchpad>/caseB/病情简要总结.html`（11891 bytes）+ 同上
  （scratchpad 为 session 临时目录；两 case 的 `.case_summary_data.json`/输入 json 已在链中逐一验证）

## 结论

- Layer 1：**pass**（13/13，含 4 图上界）。
- Case A：CA19-9 被选为 hero，未被 6 点 ALT 挤掉 → **pass**。
- Case B：`—` 癌种未硬凑规范 marker，段占位保留 → **pass**。
