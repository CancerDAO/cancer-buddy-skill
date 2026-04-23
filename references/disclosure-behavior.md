# Disclosure Behavior Matrix

When `patients/<patient_code>/profile.json.disclosure_state = "suppressed"` and the current session role is `patient`, every sub-skill must apply the behavior below. This is the authoritative table; each affected sub-skill's `## Role behavior` section must match.

## Matrix

| Skill | suppressed + patient behavior |
|---|---|
| cancer-buddy (meta) | route (no change) |
| cancer-buddy-organize | normal — patient running organize implies awareness; warn if profile.disclosure_state="suppressed" that entering this workflow will likely break suppression |
| cancer-buddy-explore | refuse + redirect: `医生已经在和你的家人讨论这些选项，我先不在这里展开；你想先和家人聊聊你想了解多少吗？` |
| cancer-buddy-mtb-lite | refuse + redirect (same template as explore) |
| cancer-buddy-trial-match | refuse + redirect |
| cancer-buddy-access | refuse + redirect |
| cancer-buddy-manage | soften — "你最近哪里不舒服？" without cancer-specific framing. Symptom tracking continues but output avoids diagnostic terminology. |
| cancer-buddy-vault | redacted view — diagnosis fields masked, treatment_history entries shown with drug names but no cancer-type label. Patient can export but export is redacted. |
| cancer-buddy-education | refuse patient-version handbook. Offer "一般健康与治疗期生活建议" as non-diagnostic alternative. |
| cancer-buddy-caregiver | N/A — patient never routes here |
| cancer-buddy-mind | continue — depression/anxiety screening works without "because cancer" framing. Use generic phrasing: "你最近心情怎么样" rather than "你癌症相关的焦虑". |
| cancer-buddy-inflection | refuse — inflection framing breaks suppression |
| cancer-buddy-nutrition | normal — nutrition discussed abstractly ("你现在吃 X 药，饮食注意这些"). Drug name OK; cancer-type not surfaced. |
| cancer-buddy-second-opinion | refuse — operator-only skill |
| cancer-buddy-adherence | continue with abstracted language — "按医生说的时间吃 X 药" without "这是靶向药治癌症". Missed-dose decisions still work. |
| cancer-buddy-survivorship | refuse — survivorship premise requires patient knowing treatment ended |
| cancer-buddy-comfort | refuse + strong redirect: `这部分对话需要你先和家人确认是否愿意知道全部情况。我建议你先和家人一起用 disclosure 子技能聊聊。` |
| cancer-buddy-disclosure | main workflow — this is exactly the case it handles |

## Refuse/redirect template

Where the table says "refuse + redirect", use this pattern:

> 这部分内容你的家人/医生可能还没和你详细讨论。我先不在这里展开 — 你想和我聊聊你对自己的身体状况了解到哪一步吗？如果你想知道更多，可以一起看 `cancer-buddy-disclosure` 怎么和家人谈。

Never fail silently. Never leak suppressed diagnosis information.

## When the matrix updates

Any new sub-skill added later MUST declare its suppressed-patient behavior in `## Role behavior` AND update this file. `tests/integration/disclosure-gate.sh` enforces both the declaration and consistency with this file.
