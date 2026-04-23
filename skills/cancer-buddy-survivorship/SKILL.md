---
name: cancer-buddy-survivorship
description: "Long-horizon monitoring post curative-intent treatment or after entering stable maintenance. Builds therapy-specific late-effects watchlist (anthracyclines → LVEF lifetime; chest radiation → secondary breast/thyroid/CV; cisplatin → hearing/renal/neuropathy; pediatric → growth/fertility/cognitive; heme → secondary MDS/AML), personalized surveillance schedule anchored on treatment-end date, secondary-cancer screening cadence, return-to-work and fertility guidance, scanxiety coping, annual visit prep. Role-aware: patient main; caregiver supports; family summary. Triggers on: 治疗结束, 治愈, 缓解, 随访, 生存期, 长期副作用, 晚发效应, 复查间隔, 二原发, 回归生活, 复发恐惧, scanxiety."
---

# cancer-buddy-survivorship

Curing the cancer isn't the end — survivors die of late cardiotoxicity, secondary cancers, cardiovascular disease preventable with surveillance. This skill builds the surveillance plan from what therapies the patient received.

## When to use

- `profile.json.current_therapy` transitions to "maintenance" / "off-treatment" / "surveillance" status.
- `surveillance_schedule_anchor` is set (or user asks to set it).
- User says 治疗结束 / 治愈 / 缓解 / 随访 / 长期副作用 / 晚发效应.
- Any sub-skill detects "in survivorship phase" and routes here.

## Preflight

- Role resolution
- Disclosure gate (suppressed + patient → refuse per disclosure-behavior.md)
- Readiness ≥ C
- Schema validity

## Workflow

1. **Confirm survivorship phase**: read `profile.json.current_therapy` and `treatment_history`. If unclear, ask user whether treatment has ended (definitive/curative intent), is in maintenance, or is stable on ongoing therapy.
2. **Set surveillance anchor**: if `surveillance_schedule_anchor` missing, set to last treatment end date or today.
3. **Build late-effects watchlist** from `treatment_history`: look up each therapy received in [references/therapy-specific-watchlist.md](references/therapy-specific-watchlist.md) and aggregate the per-therapy late-effect concerns.
4. **Generate surveillance calendar** per [references/surveillance-calendar-templates.md](references/surveillance-calendar-templates.md) based on cancer type + stage at treatment + risk factors.
5. **Return-to-life guidance** from [references/return-to-life.md](references/return-to-life.md) — work, exercise, diet, sexual health, fertility (if young patient), smoking/alcohol.
6. **Scanxiety coping** for the pre-scan week — see [references/scanxiety.md](references/scanxiety.md).
7. **New-symptom triage**: if user reports a new symptom during follow-up, do NOT treat as "just ask at next follow-up". Route back to `cancer-buddy-organize` for re-evaluation — new breast lumps in breast survivors, new cough in lung survivors, these can be recurrence or second primary.

## Output

Under `patients/<patient_code>/reports/survivorship/`:
- `surveillance-calendar.md`
- `late-effects-watchlist.md`
- `lifestyle-plan.md`
- `secondary-screening.md`
- `annual-visit-prep.md`

## Role behavior

- **Role = patient**: main user. 1st-person. Surveillance "你的", lifestyle "你可以".
  - *Disclosure*: disclosure_state=suppressed → refuse (survivorship premise requires knowing treatment ended).
- **Role = caregiver**: support role. Reminders for surveillance timing, watching for new symptoms the patient may minimize.
- **Role = family**: summary. "Ta 治好了，但需要定期回医院。别催 Ta 恢复得像以前一样快。"

## Safety

- **New lump / symptom during follow-up** → NOT "just monitor until next scan" → route to `cancer-buddy-organize` for re-evaluation.
- **Scanxiety** → route to `cancer-buddy-mind` if persistent / disabling.
- **Fertility concerns** in young survivors → specialized oncofertility referral; general skill offers info not medical advice.
- **Cardiac late effects** (anthracyclines, chest radiation): annual cardiac assessment is not optional — frame as standard.
- **Cognitive late effects** ("chemo brain"): validate that this is real, not imagined; offer brain-training + patience; if severe → neuropsych referral.

## References

- [therapy-specific-watchlist.md](references/therapy-specific-watchlist.md)
- [surveillance-calendar-templates.md](references/surveillance-calendar-templates.md)
- [return-to-life.md](references/return-to-life.md)
- [scanxiety.md](references/scanxiety.md)
- [../../references/preflight.md](../../references/preflight.md)
- [../../references/disclosure-behavior.md](../../references/disclosure-behavior.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/roles.md](../../references/roles.md)
