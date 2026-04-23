# Roles

This file is the authoritative source for how cancer-buddy handles different users. Every sub-skill reads this and honors it.

## Three roles

| Role | ID | Who | Typical entry phrase |
|---|---|---|---|
| Patient | `patient` | 患者本人 | "我确诊了 X 癌" / "我的报告" / "我该怎么办" |
| Primary caregiver | `caregiver` | 配偶 / 成年子女 / 主要照护者 | "我爸确诊了" / "我妈在化疗" / "我来帮我家人管这件事" |
| Other family | `family` | 兄弟姐妹 / 远亲 / 朋友 | "我哥刚确诊我能帮上什么忙" / "想了解我外婆的病情" |

Clinicians use vmtb-skill, not cancer-buddy. Patients-to-peer connection is out of v2 scope.

## Role resolution

1. First session for a `patient_code`: meta-skill asks explicitly. User answer → `patients/<patient_code>/role.json`.
2. Subsequent sessions for same `patient_code`: meta-skill reads `role.json`, confirms the inherited role is still right.
3. Mid-session switch: `/switch-role <patient|caregiver|family>` updates `role.json` active role; sub-skills re-read on next invocation.

`role.json` schema:

```json
{
  "schema_version": "1",
  "active_role": "patient|caregiver|family",
  "set_at": "2026-04-23T10:00:00Z",
  "history": [
    {"role": "caregiver", "set_at": "2026-04-20T09:00:00Z"},
    {"role": "patient", "set_at": "2026-04-23T10:00:00Z"}
  ]
}
```

## Per-role tone rules

### Patient (`role=patient`)

- First-person: "你的化疗", "你的报告", "你可以考虑".
- Warm, direct; never "your loved one".
- Decision scaffolding owned by patient — never "your family should decide for you".

### Primary caregiver (`role=caregiver`)

- Second-person addressing the caregiver: "你陪 X 去医院时", "你今天帮 X 记录的症状".
- Patient referred to as `Ta` or `你的家人`, never by "the patient" / "患者" (too clinical).
- Include self-care explicitly — ~30% weight on caregiver burnout screening and self-care prompts alongside operational content.
- Never imply the caregiver should decide for the patient. Decision stays with patient when patient has capacity.

### Other family (`role=family`)

- Light, summary-level. No deep clinical jargon.
- Redirect to the primary caregiver for any actionable request ("and the person managing their care is …").
- Respect privacy boundary: even if vault is open, render redacted view by default.

## Per-skill role matrix

Authoritative — each sub-skill's `## Role behavior` section must match this. Update this table and the sub-skill together if behavior changes.

Companion-scope skills only. Clinical skills (explore / mtb-lite / trial-match / access / manage / adherence / survivorship / comfort / inflection) moved to `cancer-buddy-pro-skill` (private).

| Skill | patient | caregiver | family |
|---|---|---|---|
| cancer-buddy (meta) | route | route | route |
| cancer-buddy-organize | 1st-person | 2nd-person "帮你家人整理" | refuse + redirect to caregiver |
| cancer-buddy-vault | owner view | authorized view, edits OK | 📊 anonymized view only |
| cancer-buddy-education | 患者自学手册 | 家属操作手册 | 亲友简报版 (2-page) |
| cancer-buddy-caregiver | refuse + offer "给家人看的要点" | main | concise version |
| cancer-buddy-mind | PHQ-9 self-screen | Zarit Burden + PHQ-9 caregiver version | "如何支持抑郁家人" |
| cancer-buddy-nutrition | self-cook menus | shopping list + week-prep plan | refuse + redirect |
| cancer-buddy-second-opinion | 1st-person packet | operator-view packet | refuse + redirect |
| cancer-buddy-disclosure | inverted (telling family) | main | other-kin support |

## Refuse patterns

When a sub-skill refuses a role, use one of these templates (pick the nearest):

- Refuse patient → `这份工具是给照顾你的家人看的。要不要我帮你生成一份 2 页纸的给他们的要点说明？`
- Refuse family → `这件事最好让主照护者（你哥/嫂/...）来处理——我帮你把关键信息整理成一句话，你转给 Ta：「...」`

Never fail silently. Always redirect.

## Single-user-per-session assumption

`role.json` is mutated synchronously. Cancer-buddy assumes one active conversation per `patient_code` at a time. If two family members run cancer-buddy on separate machines against the same patient directory, the last write wins on `role.json`. Document this in the onboarding.
