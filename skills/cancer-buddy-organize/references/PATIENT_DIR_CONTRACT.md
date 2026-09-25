⚠️ SHARED CONTRACT — producer = cancer-buddy-organize (this repo is the single source of this file). Consumers = **smtb-skill** (`scripts/facts.py build` reads the archive; `runlog.py init` reads `organize_meta.json`) and the legacy cancerdao-vmtb skip-organize path. smtb-skill keeps no copy of this file; its own reading rules must track this file, and any change to §4–§5 is announced in this repo's CHANGELOG.

# PATIENT_DIR_CONTRACT — the on-disk patient archive (SHARED-1)

This is the **single cross-repo interface contract** for the on-disk patient archive that
`cancer-buddy-organize` **PRODUCES** and `smtb-skill` (and, historically, `vmtb-skill` in skip-organize
mode) **CONSUMES**. It is
narrower and more stable than either repo's internal docs: a consumer that programs against ONLY
what is written here will not break when either side iterates its private layout. If this file and a
repo-internal doc disagree on the interop surface (§5) or the producer/consumer boundary (§6), **this
file wins and the other is a drift bug to fix**.

- Producer-authoritative deep docs (cancer-buddy-skill): `references/bucket-taxonomy.md` +
  `references/bucket_taxonomy.json` (bucket scheme, `scheme_version 3`), `references/patient-profile-schema.md`
  (profile / readiness field contract), `skills/cancer-buddy-organize/SKILL.md` (the write pipeline).
- Consumer entry (smtb-skill): `scripts/facts.py build` turns the structured JSON files of §4 into the
  run register; `scripts/runlog.py init` records `organize_meta.json`. Legacy consumer entry (vmtb-skill):
  `skills/cancerdao-vmtb/SKILL.md` (Step 2 skip-organize, Step 3 readiness gate).

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

## 3. Bucket taxonomy (v3, `scheme_version 3`)

The clinical-domain buckets are **14 domains** with a two-digit `NN_` prefix, each with pinned typed
sub-buckets. The **machine-readable source is `bucket_taxonomy.json`** (producer repo:
`skills/cancer-buddy-organize/references/bucket_taxonomy.json`; consumers do not keep a mirror) — a
consumer that needs to enumerate buckets reads that JSON, it does NOT re-hardcode the list. The 14 domains:

```
01_身份与基础信息   02_既往史与家族史   03_病程与叙事文书   04_诊断与分期      05_影像
06_分子与组学       07_检验             08_治疗             09_手术与操作      10_随访与监测
11_会诊与转诊       12_心理社会与支持   13_行政与财务       14_患者自管补充
```

(zh slugs shown; `locale≠zh` uses the pinned `en` set — `01_identity_basics … 14_patient_supplement`.
The **pinned typed sub-buckets** per domain — e.g. `04_诊断与分期/{病理报告,诊断证明,分期评估,其他}`,
`06_分子与组学/{NGS报告,免疫组化,…}` — are enumerated in `bucket_taxonomy.json`; do not re-list here.
One sub-bucket carries a provenance meaning a consumer may rely on: `03_病程与叙事文书/既往档案摘录`
(`en`: `03_clinical_notes/prior-archive-digest`) holds only prior-archive digests — see §5 (e).)

**Rules a consumer MUST rely on:**

- **The `NN_` two-digit prefix is the language-independent STABLE key.** Match on `^[0-9]{2}_` — never
  on the localized slug. The **localized slug is NOT stable across locales** (two pinned sets only: `zh`
  when `locale=zh`, `en` for every other locale — fr/es/de/… all use the `en` column, never a
  runtime-translated slug). To glob a domain regardless of locale, key on `NN_` (e.g. vMTB Step 3.25
  globs `<patient_dir>/[01][0-9]_*/**/*.md`).
- **Buckets are lazily created.** A domain dir exists on disk **iff** the archive actually filed a
  record for it. **An absent bucket means "no source was filed for this domain", NOT "scaffold missing"
  or "domain checked and clear"** — never treat an absent `09_手术与操作/` as "no surgery"; the
  existing-document inventory channel is `missing_items.json`; absence never means a test is indicated.
- **`raw/` and `99_无关文件/` are NEVER anchor targets.** `raw/` is the hidden verbatim vault of
  uploaded originals (never pixel-redacted, filename de-identified); `99_无关文件/` is the relevance
  quarantine (`high_confidence/ uncertain/`). Downstream never reads `99_`, and anchors point only at
  the clinical-domain `.md` sidecars.
- **`ocr/` is absent in a completed run** — it is transient Phase-1 staging, drained into the buckets
  and removed. If you see `ocr/`, the archive is mid-run or a Phase-2 relocation failed.
- **Sidecar `.md` files live co-located inside their domain bucket** (e.g.
  `04_诊断与分期/病理报告/2024-03-15_病理报告_示例医院.md`). The uploaded original is NOT copied into
  the bucket — it lives once in `raw/`, deep-linked from each sidecar via `source_inventory.json.raw_path`.

---

## 4. Canonical file set at `<patient_data_root>/<patient_code>/`

One-line purpose each (producer writes all of these; the conditional ones only when applicable). On a current-contract archive every structured file except `longitudinal_observations.json` is written on every run — an empty domain is an empty array, and a missing file fails the acceptance gate:

| File | Purpose |
|---|---|
| `profile.json` | Slim first-read index with provenance/verification state, including `demographics` (`sex`, `age`, `age_as_of`, `performance_status_verbatim[]` — a copy of `patient_summary.json.demographics`, which stays authoritative) and `latest_status` (the ongoing episode's `regimen`, `as_of` and `status_basis`, or null); `patient_code` is not identity authentication. |
| `patient_summary.json` | Source-preserving rollup; structured fields are not clinically authoritative merely because they are normalized. |
| `molecular.json` | Source-preserving report, sample, assay, quality and result records, plus `hla_typing[]` (bare locus letters `A`/`B`/`C`/`DRB1`; a row with `allele: null` and `zygosity` only records that typing was done — it is never an allele to match); no actionability inference. |
| `treatment_lines.json` | Chronological treatment episodes — one per regimen course (cycles of one regimen are one episode; `cycle_label_verbatim` keeps the latest cycle wording) — with `status` (`ongoing|stopped|unknown`), `status_basis`, verbatim `status_basis_text`, `status_as_of` (null only for an undated family/patient statement, marked `status_as_of_precision: "undated_self_report"`); `line_number` / `documented_line_label` only when the source states a line. |
| `labs.json` | Lab panels with serial values; `pairing_method` / `candidate_value` record how each result was bound to its row. |
| `comorbidities.json` | Conditions, medication orders/records (each with `administration_setting`, `setting_basis`, optional `order_role`), allergies. |
| `acute_findings.json` | Source-worded acute/incidental findings (`finding_class`, `acuity`, `acuity_basis`, verbatim text, `change_vs_prior`, `source_ref`). **Always written**; `findings: []` means "checked, none found". |
| `timeline.json` | Machine-readable mirror of `timeline.md`; events may carry `conflict_group` (self-report vs source side by side) and `acute_finding_id` (`category: acute_finding`). |
| `timeline.md` | Human-readable treatment timeline (every line carries a `[[src:…]]` anchor). |
| `readiness.json` | Documentation coverage, review flags graded by `kind` + `severity`, and source recency (`latest_source_date`, `days_since_latest`, `as_of_run_date`); no A–F clinical readiness grade. |
| `source_inventory.json` | `"schema": "source_inventory_v2.1"` (legacy archives: `source_inventory_v2`): one row per content unit with `file_id ↔ source_id ↔ sidecar ↔ raw_path ↔ page_range ↔ modality`, `sha256` / `size_bytes` / `page_count` / verbatim `page_label`, `source_kind` (`upload` or `prior_archive_digest`), extraction provenance incl. `worker_id`, `second_read_channel`, `independent_reread`, and top-level `skipped_inputs[]`. The frontend deep-link map, not an authorization record. |
| `missing_items.json` | Compatibility filename for `document_gaps[]`: existing records not found/unknown/requested by a clinician, and `missing_pages` gaps (`pages_present`, `pages_missing`, `page_total`); never a test recommendation. |
| `update_log.json` | Append-only audit trail of every run (`schema_version: "1"`, `update_log.schema.json`): `inputs[]` by sha256, `added`/`removed`, `workers[]` and `degradations[]`; gated runs record the user's decisions in `note`. |
| `organize_meta.json` | `{skill, skill_version, skill_commit, skill_fingerprint, generated_at, pii_layer1_scan}` of the organize run that wrote the archive; `pii_layer1_scan` = `{worker_id, clean: true}` of the semantic PII scan (SKILL.md Step 12.5), required by the acceptance gate. |
| `case_text.md` | Consolidated narrative; every factual sentence anchored via `[[src:<bucket>/<file>.md#L<a>-L<b>]]`. |
| `INDEX.md` | File manifest; **first line is `# patient_code: <code>`**. |
| `AGENTS.md` | Agent-facing cross-session recall pointer (routing table + two-layer drill-down rule + citation floor), filled from `profile.json`. |
| `review_summary.md` | 1-page extracted-field spot-check with verbatim source citations (always written). |
| `review_flags.md` | Human-readable rendering of `readiness.json.review_flags[]` — **conditional** (only when the array is non-empty). |
| `longitudinal_observations.json` | Parsed time series (wearable / PRO / lab trends) — **conditional** (only when timeseries/trended data exists; absent otherwise). |
| `病情简要总结.html` | Purpose-limited patient-facing summary. Include age or other quasi-identifiers only when necessary and authorized; direct identifiers are excluded from the derived surface. |

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
- **(c) Uncertain fields are not premises.** A field whose flag has `kind: document_intent` and
  `resolution_status: unresolved`, or whose text contains `[OCR_UNCERTAIN:U-nnn]`, MUST NOT be used as a
  premise for staging, pathology or treatment reasoning, and MUST NOT spawn an alternative-stage or
  alternative-diagnosis scenario. A layout anomaly downgraded to `kind: artifact` keeps its literal reading
  ("版面异常，字面读作 X"); that literal is the source text, not evidence of a deletion. Lexicon candidates
  exist only inside sidecars and are never values. `labs.json` rows with `candidate_value` and
  `value: null` are position-paired, unverified readings — not measured results.
- **(d) `administration_setting` semantics.** `day_ward` = a same-day infusion/injection given on a
  day-care unit; `discharge` = listed under a 出院带药 heading; `unknown` = no rule applied (it does NOT mean
  long-term home use). Two rows from one order sheet with different settings (e.g. a day-ward IV dose and
  a discharge oral supply) are sequential orders, not concurrent duplicate use; `order_role: diluent`
  rows are carriers, not active drugs. Antineoplastic rows are also present as treatment episodes.
- **(e) `prior_archive` semantics.** `provenance_layer: prior_archive` facts come from an explicitly
  authorized digest of an earlier organized archive (`source_kind: prior_archive_digest`, original not in
  this archive). Use them for history only; never for current status, current regimen or as the basis of a
  recommendation, and label them "来自既往摘要，原件未在本次资料中" wherever they are cited.
- **(f) Acute findings.** `acuity` is a fixed class table applied to source wording, not organize's
  triage; emergent/urgent rows are for the consumer to surface to the treating team. A missing
  `acute_findings.json` means "not checked", never "none". It is written on every pass, a Phase-2-only
  pass on a legacy archive included (it is a safety surface, not a current-contract marker); on a legacy
  archive `timeline_event_id` may be null until `legacy_upgrade` adds the timeline events.
- **(g) Severity is not clinical severity.** `readiness.json.review_flags[].severity` and
  `missing_items.json` gap `severity` grade extraction/archive-completeness uncertainty only.
- **(h) Treatment status.** `status: ongoing` rests on the recorded `status_basis` (also copied to
  `profile.json.latest_status.status_basis`); a consumer that needs a stronger basis states the gap rather than
  silently downgrading the episode. `order_or_indication_only` (e.g. an imaging request stating the patient is on
  X) is not an administration record. An undated self-report (`status_as_of: null`,
  `status_as_of_precision: "undated_self_report"`) is stated as such — "家属陈述（未注明日期）正在接受 X" — never
  given a borrowed date. `performance_status_verbatim` strings are never converted between scales; an entry with
  `provenance_layer: prior_archive` is a past statement, never the current performance status.
- **(i) Versions and legacy archives.** Structured files that gained required fields in this iteration use
  `schema_version` `"2.1"` (`patient_summary` `"2.2"`, `source_inventory` `schema: "source_inventory_v2.1"`,
  `update_log` / `acute_findings` `"1"`); older archives (`"2"` / `"2.1"` / `source_inventory_v2`) remain
  readable and validate with a warning. Consumers branch on the version and tolerate absent new fields in
  legacy archives. An archive is current-contract as soon as it carries ANY current-contract marker —
  `organize_meta.json`, `readiness.json` ≥ `2.1`, a structured file at its current version, an
  `update_log.json` entry with `workers[]`, or a bucket sidecar header naming `EXTRACTOR`
  (`validate_structured_outputs.py --generation <dir>` prints the verdict and the markers); then every structured
  file is at its current version (a leftover legacy version fails validation as a
  mixed-version archive). A legacy archive is never partially upgraded: the first organize run on it is a full
  re-transcription from `raw/` (`run_mode: legacy_upgrade`), which moves the old buckets, the old-shape
  `update_log.json` and the rewritten top-level files into `raw/_legacy_<ts>/` (kept inside the access-controlled
  vault, never an anchor target, not read by consumers) and starts a new `schema_version: "1"` `update_log.json`; a
  Phase-2-only rerun on a legacy archive keeps every file at its old version and writes no marker (the archive stays
  legacy and validates with warnings until that upgrade). Update diffs use
  the last v1 entry with a non-empty `inputs[]` (conversation entries carry `inputs: []`) plus
  `source_inventory.json.skipped_inputs[]`; an archive without one is treated as all-new.
- `patient_code` is the only universal locator field and is not authentication. Missing diagnosis fields
  remain unknown; consumers may continue stable general help but must not generate patient-specific
  clinical conclusions. All consumers tolerate missing optional fields without throwing.

---

## 6. Producer / consumer boundary

- **`cancer-buddy-organize` WRITES everything under `<patient_code>/`** — the archive file set (§4),
  the buckets (§3), `raw/`. It is the sole storage-contract writer of `profile.json` / `readiness.json` /
  `timeline.*` / the structured JSONs.
- **`smtb-skill` READS that archive** through `scripts/facts.py build` and writes only inside its own run
  directory; it MUST NOT mutate any organize-produced file.
- **Validating as a consumer:** `validate_structured_outputs.py <patient_dir> --readonly`. Without `--readonly` the
  validator is the organize run's own terminal gate and records untrusted-content flags into `readiness.json`
  (a write a consumer is not allowed to make).
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
