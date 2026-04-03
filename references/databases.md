# Medical Database Reference (17 Categories)

Query method legend: **API** = direct API call, **MCP** = MCP tool (medical-database-query skill), **Web** = WebSearch/browser

---

## 1. Clinical Literature

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| PubMed | Published research, clinical trials | MCP `search_pubmed` | `EGFR exon 20 insertion NSCLC treatment 2024` |
| medRxiv | Preprints (clinical) | Web | `site:medrxiv.org KRAS G12C resistance mechanisms` |
| bioRxiv | Preprints (basic science) | Web | `site:biorxiv.org neoantigen vaccine solid tumor` |
| Cochrane | Systematic reviews, meta-analyses | MCP `search_cochrane` | `immunotherapy vs chemotherapy first-line NSCLC` |

## 2. Treatment Guidelines

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| NCCN | US standard-of-care pathways | MCP `search_nccn_guidelines` | `NCCN NSCLC version 2025 second-line` |
| ESMO | European guidelines + ESCAT molecular | MCP `search_esmo_guidelines` | `ESMO cholangiocarcinoma FGFR2 fusion` |
| CSCO | China-specific guidelines | Web | `CSCO 2025 胃癌诊疗指南 三线治疗` |
| ASCO | Clinical practice guidelines | MCP `search_asco_guidelines` | `ASCO guideline HER2-low breast cancer` |
| NICE | UK cost-effectiveness + access | MCP `search_nice_guidelines` | `NICE pembrolizumab MSI-H solid tumors` |

## 3. Drug Information

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| DrugBank | Mechanism, PK/PD, interactions | MCP `search_drugbank` | `sotorasib mechanism pharmacokinetics` |
| FDA Labels | US prescribing information, dosing | MCP `search_fda_labels` | `osimertinib renal impairment dose adjustment` |
| NMPA | China approval status, labels | MCP `search_nmpa` | `信迪利单抗 NMPA 适应症` |

## 4. Genomics

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| OncoKB | Actionable alterations + evidence levels | MCP `search_oncokb` | `BRAF V600E level 1 all tumor types` |
| COSMIC | Mutation frequency by cancer type | MCP `search_cosmic` | `PIK3CA H1047R frequency breast cancer` |
| ClinVar | Variant clinical significance (incl. germline) | MCP `search_clinvar` | `BRCA2 c.5946delT pathogenicity` |
| cBioPortal | Genomic alterations, co-occurrence, outcomes | MCP `search_cbioportal` | `KRAS G12C co-mutations NSCLC survival` |

## 5. Clinical Trials

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| ClinicalTrials.gov | Global trial registry | MCP `search_clinical_trials` / API | `CONDITION=NSCLC&INTERVENTION=bispecific&STATUS=RECRUITING` |
| ChiCTR | China trial registry | MCP (chictr-mcp-server) | `非小细胞肺癌 EGFR 20ins 招募中` |
| JapicCTI | Japan trial registry | MCP `search_japiccti` / Web | `gastric cancer claudin 18.2 phase III` |

## 6. Cell Therapy

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| CAR-T Database | CAR-T targets, trials, outcomes | Web | `CAR-T Claudin18.2 solid tumor clinical trial` |
| TIL Therapy | Tumor-infiltrating lymphocyte trials | Web | `TIL therapy melanoma lifileucel results` |
| China CAR-T Registry | China-specific cell therapy | Web | `中国 CAR-T 实体瘤 临床试验 2025` |

## 7. Cancer Vaccines & Neoantigens

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| IEDB | Immune epitope data | Web/API | `KRAS G12D HLA-A*11:01 epitope binding` |
| NeopepDB | Neoantigen peptide database | Web | `neoantigen prediction TP53 R248W` |

## 8. ADC Drugs

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| ADC Review | ADC pipeline, targets, payloads | Web | `Trop2 ADC datopotamab deruxtecan NSCLC` |
| PubMed | ADC clinical data | MCP `search_pubmed` | `antibody drug conjugate HER2-low 2024 phase III` |

## 9. TCM & Natural Products

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| TCMSP | TCM systems pharmacology | Web | `curcumin target network NSCLC` |
| PubMed | Evidence for TCM in oncology | MCP `search_pubmed` | `traditional Chinese medicine chemotherapy synergy RCT` |

## 10. Drug Sensitivity

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| GDSC | Genomics of Drug Sensitivity in Cancer | MCP `search_gdsc` | `KRAS mutant cell lines MEK inhibitor sensitivity` |
| PRISM | Drug repurposing screen | Web | `PRISM drug repurposing pancreatic cancer cell lines` |

## 11. Regulatory Approvals

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| FDA | US approval, accelerated/breakthrough | Web/API | `FDA approved FGFR inhibitor cholangiocarcinoma` |
| EMA | EU approval status | MCP `search_ema_approvals` | `EMA zanidatamab HER2 biliary` |
| PMDA | Japan approval | Web | `PMDA approved ADC 2024 2025` |
| NMPA | China approval | MCP `search_nmpa_approvals` | `NMPA 2025 新批准抗肿瘤药物` |

## 12. Real-World Data

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| SEER | US population-based cancer statistics | Web | `SEER stage IV pancreatic cancer 5-year survival` |
| NCDB | National Cancer Database outcomes | Web | `NCDB cholangiocarcinoma resection outcomes` |

## 13. Adverse Events

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| FAERS | FDA adverse event reports | MCP `search_faers` | `pembrolizumab myocarditis signal reports` |
| EudraVigilance | EU adverse event reports | MCP `search_eudravigilance` | `nivolumab hepatotoxicity grade 3-4 frequency` |

## 14. Drug Interactions

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| DrugBank Interactions | DDI mechanism, severity | MCP `drug_interactions` | `sotorasib omeprazole CYP3A4 interaction` |
| PharmGKB | Pharmacogenomics, gene-drug | MCP `search_clinpgx_database` | `UGT1A1*28 irinotecan dose reduction` |

## 15. AI & Structural Tools

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| AlphaFold | Protein structure prediction | Web/API | `AlphaFold EGFR exon20 insertion structural impact` |
| BindingDB | Binding affinity data | Web | `BindingDB KRAS G12C covalent inhibitor Ki` |

## 16. Oncolytic Virus

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| OV-DB / PubMed | Oncolytic virus trials, mechanisms | Web / MCP `search_pubmed` | `oncolytic virus T-VEC combination checkpoint inhibitor` |

## 17. Molecular Diagnostics

| Database | Purpose | Method | Example Query |
|----------|---------|--------|---------------|
| FoundationOne CDx | Comprehensive genomic profiling panel | Web | `FoundationOne CDx gene list FDA companion diagnostic` |
| MSK-IMPACT | Memorial Sloan Kettering panel | Web | `MSK-IMPACT 505 gene panel clinical utility` |
| Guardant360 | Liquid biopsy ctDNA panel | Web | `Guardant360 CDx FDA approved indications` |

---

## Query Strategy

1. Start with MCP tools (fastest, structured output)
2. Fall back to WebSearch for databases without MCP integration
3. Cross-reference across categories: genomics (4) -> drug info (3) -> trials (5) -> safety (13)
4. For China-specific needs: always check NMPA (3), ChiCTR (5), CSCO (2)
5. For novel targets: check OncoKB (4) + PubMed (1) + ClinicalTrials.gov (5) in parallel

## Tool Availability Fallbacks

If MCP tools are unavailable, use these fallbacks without stopping the workflow:

| MCP Tool | Fallback |
|----------|----------|
| `search_pubmed` | WebSearch `site:pubmed.ncbi.nlm.nih.gov {query}` or WebFetch `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}` |
| `search_oncokb` | WebSearch `site:oncokb.org {gene} {mutation}` |
| `search_clinvar` | WebFetch `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=clinvar&term={query}` |
| `search_clinical_trials` | WebFetch `https://clinicaltrials.gov/api/v2/studies?query.cond={condition}&query.term={term}&filter.overallStatus=RECRUITING` |
| `search_chictr` / chictr-mcp-server | WebSearch `site:chictr.org.cn {中文关键词}` |
| `search_faers` | WebSearch `FDA FAERS {drug name} adverse events` |
| `search_nccn_guidelines` | WebSearch `NCCN guidelines {cancer type} {year} recommendations` |
| Any guideline database | WebSearch `{guideline org} {cancer type} {year} treatment algorithm` |

**Rule**: Always attempt MCP tool first. If it errors or returns empty, immediately fall back. Never let tool unavailability block the patient's navigation.
