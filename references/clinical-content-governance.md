# Clinical Content Governance

This contract applies to every patient-facing medical or legal claim produced by Cancer Buddy.
It complements `safety-guardrails.md`; when two instructions conflict, use the stricter rule.

## 1. Claim lifecycle

A version-sensitive claim may reach a patient only when all fields below are available:

```yaml
claim_id: stable-id
claim_text: one atomic claim
population: cancer type, stage, treatment setting, age, and other applicability limits
jurisdiction: CN|US|EU|other
source_type: guideline|regulator_label|law|systematic_review|trial
source_url: direct primary-source URL
version_or_date: YYYY-MM-DD or exact version
accessed_at: YYYY-MM-DD
certainty: high|moderate|low|very_low|not_assessed
recommendation_strength: strong|conditional|not_applicable|not_assessed
reviewer_role: oncologist|pharmacist|dietitian|pathologist|palliative|legal|other
reviewed_at: YYYY-MM-DD
expires_at: YYYY-MM-DD
patient_facing_allowed: true|false
```

Required behavior:

- Keep each claim atomic. Do not attach one citation to a paragraph containing multiple conclusions.
- Use the source's actual population and setting. Do not extrapolate across cancer types, stages,
  treatment intents, drugs, formulations, age groups, or jurisdictions.
- `certainty` and `recommendation_strength` are separate. Never infer either from study phase alone.
- When any required field is missing, expired, or contradictory, do not render the claim as current
  guidance. State what is unconfirmed and give the primary-source question to verify.
- A model-generated summary is not a clinical review. `reviewed_at` requires a named-role human
  review in the product's governed content process.

## 2. Source hierarchy and answer-time verification

Use direct, current primary sources:

1. Regulator-approved product label for drug administration, contraindications, dose modification,
   organ-function requirements, and food or drug interactions.
2. Current professional-society or government guideline for cancer-specific care pathways.
3. Current statute, regulation, or regulator guidance for legal and privacy statements.
4. Trial registry and primary publication for clinical-trial claims.
5. Systematic reviews or primary studies for background education, with limitations stated.

NCI PDQ and similar summaries are useful evidence syntheses, but they are not automatically a
professional-society guideline. Search-engine snippets, hospital marketing pages, rankings, model
memory, and bundled snapshots are never sufficient for a current clinical or legal claim.

Answer-time verification is mandatory for drug labels, treatment regimens or line of therapy, approvals,
reimbursement, trial status, center services, guideline recommendations, prognostic estimates,
interactions, and law. An authorized, legitimately held local primary source counts only when its
publisher, title, version/date and relevant page are verifiable; otherwise use the current official online
source. Source failure is a normal outcome: fail closed and mark the item `unconfirmed` rather than
filling the gap from memory.

## 3. Patient-specific boundaries

- Do not diagnose, stage, score ECOG, classify response, estimate prognosis, select treatment,
  recommend dose changes, or decide that a test is indicated.
- A patient or caregiver may correct demographics and describe symptoms, function, medicines, and
  preferences. Their confirmation does not convert a patient report into a clinician-verified fact.
- Preserve `source_reported`, `patient_reported`, and `system_normalized` as separate layers.
  Conflicts remain `disputed` until an amended source document or authorized clinician attestation
  resolves them.
- Preserve the original term and value. A validated normalized field and a plain-language translation
  may be added beside it; neither may overwrite the source.
- Tumor-marker movement, symptoms, wearable data, or lesion-description changes are observations,
  not response or progression. Copy response categories only when a source clinician explicitly states
  them, and attach the source.

## 4. Emergency and toxicity routing

Cancer Buddy may provide general red-flag routing, but it does not calculate a universal toxicity
threshold from static rules. Use the treating team's written emergency plan when available. Otherwise:

- New severe or rapidly worsening symptoms, breathing difficulty, major bleeding, new confusion,
  seizure, inability to keep fluids down, or other possible emergencies require immediate local
  emergency assessment.
- Fever during cytotoxic chemotherapy can be a medical emergency. Tell the patient to contact the
  oncology team's urgent number immediately and follow that team's stated temperature threshold;
  if unavailable or the patient is acutely unwell, use local emergency care.
- Suspected immune-related toxicity is not managed as routine chemotherapy side effects. Escalate
  promptly to the oncology team; severe symptoms need emergency assessment.
- Do not tell a patient to start, stop, delay, or change prescription medicines based on the skill.

Platform-level self-harm and suicide-risk handling is owned by the host LLM safety layer. This skill
must not disable, contradict, or override that layer.

## 5. Clinical content review

Minimum review roles before enabling affected patient-facing claims:

- oncology plus the relevant disease specialty for cancer pathways;
- oncology pharmacist for labels, drug interactions, food interactions, and supplements;
- registered dietitian for nutrition and perioperative or symptom-directed diets;
- palliative-care or pain clinician for cancer pain, opioids, hospice, and serious-illness communication;
- pathologist or molecular diagnostician for pathology, biomarkers, and genomic data;
- qualified counsel/privacy officer for medical disclosure, privacy, human-genetic-resource, and
  cross-border statements.

Every governed claim needs an expiry policy. A release must fail closed when an expired claim would
otherwise appear in patient-facing output.

## 6. Baseline primary sources

These sources support the safety architecture, not individual treatment recommendations:

- NCI, Palliative Care in Cancer: https://www.cancer.gov/about-cancer/advanced-cancer/care-choices/palliative-care-fact-sheet
- CDC, Watch Out for Fever: https://www.cdc.gov/cancer-preventing-infections/patients/fever.html
- NCI, Cancer Therapy Interactions With Foods and Dietary Supplements:
  https://www.cancer.gov/about-cancer/treatment/cam/hp/dietary-interactions-pdq
- NCI, Nutrition During Cancer Treatment:
  https://www.cancer.gov/about-cancer/treatment/side-effects/nutrition
- RECIST Working Group/EORTC, RECIST 1.1: https://recist.eortc.org/recist-1-1/
- PRC Physicians Law: https://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313104.html
- PRC Personal Information Protection Law:
  https://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html
- MOST, Rules for the Regulation of Human Genetic Resources:
  https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/bmgz/202306/t20230601_186416.html

Last evidence check for this governance file: 2026-07-17. Answer-time verification still applies.
