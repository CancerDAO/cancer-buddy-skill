---
name: cancer-buddy-access
description: "Navigate the 5 China expanded-access pathways and cross-border treatment options for a specific target drug or clinical trial ID. Produces application materials, sponsor sponsor communication templates, cost estimates, timelines, and legal risk assessment. Covers 临床急需药品临时进口 (博鳌), 拓展性临床试验, 研究者发起的试验 (IIT), 跨境医疗, 超说明书用药. Triggers on 博鳌, 同情用药, 扩展准入, 跨境治疗, 超说明书."
---

# cancer-buddy-access

Map the exact access pathway for each treatment option. What can the patient actually get, how, from where, at what cost, with what risk.

## When to use

- Patient has a specific drug name or trial ID in hand.
- Patient says: 博鳌 / 同情用药 / 扩展准入 / 跨境治疗 / 超说明书 / 临床急需药品.

## Inputs

- Target: drug name OR trial ID (from `cancer-buddy-trial-match` output or user).
- `patients/<pid>/profile.json`.

## Outputs

Written under `patients/<pid>/reports/access/<target>.md`:
- 5-pathway analysis for the target:
  1. 临床急需药品临时进口 (Emergency import — Hainan Boao fast track)
  2. 拓展性临床试验 (Expanded access via sponsor)
  3. 研究者发起的试验 (IIT, ethics-only approval)
  4. 跨境医疗 (US/Japan/Germany/Korea/Singapore)
  5. 超说明书用药 (Off-label with ethics committee approval)
- Per pathway: application materials, sponsor contact template, cost estimate, timeline, legal risk.
- Patient assistance programs (PAP), charity funds, 惠民保 / 特药险 insurance coverage.

## Workflow

See [references/access-pathways.md](references/access-pathways.md) for per-pathway detail. Main steps:

1. Classify the target (approved in China? approved elsewhere? investigational?)
2. For each applicable pathway, fill the template with patient-specific facts.
3. For sponsor templates, generate both English (for multinational trials) and Chinese (for domestic access).
4. Flag legal risk: which pathways require ethics committee approval, which require hospital IRB, which require NMPA filing.
5. Append insurance/charity funding options relevant to patient's city and cancer type.

## Safety

- Never encourage the patient to skip clinician oversight.
- Always include: "所有路径都必须经主诊医院伦理委员会或 IRB 审批后执行。"
- For cross-border, flag FDA/EMA label differences and reimbursement complexity.

## References

- [access-pathways.md](references/access-pathways.md) — China-specific pathway details
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
