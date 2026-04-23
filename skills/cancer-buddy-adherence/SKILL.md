---
name: cancer-buddy-adherence
description: "Oral oncology drug adherence support. Generates daily/weekly schedules, handles missed-dose decisions with drug-specific rules (osimertinib / imatinib / 他莫昔芬 / 华法林 / 甲氨蝶呤 / palbociclib / sunitinib etc.), flags accidental double doses for narrow-therapeutic-index drugs, advises on drug-food timing and pill handling. Role-aware: patient 1st-person daily check-in; caregiver 2nd-person pill-manager workflow; other family refused. Triggers on: 忘记吃药, 漏服, 漏了一次, 服药提醒, 药盒, 出差怎么吃药, 吃药, compliance, 依从性."
---

# cancer-buddy-adherence

6-month oral-drug adherence drops ~30% in oncology. This skill keeps the patient on schedule, and when misses happen, guides the decision on what to do next — because different drugs have different rules.

## When to use

- Patient or caregiver asks about medication timing, missed doses, pill management.
- Starting a new oral regimen (schedule generation).
- Travel / schedule disruption ahead.
- Any other sub-skill detects non-adherence signal and routes here.

## Preflight

Per `../../references/preflight.md`:
- Role resolution
- Disclosure gate (if suppressed + patient: continue with abstracted language per below)
- Readiness ≥ C
- Schema validity (run `scripts/validate-profile-schema.sh`)

## Workflow

1. **Resolve current oral meds** from `profile.json.treatment_history[].regimen` + `current_therapy`. Parse drug names. If unclear, ask user.
2. **Generate schedule** based on drug label dosing (per `references/drug-food-timing.md`). Output `patients/<pid>/reports/adherence/schedule.md` with per-drug timing, with-food/without-food notes, and storage requirements.
3. **Missed-dose handling**: when user reports a miss, consult `references/missed-dose-rules.md` for the specific drug. Output one of: (a) take now, (b) skip and resume next scheduled dose, (c) contact physician before next dose. Log to `patients/<pid>/reports/adherence/missed-dose-events.md`.
4. **Accidental double-dose**: for narrow-therapeutic-index drugs (warfarin, methotrexate, digoxin), immediate MD-contact prompt. Log event.
5. **Extended miss** (e.g. > 3 days TKI): contact physician before resuming — restart may require re-titration.
6. **Monthly trend**: count scheduled vs taken from events log → `patients/<pid>/reports/adherence/monthly-trend.md`. Flag if < 80%.

## Output

Under `patients/<patient_code>/reports/adherence/`:
- `schedule.md`
- `missed-dose-events.md`
- `monthly-trend.md`
- `drug-critical-warnings.md`

## Role behavior

- **Role = patient**: 1st-person daily/weekly check-in. "你今天吃药了吗？" "你下一次是 X 点。"
  - *Disclosure*: disclosure_state=suppressed → continue with abstracted language ("按医生说的时间吃你手里的 X 药"); avoid cancer-specific framing.
- **Role = caregiver**: 2nd-person pill-manager workflow. "你今天提醒 X 吃药了吗？" Pill-box packing, travel kits, storage checks.
- **Role = family**: refuse. Emit: `服药管理最好由一个人统一负责，否则容易重复或漏。这件事建议主照护者或患者本人做。`

## Safety

- **Double dose on narrow-therapeutic-index drugs** (warfarin / methotrexate / digoxin / lithium) → immediate MD contact prompt. Not overridable.
- **Anticoagulant missed dose** → never double up next dose. Single dose + log.
- **TKI missed ≥ 3 consecutive days** → contact MD before resuming; possible dose-titration restart.
- **Extended miss on hormone therapy** (他莫昔芬 / 阿那曲唑 / 来曲唑): single miss is minor; persistent non-adherence over weeks → discuss with oncologist (these are years-long regimens).
- Never interpret non-adherence as patient choice without checking. Could be side effects, cost, logistics, depression (route to `cancer-buddy-mind` if suspected).

## References

- [missed-dose-rules.md](references/missed-dose-rules.md) — per-drug decision trees
- [drug-food-timing.md](references/drug-food-timing.md) — with/without food rules per drug
- [pill-handling-safety.md](references/pill-handling-safety.md) — crush/split rules, storage, disposal
- [../../references/preflight.md](../../references/preflight.md)
- [../../references/disclosure-behavior.md](../../references/disclosure-behavior.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/roles.md](../../references/roles.md)
