# TrialGPT Dual-Source Clinical Trial Matching Protocol

Match patients to clinical trials using ClinicalTrials.gov + ChiCTR with structured assessment and compliance-safe output.

---

## Search Plan JSON Structure

Generate a search plan with 8 keyword dimensions before querying:

```json
{
  "patient_id": "___",
  "search_plan": {
    "1_disease_specific": ["exact cancer type + histology + stage", "e.g. advanced cholangiocarcinoma intrahepatic"],
    "2_broad_tumor": ["solid tumor", "pan-cancer", "hepatobiliary", "biliary tract cancer"],
    "3_specific_drugs": ["EXHAUSTIVE list of ALL known drugs for patient's targets — e.g. pemigatinib, futibatinib, infigratinib, erdafitinib, derazantinib for FGFR2"],
    "4_combination_targets": ["target + checkpoint inhibitor", "target + chemo", "target + anti-angiogenic"],
    "5_pathway_targeting": ["downstream pathway", "resistance pathway", "e.g. FGFR + PI3K", "FGFR + mTOR"],
    "6_cell_therapy": ["CAR-T solid tumor", "TIL therapy", "NK cell therapy", "TCR-T — NO mutation restriction for this dimension"],
    "7_chinese_keywords": ["中文癌种名 + 靶点", "e.g. 胆管癌 FGFR2融合 临床试验", "for ChiCTR search"],
    "8_resistance_strategies": ["post-[drug] resistance", "acquired resistance [target]", "next-line after [prior treatment]"]
  }
}
```

Construct queries from ALL 8 dimensions. Do not skip any dimension.

---

## Dual-Source Search

### Source 1: ClinicalTrials.gov API

Query the ClinicalTrials.gov API with each keyword dimension:
```
GET https://clinicaltrials.gov/api/v2/studies?query.cond={condition}&query.intr={intervention}&filter.overallStatus=RECRUITING&countTotal=true
```

Filter: `RECRUITING` or `NOT_YET_RECRUITING`. Prioritize trials with China sites.

### Source 2: ChiCTR MCP Server

Use chictr-mcp-server for Chinese Clinical Trial Registry:

```bash
# Setup (if not already configured)
# Add to MCP config:
{
  "chictr-mcp-server": {
    "command": "npx",
    "args": ["-y", "chictr-mcp-server"]
  }
}
```

Search with Chinese keywords (dimension 7). Also search English terms as ChiCTR contains bilingual entries.

---

## Hard Filtering Rules

Apply BEFORE criterion-level assessment. Exclude trials that fail these:

1. **First-line-only exclusion**: If patient has received >=2 lines, exclude trials requiring treatment-naive/first-line only
2. **Molecular mismatch exclusion**: If trial requires specific mutation (e.g., EGFR L858R) and patient lacks it, exclude
3. **ECOG exclusion**: If trial requires ECOG 0-1 and patient is ECOG >=3, exclude
4. **Organ function hard cutoff**: If trial specifies CrCl >60 and patient has CrCl <30, exclude

---

## Criterion-Level Assessment

For each candidate trial that passes hard filtering, assess EVERY key eligibility criterion:

```
| 序号 | 入排标准 | 判定 | 依据 |
|------|----------|------|------|
| I-1  | 组织学确认的___癌 | ✅符合 | 病理报告确认___ |
| I-2  | ___突变阳性 | ✅符合 | NGS报告: ___突变, VAF ___% |
| E-1  | 既往未使用过___类药物 | ❌不符合 | 患者___线使用过___ |
| I-3  | ECOG 0-2 | ⚠️边界 | 当前ECOG 2, 但近期体力下降 |
| I-4  | 可测量病灶(RECIST) | ❓缺失 | 未提供近期影像报告 |
```

Judgment codes:
- ✅符合 — criterion clearly met
- ❌不符合 — criterion clearly not met
- ⚠️边界 — borderline, may need investigator judgment
- ❓缺失 — insufficient data to assess

---

## Matching Grade Rules (R1-R5 Downgrade)

Start at "高度匹配". Apply rules to downgrade to "条件匹配":

| Rule | Trigger | Downgrade |
|------|---------|-----------|
| **R1** | Trial excludes prior same-class drug AND patient has used it | 高度匹配 → 条件匹配 |
| **R2** | Trial's line-of-therapy limit < patient's actual line count | 高度匹配 → 条件匹配 |
| **R3** | Trial's primary expansion cohort does NOT include patient's tumor type (but has basket/all-comers arm) | 高度匹配 → 条件匹配 |
| **R4** | Patient's organ function is borderline for trial requirements | 高度匹配 → 条件匹配 |
| **R5** | >=2 critical inclusion criteria have ❓缺失 (missing info) | 高度匹配 → 条件匹配 |

If ANY criterion is ❌不符合, the trial is excluded (not downgraded).

Final grades:
- **高度匹配**: All criteria ✅, no R-rule triggered
- **条件匹配**: All criteria ✅ or ⚠️, but 1+ R-rule triggered — enrollment possible with investigator discretion or additional testing

---

## Validation Step

**MANDATORY**: Before including any trial in the report, verify it exists and is currently recruiting:

- **NCT trials**: Query ClinicalTrials.gov API with exact NCT ID → confirm status = RECRUITING
- **ChiCTR trials**: Query ChiCTR with exact registration number → confirm status

Remove any trial that cannot be verified. Never fabricate or hallucinate trial IDs.

---

## HTML Report Structure

Output 8 sections in HTML:

### Section 1: 患者概况
Patient profile summary (cancer type, stage, molecular features, treatment lines, ECOG, key organ function).

### Section 2: 治疗时间线
Visual timeline of all treatment lines with responses and progression events.

### Section 3: 匹配结论概要
Summary table: number of trials searched, number passing hard filter, number 高度匹配, number 条件匹配.

### Section 4: 候选临床试验 — 高度匹配
Card per trial: NCT/ChiCTR ID (linked), phase, title, mechanism, PI/institution, key inclusion met, enrollment contact.

### Section 5: 候选临床试验 — 条件匹配
Same card format. Add: which R-rule(s) triggered, what action resolves it (e.g., "confirm organ function with recent labs").

### Section 6: 入排标准逐条评估卡
One assessment card per candidate trial (from Section 4+5). Full criterion table with ✅❌⚠️❓ and evidence column.

### Section 7: 已排除方向
Directions searched but yielded no viable trials. Brief reason per direction. Important so patient knows these were explored.

### Section 8: 临床中心联系方式 + 信息缺口 + 行动项
- Contact info for each trial's recruiting site (PI name, hospital, phone/email if available)
- Information gaps that would improve matching (prioritized 🔴🟡🟢)
- Concrete action items: tests to get, doctors to contact, applications to submit

---

## Compliance Rules

1. **No scoring in external reports** — do not assign numerical scores to trials or patients
2. **No "推荐" terminology** — use "匹配" (match), "匹配理由" (matching rationale), never "推荐" (recommend)
3. **Provide researcher contact info** — always include PI/site contact so patient can reach trial team directly
4. **Disclaimer** — every report must include: "本报告为信息整理, 不构成医疗建议. 入组需经研究者评估确认."
5. **No guarantee language** — never state patient "will qualify" or "should enroll"; use "based on available information, this trial appears potentially matchable"
