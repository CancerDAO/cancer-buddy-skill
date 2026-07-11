# Zarit Burden Interview — 照护者负担自评

> **Locale** — this is a validated screening instrument: render the 22 item prompts, the response-anchor labels and the interpretation/trigger scaffold in `profile.json.locale` (see `../../cancer-buddy/references/i18n.md`). The `zh` items below are the source string table; output the localized equivalent for any other locale, but **keep the instrument's standard name verbatim** (`Zarit Burden Interview`) and **keep all numbers/cutoffs verbatim** (`0-4` anchors, item numbers, score bands `0-20 / 21-40 / 41-60 / >60`, hard-trigger thresholds `≥ 3`). For a validated locale, prefer that locale's officially translated Zarit wording over an ad-hoc rendering; numbers and scoring never change.

22 题版。每题按 0-4 评分（0=从来没有, 1=很少, 2=有时, 3=常常, 4=几乎总是）。

## 量表（直接问自己）

1. 你是否觉得家人向你要求的帮助超过他实际的需要？
2. 你是否觉得因为照顾 Ta，自己没有足够时间做自己的事？
3. 你是否觉得在照顾 Ta 和努力顾及家里其他人或工作间有压力？
4. 你是否因 Ta 的行为而感到尴尬？
5. 你是否因在 Ta 身边而生气？
6. 你是否觉得 Ta 影响到你和家人或朋友的关系？
7. 你是否担心 Ta 的未来？
8. 你是否觉得 Ta 依赖你？
9. 你是否因 Ta 在身边而感到紧张？
10. 你是否觉得照顾 Ta 影响到你自己的健康？
11. 你是否觉得因为照顾 Ta，你少了自己的隐私？
12. 你是否觉得因为照顾 Ta，你的社交生活受到影响？
13. 你是否因为 Ta 在家而和朋友来往感到不自在？
14. 你是否觉得 Ta 只能期望你照顾 Ta，好像你是 Ta 唯一能指望的人？
15. 你是否觉得自己没有足够的钱继续照顾 Ta（除了自己花销之外）？
16. 你是否觉得你没办法再继续照顾 Ta 很长时间了？
17. 你是否觉得自从 Ta 生病以来，你失去了对自己生活的控制？
18. 你是否希望能把照顾 Ta 的事交给别人？
19. 你是否觉得不确定该怎么对待 Ta？
20. 你是否觉得应该为 Ta 做更多？
21. 你是否觉得能把 Ta 照顾得更好？
22. 总体来说，你觉得照顾 Ta 的负担有多重？

## 评分解读

总分 = 所有 22 题之和（0-88）。

| 总分 | 负担程度 | 建议 |
|---|---|---|
| 0-20 | 轻度或无负担 | 继续关注自己的状态 |
| 21-40 | 轻-中度负担 | 开始有意识安排休息时间；让家人分担 |
| 41-60 | 中-重度负担 | 需要喘息服务或专业心理支持 |
| > 60 | 重度负担 | **必须**求助——联系心理医生，启动家庭分工或请护工 |

## 硬触发

题 22（总体负担）≥ 3，或题 5 / 9 / 17 / 18 ≥ 3 → 提示 `cancer-buddy-mind` 做抑郁筛查。
题内容涉及自伤想法 → 立即路由 `cancer-buddy-mind` 危机流程，不继续 Zarit 问答。

## 纵向追踪

每月一次或每次治疗线变化时重测。`patients/<patient_code>/reports/caregiver/zarit-YYYY-MM-DD.md` 保存一次。
