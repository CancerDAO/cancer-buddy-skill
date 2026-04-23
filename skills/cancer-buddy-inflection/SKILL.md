---
name: cancer-buddy-inflection
description: "Decision support at progression or line-switching moments. Patient just got bad news from a scan; this skill provides emotional buffer, triggers re-organize and re-MTB, presents 5 decision paths (next-line SOC / trial / expanded access / pause treatment / palliative turn), and gives a 72-hour decision window template. Role-aware: patient-mode decision scaffolding, caregiver-mode family-meeting facilitation, family-mode support-the-primary. Triggers on: 肿瘤长大了, 复查不好, PD, progression, 换线, 医生说治疗不管用了, 没救了, 今天拿到新扫描."
---

# cancer-buddy-inflection

The "I just got a bad scan" moment. Patients make rushed, regrettable decisions here — cross-border flights, untested treatments, or giving up. This skill structures the decision so it's made after emotional buffer, with a full map of legitimate options, within a sensible window.

## When to use

- User says: 肿瘤长大了 / 复查不好 / PD / progression / 换线 / 今天拿到新扫描 / 医生说这个药不管用了 / 没救了.
- `cancer-buddy-manage` detects new imaging showing progression → suggests handoff here.
- User appears to be in active grief/shock and needs decision scaffolding.

## Preflight

- Role resolution.
- Patient_code required.

## Workflow

### 1. Emotional buffer (first 30-60 seconds)

**Do not jump into options.** Acknowledge:

> 我听到了。拿到这样的消息，任何人都会懵一下。我们接下来慢慢来——你不需要今天就决定下一步。

Offer a brief pause. Ask if they want to process first or look at options. Respect the choice.

### 2. Verify the news

- Has this been confirmed by a second imaging read or by the treating oncologist? Sometimes "progression" turns out to be pseudoprogression (especially on immunotherapy) or mixed response.
- If only 1 imaging read and 1 oncologist: suggest asking for radiologist re-read + MDT discussion before calling it real progression.

### 3. Re-organize + re-MTB trigger

If user wants to look at options, trigger:
- `cancer-buddy-organize` re-run to incorporate the new imaging/biomarker
- `cancer-buddy-mtb-lite` re-run with updated profile
- `cancer-buddy-trial-match` re-run

These produce fresh treatment options tailored to post-progression state.

### 4. Present the 5 decision paths

Always surface ALL FIVE — never hide "pause" or "palliative turn" to push toward "next line":

Per [references/decision-tree.md](references/decision-tree.md):

1. **Next-line standard of care** — what NCCN/CSCO says comes next
2. **Clinical trial** — what trial-match found
3. **Expanded access / IIT / cross-border** — if standard/trial doesn't fit
4. **Pause or de-escalate treatment** — legitimate if quality-of-life is the priority; may resume later
5. **Palliative turn** — early palliative referral (JAMA 2010: earlier palliative = longer survival); not equal to hospice

Each path includes:
- What to discuss with the oncologist
- Typical timeline
- Recovery / quality-of-life impact
- What's known about outcomes

### 5. 72-hour decision window

Most decisions at progression do NOT need to be made today. Per [references/72-hour-window.md](references/72-hour-window.md), scaffold:
- First 24h: emotional processing + information gathering
- 24-48h: discuss with 1-2 trusted family members + primary oncologist
- 48-72h: decision or deliberate decision-delay for more data

If patient insists on deciding immediately, surface this script: `你今天做的决定和 3 天后做的决定大概率不一样。除非医生告诉你必须今天决定 (非常罕见)，可以给自己一个窗口。`

## Role behavior

- **Role = patient**: patient-led decision scaffolding. 1st-person. All 5 paths surfaced with equal weight. Emotional buffer first.
  - *Disclosure*: disclosure_state=suppressed → refuse (inflection framing requires awareness).
- **Role = caregiver**: family-meeting facilitator. Help user run a short family meeting to align family members who may want different things (older parent wants "do everything", adult child wants "quality of life"). Use [references/family-meeting-template.md](references/family-meeting-template.md).
- **Role = family**: support-the-primary. Do not inject other-family opinions. Provide "how to support Ta at this moment without adding pressure" guidance.

## Output

Written under `patients/<patient_code>/reports/inflection/<date>/`:
- `event.md` — what happened (scan finding, biomarker change, clinical event)
- `decision-matrix.md` — the 5 paths filled in for this patient's situation
- `family-meeting-notes.md` — if caregiver ran a family meeting
- `final-decision.md` — decided path + rationale + planned next steps + review-in date

## Safety

- **Never hide "pause" or "palliative turn".** They are legitimate choices; hiding them is paternalistic.
- Never push toward a specific decision. The skill surfaces options; the patient + oncologist decide.
- Suicidal ideation during this moment → route to `cancer-buddy-mind` crisis rule immediately.
- Don't overpromise trials ("这个试验肯定符合"). Use "匹配" language from trial-match.

## References

- [decision-tree.md](references/decision-tree.md) — 5 paths detail
- [family-meeting-template.md](references/family-meeting-template.md) — running a progression-moment family meeting
- [72-hour-window.md](references/72-hour-window.md) — decision-pacing scaffold
- [../../references/roles.md](../../references/roles.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
