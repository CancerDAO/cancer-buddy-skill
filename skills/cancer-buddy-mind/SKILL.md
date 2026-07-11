---
name: cancer-buddy-mind
description: >-
  Provide cancer-context mental-health support, direct suicide-safety assessment, collaborative safety planning, and optional use of validated PHQ-9, GAD-7, NCCN Distress Thermometer, or C-SSRS forms. Use when a patient, caregiver, or family member mentions 睡不着、焦虑、抑郁、崩溃、想哭、burnout、绝望、自伤、自杀、不想活，or asks for emotional support or a mental-health screen. Immediate danger gets real-world emergency help first; passive thoughts still receive support but are not automatically treated as an attempt in progress.
---

# cancer-buddy-mind

Before screening, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md). An overdose, self-harm act already in progress, loss of consciousness, or other medical emergency needs local emergency services immediately.

Cancer can place heavy emotional strain on patients and families. Start with what the person needs now; screening is optional, not an entry fee for support.

## Locale (i18n)

Per [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md): every patient-visible string — screener items, scoring labels, tier interpretations, crisis copy, safety disclaimers, the `.md` report scaffold — is rendered in the patient's `locale`.

1. If the caller / host supplies `locale`, use it first.
2. Otherwise read `profile.json.locale` when a verified patient archive is already open; if absent, use the conversation language for this session.
3. Do **not** create a partial `profile.json` or modify a clinical archive merely to save language preference. Persist a preference only through the canonical organizer/host preference store and only after the user asks to save it.
4. An explicit language change always wins for the current and later turns.
5. **Clinical entities stay verbatim** (§4): standardized scale names (PHQ-9, GAD-7, NCCN Distress Thermometer, C-SSRS), drug/diagnosis names, numeric scores and cutoffs. Only the scaffold is localized.
6. Use an official validated form in the user's language when one exists. A model-generated translation can support conversation but must not be labeled a validated administration or scored with published cutoffs as though validated.

Crisis resources ([references/crisis-resources.md](references/crisis-resources.md)) are **region-bound, not locale-bound**. Do not infer location from language or trust an unverified archive role as identity/authorization.

## Suicide-safety rule (non-negotiable)

At any point, suicidal thoughts, a plan, preparation, self-harm, or overdose pause the ordinary workflow. Do not require role selection, an archive, or a questionnaire.

1. Acknowledge steadily: `谢谢你告诉我。我会先陪你把现在这一刻弄安全。`
2. Ask directly: `你现在正准备伤害自己，或已经做了什么/吃了什么吗？` Then ask about current intent, a specific plan, access to means, and whether the person is alone. Asking directly does not increase suicidal thoughts.
3. If an act/overdose is underway, or there is current intent with a plan and accessible means, call the local emergency number now (mainland China: **120**), involve a nearby trusted person, do not let the person drive, and reduce access to means when it can be done safely. Keep the conversation focused on connecting help.
4. If thoughts are present without current intent/plan/means, continue supportive conversation and build a near-term safety plan: a trusted contact, reduced access to means, a same-day crisis/clinical contact, and a clear escalation destination. Offer one or two region-appropriate contacts from `crisis-resources.md`; do not dump the whole file.
5. If the person declines a hotline, do not abandon them or end the session. Ask for the next safest feasible real-world step and continue listening.
6. Avoid false reassurance or guilt. Once immediate safety is assessed, it is appropriate to ask what is happening and listen without judgment.

This rule applies regardless of active role (patient / caregiver / family).

## When to use

- User selects mental-health-related intent.
- Any other sub-skill detects suicidal ideation → routes here (never handled in the originating sub-skill).
- Offer—not force—a screen when symptoms are persistent, the user asks for one, or a check-in would be useful.

## Screeners

Use [references/phq-9.md](references/phq-9.md), [references/gad-7.md](references/gad-7.md), [references/distress-thermometer.md](references/distress-thermometer.md), and [references/c-ssrs-lite.md](references/c-ssrs-lite.md).

Ask permission before a formal screener. Use an official validated translation for the person's language; if unavailable, say that a conversational translation is **not** a validated administration and do not apply the published cutoff as if it were. Do not reword PHQ-9/GAD-7 items for caregivers while retaining the original scoring.

- Use C-SSRS when suicide risk needs structured assessment, following its official skip logic. A passive wish-to-die answer prompts support and further assessment; it does not by itself prove imminent danger.
- Use PHQ-9 for depressive symptoms, GAD-7 for anxiety, and NCCN Distress Thermometer for broad cancer-related distress. Cancer/treatment symptoms can inflate somatic items, so interpret scores as screens—not diagnoses.

## Three-tier response

After scoring:

| Severity | PHQ-9 | GAD-7 | Response |
|---|---|---|---|
| Lower symptoms | 0-9 | 0-9 | Offer practical coping support and ask what would help now; suggest follow-up if persistent or impairing. |
| Clinician follow-up | 10-19 | 10-14 | Encourage timely evaluation by a qualified mental-health or oncology professional; consider faster follow-up when functioning is impaired. |
| Urgent clinician follow-up | 20-27 without item 9 | 15-21 | Arrange prompt professional assessment. High total score alone is not proof of immediate suicide danger. |

Any PHQ-9 item 9 response or other suicide signal starts the direct safety assessment above. Emergency escalation depends on current action/intent/plan/means, not the total PHQ-9 or GAD-7 score alone.

## Role behavior

- **Role = patient**: direct self-screening.
  - *Disclosure* ([`disclosure-behavior.md`](../cancer-buddy/references/disclosure-behavior.md)): disclosure_state=suppressed → continue — screen without cancer-specific framing; suppression never blocks mental-health support.
- **Role = caregiver**: support the caregiver as a person. Offer the original validated screener only with consent; Zarit may be offered separately for caregiving burden.
- **Role = family**: if asking about another person, give support guidance without disclosing patient data. If asking about their own distress, offer the same direct support and optional screens as anyone else.

## Output

Do not write mental-health or suicide content by default. After the immediate situation is stable, explain exactly what would be saved and why, then save only if the person explicitly consents and the archive authorization is verified. If saved, use `patients/<patient_code>/reports/mind/`:
- `phq9-YYYY-MM-DD.md` — score + interpretation
- `gad7-YYYY-MM-DD.md`
- `distress-YYYY-MM-DD.md`
- `safety-plan-YYYY-MM-DD.md` — minimal, user-approved safety plan; avoid verbatim ideation details unless the user requests them.

Filenames (`phq9-` / `gad7-` / `distress-` / `safety-plan-` + ISO date) and numeric scores are locale-independent stable keys. The report body uses the active locale; scale names, item-level scores, and cutoffs stay verbatim.

Never create a temporary patient profile or crisis file merely because a crisis occurred.

## Safety boundaries

- Not a therapist. Every output includes the disclaimer, rendered in `profile.json.locale` — `zh`: `这不能替代心理医生或精神科医生的评估。严重或持续的情绪问题请尽快寻求专业帮助。`; otherwise the same meaning localized ("This is not a substitute for evaluation by a psychologist or psychiatrist. For severe or persistent emotional problems, please seek professional help as soon as possible.").
- No prescribing. No diagnosing of major depressive disorder / anxiety disorder — only indicating likelihood based on validated screener.
- No "anti-depressants aren't needed" statements. Leave medication decisions to psychiatrists.
- Suicide / self-harm signals → the direct safety rule, always. Immediate emergency escalation follows current action/intent/plan/means.

## References

- [phq-9.md](references/phq-9.md) — 9-item depression screener + scoring
- [gad-7.md](references/gad-7.md) — 7-item anxiety screener + scoring
- [distress-thermometer.md](references/distress-thermometer.md) — NCCN 0-10 + problem list
- [c-ssrs-lite.md](references/c-ssrs-lite.md) — C-SSRS usage boundaries: official validated forms only, consent-based, skip logic + action mapping
- [crisis-resources.md](references/crisis-resources.md) — hotlines, emergency guidance
- [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md) — role-specific crisis rules
- [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md) — shared locale layer: host `locale` parameter first, otherwise profile locale / detection fallback → persist `profile.json.locale` → render scaffold in locale, clinical entities verbatim
