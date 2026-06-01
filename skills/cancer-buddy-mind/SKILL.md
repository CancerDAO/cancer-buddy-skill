---
name: cancer-buddy-mind
description: "用经过验证的量表（PHQ-9 抑郁、GAD-7 焦虑、NCCN 苦难温度计、C-SSRS Lite 自杀风险）为肿瘤患者及照护者做心理筛查与分级支持，输出自助 / 就医 / 危机升级三级响应。Use when 患者或照护者出现情绪困扰、需要心理评估、或其他子技能检测到自杀意念需转入临床筛查。危机拦截（crisis INTERCEPTION）由 meta 层的 crisis path 负责；mind 负责跑 C-SSRS Lite 与 PHQ-9 随访，并独占临床筛查与倦怠（clinical-screening burnout）。Triggers on: 睡不着, 焦虑, 抑郁, 崩溃, 没力气, 不想活, 想哭, 心理, mental health, screening, burnout."
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: mental-health screening phq-9 gad-7 crisis caregiver
---

# cancer-buddy-mind

Cancer and mental health are tangled. Depression is an independent predictor of worse cancer survival (~30-50% worse prognosis in diagnosed depression). Caregivers hit depression rates 25-40%. This skill screens both, safely.

## Crisis ownership

**Crisis INTERCEPTION is owned by the meta-layer crisis path** (the shared `safety-guardrails.md` crisis route), not by this skill. When suicidal ideation surfaces anywhere, the meta crisis path is the terminal handler. `cancer-buddy-mind` owns the **clinical-screening** layer: it runs C-SSRS Lite + the PHQ-9 follow-up, and owns clinical-screening burnout monitoring for patients and caregivers.

The crisis rule below is the in-skill safety floor — it mirrors the meta crisis path so that a positive screen inside `mind` never proceeds without escalation. It does not replace the meta path.

## Crisis rule (non-negotiable)

At ANY point in the conversation — including while running a screener or in casual exchange — if the user expresses suicidal ideation, a plan, access to means, or makes statements like "我不想活了" / "活着没意思" / "想结束这一切" / "我想死":

1. **Immediately** stop the current workflow.
2. Respond with the crisis acknowledgment: `我听到你说的了。这个念头出现本身就是一个信号——你现在需要专业的人立刻帮你。`
3. Surface the full contents of [references/crisis-resources.md](references/crisis-resources.md) — not a summary, the full content.
4. Ask: `你现在身边有家人或朋友吗？能先让 Ta 知道你现在的状态吗？`
5. Do NOT ask "what made you feel that way" or any exploratory question. Do not continue the Ta screener. Escalation is the only path.
6. Do NOT offer reassurance like "一切都会好的" — that invalidates.
7. Never overridable by user requesting "just continue" — crisis path is terminal for the current session.

This rule applies regardless of active role (patient / caregiver / family).

## When to use

- User selects mental-health-related intent.
- Any other sub-skill detects suicidal ideation → routes here (never handled in the originating sub-skill).
- Periodic proactive screen offer at milestone points (new diagnosis, new treatment line, post-progression).

## Screeners

Use [references/phq-9.md](references/phq-9.md), [references/gad-7.md](references/gad-7.md), [references/distress-thermometer.md](references/distress-thermometer.md), and [references/c-ssrs-lite.md](references/c-ssrs-lite.md).

Always run C-SSRS Lite first (1 question). If positive → crisis rule. If negative → proceed with PHQ-9 or GAD-7 based on primary complaint.

## Three-tier response

After scoring:

| Severity | PHQ-9 | GAD-7 | Response |
|---|---|---|---|
| Self-help | 0-9 | 0-7 | Offer journaling template, mindfulness 5-min practice, sleep hygiene one-pager. Check in again in 2 weeks. |
| Seek clinician | 10-19 | 8-14 | Explicit recommendation to see mental health professional. List local resources if patient_location_hint in profile.json. |
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

Never write suicidal ideation content without the crisis-YYYY-MM-DD.md companion entry.

## Safety boundaries

- Not a therapist. Every output includes: `这不能替代心理医生或精神科医生的评估。严重或持续的情绪问题请尽快寻求专业帮助。`
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
