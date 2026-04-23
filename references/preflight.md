# Readiness Preflight

Shared entry-gate check for every sub-skill that reads an existing patient directory (`explore`, `mtb-lite`, `trial-match`, `manage`). See `patient-profile-schema.md` §readiness.json for the full schema.

## Step 0 — Role

Check `patients/<patient_code>/role.json` exists. If missing → stop and route back to meta-skill for role selection. If present, read `active_role` (patient / caregiver / family) and branch the sub-skill's behavior per its `## Role behavior` section (authoritative matrix in `roles.md`).

If the sub-skill refuses the current role, emit the refuse + redirect template from `roles.md` and exit without running the main workflow.

Only after role is resolved do the readiness rules below apply.

## Step 1 and 2 — Readiness

1. **File missing** — if `patients/<pid>/readiness.json` does not exist, stop and prompt:
   > `先让抗癌搭子整理病历再继续：请触发 cancer-buddy-organize。`
   Do NOT proceed to the sub-skill's main workflow.

2. **Grade below C** — if `readiness.grade` ∈ {`D`, `F`}, stop and prompt:
   > `目前数据完备度 <grade>（<score>/100），缺项：<blocking_gaps>。建议先补齐这些资料，或重新触发 cancer-buddy-organize 做一次深度挖掘，再跑这一步。`
   Only proceed if the user explicitly insists (record the override in the report footer).

Grades A / B / C → proceed silently.

## Why the gate exists

Sub-skills that reason over missing molecular drivers, unknown staging, or absent treatment history produce actively misleading output. The gate fails fast before the patient sees bad evidence. Re-running organize (step 2 of `cancer-buddy-organize`) with the newly supplied records is the deterministic recovery path.
