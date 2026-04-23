---
name: cancer-buddy-manage
description: "Manage multiple parallel treatment lines — build the treatment dashboard (active/waiting/stopped per line), run drug-drug interaction checks, generate integrated monitoring calendar (blood, imaging, ctDNA, tumor markers), track RECIST response per line, alert on anomalies. Triggers failure → pathway re-exploration handoff. Use when patient is on or planning multiple treatments simultaneously. Triggers on 多线治疗, 怎么监测, 药物相互作用, RECIST 评估. v1 basic version; side-effects module coming in v2."
---

# cancer-buddy-manage

Manage treatment-in-flight. Multiple lines active at once (trial + standard + supportive), each with its own timeline and monitoring burden.

## When to use

- Patient is actively on one or more treatments.
- Patient says: 多线治疗 / 怎么监测 / 有哪些副作用要注意 (for v1, basic monitoring; deeper side-effect management arrives in v2).

## Preflight

- `patients/<pid>/readiness.json` grade ≥ C.
- `profile.json.treatment_history` must have at least one entry.

## Outputs

Written under `patients/<pid>/reports/manage/`:
- `dashboard.md` — active/waiting/stopped by treatment line (see [references/dashboard-template.md](references/dashboard-template.md))
- `drug-interactions.md` — pairwise interaction check across all active drugs
- `monitoring-calendar.md` — what to test, when, where (labs, imaging, ctDNA, markers)
- `response-assessment.md` — RECIST/iRECIST per line, plain-language interpretation

## Workflow

1. Build dashboard: for each line in `profile.json.treatment_history`, bucket as active / waiting (e.g. IIT awaiting approval) / stopped (with stop-reason: completed / PD / toxicity / patient choice).
2. Drug-interaction check: pairwise scan of active drugs against major DDI databases (stored names in lay glossary; link to references/safety-guardrails.md for CYP/transporter rules).
3. Monitoring calendar: for each active line, derive the monitoring schedule from the drug's label + the regimen protocol (if trial). Render as a patient-friendly calendar with what-when-where rows.
4. Response assessment: for every imaging in `patients/<pid>/` under diagnostic reports, apply RECIST 1.1 rules (sum of target lesions) + iRECIST if immunotherapy active. Explain the response category in plain Chinese (CR/PR/SD/PD + plain meaning).
5. Anomaly alerts: detect trend anomalies (rising LDH, falling HGB > 2 g/dL in 2 weeks, etc.) and surface them as 🚨.

## Handoff

- Line fails (PD or toxicity stop) → hand off to `cancer-buddy-explore` for re-exploration.
- Trial line needs access navigation → hand off to `cancer-buddy-access`.

## v1 scope note

This v1 basic version does NOT include:
- Personalized side-effect management protocols (coming in v2)
- Nutrition support (planned `cancer-buddy-nutrition` sub-skill, v2)

## Safety

Drug-interaction warnings are critical. Never omit a major (D/X) interaction even if it complicates the narrative.

## References

- [dashboard-template.md](references/dashboard-template.md)
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
