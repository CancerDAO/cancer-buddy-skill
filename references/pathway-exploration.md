# Treatment Pathway Exploration Protocol

Phase 4. Exhaustively explore ALL treatment options using 8-dimension strategy.

## 8-Dimension Search Strategy

For each patient, systematically search along ALL 8 dimensions. Do not skip any.

### Dimension 1: Standard Care Audit

Before exploring beyond standard care, verify nothing was missed:

1. Identify cancer type + stage + molecular profile
2. Check NCCN, ESMO, CSCO guidelines for ALL recommended options
3. Cross-check against patient's treatment history
4. Flag any guideline-recommended option NOT yet tried
5. Common misses: combination regimens, maintenance therapy, rechallenge after washout

### Dimension 2: Targeted Therapy (On-label + Off-label)

Based on patient's molecular profile:

1. **On-label**: Approved targeted drugs for this cancer type + mutation
   - Query OncoKB for evidence Level 1/2 actionable alterations
   - Check NMPA approval status for China availability
2. **Off-label (same target, different cancer)**: Basket/umbrella trial logic
   - Same mutation approved in another cancer type → potential off-label use
   - Example: NTRK inhibitors approved pan-tumor, but check specific evidence
   - Query cBioPortal for mutation frequency in patient's cancer type
3. **Emerging targets**: Mutations with preclinical evidence but no approval yet
   - Query COSMIC + PubMed for recent publications

### Dimension 3: Immunotherapy Combinations

1. Single-agent checkpoint inhibitors (if not tried)
2. Dual checkpoint (anti-PD-1 + anti-CTLA-4)
3. Checkpoint + targeted therapy combinations
4. Checkpoint + chemotherapy combinations
5. Checkpoint + anti-angiogenic combinations
6. Check: MSI-H/dMMR status (pan-tumor approval), TMB-H, PD-L1 expression
7. If immunotherapy previously failed: check for combination strategies that may overcome resistance

### Dimension 4: Clinical Trial Matching

Follow TrialGPT protocol in [trial-matching.md](trial-matching.md):

1. Generate 8-dimension keyword search plan
2. Dual-source search (ClinicalTrials.gov + ChiCTR)
3. Hard-filter by treatment line + molecular profile
4. Criterion-level assessment per trial
5. Validate trial IDs against official API

### Dimension 5: Frontier Therapies

Search for cutting-edge options Sid-style:

| Category | What to Search | Databases |
|----------|---------------|-----------|
| Neoantigen vaccines | mRNA personalized vaccine trials, peptide vaccines | PubMed, ClinicalTrials.gov |
| Cell therapy | CAR-T, TCR-T, TIL, NK cell therapy | CAR-T Database, China CAR-T Registry |
| Theranostics | Radioligand therapy (Lu-177, Ac-225), FAP-targeting | PubMed, nuclear medicine centers |
| Oncolytic virus | OVs in clinical trials for patient's cancer type | OV-DB, ClinicalTrials.gov |
| ADC drugs | Antibody-drug conjugates with matching target | ADC Review, clinical trials |
| Bispecific antibodies | T-cell engaging bispecifics | PubMed, clinical trials |

For each: evidence level, availability (China/international), access pathway, estimated cost.

### Dimension 6: Specific Drug Name Exhaustion

For each actionable target in patient's profile, enumerate ALL known drugs:

1. Identify the target (e.g., KRAS G12C)
2. List every drug in development or approved for that target:
   - Approved: [list all by generic name]
   - Phase III: [list]
   - Phase II: [list]
   - Phase I: [list]
3. For each drug, search: `"{drug name}" AND "{cancer type}" clinical trial`
4. Include combination searches: `"{drug A}" AND "{drug B}" AND "{cancer type}"`

This dimension catches trials that disease-keyword searches miss because the trial description uses drug names, not disease terms.

### Dimension 7: Resistance Strategies

Based on patient's current/recent treatment, search for what comes next:

1. Identify the mechanism of current treatment
2. Search for known resistance mechanisms to that treatment
3. Search for drugs/trials targeting those resistance mechanisms
4. Keywords: `"{current drug} resistance"`, `"{target} resistance mechanism"`, `"{cancer type} after {current drug} progression"`
5. Example: Patient on KRAS G12C inhibitor → search for RAS-ON inhibitors, SHP2 inhibitors, combination strategies to overcome adaptive resistance

### Dimension 8: Cross-border Options

When domestic options are exhausted or specific treatments are only available abroad:

| Region | Strengths | Key Search |
|--------|-----------|-----------|
| US | Most clinical trials, compassionate use programs | ClinicalTrials.gov US sites |
| Japan | Proton/heavy ion therapy, cell therapy | JapicCTI, PMDA approvals |
| Germany | Radioligand therapy (Lu-177), experimental nuclear medicine | DRKS, university hospitals |
| Korea | Proton therapy, cost-effective oncology | Korean cancer centers |
| Singapore | Asia hub, multilingual, early access programs | CTRIS Singapore |
| Israel | Innovative immunotherapy approaches | Israeli clinical trials |

For each: refer to [access-pathways.md](access-pathways.md) for logistics.

### Dimension 0.5: Re-Baseline at Progression

> **Prior genomics become unreliable after progression — tumor may have evolved.**

Before escalating treatment at progression, mandatory re-testing is required. Decision tree:

```
Progression on targeted therapy
  └── Liquid biopsy (ctDNA) first
        ├── New actionable mutation found → Pivot treatment to match new target
        └── No new mutation found
              └── Tissue re-biopsy if feasible
                    ├── New findings → Adjust treatment
                    └── Tissue unavailable → Proceed with empiric next line
```

#### Resistance Mechanism Matrix

When progression occurs on a targeted therapy, check for these known resistance mechanisms:

| Prior Therapy Target | Resistance Mechanisms to Check |
|---|---|
| **EGFR TKI (1st/2nd gen)** | T790M (most common), MET amplification, HER2 amplification, small-cell transformation, PIK3CA mutation |
| **EGFR TKI (3rd gen, e.g., osimertinib)** | C797S mutation, MET amplification, HER2 amplification, RAS-MAPK activation, histologic transformation |
| **KRAS G12C inhibitor** | RAS-ON state reactivation, SHP2 pathway activation, MAPK reactivation, acquired KRAS mutations, RTK amplification |
| **ALK TKI** | ALK resistance mutations (G1202R, L1196M, I1171T/N/S, F1174L, others — varies by generation), MET amplification, EGFR activation, TP53 co-mutation |

**Rule:** At every progression event, re-run at minimum ctDNA panel. If switching treatment line, strongly recommend full re-baseline (panel + ctDNA + relevant IHC). Do not assume the original molecular profile still holds.

---

## Synthesis: Treatment Pathway Map

After searching all 8 dimensions, synthesize into a pathway map:

```
🟢 High Feasibility (strong evidence + accessible + affordable)
├── [Option 1]: [evidence] | [access] | ¥[cost] | Next: [action]
├── [Option 2]: ...
└── ...

🟡 Medium Feasibility (worth pursuing with effort)
├── [Trial NCTXXX]: [match level] | [center] | Next: [action]
├── [Off-label drug]: [evidence] | [access path] | Next: [action]
└── ...

🔴 Exploratory (frontier, requires significant effort/cost)
├── [Frontier therapy]: [evidence] | [access] | Next: [action]
└── ...
```

**Parallel pursuit rule**: Identify which paths can be pursued simultaneously. Sid's core insight — don't wait for one to fail before trying the next.

## Output Checklist

Before delivering the pathway map, verify:

- [ ] All 8 dimensions searched (none skipped)
- [ ] Every option has evidence level (A/B/C/D)
- [ ] Every option has access pathway identified
- [ ] Every option has cost estimate
- [ ] Drug interactions checked across proposed parallel options
- [ ] No use of "推荐" — only "匹配" and "可选方案"
- [ ] Trial IDs validated against official APIs
- [ ] Concrete next-step action for each option
- [ ] Parallel pursuit recommendations included

## Tool Availability & Fallbacks

| Primary Tool | Fallback if Unavailable |
|-------------|------------------------|
| MCP medical-database tools | WebSearch with structured queries |
| chictr-mcp-server | WebSearch `site:chictr.org.cn` + manual extraction |
| ClinicalTrials.gov API | WebFetch `https://clinicaltrials.gov/api/v2/studies?query.cond=...` |
| OncoKB API | WebSearch `site:oncokb.org {gene} {mutation}` |
| pdftotext / PyPDF2 | Read tool for PDF, manual extraction for images |

Always attempt primary tool first. If unavailable, use fallback without stopping the workflow.
