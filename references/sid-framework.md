# Sid Sijbrandij Case Analysis — Design Philosophy Reference

Internal reference for understanding the methodology behind cancer-buddy. Not patient-facing.

---

## Who

- Sid Sijbrandij, GitLab co-founder/CEO
- Osteosarcoma (bone cancer), T5 vertebra (upper spine)
- Diagnosed November 2022, recurrence late 2024
- Doctors said: "You're done with standard of care, maybe there's a trial somewhere, good luck."
- Achieved NED (No Evidence of Disease) via systematic "founder mode" approach
- Published 25TB of medical data at osteosarc.com
- Started Even One Ventures (biotech fund) + Kilo Code (software company)

---

## The Three Principles

These are encoded into every phase of cancer-buddy.

### 1. Maximal Diagnostics (极致诊断)

> "The goal is simple: do every diagnostic available as often as possible. Just like GitLab's operating culture, no unit of information is too small to document."

Not "do the standard tests." Do **everything**. The insight: standard care operates "under the lamp post where we can see" — using well-understood tests. But Sid's cancer required molecular understanding unavailable through standard pathology. The more you measure, the more treatment handles you find.

### 2. 10+ Personalized Treatments in Parallel (并行不串行)

Standard oncology deploys treatments **serially** — try one, wait months for scans, if it fails try the next. Sid rejected this:

> Make 10+ personalized treatments and pursue them simultaneously. Don't wait for failure before trying alternatives.

Rationale: Cancer adapts in real-time. Serial approaches let the tumor evolve resistance between lines. Parallel pursuit maximizes the chance of finding something that works before the window closes.

### 3. Data is Power (数据即力量)

Sid maintained a **1,000+ page Google Doc** ("Sid Health Notes") cataloging every medical interaction, test result, and decision point. Plus 25TB of structured data at osteosarc.com.

Why: Patterns emerge only when you can see the full picture. His single-cell data at 3 timepoints revealed T-cell infiltration going from 19% → 89% — which proved the combination therapy was working. Without that longitudinal tracking, the signal would have been invisible.

---

## The Team Structure

Sid treated cancer like a startup. He hired a team:

### Jacob Stern — "Health CEO"
- Former Director at 10x Genomics (single-cell sequencing company)
- Full-time orchestrator: coordinated hospitals, labs, pharma companies, academic researchers
- Sequenced and interpreted single-cell data to guide treatment selection
- Translated scientific findings into actionable treatment decisions
- Described as "Forward Deployed Software Engineer" for healthcare — navigating bureaucracy, refusing to accept "no"

### Support Structure
- **Concierge medical services**: Private Medical, Private Health Management, Pathfinder Oncology — scaled diagnostic infrastructure
- **Clinical Advisory Board**: Senior oncologists providing medical guidance and institutional credibility
- **Scientific Advisory Board**: Computational biologists interpreting multi-omic data
- **External network**: Academic labs (organoids, cell therapy), pharma companies (expanded access), vaccine designers

**Key insight**: The most critical asset was not money — it was **Jacob Stern**. Someone who could simultaneously read single-cell data, coordinate with German radiotherapy centers, file FDA INDs, and translate it all into treatment decisions. Cancer-buddy exists to replicate this role.

---

## The Diagnostic Strategy (Deep Dive)

Not just "do tests." A systematic multi-modal, multi-timepoint measurement strategy:

| Category | What Sid Did | Why It Mattered |
|----------|-------------|-----------------|
| Single-cell sequencing (10x Genomics) | 3 tumor timepoints + 8 PBMC timepoints | Revealed tumor evolution in real-time; showed T-cell infiltration 19%→89% |
| WGS + WES | Full genome + coding regions | Identified ALL mutations, not just panel-limited ones |
| RNA-seq (3 platforms) | BostonGene, Tempus, Personalis | Cross-validation; each platform has different biases |
| TCR sequencing | Tracked tumor-infiltrating T-cell clones | Showed whether immune system was learning to fight — key signal for vaccine/immuno decisions |
| ctDNA/MRD monitoring | Serial blood tests from multiple providers | Early warning system for recurrence; detected trace tumor DNA before imaging could see it |
| Organoid drug sensitivity | Grew his tumor cells in lab, tested drugs on them | Predicted which drugs would actually work on HIS tumor, not average tumors |
| FAP-targeting diagnostic imaging | Cold isotope imaging | Revealed FAP+ cells → unlocked Lu-177 FAPI radiotherapy (the breakthrough treatment) |
| Pathology (H&E + IHC) | 12 tissue specimens | Confirmed genomic hypotheses at protein level |
| ASCAT copy number analysis | Chromosomal gains/losses | Identified structural variants missed by standard sequencing |

**Critical lesson for cancer-buddy**: The FAP imaging is what unlocked the breakthrough treatment. Without that specific diagnostic, they never would have known Lu-177 FAPI was an option. This is why "maximal diagnostics" isn't waste — you don't know which test will reveal the handle.

**Sample preservation protocol** (Sid's hard-won lesson):
> "Incredible struggle at every hospital to gain access to one's own tissue samples."

Hospitals typically preserve tissue only as FFPE (formalin-fixed, paraffin-embedded), which **destroys nucleic acids**. Sid insisted on fresh-frozen tissue in multiple aliquots. This is now a core teaching in cancer-buddy Phase 2.

---

## The Treatment Strategy (Deep Dive)

10+ parallel treatment lines, coordinated like concurrent engineering:

| Treatment | Type | Access Method | Role |
|-----------|------|---------------|------|
| Surgical resection + titanium spine fusion | Surgery | Standard | Remove bulk tumor |
| SBRT + proton beam therapy | Radiation | Standard | Local control |
| Aggressive systemic chemotherapy (4 transfusions) | Chemo | Standard | First-line standard care |
| **Lu-177 FAPI radiotherapy** | Nuclear medicine | **Flew to Germany** | **Breakthrough** — dramatic tumor shrinkage, enabled secondary surgery |
| Checkpoint inhibitors (anti-PD-1/PD-L1) | Immunotherapy | Standard/off-label | Release immune brakes |
| Neoantigen peptide vaccine | Immunotherapy | Experimental | Train immune system against tumor-specific mutations |
| Oncolytic virus therapy | Immunotherapy | Experimental | Selective cancer cell killing + immune activation |
| Personalized mRNA neoantigen vaccine | Immunotherapy | Experimental (Moderna-like platform) | Sustained anti-cancer immune response; maintenance therapy |
| Shasqi FAP-targeting chemotherapy | Targeted chemo | Single-patient IND trial | Delivered chemo directly to FAP+ tumor cells |
| **5 FDA expanded access INDs (Form 3926)** | Drug repurposing | **All approved in 48 hours** | Accessed investigational drugs outside of trials |
| CAR-T with genetic logic gates | Cell therapy | Academic collaboration | **Nuclear option** — backup if others failed; multi-target to prevent escape |

**Coordination model**: These weren't tried randomly. Jacob Stern sequenced them based on single-cell data and imaging feedback:
1. FAP imaging revealed target → Lu-177 FAPI radiotherapy in Germany
2. Radiotherapy shrunk tumor → enabled surgery
3. Post-surgery single-cell data showed immune activation → doubled down on immunotherapy combinations
4. mRNA vaccine as maintenance to sustain the immune response
5. CAR-T held in reserve as escalation option

**The 48-hour IND story**: Filing an FDA expanded access IND typically takes weeks-to-months. Sid's team filed 5 simultaneously and got all approved in 48 hours. This required: knowing the Form 3926 pathway exists, having pharma contacts willing to provide the drugs, and legal/medical teams ready to execute. Cancer-buddy's Phase 5 systematizes this knowledge.

---

## What's Broken in the System (Sid's Critique)

### Eroom's Law
The cost of drug development has **increased** exponentially since 1950 — the inverse of Moore's Law:
- $4.4 billion average for a new oncology drug (2017-2020)
- Only blockbuster market potential justifies investment
- Result: promising drugs for rare cancers are abandoned because market size is too small

### Hospital Tissue Access
> "Incredible struggle at every hospital to gain access to one's own tissue samples."

- Hospitals keep FFPE tissue that destroys RNA/DNA quality
- No standard process for patients to request fresh-frozen samples
- Pathology departments resist releasing tissue to external labs
- Each hospital is a separate battle

### IRB Vetocracy
- Institutional Review Boards can block experimental treatments
- One conservative member can veto novel approaches
- Designed for population-level research, not individual optimization
- Sid's words: standard care interprets "first do no harm" as "first do nothing"

### The Information-Treatment Gap
- Genomic sequencing is cheap and yields rich data
- But treatment options remain constrained to standard protocols
- No mechanism for dynamically matching molecular profiles to personalized therapies
- The measurement capability has outpaced the treatment capability

---

## The Economics

### What Sid Spent (estimated)
- Jacob Stern: full-time salary ($200K-400K/year)
- Concierge medical services: $50K-100K+/year
- Single-cell + multi-omic testing: $100K-300K
- International travel (Germany, multiple US centers): $50K+
- Organoid testing: $50K-100K
- Experimental drug access: variable
- **Total: estimated $2-5M+**

### What It Could Cost at Scale
Elliot Hershberg's future scenario from the Century of Bio article:
- Consumer cancer screening (early detection): $1,000-2,000
- Concierge oncology platform initial workup: $1,500
- AI-driven bioinformatics analysis: near-zero marginal cost
- Generic checkpoint inhibitor: ~$1,000
- Off-the-shelf cancer vaccine: TBD
- Custom radiotherapy (theranostics): $20,000-50,000
- **Total envisioned: ~$175,000** (with insurance coverage)

### Sid's Key Quote
> "It costs $1B to get a drug approved. But it costs $1M to dose a single person with a personalized therapy. That discrepancy is the highest it's ever been."

---

## Cancer-Buddy Translation Table

| What Sid Had | What Cancer-Buddy Provides | Cost Reduction |
|---|---|---|
| Jacob Stern (full-time Health CEO) | AI Agent — 24/7, structured workflows, no salary | ~95% |
| Team of computational biologists | AI genomic interpretation + database cross-reference | ~99% |
| Concierge medical coordination | Structured workflow: diagnostics → reports → trial matching → access nav | ~90% |
| Personal pharma connections | Systematic expanded access database + communication templates | ~80% |
| Custom data infrastructure (25TB) | Standardized JSON data vault, patient-controlled | ~95% |
| Advisory board meetings | On-demand consultation with evidence grading | ~95% |
| Legal team for IND filings | Application templates + pathway navigation | ~70% |

**What cancer-buddy cannot replace:** actual drug costs, hospital fees, international travel, willing physicians, and the patient's own determination.

---

## Even One Ventures

Sid's cancer-motivated biotech investment fund (evenone.ventures). Portfolio:

| Company | Focus |
|---|---|
| Arden Bio | Therapeutic development |
| Bulsara BioWorks | Life sciences |
| Echo Immune | Immune monitoring/profiling |
| Invocata | Biotech |
| Kernis Health | Healthcare |
| Ranata Therapeutics | Drug development |
| Valius Sciences | Life sciences |

Relevance: these represent the frontier of personalized oncology. Their pipelines may yield future treatment options for cancer-buddy users.

---

## The Core Thesis

The barriers to Sid-level cancer care are **structural and organizational**, not technical:
- The knowledge exists (published literature, clinical data)
- The drugs exist (approved somewhere, or in clinical trials)
- The diagnostics exist (commercially available)
- What's missing: **someone to connect the dots, navigate the system, and move fast**

Sid proved the **possibility**. Cancer-buddy's mission is to prove the **scalability**.

An AI agent can perform 80-90% of the coordination work that Jacob Stern did, at <5% of the cost, making systematic cancer navigation accessible to non-billionaires.

> "The future is here, it's just not evenly distributed." — William Gibson
