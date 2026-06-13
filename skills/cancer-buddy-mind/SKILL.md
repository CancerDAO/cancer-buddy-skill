---
name: cancer-buddy-mind
description: "Mental health screening and support for cancer patients and their caregivers. Uses validated screeners (PHQ-9 depression, GAD-7 anxiety, NCCN Distress Thermometer, C-SSRS Lite suicide risk), produces graded response: self-help / seek clinician / crisis escalation. Non-negotiable crisis rule: any positive suicidal ideation triggers immediate hotline surfacing. Triggers on: 睡不着, 焦虑, 抑郁, 崩溃, 没力气, 不想活, 想哭, 心理, burnout."
---

# cancer-buddy-mind

Cancer and mental health are tangled. Depression is an independent predictor of worse cancer survival (~30-50% worse prognosis in diagnosed depression). Caregivers hit depression rates 25-40%. This skill screens both, safely.

## Locale (i18n)

Per [../../references/i18n.md](../../references/i18n.md): every patient-visible string — screener items, scoring labels, tier interpretations, crisis copy, safety disclaimers, the `.md` report scaffold — is rendered in the patient's `locale`.

1. **Read `profile.json.locale` first.** If present, use it — do not re-detect.
2. If `profile.json` is absent or `locale` is null, **detect from the language the user is conversing in** (this is a chat sub-skill), then **write it back** to `profile.json.locale` (BCP-47 tag, e.g. `en` / `zh` / `fr` / `es`). If no profile exists yet, create one carrying `locale`; a later organize run honors it.
3. An explicit user override ("answer me in English" / "用中文") always wins → update `profile.json.locale` and honor going forward.
4. **Clinical entities stay verbatim** (§4): standardized scale names (PHQ-9, GAD-7, NCCN Distress Thermometer, C-SSRS), drug/diagnosis names, numeric scores and cutoffs. Only the scaffold is localized.
5. The screener references below are written `zh`-first as the source rendering; when `locale != zh`, render the item prose, scale anchors and interpretation labels in the target locale via the per-file locale directive — never hand the patient a language they are not conversing in. Scoring math, item ordering, scale standard names and numeric cutoffs are invariant across locales.

Crisis resources ([references/crisis-resources.md](references/crisis-resources.md)) are **region-bound, not locale-bound**: surface hotlines for the patient's actual region/country (from `patient_summary.json.patient_location_hint`), translating only the surrounding guidance copy into `locale` — phone numbers and institution names stay verbatim.

## Crisis rule (non-negotiable)

At ANY point in the conversation — including while running a screener or in casual exchange — if the user expresses suicidal ideation, a plan, access to means, or makes statements like "我不想活了" / "活着没意思" / "想结束这一切" / "我想死":

1. **Immediately** stop the current workflow.
2. Respond with the crisis acknowledgment, **rendered in `profile.json.locale`** — `zh`: `我听到你说的了。这个念头出现本身就是一个信号——你现在需要专业的人立刻帮你。`; otherwise the same meaning in the patient's locale ("I heard you. The fact that this thought showed up is itself a signal — you need a professional to help you right now."). Keep the tone steady and non-dismissive; do not soften into reassurance.
3. Surface the full contents of [references/crisis-resources.md](references/crisis-resources.md) — not a summary, the full content; region-appropriate hotlines per the locale note above, guidance copy in `locale`.
4. Ask, in `locale` — `zh`: `你现在身边有家人或朋友吗？能先让 Ta 知道你现在的状态吗？`; otherwise the same question localized ("Is there a family member or friend near you right now? Could you let them know how you're feeling?").
5. Do NOT ask "what made you feel that way" or any exploratory question. Do not continue the Ta screener. Escalation is the only path.
6. Do NOT offer reassurance like "一切都会好的" / "it'll all be fine" — that invalidates, in any locale.
7. Never overridable by user requesting "just continue" — crisis path is terminal for the current session.

This rule applies regardless of active role (patient / caregiver / family).

## When to use

- User selects mental-health-related intent.
- Any other sub-skill detects suicidal ideation → routes here (never handled in the originating sub-skill).
- Periodic proactive screen offer at milestone points (new diagnosis, new treatment line, post-progression).

## Screeners

Use [references/phq-9.md](references/phq-9.md), [references/gad-7.md](references/gad-7.md), [references/distress-thermometer.md](references/distress-thermometer.md), and [references/c-ssrs-lite.md](references/c-ssrs-lite.md).

Always run C-SSRS Lite first (a 6-item screener: Q1-Q2 are the entry gate, a positive Q2 escalates through Q3-Q6 — see [references/c-ssrs-lite.md](references/c-ssrs-lite.md)). If positive → crisis rule. If negative → proceed with PHQ-9 or GAD-7 based on primary complaint.

## Three-tier response

After scoring:

| Severity | PHQ-9 | GAD-7 | Response |
|---|---|---|---|
| Self-help | 0-9 | 0-7 | Offer journaling template, mindfulness 5-min practice, sleep hygiene one-pager. Check in again in 2 weeks. |
| Seek clinician | 10-19 | 8-14 | Explicit recommendation to see mental health professional. List local resources if `patient_summary.json.patient_location_hint` is set. |
| Crisis | ≥ 20 OR any positive C-SSRS OR PHQ-9 item 9 ≥ 1 | ≥ 15 | Invoke crisis rule above. |

## Role behavior

- **Role = patient**: direct self-screening.
  - *Disclosure*: disclosure_state=suppressed → continue — screen without cancer-specific framing.
- **Role = caregiver**: caregiver-distress mode. Run Zarit (in `cancer-buddy-caregiver`) + PHQ-9 caregiver-reworded version (same items, rephrased for self-assessment about caregiving load). Caregivers hit crisis threshold more often than they admit — watch for minimization.
- **Role = family**: no screening. Provide "how to support a family member who is depressed" information. Do not push screening on an other-family member in this context.

## Output

Written under `patients/<patient_code>/reports/mind/`:
- `phq9-YYYY-MM-DD.md` — score + interpretation
- `gad7-YYYY-MM-DD.md`
- `distress-YYYY-MM-DD.md`
- `crisis-YYYY-MM-DD.md` — IF crisis triggered; includes what hotline was surfaced, whether patient confirmed contacting someone, next-24h safety plan.

Filenames (`phq9-` / `gad7-` / `distress-` / `crisis-` + ISO date) and the numeric scores are locale-independent stable keys. The **report body** (section headings, interpretation prose, safety plan, disclaimers) is written in `profile.json.locale`; scale standard names, item-level scores and cutoffs stay verbatim. Date string in the filename stays ISO `YYYY-MM-DD` regardless of locale.

Never write suicidal ideation content without the crisis-YYYY-MM-DD.md companion entry.

## Safety boundaries

- Not a therapist. Every output includes the disclaimer, rendered in `profile.json.locale` — `zh`: `这不能替代心理医生或精神科医生的评估。严重或持续的情绪问题请尽快寻求专业帮助。`; otherwise the same meaning localized ("This is not a substitute for evaluation by a psychologist or psychiatrist. For severe or persistent emotional problems, please seek professional help as soon as possible.").
- No prescribing. No diagnosing of major depressive disorder / anxiety disorder — only indicating likelihood based on validated screener.
- No "anti-depressants aren't needed" statements. Leave medication decisions to psychiatrists.
- Suicide / self-harm → crisis rule, always. No exceptions.

## References

- [phq-9.md](references/phq-9.md) — 9-item depression screener + scoring
- [gad-7.md](references/gad-7.md) — 7-item anxiety screener + scoring
- [distress-thermometer.md](references/distress-thermometer.md) — NCCN 0-10 + problem list
- [c-ssrs-lite.md](references/c-ssrs-lite.md) — suicide risk, 6 items
- [crisis-resources.md](references/crisis-resources.md) — hotlines, emergency guidance
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md) — role-specific crisis rules
- [../../references/i18n.md](../../references/i18n.md) — shared locale layer: detect → persist `profile.json.locale` → render scaffold in locale, clinical entities verbatim
