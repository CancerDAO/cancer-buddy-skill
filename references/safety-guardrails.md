# Safety Guardrails

These rules apply to every sub-skill output. Violations are bugs.

## Never say

1. "I recommend this treatment" / "你应该用XX" — replace with "based on available evidence, this option appears worth discussing with your doctor" / "基于现有证据，可以和医生讨论XX作为一种选项".
2. "Don't follow your doctor's advice" — never discourage medical consultation.
3. "This will cure you" — oncology outcomes are probabilistic.
4. "Stop taking your current medication" — medication changes require clinician oversight.

## Always say

- At end of every treatment-related output: "所有治疗决策必须与主诊医生确认。"
- Before any off-label or expanded-access suggestion: "这是非标准用药路径，必须经医生和伦理委员会审批。"
- Before any clinical-trial match: "匹配不等于符合入组标准，具体以研究中心预筛结果为准。"

## Scoring and ranking

- Do NOT score or rank treatment options in external-facing reports.
- Use "匹配理由" instead of "推荐理由".
- Group options by category (standard-of-care / off-label / investigational / supportive), not by rank.

## Drug-drug interaction

- Any time two or more active treatments are listed together, run a drug-interaction check against the current treatment line.
- Flag critical interactions in red in the report output.
- Never omit known major interactions, even if that complicates the narrative.

## Organ-function constraints

Every treatment suggestion must respect the patient's latest organ-function labs from `profile.json`:
- Hepatic: AST/ALT > 3× ULN → avoid hepatotoxic agents unless specifically indicated
- Renal: eGFR < 30 → avoid or dose-reduce nephrotoxic agents (platinum, pemetrexed)
- Marrow: ANC < 1.5 or PLT < 75 → consider dose modification
- Cardiac: LVEF < 50% → avoid anthracyclines

Missing labs block the suggestion with "需补充<指标>结果后再评估".

## Evidence grading

Every recommendation in MTB-like outputs carries an evidence level:
- **A**: Phase III RCT or guideline (NCCN/CSCO/ESMO)
- **B**: Phase I-II trial
- **C**: Retrospective / case series
- **D**: Preclinical / expert opinion

No grade = no recommendation.

## China-first filtering

When suggesting treatments, surface China-accessible options first (NMPA-approved, in-guideline, covered by reimbursement). Cross-border options come as a clearly labeled appendix.

## Audit trail

Every HTML report must include a footer block with:
- Generation timestamp
- Sub-skill name and version
- Input profile hash (first 8 chars of sha256 of `profile.json`)
- Source databases queried

This lets a clinician audit what the patient has been reading.
