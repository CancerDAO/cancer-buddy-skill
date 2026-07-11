---
name: cancer-buddy-caregiver
description: "Operator-grade support for the primary caregiver (spouse / parent / adult child) through the cancer journey. Covers chemo companion checklists, family division-of-labor templates, Zarit Burden self-assessment, how-to-talk-to-children, grief preparation. Also serves secondary family members in a concise summary mode. Refuses patient role with a redirect. Triggers on: 家属, 陪护, 照护者, burnout, 我在照顾, 我爸/妈/爱人得癌症, 怎么陪诊, 我太累了."
---

# cancer-buddy-caregiver

Before role checks or the main workflow, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md) and the suicide-safety rules in [`safety-guardrails.md`](../cancer-buddy/references/safety-guardrails.md). Urgent safety help never requires an archive.

Cancer treatment's real operator is often a spouse or adult child. This skill gives them what clinicians rarely offer — practical checklists, a framework for sharing load, permission to take care of themselves, and preparation for the hard moments.

## When to use

- User selected role = caregiver or family in meta-skill.
- User says: 家属 / 陪护 / burnout / 我是照顾者 / 我太累了 / 怎么陪诊 / 我爸妈/爱人生病了.
- Any sub-skill detects caregiver-specific distress and routes here.

## Locale

Per `../cancer-buddy/references/i18n.md`: if the caller / host supplies `locale` (the user's explicit product UI language), use it first. Otherwise read `profile.json.locale` when a verified patient archive is already open; if absent (or no profile yet), detect it from the **language the caregiver is conversing in** (the current chat input) and use it for this session. Do **not** create a partial `profile.json` or modify a clinical archive merely to save a language preference — persist only through the canonical organizer/host preference store after the user asks. An explicit user override ("answer me in English" / "用中文") always wins for the current and later turns.

Render **every caregiver-visible output in that locale** — orientation copy, Zarit questionnaire, chemo-companion checklist, family-roles template, explaining-to-children scripts, the bad-news framing prompt, diff cards and routing copy. **Keep clinical entities verbatim** (drug names, genes/variants, TNM/stage, numbers + units, scale standard names) per `i18n.md` §4 — mistranslating one is a P0 safety bug. The reference files below carry their scaffold in `zh`; treat them as the source string table and render the localized equivalent at output time (§5 of `i18n.md`).

## Preflight

Per `../cancer-buddy/references/preflight.md`: safety gates (medical-emergency + suicide-safety) run first; conversation role adapts content and tone only — it is not an authorization gate. If the speaker is the patient, skip the caregiver workflow and offer a 2-page "key points for the family" summary instead, localized to the active locale.

## Workflow

Determine what the caregiver needs:

1. **First time here** → orient + baseline Zarit screen (see [references/zarit-burden.md](references/zarit-burden.md)). Offer to populate `patient_summary.json.caregivers[]` with their name + relation + contact — write only with the caregiver's explicit consent and a verified archive authorization scope, never automatically.
2. **Chemo / radiotherapy / surgery day ahead** → [chemo-companion-checklist.md](references/chemo-companion-checklist.md).
3. **Want to share load** → [family-roles-template.md](references/family-roles-template.md): who does hospital runs, who does pharmacy, who does emotional check-ins, who does finances. Export shareable family doc.
4. **Kids ask what's going on** → [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md) (age-appropriate language).
5. **"I'm at the end of my rope"** → a Zarit hard-trigger hit (题22 总体负担 ≥3, 或题 5/9/17/18 ≥3 — see [references/zarit-burden.md](references/zarit-burden.md)) or affirmative suicidal statement → route to `cancer-buddy-mind` for caregiver-distress branch. Do NOT keep caregiver talking only to you.
   - **When she plainly says "我快撑不住了"**: don't open a long opt-in menu. Lead with just two: "我在，先陪你说说话" 和 "也可以帮你想想眼下这几件事怎么分出去一点"。其余（喘息安排、Zarit、找人接手）等她接话、有力气了再提，不要一次全端上来。
   - **Make 喘息 (respite) concrete for a solo caregiver** — 不是"你歇一歇"这种空话，而是能真的够得到的几个口子：请**短期护工/陪护**顶两三个小时或一个夜班（医院附近护工中介、住院部护士站通常能给联系方式）；找**医院社工部**（很多三甲医院有，能协调陪护资源、经济援助、喘息安排）；问本地**社区卫生服务中心或安宁疗护/宁养服务**有没有"喘息服务"（部分地区提供上门或短期接手照护）。按她所在地和患者情况给 1–2 个最够得着的，不要罗列一长串。
   - **One tiny no-pressure rest for the next few hours** — 不是"今天好好睡"（她大概睡不着），而是一件小的、马上能做的：接下来这几个小时，把手机静音 20 分钟坐下来喝口热的，或者让别人替你守一小时你先躺平闭眼——不用睡着，躺着就行。
   - **Continuity signal**: 结束前留一句"我明天还在，你随时回来"，让她知道这不是一次性的。
6. **Preparing for bad news** → soft framework for emotional pre-commitment without being morbid; render in `profile.json.locale`. `zh` source phrasing: "你想不想花 10 分钟想一下，如果接下来复查不好，你希望 Ta 得到什么？你希望你自己怎么被对待？"

## Role behavior

- **Role = patient**: offer the 2-page summary of this skill for them to show their caregiver instead of running the caregiver workflow. (Summary in the active locale.)
- **Role = caregiver**: main workflow. All content second-person addressing the caregiver, in `profile.json.locale`; 30% weight on self-care prompts.
- **Role = family**: concise version. Focus on "how to support the primary caregiver without adding burden". Skip Zarit deep-dive; skip chemo-companion. (In `profile.json.locale`.)

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

- [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md) — shared locale layer (host `locale` first, otherwise profile locale / detection fallback / persist / verbatim-clinical)
- [chemo-companion-checklist.md](references/chemo-companion-checklist.md)
- [family-roles-template.md](references/family-roles-template.md)
- [zarit-burden.md](references/zarit-burden.md) — 22-item Zarit Burden Interview (validated)
- [explaining-cancer-to-children.md](references/explaining-cancer-to-children.md)
- [../cancer-buddy/references/roles.md](../cancer-buddy/references/roles.md)
- [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md)
- [../cancer-buddy/references/terminology.md](../cancer-buddy/references/terminology.md)
