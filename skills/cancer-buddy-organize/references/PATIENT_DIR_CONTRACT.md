⚠️ SHARED CONTRACT — this file is duplicated in cancer-buddy-skill and vmtb-skill. Any edit MUST be mirrored to the other repo. Producer = cancer-buddy-organize; consumer = cancerdao-vmtb (skip-organize).

# PATIENT_DIR_CONTRACT — the on-disk patient archive (SHARED-1)

This is the **single cross-repo source of truth** for the on-disk patient archive that
`cancer-buddy-organize` **PRODUCES** and `vmtb-skill` **CONSUMES** (in skip-organize mode). It is
narrower and more stable than either repo's internal docs: a consumer that programs against ONLY
what is written here will not break when either side iterates its private layout. If this file and a
repo-internal doc disagree on the interop surface (§5) or the producer/consumer boundary (§6), **this
file wins and the other is a drift bug to fix**.

- Producer-authoritative deep docs (cancer-buddy-skill): `references/bucket-taxonomy.md` +
  `references/bucket_taxonomy.json` (bucket scheme, `scheme_version 3`), `references/patient-profile-schema.md`
  (profile / readiness field contract), `skills/cancer-buddy-organize/SKILL.md` (the write pipeline).
- Consumer entry (vmtb-skill): `skills/cancerdao-vmtb/SKILL.md` (Step 2 skip-organize, Step 3
  readiness gate, Step 3.25 deepdive glob), `references/organize/organize-binding-vmtb.md` (vMTB's
  deviations from the cancer-buddy v3 contract).

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
    ├── 01_…/ … 14_…/  raw/  99_…/       # bucket taxonomy (§3)
    ├── runs/
    │   └── <run_id>/                    # vMTB per-run artifacts; run_id = YYYYMMDD_HHMMSS
    │       ├── chair_corrections.json   # consumer-side correction overlay (§6)
    │       ├── profile_resolved.json    # consumer-side flat projection (§6)
    │       └── …                        # chair report, evidence graph, delivery/
    └── reports/
        └── mtb-full/                    # canonical published delivery pack location
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

- **Value**: caller-supplied OR auto-generated `PT-<hex>` (e.g. `PT-17CE02BC33`) — cancer-buddy
  auto-derives from `hash(input basename + mtime)`; vMTB auto-derives from a hash when none is passed.
- **Invariant**: the code MUST be **de-identified and whitespace-free**. A caller code containing a
  real name (CJK / non-ASCII) or spaces (e.g. `"023 兰芳"`) is **slugified**, never used verbatim —
  the ASCII-safe alnum tokens are kept, non-ASCII tokens dropped, and a short deterministic hash is
  appended (→ e.g. `023-a1b2c3d4`); if nothing ASCII-safe survives → `PT-<HEX>`. This guarantees the
  on-disk path leaks no real name and never word-splits in an unquoted shell command. Cross-ref the
  canonical de-identifier: vmtb `scripts/utils/patient_code.py`.
- **Consumer rule**: accept EITHER an auto `PT-` code OR a caller-supplied slug. **Do NOT hard-reject
  a directory on a `PT-` regex** — a legitimately organized patient may have a caller code like
  `48C507_CRC_2022` or `023-a1b2c3d4`. The `patient_code` is also declared on the first line of
  `INDEX.md` as `# patient_code: <code>` and mirrored in `profile.json.patient_code`.

---

## 3. Bucket taxonomy (v3, `scheme_version 3`)

The clinical-domain buckets are **14 domains** with a two-digit `NN_` prefix, each with pinned typed
sub-buckets. The **machine-readable source is `bucket_taxonomy.json`** (producer repo:
`skills/cancer-buddy-organize/references/bucket_taxonomy.json`; mirrored in vmtb
`references/organize/`) — a consumer that needs to enumerate buckets reads that JSON, it does NOT
re-hardcode the list. The 14 domains:

```
01_身份与基础信息   02_既往史与家族史   03_病程与叙事文书   04_诊断与分期      05_影像
06_分子与组学       07_检验             08_治疗             09_手术与操作      10_随访与监测
11_会诊与转诊       12_心理社会与支持   13_行政与财务       14_患者自管补充
```

(zh slugs shown; `locale≠zh` uses the pinned `en` set — `01_identity_basics … 14_patient_supplement`.
The **pinned typed sub-buckets** per domain — e.g. `04_诊断与分期/{病理报告,诊断证明,分期评估,其他}`,
`06_分子与组学/{NGS报告,免疫组化,…}` — are enumerated in `bucket_taxonomy.json`; do not re-list here.)

**Rules a consumer MUST rely on:**

- **The `NN_` two-digit prefix is the language-independent STABLE key.** Match on `^[0-9]{2}_` — never
  on the localized slug. The **localized slug is NOT stable across locales** (two pinned sets only: `zh`
  when `locale=zh`, `en` for every other locale — fr/es/de/… all use the `en` column, never a
  runtime-translated slug). To glob a domain regardless of locale, key on `NN_` (e.g. vMTB Step 3.25
  globs `<patient_dir>/[01][0-9]_*/**/*.md`).
- **Buckets are lazily created.** A domain dir exists on disk **iff** the archive actually filed a
  record for it. **An absent bucket means "no source was filed for this domain", NOT "scaffold missing"
  or "domain checked and clear"** — never treat an absent `09_手术与操作/` as "no surgery"; the
  authoritative "expected-but-missing" channel is `missing_items.json`.
- **`raw/` and `99_无关文件/` are NEVER anchor targets.** `raw/` is the hidden verbatim vault of
  uploaded originals (never pixel-redacted, filename de-identified); `99_无关文件/` is the relevance
  quarantine (`high_confidence/ uncertain/`). Downstream never reads `99_`, and anchors point only at
  the clinical-domain `.md` sidecars.
- **`ocr/` is absent in a completed run** — it is transient Phase-1 staging, drained into the buckets
  and removed. If you see `ocr/`, the archive is mid-run or a Phase-2 relocation failed.
- **Sidecar `.md` files live co-located inside their domain bucket** (e.g.
  `04_诊断与分期/病理报告/2024-03-15_病理报告_中山六院.md`). The uploaded original is NOT copied into
  the bucket — it lives once in `raw/`, deep-linked from each sidecar via `source_inventory.json.raw_path`.

---

## 4. Canonical file set at `<patient_data_root>/<patient_code>/`

One-line purpose each (producer writes all of these; the conditional ones only when applicable):

| File | Purpose |
|---|---|
| `profile.json` | **Slim canonical first-read snapshot** — identity + `locale` + denormalized `summary` diagnosis + `latest_status`. The stable primary read (see §5). |
| `patient_summary.json` | Full normalized structured rollup — demographics + diagnosis (icd10/diagnosed_at) + current_status; **authoritative for structured diagnosis fields**. |
| `molecular.json` | NGS variants + IHC + MSI/MMR + TMB (+ optional germline/pharmacogenomics); **authoritative for molecular**. |
| `treatment_lines.json` | Ordered lines of therapy; **authoritative for treatment lines**. |
| `labs.json` | Lab panels with serial values. |
| `comorbidities.json` | Conditions + long-term meds + allergies. |
| `timeline.json` | Machine-readable mirror of `timeline.md`. |
| `timeline.md` | Human-readable treatment timeline (every line carries a `[[src:…]]` anchor). |
| `readiness.json` | MTB readiness — coverage `score`/`grade` (A≥.90 B≥.75 C≥.60 D≥.40 F) + `blocking_gaps[]` + `review_flags[]` (9-check suspicious-value audit). |
| `source_inventory.json` | One row per content unit: `file_id ↔ source_id ↔ sidecar ↔ raw_path ↔ page_range ↔ modality`. The frontend deep-link map. |
| `missing_items.json` | Cancer-type checklist diff — the authoritative "expected-but-missing domain" channel. |
| `update_log.json` | Append-only audit trail of every full / incremental run. |
| `case_text.md` | Consolidated narrative; every factual sentence anchored via `[[src:<bucket>/<file>.md#L<a>-L<b>]]`. |
| `INDEX.md` | File manifest; **first line is `# patient_code: <code>`**. |
| `AGENTS.md` | Agent-facing cross-session recall pointer (routing table + two-layer drill-down rule + citation floor), filled from `profile.json`. |
| `review_summary.md` | 1-page extracted-field spot-check with verbatim source citations (always written). |
| `review_flags.md` | Human-readable rendering of `readiness.json.review_flags[]` — **conditional** (only when the array is non-empty). |
| `longitudinal_observations.json` | Parsed time series (wearable / PRO / lab trends) — **conditional** (only when timeseries/trended data exists; absent otherwise). |
| `病情简要总结.html` | Patient-facing one-page 段D summary (precise age retained for trial matching; name/DOB/birthplace/occupation masked). |

---

## 5. THE INTEROP SURFACE (what consumers may rely on)

**`profile.json` is the stable primary read.** Program against these guarantees:

- **Branch on the `schema` string.** Its value is in the family `cancer_buddy_profile_v*`
  (**current: `cancer_buddy_profile_v3`**). A consumer MUST branch on `schema` / `schema_version` — never
  assume a single frozen shape.
- **Diagnosis is NESTED under `summary`** (v3 shape), NOT flat top-level:
  cancer type = **`summary.primary`**, histology = **`summary.histology`**, stage = **`summary.stage`**.
  (The old flat `primary_cancer` / `histology` / `stage` at top level is a `*_v1`-era shape.)
- **Authoritative sources by domain**: molecular facts → `molecular.json`; treatment lines →
  `treatment_lines.json`; structured diagnosis → `patient_summary.json`. `profile.summary` is a
  **denormalized convenience copy** — cheap to read, but on disagreement the domain file above wins.

**Consumers MUST:**

- **(a)** branch on the `schema` / `schema_version` string (never hardcode one shape);
- **(b)** tolerate BOTH the strict schema shapes AND the looser hand-authored `*_v1` shapes seen in
  real archives. Concretely, defend against these real variances:
  - `molecular.json` may be `variants[]` **OR** `somatic_variants[]` + `germline_variants[]` + `biomarkers{}`;
  - `patient_summary` diagnosis may be `.primary` **OR** `.primary_site`;
  - `source_inventory.json` may be `files[]` **OR** `entries[]`.
- **Never assume bucket names beyond the `NN_` prefix** (§3) — the localized slug is not stable.
- **Minimum fields for any downstream to run**: `patient_code`, `summary.primary`, `summary.histology`,
  `summary.stage`. If any are missing → **prompt the user to re-run organize; never crash.** All
  consumers tolerate missing optional fields by surfacing a prompt, not by throwing.

---

## 6. Producer / consumer boundary

- **`cancer-buddy-organize` WRITES everything under `<patient_code>/`** — the canonical file set (§4),
  the buckets (§3), `raw/`. It is the sole canonical writer of `profile.json` / `readiness.json` /
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
