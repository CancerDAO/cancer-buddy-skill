# PRD — pii_rescan 混合化：prompt 主扫 + 确定性 shape 兜底

> 状态：待确认（用户已批准"混合"方向，本 PRD 定最终形态 + 抽取点 + 时序 + 测试迁移，确认后执行）
> 触发：用户提出"pii_rescan.py 是不是可以用 prompt 来做，保证泛化性"
> 决策：混合（prompt 主扫泛化任意 PII 类别 + pii_rescan.py 收敛为纯 shape 兜底，保留 trust-but-verify 双层）

## 1. 问题（根因）

`pii_rescan.py` 的 `_PII_LABEL_PATTERNS` / `_PII_LABEL_TAIL` 是硬编码标签正则清单，**结构上只能抓预先写了 pattern 的类别**（姓名/住院号/电话/身份证/床号/检验号/签名…）。它抓不到：出生地/籍贯、职业/工作单位、家属姓名（非签名场景）、民族、转诊医生、雇主、宗教、保险号别名…——正是本轮泄漏的那批。这与 `feedback_default_prompt_over_script`（需要 LLM 判断的抽取/分类走 prompt/agent）同源。

## 2. 最终形态（END state）

两层、fail-closed 并联，任一命中即拦截交付：

### 2a. 主扫（新增）— `references/pii-rescan-prompt.md`（agent / prompt）
- 由编排器在每个 PII 门点 dispatch（与 Phase-1 masking / narrative / case-summary 一样是 agent 任务，pii_rescan 此前是唯一的纯 Python 异类）。
- **开放式语义判断**：读每个待扫面的文本，标记**任意**可识别个人信息类别——不给固定清单，给"判据 + 正/负例"，让 agent 按含义判断（姓名、联系方式、各类编号、住址、出生地/籍贯、职业/单位、家属/关系人身份、生物识别、账号/路径等）。
- 临床保真红线：只标 PII，VAF/剂量/数值/突变记法/TNM/日期一律不动（沿用 §2.2a 反锚定）。
- 返回结构化 findings（surface、行号、类别、片段、建议动作）；`findings>0` → fail-closed，回交 producer 重新打码后复扫至清。
- 网络/headless：若以外部模型执行，遵 `reference_minimax_llm` + `feedback_no_offline_only`，不可达则报错不静默跳过（门不能因离线而放行）。

### 2b. 兜底（收敛）— `pii_rescan.py`（确定性 shape-only）
- **保留**（零假阴性的纯形状）：`_STANDALONE`（email / 中国手机 / 座机 / E.164 / US-SSN / 身份证18位 / ≥11位数字ID）、`_PATH_PII`（/Users/ 绝对路径、云账号路径）、`_FILENAME_PII`（CJK名-Latin 文件名，仅 index/provenance 面）、identity-denylist token、delivered-surface 扫描入口。
- **移除**：`_PII_LABEL_PATTERNS`、`_PII_LABEL_TAIL`、`scan_cross_line` 标签跨行逻辑——这部分既不泛化又是历史假阳性来源（注释里记录过多次 clean record 误杀），语义/标签检测整体移交 2a。
- 角色重定义：从"标签+形状双职"降为"独立、可复现、零网络的 shape 兜底"，作为 2a 的独立第二意见（防两层 LLM 相关性盲点）。

## 3. 抽取 / 改线点（6 处调用 + 2 处测试 + 文档）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `references/pii-rescan-prompt.md` | **新建** agent 扫描 prompt（2a） |
| 2 | `scripts/pii_rescan.py` | 收敛为 shape 兜底（2b），改 docstring 角色说明 |
| 3 | `references/organizer-prompt-phase1-ocr.md` §2.5 | 槽位 gate 加 agent 主扫；`pii_rescan.py` 留作兜底；`pii_rescan_passed` attestation 扩为"两层均过" |
| 4 | `scripts/validate_structured_outputs.py` `gate_pii_rescan` | 验收门：agent 主扫结果纳入 + 保留 `pii_rescan` 兜底调用（已 import sibling，沿用） |
| 5 | `references/conversation-incremental-prompt.md` §段C | 同 §2.5：加 agent 主扫 |
| 6 | `scripts/export_share.py` | export 门复用 `validate_structured_outputs` → 自动覆盖；确认无独立 pii_rescan 直调 |
| 7 | `references/organize-contract.md` §§63/185/197/203 + `SKILL.md` + `runtime-bindings/*` + `schemas/README.md` | 不变量文案：去标识 = sidecar 文本遮蔽 + **agent 主扫** + 已交付面 shape 兜底 |
| 8 | `tests/unit/organize-fidelity-gates.test.sh` | Test1/2（path/filename/email = shape）**保留**；Test3（specimen_id + 散落医师名 = label）**迁移**为 agent-scan eval（或移到 `tests/eval/`），不在确定性单测里断言已移除的 label 臂 |
| 9 | `tests/eval/lint/04-pii-desensitization.sh` + `tests/eval/scenarios/cancer-buddy-organize.md` | 补 agent 主扫的语义泛化用例（出生地/职业/籍贯 必被标记） |
| 10 | `CHANGELOG.md` + `README*.md` | 同步（feedback_branch_readme_sync） |

## 4. 时序（避免隐私泄漏窗口）

**严格 additive-first**，绝不"先删后接"：

1. **Phase A（纯增）**：建 2a prompt + 把 agent 主扫接到全部 6 个门点，`pii_rescan.py` 维持**完整**（含 label 臂）当兜底。此时覆盖只增不减，零回归窗口，旧测试照过。top-down trace 验证：真实病例（含 出生地/职业）跑一遍，确认 agent 主扫**实际**标记到、门**实际**拦截（防 computed-but-disconnected）。
2. **Phase B（再减）**：A 验证通过后，收敛 `pii_rescan.py` 为 shape-only，迁移 Test3，补 eval 用例。

> 说明：用户已批准"删掉脆弱 label 清单"（最终形态）。A→B 是为了在隐私门上不开窗口的安全落地次序，不是分批交付不同顶层目录的形态迁移（与 `feedback_no_phased_form_migration` 不冲突——同一形态、同一目录，仅先增后减）。

## 5. 验收（E2E，自证）

- ≥2 患者 ≥2 癌种（feedback_multi_case_validation），其一刻意含 出生地+职业+籍贯。
- 证据：agent 主扫 findings JSON 命中这些类别；门 exit≠0 拦截；打码后复扫 findings=0、门 exit 0。
- shape 兜底单测（Test1/2）green；身份证/手机/email/绝对路径仍被确定性层独立抓到。
- 渲染→validator 全链 exit 0；CHANGELOG/README 已同步。

## 6. 待用户确认的点

- (A) 兜底是否**确定**收敛为 shape-only（移除 label 臂）= 你已选的"混合"含此；本 PRD 按"是"执行，A→B 次序落地。
- (B) Test3 迁移到 `tests/eval/`（agent 场景）可接受？还是希望保留一条确定性 specimen_id/签名 兜底（即 shape floor 额外保留这两类 label）？
