# Readiness Preflight

Shared entry-gate check for every sub-skill that reads an existing patient directory (`explore`, `mtb-lite`, `trial-match`, `manage`). See `patient-profile-schema.md` §readiness.json for the full schema.

## Two rules

1. **File missing** — if `patients/<pid>/readiness.json` does not exist, stop and prompt:
   > `先让抗癌搭子整理病历再继续：请触发 cancer-buddy-organize。`
   Do NOT proceed to the sub-skill's main workflow.

2. **Grade below C** — if `readiness.grade` ∈ {`D`, `F`}, stop and prompt:
   > `目前数据完备度 <grade>（<score>/100），缺项：<blocking_gaps>。建议先补齐这些资料，或重新触发 cancer-buddy-organize 做一次深度挖掘，再跑这一步。`
   Only proceed if the user explicitly insists (record the override in the report footer).

Grades A / B / C → proceed silently.

## Why the gate exists

Sub-skills that reason over missing molecular drivers, unknown staging, or absent treatment history produce actively misleading output. The gate fails fast before the patient sees bad evidence. Re-running organize (step 2 of `cancer-buddy-organize`) with the newly supplied records is the deterministic recovery path.
