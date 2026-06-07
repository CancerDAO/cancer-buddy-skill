# 段B — 异步 PaddleOCR 打码 job

> 海外站把图内 PII 真正涂黑的那一步。段 A 只做 MD 文本级脱敏(下游唯一读取源已干净);桶里的图片本身仍含明文 PII,由本异步 job 涂黑后回填,并在 QA 通过后删除打码前原件。**删原件不可逆**,所有删除都被 QA 门 gate。

## 角色与脚本

| 脚本 | 角色 |
|---|---|
| `scripts/redact_ocr.py` | 打码引擎(vendored from `cancer-buddy-organize-local-skill`,原样)。`redact_image_ocr()`:PaddleOCR 取字 → 正则+NER 判 PII → 只对 PII 区域画黑框 → 存图。 |
| `scripts/run_redaction_job.py` | 批处理器。读 manifest → 逐图打码 → QA 门 → 回填桶+镜像 → 删原件 → 写 status。幂等可重试。 |

## 平台异步触发约定

- **运行模型**:异步后端 job。organize skill(段 A/D)**不阻塞**等打码;段 A 完成即产出 `redaction_manifest.json` 作为工作队列交接。
- 平台 worker 在 organize 完成后,**用 PaddleOCR venv 解释器**拉起本脚本:

  ```bash
  ~/.venvs/mtb-ocr/bin/python \
    skills/cancer-buddy-organize/scripts/run_redaction_job.py <patient_dir>
  # 或显式指定 manifest:
  ~/.venvs/mtb-ocr/bin/python \
    skills/cancer-buddy-organize/scripts/run_redaction_job.py --manifest <path/to/redaction_manifest.json>
  ```

- 入参:`patient_dir`(脚本去其中找 `redaction_manifest.json`)或 `--manifest <path>`(覆盖 `patient_dir`)。
- **必须用 `~/.venvs/mtb-ocr/bin/python` 启动**:脚本 `import redact_ocr`,后者透传依赖 `paddleocr`/`paddlepaddle`/`Pillow`,这些只装在该 venv。用系统 python 跑会落到 blocked。
- **可重试**:job 被杀或重跑都安全。脚本每处理一张就刷一次 `redaction_status.json`;重跑时 `status == "done"` 的文件直接跳过(幂等)。
- 退出码:`0` = status 写出且无 failed/blocked;`1` = 至少一文件 failed 或 blocked;`2` = 调用错误 / manifest 不可读。

## venv 要求

- 期望 `~/.venvs/mtb-ocr/`(paddleocr 3.x + paddlepaddle)。
- **venv 缺失** → 脚本不调 PaddleOCR,把 manifest 里**每个文件标 `blocked`**,`reason` 写明创建命令,exit 1。原件、桶图、镜像全部**不动**。
  ```bash
  python3 -m venv ~/.venvs/mtb-ocr
  ~/.venvs/mtb-ocr/bin/pip install paddleocr paddlepaddle
  ```
- venv 存在但 `import redact_ocr` 失败(缺 Pillow / paddleocr 装坏)→ 同样全 `blocked`,`reason` 提示用 venv 解释器重跑。
- 建议在调用前 export(见 `references/schemas/.. paddleocr` 习惯;来自 vendor 源):
  ```bash
  export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
  export FLAGS_use_mkldnn=0   # macOS Apple Silicon
  ```

## QA 门语义(删原件的唯一前置)

每张图打码后,在**删任何原件之前**必须过 QA 门:

1. 打码先写到桶图旁的临时文件 `<stem>__redacted_tmp.<ext>`,**不覆盖原图**。
2. QA = 对该打码图**再跑一次** `redact_image_ocr()`(二次 PaddleOCR 扫 + NER PII 检测,结果丢弃)。
3. 二次扫描若仍检出 PII 区域(`pii_detected > 0`)→ 说明目标 PII 区没被框全(有残留可识别 PII token)→ **QA 失败**。
4. **通过(残留 PII = 0)** → 才进入提交+删除;**失败** → 丢弃临时打码图,保留打码前原图,该文件标 `failed`,`original_deleted=false`,`reason` 记残留详情,留人工。

QA 门是 `redaction_status.json` 里 `qa_passed` 字段的来源,也是 `safety-guardrails.md`「打码后删原件」豁免的权威前置:**仅当 `qa_passed: true` 才允许删打码前原件**。

> 说明:复用引擎自身的 PII 检测做二次扫属保守 self-check——只要引擎判定该图还有 PII 就拦下,不放行。需要"目标 PII 标签区域语义判断是否覆盖"这类更细的判断时,交 subagent/LLM 复核 `reason` 里的残留 preview,不在本脚本写硬编码 keyword 名单。

## 提交语义(QA 通过后)

1. **桶图替换**:`os.replace(临时打码图 → 桶图)` —— 原子替换,即删掉上传原件,桶里只剩打码版。
2. **镜像替换**:把打码后的桶图 `copy2` 覆盖 `10_原始文件/<subdir>/<原图>` —— 删掉镜像里的打码前原图,**镜像只留打码版**(审计链本身已脱敏)。
3. 标 `status="done"`、`redacted_path=<bucket_path>`、`qa_passed=true`、`original_deleted=true`。

## 删原件不可逆警告

- ⚠️ **不可逆**:`status="done"` 的文件,其上传原件 + 镜像原图已被打码版**永久覆盖删除**,无法恢复明文原图。
- 删除**只**在 `qa_passed=true` 时发生。QA 失败 / 打码异常 / 替换 IO 失败 → 一律保留原图,标 `failed`,`original_deleted=false`。
- 镜像 `10_原始文件/` 旧红线「永不删除」在平台版被本豁免覆盖:保留的是**打码版**镜像,审计链不丢、但不含明文 PII。详见 `references/safety-guardrails.md` 的「平台版打码后删原件」豁免。
- 脱敏只遮 PII,**不改临床字符**(黑框只盖 PII 区域 quad)。

## manifest / status 契约

- **输入** `redaction_manifest.json` —— schema `redaction_manifest_v1`,见 `references/schemas/redaction_manifest.schema.json`。由段 A phase2-synthesis 产出,列每张待打码图的桶内路径 `bucket_path` + 镜像路径 `mirror_path` + 可选 `pii_hint`(advisory,段 B 自己重新 NER 检测,不只靠它)。
- **输出** `redaction_status.json` —— schema `redaction_status_v1`,见 `references/schemas/redaction_status.schema.json`。`summary{total,pending,done,failed,blocked}` + per-file `{id,status,redacted_path,qa_passed,original_deleted,reason}`。`id` 与 manifest 按 `^f\d{3,}$` join。
- 两文件同目录(`<patient_dir>/`)。status 每张刷一次,partial run 可恢复。

### 状态机

```
pending ──redact ok──▶ QA pass ──commit──▶ done   (qa_passed=true, original_deleted=true)
   │                      │
   │                      └──QA fail──▶ failed (qa_passed=false, original_deleted=false, reason)
   ├──redact/IO error────────────────▶ failed (original_deleted=false, reason)
   └──venv/import missing────────────▶ blocked (reason=创建 venv 指引)
```

## 下游衔接

- 段 A 完成 → 产 manifest;段 D HTML 只读脱敏 JSON/MD,不读图,**不依赖**段 B 是否跑完。
- 段 B 是纯收尾的图内涂黑 + 镜像收敛;跑完后桶里图为打码版,`.md` 旁车(段 A 已文本脱敏)仍是下游唯一读取源。
