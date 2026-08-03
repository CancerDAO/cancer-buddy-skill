# 三层参考文献库（全局共享合同）

本文件规定 cancer-buddy 全部 skill 与 sub-skill 读写本地参考资料的唯一方式：三层库怎么放、
清单怎么写、哪一层的内容能拿来做什么、什么绝对不能做。

引用**长什么样**见 `citation-format.md`；**什么时候必须实时联网核验**见
`clinical-content-governance.md` §2 与 `safety-guardrails.md`。本文件不改这两条，只规定
本地这一侧。

## 1. 三层

| 层 | 位置 | 内容 | 谁维护 | 随 git 分发 |
|---|---|---|---|---|
| **L1 · 产品自带** | skill 内 `references/library/` | 我们维护的**结构化事实清单**（JSONL，有字段可检索），不是文档 | 我们 | ✅ 是 |
| **L2 · 用户全局** | `$CANCER_BUDDY_GUIDELINES`，未设则 `~/CancerDAO/library/` | 用户自己的**跨患者**资料：指南、论文、科普 | 用户（skill 协助登记） | ❌ 否 |
| **L3 · 患者专属** | `<patient_dir>/library/` | 与该患者直接相关的参考资料 | 用户（skill 协助登记） | ❌ 否 |

- **L2 是"一个用户多份档案"的落点**：指南、论文这类**非患者特异**内容只放一份，所有档案共用，
  不重复存储、不产生跨档案不一致。
- **L3 是 `<patient_dir>/` 下的基础设施目录**，与 `raw/`、`ocr/`、`reports/`、`runs/` 同级，
  **不是第 15 个 `NN_` 临床域桶**。参考文献不是这个患者的临床资料。
  由此顺带得到一条语法级保护：`anchor-contract.md` 规定合法锚点前缀是 `01_…14_`，
  `library/` 不在这个前缀集里，**参考资料的路径在语法上就无法成为临床结构化 JSON 的 `source_refs`**。
  不需要额外写硬拒规则。
- `$CANCER_BUDDY_GUIDELINES` 兼容说明：这个环境变量不废弃，它就是 L2 的根路径覆盖，
  **不是第二套机制**（原 `guideline-lookup.md` §1.5 的形态收编到这里）。

三层目录结构相同：

```
<library_root>/
├── index.json          # 清单：唯一权威，未登记的文件不作来源
├── guidelines/         # 指南
├── literature/         # 论文 / 综述
├── education/          # 科普 / 患教
├── datasets/           # 结构化事实清单（主要是 L1）
└── other/
```

## 2. 检索链

回答前按固定顺序查，命中内容作为回答的骨架、术语基底与引用锚：

```
① <patient_dir> 结构化档案（profile / 域 JSON / sidecar）
② 第一方指令层（主诊团队对本人的书面交代）
③ L3 患者专属库
④ L2 用户全局库
⑤ L1 产品自带清单
⑥ 实时联网
```

**优先检索 ≠ 优先采信。** 五类时效敏感断言——**获批状态 / 医保报销 / 试验在招 / 指南版本 /
中心名单**——无论本地是否命中，都要 answer-time 实时核一次，并按 `citation-format.md` §4 并列给出
`〔联网〕`结果。本地命中让联网这一步更强：拿着具体方案名、药名、线次去精准核验，而不是从零盲搜。

核验不可达时按 `safety-guardrails.md` 失败关闭，如实标注未核实，**不以本地命中冒充当前状态**。

## 3. `index.json` 契约

清单是唯一权威。schema：`skills/cancer-buddy-organize/references/schemas/library_index.schema.json`。

```json
{ "schema_version": 1, "entries": [ { …条目… } ] }
```

每条**必填 9 个字段**：

| 字段 | 说明 |
|---|---|
| `file` | 库内相对路径。绝对路径、`..`、符号链接、解析后越界一律硬拒 |
| `title` / `publisher` | 出处，引用时显示 |
| `version` | 版本 / 版次 / 收录批次 |
| `date` | 该版本的发布日期 |
| `retrieved_at` | 用户获取日期。与 `date` 分开——"2020 年的指南我今天下载的"，两个日期都要 |
| `lang` | 语言，按 `profile.json` 的 locale 优先检索 |
| `redistribution` | `allowed` \| `restricted` \| `unknown` |
| `patient_scope` | `general` \| `patient_specific` |

可选：`expires_at`、`jurisdiction`、`cancer_types[]`、`license`、`notes`、`pages`、`sha256`。
数据集类条目另有：`source_url`、`as_of`、`latest_batch`、`record_count`、`update_cadence`、`build_script`。

**`trust_tier` 不是清单字段。** 写进 `index.json` 会直接 schema 校验失败——见 §4。

**未登记的文件不作来源。** 文件在目录里但不在 `index.json` 里 → 检索时跳过，并提示用户
"有 N 个文件未登记，要登记吗"。孤儿文件对所有 gate 隐形，所以宁可不用。

**条目失效（由 `library_verify.py` 判定，失效条目不得引用）**：

- `version` / `date` / `retrieved_at` 缺失，或填的是 `待填` / `TBD` / `<…>` 这类占位
- `date` 在未来
- `expires_at` 已过
- `retrieved_at` 距今超过 `--max-age-days`（默认 730 天）
- 清单有、文件没有；或路径越界 / 是符号链接 / 是硬链接
- 超过条目数或总字节上限（默认 500 条 / 1 GiB）——整层作废，不做部分采信

## 4. `trust_tier` 由位置硬判，不由内容自述

`publisher` / `version` 全是用户可写的自我声明。一份营销册配一条自称 NCCN 的条目，就会以
比联网来源还权威的格式被引用。因此：

| 位置 | `trust_tier` | 能用来做什么 |
|---|---|---|
| L1（产品自带，我们审过） | `curated` | 可作答案依据 |
| L2 / L3（用户投放） | `user_supplied` | 可作骨架、术语基底、引用锚；**五类时效敏感断言不作最终依据**，必须并列 answer-time 核验 |
| `99_无关文件/` | 不进检索链 | — |

判定写在 `library_resolve.py` 的 `LAYER_TRUST_TIER` 里，按路径层级赋值。**模型无权提级**，
清单也无权自述——schema 的 `additionalProperties: false` 不包含 `trust_tier`，写了就校验失败。

**不做内容-清单一致性抽查**（例如"PDF 首页文本须含声明的 publisher"）：扫描件没有文本层、
中文指南首页不含英文出版方名、封面常是整页图——误伤率会高到让合法资料登记不进来。
主防线是位置硬判 + 时效项并列核验，去掉抽查不改变防护强度。

内部分级**不外显**：患者看到的标签只有 `citation-format.md` 的四类，不出现 `user_supplied` 之类的词。

## 5. `redistribution` 处置矩阵

| 值 | 本地读取引用 | 进导出包 / 第二意见包 | 允许出现在 L1 |
|---|---|---|---|
| `allowed` | ✅ | ✅ 需显式 opt-in（`export_share.py --include-library-entry`） | ✅ |
| `restricted` | ✅ 只呈现完成本次解释所需的最小内容 | 🚫 永不 | 🚫 |
| `unknown` | ✅ 同上 | 🚫 未声明许可前等同 restricted | 🚫 |

- **判定不靠猜**：默认 `unknown`；用户可声明；检测到常见受限出版方（NCCN / CSCO / ESMO /
  UpToDate 等）时默认置 `restricted` 并告知其许可条款要求。
- **L1 随 git 分发，只准 `allowed`**，由 lint 强制。
- `library/` 在 `export_share.py` 的 `FORBIDDEN_TOPLEVEL` 里，默认整体不进导出包。

## 6. 「存一下这个」写入动作

由 `skills/cancer-buddy-organize/scripts/library_save.py` 执行，skill 负责前置对话：

1. 问归属：**全局库（所有档案共用）还是这个患者的库**
2. 判 `patient_scope`：文件名 / 标题 / 文本内容出现姓名、住院号、病案号、身份证形状 →
   强制 L3，**禁止进 L2**（L2 跨档案，放患者特异内容会造成交叉污染）
3. 抽取元数据填 `index.json` 草案，走 `confirm-gate.md` 的 diff card 让用户确认——
   版本号、日期抽错会直接让过期判定失效
4. 复制文件 → 写清单条目 → 记 `update_log.json`

**写入目标永远在 `$HOME` 下**（`<patient_dir>/library/` 或 `~/CancerDAO/library/`）。
脚本**硬拒写入任何 git 工作区**：L1 是我们维护的内容，不接收用户文件。

L2 侧另有一道复查门：`library_verify.py` 对 `patient_scope: general` 的条目扫姓名 / 住院号 /
身份证形状，命中即报警并建议移入 L3。

## 7. 脚本

| 脚本 | 作用 |
|---|---|
| `library_resolve.py` | 解析三层根、读清单、强制路径边界、报告未登记的孤儿文件 |
| `library_verify.py` | 双向对账 + 过期 + 上限 + schema + L2 scope 门 → 输出 `verified_entries.json` |
| `library_save.py` | 「存一下这个」落盘 |
| `build_filings_dataset.py` | L1 数据集构建（新批次发布时重跑） |

**回答只准用 `verified_entries.json` 里的条目。** 直接读 `index.json` 等于跳过全部失效判定。

## 8. L1 呈现的安全边界（硬）

L1 首个数据集是**生物医学新技术临床研究备案项目表**（`datasets/cn-biomed-newtech-filings.jsonl`）。

**备案 ≠ 可以入组 ≠ 适合这个患者。** 备案只说明该项目在该机构合法开展。呈现规则沿用 find-care
既有立场（`cancer-buddy-find-care/references/data-sources.md`：不排序、不推荐、不判资格）：

- ✅ 只呈现事实：谁、在哪、备案了什么、第几批
- ✅ 给联系路径，让患者自己去问
- ✅ 必须显示**收录批次 + 数据截止日**，并说明之后可能有新批次，最新以官方公示页为准
- ✅ **申办机构 ≠ 研究机构**：患者要联系的是 `research_institution`，两栏都给并说明区别
  （59 条里 17 条不同，按申办方去联系会打错地方）
- 🚫 不判断该患者是否符合入组条件——这是 router 的个案判决轴，收紧
- 🚫 不按"先进程度"排序，不暗示优劣
- 🚫 不因为某项目技术看起来对口就暗示"你可以考虑"

**在招状态、最新批次属时效敏感项**，必须并列 answer-time 核验（§2）。实跑证明这不是洁癖：
并列核验独立发现了本地清单没有的已获批药物，把患者从"去挤入组筛选"改成"走正常处方途径"。

**L1 数据的维护契约**：新增任何 L1 数据集必须同时提供 `source_url`、`as_of`、更新脚本、
以及该数据集的时效半衰期声明。**没有更新路径的一次性数据不进 L1**——那只会变成又一个静默变陈旧的快照。
备案表的原始公示形态尚未核实（公开检索只能确认到第 3 批），确认前 `source_url` 留空且条目
`notes` 写明，不得按官方公示原件引用。
