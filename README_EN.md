<div align="center">

# cancer-buddy.skill

> *"Cancer shouldn't be a battle fought alone."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![CancerDAO](https://img.shields.io/badge/CancerDAO-Open%20Source-orange)](https://github.com/CancerDAO)

<br>

Just diagnosed, a pile of reports and no idea how to sort them? Caring for a family member with cancer, about to burn out? Lying awake at 3am, running through the worst-case scenarios? Not sure whether — or how — to tell your family?<br>
These questions don't have standard answers, but you shouldn't have to face them alone.<br>

**You need a buddy. One that doesn't judge, doesn't decide for you, but is always there.**

<br>

Hand over your medical records, your feelings, your family situation.<br>
Your buddy will **walk this road with you, step by step**.<br>
Organizing records, helping the caregiver catch a breath, mental-health screening, figuring out how to start a disclosure conversation,<br>
drafting a handbook your parents can actually read, packing a referral case for another hospital. One Skill holds all of it.

[Features](#features) · [Install](#install) · [Usage](#usage) · [Examples](#examples) · [**中文**](README.md)

</div>

---

## What cancer-buddy can help you with

What cancer brings isn't just the treatment — it's the pile of information, the feelings, and the family pressure all at once. Most of these don't have standard answers, but they can be organized and held better.

**cancer-buddy pulls all of this into one executable support system:**

| What you're facing | How cancer-buddy helps |
|-------------------|------------------------|
| A pile of records you don't know how to sort | Auto OCR, classification, filing — a usable structured archive |
| Caring for someone, about to break | Caregiver division-of-labor templates, Zarit self-assessment, breathing-room toolkit |
| 3am insomnia, anxiety, thoughts of ending it | PHQ-9 / GAD-7 / C-SSRS Lite screeners, crisis hotlines surfaced right away |
| Should we tell Mom / Dad / the kids? | Layered, context-aware disclosure — not a binary yes/no |
| Want my own health archive | N=1 structure + sharing levels (🔒 private → 🌐 public), you own it |
| Need a handbook my parents can actually read | Patient education booklet with Mermaid diagrams, daily-living guide, follow-up schedule |
| What can I eat during chemo? Is ginseng okay? | Menus by cancer type + treatment phase, with drug-food interaction checks |
| Want to try another hospital or go abroad | One-page English case summary, Dr.-to-Dr. cover letter, shipping guide |
| Need to find a hospital that runs MTB, a sub-specialty oncologist, or a recruiting trial | Multi-subagent parallel web research over one-source data, ranked shortlist with appointment paths |

---

## Features

### 11 companion modules

```
organize        Turn PDFs / images / docx records into a structured archive (auto-isolates irrelevant files, reconciles re-uploads)
caregiver       Caregiver support: division of labor, self-care, burnout screening
mind            Mental-health screening + crisis response (depression / anxiety / suicide risk)
disclosure      Whether to tell, how to tell, when to tell
vault           Your own N=1 health archive with sharing levels
education       Patient education handbook for family (with diagrams)
nutrition       Companion nutrition by cancer type + treatment phase
second-opinion  Cross-hospital / cross-border second-opinion packet
find-care       Find MTB/MDT-capable hospitals, sub-specialty oncologists, and recruiting trials (parallel multi-subagent web research)
case-precedent  Find similar real CASE REPORTS on PubMed/EPMC — what they tried, what happened. Leads, not prognosis; mandatory publication-bias disclosure
visit-prep      One-page visit-prep pack: doctor's 30-second snapshot + questions to ask + what to bring + what changed since last visit
```

You don't have to use them in order. The system will first understand your role (patient / caregiver / family member), then guide the next step based on context.

cancer-buddy also **auto-localizes its output to your records' language**: English records get an English archive, French records get French — no manual setting (the detected language is saved to your profile so the whole journey stays consistent). Clinical terms — drug names, genes, variants, TNM, numeric values and units — always stay verbatim, because a mistranslation is a medical risk; localization only touches section titles, field labels, and narrative copy.

organize is **runtime-neutral**: its behavior contract is decoupled from its execution mechanism, so the same contract can be driven by Claude Code, codex, or any other headless agent — the logic and output structure stay the same.

### Design philosophy

cancer-buddy is a system of *companionship + structure*, not a *decision replacement*.

In cancer, the most critical decisions — treatment regimen, whether to switch lines, communicating prognosis — must happen between you and your treating physician.

What cancer-buddy does:

- Organize information (records, timeline, indicator trends) — each time you add material, the one-page **Case Summary** auto-refreshes with trend charts of tumor markers/labs (with treatment-line changes on the same axis) and a "what changed since last summary" strip
- Help you prepare questions (so every clinic visit goes further)
- Offer support under emotional pressure

What cancer-buddy won't do:

- Provide treatment plans or specific medication advice
- Replace a physician's clinical judgment

But there's one thing cancer-buddy will always do:

When clear signals of a mental-health crisis show up, surface real-world help first.

---

## Install

```bash
# Global install (usable from any project, recommended)
npx skills add CancerDAO/cancer-buddy-skill -g --all

# Or install to the current project
npx skills add CancerDAO/cancer-buddy-skill --all
```

`--all` installs all 13 sub-skills (the meta entry + 11 companions + 1 web-access dependency) at once, no interactive picking. Restart Claude Code, then say `cancer-buddy` or `抗癌搭子` to get going.

> If you only want a subset, drop `--all` and the CLI will enter interactive mode.
>
> **Criterion-level trial matching** lives in [clinical-trial-matching-skill](https://github.com/CancerDAO/clinical-trial-matching-skill) (also CancerDAO open source). You don't need to install it upfront — when `find-care` produces a shortlist with NCT / ChiCTR trials and the user asks for criterion-by-criterion matching, cancer-buddy auto-fetches it via `npx skills add` and routes the call. See [INSTALL.md](INSTALL.md) for details.

---

## Usage

You can just say what's on your mind, in plain language:

```
Help me organize my records
I'm caring for a family member and it's too much
Should we tell the family about the diagnosis
Help me prepare materials for a referral
```

The system routes you into the right module based on context.

### What you can bring

| Input | Format |
|-------|--------|
| Pathology / genomic / imaging / blood reports | PDF / image / plain text — any of them work |
| What's happening right now | Just tell the buddy in your own words |
| Emotional state | No need to compose it — say it however it comes |
| Family situation | Who's caring, who doesn't know, who won't allow disclosure |

---

## Examples

### Scenario 1: A pile of fresh reports

```
User         ❯ My mom was just diagnosed. The doctor handed me a stack
               of stuff and I have no idea what any of it is.
               [drops in a folder]

cancer-buddy ❯ Let me sort this for you. 23 files total, grouped like this:

               📋 Pathology (3)  — primary biopsy / IHC / genomics
               🔬 Imaging (8)    — chest-abdomen CT / PET-CT / brain MRI
               🩸 Blood (9)      — admission labs + tumor marker trend
               💊 Treatment (2)  — first chemo record + discharge summary
               📝 Other (1)      — a handwritten medical order

               Filed under patients/PT-17CE02BC33/.
               I've written you a timeline.md and profile.json —
               you can print them before the next visit.

               What do you want to understand first?
```

### Scenario 2: Caregiver at the edge

```
User         ❯ My dad has stage-III lung cancer. I'm caring for him alone.
               Haven't slept properly in a month.
               Cried in the hospital hallway for half an hour yesterday.

cancer-buddy ❯ You've been carrying this for a long time. Let's do a quick
               self-check first:

               [Zarit Caregiver Burden Scale — 5 questions, 2 minutes]

               ...

               You're scoring high on "emotional exhaustion" and
               "financial stress." This isn't you being weak — this is a
               normal response.

               Three things you can do this week:
               1. Share the load — I'll draft a family-chat message
                  listing tasks (your dad's cousins' generation —
                  people who'd help but haven't been asked)
               2. Backup — find even a 4-hour window where someone
                  else covers, and go outside
               3. Professional support — at this level, book a
                  psychiatry or medical-social-work visit.
                  Not for your dad — for you.

               If thoughts of "disappearing" or "ending it" show up,
               call 400-161-9995 immediately (24-hour line).
```

### Scenario 3: Should we tell him?

```
User         ❯ My mom has stage-IV breast cancer. My dad has hypertension
               and a history of depression. The whole family is hiding it
               from him. My sister says absolutely don't tell him.
               But I don't think this is sustainable.

cancer-buddy ❯ This is one of the hardest things in Chinese families.
               I won't decide for you — but I'll help you think it through.

               A few things to clarify first:
               • Does your mom know? Does she want him to know?
               • Is your dad's depression currently being treated regularly?
               • Is the concealment total or partial? How are you explaining
                 the chemo hair loss?

               A common trap: framing this as "tell vs. don't tell."
               What usually works better is **layered disclosure**:

               Layer 1: Let him know "she's sick, she's being treated"
               Layer 2: Once he's emotionally stable, discuss what it is
               Layer 3: When he needs to participate in decisions,
                        discuss stage and prognosis

               Want me to draft the Layer-1 conversation script?
               (Given his depression history, I'll include a paragraph
               suggesting coordination with his psychiatrist.)
```

---

## Project structure

```
cancer-buddy-skill/
├── README.md                          # 中文版
├── README_EN.md                       # you are here
├── INSTALL.md                         # detailed install guide
└── skills/
    ├── cancer-buddy/                  # meta entry (routes to the 11 companions below)
    ├── cancer-buddy-organize/         # record organization
    ├── cancer-buddy-caregiver/        # caregiver support
    ├── cancer-buddy-mind/             # mental-health screening + crisis
    ├── cancer-buddy-disclosure/       # disclosure conversations
    ├── cancer-buddy-vault/            # N=1 health archive
    ├── cancer-buddy-education/        # patient handbook generator
    ├── cancer-buddy-nutrition/        # nutrition companion
    ├── cancer-buddy-second-opinion/   # second-opinion packet
    ├── cancer-buddy-find-care/        # find hospitals / doctors / trial sites
    ├── cancer-buddy-case-precedent/   # find similar real case reports (leads, not prognosis)
    ├── cancer-buddy-visit-prep/       # one-page visit-prep pack
    └── web-access/                    # bundled web automation backbone (powers find-care's parallel subagents)
```

---

## Data

Everything is stored locally by default:

```
$HOME/CancerDAO/patients/
```

- Identified by an anonymous `patient_code`
- Your uploaded originals are kept **verbatim in a local `raw/` vault** (under your control, never sent off-device); the downstream artifacts (text-masked MD sidecars, structured JSON, outgoing reports) are **PII text-masked** and carry no plaintext identity information
- Custom paths supported

All generated content (timeline, profile, etc.) is in readable, exportable, open formats — nothing proprietary.

The organized archive also ships an `AGENTS.md` index: compatible agent tools (pi, Claude Code) that open a new session in that directory automatically recognize *whose* records these are and read the right file for the question — no need to re-point them each time or invoke the buddy skill first; just pick up where you left off.

---

## Notes

- This tool does not provide medical diagnosis or treatment advice
- All medical decisions should be confirmed with a qualified physician
- In a mental-health crisis, seek real-world help first

---

## Contributing

Contributions welcome, especially:

- Disclosure scripts and caregiver division-of-labor templates for Chinese family contexts
- Mental-health screener localization (PHQ-9 / GAD-7 done; C-SSRS still in progress)
- Updates to local cancer centers, social-work resources, and hotline information
- Cancer-type templates for patient education handbooks
- Bug fixes and UX improvements

Please open an [Issue](https://github.com/CancerDAO/cancer-buddy-skill/issues) or a PR.

---

## About us

[CancerDAO](https://github.com/CancerDAO) — building AI + open-source support systems for patients and families.

---

## Acknowledgements

The "parallel multi-subagent web research" capability in `cancer-buddy-find-care` is built on top of the open-source skill **[web-access](https://github.com/eze-is/web-access)** (MIT License) by [一泽Eze](https://github.com/eze-is).

We bundle `web-access` as a vendored dependency under `skills/web-access/`, preserving the original SKILL.md, scripts, and references (CDP Proxy, parallel subagent dispatch strategy, site-pattern knowledge). **All copyright and IP for that module belong to the original author** — we redistribute it under MIT and call into it from `find-care`.

If your own project needs real-browser automation, logged-in web operations, or multi-agent parallel scraping inside Claude Code, we strongly recommend installing the upstream [eze-is/web-access](https://github.com/eze-is/web-access) directly.

---

<div align="center">

MIT License © [CancerDAO](https://github.com/CancerDAO)

**You don't have to face this alone.**

</div>
