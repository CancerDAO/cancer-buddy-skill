# Patient Profile Schema

> 📎 **Cross-repo interop surface** → see the SHARED-1 contract [`skills/cancer-buddy-organize/references/PATIENT_DIR_CONTRACT.md`](../skills/cancer-buddy-organize/references/PATIENT_DIR_CONTRACT.md) (duplicated in vmtb-skill) for the stable producer→consumer surface `cancerdao-vmtb` programs against; this file remains the full producer-side field contract.

This file defines the filesystem contract shared between `cancer-buddy-skill` and `vmtb-skill`. The organizer writes the canonical archive under `patients/<patient_code>/`; other companions read it, and downstream clinical systems must write corrections/results only to their own run overlays. Every authorized writer of `profile.json`, `timeline.md`, or `readiness.json` must honor the fields here.

The canonical writer is the `cb-organizer` subagent (mirrored from `vmtb-organizer`); all other sub-skills are read-only consumers.

## Directory layout

```
patients/<patient_code>/
├── INDEX.md                  # overview; patient_code declared on first line
├── profile.json              # structured profile (write: organize only)
├── timeline.md               # human-readable treatment timeline
├── readiness.json            # documentation coverage + source/faithfulness flags (compatibility filename)
├── case_text.md              # consolidated narrative
├── patient_summary.json molecular.json treatment_lines.json labs.json comorbidities.json timeline.json  # the 6 structured JSON outputs (schema-validated)
├── longitudinal_observations.json  # parsed time series (wearable / PRO / lab trends) — CONDITIONAL: only when timeseries/trended data exists; absent otherwise
├── source_inventory.json     # v2 extraction/provenance + file_id ↔ sidecar ↔ raw_path map
├── missing_items.json        # existing-document inventory gaps; never a test recommendation
├── update_log.json           # append-only audit trail of every run
├── review_summary.md         # 1-page extracted-field spot-check (always); review_flags.md (when non-empty)
├── AGENTS.md                 # agent-facing cross-session recall pointer (filled from profile.json)
├── 病情简要总结.html          # patient-facing one-page 段D summary; case_summary_versions/ holds dated snapshots
│   # 14 clinical-domain buckets (scheme_version 3 — authoritative: skills/cancer-buddy-organize/references/bucket-taxonomy.md)
├── 01_身份与基础信息/ 02_既往史与家族史/ 03_病程与叙事文书/ 04_诊断与分期/ 05_影像/
├── 06_分子与组学/ 07_检验/ 08_治疗/ 09_手术与操作/ 10_随访与监测/
├── 11_会诊与转诊/ 12_心理社会与支持/ 13_行政与财务/ 14_患者自管补充/
├── raw/                      # access-controlled uploaded originals; not used as an automatic downstream text source
├── 99_无关文件/               # relevance quarantine (high_confidence/ uncertain/)
├── ocr/                      # transient Phase-1 staging — native/deterministic extraction retained, LLM proposals separated, text-masked sidecars drained into buckets by Phase 2; a completed run has no ocr/
└── reports/
    ├── mtb-lite/             # cancer-buddy-mtb-lite
    ├── mtb-full/             # vmtb-skill cancerdao-vmtb
    ├── explore/
    ├── trials/
    ├── access/
    ├── manage/
    └── education/
```

## patient_code

Format: `PT-<hex>`, e.g. synthetic `PT-A1B2C3D4E5`.
- Generated from cryptographically random bytes on first run, persisted as the first line of `INDEX.md` (format: `# patient_code: PT-A1B2C3D4E5`). Do not derive it from filenames, timestamps, diagnosis, or other patient data.
- Callers may supply a `patient_code` argument to override. Must be unique within the `patients/` root; on collision the organizer appends `_<n>`.
- `patient_code` is a storage locator, not proof of identity, consent, authorization, or record ownership. Access control is enforced by the host.

## profile.json (required fields)

`profile.json` is the **slim canonical first-read snapshot** (schema `cancer_buddy_profile_v3`). Shape written by `cb-organizer` (shared with `vmtb-organizer`):

```json
{
  "schema": "cancer_buddy_profile_v3",
  "patient_code": "PT-C1D2E3F4A5",
  "alias": "case-a7f2",
  "locale": "zh",
  "generated_at": "2024-07-06T08:00:00Z",
  "privacy": {
    "pii_policy": "sidecar_text_masked; raw_originals_retained_under_raw",
    "summary_minimization_policy": "purpose_and_authorization_required"
  },
  "anthropometrics": {
    "height_cm": 170,
    "weight_kg": 80,
    "bmi": 27.7,
    "provenance_layer": "patient_reported",
    "verification_status": "unverified",
    "source_refs": ["conversation:2024-07-05T10:30:00Z"]
  },
  "summary": {
    "one_line_condition": "来源记录：乙状结肠腺癌；分期原文 pT3N1b；有 FOLFOX 治疗记录",
    "primary": "乙状结肠恶性肿瘤",
    "histology": "中分化腺癌",
    "stage": "pT3N1b",
    "metastasis_sites": [],
    "current_regimen": "FOLFOX",
    "provenance_layer": "source_reported",
    "verification_status": "unverified",
    "source_refs": ["03_病程与叙事文书/出院小结/2024-07-05_出院小结.md"]
  },
  "latest_status": {
    "regimen": "FOLFOX",
    "response": null,
    "ecog": null,
    "as_of": "2024-07-05",
    "source_refs": ["03_病程与叙事文书/出院小结/2024-07-05_出院小结.md"]
  },
  "source_refs": [
    "03_病程与叙事文书/出院小结/2024-07-05_出院小结.md",
    "05_影像/CT/2024-07-01_腹部CT.md"
  ]
}
```

Block-by-block contract:

- `schema` (required): always the literal string `cancer_buddy_profile_v3`. Downstream consumers branch on this to detect the shape.
- `patient_code` (required): canonical `PT-<hex>` identity. Same value as `INDEX.md` first line.
- `alias` (optional): a user-chosen non-clinical label. It must not contain a name, diagnosis, cancer code,
  treatment year, institution, contact detail, or recognizable identifier. It is not authentication.
- `locale` (required, BCP-47 — `en` / `fr` / `es` / `zh` / `de` / …): language for patient-facing scaffold and explanation. Source clinical strings remain available exactly; validated normalization and a labeled translation may be added beside them. An explicit user override updates this field and wins over detection. Full contract: `references/i18n.md`.
- `generated_at` (required): ISO8601 timestamp of the organize run that wrote this file.
- `privacy` (required): records the applicable handling policy. Any summary or export applies purpose limitation,
  authorization, data minimization, retention, and residual-risk review. Age and other quasi-identifiers are
  included only when necessary for the authorized task; no field is categorically safe in every combination.
- `anthropometrics` (optional): `height_cm` / `weight_kg` / `bmi` plus provenance, verification and `source_refs[]`. Null block when no body metrics are known.
- `summary` (required): a denormalized source-preserving snapshot. Each clinical block carries `provenance_layer` (`source_reported|patient_reported|caregiver_reported|system_normalized`), `verification_status` (`unverified|clinician_verified|disputed`), and `source_refs[]`. Patient confirmation never promotes a value to `clinician_verified`.
- `latest_status` (required): current treatment state copied from sources. `response` and `ecog` remain `null` unless a clinician-authored source explicitly states them. Do not infer either from lesion measurements, symptoms, or function descriptions.
- `source_refs` (top-level, required): safe `01_…14_` bucket-relative paths to existing text-masked MD sidecars, or `conversation:<ISO8601>` for confirmed patient/caregiver statements. JSON refs may be path-only or carry a `#fragment`; formal Markdown facts require a fragment. Absolute paths, backslashes, `.`/`..`, `raw/`, `ocr/`, `99_…`, and dangling targets are invalid. **Every clinical block** (`anthropometrics`, `summary`-derived facts via the top-level list, `latest_status`) carries its own `source_refs[]` so each fact is traceable.

Fields are left `null` when truly unknown — the organizer **never fabricates**.

Only `patient_code` is universally required. Missing diagnosis fields remain `null`/unknown. Downstream skills may still provide stable general help, but must not produce a patient-specific clinical conclusion or tell the patient that a missing field means a test is indicated.

### profile.json vs patient_summary.json

These are two distinct files with a deliberate division of labor (this is the dedup contract, not an accident):

- **`profile.json`** = the **slim canonical first-read snapshot** — storage locator (`patient_code`), optional
  non-clinical `alias`, locale, and source-attributed summary/status fields. It is not proof of identity or a
  clinically adjudicated problem list.
- **`patient_summary.json`** (one of the 6 structured JSONs, `schema_version 2.1`) = the source-preserving structured rollup defined by `patient_summary.schema.json`. Diagnosis, current status and demographics carry provenance, verification status and source references. ECOG and response are copied only from clinician-authored sources; patient function descriptions remain separate. **Only `sex` is time-invariant:** `age` / `height_cm` / `weight_kg` / `ecog` are point-in-time snapshots and each carries its own `_as_of` source date (`age` additionally keeps the full `age_observations[]` series plus an optional coarse-grained `birth_year`). Values differing across different `_as_of` dates are normal evolution and must NOT be flagged as a source conflict — see `skills/cancer-buddy-organize/references/organizer-prompt-phase2-synthesis.md` §2.1.
- **Relationship:** `profile.summary` is a **denormalized convenience copy** of the authoritative structured facts in `patient_summary.json` — this is intentional (cheap snapshot vs full record), NOT an accidental duplicate. When the two could disagree, `patient_summary.json` is **authoritative for structured diagnosis fields**; `profile.json` is authoritative for **identity / locale / latest_status**.

> ⚠️ **Cross-repo follow-up:** the shared `vmtb-skill` (separate repo) also reads `profile.json` and must be aligned to the `cancer_buddy_profile_v3` shape — its `vmtb-organizer` writer and any downstream consumers still expecting the old flat top-level `primary_cancer` / `histology` / `stage` need to be migrated. Track as a cross-repo task.

## readiness.json

The filename is retained for compatibility; it is not an MTB or clinical-readiness score.

```json
{
  "patient_code": "PT-C1D2E3F4A5",
  "schema_version": "2",
  "documentation_coverage": {
    "diagnosis_documents": "present",
    "pathology_documents": "not_in_archive",
    "molecular_documents": "unknown"
  },
  "warnings": [],
  "review_flags": [
    {
      "id": "RF-001",
      "category": "cross_source_conflict",
      "affected_field": "diagnosis.stage",
      "current_source_values": [
        {"value": "...", "source_ref": "..."},
        {"value": "...", "source_ref": "..."}
      ],
      "issue": "Two source documents contain different stage strings.",
      "resolution_status": "unresolved"
    }
  ]
}
```

- Coverage values are document-inventory facts such as `present | not_in_archive | unknown`; do not convert them into a numeric score, band, grade, diagnosis confidence or permission to act.
- A missing document is not evidence that a test is indicated. `missing_items.json` follows the same existing-document-only rule.
- Flags are limited to extraction fidelity, source conflict, cross-patient identity risk, dangling anchors, filename/content routing and provenance. The organizer does not decide that a source is clinically illogical or physiologically impossible.
- **`cross_source_conflict` never fires on a time-varying field's normal evolution.** Age, weight, height, ECOG and `current_status.*` differing across sources with different report dates is a time series, not a conflict — it produces no review flag and no `disputed`. It escalates to a flag only when two sources share the same as-of date, or when the change contradicts the elapsed time (age going backwards). Judgement rule: `organizer-prompt-phase2-synthesis.md` §2.1.
- Preserve every conflicting value and its source. A patient acknowledgment may confirm what the patient said, but cannot resolve a clinician-source conflict or create a clinician-verified value.
- `resolution_status` is changed only by a documented corrected source, authorized clinician attestation, or a provenance-preserving administrative resolution. There is no model-proposed clinical replacement value.
- An unresolved flag blocks only the affected field from being presented as settled fact. General education, organization and question preparation continue with the limitation stated.

`review_flags.md` is a generated human-readable view; JSON remains the source of truth.

## Field-change discipline

Only `cancer-buddy-organize` may write canonical `profile.json`, `timeline.md`, and `readiness.json`. A downstream clinical workflow records proposed corrections in its run-scoped overlay and never mutates these canonical files. Any other sub-skill that wants to reflect new information (e.g. a new imaging study) must trigger an authorized organize re-run, not mutate in place.

## Defensive reads

All consumers must tolerate missing optional fields — surface a prompt, do not crash. Missing required fields trigger the re-organize suggestion above.

## role.json — per-session role state

Written and read by the meta-skill only. Schema:

```json
{
  "schema_version": "1",
  "active_role": "patient|caregiver|family",
  "set_at": "2026-04-23T10:00:00Z",
  "history": [{"role": "patient", "set_at": "2026-04-20T09:00:00Z"}]
}
```

Every sub-skill reads `patients/<patient_code>/role.json` at entry. If missing → route back to meta-skill for role resolution.

## comfort symptom-log YAML schema

Standardized format for `patients/<patient_code>/reports/comfort/symptom-log/<YYYY-MM-DD>.md`. Written as a YAML code block inside the .md file.

```yaml
date: 2026-04-23
function_description: "Most of the day in bed; walked to the bathroom with help"
pain:
  worst_last_24h: 6  # 0-10 NRS
  current: 3
  character: "dull, lower back, radiating left leg"
  relieved_by: "oxycodone 10mg q4h"
  breakthrough_doses: 2
breathing_difficulty_reported:
  at_rest: "none|mild|moderate|severe"
  on_exertion: "none|mild|moderate|severe"
  o2_use: true
nausea:
  episodes: 1
  vomiting: false
  trigger: "after breakfast"
confusion_or_behavior_change_observed:
  present: false
  description: null
  onset: null
secretions:
  noisy_breathing_observed: false
affect:
  state: "withdrawn, tearful"
  notable: "said 'I want to go home' twice"
medications_reported_today:
  - oxycodone 10mg q4h prn
  - ondansetron 8mg BID
  - lorazepam 0.5mg prn
family_observations: |
  Patient refused breakfast. Daughter stayed 6 hours.
  Grandchild video-called, patient smiled briefly.
logged_by: caregiver  # patient | caregiver | authorized family
provenance_layer: caregiver_reported
```

These are observations and self/caregiver reports, not toxicity grades or diagnoses. Do not convert a
function description into ECOG, `confusion_or_behavior_change_observed` into delirium, or symptom
intensity into a treatment decision. Concurrent updates use version checking: preserve both versions on
conflict and ask an authorized user to reconcile the reported layer; never use last-write-wins for health
records or promote that reconciliation to clinician verification.

## Version pin

Declared tested against `vmtb-skill` ≥ 4.0.0-beta.6. Breaking schema changes bump the organizer's output first, this file follows.
