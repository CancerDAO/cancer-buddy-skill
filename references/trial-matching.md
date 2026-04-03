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

---

## Rule R6: Investigator Discretion Opportunities

Not all eligibility criteria carry equal weight. Understanding which are absolute walls versus potentially negotiable helps patients and navigators identify trials worth pursuing even when a borderline criterion exists.

### Hard Walls (Non-Negotiable)

These criteria are almost never waived because they represent fundamental scientific or safety requirements:

| Criterion Type | Why It Is a Hard Wall | Example |
|---------------|----------------------|---------|
| **Molecular mismatch** | Trial drug targets a specific alteration the patient lacks; no biological rationale for enrollment | Trial requires EGFR L858R; patient has KRAS G12C |
| **Organ failure beyond safety threshold** | Enrolling would expose patient to unacceptable risk of drug-related death | CrCl <15 mL/min for a renally cleared drug; Child-Pugh C for hepatotoxic agent |
| **Active uncontrolled CNS metastases** (when excluded) | Risk of neurological emergency during trial; confounds endpoint assessment | Symptomatic brain mets requiring escalating steroids |
| **Concurrent second active malignancy** | Confounds efficacy assessment and attribution of adverse events | Active hematologic malignancy alongside solid tumor trial |
| **Pregnancy / inability to use contraception** (when excluded) | Teratogenicity risk | Phase I agent with unknown reproductive toxicity |
| **Prior organ transplant** (for immunotherapy trials) | Risk of graft rejection with immune activation | Solid organ transplant recipient for anti-PD-1 trial |

### Potentially Negotiable (Investigator Discretion Zone)

These criteria may have flexibility depending on the PI, the sponsor, and the specific clinical context:

| Criterion Type | Why It May Be Flexible | How to Approach |
|---------------|----------------------|-----------------|
| **Prior treatment lines** (e.g., "no more than 2 prior lines") | If patient has stable disease, good PS, and exhausted standard options, PI may allow enrollment | Emphasize disease stability, PS, and lack of alternatives in exception request |
| **Borderline lab values** | Values slightly outside range (e.g., ANC 1.4 vs required 1.5) may be accepted if trending in right direction | Provide serial lab trends showing recovery trajectory; offer to recheck before C1D1 |
| **Washout period flexibility** | If prior drug has short half-life and patient has fully recovered from toxicity, strict calendar washout may be negotiable | Document complete toxicity resolution; provide PK rationale for adequate clearance |
| **ECOG performance status** (borderline) | ECOG 2 when trial requires 0-1, but patient is ECOG 2 primarily due to reversible cause (e.g., pain, depression) | Explain the reversible component; offer PI assessment visit to confirm functional status |
| **Prior use of same-class drug** | Some trials exclude prior same-class but may allow if prior exposure was brief, response was seen, or mechanism is sufficiently different | Detail prior exposure duration, best response, and mechanistic differentiation of trial drug |
| **Age limits** | Upper age limits (e.g., <75) are sometimes flexible for fit patients | Provide comprehensive geriatric assessment or functional age evidence |
| **Time since last treatment** | "Must be >4 weeks since last chemo" when patient is at 3 weeks but fully recovered | Document full hematologic and organ function recovery with labs |

### Key Principles for Assessing Negotiability

1. **Safety-driven criteria** are harder to waive than **statistical/scientific design criteria**
2. **Sponsor-mandated criteria** are harder to waive than **PI-discretion criteria** — check if protocol specifies "per investigator judgment"
3. **Early-phase trials** (Phase I/II) tend to have more flexibility than **registration trials** (Phase III pivotal)
4. **Single-center investigator-initiated trials** have more flexibility than **multi-center pharma-sponsored trials**
5. When in doubt, **always ask** — the worst outcome is a "no," and many PIs appreciate well-reasoned exception requests

---

## Exception Request Template

Use this outline when contacting a Principal Investigator (PI) or study coordinator to request an eligibility waiver for a borderline criterion. The request should be concise, clinically grounded, and respectful of the PI's time.

```
═══════════════════════════════════════════════
  临床试验入组例外申请 | TRIAL ELIGIBILITY EXCEPTION REQUEST
═══════════════════════════════════════════════

【试验信息 | TRIAL INFORMATION】
  试验编号 Trial ID:       NCT___ / ChiCTR___
  试验名称 Trial Title:    ___
  研究中心 Site:            ___
  主要研究者 PI:            Dr. ___

【患者摘要 | PATIENT SUMMARY】
  年龄/性别:               ___岁 / 男|女
  诊断:                    ___ (组织学确认)
  分期:                    ___
  ECOG:                    ___
  关键分子特征:             ___
  既往治疗线数:             ___ lines
  当前疾病状态:             ___

【不满足的入组标准 | CRITERION NOT MET】
  标准编号及原文:           [Exact text from protocol, e.g., "Inclusion #5: No more than 2 prior lines of systemic therapy"]
  患者实际情况:             [Patient's actual status, e.g., "Patient has received 3 prior lines"]
  偏差程度:                [How far out of range, e.g., "1 additional line beyond limit"]

【临床论证 | CLINICAL RATIONALE FOR EXCEPTION】
  1. 为什么该标准在本例中可能不影响安全性或疗效评估:
     ___
     [e.g., "Third line was brief (2 cycles) maintenance therapy discontinued for non-progression reasons; 
      patient's current organ function and PS are comparable to a 2-line patient"]

  2. 支持例外的临床数据或先例:
     ___
     [e.g., "Published expansion cohort of similar trial (NCT___) included 3L+ patients with similar response rates"]

  3. 患者获益-风险评估:
     ___
     [e.g., "Patient has exhausted standard options; no approved therapy available for this molecular profile; 
      risk-benefit favors enrollment"]

【补充信息 | SUPPORTING INFORMATION】
  - 近期实验室检查 (附件/摘要): ___
  - 近期影像评估 (日期/结果):   ___
  - 关键病历时间线 (附件):       ___

【请求 | REQUEST】
  恳请研究者评估该患者是否可通过例外审批入组本试验。
  We respectfully request the investigator's assessment of whether this patient
  may be considered for enrollment via protocol exception/waiver.

【联系方式 | CONTACT】
  申请医师/导航员:          ___
  联系方式:                ___
  患者知情同意:             患者已知晓本申请并同意 / Patient is aware and consents

═══════════════════════════════════════════════
```

### Tips for Effective Exception Requests

1. **Be specific**: Quote the exact protocol criterion text — do not paraphrase
2. **Quantify the deviation**: "ANC is 1.4 vs. required 1.5" is better than "ANC is slightly low"
3. **Provide context**: Explain why the deviation is clinically insignificant for THIS patient
4. **Attach supporting data**: Recent labs, imaging, treatment timeline — reduce the PI's effort to review
5. **Acknowledge the ask**: Express that you understand this is a non-standard request and respect the PI's judgment
6. **Follow up appropriately**: Allow 3-5 business days; one follow-up is reasonable; do not pressure
7. **Prepare for "no"**: Have a backup plan ready — the patient should not lose time waiting on a single exception request
