# Cancer Buddy

Cancer Buddy is a non-clinical navigation skill for people affected by cancer and authorized caregivers. It organizes records, explains stable concepts, looks up and explains — with sources — what current authoritative guidelines / standard care generally say, prepares visit questions, discovers public resources, and builds source-traceable packets. It does not diagnose, restage, infer ECOG/response/progression/prognosis, or choose treatment for you personally.

## Modules

| Module | Purpose | Boundary |
|---|---|---|
| `cancer-buddy-organize` | Provenance-preserving record organization | No inferred stage, response, ECOG, progression, treatment line, or test indication |
| `cancer-buddy-visit-prep` | Snapshot, bring-list, and questions | Questions only |
| `cancer-buddy-education` | Patient education | Version-sensitive claims require answer-time verification against a current primary source and fail closed |
| `cancer-buddy-nutrition` | Symptom-directed food education and interaction verification | No automatic cancer/phase-based prescription |
| `cancer-buddy-caregiver` | Visit logistics, family roles, child communication | Family relationship is not record authority |
| `cancer-buddy-disclosure` | Information-preference and communication support | No model capacity determination or maintained deception |
| `cancer-buddy-find-care` | Official institutions, clinicians, services, and trial sites | Unranked resources; no quality recommendation or eligibility decision |
| `cancer-buddy-case-precedent` | Case-report retrieval | Complete outcomes and differences; no similarity score, treatment direction, or prognosis |
| `cancer-buddy-second-opinion` | Source summary, index, questions, and send checklist | Live logistics verification; no automatic transmission |
| `cancer-buddy-vault` | Local inventory, permissions, export, and audit workflow | Host authentication required; patient code is not authorization |

The repository also includes the `cancer-buddy` router and the `web-access` retrieval layer.

## Clinical safety model

- Preserve every source clinical string. Validated normalization and patient-language translation are additive, labeled layers; they never silently replace the source.
- Keep `source_reported`, `patient_reported`, `caregiver_reported`, and `system_normalized` data separate.
- Do not derive RECIST/response/progression from imaging, markers, or symptoms; do not infer ECOG or treatment line.
- Guidelines, labels, interactions, trials, institutions, laws, and prognosis figures require current primary-source verification. If verification fails, version-sensitive detail is withheld rather than reconstructed from model memory.
- Laboratory display uses the exact result's unit, reference range, report flag, and critical flag. Code does not assign clinical severity.
- Platform-level self-harm/suicide safety remains the responsibility of the host LLM; this skill does not add a competing path.

See [`references/clinical-content-governance.md`](references/clinical-content-governance.md).

## Install

```bash
npx skills add CancerDAO/cancer-buddy-skill -g --all
# or project-local
npx skills add CancerDAO/cancer-buddy-skill --all
```

See [INSTALL.md](INSTALL.md). Cancer Buddy does not automatically install or invoke another clinical skill at runtime. Any separate trial-matching tool remains subject to current-protocol review by the research site.

## Data and authorization

The default patient-root chain is:

```text
$CANCER_BUDDY_PATIENTS_DIR
→ $VMTB_PATIENT_DATA_ROOT
→ $HOME/CancerDAO/patients
```

Patient codes are random storage locators, not credentials. Originals remain in access-controlled `raw/`; derived sidecars and delivered surfaces are text-masked and minimized but may remain re-identifiable. Patient-specific access and export require host authentication and explicit, purpose-limited, revocable authorization.

## Test

```bash
bash tests/eval/run.sh
for test in tests/unit/*.sh tests/integration/*.sh; do bash "$test"; done
```

This tool supports organization, education, and communication preparation. It is not medical advice. For acute dangerous symptoms, follow the treating team's instructions or seek local emergency care.

License: [MIT](LICENSE). Project: [CancerDAO](https://github.com/CancerDAO).
