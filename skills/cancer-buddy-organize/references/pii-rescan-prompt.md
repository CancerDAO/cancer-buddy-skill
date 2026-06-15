# PII 复扫（agent 语义主扫）— pii-rescan-prompt

PII 门的**主扫层**（泛化）。与 `scripts/pii_rescan.py` 的**确定性 shape 兜底**并联，两层任一命中即 fail-closed 拦截交付（trust-but-verify：Phase-1 masker 是判断式打码，本层是独立的语义复检，shape 兜底是独立的零网络形状复检）。

dispatch 时机：Phase-1 槽位 gate（phase1-ocr.md §2.5）、Phase-2 验收门、段C 增量、export 前——每个门点都在跑 shape 兜底的同时跑本层。

## 你的任务

读给定面的文本，**按含义**标记任何残留的可识别个人信息（PII）。这是开放式判断——**不要套固定类别清单**，凡是能（单独或与其它字段组合）定位到某个具体自然人的信息都算。

### 扫描对象
- **sidecar MD 正文**：`<patient_dir>` 下各 `NN_` 桶内 `*.md` 的正文（Phase-1 阶段则是 `<patient_dir>/ocr/*.md`）。**跳过** sidecar 头块（`SOURCE:`/`READ_MODE:`/`ADAPTER:`/`ADAPTER_PROVENANCE:`/`CONFIDENCE:`/`FILE_ID:`/`MODALITY:`/旧 `ORIGINAL:`）与 `## PII` 尾注——它们是 provenance，不是临床正文。
- **已交付面**（整文件扫，无头块豁免）：`INDEX.md`、`source_inventory.json`、`.rename_plan.json`、`.phase1_sources.json`、`update_log.json`、`病情简要总结.html`。
- **合成下游正文面**（整文件扫）：`case_text.md`、`timeline.md`、`profile.json`、`patient_summary.json`、`review_summary.md`、`review_flags.md`。它们由 sidecar 合成，下游/患者向读它们、且 export 会打包它们。**两层都扫这些**：Layer 2（`pii_rescan.py` 的 `SYNTHESIZED_SURFACES`）跑确定性 shape 兜底（身份证/手机/座机/住院号-shape/email——抓真实漏出的 shape-PII，但对去标识原件名里的紧凑时间戳 `微信图片_<14位>.jpg` 抑制 `numeric_id` 以免误杀）；本层（Layer 1）负责"按含义才认得出"的 PII（出生地/籍贯/职业/民族/家属名…）——这些没有 shape 签名，**只有本层能拦**。这正是 sidecar masker 漏过、case_text/profile 泄漏的根因面，两层互补覆盖。
- 值已是 `[PII_MASKED]` 的（标签在、值已遮）→ 干净，跳过。

### 算 PII（举例，非穷举——按含义判断，不限于此表）
- 姓名类：患者本人、**家属/关系人**、签名/审核/记录医师护士、转诊/主治医师真名。
- 联系/地址：电话/手机/座机/传真、email、家庭/通讯/工作住址、邮编。
- 编号类：身份证/护照、住院号/门诊号/病案号/就诊卡号、MRN、**检验号/标本号/样本号/条形码**、保险号、银行卡。
- 人口学可识别项：**出生地/籍贯、职业/工作单位、民族、宗教、国籍、具体城市**、出生日期（DOB；**精确年龄不算 PII，可保留**——临床试验匹配需要）。
- 账号/路径：host 绝对路径（`/Users/...`）、云盘账号、上传文件名里的真名。
- 生物识别 / 任何上述的组合 quasi-identifier。

### 不算 PII（临床保真红线——绝不标记、绝不改）
药名、基因/变异符号、VAF/剂量/数值+单位、TNM/分期、IHC 判读值、临床日期（检查/治疗/手术日期）、影像/病理描述、ECOG、**精确年龄**、机构粗粒度化后的描述。这些没有 PII 语义签名——误标会破坏临床保真（§2.2a 反锚定）。

## 输出（结构化）

```json
{
  "scanned": ["<surface 相对路径>", "..."],
  "findings": [
    {
      "surface": "<相对路径>",
      "line": <行号 int 或 null>,
      "category": "<自由文本类别，如 出生地 / 职业 / 家属姓名 / 检验号>",
      "snippet": "<命中片段 ≤ 24 字，不要回贴整段>",
      "suggested_action": "mask | relativize | coarse-grain | remove-at-producer"
    }
  ],
  "clean": <true 当且仅当 findings 为空>
}
```

- `clean=false`（findings 非空）→ **fail-closed**：门不放行。
- sidecar 正文命中 → 回交 Phase-1/段C producer 把该 PII token 遮成 `[PII_MASKED]`（只动 PII 字符，临床字符不动），复扫至 `clean=true`。
- 已交付面命中 → 在 **producer 端**修（用去标识 handle / 相对路径 / 机构粗粒度化），不是回去改 sidecar；真名永不进 INDEX/source_inventory/dotfiles/HTML。
- 你是**检测器不是改写器**：标出位置与建议动作，重新打码由 producer 在上下文里做（避免误吃相邻临床字符）。

## 网络 / headless
本层是 agent 语义判断，由编排 agent（Claude）自身执行，不需要外部 API。若以外部模型 headless 执行，遵 `reference_minimax_llm` 调用约定；模型不可达 → **报错，不静默跳过**（隐私门不因离线放行，见 `feedback_no_offline_only`）。

## 与 shape 兜底的分工
本层负责**语义 + 标签**检测（泛化任意类别）；`pii_rescan.py` 只保留**零假阴性的纯形状** pattern 作为独立确定性兜底，且**按面分层**：sidecar 正文只跑纯形状（email / 中国手机座机 / 身份证18位 / US-SSN / E.164 / ≥11位数字ID）；`/Users/` 绝对路径 / 云账号路径 / identity-denylist token 仅在已交付面 + 合成面（`scan_delivered_file`）生效（这些不会出现在 OCR 正文里）。两层覆盖互补：本层抓"按含义才认得出"的（出生地/职业/家属名/检验号/签名…），兜底抓"形状即铁证"的（手机号/身份证/邮箱…）。
