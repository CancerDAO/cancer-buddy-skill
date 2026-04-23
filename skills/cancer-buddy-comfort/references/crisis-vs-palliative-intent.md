# Crisis vs Informed Palliative Intent — A Decision Tree

When someone says "我不想治了" / "I don't want to keep fighting" / "让我安静地走吧" — there are two very different things that might be happening:

1. **Acute depressive / suicidal crisis** — the person is experiencing a treatable mental health state that is distorting their decision-making. Under this state, they may endorse "want to die" statements that, once the depression is treated or the pain is controlled, they no longer endorse.
2. **Informed palliative preference** — a sustained, reflective, value-coherent preference for comfort-focused care over life-prolonging treatment, in a person with clear thinking and adequate support.

Treating (1) as (2) is a catastrophic error — it colludes with the depression to lethal effect. Treating (2) as (1) is also an error — it infantilizes a competent adult making a considered choice. The stakes of misclassification are high in both directions.

This reference is the decision tree for navigating that distinction. It is operationalized in the `cancer-buddy-comfort` SKILL.md "想不治了" rule: **always** route to `cancer-buddy-mind` for C-SSRS Lite first; only if C-SSRS is negative AND other markers support informed palliative preference may comfort continue.

## The decision tree

```
User says "不想治了" / "活着没意思" / "想结束" / similar
    │
    ├── STEP 1: Route to cancer-buddy-mind for C-SSRS Lite
    │       (no exceptions; never "just continue")
    │
    ├── C-SSRS POSITIVE (any ideation, plan, intent)
    │       │
    │       └── → Full crisis protocol (cancer-buddy-mind)
    │             Do not continue comfort workflow.
    │             Surface hotlines, safety plan, urgent help.
    │
    └── C-SSRS NEGATIVE
            │
            ├── STEP 2: Assess "informed palliative preference" markers (below)
            │
            ├── Markers support informed preference
            │       │
            │       └── → Continue comfort workflow, palliative options
            │             Without advocating. Loop back to crisis
            │             check if ideation emerges later.
            │
            └── Markers do not support informed preference
                    │
                    └── → Pause comfort workflow.
                          Route to cancer-buddy-mind for PHQ-9 / further assessment.
                          Address reversible drivers (see below).
                          Reassess later.
```

## Informed palliative preference — markers

A person is more likely to be expressing informed palliative preference (not acute crisis) when:

- **Sustained across time** — the preference has been present for days/weeks, not hours, and is re-endorsed after rest, food, pain control.
- **Value-coherent** — fits with the person's broader values and prior stated preferences (if the person has long said "I don't want to die in an ICU," a turn toward comfort-focused care is consistent).
- **Family / support aware** — the person has shared this with trusted family; not a secret-kept preference.
- **Cognitively clear** — person is oriented, able to articulate reasoning, weighs trade-offs, not in delirium or confusion.
- **Not in active untreated depression** — no untreated major depressive episode, hopelessness is about the medical situation (which may be objectively severe) rather than global self-worthlessness.
- **Pain and symptom burden addressed** — uncontrolled pain, dyspnea, nausea, or delirium can generate death-wish talk that resolves when symptoms are controlled. If symptoms are uncontrolled, aggressive symptom management often changes the conversation dramatically.
- **Not in acute relational crisis** — not responding to a recent fight, recent loss of insurance / housing / caregiver, recent perceived abandonment by care team.

## Depression / suicidal crisis — markers

A person is more likely in acute depressive / suicidal crisis when:

- **Recent-onset mood shift** — mood decline over days to weeks rather than a long trajectory.
- **Sleep / appetite disruption** beyond what the cancer itself explains.
- **Hopelessness / worthlessness** that is global ("I'm a burden, the world is better without me"), not medical-situation-specific.
- **Anhedonia** — loss of pleasure in previously enjoyed things beyond what physical capacity explains.
- **Withdrawal** — pulling away from family, refusing visitors, isolation.
- **Recent loss / change** — death of a close person, loss of functional capacity, change in living situation.
- **Perceived burden** to family / financial / caregiving — cognitive distortion specific to depression.
- **History** of depression or prior suicidal ideation / attempt.
- **Uncontrolled pain** — pain itself drives hopelessness and death-wish thinking in a way that is often dramatically reversible with adequate symptom control. This is a critical specific lever.
- **Substance use escalation** — alcohol, sedatives, new or increased use.
- **Ambivalence / mixed feelings** — the person simultaneously expresses wanting to die and wanting someone to stop them; often a crisis sign.

## The pain exception — extremely important

Inadequately controlled pain is one of the most common drivers of "I want to die" talk in cancer patients, AND one of the most reversible. Clinicians and family have seen this pattern many times:

1. Patient with uncontrolled pain says "let me go."
2. Pain regimen is appropriately titrated.
3. Within days, the same patient no longer endorses the death wish and may not even remember saying it.

This does NOT mean we dismiss "let me go" as "just pain." It means we take the pain seriously, address it aggressively, AND reassess the palliative-intent question from a baseline of controlled symptoms. The two are not in tension — they compound.

**Operational rule:** in a patient with significantly uncontrolled pain OR dyspnea OR delirium, do NOT definitively classify any statement about wanting to die until symptoms are adequately addressed. Treat symptoms, then re-ask.

## Conversation prompts for distinguishing

If continuing comfort workflow (C-SSRS negative, preliminary markers), these prompts help surface the real nature of the preference:

- "你能多告诉我一点这个想法 — 是这几天才有的, 还是想了很久?"
- "如果现在疼痛能被充分控制, 你对继续治疗还是停止治疗的想法会不一样吗?"
- "你心里这个想法，家里人知道吗? 他们怎么看?"
- "你是更希望'不要再受这些治疗的苦'，还是'活下去没意义'? 这两种感觉对你来说一样吗?"
- "有没有什么事情是你还想做的? 或者还想见的人?"
- "如果可以有一段生活质量还不错的时间, 哪怕不长, 你会想要那段时间吗?"

Answers that lean toward "治疗太苦" + pain / burden driven + oriented toward making most of remaining time → more likely informed preference.

Answers that lean toward "活着本身没意义" + global hopelessness + denying any remaining wants → more likely depression.

These are not binary. Ambiguity is common. When unclear: treat reversible drivers, route for mental health assessment, re-ask later. Patience is not the enemy of palliative care; rushing is.

## What this skill does with the answer

- **C-SSRS positive** → hand off entirely to `cancer-buddy-mind`. Full crisis protocol.
- **C-SSRS negative, markers support informed preference, symptoms controlled** → continue comfort workflow. Surface palliative options without advocating. Continue to monitor for any emerging ideation.
- **C-SSRS negative, markers mixed or uncontrolled symptoms** → pause comfort workflow for advocacy. Aggressive symptom management. PHQ-9 / GAD-7 via `cancer-buddy-mind`. Reassess in days.
- **Ongoing monitoring** → even in confirmed informed-preference cases, new suicidal ideation at any later point interrupts all workflows and returns to crisis protocol. (Safety rule 10.)

## Key citations

- Breitbart W, et al. "Depression, hopelessness, and desire for hastened death in terminally ill patients with cancer." *JAMA* 2000;284:2907-11 — classic finding that hopelessness and depression drive death wish more than physical symptoms in isolation; but physical symptoms powerfully amplify.
- Chochinov HM et al. work on dignity therapy and "will to live" in advanced cancer.
- WHO and national suicide prevention frameworks: C-SSRS as a validated brief screener.
- National 24-hour hotlines: 24-小时全国心理援助 400-161-9995; 希望 24 热线 400-161-9995; 北京心理危机研究与干预中心 010-82951332; 上海市心理援助热线 021-64383562 (listed for completeness; full list in `cancer-buddy-mind/references/crisis-resources.md`).

---

*本工具不替代心理医生、精神科医生或缓和医疗科医生。条件允许请尽早接触缓和医疗团队 — 早期接入已被证明延长生存并改善生活质量 (Temel et al., NEJM 2010)。出现自杀意念、计划或冲动时请立即联系专业机构。*
