# PRD — 指南级证据实时联网并入 education 条件式教育分支（方案②）

- **状态**：待 founder 确认（确认后再动代码，遵 plan-before-implement）
- **日期**：2026-07-17
- **作者**：Claude（cancer-buddy-skill 迭代）
- **目标分支**：`feat/education-guideline-lookup`（一次性全迁，不分批）
- **前置已完成**：`963163f` 已把「来源引用」扩成档案锚 + 联网锚共用编号序列（本 PRD 的引用管道依赖它）

---

## 1. 问题陈述（第一性）

用户问「基于我的病情，NCCN 指南的建议是什么 / 标准治疗是什么 / 指南怎么说」这类**指南级**问题时，现状是：

1. 主 skill 把它归进「我不做的事」（诊断路径决策 / 换线决策），`cancer-buddy/SKILL.md:108` 已软化为「别停在甩回句 → 先给条件式教育地图 → 落回医生」，条件式教育分支已存在（router `:110-125` + `education/SKILL.md:14`）。
2. **但条件式教育里的"指南一般怎么治"内容目前靠 LLM 记忆 + 静态 `cancer-type-modules.md`**。而该文件自己就承认（`:9-10`）：「NCCN/CSCO 方案是 LLM 训练知识」「canned 内容必然落后于最新指南、会静默变陈旧」。
3. 这**直接违反** skill 自己的红线 `safety-guardrails.md:193` no-silent-snapshot——该条**已明确点名 "guideline versions" 必须 answer-time live lookup、禁 LLM 合成证据**。

**根因**：条件式教育有两种子问法被混在一条静态路径上——
- (a) **一般严重度/预后条件图**（"如果病理是 X 通常怎么走"）＝疾病生物学级一般规律，LLM 通识 + 静态癌种模块**够用且合规**。
- (b) **指南级具体断言**（"NCCN/CSCO 对 XX 的建议、标准治疗、具体方案/线数/证据类别"）＝版本敏感的外部目录事实，**红线要求实时查**，现在却走 LLM 记忆——这是潜在合规缺口。

方案②只补 (b)：给条件式教育分支加一条**指南实时检索子路径**，(a) 保持不动。

---

## 2. 最终形态（What good looks like）

用户问指南级问题 → education 条件式教育分支识别为 (b) 子问法 → 读 `profile.json` 拿癌种/分期/分子分型 scope 查询 → 派 **web-access 子 agent**（镜像 find-care 派发范式）实时检索**可复制引用面**的指南源 → 逐字接地 → 用**联网锚编号引用**（已上线）呈现 → 一般性条件化措辞（非个案判决）→ "以主诊医生为准" footer 收口。

**一句话形态**：把"指南怎么说"从 *LLM 凭记忆答* 改成 *实时查 + 逐字接地 + 编号引用 + 医生兜底*，且**输出仍是一般性条件图、不是个人换线判决**。

样例输出骨架：
```
（先接情绪）这个"你该不该换/该上什么"的结论要你主诊医生定。不过我可以把指南对你这类情况一般怎么说查给你看——

对 KRAS G12C 突变的转移性结直肠癌，指南一般把 sotorasib + 帕尼单抗列为标准治疗失败后的可选方案<sup>[1]</sup>；NCI PDQ 的患者版把它归为后线选项<sup>[2]</sup>。（这是对"这一类情况"的一般说法，不是对你个案的判决。）

你具体落在哪一支、要不要换，得你主诊医生结合完整情况定。带去问医生：我的 KRAS G12C 是否适合这条？前面标准治疗算用尽了吗？

来源：
[1] 〔文献〕PMID 35658005 · N Engl J Med · 2022
[2] 〔联网〕NCI PDQ Colon Cancer Treatment (Patient) · cancer.gov — https://www.cancer.gov/... · 抓取 2026-07-17
本手册为信息参考，任何治疗调整必须与主诊医生确认。
```

---

## 3. 源面优先级（licensing 决策）

指南全文里 **NCCN 是登录墙 + 版权保护**，web-access 能登进去，但**患者产品里逐字复制 NCCN 推荐表 / category-of-evidence 是授权灰区**（NCCN 对再分发很有攻击性）。故定**可复制引用面优先级**：

| 优先 | 源 | 性质 | 用法 |
|---|---|---|---|
| P0 | **NCI PDQ**（cancer.gov） | 美国政府公开、可自由引用 | 患者版/医生版均可逐字引 |
| P0 | **CSCO 指南**（中国、对中文用户最对口） | 学会指南 | 可引要点 + 版本号 |
| P1 | **ESMO** guidelines | 公开 | 可引 |
| P1 | **PubMed/EPMC 一级研究**（注册试验、NEJM/Lancet 等） | 公开摘要 | 逐字接地 pivotal 证据 |
| P2 | **NCCN** | 版权/登录墙 | **只"指向 + 引其 category 级别"，不复制其表格全文**；能用 PDQ/CSCO 覆盖就不碰 NCCN 原文 |

> 决策项 D1：是否接受"NCCN 只做指向、主引 PDQ/CSCO"这一 licensing 立场？（我推荐接受。）

---

## 4. 「我不做的事」边界变更（决策项 D2 — 你要删的那条）

你要删的是 `cancer-buddy/SKILL.md:108`：
> 这些一律回：**"这部分要问你的主诊医生。你可以用搭子帮你整理问问题的清单。"**

**现状澄清**：main 上这句已不是纯甩回——后面已跟"别停在这一句 → 先给条件式教育地图 → 落回医生"。

**我的独立建议：重构，不是整块删。** 理由（有据反驳，不是附和也不是拦你）：

- ✅ **该删的部分**：把"要问主诊医生 + 整理问题清单"作为**开场默认动作**——这个反射式甩回与我们现在要做的"实时查指南答给你看"矛盾，删掉/降级为**收口 footer**，让条件式教育（(b) 现在还带实时检索）成为默认第一动作。
- ⚠️ **不该删的部分**：`:100 诊断路径决策` 和 `:106 进展/换线决策`**作为"个人治疗判决"**（"你该换成 X 药""你下一步该做 Y 检查"）应当继续拒绝——这是真实责任敞口（pre-revenue、无专职法务）。把它们**重新界定为**："不做**你个案的**判决；但**指南对你这类情况一般怎么说**——查了、接地、给你看。"
- 净效果：`换线决策` 这条从"整块甩回"变成"个案判决拒绝 + 一般指南信息照给"。个案 verdict 线还在，甩墙没了。

> 决策项 D2：**(选项A 我推荐)** 重构 `:108`——甩回句降为收口 footer，边界重界定为"拒个案判决、给一般指南"；**(选项B 你原话)** 直接删掉 `:108` 整句；**(选项C)** 连 `:100/:106` 两条 boundary item 一起删。
> A 与 B/C 的差别：A 保留"不替你做换线判决"这条护栏只改开场话术；C 会让 skill 可被理解为"能给个人换线建议"——那是另一个风险量级，需要你明确要不要跨。

---

## 5. 触发判定：(a) vs (b) 子问法怎么分（LLM prompt，不硬编码）

在条件式教育分支里加一步 LLM 意图判定（**不写 keyword 表**，遵 default-prompt-over-script）：

- **(b) 指南级**（→ 走实时检索）：问法点名"指南/NCCN/CSCO/ESMO/标准治疗/一线二线方案/证据级别/最新获批"，或问"我这类一般用什么药/什么方案"。
- **(a) 严重度/预后级**（→ 保持现状，LLM 通识 + 静态癌种模块）："严不严重/能治好吗/是不是晚期/会不会复发"这类疾病生物学一般规律。
- 边界模糊时**倾向 (b) 走实时检索**（更安全——宁可查也不凭记忆答指南）。

---

## 6. 文件改动清单（全量，非自截）

| # | 文件 | 动作 | 优先级 |
|---|---|---|---|
| F1 | `skills/cancer-buddy-education/references/guideline-lookup.md` | **新建**：web-access 子 agent 派发模板（镜像 find-care `:106-130`）+ 源面优先级（§3）+ 逐字接地/撤稿检查/联网锚引用规则 + 5min 超时 + JSON 落 `reports/education/guideline/<slug>/` | P0 |
| F2 | `skills/cancer-buddy-education/SKILL.md` | 改：`When to use` 条件式教育项加 (b) 子路径；新增 `## 条件式教育 — 指南实时检索` workflow 小节；Safety 加"指南级断言禁 LLM 合成、须联网锚引用"；References 挂 F1 | P0 |
| F3 | `skills/cancer-buddy/SKILL.md` | 改：按 D2 定论重构 `:108` + `:100/:106` 界定；routing 表 `:62` 行补一句"指南级问法走实时检索" | P0 |
| F4 | `references/safety-guardrails.md` | 改：`:193` no-silent-snapshot 补一句显式点名"条件式教育里的指南级断言"归此红线；`:31` conditional-education 节加 (a)/(b) 区分 | P1 |
| F5 | `skills/cancer-buddy-education/references/cancer-type-modules.md` | 改：`:9-10` 免责改为"指南级方案改由 guideline-lookup 实时查，本静态模块只给疾病生物学一般框架" | P1 |
| F6 | `tests/eval/scenarios/cancer-buddy-education.md`（或新建 guideline 场景） | 加 ≥2 场景：①指南级问法→须触发实时检索+联网锚引用+医生兜底；②纯严重度问法→**不**触发检索（负向门，防过度联网） | P0 |
| F7 | `CHANGELOG.md` + `education/SKILL.md` description | 版本/变更记录同步（遵 branch-readme-sync） | P0 |

**注意**：无 Python 代码抽取——全是 skill(markdown) prompt/reference 改动。web-access 依赖已被 find-care/case-precedent 复用，非新增依赖。

---

## 7. 依赖图

```
用户问指南级问题
   └─> cancer-buddy(router) 条件式教育路由 [F3]
         └─> cancer-buddy-education 条件式教育分支 [F2]
               ├─ 读 profile.json (癌种/分期/分子分型)
               ├─ (a)/(b) 意图判定 [F2 §5]
               ├─ (a) → 静态 cancer-type-modules.md [F5] (现状)
               └─ (b) → guideline-lookup 子 agent [F1]
                        ├─ 加载 web-access skill (已有依赖)
                        ├─ 源面优先级 PDQ/CSCO/ESMO/PubMed>NCCN [§3]
                        ├─ 逐字接地 + 撤稿检查
                        └─ 联网锚编号引用 [963163f 已上线]
                              └─ 医生兜底 footer [safety-guardrails F4]
```

---

## 8. 安全门（P0，全修完才算完成）

- **G-NO-SYNTH**：指南级断言只能来自实时抓取到、能逐字回溯的源；LLM 记忆不得挂角标（复用 `safety-guardrails:193`）。
- **G-NO-VERDICT**：输出是"对你这类情况一般…"，绝不出个人分期/预后数字/换线判决（复用条件式教育既有护栏）。
- **G-LICENSE**：NCCN 不复制表格全文，只指向 + 引 category；主引 PDQ/CSCO。
- **G-LIVE-OR-HONEST**：联网不可达 → 标"需现场核实"，不静默降级到静态/记忆。
- **G-CITE**：每条指南断言带联网锚编号引用（URL 或 PMID），撤稿源不引。
- **G-DISCLOSURE**：`disclosure_state=suppressed` 且 role=patient 时按 disclosure-behavior 让位。
- **G-NO-OVERFETCH**（负向门）：纯严重度/预后问法**不**触发联网（F6 场景②守住），避免每句都联网拖慢 + 过度授权。

---

## 9. 分支 / 交付纪律

- 单分支 `feat/education-guideline-lookup`，一交付物（本 PRD 全量），不分批。
- 每个 P0 门配负向测试（G-NO-OVERFETCH 尤其）。
- 合并前 curate 历史 + README/CHANGELOG/description 同步。
- 与 benchmark/adapter 分支命名不混。

---

## 10. 待你拍板的决策项

- **D1**：licensing 立场——NCCN 只指向、主引 PDQ/CSCO？（推荐：是）
- **D2**：`:108` 边界处理——选项 A（重构，推荐）/ B（删句）/ C（连 boundary item 删）？
- **D3**：范围——本轮只做 education 内并入（②），还是同时新起 `cancer-buddy-guideline` 独立 companion（①）？（推荐：只做②，最小面、复用现有护栏）
