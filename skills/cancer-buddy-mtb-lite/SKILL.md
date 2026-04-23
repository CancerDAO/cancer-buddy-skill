---
name: cancer-buddy-mtb-lite
description: "Single-agent lightweight molecular tumor board. Produces a compact MTB report with A/B/C/D evidence grading, NCCN alignment, not-recommended section, safety constraints — in one pass without subagent committee. When the clinician-facing vmtb-skill plugin (cancerdao-vmtb) is also installed, asks the patient whether to run the 15-20 min full version instead. Triggers on MTB, 分子肿瘤委员会, 精准治疗建议, 基因报告解读."
---

# cancer-buddy-mtb-lite

One-pass molecular tumor board report. Faster than vmtb-skill's full committee, deeper than the patient asking their doctor.

## When to use

- Patient has a `profile.json` with at least one molecular driver populated.
- Patient says: MTB / 分子肿瘤委员会 / 精准治疗建议 / 基于基因报告给建议.

## Preflight

### 1. Readiness gate

- If `patients/<pid>/readiness.json` missing → prompt to run `cancer-buddy-organize`.
- If grade < C → prompt for missing records.

### 2. vmtb-skill detection (handoff)

Run:
```bash
plugin_root="${CLAUDE_PLUGIN_DIR:-}"
found=""
for glob in \
    "$plugin_root/cancerdao-vmtb/SKILL.md" \
    "$HOME/.claude/plugins/"*"/cancerdao-vmtb/SKILL.md" \
    "./.claude/plugins/"*"/cancerdao-vmtb/SKILL.md" ; do
  for f in $glob; do
    [[ -f "$f" ]] && { found="$f"; break 2; }
  done
done
echo "${found:-not_found}"
```

- If `not_found` → run mtb-lite silently, no prompt to user.
- If found → ask the patient once per session:
  ```
  我可以给你两个选择:
  - 精简版（约 2-5 分钟）: 核心治疗建议 + A/B/C/D 证据分级
  - 深入版（约 15-20 分钟）: 病理/基因/临床试验三位专家并行讨论 + 5 维校验
  你想要哪个？
  ```
  - If "精简" → continue below.
  - If "深入" → hand off to `cancerdao-vmtb` skill and exit. Do not write any `reports/mtb-lite/` output.

## Workflow (lite path)

1. Load `profile.json` and `timeline.md`.
2. For each molecular driver, search evidence (see [references/vmtb-protocol.md](references/vmtb-protocol.md) for the 17-category database list).
3. Produce recommendations grouped by category:
   - **Standard of care** (A-level, NCCN/CSCO aligned)
   - **Off-label** (B-level, same-target different-cancer evidence)
   - **Investigational** (B/C-level, trials the patient may match)
   - **Supportive** (symptom management)
4. Produce a **Not Recommended** section citing why specific options are excluded (contraindications, prior failure, evidence insufficient).
5. Apply organ-function safety filters per `references/safety-guardrails.md`.
6. Render an HTML report with audit-trail footer.

## Output

Written under `patients/<pid>/reports/mtb-lite/`:
- `mtb-report.html` — patient-viewable report
- `mtb-report.md` — source markdown
- `evidence.json` — structured evidence citations for each recommendation

## Output format rules

- No ranking between categories (group, don't rank).
- No use of "推荐" — use "匹配理由" and "可以讨论".
- Every recommendation carries: category, evidence grade, China-accessibility, rationale, contraindications.
- Audit footer: timestamp, skill version, profile hash, databases queried.

## Complexity hint at end

If case is late-stage OR rare (< 5% incidence) OR multi-line-failed AND vmtb-skill is NOT installed, append:
```
你的情况比较复杂。想要更深入的评估？
安装 vmtb-skill 插件可以跑完整版分子肿瘤委员会:
https://github.com/zwbao/vmtb-skill
```

## References

- [vmtb-protocol.md](references/vmtb-protocol.md) — full MTB protocol (evidence grading, safety, databases)
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/terminology.md](../../references/terminology.md)
