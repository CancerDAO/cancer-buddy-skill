<div align="center">

# Cancer Buddy.skill

> *"Your doctor said there's nothing left to try. But your road isn't over."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![CancerDAO](https://img.shields.io/badge/CancerDAO-Open%20Source-orange)](https://github.com/CancerDAO)

<br>

Just diagnosed — can't make sense of the pathology report?<br>
Got genetic testing done — no idea which mutations matter?<br>
Doctor says there's no standard treatment left — but you're not ready to give up?<br>
Want to find clinical trials — don't know where to look or how to match?<br>
Juggling multiple treatments at once — losing track of what's what?<br>

**You need a buddy — an AI companion that knows the landscape and helps you find every possible path.**

<br>

Give your buddy your medical reports, genetic tests, and imaging results<br>
It helps you **understand your diagnosis, explore every treatment option, and manage the entire process**<br>
Clinical trial matching, expanded access navigation, cross-border treatment planning — one Skill covers it all

[Features](#features) · [Install](#install) · [Usage](#usage) · [Examples](#examples) · [**中文**](README.md)

</div>

---

## What Can This Buddy Do For You

From diagnosis to treatment, a cancer patient has to visit countless hospitals, consult dozens of specialists, and sift through mountains of information.

**Cancer Buddy packs all of that into one Skill:**

| Your Problem | How Buddy Helps |
|-------------|----------------|
| Can't understand my reports | Explains every item in plain language, highlights what matters |
| Don't know what tests to get | Gives you a complete testing checklist adapted to your budget |
| Want to know all treatment options | Exhaustive 8-dimension search: standard care, targeted therapy, immunotherapy, clinical trials, frontier treatments… |
| Looking for clinical trials | Simultaneously searches ClinicalTrials.gov + ChiCTR (China Clinical Trial Registry), evaluates each one |
| Doctor says "nothing more we can do" | 5 expanded access pathways + cross-border treatment options + application templates |
| Managing multiple treatments | Multi-line treatment dashboard, monitoring calendar, drug interaction alerts |
| Want to track my own cancer data | Helps you build your own N-of-1 data vault |
| Can't understand what the doctor said | Generates easy-to-read patient education materials |

---

## Features

### 9 Navigation Phases

```
Phase 0  Record Processing     PDF/images → structured patient profile
Phase 1  Understanding         Plain-language diagnosis interpretation + info gaps
Phase 2  Diagnostics           4-tier testing menu adapted to your budget
Phase 3  Report Interpretation Help you understand genetic tests and reports
Phase 4  Pathway Exploration   8-dimension exhaustive treatment search
Phase 5  Access Navigation     Expanded access / compassionate use / cross-border
Phase 6  Battle Management     Parallel multi-line treatment + monitoring calendar
Phase 7  Data Vault            Build your own N-of-1 health data archive
Phase 8  Patient Education     Generate patient-friendly educational materials
```

No need to follow the order. Buddy detects where you are and routes you to the right phase.

### Design Philosophy

Inspired by GitLab founder Sid Sijbrandij's ["Founder Mode on Cancer"](https://centuryofbio.com/p/sid) — after exhausting standard care, he assembled an elite team, ran every possible diagnostic, pursued 10+ parallel treatment lines, and achieved no evidence of disease (NED).

His three core strategies are encoded into every phase of Cancer Buddy:

1. **Maximal Diagnostics** — Run every useful test. No piece of information is too small.
2. **Parallel, Not Serial** — Explore multiple paths simultaneously. Don't wait for one to fail before trying the next.
3. **Data is Power** — Document everything. Build your own dataset.

> Sid spent millions of dollars and a full-time expert team. Cancer Buddy's mission: give everyone the same level of information support.

---

## Install

### Claude Code

```bash
# Install to current project
mkdir -p .claude/skills
git clone https://github.com/CancerDAO/cancer-buddy-skill .claude/skills/cancer-buddy

# Or install globally (available in all projects)
git clone https://github.com/CancerDAO/cancer-buddy-skill ~/.claude/skills/cancer-buddy
```

### Dependencies

None. Cancer Buddy runs on Claude Code's native capabilities.

Optional enhancement:
- `chictr-mcp-server` — Adds China Clinical Trial Registry (ChiCTR) search ([install guide](https://github.com/PancrePal-xiaoyibao/chictr-mcp-server))

---

## Usage

In Claude Code, type:

```
cancer buddy
```

Or any of these:

```
help me analyze my condition
I've run out of standard treatments
find me clinical trials
interpret this genetic report
抗癌搭子
```

Buddy auto-detects your situation and routes you to the right navigation phase.

### What You Can Give Buddy

| Input | Format |
|-------|--------|
| Pathology report | PDF / image / text |
| Genetic testing report | PDF / image / text |
| Imaging report (CT/MRI/PET-CT) | PDF / image / text |
| Blood tests | PDF / image / text |
| Treatment history | Just tell buddy in your own words |

---

## Examples

### Scenario 1: Just Diagnosed, Can't Read the Report

```
User          ❯ Help me understand this pathology report [uploads PDF]

Cancer Buddy  ❯ I've read through it. Here's the plain-language version:

                Cancer type: Sigmoid colon adenocarcinoma, moderately differentiated
                Stage: IV — means it has spread, in this case to both lungs
                Key mutation: KRAS G12C — there are targeted drugs for this
                Immune marker: MSS — immunotherapy alone is less effective

                🔴 Should do soon: ctDNA test (monitors tumor signals in blood)
                🟡 Worth considering: RNA sequencing (may reveal more targets)

                Want me to search for treatment options for this profile?
```

### Scenario 2: Standard Treatment Exhausted

```
User          ❯ I've been through 5 lines of treatment.
                Doctor says there's no standard option left.

Cancer Buddy  ❯ Running out of standard options doesn't mean running out of roads.
                Let me look into it:

                🟢 High feasibility:
                1. KRAS G12C inhibitor clinical trials — 3 currently recruiting
                2. Novel drugs available through Hainan Boao pilot zone

                🟡 Medium feasibility:
                3. Personalized neoantigen vaccine — 2 institutions in China
                4. Expanded access trial — requires contacting sponsor

                🔴 Exploratory:
                5. Lu-177 targeted radiotherapy in Germany

                Want me to evaluate which fits your situation best?
```

### Scenario 3: Finding Clinical Trials

```
User          ❯ Help me find clinical trials

Cancer Buddy  ❯ Based on your profile, I searched both ClinicalTrials.gov and
                China Clinical Trial Registry. Found 7 matching trials:

                High match (2):
                ✅ NCT06XXXXXX — Shanghai hospital, currently recruiting
                ✅ ChiCTR-XXXX — Beijing hospital

                Conditional match (3):
                ⚠️ NCT05XXXXXX — need to confirm certain lab values

                Excluded (2):
                ❌ First-line patients only

                Want me to draft contact materials for the research centers?
```

---

## Project Structure

```
cancer-buddy-skill/
├── SKILL.md                           # Skill entry point
└── references/                        # Loaded on demand
    ├── templates.md                   #   Output templates
    ├── vmtb-protocol.md               #   Consultation protocol
    ├── databases.md                   #   Medical database reference
    ├── trial-matching.md              #   Clinical trial matching protocol
    ├── pathway-exploration.md         #   Treatment pathway exploration
    ├── access-pathways.md             #   Access pathways + cross-border
    ├── diagnostics.md                 #   Diagnostic menu (China-specific)
    ├── data-vault.md                  #   Data vault schema
    └── sid-framework.md               #   Design philosophy reference
```

---

## Important Notes

- **Buddy is not a doctor.** All outputs are information organization and reference only. They do not constitute medical advice. Always confirm with your medical team before making decisions.
- **Data privacy**: Buddy runs locally. Your data is never uploaded to any third-party service.
- **Information timeliness**: Drug approvals and clinical trial recruitment statuses change. Always verify.
- **Garbage in, garbage out**: The more complete the information you provide, the more accurate the analysis.

---

## Contributing

Contributions welcome! Especially:

- Treatment pathway additions for specific cancer types
- Hospital / testing institution information updates
- Multi-language support
- Bug fixes and UX improvements

Please open an [Issue](https://github.com/CancerDAO/cancer-buddy-skill/issues) or PR.

---

## Who's Behind This

[CancerDAO](https://github.com/CancerDAO) — Making personalized cancer information support accessible to everyone through AI and open source.

---

<div align="center">

MIT License © [CancerDAO](https://github.com/CancerDAO)

**Every Star is a vote for "never give up."**

</div>
