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

1. **Resolve input** — if zip, unpack to temp dir; if folder, walk; if file list, read in place. Confirm the path with the user before proceeding.
2. **Dispatch `cb-organizer` subagent.**

   Invoke via the `Agent` tool:
   - `subagent_type: cb-organizer`
   - prompt body includes:
     - `plugin_root: <this plugin's root path>`
     - `input_path: <user-supplied path, resolved>`
     - `patient_code: <optional — auto-generated from hash if missing>`
     - `patient_data_root: <optional — defaults to $CANCER_BUDDY_PATIENTS_DIR, falling back to $VMTB_PATIENT_DATA_ROOT, then $HOME/CancerDAO/patients>`

   The subagent unpacks the input, uses Claude vision for OCR on images, classifies files into the 11-bucket taxonomy, and writes the canonical `<patient_dir>/` (INDEX.md + timeline.md + readiness.json + case_text.md + profile.json + OCR sidecars). It returns JSON containing `patient_dir`, `files_classified`, `readiness_grade`, `readiness_score`, `blocking_gaps`.

3. **Verify outputs** — read the returned JSON; confirm `profile.json` exists and required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are present. If any are missing, surface to the user as a blocker.
4. **Grade readiness** — from the returned JSON take `readiness_grade` + `readiness_score`; if grade is F or D, present the information-gap checklist 🔴🟡🟢 to the patient.
5. **Output summary** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules.

If the subagent registry is not yet set up (`~/.claude/agents/cb-organizer.md` missing), surface the one-time install step (`bash scripts/install.sh` from this plugin, then restart Claude Code) before proceeding.

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
