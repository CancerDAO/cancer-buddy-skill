# SHORTLIST.md 模板

> **i18n**：本模板**按 `profile.json.locale` 渲染**（见 `../../cancer-buddy/references/i18n.md`）。下面的中文骨架是 `zh` locale 的渲染结果；其它 locale 时，所有脚手架字符串（section 标题 / 字段标签 / 匹配度档位词 / 下一步动作 / 免责声明）查下方 §locale 字符串表渲染，HTML/markdown 结构 1:1 不变。**临床实体逐字不译**：医院/医生/试验原名、NCT/ChiCTR 编号、药名、基因、变异、TNM/分期、数值单位、量表标准名一律保持源文。机构名可在原名旁加 locale 注释，不替换原名。

```markdown
# 资源短名单 — <一句话描述本次查询>

> 查询定义：见 [QUERY.md](QUERY.md)
> 生成时间：YYYY-MM-DD
> 调研深度：N 个 subagent 并行 / M 个一手源

---

## 顶层结论

一段话（≤4 行）：本次查到的 X 个候选项里，匹配度最高的是 [...]，主要原因是 [...]。如果地理预算/时间约束放宽，候选范围会变成 [...]。

---

## 候选清单（按匹配度排序）

### 1. [名称] — 匹配度：高 / 中 / 低（X.X / 30）

**关键事实**
- 类型：医院 / 医生 / 临床试验
- 位置：城市 + 院名（医生/试验场所均锚定到院）
- 团队 / PI：（医生类必填）
- 服务能力：（如"该院肺癌内科年门诊量 12 万人次，分子检测平台院内自建"）
- 频率 / 时间：（医生：出诊安排 | 试验：当前招募状态）

**匹配理由**
- ✅ [一句话事实，带证据片段]
- ✅ [...]
- ⚠️ [一句话需注意的事，例如"号源紧张，建议通过互联网医院预约"]

**挂号 / 联系路径**
1. [具体平台 + 步骤，例如"好大夫在线 → 搜 [医生名] → 选 [出诊医院] → 选下周二上午号"]
2. [备选路径，如"或拨打院方咨询电话 0571-XXXX"]
3. （试验类）[联系 PI 邮箱 / 中心 GCP 办公室]

**潜在限制**
- 费用：自费 ~XXX / 需医保备案 / 试验免费
- 等候期：约 X 天 / 周
- 异地医保：杭州→北京 需 [备案路径]
- 排除标准（试验类）：[关键 1–2 条]

**证据来源**
- [URL 1] — 来源类型 + 抓取时间
- [URL 2] — ...

---

### 2. [名称] — ...

（同上结构）

---

### 3. ...

---

## 没进短名单但提一下

| 候选项 | 为何没纳入 |
|---|---|
| [名称] | 地理超出范围（在广州，用户最远到上海） |
| [名称] | 试验已停招（截止 2026-03） |
| [名称] | 仅二手报道，未在院方一手源核实 |

---

## 用户的下一步建议

1. [ ] 优先做 [候选 #1] 的挂号尝试 — 路径见上
2. [ ] [候选 #2] 作为备选，先邮件咨询出诊安排
3. [ ] 如果都挂不上，回来告诉我，我再扩范围 / 加候选

---

> **这是资源发现的结果，不是医学推荐。** 是否真的合适你（或你家人）的具体情况，需要带着这份清单和你的主诊医生讨论，或挂号后由对方医生评估。
> 临床试验匹配 ≠ 符合入组标准，具体以研究中心预筛结果为准。
```

## locale 字符串表

模板里的每个脚手架字符串有一个稳定 string id（语言无关）。渲染时按 `profile.json.locale` 取该 locale 列的值；表里没有的 locale，按 string id 的英文语义在目标语言生成同义文案（不要硬编码新表，交 LLM 按语义本地化输出）。**临床实体不进字符串表**——它们逐字来自数据，不本地化。

| string id | `zh`（现有骨架） | `en`（canonical） |
|---|---|---|
| `title.shortlist` | 资源短名单 | Resource Shortlist |
| `meta.query_ref` | 查询定义：见 | Query definition: see |
| `meta.generated_at` | 生成时间 | Generated |
| `meta.depth` | 调研深度 | Research depth |
| `meta.depth_unit` | N 个 subagent 并行 / M 个一手源 | N subagents in parallel / M primary sources |
| `sec.top_conclusion` | 顶层结论 | Top-line conclusion |
| `sec.candidates` | 候选清单（按匹配度排序） | Candidates (ranked by fit) |
| `sec.not_listed` | 没进短名单但提一下 | Considered but not shortlisted |
| `sec.next_steps` | 用户的下一步建议 | Your next steps |
| `field.key_facts` | 关键事实 | Key facts |
| `field.type` | 类型 | Type |
| `field.type.hospital` | 医院 | Hospital |
| `field.type.doctor` | 医生 | Doctor |
| `field.type.trial` | 临床试验 | Clinical trial |
| `field.location` | 位置 | Location |
| `field.team_pi` | 团队 / PI | Team / PI |
| `field.capability` | 服务能力 | Service capability |
| `field.freq_timing` | 频率 / 时间 | Frequency / timing |
| `field.fit_reason` | 匹配理由 | Fit rationale |
| `field.path` | 挂号 / 联系路径 | Booking / contact path |
| `field.limits` | 潜在限制 | Caveats |
| `field.fee` | 费用 | Cost |
| `field.wait` | 等候期 | Wait time |
| `field.cross_city_insurance` | 异地医保 | Cross-region insurance |
| `field.exclusion` | 排除标准（试验类） | Exclusion criteria (trials) |
| `field.evidence` | 证据来源 | Evidence sources |
| `tier.high` | 高 | High |
| `tier.mid` | 中 | Medium |
| `tier.low` | 低 | Low |
| `col.candidate` | 候选项 | Candidate |
| `col.why_excluded` | 为何没纳入 | Why excluded |
| `disclaimer.not_advice` | 这是资源发现的结果，不是医学推荐。是否真的合适你（或你家人）的具体情况，需要带着这份清单和你的主诊医生讨论，或挂号后由对方医生评估。 | This is resource discovery, not a medical recommendation. Whether it actually fits you (or your family member) must be discussed with your treating physician — bring this list, or have the booked physician assess. |
| `disclaimer.trial_match` | 临床试验匹配 ≠ 符合入组标准，具体以研究中心预筛结果为准。 | A trial match ≠ meeting enrollment criteria; the study site's pre-screening is authoritative. |

> 叙事段（顶层结论、匹配理由句、限制说明）走 prompt 指令直接用 locale 写，不查表——prompt 写明 "Output prose in `<locale>`; keep clinical entities verbatim per `../../cancer-buddy/references/i18n.md` §4."

## 渲染原则

- **匹配度用三档**（高/中/低），分数括号在后供想看的人参考；不要把分数当主轴
- **脚手架按 locale 出**——section 标题/字段标签/档位词/免责声明查 §locale 字符串表；临床实体逐字不译
- **每条候选必须有"挂号路径"**——这是用户来这个 skill 的核心 utility，没路径等于没用
- **限制项不能藏**——费用、等候、医保、试验排除标准必须显式列
- **来源 URL 全列**——审计 + 让用户自己复核
- **末尾免责声明不能省**——是临床安全红线
