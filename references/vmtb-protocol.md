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

---

## Active Treatment Overlap Assessment

When a patient is mid-treatment on Line N and the clinical situation requires considering adding a new agent or transitioning to a new regimen, the following framework must be applied.

### Washout Period Requirements

Before introducing a new systemic agent, assess whether a washout period is needed from the current therapy:

| Drug Class | Minimum Washout Period | Rationale |
|------------|----------------------|-----------|
| **Checkpoint inhibitors** (anti-PD-1/PD-L1/CTLA-4) | 4-6 weeks | Long half-life (15-25 days); persistent immune activation; risk of overlapping irAEs |
| **Tyrosine kinase inhibitors (TKIs)** | 5 half-lives of the specific TKI (typically 3-7 days for most TKIs) | Rapid clearance but variable; check specific drug PK |
| **Cytotoxic chemotherapy** | Per protocol (typically 21-28 days from last dose, or until ANC >1.5 and PLT >100) | Bone marrow recovery required |
| **Anti-VEGF/VEGFR agents** (bevacizumab, ramucirumab) | 4-6 weeks | Wound healing risk; bleeding risk with overlapping agents |
| **ADCs (antibody-drug conjugates)** | 3-4 weeks (varies by payload) | Payload-dependent myelosuppression and organ toxicity |
| **Hormonal agents** | Generally no washout needed | Low systemic toxicity overlap |
| **Radiation therapy** | 2-4 weeks (standard fractionation); 1-2 weeks (SBRT/SRS) | Tissue recovery; abscopal effect consideration |

### Decision Framework: STOP Current Line vs. ADD to It

**STOP current line and switch** when:
- Clear radiographic progression (RECIST PD) on current regimen
- Unacceptable toxicity (Grade 3-4 persistent or recurrent despite dose modification)
- New actionable molecular target identified that requires a different drug class
- Patient preference / quality of life deterioration

**ADD a new agent to current line** when:
- Mixed response (some lesions progressing, others stable/responding)
- Oligoprogression amenable to local therapy + continuation of systemic line
- Synergistic combination supported by evidence (e.g., adding anti-VEGF to checkpoint inhibitor)
- Maintenance intensification strategy with evidence basis

**Neither — hold and reassess** when:
- Pseudoprogression suspected (especially early in immunotherapy, within first 12 weeks)
- Ambiguous imaging (confirm with short-interval repeat scan at 4-6 weeks)
- Intercurrent illness confounding assessment

### Drug Combination Safety Matrix

Before combining agents, cross-check for overlapping toxicity profiles:

| Combination | Primary Overlapping Risk | Monitoring Required | Risk Mitigation |
|-------------|------------------------|--------------------|-----------------| 
| **Dual checkpoint** (anti-PD-1 + anti-CTLA-4) | Colitis (Grade 3-4: 10-15%), hepatitis, endocrinopathies | Weekly LFTs x 4 cycles, thyroid q2w, stool frequency log | Early steroid initiation at Grade 2 colitis; educate patient on diarrhea reporting |
| **Checkpoint + anti-VEGF** (e.g., atezo + beva) | GI bleeding/perforation (2-5%), proteinuria, hypertension | BP monitoring q1w initially; urine protein q2w; GI symptom tracking | Avoid in patients with GI tract primary at risk of perforation; hold anti-VEGF peri-procedurally |
| **Checkpoint + TKI** (e.g., pembro + lenvatinib) | Hepatotoxicity (Grade 3-4 ALT elevation: 5-10%), hypertension, hand-foot syndrome | LFTs weekly x 8 weeks then q2w; BP daily at home; dermatology assessment | Start TKI at reduced dose if borderline LFTs; defined TKI dose reduction steps |
| **Checkpoint + chemotherapy** | Myelosuppression, immune-mediated pneumonitis (especially with taxanes) | CBC with differential before each cycle; chest imaging if new dyspnea | G-CSF support as needed; low threshold for CT chest with new respiratory symptoms |
| **Checkpoint + radiation** | Radiation recall, pneumonitis (if thoracic field), enhanced immune toxicity | Monitor irradiated field for unexpected inflammation; pulmonary function | Consider sequential rather than concurrent if large radiation fields |
| **TKI + chemotherapy** | Cumulative myelosuppression, GI toxicity (mucositis, diarrhea) | CBC twice weekly during initial cycles; electrolytes; hydration status | Stagger administration if possible; aggressive anti-diarrheal prophylaxis |
| **Dual anti-VEGF pathway** (anti-VEGF + VEGFR-TKI) | Severe hypertension, hemorrhage, thrombotic microangiopathy | Generally NOT recommended — avoid this combination | If clinically necessary, requires intensive BP and renal monitoring |

### Common Immunotherapy Overlap Risks — Detailed

1. **Dual checkpoint blockade (anti-PD-1 + anti-CTLA-4) → Colitis**
   - Incidence of Grade 3-4 colitis: 10-15% (vs. 1-2% with monotherapy)
   - Onset: typically weeks 5-10 of combination
   - Management: hold both agents at Grade 2; IV methylprednisolone 1-2 mg/kg at Grade 3; infliximab if steroid-refractory
   - Rechallenge: consider anti-PD-1 monotherapy only after full resolution

2. **Checkpoint + anti-VEGF → Bleeding risk**
   - Mechanism: anti-VEGF impairs vascular integrity; immune activation may exacerbate mucosal inflammation
   - High-risk populations: GI primary tumors, tumors invading major vessels, patients on anticoagulation
   - Pre-treatment: confirm no cavitating lung lesions, no recent hemoptysis, no untreated varices
   - Monitoring: serial hemoglobin, stool occult blood if symptomatic

3. **Checkpoint + TKI → Hepatotoxicity**
   - Mechanism: dual immune and direct hepatocyte injury
   - Incidence of Grade 3-4 transaminase elevation: 5-10% (combination) vs. 1-3% (either alone)
   - Differentiation: immune hepatitis (typically with elevated total bilirubin, poor response to TKI hold alone) vs. TKI hepatotoxicity (typically improves rapidly with TKI hold)
   - Management: hold TKI first; if no improvement in 5-7 days, hold checkpoint and start steroids; liver biopsy if diagnostic uncertainty
