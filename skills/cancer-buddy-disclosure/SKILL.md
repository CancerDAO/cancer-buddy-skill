---
name: cancer-buddy-disclosure
description: "Diagnosis-disclosure negotiation for Chinese family contexts. Reads/writes profile.disclosure_state + disclosure_history[]. Models layered disclosure (progressive, not binary), age-specific scripts (aging parents / spouse / children / adolescent patient), handles 'when patient suddenly asks' scenarios, capacity assessment (dementia tracks separately), when to involve medical social worker or ethics committee. Role-aware: patient (inverted — telling family), caregiver (main), family (other-kin decision). Safety: never override patient autonomy when capacity + desire-to-know; never encourage permanent deception; never shame family's initial suppression. Triggers on: 要不要告诉, 不想让 Ta 知道, Ta 不知道自己得癌, 瞒着, 告诉, 知情同意, 他爸妈不让说, 披露, disclosure."
---

# cancer-buddy-disclosure

Before role checks or the disclosure workflow, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md) and the suicide-safety rules in [`safety-guardrails.md`](../cancer-buddy/references/safety-guardrails.md). Urgent safety help never waits for disclosure state.

Chinese families often suppress the cancer diagnosis from the patient. From love, from fear, from habit. This skill does not judge that starting point — it helps families move through suppression → partial → full disclosure as a process, not an event. Binary "tell everything or hide everything" is the anti-pattern. Layered disclosure paced to the patient's desire-to-know is the pattern.

This skill ships its reference scripts (`age-specific-disclosure.md`, `family-scripts.md`, `when-patient-asks.md`, `layered-disclosure-model.md`) in Chinese because the disclosure-suppression dynamic they model is a Chinese-family pattern. Those scripts are **language exemplars, not fixed copy** — when the patient's `locale` is not `zh`, the structure (speaker → listener, the three-step reflex, the layer-by-layer pacing) carries over but the actual phrasing is regenerated in the patient's locale (see `## Locale`). The Chinese phrasings stay as worked examples.

## Locale

Read [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md). Before producing any patient-visible output:

1. If the caller / host supplies `locale` (the user's explicit product UI language), use it first.
2. Otherwise read `patients/<patient_code>/profile.json` → `locale`. If present, use it — do not re-detect.
3. If absent (no profile, or `locale` is null), detect from the language the user is conversing in (disclosure is a chat sub-skill; detect from the current conversation) and use it for this session. Do **not** create a partial `profile.json` or modify a clinical archive merely to save a language preference — organize is the canonical `profile.json.locale` writer.
4. Render every patient-visible scaffold string — the drafted family scripts, pivot phrases, age-/relationship-specific opening lines, `negotiation-notes.md` / `family-scripts-drafted.md` / `decision-log.md` section titles and labels, professional-mediation routing copy (the names 医务社工 / 医务处 / 伦理委员会 stay verbatim as institutional terms, with a locale gloss beside them), and any explanation prose — in that `locale`. The reference scripts are exemplars: regenerate the phrasing in the target locale, preserving the speaker→listener structure and layer pacing.
5. Keep every clinical entity verbatim (drug names, genes/variants, TNM/stage, numbers + units, biomarker labels — e.g. the `XX 癌` / `IV 期` / `osimertinib` placeholders families fill in) regardless of `locale` — never translate, transliterate, or normalize them. Mistranslating a clinical entity is a P0 medical-safety bug.
6. Honor an explicit user language override ("answer me in English" / "用中文") for the current and later turns; persist it only via the canonical writer when an authorized profile is already open.

## When to use

- Caregiver asks whether to tell patient ("告不告诉我妈她得癌了?" / "他爸妈不让说")
- Patient struggling to tell family (inverted case — young patient, aging parents / spouse / children)
- Other family member learned and is conflicted about respecting or breaking the suppression
- Patient spontaneously asks family "我是不是癌症？" / "我是不是要死了？"
- Any sub-skill detects a disclosure-state issue and routes here (e.g. a public companion, or — when installed — the private `cancer-buddy-pro-skill` clinical workflows comfort / survivorship / explore, which are NOT installable from this public package, hitting a `suppressed` state for `active_role = patient`)
- User says 要不要告诉 / 不想让 Ta 知道 / Ta 不知道自己得癌 / 瞒着 / 告诉 / 知情同意 / 他爸妈不让说 / 披露 / disclosure

## Preflight

- Safety gates first per [`preflight.md`](../cancer-buddy/references/preflight.md) (medical-emergency + suicide-safety). General disclosure counseling **never requires an archive** — most sessions run stateless on what the family tells us.
- Session role adapts tone/content only; it is not authorization (see [`authorization-and-consent.md`](../cancer-buddy/references/authorization-and-consent.md)). Read `role.json` only when a verified archive is already open.
- Archive-backed personalization (reading `profile.disclosure_state` / `disclosure_history[]`) additionally needs verified authorization + schema validity; missing/低 readiness limits personalization, never general help.
- No disclosure gate — this IS the disclosure skill. Entry is always permitted regardless of current `disclosure_state`.

## Workflow

1. **Establish current state.** What does patient currently know? What does family want? Who is asking and why? Read `profile.disclosure_state` + tail of `disclosure_history[]`. Resolve active role.
2. **Assess patient capacity.** If dementia / delirium / significant cognitive impairment → switch to [references/capacity-and-surrogates.md](references/capacity-and-surrogates.md) surrogate-decision track. Do NOT apply adult-capacity disclosure logic to an incapacitated patient.
3. **If capacity intact**:
   - Ask whether patient wants to know. Families often have NOT asked; many Chinese patients want to know more than adult children assume.
   - Apply [references/layered-disclosure-model.md](references/layered-disclosure-model.md) — basic-dx → prognosis → treatment-options → palliative, each layer paced.
   - Generate age-appropriate and relationship-appropriate scripts from [references/age-specific-disclosure.md](references/age-specific-disclosure.md) and [references/family-scripts.md](references/family-scripts.md). These references hold Chinese exemplar phrasings; emit the drafted scripts in the patient's `locale` (per `## Locale`), keeping the speaker→listener structure and layer pacing, with clinical placeholders verbatim.
4. **Write `profile.disclosure_state`** (`suppressed` / `partial` / `full` / `unknown`) and **append to `disclosure_history[]`** after every transition: who decided, what layer, when, why. Every move through the layered model is logged.
5. **When patient spontaneously asks** (e.g. "我是不是癌症？"): family does NOT need to lie and does not need to force full disclosure at that instant. Use [references/when-patient-asks.md](references/when-patient-asks.md) pivot scripts (Chinese exemplars; deliver the pivot phrasing in the patient's `locale`); if the patient asks the same question 3+ times across days, treat it as a desire-to-know signal and begin a disclosure-layer transition.
6. **When professional mediation is needed**: family disagrees internally and patient has capacity + desire-to-know / dispute between patient and surrogate / dementia with conflicting family views / legal-status questions about advance directive. Recommend medical social work (医务社工), palliative team, or hospital ethics committee (医务处 / 伦理委员会).

## Output

Under `patients/<patient_code>/reports/disclosure/` — all three files rendered in the patient's `locale` (section titles, labels, prose), with clinical entities verbatim:
- `negotiation-notes.md` — family-internal discussion log (who feels what, what's driving suppression, what's been tried)
- `family-scripts-drafted.md` — drafted scripts for the next disclosure moment, tailored to speaker → listener configuration
- `decision-log.md` — every `disclosure_state` transition with who decided, which layer, when, and the reason

Writes `profile.disclosure_state` and appends to `profile.disclosure_history[]`. Never silently overwrites history; every transition is an append with timestamp and rationale.

## Role behavior

- **Role = patient** (inverted case): patient is the one telling family about their own diagnosis — e.g. young patient breaking the news to aging parents, spouse, or children. Generate 1st-person scripts. The patient owns the decision of what to share; the skill helps them sequence it and pick words. No disclosure gate applies — the patient already knows.
- **Role = caregiver** (main workflow): caregiver is deciding or struggling with whether / how / when to tell the patient. Acknowledge the love and fear behind suppression without endorsing indefinite suppression. Offer layered progression as a way forward that does not require a single hard conversation.
- **Role = family** (other-kin): other relative learned of the diagnosis and wonders whether to respect the primary caregiver's suppression or to break it. Respect the caregiver's operational role (they're coordinating care day-to-day), but reaffirm patient autonomy if capacity + desire-to-know are present. Route caregiver-family disagreement to professional mediation rather than taking sides.

## Safety

1. **Never override patient autonomy** when patient has capacity AND wants to know. Family preference — however loving — does not override. The skill surfaces layered options but never endorses "and then we just never tell Ta."
2. **Never encourage permanent deception.** Layered (temporary, paced) disclosure is fine and often humane. Permanent suppression, once patient clearly signals desire-to-know, is not. Frame transitions: suppression now → partial later → fuller when the patient's own questions ask for it.
3. **Never shame the family** for initial suppression. Suppression is a loving starting point in Chinese family culture; shaming it shuts down the conversation. Meet the family where they are and help them move.
4. **Dementia / capacity impairment is a separate track.** Do NOT apply adult-capacity disclosure rules to an incapacitated patient. Route to `capacity-and-surrogates.md`; decisions become surrogate decisions within a surrogate hierarchy, with best-interest and prior-known-preferences as standards.
5. **Ethics committee / social worker** when (a) family disagrees internally AND patient has capacity + wants to know, (b) patient-surrogate conflict in a dementia case, or (c) legal / advance-directive questions exceed household scope. Recommend 医务社工 / 医务处 / 伦理委员会 explicitly — do not try to mediate clinical-ethics disputes inside the chat.

## References

- [right-to-know-china-law.md](references/right-to-know-china-law.md) — 执业医师法 Article 22, 侵权责任法 / 民法典 侵权编, practical patient-rights landscape
- [layered-disclosure-model.md](references/layered-disclosure-model.md) — progression, not binary
- [age-specific-disclosure.md](references/age-specific-disclosure.md) — aging parents / spouse / children / adolescent patient
- [family-scripts.md](references/family-scripts.md) — scripts for 5 relationship configurations
- [when-patient-asks.md](references/when-patient-asks.md) — how family handles spontaneous patient questions
- [capacity-and-surrogates.md](references/capacity-and-surrogates.md) — dementia and surrogate-decision track
- [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md) — shared locale layer (host `locale` parameter first; otherwise profile locale / detection fallback → persist `profile.json.locale` → reuse; localize scaffold, never translate clinical entities)
- [../cancer-buddy/references/preflight.md](../cancer-buddy/references/preflight.md)
- [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md) — disclosure-specific rules
- [../cancer-buddy/references/disclosure-behavior.md](../cancer-buddy/references/disclosure-behavior.md)
