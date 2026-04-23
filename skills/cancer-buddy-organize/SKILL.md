---
name: cancer-buddy-organize
description: "Organize patient medical records from PDF/images/docx into a canonical patients/<id>/ directory with profile.json, timeline.md, readiness.json, OCR sidecars, and 01_当前状态…11_诊断证明 buckets. Use when the user hands over a folder of medical records, or says 病历整理, 我有一堆报告, 帮我整理报告. Delegates the OCR + structure extraction to the cb-organizer subagent."
---

# cancer-buddy-organize

Turn raw medical records into structured data every other sub-skill can use.

## When to use

- User provides a folder path or set of files (PDF, JPG, PNG, DOCX, ZIP).
- User asks: 病历整理 / 帮我整理这些报告 / 我有一堆检查单.
- Any other sub-skill detects missing `profile.json` / `readiness.json` and prompts the user to run organize first.

## Inputs

- Path to a folder OR list of file paths OR a zip archive.

## Outputs

Written under `patients/<patient_code>/`:
- `INDEX.md` (first line: `# patient_code: <pid>`)
- `profile.json` (conforms to `references/patient-profile-schema.md`)
- `timeline.md` (human-readable treatment timeline)
- `readiness.json` (MTB readiness score)
- `case_text.md` (consolidated narrative)
- `01_当前状态/`…`11_诊断证明/` (raw file buckets)
- `ocr/` (OCR sidecars)

## Workflow

1. **Resolve input** — if zip, unpack to temp dir; if folder, walk; if file list, read in place.
2. **Delegate to subagent** — invoke `cb-organizer` subagent with input path. The subagent does OCR, classification, schema extraction.
3. **Verify outputs** — check that `profile.json` validates against schema and that required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are present.
4. **Grade readiness** — verify `readiness.json` was written; if grade is F or D, present the information-gap checklist 🔴🟡🟢 to the patient.
5. **Output summary** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules.

## patient_code collision

If the generated `patient_code` (e.g. `PT-17CE02BC33`) already exists under `patients/`, subagent should append `_2`, `_3`, etc., and announce the assigned id in the summary.

## Configurable root

`patients/` root defaults to the current working directory. Override with `CANCER_BUDDY_PATIENTS_DIR` env var.

## Next-step guidance

After successful organize, route the patient to the most relevant next sub-skill based on their initial question:
- Newly diagnosed, wants to understand → `cancer-buddy-explore` (maximal diagnostics tier)
- Has gene report, wants treatment guidance → `cancer-buddy-mtb-lite`
- Looking for trials → `cancer-buddy-trial-match`

## References

- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
