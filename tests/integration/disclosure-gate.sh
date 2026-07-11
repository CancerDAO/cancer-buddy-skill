#!/usr/bin/env bash
# For every sub-skill affected by disclosure (per skills/cancer-buddy/references/
# disclosure-behavior.md), assert its SKILL.md (1) declares a disclosure behavior,
# (2) cites the shared authority (disclosure-behavior.md), AND (3) the declaration
# expresses the CURRENT model: `disclosure_state` is a communication-planning hint,
# not access control — the mandated behaviors are "ask the authorized patient how
# much diagnostic detail to surface", "preview before generating/exporting", and
# "explicit scope-specific consent for exports; never infer consent from
# disclosure_state". A cell that still encodes the retired access-control model
# (refuse the patient's own artifact / censor on a caregiver-set flag) must FAIL.
#
# CONSISTENCY DESIGN (after three earlier weaknesses — fixed-window leak, trigger-condition
# collision, and subject-noun/forbidden-word/generic-word collision): the per-skill check is
# a behavior-DIRECTION regex chosen so a plausible FLIP of the cell DESTROYS the match. A
# direction token is a verb phrase that distinguishes the mandated behavior — NEVER a
# subject noun (cancer-type), the trigger condition (disclosure_state=suppressed), or a
# generic word. A flip back to the retired model (silently generate full detail / refuse
# or censor the patient) drops the ask-detail/preview/scope-consent phrasing entirely.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import re, sys, os
root = sys.argv[1]

# Companion-scope skills affected by disclosure (disclosure-behavior.md).
# Excluded: caregiver (N/A — patient never routes here); meta cancer-buddy (routing-only).
# Clinical skills live in cancer-buddy-pro-skill (private).
affected = ["organize", "vault", "education", "mind", "nutrition",
            "second-opinion", "disclosure", "find-care", "visit-prep"]

# behavior-DIRECTION regex per companion (None = presence-only). See header for the rule.
direction = {
    "organize":       r"(?s)(?=.*how much)(?=.*preview)",   # ask detail level + preview before writing the summary
    "vault":          r"(?s)(?=.*scope-specific)(?=.*consent)",  # exports need explicit scope-specific consent
    "education":      r"how much.*detail|多少.*细节",        # ask the patient how much detail the handbook shows
    "mind":           r"\bcontinue",                         # continue screening (suppressed never blocks support)
    "nutrition":      r"how much.*detail|多少.*细节",        # ask detail level for personalized plans
    "second-opinion": r"(?s)(?=.*scope-specific)(?=.*consent)(?=.*(never|not)\s+infer)",  # export consent never inferred from disclosure_state
    "disclosure":     None,                                  # this IS the disclosure workflow
    "find-care":      r"多少.*细节|预览",                    # ask detail level + preview before writing the shortlist
    "visit-prep":     r"how much.*detail",                   # ask detail level; caregiver flag never censors the patient
}

# Cells (except the disclosure workflow itself) must cite the shared authority so the
# per-skill specialization cannot drift from disclosure-behavior.md unnoticed.
CITE = re.compile(r'disclosure-behavior\.md')

def disclosure_cell(path):
    """The ACTUAL disclosure-behavior cell: the body of a `## Disclosure` section, or an
    inline `*Disclosure*:` / `**Disclosure**` declaration line. Scoping to the cell (not a
    line window) keeps unrelated prose (preflight role-gate, example query) out."""
    out, sec = [], False
    for ln in open(path, encoding="utf-8").read().splitlines():
        if re.match(r'^#+ *Disclosure', ln):
            sec = True; out.append(ln); continue
        if sec and re.match(r'^#+ ', ln):
            sec = False
        if sec:
            out.append(ln); continue
        if re.search(r'\*Disclosure\*\s*[:(]|\*\*Disclosure\*\*', ln):
            out.append(ln)
    return "\n".join(out)

errs = 0
for s in affected:
    f = os.path.join(root, "skills", "cancer-buddy-" + s, "SKILL.md")
    if not os.path.isfile(f):
        print(f"FAIL: cancer-buddy-{s} SKILL.md not found", file=sys.stderr); errs += 1; continue
    txt = open(f, encoding="utf-8").read()
    # 1) declares a disclosure behavior at all
    if not re.search(r'disclosure', txt, re.I):
        print(f"FAIL: cancer-buddy-{s} missing Disclosure declaration in SKILL.md", file=sys.stderr)
        errs += 1; continue
    rx = direction[s]
    if rx is None:
        continue  # disclosure skill = the workflow; presence suffices
    cell = disclosure_cell(f)
    # 2) the cell cites the shared authority
    if not CITE.search(cell):
        print(f"FAIL: cancer-buddy-{s} disclosure cell does not cite disclosure-behavior.md",
              file=sys.stderr)
        errs += 1
        continue
    # 3) the cell expresses the current behavior-direction (a flip would destroy this match)
    if not re.search(rx, cell, re.I):
        print(f"FAIL: cancer-buddy-{s} disclosure cell missing behavior-direction (/{rx}/)",
              file=sys.stderr)
        errs += 1

if errs:
    print(f"{errs} disclosure-gate violation(s)", file=sys.stderr)
    sys.exit(1)
print("disclosure gate intact (9 companions, behavior-direction consistent with disclosure-behavior.md)")
PY
