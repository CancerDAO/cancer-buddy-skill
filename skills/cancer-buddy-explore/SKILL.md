---
name: cancer-buddy-explore
description: "Exhaustively explore diagnostic completion plans and treatment pathway options for a patient. Produces a 4-tier diagnostic menu (¥3K-¥100K+) and an 8-dimension treatment pathway list (standard, targeted on/off-label, immunotherapy combos, trials, frontier therapies, resistance strategies, cross-border). Use when the patient asks 还能做什么检查, 还有什么治疗, 标准治疗用尽, 穷举选项, or wants to plan diagnostic workup."
---

# cancer-buddy-explore

Exhaustively list every useful diagnostic and every treatment pathway the patient could consider.

## When to use

- Patient says: 还能做什么检查 / 还有什么治疗 / 标准治疗用尽 / 穷举选项 / 我的选项有哪些.
- Any time the patient wants a landscape view before narrowing down.

## Inputs

- `patients/<pid>/profile.json` and `readiness.json`.

## Outputs

Written under `patients/<pid>/reports/explore/`:
- `diagnostic-plan.md` — 4-tier menu with cost, timeline, China-specific institutions.
- `pathway-options.md` — 8-dimension treatment pathway list with category labels.
- `information-gaps.md` — prioritized 🔴🟡🟢 gap list.

## Workflow

### Preflight

Apply [../../references/preflight.md](../../references/preflight.md) (readiness-gate: file must exist, grade ≥ C).

### Diagnostic plan

Generate 4 tiers per [references/diagnostics.md](references/diagnostics.md):
- Tier 1 Essential (¥3K–10K): confirm diagnosis + stage
- Tier 2 Recommended (¥10K–30K): + molecular profiling
- Tier 3 Comprehensive (¥30K–100K): + germline/ctDNA/MRD
- Tier 4 Frontier (¥100K+): WGS/single-cell/organoid

Every tier lists Chinese institutions, turnaround, sample-preservation rules.

### Pathway options (see [references/pathway-exploration.md](references/pathway-exploration.md))

8 dimensions:
1. Standard of care audit (any unused guideline options?)
2. Targeted therapy — on-label + off-label (same target, different cancer)
3. Immunotherapy combinations
4. Clinical trials (delegates to `cancer-buddy-trial-match` for depth; in explore just list top candidates)
5. Frontier therapies — neoantigen, CAR-T/TIL, theranostics, drug repurposing
6. Specific-drug name exhaustion for patient's targets
7. Resistance strategies (what comes next)
8. Cross-border options

### Information gaps

Any missing profile field that would change a pathway's applicability becomes a gap item. Prioritize:
- 🔴 must fix (blocks key pathways)
- 🟡 should fix (expands options)
- 🟢 nice to have (optimization)

## Output format

Every suggestion carries:
- Category label: standard-of-care / off-label / investigational / supportive
- Evidence grade A/B/C/D per `references/safety-guardrails.md`
- China-accessibility note (NMPA approved? covered? IIT only?)

No ranking, no "推荐" — only "匹配理由" per option.

## References

- [diagnostics.md](references/diagnostics.md) — 4-tier menu details, institutions, costs
- [pathway-exploration.md](references/pathway-exploration.md) — 8-dimension strategy
- [databases.md](references/databases.md) — 17-category database index for evidence search
- [diagnostic-plan-template.md](references/diagnostic-plan-template.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
