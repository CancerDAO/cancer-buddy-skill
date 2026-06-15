#!/usr/bin/env bash
# For every sub-skill affected by disclosure (per references/disclosure-behavior.md),
# assert its SKILL.md (1) declares a disclosure behavior AND (2) that declaration is
# consistent with the matrix cell — enforcing disclosure-behavior.md §"When the matrix
# updates" ("enforces both the declaration and consistency with this file").
#
# CONSISTENCY DESIGN (after three earlier weaknesses — fixed-window leak, trigger-condition
# collision, and subject-noun/forbidden-word/generic-word collision): the per-skill check is
# a behavior-DIRECTION regex chosen so a plausible FLIP of the cell DESTROYS the match. A
# direction token is a verb or negation that distinguishes the mandated behavior — NEVER a
# subject noun (cancer-type), the trigger condition (disclosure_state=suppressed), a forbidden
# staging word the cell says to AVOID (晚期/进展后), a generic word (normal), or an antonym
# substring (redact ⊂ unredacted). Word boundaries (\b) keep antonyms like "unredacted" from
# satisfying "redacted". Each direction has been mutation-tested to FAIL on a flipped cell.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import re, sys, os
root = sys.argv[1]

# Companion-scope skills affected by disclosure (disclosure-behavior.md Matrix).
# Excluded: caregiver (N/A — patient never routes here); meta cancer-buddy (routing-only).
# Clinical skills live in cancer-buddy-pro-skill (private).
affected = ["organize", "vault", "education", "mind", "nutrition",
            "second-opinion", "disclosure", "find-care", "visit-prep"]

# behavior-DIRECTION regex per companion (None = presence-only). See header for the rule.
direction = {
    "organize":       r"\bwarn",                       # warn ... breaks suppression
    "vault":          r"(?s)(?=.*(?:\bredacted\b|\bmasked\b))(?=.*export)",  # cell must say BOTH redacted/masked AND export (suppressed export redacted, not just the view)
    "education":      r"\brefuse",                      # refuse patient handbook
    "mind":           r"\bcontinue",                    # continue screening
    "nutrition":      r"not\s+surfaced",               # cancer-type NOT surfaced (flip drops 'not')
    "second-opinion": r"\brefuse",                      # refuse operator-only
    "disclosure":     None,                             # this IS the disclosure workflow
    "find-care":      r"避免",                          # 避免渲染晚期 (flip 避免->正常 drops it)
    "visit-prep":     r"\bavoid",                       # avoids surfacing 晚期 (flip avoids->surfaces drops it)
}

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
        if re.search(r'\*Disclosure\*:|\*\*Disclosure\*\*', ln):
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
    # 2) the cell expresses the matrix behavior-direction (a flip would destroy this match)
    if not re.search(rx, disclosure_cell(f), re.I):
        print(f"FAIL: cancer-buddy-{s} disclosure cell missing matrix behavior-direction (/{rx}/)",
              file=sys.stderr)
        errs += 1

if errs:
    print(f"{errs} disclosure-gate violation(s)", file=sys.stderr)
    sys.exit(1)
print("disclosure gate intact (9 companions, matrix behavior-direction consistent)")
PY
