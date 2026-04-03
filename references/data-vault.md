# Data Vault — N=1 Patient Data Schema & Sharing Protocol

Reference: osteosarc.com (Sid Sijbrandij's public cancer data site)

## Directory Structure

```
patient-vault/
├── profile.json           # Patient Profile Card
├── timeline.json          # All events chronologically
├── diagnostics/
│   ├── genomics/          # Gene test reports (panel, WES, WGS, RNA-seq)
│   ├── imaging/           # CT/MRI/PET-CT reports + DICOM references
│   ├── pathology/         # Biopsy, surgical pathology, IHC
│   └── blood/             # CBC, biochemistry, tumor markers, ctDNA
├── treatments/            # Per-line treatment records + response assessment
├── monitoring/            # Longitudinal tracking (MRD, markers, imaging series)
├── notes/                 # Doctor visit notes, Q&A records, second opinions
└── sharing-settings.json  # Access control configuration
```

## JSON Schema: profile.json

```json
{
  "version": "1.0",
  "patient_id": "patient-xxxx",
  "demographics": {
    "age_at_diagnosis": 45,
    "sex": "M/F",
    "ethnicity": "Han Chinese",
    "location": "Shanghai"
  },
  "diagnosis": {
    "primary": "Osteosarcoma",
    "icd10": "C40.2",
    "histology": "Conventional osteoblastic",
    "grade": "High",
    "stage_at_diagnosis": "IIB",
    "tnm": "T2N0M0",
    "date_of_diagnosis": "2024-01-15",
    "primary_site": "Left distal femur",
    "metastatic_sites": ["lung"]
  },
  "molecular_features": {
    "key_mutations": [
      {"gene": "TP53", "variant": "R175H", "vaf": 0.45, "source": "WES"}
    ],
    "tmb": {"value": 8.2, "unit": "mut/Mb"},
    "msi_status": "MSS",
    "pd_l1": {"tps": 10, "cps": 15, "clone": "22C3"},
    "fusions": [],
    "hrd_score": null,
    "signatures": ["SBS3"],
    "additional_biomarkers": {}
  },
  "treatment_history": [
    {
      "line": 1,
      "regimen": "MAP (Methotrexate/Adriamycin/Cisplatin)",
      "start_date": "2024-02-01",
      "end_date": "2024-06-15",
      "best_response": "PR",
      "reason_stopped": "Surgery",
      "toxicities": ["Grade 2 nausea", "Grade 3 neutropenia"]
    }
  ],
  "ecog_status": 1,
  "allergies": [],
  "comorbidities": [],
  "current_medications": [],
  "insurance_type": "城镇职工医保",
  "last_updated": "2024-12-01"
}
```

## JSON Schema: timeline.json

```json
{
  "version": "1.0",
  "patient_id": "patient-xxxx",
  "events": [
    {
      "date": "2024-01-10",
      "type": "symptom",
      "category": "presentation",
      "title": "Left knee pain onset",
      "description": "Progressive pain, worse at night",
      "outcome": null,
      "documents": []
    },
    {
      "date": "2024-01-15",
      "type": "diagnosis",
      "category": "pathology",
      "title": "Biopsy confirmed osteosarcoma",
      "description": "Core needle biopsy, conventional osteoblastic subtype",
      "outcome": "diagnosis_confirmed",
      "documents": ["diagnostics/pathology/biopsy-20240115.pdf"]
    },
    {
      "date": "2024-02-01",
      "type": "treatment_start",
      "category": "chemotherapy",
      "title": "MAP regimen initiated",
      "description": "Neoadjuvant chemotherapy, cycle 1",
      "outcome": null,
      "documents": ["treatments/line1-MAP.json"]
    },
    {
      "date": "2024-04-15",
      "type": "assessment",
      "category": "imaging",
      "title": "Mid-treatment CT",
      "description": "Partial response per RECIST 1.1, 40% reduction",
      "outcome": "PR",
      "documents": ["diagnostics/imaging/ct-20240415.pdf"]
    }
  ]
}
```

**Event types:** `symptom`, `diagnosis`, `treatment_start`, `treatment_end`, `assessment`, `surgery`, `biopsy`, `lab`, `consultation`, `adverse_event`, `hospitalization`, `trial_enrollment`, `expanded_access`, `genetic_test`, `other`

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

| Level | Icon | Description | Use Case |
|---|---|---|---|
| Private | 🔒 | Only patient + designated caregiver | Default. All data starts here. |
| Authorized | 🔑 | Specific doctors/researchers by invitation | Second opinions, clinical trial screening, MDT consultation |
| Anonymized-for-AI | 📊 | De-identified data for federated learning | AI model improvement, population-level insights, no re-identification possible |
| Public | 🌐 | Fully open (like osteosarc.com) | Patient advocacy, advancing research, radical transparency |

## Data Quality Scoring

Compute completeness percentage per category:

| Category | Required Fields | Scoring |
|---|---|---|
| Demographics | age, sex, diagnosis, stage, date | Each field = 20% |
| Molecular | gene panel OR WES, TMB, MSI, PD-L1 | Each = 25% |
| Treatment history | all lines with dates, response, reason stopped | Each complete line = equal share of 100% |
| Imaging | baseline + most recent | Baseline = 50%, latest = 50% |
| Timeline | >10 events covering diagnosis through current | <5 events = 30%, 5-10 = 60%, >10 = 100% |

Generate missing data reminders: "Profile is 72% complete. Missing: PD-L1 status, RNA-seq results, most recent imaging report."

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

## Comparison: osteosarc.com vs Cancer-Buddy Data Vault

| Dimension | Sid / osteosarc.com | Cancer-Buddy Data Vault |
|---|---|---|
| Storage | 25TB Google Cloud | Structured local storage (patient-controlled) |
| Format | Custom data browsers, ad-hoc formats | Standardized JSON schemas |
| Sharing default | Public by default (radical transparency) | Private by default (patient chooses) |
| Access control | Open web | Granular per-recipient, per-scope, with expiry |
| Cost | Significant cloud + engineering costs | Local-first, minimal infrastructure cost |
| Genomic compliance | US-based (no restriction) | China PIPL + genetic resource regulations compliant |
| Data browsers | Custom-built visualization tools | AI-generated summaries + standard JSON viewers |
| Audience | Researchers, public, pharma | Patient, their doctors, authorized researchers |
| Portability | Platform-dependent | JSON export, platform-independent |

---

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
Every revocation must generate a confirmation record sent to the patient containing:
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
1. Notify affected patients with:
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
