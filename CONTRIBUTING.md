# Contributing to cancer-buddy (抗癌搭子)

Thank you for helping improve a tool that real cancer patients and their
families rely on. Because this project is patient-facing and medical, the bar
for contributions is higher than for a typical skill repo.

## The required contract: no fabricated medical facts

This is the single most important rule. **Every factual medical claim must
trace to a live, verifiable source.** Specifically, the following may never be
invented, guessed, or LLM-synthesized:

- **Doctors, hospitals, clinics** — must come from a real, citable source.
- **Clinical trials** — must come from a live registry query (e.g.
  ClinicalTrials.gov, ChiCTR), not generated from memory.
- **Citations** (guidelines, papers, legal references) — must point to a real,
  resolvable source.
- **Drug–food / drug–drug interactions and doses** — must carry a traceable
  evidence anchor.

If a fact cannot be sourced live, the correct behavior is to **decline or say
"I don't know"** — never to fabricate. When in doubt, degrade to "I can't
verify this right now" rather than inventing.

The design rationale behind this patient-first, never-fabricate posture is
documented in [`references/sid-framework.md`](references/sid-framework.md)
(internal design philosophy — not patient-facing).

## Safety-critical files

Changes to the following files are **safety-critical** and require extra review
(a second maintainer sign-off and a passing test run before merge):

- `references/safety-guardrails.md`
- `references/disclosure-behavior.md`
- `skills/cancer-buddy-nutrition/references/drug-food-interactions.md`

If your change touches any of these, call it out explicitly in your PR
description and justify each medical fact with its source.

## Running the tests

From the repo root:

```bash
# Schema validation
bash scripts/validate-profile-schema.sh
bash tests/unit/validate-profile-schema.test.sh

# Integration / structural checks
bash tests/integration/trigger-words.sh
bash tests/integration/disclosure-gate.sh
bash tests/integration/role-matrix.sh
```

Or run everything:

```bash
for t in tests/unit/*.sh tests/integration/*.sh scripts/validate-profile-schema.sh; do
  echo "== $t =="; bash "$t" || exit 1
done
```

All tests must pass (and CI must be green) before a PR is merged.

## Commit messages: Conventional Commits

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Examples:

- `feat(find-care): add never-fabricate gate before returning results`
- `docs(contributing): add safety-critical files list`
- `chore(release): cut v0.2.0`

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`.
Use a scope that names the affected sub-skill where it helps reviewers.
