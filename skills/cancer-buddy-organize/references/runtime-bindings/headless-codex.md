# Runtime Binding — headless codex(草案 / draft)

> `cancer-buddy-organize` 在**平台 headless codex 单进程**上的运行时绑定**草案**,供平台(HanduoZ)照着接 adapter。它把契约的 5 个接缝(`organize-contract.md` §6)用 codex `exec` + 宿主 bash 原语填出来,**逐接缝对应契约要求**,行为/schema/产物结构与 Claude Code 参考实现(`claude-code.md`)逐字节等价——只换"谁执行机制"。
>
> **场景前提(issue #13 / PRD §1)**:codex GPT-5.5 单进程 headless,沙箱临时盘,跑完删沙箱;persistVault 只持久化结构化文本(此前跳过桶 + 原图,导致 77 张原图全丢、档案不可浏览)。本 binding 的任务是让平台用 codex 驱动**新两阶段 organize** 而非退回旧 organize-local,从而进桶 + 段B 留可浏览打码版。
>
> **状态**:待平台确认两个开放点——(a) codex 走 `-i` 视觉 OCR 还是沙箱内 PaddleOCR(两者契约都支持,见 §2);(b) 段B 时序须接进 persistVault **之前**(§5 / 契约 §4.3)。字段级真值仍以 `phase1-ocr.md` / `phase2-synthesis.md` / `confirm-gate.md` / `redaction-job.md` 为准。

## 0. 绑定总览

| 接缝 | 契约要求(不变) | headless codex 填法 |
|---|---|---|
| 编排 | 所有 sidecar 在 Phase2 前就绪 | **单进程顺序**:逐文件 `codex exec` 产 sidecar,不并行 |
| OCR 源 | 每文件产脱敏 MD(`SOURCE`/`CONFIDENCE`/`## PII`) | `codex exec -i <image>` 视觉 **或** 沙箱内 PaddleOCR(待平台选) |
| 图像解码 | 给出可读栅格 | `heif-convert` / ImageMagick 转 HEIC(非 `sips`) |
| 确认门 | 未确认不写正式字段 | **confirm-as-product**:产待确认项 JSON,平台 UI 两轮往返 |
| 存储 | 结构化产物 + 桶 + manifest 为 canonical 输出集 | 平台 persist 选定桶 + manifest + 结构化文本到 R2/PG |

**宿主额外职责(契约 §1.1 / §7 开放问题)**:codex `-i` 喂的是**匿名字节**,codex 不知道原文件名。因此 **`file_id` 由宿主分配并维护 `file_id ↔ 原名` 双向映射**——这是 headless 路径的契约基石(Phase2 的 `file_id_to_name` input、canonical 改名可追溯、sidecar 回指源文件全靠它)。CC 路径因 worker 内 `Read` 按路径读图天然知道文件名,无需此步;headless 必须显式做。

---

## 1. 接缝:编排 —— 单进程顺序,不并行

- **契约要求**:Phase2 开始前,覆盖范围内所有源文件的 sidecar 必须就绪(契约只要"就绪",不要"如何就绪")。
- **填法**:宿主在沙箱内**顺序**遍历源清单,对每个源文件起一次 Phase1(§2),逐个产 sidecar 到沙箱暂存区。**无并行、无扇出、无 continuation loop**——单进程 codex 不需要 CC 的多 subagent 编排,也没有 CC 的 per-context 多图预算问题(故 §3 的"≤15 切片"对本 binding **不适用**,见下)。
- **宿主伪流程**:
  ```
  file_map = {}                       # file_id -> 原名/原路径
  for src in enumerate(source_inventory):
      fid = assign_stable_file_id(src)        # 宿主分配,跨 run 稳定
      file_map[fid] = src.original_name
      raster = decode_if_needed(src)          # §3 图像解码
      sidecar = run_phase1(fid, raster)       # §2 OCR 源
      write(sandbox/_sidecars/<fid>.md, sidecar)
  persist(file_map)                   # Phase2 的 file_id_to_name input
  ```
- **切片预算**:契约把"≤N 图/实例"明确为 **host-tunable 参数,非不变量**(契约 §1.5 / §7)。CC 因 Claude 多图预算需 ≤15 切片;codex 单进程逐文件跑,**不切或按 codex 自己预算切**都合规,1.4 不变量照样成立。
- **不变量**:sidecar 就绪是 Phase2 唯一前置;Phase1 阶段只写 sidecar 暂存区 + 原图镜像,不写任何全局产物;幂等(重跑跳过 mtime 更新的既有 sidecar)。

## 2. 接缝:OCR 源 —— `codex exec -i` 或沙箱内 PaddleOCR

- **契约要求**:每文件产**恰好一个**脱敏 sidecar MD,三段固定:`SOURCE: <type> | CONFIDENCE: <low|medium|high>` + `ORIGINAL: <稳定引用>` 头 / 逐字脱敏 OCR 正文(文字图全文逐字、影像图 ≤5 行 stub)/ `## PII` trailer(`masked: <类别>` 或 `masked: none`)。sidecar 是下游唯一读取源,**强制 PII 脱敏**成 `[PII_MASKED]`,不得带明文。
- **填法 A — codex `-i` 视觉(已生产验证)**:
  ```bash
  codex exec -i "$raster" "<phase1-ocr.md 全文 + Call parameters: file_id=<fid>>"
  ```
  把 `phase1-ocr.md` 的 per-file 部分作为 prompt,要求 codex 输出符合三段结构的 sidecar MD 文本;宿主把 stdout 写成 `<fid>.md`。**注意 `-i` 是匿名字节**:prompt 里不能依赖文件名,`ORIGINAL` 头用宿主传入的 `file_id`(宿主据 `file_map` 回填真实引用)。
- **填法 B — 沙箱内 PaddleOCR**:在沙箱跑 vendored PaddleOCR(同段B `redact_ocr.py` 用的引擎)抽原始文字,再用一次 `codex exec`(纯文本,无 `-i`)做脱敏 + 三段结构化 + CONFIDENCE 规则判定。字符精度更高、无多模态预算,但多一道脱敏 LLM 调用。
- **待平台确认**:走 A 还是 B(契约 §7 开放问题)。两者契约都支持,产出的 sidecar MD 结构必须逐字相同——下游不区分 OCR 源。
- **CONFIDENCE 是规则判定非自评**(命中 `[OCR_UNCERTAIN]`/手写/瓶贴→`low`;正式文书且 ≥2 文档关键字段逐字一致→`high`;默认 `medium`,详见 phase1-ocr.md §2.3),无论 A/B 都按规则填。
- **不变量**:anti-anchoring(单文件单进程跑,天然不跨文件纠正;矛盾留给 Phase2 调和)、unreadable→`[OCR_UNCERTAIN]`、未知名→verbatim+`[CANDIDATES]`、无采样、只动 PII 不动临床字符、只写 per-file sidecar。

## 3. 接缝:图像解码 —— heif-convert / ImageMagick(非 sips)

- **契约要求**:给 OCR 源一张可读栅格。
- **填法**:沙箱内无 macOS `sips`。HEIC/HEIF →
  ```bash
  heif-convert "$heic" "$tmp/<fid>.jpg"        # libheif
  # 或
  convert "$heic" "$tmp/<fid>.jpg"             # ImageMagick(需 HEIC delegate)
  ```
  PDF 多页若需逐页栅格,用 `pdftoppm` / ImageMagick。也可由平台在**喂进沙箱前**预处理成 JPEG/PNG,沙箱只收可读栅格。
- **不变量**:解码只为"给出可读栅格",不改像素语义、不在此步做 PII 处理。

## 4. 接缝:确认门 —— confirm-as-product + 平台 UI 两轮往返

- **契约要求**:任何写正式字段 / 不可逆删除前先产待确认项数据,未确认绝不写;删除非对称(高置信非医疗 no-confirm⇒删、borderline⇒留);留 `update_log.json` ledger。headless 没有 inline 会话,**必须产物化**。
- **填法(两轮)**:
  1. **第一轮(产)**:codex 把待确认项**落盘成 JSON**(沿用段C 候选结构 + `confirm-gate.md` 的 diff-card 内容契约):每候选含 `current_value → proposed_value`(字段改)/ 整条新行(timeline)/ `isolated as X — 一行理由`(relevance/删除候选);带依据(用户原话 / 检查名·日期·机构·矛盾字段);`low` 置信候选明标;关键字段变更与"已删除"绝不呈现为已完成;矛盾两值并陈标 ⚠️。按 `profile.json.locale` 渲染患者向文案,内部临床实体 verbatim。宿主在此**暂停管线**,不落任何正式字段。
  2. **平台 UI**:把该 JSON 渲染成 UI,收集用户每条决定(`accept_suggestion` / `keep_original` / `custom_value` / `defer`;段E 为 删/回收/留)。
  3. **第二轮(灌)**:宿主把已确认决定回灌给 codex(第二次 `codex exec`),**只**对已确认候选落正式字段 / 执行不可逆删除,并写 `update_log.json` ledger 条目。
- **删除非对称(load-bearing,headless 照样守)**:高置信非医疗文件**用户未在 UI 响应 = no-confirm ⇒ 删**(隐私底线 by design,UI 第一轮必须告知"沉默=删");borderline `relevance_uncertain` no-confirm ⇒ **留、永不自动删**。段E `99_无关文件/high_confidence/` vs `uncertain/`、upload-reconciliation 的 new/supersede/conflict 都复用这同一门(不开第二道门),各自 specialization 见其 doc。
- **不变量**:未确认绝不写正式字段;沉默/推迟/关闭 = no-confirm;矛盾两值并陈交用户裁、关键字段绝不既成事实;候选检测/分类是 LLM 判断(不跑硬编码关键词名单);每次 gated 动作在 `update_log.json` 留一条,无匹配条目不许写/删。

## 5. 接缝:存储 —— 平台 persist 桶 + manifest + 结构化文本

- **契约要求**:结构化产物 + 桶(含 co-located 脱敏 MD)+ `redaction_manifest.json` 为 canonical 输出集,落在契约 §2.2 产物结构里。
- **填法(语义判定 LLM / 机械搬运宿主分离)**:
  1. **Phase2 综合(LLM)**:一次 `codex exec` 读**全部** sidecar + `source_inventory` + `file_id_to_name`,产:11 桶分类 + canonical 命名 + `profile.json` + `timeline.*` + `case_text.md` + `readiness.json` + `review_flags.md` + 6 结构化 JSON + `missing_items.json` + `update_log.json` + `redaction_manifest.json` + 桶相对 `[[src:...]]` 锚点。**语义判定(哪个桶、什么 canonical 名)固化为一份 `.rename_plan.json`**(契约 §2.6:这是必须的 LLM 判断)。
  2. **机械 mv / persist(宿主 bash,无判断)**:宿主据 `.rename_plan.json` 把原件按 canonical 名拷进桶、把 MD co-locate 到旁边、回填 `file_id↔canonical` 映射、**排空 sidecar 暂存区**、生成最终 `redaction_manifest.json`。这是无判断纯字节搬运,契约允许宿主做(契约 §2.6「编排/存储」接缝)。
  3. **HEIC 等**:同 §3,搬运前若桶要存可读栅格用 `heif-convert`/`imagemagick`。
  4. **persist**:平台把**选定文件**持久化——结构化文本(6 JSON / profile / readiness / timeline / case_text / INDEX / update_log / missing_items)+ **桶(含 co-located 脱敏 MD + 桶图)** + `redaction_manifest.json` → R2(对象存储)/ PG(库)。`ocr/` 中央暂存区已废弃(MD 已在桶里,不 persist);`10_原始文件/` 镜像可不持久化(契约 §9 / PRD §9)。
- **存储模型对齐(PRD §9,平台必须照此改)**:此前 persistVault 只持久化结构化文本、跳过桶 + 原图 → 77 张原图全丢。**修正**:persist 必须含**桶(co-located 脱敏 MD + 段B 打码后的桶图)** + `redaction_manifest.json`。
- **段B 时序(契约 §4.3 / PRD §9.2,硬约束)**:段B 像素打码**必须在 persistVault 之前(沙箱内)跑**,持久化的桶图才是打码版。平台把 `run_redaction_job.py` 接进沙箱生命周期:
  ```bash
  ~/.venvs/mtb-ocr/bin/python \
    skills/cancer-buddy-organize/scripts/run_redaction_job.py <patient_dir>
  ```
  脚本读 `redaction_manifest.json` → PaddleOCR 打码 → QA 门 → 仅 `qa_passed=true` 才删原件 → 写 `redaction_status.json`。**原图永不离开沙箱**(段B 删前;段B 跑完只留打码版)→ 既"可浏览档案库"又"at-rest 不留明文"。段B 本就 runtime-neutral(契约 §4),与 CC 用同一脚本同一 manifest/status 契约,只是宿主负责"接进 persist 前"的触发时序。
- **不变量**:sidecar 是唯一明文边界(Phase2/段D/段B 只读脱敏 MD);进桶 + 段B 打码留可浏览版不退化回"丢原图/不进桶";桶 `NN_` 数字前缀稳定 key、localize slug 不破坏锚点解析;暂存区综合后必须排空(`ocr_drain_incomplete` 暴露);manifest 必产且过 schema;schema 不过的 JSON 不写、dangling 锚点的 case_text 不写。

---

## 6. 平台握手清单(PRD §10)

平台需实现的 codex adapter:
1. **顺序 driver**:遍历源清单逐文件起 Phase1(§1),全 sidecar 就绪后单次 Phase2(§5.1)。
2. **OCR 源**:`codex exec -i` 视觉 **或** 沙箱内 PaddleOCR(§2,二选一,待确认)。
3. **`file_id` 分配 + `file_id↔原名` 映射维护**(§0,因 `-i` 匿名字节)。
4. **机械 mv / persist**:据 `.rename_plan.json` 搬运 + 选定文件 persist 到 R2/PG(§5.2/§5.4)。
5. **confirm-as-product UI**:待确认项 JSON ↔ 平台 UI 两轮往返(§4)。
6. **段B 接进 persist 前**:沙箱生命周期内跑 `run_redaction_job.py`(§5 段B 时序)。

## 7. 验收(对应 PRD §11.5–6)

- 平台用本 binding 产出 **桶 + `redaction_manifest.json`**(PRD §11.5,平台侧验证)。
- confirm-as-product 满足 confirm-gate 不变量:未确认不写正式字段、删除非对称、留 ledger(PRD §11.6)。
- 产物与 CC 参考实现逐字节同 schema(逻辑/schema/产物结构零改动,PRD §11.4)。

## 8. 相关文件

- `organize-contract.md` — 运行时中立契约(本 binding 的分母);§1.1 file_id、§4.3 段B 时序、§7 开放问题尤为相关。
- `runtime-bindings/claude-code.md` — 参考实现(同 5 接缝的 CC 填法,逐字节等价目标)。
- `runtime-bindings/_template.md` — 第三方 host 照填的空模板。
- `redaction-job.md` — 段B 脚本/manifest/status 契约 + venv 要求(`~/.venvs/mtb-ocr`)。
- `phase1-ocr.md` / `phase2-synthesis.md` / `confirm-gate.md` / `relevance-gate.md` / `upload-reconciliation.md` — 字段级真值出处。
