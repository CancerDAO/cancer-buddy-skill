# vMTB Consultation Protocol

Full protocol for Virtual Molecular Tumor Board consultations. Produce clinically actionable, auditable HTML reports.

---

## Input Specification

Accept one or multiple documents:
- PDF files (病理报告, NGS报告, 影像报告, 检验报告)
- Word documents (.docx, .doc)
- Plain text, markdown
- Images/screenshots of reports

### Document Extraction

```bash
# PDF — primary method
pdftotext /path/to/file.pdf - 2>/dev/null

# PDF — fallback
python3 -c "
import PyPDF2
with open('/path/to/file.pdf', 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    for i, page in enumerate(reader.pages):
        print(f'=== Page {i+1} ===')
        print(page.extract_text())
"

# Word
python3 -c "
from docx import Document
doc = Document('/path/to/file.docx')
for para in doc.paragraphs:
    print(para.text)
"
```

Never assume a file cannot be read. Try alternative methods if first extraction fails.

---

## Critical Rule

Do NOT assume cancer type, biomarkers, or target genes from previous cases. Treat any prior case as example only. Extract all information fresh from uploaded documents.

---

## Case-First Extraction (Step 0)

Before any recommendation, reconstruct and present:

1. **Cancer type & histology** (or "uncertain" with reason)
2. **Stage & metastatic sites**
3. **Treatment lines**: regimens, dates, best response (CR/PR/SD/PD), key toxicities
4. **Current status**: ongoing therapy vs progressed
5. **Molecular profile**: actionable drivers + co-alterations (gene, variant, VAF)
6. **Immune biomarkers**: MSI/MMR, TMB, PD-L1 (TPS/CPS), EBV, POLE/POLD1, HLA loss — as applicable
7. **Organ function constraints**: renal (CrCl/eGFR), hepatic (Child-Pugh/bilirubin), bone marrow (ANC/PLT), cardiac (LVEF) + ECOG PS

Flag missing or contradictory data explicitly. Derive top 3-6 "decision drivers" (e.g., targetable driver, resistance mechanism, immunotherapy eligibility, organ limit).

---

## Evidence Grading System

Every recommendation must carry TWO labels:

### Evidence Level
| Level | Definition |
|-------|-----------|
| **A** | Phase III RCT or guideline-endorsed for this tumor context |
| **B** | Phase I-II, basket trial, or strong subgroup in this/close analog tumor |
| **C** | Retrospective, case series, or translational rationale |
| **D** | Preclinical or hypothesis only |

### Category Label
- **Standard-of-care** — guideline-endorsed for this indication
- **Off-label** — approved drug, different indication
- **Clinical trial / Investigational** — available only via trial enrollment
- **Supportive care / local therapy** — palliative, symptom management, radiation, surgery

---

## Negative Recommendation Rule

MUST include a "Not Recommended / 不建议" section listing:
- Options ineffective in this biomarker/tumor setting (with reason)
- Options unsafe due to organ function or prior severe AEs
- Options lacking evidence for this tumor type
- Common patient-asked-about drugs that do NOT apply

Never omit this section. Patients need to know what NOT to pursue.

---

## Safety-First Rule (Organ-Constraint Priority)

1. Identify the **dominant limiting organ system** (renal / hepatic / marrow / cardiac / neuro)
2. Every regimen suggestion must include:
   - Dose adjustment for the limiting organ
   - Monitoring requirements
   - Contraindications
   - Drug-drug interactions with current medications
3. If multiple organ systems compromised, flag cumulative risk

---

## China-Specific Realism

- Prefer drugs accessible in China (NMPA-approved > imported > compassionate)
- Trial matching: prioritize China recruiting sites
- Clearly state access uncertainty: 国内上市 / 未上市但可及 / 仅临床试验 / 需跨境
- Include cost context where relevant (medical insurance coverage, PAP programs)
- Note NMPA vs FDA approval status differences

---

## Workflow Steps

### Step 1: Molecular & Genomic Interpretation
Query databases for each actionable alteration:
- OncoKB (evidence levels 1-4), COSMIC (mutation frequency), ClinVar (clinical significance)
- cBioPortal (comparable cases), PubMed (recent 2 years), GDC/ICGC (survival data)

Classify each alteration: driver vs passenger, therapy-associated vs prognostic, germline implications.
Interpret immune biomarkers. Output: ranked molecularly informed strategies with evidence grading.

### Step 2: Pharmacology & Regimen Comparison
Trigger when: choice between 2+ agents in same class, OR dosing/safety central, OR user asks drug comparison.
Query: DrugBank, FDA Labels, NMPA, drug interactions, GDSC.
Compare: potency, PK, interactions, toxicity, renal/hepatic dosing, China availability.

### Step 3: Clinical Strategy Optimization
Query: NCCN, ESMO, ASCO, NICE guidelines; PubMed; Cochrane; FAERS.
Assess: standard-of-care pathways, rechallenge feasibility, novel combinations, next-line roadmap with contingency.

### Step 4: Clinical Trial Matching (China-Prioritized)
Query: ClinicalTrials.gov, ChiCTR, JapicCTI.
Search by: tumor type, actionable targets, resistance mechanisms, immune phenotype.
Return table: Trial ID, Phase, Target, City/institution, key inclusion/exclusion, organ requirements, feasibility rating.

### Step 5: Safety & Adverse Event Check
Query: FAERS, EudraVigilance, drug interactions.
Identify: severe AEs (>=5% incidence), black box warnings, interactions, organ contraindications.

### Step 6: Real-World Evidence
Query: GDSC, SEER/NCDB if accessible.
Provide real-world context and survival outcomes from comparable populations.

---

## HTML Output Structure

Output Chinese (Simplified) HTML. No Markdown, no preface. Sections:

1. **Header**: 虚拟分子肿瘤委员会会诊报告 + report date
2. **Executive Summary**: patient one-liner, current treatment, core recommendations (3-5 bullets)
3. **Section 1 — 患者概况**: info grid (age/sex, height/weight, ECOG, diagnosis, metastases, tumor markers, renal function, comorbidities)
4. **Section 2 — 分子特征**: table (biomarker, result, clinical significance, recommended action)
5. **Section 3 — 治疗史**: visual timeline with markers (line numbers, events, PD markers)
6. **Section 4 — 药物/方案对比**: drug comparison grid with evidence badges
7. **Section 5 — 器官功能剂量调整**: calculation box + dosing table
8. **Section 6 — 治疗路线图**: prioritized recommendations with evidence level badges (A=green, B=yellow, C=orange, D=red)
9. **Section 7 — 临床试验**: matched trials table with feasibility rating
10. **Section 8 — 不建议方向**: Not Recommended with rationale
11. **Section 9 — 支持治疗**: symptom management, nutrition, pain, psycho-oncology
12. **Section 10 — 下一步行动**: concrete next steps with timeline
13. **Footer**: disclaimer (信息仅供参考, 请与主治医生确认)

Use CSS classes: `.badge-success` (A), `.badge-warning` (B), `.badge-danger` (D), `.badge-info` (standard), `.badge-secondary` (off-label). Include `@media print` rules for clean printing.
