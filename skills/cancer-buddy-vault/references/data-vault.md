# Data Vault — N=1 Patient Data Schema & Sharing Protocol

## Locale

This protocol is governed by [../../../references/i18n.md](../../../references/i18n.md). Resolve `locale` from host-supplied `locale` first, otherwise `profile.json.locale`, otherwise detection fallback + persist, before producing any patient-visible output.

- **JSON keys and enum values stay verbatim** (`recipient_type`, `access_type`, `"view"`, `"anonymized"`, level ids `private`/`authorized`/`anonymized`/`public`) — they are machine keys, not patient-facing prose.
- **Human-readable values and prose are rendered in `locale`**: the `purpose` free-text, sharing-level *descriptions*, data-quality reminders, revocation confirmations, and breach notifications. Render fixed labels (level names, notice headings) as a `locale → string` lookup; run generative prose (case report, reminders) via a prompt instruction "Output scaffold/narrative prose in `<locale>`; keep clinical entities verbatim per `i18n.md` §4."
- **Clinical entities stay verbatim in every locale** — diagnosis names, drug regimens, gene/variant strings, TNM/stage, numbers + units, biomarker labels are never translated, transliterated, or normalized (P0 medical-safety bug). The example strings below (e.g. "Profile is 72% complete. Missing: PD-L1 status…") show `en`; render the scaffold in the active `locale` while keeping the clinical tokens (`PD-L1`, `RNA-seq`) verbatim.

## Sharing-Scope View (logical, NOT the on-disk layout)

⚠️ The tree below is a **logical sharing-scope view** — the set of category names vault uses for `scope` / `data_scope` values in `sharing-settings.json` and `audit-log` entries. These are **not directories on disk**; vault does not create them.

The **real on-disk archive** is the one `cancer-buddy-organize` produces at `patients/<patient_code>/` — the **14 clinical-domain buckets** `01_身份与基础信息/ … 14_患者自管补充/` (scheme_version 3), plus `raw/` (verbatim originals), `99_无关文件/`, and the structured JSONs (`profile.json`, `patient_summary.json`, `treatment_lines.json`, `molecular.json`, `comorbidities.json`, …). Authoritative on-disk layout: [../../cancer-buddy-organize/references/bucket-taxonomy.md](../../cancer-buddy-organize/references/bucket-taxonomy.md) and [../../../references/patient-profile-schema.md](../../../references/patient-profile-schema.md).

```
# Logical sharing-scope categories (each maps to on-disk buckets — see table below)
profile                 # Patient Profile Card (on-disk: profile.json — cancer_buddy_profile_v3)
timeline                # All events chronologically
diagnostics             # genomics / imaging / pathology / blood
treatments              # Per-line treatment records + response assessment
monitoring              # Longitudinal tracking (MRD, markers, imaging series)
notes                   # Doctor visit notes, Q&A records, second opinions
sharing-settings.json   # Access control configuration (vault-produced)
```

### Sharing-scope → on-disk bucket mapping

| Sharing scope | Spans on-disk buckets (from `cancer-buddy-organize`) |
|---|---|
| `profile` | `profile.json` (+ structured `patient_summary.json` / `molecular.json` / `treatment_lines.json` / `comorbidities.json`) |
| `timeline` | derived across buckets (chronological roll-up; no single bucket) |
| `diagnostics` | `04_诊断与分期/` (pathology), `05_影像/` (imaging), `06_分子与组学/` (genomics), `07_检验/` (blood/labs) |
| `diagnostics/genomics` | `06_分子与组学/` (NGS, WES-WGS, transcriptome, IHC, germline) |
| `diagnostics/imaging` | `05_影像/` (CT/MRI/PET-CT/ultrasound/nuclear) |
| `diagnostics/pathology` | `04_诊断与分期/` (pathology, diagnosis certificate, staging) |
| `diagnostics/blood` | `07_检验/` (CBC, biochemistry, tumor markers, coagulation) |
| `treatments` | `08_治疗/` (chemo/radiation/immuno/targeted/…), `09_手术与操作/` (surgery & procedures) |
| `monitoring` | `10_随访与监测/` (follow-up, wearable export, PRO, home monitoring) |
| `notes` | `03_病程与叙事文书/` (admission/discharge/progress/outpatient notes), `11_会诊与转诊/` (MDT, consult, referral, second opinions) |

## profile.json (canonical shape — vault does NOT define its own)

Vault **does not define a competing `profile.json` schema**. It reads the canonical `profile.json` written by `cancer-buddy-organize`, which is the slim **`cancer_buddy_profile_v3`** snapshot — top-level `schema` / `patient_code` / `alias` / `locale` / `generated_at` / `privacy` / `anthropometrics` / `summary{one_line_condition, primary, histology, stage, metastasis_sites, current_regimen}` / `latest_status{regimen, response, ecog, as_of, source_refs}` / `source_refs`.

`profile.json` carries **none** of the old flat `demographics` / `diagnosis` / `molecular_features` / `treatment_history` / `comorbidities` / `ecog_status` fields. Those live in the structured JSONs alongside it:

| Need | Read this file |
|---|---|
| identity / locale / one-line condition / current status | `profile.json` (`cancer_buddy_profile_v3`) |
| demographics + diagnosis (icd10, diagnosed_at, confidence, staging) | `patient_summary.json` |
| lines of therapy | `treatment_lines.json` |
| drivers / variants / biomarkers | `molecular.json` |
| comorbidities | `comorbidities.json` |

Authoritative profile contract: [../../../references/patient-profile-schema.md](../../../references/patient-profile-schema.md).

### vault_export.json (vault-produced aggregate)

When a share / export needs a single aggregated object (e.g. a de-identified bundle for an authorized recipient), vault emits **`vault_export.json`** — a vault-produced aggregate, **not** the on-disk `profile.json`. It is assembled from the canonical sources above (and scoped/de-identified per the active `sharing-settings.json` rule), so its shape is determined by the requested `scope`, not by any fixed profile schema. It must never be named `profile.json` and never re-introduce the retired flat `version: "1.0"` shape.

## timeline.json (organize-produced; vault is a read-only consumer)

Vault does **not** define this schema — the authority is [`../../cancer-buddy-organize/references/schemas/timeline.schema.json`](../../cancer-buddy-organize/references/schemas/timeline.schema.json) (and `../../../references/patient-profile-schema.md`). The canonical on-disk shape vault reads / shares is `cancer_buddy_profile_v3`-era:

```json
{
  "patient_code": "PT-48C5070065",
  "schema_version": "1",
  "events": [
    {
      "date": "2024-01-15",
      "category": "diagnosis",
      "title": "Biopsy confirmed osteosarcoma",
      "detail": "Core needle biopsy, conventional osteoblastic subtype",
      "hospital": "中山六院",
      "source_refs": ["04_诊断与分期/病理报告/2024-01-15_病理报告_中山六院.md#L4-L8"]
    },
    {
      "date": "2024-02-01",
      "category": "chemo",
      "title": "MAP regimen initiated",
      "detail": "Neoadjuvant chemotherapy, cycle 1",
      "hospital": "中山六院",
      "source_refs": ["08_治疗/化疗/2024-02-01_化疗_中山六院.md#L1-L6"]
    }
  ]
}
```

**Event `category` enum** (from the schema): `diagnosis`, `surgery`, `chemo`, `radio`, `immuno`, `targeted`, `molecular_test`, `imaging`, `lab`, `hospitalization`, `consult`, `other`. Citations are per-event `source_refs[]` (NN_ bucket-relative `.md` anchors). The retired flat `version` / `patient_id` / per-event `type` / `outcome` / `description` / `documents[]` shape must **never** be re-introduced (per the prohibition above) — it would fail `timeline.schema.json` (`additionalProperties:false`) and the `validate_structured_outputs.py` gate.

## sharing-settings.json

```json
{
  "default_level": "private",
  "sharing_rules": [
    {
      "recipient_type": "doctor",
      "recipient_id": "dr-zhang-ruijin",
      "level": "authorized",
      "scope": ["profile", "diagnostics", "treatments", "timeline"],
      "expires": "2025-06-01"
    },
    {
      "recipient_type": "researcher",
      "recipient_id": "study-nct12345",
      "level": "anonymized",
      "scope": ["diagnostics/genomics", "treatments"],
      "expires": null
    }
  ],
  "ai_consent": {
    "federated_learning": false,
    "anonymized_analysis": true
  }
}
```

## Data Sharing Levels

The level **id** (`private` / `authorized` / `anonymized` / `public`) and icon are stable across locales; the **name / description / use-case** columns are rendered from a `locale → string` lookup (the table below is the `en` rendering).

| Level id | Icon | Description (localize) | Use Case (localize) |
|---|---|---|---|
| private | 🔒 | Only patient + designated caregiver | Default. All data starts here. |
| authorized | 🔑 | Specific doctors/researchers by invitation | Second opinions, clinical trial screening, MDT consultation |
| anonymized | 📊 | De-identified data for federated learning | AI model improvement, population-level insights, no re-identification possible |
| public | 🌐 | Fully open (like a public patient data portal) | Patient advocacy, advancing research, radical transparency |

## Data Quality Scoring

Compute completeness percentage per category:

| Category | Required Fields | Scoring |
|---|---|---|
| Demographics | age, sex, diagnosis, stage, date | Each field = 20% |
| Molecular | gene panel OR WES, TMB, MSI, PD-L1 | Each = 25% |
| Treatment history | all lines with dates, response, reason stopped | Each complete line = equal share of 100% |
| Imaging | baseline + most recent | Baseline = 50%, latest = 50% |
| Timeline | >10 events covering diagnosis through current | <5 events = 30%, 5-10 = 60%, >10 = 100% |

Generate missing-data reminders in `locale`, keeping the clinical field names verbatim. `en`: "Profile is 72% complete. Missing: PD-L1 status, RNA-seq results, most recent imaging report." — render the scaffold ("Profile is N% complete. Missing: …") in the active `locale`, but keep `PD-L1`, `RNA-seq`, and any other clinical token verbatim.

## Privacy Compliance

### 《个人信息保护法》(PIPL)
- Explicit consent required before any data collection or sharing
- Patient can view, correct, and delete their data at any time
- Data processor must document legal basis for processing
- Cross-border transfer requires security assessment or standard contractual clauses

### 《人类遗传资源管理条例》
- **Genomic data must stay in China** — no cross-border transfer without 科技部 approval
- This affects: WES, WGS, RNA-seq, single-cell, germline data
- Anonymized aggregate statistics may be exportable
- Foreign entities cannot directly collect Chinese genetic resources

### Patient Rights
- Revoke any sharing authorization at any time → immediate effect
- Request complete data deletion (except legally required medical records)
- Receive copy of all data in portable format (JSON export)
- Be informed of any data breach within 72 hours

## Access Audit Log

Every data access event must be logged for compliance and patient transparency.

### Schema: audit-log entry

```json
{
  "log_id": "audit-20240601-001",
  "recipient_id": "dr-zhang-ruijin",
  "recipient_type": "doctor",
  "data_scope": ["diagnostics/genomics/wes-report.json", "profile.json"],
  "access_time": "2024-06-01T14:30:00+08:00",
  "access_type": "view",
  "purpose": "Second opinion consultation for treatment line 3",
  "ip_address": "10.0.x.x",
  "session_duration_seconds": 1200,
  "data_exported": false
}
```

**Fields:**
| Field | Required | Description |
|---|---|---|
| `log_id` | Yes | Unique identifier for each access event |
| `recipient_id` | Yes | Who accessed the data (doctor ID, researcher ID, system ID) |
| `recipient_type` | Yes | `doctor`, `researcher`, `system`, `patient`, `caregiver` |
| `data_scope` | Yes | Array of paths/categories accessed |
| `access_time` | Yes | ISO 8601 timestamp with timezone |
| `access_type` | Yes | `view`, `download`, `export`, `api_query` |
| `purpose` | Yes | Free-text reason for access (required by PIPL) |
| `ip_address` | No | Network origin of access |
| `session_duration_seconds` | No | How long the data was accessed |
| `data_exported` | Yes | Whether data was downloaded/exported outside the system |

**Retention:** Audit logs must be retained for minimum 3 years per PIPL requirements.

---

## Revocation Process

When a patient revokes data sharing authorization:

### Genetic / Genomic Data (highest sensitivity)
- **Timeline:** Immediate revocation — access must be terminated within minutes, not hours
- **Scope:** All genomic data (WES, WGS, RNA-seq, panel results, ctDNA, single-cell, germline)
- **Actions:**
  1. Disable recipient's access tokens immediately
  2. Send deletion confirmation request to recipient
  3. Confirm to patient that access has been revoked (with timestamp)
  4. Log revocation event in audit log
  5. If data was exported, send formal deletion request to recipient with 48h compliance deadline

### Other Medical Data (non-genetic)
- **Timeline:** 24-hour notice period — recipient is notified that access will be revoked in 24 hours
- **Scope:** Treatment records, imaging, lab results, clinical notes
- **Actions:**
  1. Notify recipient of pending revocation (24h countdown)
  2. Revoke access after 24h (or immediately if patient requests urgent revocation)
  3. Confirm to patient that access has been revoked (with timestamp)
  4. Log revocation event in audit log

### Confirmation to Patient
Every revocation must generate a confirmation record sent to the patient, with its prose rendered in `locale` (recipient ids, data-scope paths, and any clinical entity stay verbatim), containing:
- Recipient whose access was revoked
- Data scope that was revoked
- Timestamp of revocation
- Whether any data export occurred during the sharing period (from audit log)
- Next steps if data was previously exported

---

## Data Breach Protocol

Per PIPL (《个人信息保护法》) requirements:

### 72-Hour Notification Rule

Upon discovery of a data breach involving patient data:

**Hour 0–4: Containment**
1. Identify and isolate the breach vector
2. Revoke compromised access credentials
3. Preserve forensic evidence (logs, access records)
4. Assess scope: which patients, what data types, what volume

**Hour 4–24: Assessment**
1. Determine whether genetic/genomic data was involved (triggers heightened protocol under 《人类遗传资源管理条例》)
2. Classify severity: low (metadata only), medium (medical records), high (genomic + identifiable data)
3. Prepare notification content

**Hour 24–72: Notification**
1. Notify affected patients (notification prose rendered in each patient's `locale`; authority names and clinical entities verbatim) with:
   - What data was compromised
   - When the breach occurred and was discovered
   - What remediation steps have been taken
   - What the patient should do (e.g., monitor for misuse, update passwords)
   - Contact information for questions
2. Report to relevant authorities:
   - 网信办 (Cyberspace Administration) for personal data breaches
   - 科技部 (Ministry of Science and Technology) if genetic resource data was involved
   - Public security if criminal activity suspected

**Post-Breach Remediation:**
- Conduct root cause analysis
- Implement technical fixes to prevent recurrence
- Update security protocols
- Provide affected patients with ongoing monitoring if genetic data was exposed
- Document entire incident for compliance records (retain indefinitely)

### Patient Rights During Breach
- Right to know exactly what data was compromised
- Right to request immediate deletion of remaining data
- Right to revoke all sharing authorizations
- Right to receive updates on investigation progress
- Right to seek compensation for damages per PIPL Article 69
