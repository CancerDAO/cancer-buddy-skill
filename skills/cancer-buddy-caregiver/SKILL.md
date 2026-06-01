---
name: cancer-buddy-caregiver
description: "支持癌症患者的主要照护者（配偶/父母/成年子女）走过照护全程：陪诊清单、化疗当天准备、家庭分工模板、Zarit 照护负担自评、如何向孩子解释病情、坏消息的情绪预备；也为次要家属提供精简支持模式。Use when 用户以照护者或家属身份求助，需要陪护实务、分担照护负担、或处理照护倦怠。Triggers on: 家属, 陪护, 照护者, 照护倦怠, 我照顾得太累, 我在照顾, 我爸/妈/爱人得癌症, 怎么陪诊, 陪诊清单, 化疗当天带什么, 我太累了."
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: caregiver oncology burnout family-support patient-companion zarit
---

# cancer-buddy-caregiver

Cancer treatment's real operator is often a spouse or adult child. This skill gives them what clinicians rarely offer — practical checklists, a framework for sharing load, permission to take care of themselves, and preparation for the hard moments.

## When to use

- User selected role = caregiver or family in meta-skill.
- User says: 家属 / 陪护 / 照护者 / 照护倦怠 / 我照顾得太累 / 我太累了 / 怎么陪诊 / 陪诊清单 / 化疗当天带什么 / 我爸妈/爱人生病了.
- Any sub-skill detects caregiver-specific distress and routes here.

## Preflight

Per `../../references/preflight.md`: role must be caregiver or family. If patient → refuse + offer "给家人看的要点" 2-page summary.

## Workflow

Determine what the caregiver needs:

1. **First time here** → orient + baseline Zarit screen (see [references/zarit-burden.md](references/zarit-burden.md)). Offer to populate `profile.json.caregivers[]` with the caregiver's `name`, `relation`, `is_primary`, `contact_preference`, and `lives_with_patient` (per the schema's [caregivers[]](../../references/patient-profile-schema.md#caregivers) entry — a documented exception to field-change discipline; this skill owns `caregivers[]` only and touches no other field).
2. **Chemo / radiotherapy / surgery day ahead** → [chemo-companion-checklist.md](references/chemo-companion-checklist.md).
3. **Want to share load** → [family-roles-template.md](references/family-roles-template.md): who does hospital runs, who does pharmacy, who does emotional check-ins, who does finances. Export shareable family doc.
4. **Kids ask what's going on** → [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md) (age-appropriate language).
5. **照护倦怠 / "我照顾得太累了"** → caregiving-burnout support: validate the burnout, surface the self-care prompts, and revisit family-roles load-sharing. A positive burnout/depression screen (Zarit > 21, or an affirmative depression/suicidal statement) escalates to `cancer-buddy-mind` for the caregiver-distress branch. Do NOT keep the caregiver talking only to you.
6. **Preparing for bad news** → soft framework for emotional pre-commitment without being morbid: "你想不想花 10 分钟想一下，如果接下来复查不好，你希望 Ta 得到什么？你希望你自己怎么被对待？"

## Role behavior

- **Role = patient**: refuse + offer 2-page summary of caregiver skill for them to show their caregiver. Do not run workflow.
- **Role = caregiver**: main workflow. All content second-person addressing the caregiver; 30% weight on self-care prompts.
- **Role = family**: concise version. Focus on "how to support the primary caregiver without adding burden". Skip Zarit deep-dive; skip chemo-companion.

## Output

Written under `patients/<patient_code>/reports/caregiver/`:
- `zarit-YYYY-MM-DD.md` — longitudinal burden scores
- `chemo-prep-YYYY-MM-DD.md` — per-companion-day checklist
- `family-roles.md` — editable division-of-labor doc
- `explaining-to-children.md` (if invoked)

## Safety

- Crisis rule applies (from `safety-guardrails.md` role-specific section): caregiver suicidal statement → hand off to `cancer-buddy-mind` with full crisis protocol.
- Never shame burnout. Never say "you should be stronger for them". Burnout is a rational response to an irrational situation.
- Never encourage hiding information from the patient.

## References

- [chemo-companion-checklist.md](references/chemo-companion-checklist.md)
- [family-roles-template.md](references/family-roles-template.md)
- [zarit-burden.md](references/zarit-burden.md) — 22-item Zarit Burden Interview (validated)
- [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md)
- [../../references/roles.md](../../references/roles.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
