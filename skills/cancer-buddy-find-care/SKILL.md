---
name: cancer-buddy-find-care
description: "查找能做特定治疗资源的医院、专科医生和临床试验。**只做资源发现，不做临床判断**。典型问题：哪家医院能做 MTB（分子肿瘤委员会）？我这个癌种谁是国内做得最好的医生？我能去的城市里有没有 X 靶点的临床试验？这个免疫治疗副作用问题哪里看更专业？输入：profile.json（癌种/分期/分子分型/所在城市/能否跨城/经济条件）+ 一个具体诉求。输出：排序后的资源短名单（含挂号路径、地址、联系方式、匹配理由）。Triggers on: 找医院, 哪家医院能做 MTB, 哪个医生擅长, 临床试验在哪招, 异地就医, 推荐医生, 找专家, 哪儿能做 NGS, 找肿瘤多学科会诊, MDT 哪里有, 找试验中心."
---

# cancer-buddy-find-care

帮你找资源，不替你做判断。

「找医院 / 找医生 / 找临床试验中心」是患者和家属反复要做的事，但靠社交媒体口碑、四处问朋友、搜出一堆软文很难得到结构化的答案。这个 skill 把它做成一次可执行的并行调研：先理解你的具体诉求，分派多个子 agent 并行去查权威源，再汇总成一份带匹配理由和挂号路径的短名单。

## When to use

触发场景（用户说类似这些话）：
- "我妈非小细胞肺癌 EGFR 19del，杭州/上海有哪家医院的 MTB 能接？"
- "胰腺癌晚期，国内谁做得最好？"
- "我这个 HER2 低表达乳腺癌有没有 DXd 相关的临床试验在招？北京可以"
- "免疫治疗后出现心肌炎，找哪里看？"
- "想做 NGS 全外显子，哪家医院靠谱、需要怎么挂号？"

## What this skill is NOT

**这不是 MTB，不是治疗方案推荐，不是临床判断。**

- 不评估"这个方案适不适合你" → 那是 cancer-buddy-pro-skill / 主诊医生
- 不解读基因报告的临床意义 → 同上
- 不判断"该不该换线" → 同上
- 不做 criterion 级（入排标准逐条）的患者×试验匹配 → 那是配套的 [`clinical-trial-matching`](https://github.com/CancerDAO/clinical-trial-matching-skill) skill
- 不替代"挂号 → 看诊 → 主诊医生评估"这条路

我们做的就是：**告诉你哪里有人能做这件事**。

## Locale (i18n)

读共享 `../../references/i18n.md`。流程开始时：

1. 读 `patients/<patient_code>/profile.json` 的 `locale` 字段。有则直接复用，**不重新检测**——保证整个患者旅程脚手架语言一致。
2. 无 profile / `locale` 为 null → 从用户当前对话语言检测 BCP-47 locale（en / fr / es / zh / …），写回 `profile.json.locale`（无 profile 时由后续 organize 落地，本 skill 检测到则先写）。
3. 用户显式要求换语言（"answer me in English" / "用中文"）→ 更新 `profile.json.locale` 并照办，覆盖自动检测。

**本地化脚手架，绝不动临床实体**：所有患者可见输出（QUERY.md、SHORTLIST.md、顶层结论、匹配理由、挂号路径、限制项、路由话术、diff/确认话术、免责声明、日期格式）按 locale 出；药名 / 基因 / 变异 / TNM / 分期 / 数值单位 / 量表标准名 / 注册号（NCT/ChiCTR）/ 机构原名一律 **verbatim 原文逐字**，禁止翻译（误译=医疗风险，见 `../../references/safety-guardrails.md` → 临床实体禁译）。机构名可在原名旁加 locale 通俗注释，不替换原名。

派发 subagent 时在 prompt 里写明 **"Output all patient-visible scaffold/narrative prose in `<locale>`; keep clinical entities (drugs / genes / variants / TNM / numbers+units / registry IDs / institution names) verbatim per `../../references/i18n.md` §4."**

## Preflight

### Role check

- `role=patient` 或 `role=caregiver`：正常工作
- `role=family`（远亲/朋友）：refuse + 引导回主照护者
  - 输出（**按 locale 出**，下文 zh 为 `zh` locale 的措辞，其它 locale 渲染同义文案）：`找医院/医生/试验涉及实际就医操作，需要患者本人或主照护者来推进。我可以陪你做的是把搜到的信息整理给 Ta 看。`

### Profile completeness

调研前先确认信息齐全。**病历侧**字段从 organize 产出读（`cancer_buddy_profile_v3` 嵌套形态 + 结构化 JSON）；**query 侧**字段从对话向用户收集、落进 Step-1 的 `QUERY.md`（它们**不是** profile.json 字段，别去 profile.json 找、更别因其缺失而阻断）。

**病历侧（organize 产出）：**

| 字段 | 来源文件 | 必需？ | 用途 |
|---|---|---|---|
| `summary.primary` | `profile.json` | 必需 | 决定查哪些专科榜单 |
| `summary.stage` | `profile.json` | 推荐 | 影响 MTB / 试验匹配优先级 |
| drivers（基因 / 变异） | `molecular.json` | MTB/试验任务必需 | 没有就先去 `organize` 整理 / 做 NGS |

**query 侧（向用户收集 → `QUERY.md`）：**

| 字段（→ QUERY.md） | 必需？ | 用途 |
|---|---|---|
| 当前城市 + 可接受范围（`geo`） | 必需 | 否则全国/全球范围太散 |
| 预算档位（`constraints.budget`） | 推荐 | 影响公立/私立/海外比例 |
| 异地医保参保地 | 推荐 | 异地医保备案影响推荐 |

**病历侧字段不全时**：不要让 subagent 瞎跑。先回过头让用户补齐（或先去 `organize` 整理病历 / 做 NGS），再调研。query 侧字段直接在对话里问用户。

## Core workflow

### Step 1 — Clarify the ask

把用户那句话翻译成一个**可调研的查询**，写到 `patients/<patient_code>/reports/find-care/<query-slug>/QUERY.md`：

```yaml
query_type: hospital | doctor | trial_site | combined
clinical_target:
  cancer_type: 非小细胞肺癌
  subtype: 腺癌
  stage: IV
  molecular: EGFR 19del, post-Osimertinib progression
  service_needed: MTB（分子肿瘤委员会）会诊
geo:
  primary_city: 杭州
  acceptable_cities: [上海, 南京]
  cross_border: false
constraints:
  budget: 公立可承受 / 不考虑海外
  timing: 2 周内
patient_profile_ref: patients/PT-XXXX/profile.json
```

不确定的字段当面问用户，**别让 subagent 替你猜**。问用户的话术按 locale 出。

> QUERY.md 的 YAML **键（key）是语言无关的稳定结构**，不本地化；值里的临床实体（cancer_type / molecular / stage…）保持病历原文逐字，叙事性自由文本（service_needed 描述、constraints 说明）按 locale 出。

### Step 2 — Plan parallel investigations

根据 `query_type` 决定要派哪些 subagent。每条调研路线一个 subagent，互不依赖。

**典型分派：**

| query_type | Subagent A | Subagent B | Subagent C | Subagent D |
|---|---|---|---|---|
| hospital | 国家癌症中心 / 复旦版排行 → 拿到该癌种 top 中心 | 各 top 中心官网/新闻：是否设 MTB / MDT，参与频率，团队构成 | 好大夫在线该癌种 top 医生所属医院（反向找院） | （可选）患者社群讨论：实际可及性、就诊体验 |
| doctor | 好大夫在线 / 微医 ：该癌种排名医生 + 患者口碑 + 出诊医院 | Pubmed / Google Scholar：该医生近 5 年发表是否对口 | 学会理事/委员名单（CSCO / CACA 专委会）反查行业地位 | 院官网医生介绍 + 出诊安排 |
| trial_site | ChiCTR：搜目标分子型 + 癌种 + 状态=招募中 | ClinicalTrials.gov：同上，限定 location=China 或 acceptable countries | 主要研究者所属医院 + 该院 GCP 中心信息 | 公司试验注册页（如有 sponsor 是大厂） |
| combined | 上述按需混合，控制在 4–6 个 subagent | | | |

### Step 3 — Dispatch (并行)

每个 subagent 用 Agent tool 启动，prompt 模板：

```
任务：<具体目标，例如：查国家癌症中心 2024 版肺癌专科声誉排名 top 10 中文医院列表，每家附 location 和官网 URL>

约束：
- **必须加载 web-access skill 并遵循指引**
- 数据源限定一手（机构官网、官方榜单、注册库），不接受社交媒体软文作为唯一证据
- 如果遇到反爬或登录墙，按 web-access 指引处理（CDP 直连用户已登录的 Chrome）
- 单个 subagent 最多耗时 5 分钟，超时返回"未完成 + 已采集到的部分"

输出格式（JSON 写到 patients/<patient_code>/reports/find-care/<query-slug>/raw/<subagent-name>.json）：
{
  "source_type": "ranking|institution_page|registry|profile_page",
  "source_url": "...",
  "fetched_at": "ISO8601",
  "items": [
    {"name": "...", "url": "...", "evidence_quote": "原文片段", "fields": {...}}
  ],
  "notes": "执行中遇到的问题、未覆盖的子目标"
}
```

**并行而非串行**：如果一次性派 4 个 subagent，主 agent 只在 prompt 里说要什么，**不指定 web-access 内部步骤**——每个 subagent 自己判断该用 WebSearch 还是 CDP。

### Step 4 — Merge & score

收到所有 subagent 的 JSON，主 agent 做：

1. **De-duplicate** — 同一家医院/医生在多个源出现，合并条目，证据列表叠加
2. **Score by fit** — 按 [references/scoring-rubric.md](references/scoring-rubric.md) 的维度打分
3. **Filter** — 删除明显不匹配的（不在地理范围 / 不接此癌种 / 试验已停招）
4. **Rank** — 按总分排序，输出 top 5–8

打分维度（详细权重见 rubric）：
- 服务匹配度（是否真做 MTB / 是否专攻该癌种）
- 地理可及性（是否在用户接受的城市范围）
- 证据强度（一手源 > 二手源；多源互证 > 单源）
- 可达性（挂号难度、是否需要转诊、医保备案是否复杂）
- （仅医生类）实际出诊频率 + 患者反馈量

### Step 5 — Write shortlist

写到 `patients/<patient_code>/reports/find-care/<query-slug>/SHORTLIST.md`，按 [references/output-template.md](references/output-template.md)。模板的脚手架字符串（section 标题 / 字段标签 / 匹配度档位词 / 免责声明）查 locale 字符串表渲染；临床实体逐字。

每条目必含：
- 名称（医院/医生/试验编号）
- 匹配度（高/中/低 + 一句话理由，**不是 "我推荐"**）
- 关键事实（位置 / 团队 / 频率 / 试验状态）
- **挂号或联系路径**（具体到平台 + 操作步骤）
- 证据来源 URL 列表
- 潜在风险/限制（费用 / 等候期 / 异地医保 / 试验排除标准）

末尾**必须**有（**按 locale 出**；下文均为 `zh` locale 示例措辞，其它 locale 渲染同义文案，临床实体与触发命令字面量逐字不译）：

```
> 这是资源发现的结果，不是医学推荐。是否真的合适你（或你家人）的具体情况，需要带着这份清单和你的主诊医生讨论，或挂号后由对方医生评估。
```

**当短名单里包含临床试验**（NCT / ChiCTR 编号），追加 next-step 路由 + 按需安装 companion。

给用户的话术（追加在 SHORTLIST 末尾，**按 locale 出**；NCT/ChiCTR 编号、命令字面量逐字不译）：

```
> 这份名单只是把"在招"的试验筛选了一遍，不等于你符合入排标准。要做 patient × trial 的 criterion 级（入排标准逐条 CoT 评估）匹配并出可审计的决策报告，跑配套的 [`clinical-trial-matching`](https://github.com/CancerDAO/clinical-trial-matching-skill) skill。
>
> 一句话触发：`给 patients/<patient_code> 跑临床试验匹配`
```

**搭子内部逻辑**（用户说"跑临床试验匹配 / criterion 级匹配 / 入排逐条评估 / shortlist trials" 时）：

1. **检查 companion 是否已装**：
   ```bash
   if [ -d "$HOME/.claude/skills/clinical-trial-matching" ] || [ -d ".claude/skills/clinical-trial-matching" ]; then
     echo "installed"
   else
     echo "missing"
   fi
   ```
2. **未装 → 自动拉 CancerDAO 开源 companion**（无需用户先 `npx skills add`），先告知用户一句（**按 locale 出**，命令与 repo URL 逐字不译）：
   > 我先把 [`clinical-trial-matching`](https://github.com/CancerDAO/clinical-trial-matching-skill) companion 装上（CancerDAO 开源 skill，约 3 秒），装完直接跑匹配。
   ```bash
   npx skills add CancerDAO/clinical-trial-matching-skill -g --all
   ```
   失败时（无网络 / npx 不可用）才回退到提示用户手装：`npx skills add CancerDAO/clinical-trial-matching-skill -g --all`，repo: https://github.com/CancerDAO/clinical-trial-matching-skill
3. **调用 companion**：通过 Skill 工具触发 `clinical-trial-matching`，传 `patients/<patient_code>/profile.json` + 短名单中的 NCT/ChiCTR 编号集合。
4. **`vmtb-skill` 不走自动安装**——它还没开源。被用户问到时只引导手装路径（见 INSTALL.md），不要尝试 `npx skills add`。

## Role behavior

- **Role = patient**：第二人称 "你"，挂号路径以患者本人操作为准
- **Role = caregiver**：第二人称 "你"，但任务理解为帮家人办，挂号路径以照护者操作为准（包括异地医保备案、协助身份证明等）
- **Role = family**：refuse（见 Preflight）

## Disclosure 行为

如果 `profile.json.disclosure_state == "suppressed"` 且 `role=patient`：
- 患者可能还不完全知道分期/分子情况，但"找做 X 的医院" 这个动作本身已经说明 ta 知道在找什么
- 正常执行，但 SHORTLIST 里**避免**渲染"晚期/IV/进展后"等可能加重情绪的表述，用临床中性语
- 详见 `../../references/disclosure-behavior.md`

## Output

写在：

```
patients/<patient_code>/reports/find-care/<query-slug>/
  ├── QUERY.md              # Step 1 的查询定义
  ├── SHORTLIST.md          # 最终给用户的短名单
  └── raw/
      ├── subagent-A.json
      ├── subagent-B.json
      └── ...
```

`<query-slug>` 形如 `mtb-nsclc-egfr-hangzhou-2026-04`，便于翻历史。

## Safety

- **绝不**承诺"这家医院能治好"或"这位医生方案最好"
- **绝不**把 NGS 报告解读、用药建议、剂量调整写到 SHORTLIST 里——遇到这类需求路由回 pro-skill 或主诊医生
- **绝不**鼓励通过非正规渠道（黄牛、付费内推）挂号；可以提示"号源紧张时通过院方互联网医院 / 转诊门诊更稳"
- 临床试验匹配 **必须**带一句"匹配不等于符合入组，具体以研究中心预筛为准"（见 safety-guardrails.md）
- 海外/跨境推荐时同步提示费用量级、签证、医疗记录跨境运输（可路由到 cancer-buddy-second-opinion）
- 所有 subagent 抓到的内容必须可追溯回 URL；不写"据某专家说"这种无源信息

## References

- [data-sources.md](references/data-sources.md) — 各类资源对应的权威源 + 已知抓取陷阱
- [scoring-rubric.md](references/scoring-rubric.md) — 排序打分维度和权重
- [output-template.md](references/output-template.md) — SHORTLIST.md 模板
- [mtb-centers-cn-seed.md](references/mtb-centers-cn-seed.md) — 已知设有 MTB/MDT 项目的中国大陆癌种中心种子列表（人工维护，不替代实时调研）
- 共用：`../../references/roles.md`, `../../references/safety-guardrails.md`, `../../references/disclosure-behavior.md`, `../../references/i18n.md`（locale 检测/persist/临床实体禁译）
- 联网底层依赖：`../web-access/SKILL.md`（subagent 必须加载）
