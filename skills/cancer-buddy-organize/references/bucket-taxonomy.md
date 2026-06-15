# Bucket Taxonomy — single source of truth (`scheme_version: 3`)

> This file is the **one authoritative definition** of the `cancer-buddy-organize` bucket scheme.
> Every other reference (`organize-contract.md`, `organizer-prompt-phase2-synthesis.md`,
> `organizer-prompt-phase1-ocr.md`, `../../../references/i18n.md §6`, `SKILL.md`,
> `references/patient-profile-schema.md`, `schemas/anchor-contract.md`, runtime bindings, the
> redaction job, and every sibling/downstream skill) MUST agree with the tables below. If they
> disagree, **this file wins** and the other is a drift bug to fix.

## 0. What changed in v3 (and why)

v2 collapsed three conflicting bucket lists into one contiguous `00…09` oncology-document scheme.
v3 **generalizes** that scheme into a longitudinal, multi-modal, multi-disease data layer, because
the CancerDAO data layer must serve **non-oncology patients + omics + imaging + wearable + PRO +
longitudinal time series**, not only "tumor patient + image/text". The redesign rests on three moves:

1. **Single classification axis = clinical domain** (modality-agnostic). v1/v2 mixed four axes —
   document-type (`04_影像`), synthesized state (`00_当前状态`), provenance (`09_患者补充`), and
   infrastructure (`10_原始文件`). v3 files every *source document* on one axis: its clinical domain.
   `00_当前状态` is **removed** as a bucket — it was synthesized output that already lives in
   `profile.json` + `case_text.md`, never a folder of raw uploads.
2. **Modality is an orthogonal tag, not a bucket** (§2). Every filed source carries a `modality`
   value (`text` / `image` / `structured` / `omics_raw` / `timeseries` / `binary_other`). A pathology
   report is domain `04` + modality `text`; an NGS panel is domain `06` with a `text` report page and
   an `omics_raw` VCF. ingest dispatches its parser off `modality`, never off the bucket.
3. **Longitudinal streams are first-class, not documents** (§3). Wearable exports, PRO diaries, and
   lab trends are *series*, not one-shot files. Their parsed observations accumulate in
   `longitudinal_observations[]` next to `profile.json`; only the raw export file is filed (domain
   `10`). This is what lets the profile carry a trajectory, not just `latest_status`.

## 1. Authoritative scheme

`NN_` is a **language-independent stable key** — downstream anchors, `_FILENAME_MAPPING`, and every
`[[src:…]]` resolve on the `NN_` numeric prefix (anchor regex `^[0-9]{2}_…`), never on the localized
slug (see `../../../references/i18n.md §6`). The `zh` slug is the on-disk folder name for `locale=zh`; the `en` slug per
`../../../references/i18n.md §6.1`. The scheme is disease-agnostic: the same 14 domains serve oncology, rare-disease
(firefly), chronic-disease, and healthy-baseline records — no domain hardcodes a cancer-only concept
(`TNM`, `肿瘤标志物` are *typed subdirs / schema fields*, not bucket-level identity).

### 1.1 Clinical domains (visible, anchored)

| NN_ | `zh` slug | `en` slug | typed sub-buckets (`zh`) | from v2 |
|---|---|---|---|---|
| `01_` | `01_身份与基础信息` | `01_identity_basics` | `身份证件/ 人口学/ 参保信息/` | `01_基本信息` |
| `02_` | `02_既往史与家族史` | `02_history_family` | `既往病史/ 手术史/ 过敏史/ 用药史/ 家族史/ 胚系遗传/` | **new** |
| `03_` | `03_病程与叙事文书` | `03_clinical_notes` | `入院记录/ 出院小结/ 病程记录/ 门诊病历/ 主诉首程/` | **new** |
| `04_` | `04_诊断与分期` | `04_diagnosis_staging` | `病理报告/ 诊断证明/ 分期评估/ 其他/` | `02_诊断与分期` + `11_诊断证明` |
| `05_` | `05_影像` | `05_imaging` | `CT/ MRI/ PET-CT/ 超声/ X光DR/ 核医学/ 内镜影像/ 其他/` | `04_影像学` |
| `06_` | `06_分子与组学` | `06_molecular_omics` | `NGS报告/ 免疫组化/ 胚系检测/ WES-WGS/ 转录组/ 甲基化/ 蛋白-代谢/ 微生物组/ 其他/` | `05_分子检测` (expanded) |
| `07_` | `07_检验` | `07_labs` | `血常规/ 生化肝肾功/ 肿瘤标志物/ 凝血/ 尿便/ 心电图功能检查/ 其他/` | `06_检验` |
| `08_` | `08_治疗` | `08_treatment` | `化疗/ 放疗/ 免疫治疗/ 靶向/ 内分泌/ 中医中药/ 处方医嘱/ 支持治疗/` | `07_治疗记录` (surgery split out) |
| `09_` | `09_手术与操作` | `09_procedures` | `手术记录/ 麻醉记录/ 介入/ 内镜操作/ 植入物-器械卡/` | split from `07_治疗记录/手术-内镜` |
| `10_` | `10_随访与监测` | `10_followup_monitoring` | `随访复查/ 可穿戴导出/ PRO自报/ 居家监测/` | **new** |
| `11_` | `11_会诊与转诊` | `11_consult_referral` | `MDT/ 会诊/ 转诊/ 第二意见/` | `08_会诊-转诊` |
| `12_` | `12_心理社会与支持` | `12_psychosocial_support` | `心理评估/ 营养/ 康复/ 缓和/ 社工/` | **new** |
| `13_` | `13_行政与财务` | `13_admin_financial` | `知情同意/ 费用发票/ 医保报销/ 证明材料/` | **new** |
| `14_` | `14_患者自管补充` | `14_patient_supplement` | `患者补充/ 日记/ 自测/ conversation_notes/` | `09_患者补充` |

### 1.1a Typed subdirectory slug map (`zh` ↔ `en`, pinned)

> **Folder-slug policy (two pinned sets, never per-language).** On-disk folder slugs are
> infrastructure keys, not user-facing prose. They come in exactly **two pinned forms**: `zh`
> (when `locale=zh`) and `en` (**every other locale** — fr/es/de/pt/ar/… all use the `en` column,
> NOT a runtime-translated French/Spanish/German slug). Subdirs are **never runtime-translated** into
> other languages. The `NN_` numeric prefix stays language-independent and stable; `high_confidence`
> / `uncertain` / `conversation_notes` stay ASCII as before. All user-facing localization (timeline
> prose, summaries, INDEX labels, UI) still renders in the patient's locale — only the folder NAMES
> are restricted to these two pinned sets.

| domain | `zh` subdir | `en` subdir (pinned, used for every non-zh locale) |
|---|---|---|
| `01_身份与基础信息` | 身份证件 | `id_documents` |
| `01_身份与基础信息` | 人口学 | `demographics` |
| `01_身份与基础信息` | 参保信息 | `insurance_enrollment` |
| `02_既往史与家族史` | 既往病史 | `past_history` |
| `02_既往史与家族史` | 手术史 | `surgical_history` |
| `02_既往史与家族史` | 过敏史 | `allergies` |
| `02_既往史与家族史` | 用药史 | `medication_history` |
| `02_既往史与家族史` | 家族史 | `family_history` |
| `02_既往史与家族史` | 胚系遗传 | `germline` |
| `03_病程与叙事文书` | 入院记录 | `admission_notes` |
| `03_病程与叙事文书` | 出院小结 | `discharge_summary` |
| `03_病程与叙事文书` | 病程记录 | `progress_notes` |
| `03_病程与叙事文书` | 门诊病历 | `outpatient_notes` |
| `03_病程与叙事文书` | 主诉首程 | `chief_complaint` |
| `04_诊断与分期` | 病理报告 | `pathology` |
| `04_诊断与分期` | 诊断证明 | `diagnosis_certificate` |
| `04_诊断与分期` | 分期评估 | `staging` |
| `04_诊断与分期` | 其他 | `other` |
| `05_影像` | CT | `CT` |
| `05_影像` | MRI | `MRI` |
| `05_影像` | PET-CT | `PET-CT` |
| `05_影像` | 超声 | `ultrasound` |
| `05_影像` | X光DR | `xray_dr` |
| `05_影像` | 核医学 | `nuclear_medicine` |
| `05_影像` | 内镜影像 | `endoscopy_imaging` |
| `05_影像` | 其他 | `other` |
| `06_分子与组学` | NGS报告 | `ngs` |
| `06_分子与组学` | 免疫组化 | `ihc` |
| `06_分子与组学` | 胚系检测 | `germline_panel` |
| `06_分子与组学` | WES-WGS | `wes_wgs` |
| `06_分子与组学` | 转录组 | `transcriptome` |
| `06_分子与组学` | 甲基化 | `methylation` |
| `06_分子与组学` | 蛋白-代谢 | `proteomics_metabolomics` |
| `06_分子与组学` | 微生物组 | `microbiome` |
| `06_分子与组学` | 其他 | `other` |
| `07_检验` | 血常规 | `cbc` |
| `07_检验` | 生化肝肾功 | `biochemistry` |
| `07_检验` | 肿瘤标志物 | `tumor_markers` |
| `07_检验` | 凝血 | `coagulation` |
| `07_检验` | 尿便 | `urine_stool` |
| `07_检验` | 心电图功能检查 | `ecg_functional` |
| `07_检验` | 其他 | `other` |
| `08_治疗` | 化疗 | `chemo` |
| `08_治疗` | 放疗 | `radiation` |
| `08_治疗` | 免疫治疗 | `immunotherapy` |
| `08_治疗` | 靶向 | `targeted` |
| `08_治疗` | 内分泌 | `endocrine` |
| `08_治疗` | 中医中药 | `tcm` |
| `08_治疗` | 处方医嘱 | `prescriptions_orders` |
| `08_治疗` | 支持治疗 | `supportive` |
| `09_手术与操作` | 手术记录 | `operative_notes` |
| `09_手术与操作` | 麻醉记录 | `anesthesia` |
| `09_手术与操作` | 介入 | `interventional` |
| `09_手术与操作` | 内镜操作 | `endoscopy_procedure` |
| `09_手术与操作` | 植入物-器械卡 | `implant_device_cards` |
| `10_随访与监测` | 随访复查 | `followup_visits` |
| `10_随访与监测` | 可穿戴导出 | `wearable_export` |
| `10_随访与监测` | PRO自报 | `pro_reported` |
| `10_随访与监测` | 居家监测 | `home_monitoring` |
| `11_会诊与转诊` | MDT | `MDT` |
| `11_会诊与转诊` | 会诊 | `consult` |
| `11_会诊与转诊` | 转诊 | `referral` |
| `11_会诊与转诊` | 第二意见 | `second_opinion` |
| `12_心理社会与支持` | 心理评估 | `psych_assessment` |
| `12_心理社会与支持` | 营养 | `nutrition` |
| `12_心理社会与支持` | 康复 | `rehab` |
| `12_心理社会与支持` | 缓和 | `palliative` |
| `12_心理社会与支持` | 社工 | `social_work` |
| `13_行政与财务` | 知情同意 | `informed_consent` |
| `13_行政与财务` | 费用发票 | `bills_invoices` |
| `13_行政与财务` | 医保报销 | `insurance_reimbursement` |
| `13_行政与财务` | 证明材料 | `certificates_admin` |
| `14_患者自管补充` | 患者补充 | `patient_uploads` |
| `14_患者自管补充` | 日记 | `diary` |
| `14_患者自管补充` | 自测 | `self_test` |
| `14_患者自管补充` | conversation_notes | `conversation_notes` |

### 1.1b Empty-bucket policy (lazy creation — never pre-scaffold an empty domain)

**A clinical bucket is created on disk only when a sidecar is actually filed into it** (Phase 2 `mkdir -p <bucket>` immediately before writing each sidecar; setup creates **only `ocr/` + `raw/`**, never the 14 domains up front — see `SKILL.md` Step 2). The reason is a patient-safety one: **an empty folder must not imply "no such record exists".** A pre-created empty `09_手术与操作/` reads to a human (and to a downstream skill scanning the tree) as "no surgery" — which is a silent, dangerous lie when the discharge summary states a resection was performed but the operative note simply wasn't among the uploaded files. With lazy creation, an absent `09_手术与操作/` truthfully means **"no surgery document was filed"**, and the authoritative channel for "a record is expected for this domain but missing" is `missing_items.json` (cancer-type checklist diff), **not** an empty folder.

If a host binding insists on pre-creating buckets, it MUST, at the end of the run, for every bucket left empty, **either remove it OR annotate it in `INDEX.md`** as `该桶为空：源材料未提供原始X`（X = that domain, e.g. 手术记录）— an empty folder may never sit silently in the tree implying the record exists or that its domain was checked and found clear. The lazy-create path above is the default because it makes this invariant hold structurally.

### 1.2 Infrastructure buckets (hidden, never anchored)

| key | `zh` slug | `en` slug | visible? | anchored? | role |
|---|---|---|---|---|---|
| `raw/` | `raw` | `raw` | **no (HIDDEN)** | never | **un-redacted vault of every uploaded original**, one copy per upload, stored at `raw/<original_subdir>/<de-identified-basename>`. raw/ keeps every uploaded original's BYTES verbatim (never byte-altered, never pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by Phase 1 (identity token stripped; if the whole basename is the identity, fall back to `<source_id>.<ext>`) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared surface. The verbatim original filename is preserved ONLY in raw/_FILENAME_MAPPING.md (inside raw/, excluded from export, never a delivered/scanned surface). The original sub-folder structure is preserved; the `file_id`↔`raw_path` link lives in `source_inventory.json`. The frontend deep-links a sidecar back to its original here (see §4). **Never pixel-redacted** (image-level 段B redaction is removed — see §5). |
| `99_` | `99_无关文件` | `99_unrelated` | **no (quarantine)** | never | `high_confidence/ uncertain/` relevance quarantine, outside the clinical scheme. |

`raw/` and `99_` are **never patient-visible scaffold** and **never anchor targets** (anchors point
only at the bucket `.md` sidecars; downstream never reads `99_`). `raw/` is the single store of
originals **as uploaded** — it replaces the former `90_原始文件镜像` byte mirror. Because the originals
are no longer pixel-redacted, there is no separate "redacted vs mirror" copy: `raw/` holds the
verbatim upload, and each clinical-domain `.md` sidecar links back to it via
`source_inventory.json.raw_path` (+ `page_range` for a multi-document source).

> Subdir rule: under any bucket the parent `NN_` prefix is stable; the subdir slug is **one of the
> two pinned forms** — `zh` when `locale=zh`, `en` for every other locale (see §1.1a). Subdir slugs
> are **never runtime-translated** into other languages. `high_confidence` / `uncertain` /
> `conversation_notes` are ASCII keys and stay as-is across locales.
>
> **`conversation_notes/` is cross-domain, not exclusive to `14_`.** A 段C conversation fact is
> archived under the `conversation_notes/` subdir of its **corresponding clinical domain** (e.g. a
> lab value → `07_检验/conversation_notes/`, a staging change → `04_诊断与分期/conversation_notes/`),
> falling back to `14_患者自管补充/conversation_notes/` only when the fact fits no clinical domain
> (matches `schemas/anchor-contract.md` §1 and `conversation-incremental-prompt.md`). The `14_` row
> above lists it because `14_` is the fallback home, not its only home.

### 1.3 Classification disambiguation (judge by clinical context, not a title keyword)

The 14-domain scheme is filed by **LLM judgment of content** (`organizer-prompt-phase2-synthesis.md` Step 1a) — never a keyword match on the filename. Known traps:

- **Inpatient 体温单 / 护理生命体征记录 / 出入量单 → `03_病程与叙事文书/病程记录`, never `10_随访与监测`.** `10_随访与监测` is **outpatient-only** (门诊随访 / wearable / PRO自报 / 居家监测). If a "生命体征 / 体温 / 趋势" file's recording window falls inside an admission (ward + continuous inpatient dates), it is a hospitalization record → `03`. The words "趋势 / 监测 / 生命体征" in a title are a keyword trap — do not route to `10` on that basis.
- **心电图 / 心电监测 / 肺功能 等功能检查 → `07_检验/心电图功能检查`** (functional/physiologic studies — not specimen labs, not imaging).
- `10_随访与监测` positive examples: post-discharge outpatient re-check, Apple Health / wristband export, patient-reported symptom diary, home BP/glucose logs. The same record type recorded *during* an admission goes to `03`.

## 2. Modality tag (orthogonal attribute)

Every filed source records a `modality` in `source_inventory.json` (the authoritative location); typed
ingest adapters (omics/timeseries) MAY additionally echo it as an OPTIONAL `MODALITY:` line in the
sidecar header (per organizer-prompt-phase1-ocr.md — the header field is optional, `source_inventory.json`
is authoritative). It describes the **data nature**, independent of the clinical domain, and drives
ingest-parser dispatch.

| `modality` | meaning | example | ingest path |
|---|---|---|---|
| `text` | prose / OCR'd document | discharge summary, pathology narrative | LLM Markdown ingestion (§ phase1) |
| `image` | imaging / scan, stub-summarized | CT series, IHC slide photo | LLM vision stub |
| `structured` | tabular numeric report | CBC panel, biochemistry sheet | LLM table → Markdown table |
| `omics_raw` | parseable omics payload | VCF / annotated TSV / expression-methylation matrix | omics ingest adapter (§ ingest-adapters) |
| `timeseries` | longitudinal stream | wearable export, glucose log, PRO diary | timeseries ingest adapter → `longitudinal_observations[]` |
| `binary_other` | unsupported/opaque binary | BAM / FASTQ / DICOM raw / proprietary export | stub + `[INGESTION_BLOCKED]`, never silently dropped |

A single source may emit **one bucket file + one modality**; a compound source (NGS report PDF +
its VCF) is two `source_inventory` entries (`text` report → `06`, `omics_raw` VCF → `06`).

Per-modality ingestion behavior (what sidecar + structured output each modality produces) is defined
in [`ingest-adapters.md`](ingest-adapters.md) — dispatch reads this `modality` value.

## 3. Longitudinal store (streams, not buckets)

`timeseries` (and trended `structured`) sources do **not** become a pile of dated documents. Their
parsed observations accumulate in `<patient_dir>/longitudinal_observations.json` beside
`profile.json` (schema: `schemas/longitudinal_observations.schema.json`). The **raw export file**
is still filed (domain `10_随访与监测/可穿戴导出` or `/PRO自报`) and the observations carry a
`source_ref` anchor back to it.

```
longitudinal_observations[] := {
  obs_type: "vital|lab|symptom|pro|adherence|activity",
  metric:   "<name, verbatim>",        # e.g. "HbA1c", "resting_hr", "ECOG"
  value:    <number|string>,
  unit:     "<unit, verbatim>",
  timestamp:"<ISO8601>",
  modality: "timeseries|structured",
  source_ref:"10_随访与监测/可穿戴导出/<file>.md#L.."  # or conversation:<ISO8601>
}
```

This is the substrate for **单时间点 → 多时间点 → 纵向曲线 → 治疗反应轨迹**. `profile.json` keeps a
`latest_status` snapshot AND points consumers at `longitudinal_observations.json` for the trajectory.

## 4. Source ↔ sidecar mapping (frontend deep-link)

Every uploaded original lives once under `raw/`, preserving its original sub-folder structure
(`raw/<original_subdir>/<de-identified-basename>`). raw/ keeps every uploaded original's BYTES verbatim
(never byte-altered, never pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by
Phase 1 (identity token stripped; if the whole basename is the identity, fall back to
`<source_id>.<ext>`) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared
surface. The verbatim original filename is preserved ONLY in raw/_FILENAME_MAPPING.md (inside raw/,
excluded from export, never a delivered/scanned surface). Every clinical `.md` sidecar is one **content unit**
(one document type extracted from a source). The 1:1 code is `file_id`; the link between a sidecar and
its original is carried in `source_inventory.json` (one row per content unit) and surfaced in `INDEX.md`:

```
content unit := {
  file_id:    "<stable id, 1:1 with this sidecar>",   # e.g. f001
  source_id:  "<id of the upload it came from>",        # e.g. s001  (N content units may share one source_id)
  sidecar_path: "04_诊断与分期/病理报告/2024-03-15_病理报告_中山六院.md",
  raw_path:   "raw/2024-Q1/discharge_2024-03-15.pdf",   # the un-redacted original (bytes verbatim) in raw/, de-identified filename; verbatim name only in raw/_FILENAME_MAPPING.md
  page_range: "3-5"                                      # which pages of a multi-document source; null if whole file
}
```

- **One upload → many content units** (a PDF that is discharge summary + labs + pathology): one
  `raw/` file, **multiple sidecars** each with its own `file_id`, all sharing `source_id`, each with a
  distinct `page_range`. The frontend renders the `.md` and offers a "view original" button →
  `raw_path` (deep-linked to `page_range` when present).
- `file_id` is 1:1 with a sidecar; `source_id` is 1:1 with an upload. Two distinct `raw/` audit files (never the same file): **`_FILENAME_MAPPING.md`** = Phase-1 verbatim-name audit table (`verbatim_upload_name | deid_raw_name | source_id` — the ONLY surviving copy of the real upload name, excluded from export); **`_SIDECAR_MAP.md`** = Phase-2 de-identified raw→sidecar→bucket nav table (no verbatim name). `source_inventory.json` is the machine-readable reverse lookup.

## 5. Redaction policy (image-level 段B removed)

- **Originals in `raw/` are kept verbatim and are never pixel-redacted.** The image-level redaction job
  (段B: `redaction_manifest`/`redaction_status`/`source_redaction_status` + `run_redaction_job.py` +
  `redaction-job.md`) is **removed** — there is no redact-then-delete of originals.
- **Sidecar text PII masking stays.** Phase 1 still masks PII in the `.md` sidecar body
  (`phase1-ocr.md §2.4`) and `pii_rescan.py` still rescans the text — the sidecar remains the
  downstream-only read source with no plaintext PII, so structured JSONs and patient-facing answers
  stay de-identified.
- **段E (unrelated-file deletion) is unchanged** — high-confidence non-medical files are still
  auto-deleted on no-confirm; that privacy floor is independent of 段B.
- Net: the patient keeps every original as uploaded (frontend can show it), while downstream artifacts
  built from the text sidecars remain desensitized.

## 6. Clean replacement — no backward compatibility

v3 **fully replaces** the prior scheme. There is **no migration of existing patient directories** and
**no compatibility layer**: old `NN_` prefixes are not aliased, old anchors are not rewritten in
place. Any directory organized under the old scheme is simply re-run through `organize` to land on
v3 — pre-revenue, this is the cheaper and cleaner path than a re-anchor migration. Downstream skills
read the v3 prefixes only; they do not need to recognize legacy `00_/02_诊断…/10_原始文件` layouts.

The "from v2" column in §1.1 / §1.2 is **provenance for the reader** (why each domain exists), not a
migration instruction — nothing reads it at runtime.
