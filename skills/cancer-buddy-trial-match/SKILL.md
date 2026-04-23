---
name: cancer-buddy-trial-match
description: "Patient-view clinical trial matching using TrialGPT dual-source protocol (ClinicalTrials.gov + ChiCTR) with criterion-level eligibility assessment (✅/❌/⚠️/❓) and patient-friendly output. Produces an HTML report the patient can use to contact study centers. Uses 匹配 never 推荐. Triggers on 帮我找临床试验, clinical trial matching, 试验匹配, 我符合哪些试验."
---

# cancer-buddy-trial-match

Match the patient's molecular + clinical profile against open trials in ClinicalTrials.gov and ChiCTR. Present the results patient-friendly — which trials you may qualify for, what the inclusion criteria mean in plain Chinese, how to contact the center.

## When to use

- Patient says: 帮我找临床试验 / clinical trial / 试验匹配 / 我符合哪些试验.
- After mtb-lite or explore identifies investigational options worth pursuing.

## Preflight

Apply [../../references/preflight.md](../../references/preflight.md) (readiness-gate: file must exist, grade ≥ C). Additionally require at least one molecular driver in `profile.json` — without a target, trial matching is weak.

## Workflow (TrialGPT protocol)

See [references/trial-matching.md](references/trial-matching.md) for the full protocol. Summary:

1. **Search plan** — generate JSON with 8 keyword dimensions (driver gene, variant, cancer type, stage, line of therapy, prior regimens, comorbidities, geography).
2. **Parallel query** — ClinicalTrials.gov API + ChiCTR MCP (`mcp__chictr__search_trials`).
3. **Hard filters** — reject trials that violate line-of-therapy rules, exclude patients with prior failed drugs in inclusion criteria, or require negative biomarker that patient has.
4. **Criterion-level scoring** — for each surviving trial, assess each inclusion/exclusion criterion: ✅符合 / ❌不符合 / ⚠️边界 / ❓缺失.
5. **Matching grades** (R1–R5 in reference file) — translate criterion mix into overall grade.
6. **Validate IDs** — every NCT/ChiCTR id must be confirmed against the official API before inclusion.

## Output

Written under `patients/<pid>/reports/trials/`:
- `trials-report.html` — patient-viewable ranked list
- `trials-report.md` — source markdown
- `trials-raw.json` — structured trial data for downstream access sub-skill

## Patient-friendly rules

- Use **匹配** never 推荐.
- Every inclusion criterion explained in plain Chinese alongside the English text.
- "Contact this center" action items: center name, phone (if public), registration URL.
- Warn: "匹配 ≠ 入组。最终以研究中心预筛为准。"
- Budget impact: flag whether the trial sponsor covers drug, imaging, hotel, travel (look up from trial protocol).

## Safety

Apply `safety-guardrails.md` rules:
- Evidence grading — annotate every matched trial with the phase (I/II/III) and whether the underlying mechanism has A/B/C/D evidence.
- Eligibility vs labs — when eligibility hinges on organ-function thresholds (ECOG, ANC, bilirubin, creatinine), cross-check against the latest labs in `profile.json`; flag ⚠️ if labs are stale or missing.
- 匹配 ≠ 入组 — every report footer repeats the `匹配 ≠ 入组。最终以研究中心预筛为准。` warning.

## Handoff

- Trial IDs from this output feed `cancer-buddy-access` when the patient decides to pursue one.
- If patient wants the trial in the context of a full treatment plan, route back to `cancer-buddy-explore` or `cancer-buddy-mtb-lite`.

## References

- [trial-matching.md](references/trial-matching.md) — full TrialGPT dual-source protocol
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
