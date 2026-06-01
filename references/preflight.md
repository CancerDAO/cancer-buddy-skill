# Readiness Preflight

Shared entry-gate check for every companion sub-skill in this public bundle that reads an existing patient directory: `cancer-buddy-organize`, `cancer-buddy-education`, `cancer-buddy-nutrition`, `cancer-buddy-second-opinion`, `cancer-buddy-disclosure`, `cancer-buddy-caregiver`. See `patient-profile-schema.md` §readiness.json for the full schema.

## Step 0 — Role

Check `patients/<patient_code>/role.json` exists. If missing → stop and route back to meta-skill for role selection. If present, read `active_role` (patient / caregiver / family) and branch the sub-skill's behavior per its `## Role behavior` section (authoritative matrix in `roles.md`).

If the sub-skill refuses the current role, emit the refuse + redirect template from `roles.md` and exit without running the main workflow.

Only after role is resolved do the readiness rules below apply.

## Step 1.5 — Disclosure

Read `profile.disclosure_state`. If the file itself doesn't have the field, treat as `"full"` (back-compat with v1/v2 profiles).

If `disclosure_state = "suppressed"` AND current `active_role = "patient"`: apply this sub-skill's suppressed-patient behavior per `references/disclosure-behavior.md`. Do not proceed to Step 2 readiness rules in the default path — the behavior variant may refuse, soften, or continue with abstracted language.

If `disclosure_state` is `"partial"`: treat as `"full"` for routing purposes but be cautious with diagnostic specifics; prefer softer framing.

If role is `caregiver` or `family`: disclosure state does not gate behavior (they know regardless).

## Step 1 and 2 — Readiness

1. **File missing** — if `patients/<pid>/readiness.json` does not exist, stop and prompt:
   > `先让抗癌搭子整理病历再继续：请触发 cancer-buddy-organize。`
   Do NOT proceed to the sub-skill's main workflow.

2. **Grade below C** — if `readiness.grade` ∈ {`D`, `F`}, stop and prompt:
   > `目前数据完备度 <grade>（<score>/100），缺项：<blocking_gaps>。建议先补齐这些资料，或重新触发 cancer-buddy-organize 做一次深度挖掘，再跑这一步。`
   Only proceed if the user explicitly insists (record the override in the report footer).

Grades A / B / C → proceed silently.

## Step 2.5 — Review-flags gate (red flags must be human-confirmed)

After the readiness grade check, read `readiness.json.review_flags[]`. For each entry where `severity == "red"` AND `user_confirmed == false`, the sub-skill MUST refuse to proceed with normal workflow.

**Why this is a separate gate from grade**: the readiness grade measures *coverage* (how many fields are populated). Review flags measure *correctness* (whether populated fields are trustworthy). A patient_dir can be grade A (every field populated) and still have a 🔴 RED flag saying "current_therapy OCR'd as drug X but orders sheet says drug Y" — the data is COMPLETE but WRONG. Downstream sub-skills that consume `current_therapy`, `stage`, `molecular_drivers_known`, `treatment_history` etc. will produce confidently-wrong output if a RED flag goes unconfirmed.

**Block behavior:**

```
你之前 organize 的时候，系统标了 <N> 个 🔴 待确认项 — 这些字段直接影响这次要做的事，需要你先确认或 override 才能继续：

<for each unconfirmed RED flag>
- field: <field_path>
  现写: <current_value>
  可疑点: <issue>
  建议: <suggested_value>
</for>

你可以:
1. 接受建议 — 我会更新 profile.json 后继续
2. 保留原写 — 我会在本次报告页脚标注 "用户已 override RF-xxx"
3. 自定义值 — 直接告诉我正确写法
4. 暂缓 — 先去做 cancer-buddy-organize 进一步核对再回来

等你回复。
```

Only after every unconfirmed RED flag is resolved (`user_confirmed = true` with explicit `accept_suggestion` / `keep_original` / `custom_value`) does the sub-skill proceed.

🟡 yellow / 🟢 green flags **do NOT block** — they are surfaced in the sub-skill's report footer as "整理时已标记的待核对项 (不阻塞)" but the workflow runs.

**Override recording**: when the user picks `keep_original` or explicitly says "继续 anyway", append to the sub-skill's final report footer:
```
> ⚠️ 用户对 organize 的 🔴 review_flag 选择了 override (RF-xxx, RF-yyy):
>   - RF-xxx: <field_path> 保留原值 "<current_value>" — 用户原因: <user-stated reason or "未说明">
> 本报告基于此值生成。如该值实际有误, 报告结论需相应调整。
```

This is non-negotiable. A sub-skill that consumes `profile.json` without checking RED flags is non-compliant. **Affected sub-skills**: anything using `current_therapy` (nutrition, mtb-lite, find-care), `stage` / `histology` (education, find-care, second-opinion), `treatment_history` (mtb-lite, second-opinion, education), `molecular_drivers_known` (mtb-lite, find-care, second-opinion).

## Why the gate exists

Sub-skills that reason over missing molecular drivers, unknown staging, or absent treatment history produce actively misleading output. The grade gate fails fast before the patient sees bad evidence. Re-running organize (step 2 of `cancer-buddy-organize`) with the newly supplied records is the deterministic recovery path.

The Step 2.5 gate adds a second failure mode: data is *present* but *wrong*. Without this gate, an OCR error at organize time silently propagates into every downstream report — which has actually happened in the field (real case: OCR misread "雷替曲塞 + 信迪利单抗" as "瑞戈非尼 + 伊立替康", and the nutrition skill produced a full TKI-themed meal plan with low-fat-breakfast medication timing — clinically wrong, but no gate caught it because the field was *populated*, just *wrong*).

## Step 3 — Schema validity

Optionally run `scripts/validate-profile-schema.sh patients/<patient_code>/` before producing output. Critical failures (missing required fields, corrupt JSON) block the workflow and surface the specific error. Warnings (optional field missing) proceed.
