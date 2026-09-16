⚠️ SHARED CONTRACT — this file is duplicated in cancer-buddy-skill and vmtb-skill. Any edit MUST be mirrored to the other repo. Producer = cancer-buddy-organize; consumer = cancerdao-vmtb (skip-organize).

> **Mirror status (2026-09-17, scheme_version 4)**: the `references/organize/` mirror is **absent** from the live `CancerDAO/vmtb-skill` default branch and its active feature branches; it survives only in detached local copies. The active SMTB consumer (`smtb-skill`, `scripts/facts.py`) resolves provenance from `source_ref` path prefixes and does not enumerate bucket directories — `15_` is never a `source_ref` target (§3.2), so it needs no consumer change. Re-establishing the mirror is a vmtb-side task; until then this file is the only authoritative copy.

# PATIENT_DIR_CONTRACT — the on-disk patient archive (SHARED-1)

This is the **single cross-repo interface contract** for the on-disk patient archive that
`cancer-buddy-organize` **PRODUCES** and `vmtb-skill` **CONSUMES** (in skip-organize mode). It is
narrower and more stable than either repo's internal docs: a consumer that programs against ONLY
what is written here will not break when either side iterates its private layout. If this file and a
repo-internal doc disagree on the interop surface (§5) or the producer/consumer boundary (§6), **this
file wins and the other is a drift bug to fix**.

- Producer-authoritative deep docs (cancer-buddy-skill): `references/bucket-taxonomy.md` +
  `references/bucket_taxonomy.json` (bucket scheme, `scheme_version 4`), `references/schemas/patient_summary.schema.json`
  + `references/schemas/readiness.schema.json` (profile / readiness field contract),
  `skills/cancer-buddy-organize/SKILL.md` (the write pipeline).
- Consumer entry (vmtb-skill): `skills/cancerdao-vmtb/SKILL.md` (skip-organize probe, readiness
  gate, deepdive glob), `references/organize/organize-binding-vmtb.md` (vMTB's deviations from the
  cancer-buddy v3 contract). **The `references/organize/` mirror is currently ABSENT on the
  vmtb-skill side (see the mirror-status note above) — where it is missing, THIS FILE is the
  authoritative copy; a missing mirror is not a second, differing contract.**

---

## 1. Location is configurable — the internal structure is FIXED

`patient_data_root` (the directory that holds one sub-directory per patient) is resolved by BOTH
skills from the same precedence chain:

```
$CANCER_BUDDY_PATIENTS_DIR  →  $VMTB_PATIENT_DATA_ROOT  →  $HOME/CancerDAO/patients
```

(vMTB additionally accepts a CLI `--patient-data-root` that wins over env; cancer-buddy-organize
takes a caller arg. The env-chain above is the shared fallback both honor.)

**Regardless of which root wins, the internal structure is FIXED and MUST NOT be renamed by a caller:**

```
<patient_data_root>/
└── <patient_code>/                     # one dir per patient (§2)
    ├── profile.json  patient_summary.json  molecular.json  …   # canonical file set (§4)
    ├── 01_…/ … 14_…/                    # 14 anchored clinical domains (§3)
    ├── 15_未分类资料/                     # open bucket — NEVER an anchor target (§3)
    │   └── <slug>/                      # model-generated slug, whitelist regex (§3)
    ├── 99_…/                            # relevance quarantine (likely_unrelated only)
    ├── raw/                             # access-controlled vault — NEVER an anchor target
    │   ├── <de-identified originals>    # uploaded bytes, verbatim
    │   ├── transcript/
    │   │   └── <source_id>/page-NNN.md  # VERBATIM transcription; never enters downstream
    │   │                                #   context; excluded from every export
    │   ├── adapter_views/
    │   │   └── <source_id>/page-NNN.png|.txt|.ocr.txt   # 段 0 renders + text layers
    │   ├── _cache/
    │   │   └── transcripts/
    │   │       └── <sha256(image)>.<sha256(text_layer)[:16]>.<prompt_version>.<model_id>.md
    │   └── _provenance/
    │       └── <run_id>/
    │           ├── transcribe-manifest.json   # one row per page (see §3)
    │           ├── pages.json                 # 段 0 page packages
    │           ├── second-read-plan.json      # 段 1.5 per-page verification batches
    │           └── …                          # human spot-check record
    ├── runs/
    │   └── <run_id>/                    # vMTB per-run artifacts; run_id = YYYYMMDD_HHMMSS
    │       ├── chair_corrections.json   # consumer-side correction overlay (§6)
    │       ├── profile_resolved.json    # consumer-side flat projection (§6)
    │       └── …                        # chair report, evidence graph, delivery/
    └── reports/
        └── mtb-full/                    # published delivery pack location (not proof of clinical validity)
            └── delivery/                # 8 HTML + 8 PDF + REVIEW_CHECKLIST.md
```

- Producer (`cancer-buddy-organize`) writes everything directly under `<patient_code>/` (§4) plus
  the buckets (§3).
- Consumer (`cancerdao-vmtb`) writes ONLY under `runs/<run_id>/` and `reports/` (§6). `run_id` is a
  `YYYYMMDD_HHMMSS` timestamp. The delivery pack lands at `reports/mtb-full/delivery/`.

Callers **may redirect the root** (env / CLI) but **MUST NOT rename the internal layout** — the
`<patient_code>/…`, `runs/<run_id>/`, and `reports/mtb-full/delivery/` paths are the interop contract.

---

## 2. `patient_code` (the per-patient directory name)

- **Value**: generated from cryptographically random bytes as `PT-<hex>` (for example
  synthetic `PT-A1B2C3D4E5`). Never derive it from a filename, path, diagnosis, timestamp, name, medical-record
  number, or other patient data.
- **Invariant**: the code is a storage locator, not identity, consent, or authorization. Reject a supplied
  real-world identifier and generate a new random code; do not preserve recognizable substrings or append
  a deterministic hash.
- **Consumer rule**: accept the `PT-<hex>` form declared on the first line of `INDEX.md` and mirrored in
  `profile.json.patient_code`. A separately protected optional alias must be non-clinical and
  non-identifying; it never replaces the canonical random locator.

---

## 3. Bucket taxonomy (v4, `scheme_version 4`)

The visible buckets are **14 pinned clinical domains + 1 open bucket**, each with a two-digit `NN_`
prefix. The **machine-readable source is `bucket_taxonomy.json`** (producer repo:
`skills/cancer-buddy-organize/references/bucket_taxonomy.json`) — a consumer that needs to enumerate
buckets reads that JSON, it does NOT re-hardcode the list. **The vmtb-side
`references/organize/bucket_taxonomy.json` mirror is currently missing; where the mirror is absent,
the producer copy named above is authoritative.** Re-establishing the mirror is a vmtb-side task,
not a licence to fork the list. The 14 clinical domains:

```
01_身份与基础信息   02_既往史与家族史   03_病程与叙事文书   04_诊断与分期      05_影像
06_分子与组学       07_检验             08_治疗             09_手术与操作      10_随访与监测
11_会诊与转诊       12_心理社会与支持   13_行政与财务       14_患者自管补充
```

plus the **open bucket**:

```
15_未分类资料   (en: 15_unclassified)   open_sub_buckets: true
```

(zh slugs shown; `locale≠zh` uses the pinned `en` set — `01_identity_basics … 14_patient_supplement`,
`15_unclassified`. The **pinned typed sub-buckets** per domain — e.g.
`04_诊断与分期/{病理报告,诊断证明,分期评估,其他}`, `06_分子与组学/{NGS报告,免疫组化,…}` — are
enumerated in `bucket_taxonomy.json`; do not re-list here.)

### 3.1 `15_未分类资料` — the open bucket

`15_` holds material whose **document type is not in the taxonomy at all** (a new sequencing
vendor's custom panel, a microbiome report, an unfamiliar scoring instrument) — not material the
producer was merely unsure how to file, and **not material that was merely hard to read**.

**`15_` admits `kind: novel` and nothing else** — a *type* gap, never a *quality* gap. A blurred,
truncated or low-quality page (`possibly_relevant`) stays in its **best-matching `01_…14_` bucket**
with `kind: unreadable` plus a `review_flags[]` entry carrying `category: coverage_gap` and
`audience: internal_qc`. The gate binds this both ways: every sidecar under `15_` has an inventory
row with `kind == novel` and `novel_reason` ≥ 8 chars, and every `kind: novel` row has its sidecar
under `15_`. Either direction failing is an ERROR.

Its sub-buckets are **not pinned**: one `<slug>/` per novel
type, where the slug is model-generated and validated against a whitelist regex before `mkdir`:

```
^[一-鿿A-Za-z0-9][一-鿿A-Za-z0-9-]{1,23}$
```

| rule | value |
|---|---|
| charset | CJK + Latin letters + digits + hyphen |
| length | 2–24 characters; first character is not a hyphen |
| must not equal | any pinned sub-bucket slug (`zh` or `en`), any `ascii_infra_dirs` key (`high_confidence` / `uncertain` / `conversation_notes`), any `universal_fallback_sub_buckets` value (`其他` / `other`) |
| must not start with | `NN_` (two digits + underscore) |
| must not contain | `.` `/` `\` `..` or any control character |

The gate asserts this regex on **every** `15_` sub-directory; it does not blanket-allow anything
under `15_`. The slug is a path component derived from an untrusted transcription, so validation is a
security boundary, not a style rule.

Every `15_` source still carries a full `source_inventory` row: `kind: novel`, a required
`novel_reason` (≥8 chars), and a required `clinical_class ∈ {molecular, lab, imaging, pathology,
narrative, admin, unknown}`.

### 3.2 `15_` vs `99_` and the anchor rule

- **`15_` is an open archive, not a quarantine.** `novel` material is transcribed, masked, filed and
  inventoried exactly like `01_…14_` material; it is **never automatically deleted** and never
  demoted into `99_`. `99_无关文件/` holds `likely_unrelated` only.
- **`15_` is NEVER an anchor target** — the same rule that already covers `raw/` and `99_`. Anchors
  (`[[src:…]]` / `source_refs[]`) resolve only to `01_…14_` sidecars. A fact that exists only in a
  `15_` source is referenced through `extracted_fields.json`'s own
  `open_ref = {source_id, page, bbox}` (pointing at the `raw/` page, not a bucket path), and **open
  fields never enter a confirmed-fact surface**. `extracted_fields.json` is also not a legal source
  store for charts or core-completeness.
- **Consumers decide whether to read `15_` from the row's `clinical_class`**, never from the slug
  and never from the path. A `15_` source with `clinical_class: molecular` is subject to the same
  molecular completeness gate as one filed in `06_`; a consumer that enumerates only `01_…14_` when
  looking for molecular evidence will silently miss it, so enumerate by `clinical_class`.
- A row with `kind: unreadable` is **never counted as covered** by any patient-facing surface; it
  appears in `readiness.json.projection_coverage.summary.unreadable_sources`.

**Rules a consumer MUST rely on:**

- **The `NN_` two-digit prefix is the language-independent STABLE key.** Match on `^[0-9]{2}_` — never
  on the localized slug. The **localized slug is NOT stable across locales** (two pinned sets only: `zh`
  when `locale=zh`, `en` for every other locale — fr/es/de/… all use the `en` column, never a
  runtime-translated slug). To glob a domain regardless of locale, key on `NN_` (e.g. vMTB's deepdive
  stage globs `<patient_dir>/[01][0-9]_*/**/*.md`).
- **Buckets are lazily created.** A domain dir exists on disk **iff** the archive actually filed a
  record for it. **An absent bucket means "no source was filed for this domain", NOT "scaffold missing"
  or "domain checked and clear"** — never treat an absent `09_手术与操作/` as "no surgery"; the
  existing-document inventory channel is `missing_items.json`; absence never means a test is indicated.
- **`raw/`, `99_无关文件/` and `15_未分类资料/` are NEVER anchor targets.** `raw/` is the hidden
  verbatim vault of uploaded originals (never pixel-redacted, filename de-identified) and now also
  holds `raw/transcript/`, `raw/_cache/transcripts/` and `raw/_provenance/<run_id>/`; `99_无关文件/`
  is the relevance quarantine (`high_confidence/ uncertain/`); `15_未分类资料/` is the open archive
  (§3.1). Downstream never reads `99_`, reads `15_` only by `clinical_class`, and anchors point only
  at the `01_…14_` clinical-domain `.md` sidecars.
- **`raw/transcript/<source_id>/page-NNN.md` is the VERBATIM transcription layer.** It is under the
  same access control as `raw/` and is **excluded from every export**. Its readers are exactly two:
  **deterministic scripts** (`ingest_transcripts.py`, `verify_native_text.py`, and `export_share.py`
  to exclude it) and **an authorized human** doing the spot-check. It **never enters any downstream
  context** — not the synthesis stage, not the faithfulness stage (which compares against the `raw/`
  page `bbox` / `text_layer_offset`, never against the transcript), not the PII semantic scan. A
  consumer that reads it is violating this contract. `raw/_cache/transcripts/` (content-addressed
  transcription cache, keyed `sha256(page image) + prompt_version + model_id`) and
  `raw/_provenance/<run_id>/` (`transcribe-manifest.json`, `pages.json`, `second-read-plan.json`,
  the human spot-check record) are likewise producer-internal and non-anchorable.
- **`ocr/` is absent in a completed run** — it is transient 段 1 staging for the **masked**
  per-page Markdown, drained into the buckets by 段 2 and then **deleted** (including `ocr/_inbox/`
  and `ocr/_reports/`). A non-empty `ocr/` at the end of a run is an ERROR that lists the residue.
  If you see `ocr/`, the archive is mid-run or a 段 2 relocation failed. (`ocr/` is the masked staging dir; `raw/transcript/` is the
  verbatim one and is permanent.)
- **Sidecar `.md` files live co-located inside their domain bucket** (e.g.
  `04_诊断与分期/病理报告/2024-03-15_病理报告_示例医院.md`). The uploaded original is NOT copied into
  the bucket — it lives once in `raw/`, deep-linked from each sidecar via `source_inventory.json.raw_path`.

---

## 4. Canonical file set at `<patient_data_root>/<patient_code>/`

One-line purpose each (producer writes all of these; the conditional ones only when applicable):

| File | Purpose |
|---|---|
| `profile.json` | Slim first-read index with provenance/verification state; `patient_code` is not identity authentication. |
| `patient_summary.json` | Source-preserving rollup; structured fields are not clinically authoritative merely because they are normalized. |
| `molecular.json` | Source-preserving report, sample, assay, quality and result records; no actionability inference. |
| `treatment_lines.json` | Chronological treatment episodes; line labels only when clinician-documented. |
| `labs.json` | Lab panels with serial values. |
| `comorbidities.json` | Conditions + long-term meds + allergies. |
| `timeline.json` | Machine-readable mirror of `timeline.md`. |
| `timeline.md` | Human-readable treatment timeline (every line carries a `[[src:…]]` anchor). |
| `readiness.json` | Documentation coverage, `projection_coverage` (which field classes exist in full text but were not projected into a known slot), and source/faithfulness review flags each carrying `audience ∈ {clinician, internal_qc}` and a `category` enum; no A–F clinical readiness grade. |
| `source_inventory.json` | `source_inventory_v2` (`scheme_version 4`): one row per content unit with `file_id ↔ source_id ↔ sidecar ↔ raw_path ↔ page_range ↔ modality`, plus `kind`, `doc_kind`, `clinical_class`, `text_layer_kind`, `novel_reason`, `reread_channel`, `transcript_path`, extraction engine/version/raw-output provenance, bounded LLM role, and high-risk reread status. The frontend deep-link map, not an authorization record. |
| `missing_items.json` | Compatibility filename for `document_gaps[]`: existing records not found/unknown/requested by a clinician; never a test recommendation. |
| `extracted_fields.json` | Open key-values projected from novel/unmapped material, each with its own `open_ref = {source_id, page, bbox}` — **conditional** (only when such material exists). NOT an anchor source, NOT a confirmed-fact surface, and NOT a legal source store for charts or core-completeness. |
| `update_log.json` | Append-only audit trail of every full / incremental run. |
| `case_text.md` | Consolidated narrative; every factual sentence anchored via `[[src:<bucket>/<file>.md#L<a>-L<b>]]`. |
| `INDEX.md` | File manifest; **first line is `# patient_code: <code>`**. |
| `AGENTS.md` | Agent-facing cross-session recall pointer (routing table + two-layer drill-down rule + citation floor), filled from `profile.json`. |
| `review_summary.md` | 1-page extracted-field spot-check with verbatim source citations (always written). |
| `review_flags.md` | Human-readable rendering of `readiness.json.review_flags[]` — **conditional** (only when the array is non-empty). |
| `longitudinal_observations.json` | Parsed time series (wearable / PRO / lab trends) — **conditional** (only when timeseries/trended data exists; absent otherwise). |
| `病情简要总结.html` | Purpose-limited patient-facing summary. Include age or other quasi-identifiers only when necessary and authorized; direct identifiers are excluded from the derived surface. |
| `gap_asks.json` | Ledger of which existing-document categories were asked about, when, through which channel, and the outcome (`pending` / `answered` / `declined`) — so a category the patient declined is not re-asked every run. Never a clinical judgement; see `gap-followup.md`. **Conditional** (only once something has been asked). |
| `case_summary_versions/` | Previous renderings of `病情简要总结.html`, retained (never overwritten, never deleted) when the summary is regenerated. **Conditional**. |
| `library/index.json` | Index of the reusable reference library attached to this archive (schema: `schemas/library_index.schema.json`). **Conditional**. |
| `raw/_FILENAME_MAPPING.md` | 段 1 verbatim-upload-name audit table (`verbatim_upload_name \| deid_raw_name \| source_id`) — the ONLY surviving copy of the real upload name. Under `raw/` access control and **excluded from every export**. |

---

## 5. THE INTEROP SURFACE (what consumers may rely on)

**`profile.json` is the stable primary read.** Program against these guarantees:

- **Branch on the `schema` string.** Its value is in the family `cancer_buddy_profile_v*`
  (**current: `cancer_buddy_profile_v3`**). A consumer MUST branch on `schema` / `schema_version` — never
  assume a single frozen shape.
- **Diagnosis is NESTED under `summary`** (v3 shape), NOT flat top-level:
  cancer type = **`summary.primary`**, histology = **`summary.histology`**, stage = **`summary.stage`**.
  (The old flat `primary_cancer` / `histology` / `stage` at top level is a `*_v1`-era shape.)
- **Storage locations by domain**: molecular records → `molecular.json`; treatment episodes →
  `treatment_lines.json`; structured diagnosis records → `patient_summary.json`. These files are
  authoritative only for archive location/schema, not for clinical correctness. On disagreement, preserve
  all sources and `disputed` state rather than selecting a winner.

**Consumers MUST:**

- **(a)** branch on the `schema` / `schema_version` string (never hardcode one shape);
- **(b)** tolerate BOTH the strict schema shapes AND the looser hand-authored `*_v1` shapes seen in
  real archives. Concretely, defend against these real variances:
  - `molecular.json` may be `variants[]` **OR** `somatic_variants[]` + `germline_variants[]` + `biomarkers{}`;
  - `patient_summary` diagnosis may be `.primary` **OR** `.primary_site`;
  - `source_inventory.json` may be `files[]` **OR** `entries[]`.
- **Never assume bucket names beyond the `NN_` prefix** (§3) — the localized slug is not stable.
- **Branch on `scheme_version`** in `bucket_taxonomy.json` / `source_inventory.json`: accept `4`
  (14 pinned domains + the `15_` open bucket) and continue to accept `3` (14 domains only). A `15_`
  path appearing in any `source_refs[]` is a producer bug, not a new anchor form.
- **Route on `clinical_class`, not on the bucket path**, when looking for molecular / lab evidence —
  a novel source with real molecular content can live under `15_未分类资料/<slug>/`.
- **Never read anything under `raw/` except what `source_inventory.json` references** — in
  particular never `raw/transcript/`, `raw/_cache/`, `raw/_provenance/` or `raw/adapter_views/`,
  and never include any of them in an export.
- **Two different `verification_status`-shaped enums exist — branch on which file you are reading:**

  | where | field | enum |
  |---|---|---|
  | `patient_summary.json` / `molecular.json` / `treatment_lines.json` / `labs.json` / `comorbidities.json` / `profile.json` | `verification_status` | `unverified` \| `clinician_verified` \| `disputed` |
  | `timeline.json` (events **only**) | `verification_status` | `unverified` \| `clinician_verified` \| `disputed` \| **`withdrawn`** — the source retracted the event; a retracted event is not evidence and admits no consumer value |
  | `extracted_fields.json` (open fields only) | **`open_verification_status`** | `unverified` \| `settled` \| `needs_human_review` |

  They are **not interchangeable**. `settled` on an open field means "two channels read the same
  string" — a transcription statement. `clinician_verified` on a structured field means a clinician
  signed off — a clinical statement. A consumer that maps one onto the other turns an un-anchored,
  un-gated open key-value into a clinician-verified fact. The second-read outcome for a high-risk
  field is a **third**, separate vocabulary carried by `source_inventory.json`'s
  `high_risk_fields[].status: passed_independent_reread`, and it is the only one that means "passed a
  channel-independent second read".
- `patient_code` is the only universal locator field and is not authentication. Missing diagnosis fields
  remain unknown; consumers may continue stable general help but must not generate patient-specific
  clinical conclusions. All consumers tolerate missing optional fields without throwing.

---

## 6. Producer / consumer boundary

- **`cancer-buddy-organize` WRITES everything under `<patient_code>/`** — the archive file set (§4),
  the buckets (§3), `raw/`. It is the sole storage-contract writer of `profile.json` / `readiness.json` /
  `timeline.*` / the structured JSONs.
- **`cancerdao-vmtb` in skip-organize mode READS that archive** (probe: `profile.json` AND
  `readiness.json` both exist → treat as pre-organized, do NOT re-run organize, do NOT recompute
  readiness) **and writes ONLY under `runs/<run_id>/` + `reports/`.** It **MUST NOT mutate any
  organize-produced file** under `<patient_code>/`.
  - **Corrections** a vMTB run needs to apply to an upstream fact go into an **overlay**, not a
    mutation: `runs/<run_id>/chair_corrections.json` (`{staging_corrections[], fact_corrections[]}`).
  - The **flat projection** a run's delivery layer reads is materialized at
    `runs/<run_id>/profile_resolved.json` — the corrections overlaid onto a flat profile in memory,
    written per-run. `profile.json` itself is never touched.

This boundary is what makes the archive safe to re-consume: an organize re-run (or a different
consumer) always finds the producer's files exactly as written, and each vMTB run's mutations are
quarantined inside its own `runs/<run_id>/`.
