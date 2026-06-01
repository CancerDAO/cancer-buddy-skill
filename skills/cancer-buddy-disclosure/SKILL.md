---
name: cancer-buddy-disclosure
description: "Negotiates whether/how/when to tell a Chinese cancer patient their diagnosis, modeling layered (not binary) disclosure. Use when a family is deciding whether to suppress or reveal the diagnosis, a patient is breaking the news to kin, or someone spontaneously asks 我是不是癌症. Triggers on: 要不要告诉, 不想让 Ta 知道, Ta 不知道自己得癌, 瞒着, 知情同意, 他爸妈不让说, 披露, disclosure."
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: disclosure diagnosis-disclosure chinese-family patient-autonomy caregiver palliative
---

# cancer-buddy-disclosure

Chinese families often suppress the cancer diagnosis from the patient. From love, from fear, from habit. This skill does not judge that starting point — it helps families move through suppression → partial → full disclosure as a process, not an event. Binary "tell everything or hide everything" is the anti-pattern. Layered disclosure paced to the patient's desire-to-know is the pattern.

## When to use

- Caregiver asks whether to tell patient ("告不告诉我妈她得癌了?" / "他爸妈不让说")
- Patient struggling to tell family (inverted case — young patient, aging parents / spouse / children)
- Other family member learned and is conflicted about respecting or breaking the suppression
- Patient spontaneously asks family "我是不是癌症？" / "我是不是要死了？"
- Any sub-skill detects disclosure-state issue and routes here (e.g. comfort / survivorship / explore hitting a `suppressed` state for `active_role = patient`)
- User says 要不要告诉 / 不想让 Ta 知道 / Ta 不知道自己得癌 / 瞒着 / 知情同意 / 他爸妈不让说 / 披露 / disclosure

## Preflight

This skill's core use-case is the **early family conversation that precedes organize** — often before any records exist. So the usual readiness/schema gates are relaxed here.

- Role resolution (read `patients/<patient_code>/role.json` if present; otherwise infer role from how the user frames the question).
- **No readiness gate.** A diagnosis name alone (even spoken, with no `profile.json`) is enough to start. If `profile.json` is missing, proceed on what the user tells you and offer to run organize later.
- **No schema-validity gate.** Do NOT block on `validate-profile-schema.sh`. If `profile.json` exists, read `disclosure_state` + `disclosure_history[]` defensively (tolerate missing/partial fields); if it does not exist, skip straight to the conversation and only persist state once a patient directory exists.
- No disclosure gate — this IS the disclosure skill. Entry is always permitted regardless of current `disclosure_state`.

## Workflow

1. **Establish current state.** What does patient currently know? What does family want? Who is asking and why? Read `profile.disclosure_state` + tail of `disclosure_history[]`. Resolve active role.
2. **Assess patient capacity.** If dementia / delirium / significant cognitive impairment → switch to [references/capacity-and-surrogates.md](references/capacity-and-surrogates.md) surrogate-decision track. Do NOT apply adult-capacity disclosure logic to an incapacitated patient.
3. **If capacity intact**:
   - Ask whether patient wants to know. Families often have NOT asked; many Chinese patients want to know more than adult children assume.
   - Apply [references/layered-disclosure-model.md](references/layered-disclosure-model.md) — basic-dx → prognosis → treatment-options → palliative, each layer paced.
   - Generate age-appropriate and relationship-appropriate scripts from [references/age-specific-disclosure.md](references/age-specific-disclosure.md) and [references/family-scripts.md](references/family-scripts.md).
4. **Write `profile.disclosure_state`** (`suppressed` / `partial` / `full` / `null`, per the canonical schema enum) and **append to `disclosure_history[]`** after every transition: who decided, what layer, when, why. Every move through the layered model is logged. (Only persist once a patient directory exists — see Preflight.)
5. **When patient spontaneously asks** (e.g. "我是不是癌症？"): family does NOT need to lie and does not need to force full disclosure at that instant. Use [references/when-patient-asks.md](references/when-patient-asks.md) pivot scripts; if the patient asks the same question 3+ times across days, treat it as a desire-to-know signal and begin a disclosure-layer transition.
6. **When professional mediation is needed**: family disagrees internally and patient has capacity + desire-to-know / dispute between patient and surrogate / dementia with conflicting family views / legal-status questions about advance directive. Recommend medical social work (医务社工), palliative team, or hospital ethics committee (医务处 / 伦理委员会).

## Output

Under `patients/<patient_code>/reports/disclosure/`:
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

- [right-to-know-china-law.md](references/right-to-know-china-law.md) — 《医师法》第二十五条（现行）、旧《执业医师法》第二十六条（已废止）、《民法典》第 1219 条, practical patient-rights landscape
- [layered-disclosure-model.md](references/layered-disclosure-model.md) — progression, not binary
- [age-specific-disclosure.md](references/age-specific-disclosure.md) — aging parents / spouse / children / adolescent patient
- [family-scripts.md](references/family-scripts.md) — scripts for 5 relationship configurations
- [when-patient-asks.md](references/when-patient-asks.md) — how family handles spontaneous patient questions
- [capacity-and-surrogates.md](references/capacity-and-surrogates.md) — dementia and surrogate-decision track
- [../../references/preflight.md](../../references/preflight.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md) — disclosure-specific rules
- [../../references/disclosure-behavior.md](../../references/disclosure-behavior.md)
