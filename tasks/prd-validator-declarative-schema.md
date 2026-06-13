# PRD: Declarative-Schema Profile Validator

> Status: **DRAFT — awaiting founder confirmation before any code is written.**
> Author: Claude Code (engineering). Date: 2026-06-06.
> Related history: PR #8, #9, #10 — three consecutive PRs fixing the *same class*
> of bug in `scripts/validate-profile-schema.sh`.
>
> ⚠️ **Partially superseded (2026-06-14, round 13).** The imperative validator has been
> migrated in place to the **`cancer_buddy_profile_v3` nested shape** (top-level `schema`
> == `cancer_buddy_profile_v3` + `summary.{primary,histology,stage}`; ECOG under
> `latest_status`; demographics/drivers/treatment-lines validated in
> `patient_summary.json`/`molecular.json`/`treatment_lines.json`, not here), and the
> `review_flags` category whitelist expanded to the full 9-category roster. So the
> "current accept/reject behavior" referenced below is now the **v3** contract, NOT the
> retired flat shape. The schema specs in US-001 below have been repointed to v3 — if this
> declarative refactor is ever executed, it MUST target v3, not `schema_version`+`diagnosis`.

## 1. Introduction / Overview

`scripts/validate-profile-schema.sh` is the source-of-truth validator for
`patients/<patient_code>/{profile,readiness,role}.json`. It is a hand-rolled,
imperative Python script (≈140 lines) embedded in a bash heredoc. Every field is
checked with ad-hoc `if "x" in obj` / `obj.get(...)` logic.

This design produces a recurring, predictable bug class: **every time an optional
field can be `null` or a required field can be malformed, someone must hand-write
a guard, and the guards are routinely missed.** Evidence is unambiguous:

- **#8** — `treatment_history[].start/.line` null → `TypeError` crash; `basics.ecog` null → false-reject.
- **#9** — same class in `basics` (whole-object null crash), `basics.sex`, `readiness.grade`, `readiness.review_flags`.
- **#10** — the mirror image: required fields (`patient_code`, `diagnosis`, sub-keys) and wrong types (`basics` as string → crash, `treatment_history` as string → silent pass) were not validated; plus residuals #9 *itself* missed (`basics` non-object crash, `role.json` asymmetry).

Three PRs, one root cause. The structural fix is to **declare** the contract once
and validate against it with a standard engine, so null/type/enum/required are all
handled uniformly and a new field needs a schema edit, not a new hand-written guard.

## 2. Goals

- Eliminate the "hand-write a null/type guard per field" bug class permanently.
- Make the contract **declarative and single-source**: one schema document that
  `references/patient-profile-schema.md` describes in prose.
- Preserve **100% of current accept/reject behavior** (this is a refactor, not a
  policy change) — proven by an equivalence harness, not by eyeballing.
- Keep the skill **distribution-light**: it currently has zero pip dependencies and
  ships via `npx skills add`. Adding heavy runtime deps is a cost to justify, not a default.
- Keep the existing CLI contract: `validate-profile-schema.sh <patient_dir>`,
  exit 0 on valid, non-zero + `ERROR:` lines on invalid.

## 3. User Stories

### US-001: Author `profile.schema.json` (Draft 2020-12 JSON Schema)
**Description:** As a maintainer, I want the profile contract expressed as a JSON
Schema file so the rules live in data, not code.

**Acceptance Criteria:**
- [ ] `references/schemas/profile.schema.json` exists, encoding the **cancer_buddy_profile_v3** contract in `references/patient-profile-schema.md`:
  - required: `schema` (const `"cancer_buddy_profile_v3"`), `patient_code` (pattern `^PT-`), `summary` (object, required `primary`/`histology`/`stage`).
  - optional, type+enum constrained, **nullable where the doc says so**: `latest_status.ecog` (int 0–4 | null), `latest_status.{regimen,response,as_of}`, `disclosure_state` (`full`/`partial`/`suppressed`), `alias`, `locale`, `anthropometrics`, `privacy`, top-level `source_refs[]`. (Demographics/`sex`, molecular drivers, and ordered treatment lines are NOT in profile.json under v3 — they live in `patient_summary.json`/`molecular.json`/`treatment_lines.json` and are validated by `validate_structured_outputs.py`. The retired flat fields `schema_version`/`diagnosis`/`basics`/`acp_status`/`surveillance_schedule_anchor`/`treatment_history` are gone.)
  - `additionalProperties: true` at top level (doc: "validator ignores unknown top-level keys" — must NOT regress into rejecting unknown blocks).
- [ ] Each of the 21 existing unit cases maps to an expected accept/reject under this schema (traceability table), including the regression cases that reject the legacy flat shape and a v3 profile missing `summary.stage`.

### US-002: Author `readiness.schema.json` and `role.schema.json`
**Description:** As a maintainer, I want the other two validated files covered by the same mechanism.

**Acceptance Criteria:**
- [ ] `readiness.schema.json`: `grade` enum `A–F`|null; `review_flags` null|array, each item required keys + `severity`/`category` enums + type checks for `source_evidence`/`user_confirmed`.
- [ ] `role.schema.json`: `active_role` enum `patient`/`caregiver`/`family`.
- [ ] Permissive items #10 left open (empty `source_evidence[]`, null content-keys) stay permissive unless US-006 decides otherwise.

### US-003: Choose & wire the validation engine
**Description:** As a maintainer, I want the validator to run the schema with minimal distribution cost.

**Acceptance Criteria:**
- [ ] Decision recorded (see Open Questions Q1): **(A, recommended)** vendor a tiny stdlib-only Draft-subset validator (~80 LOC, zero deps), or **(B)** depend on `jsonschema` with a graceful "pip install jsonschema" error when absent.
- [ ] If (B): import guarded; absence prints an actionable message, never a traceback.
- [ ] No network access; runs offline.

### US-004: Rewrite `validate-profile-schema.sh` to load schema + run engine + post-checks
**Description:** As a consumer, I want the same CLI to now validate via the schema.

**Acceptance Criteria:**
- [ ] Same usage / exit codes / `ERROR:`-prefixed stderr lines.
- [ ] Loads the three schema files relative to the script dir (robust to CWD).
- [ ] Schema violations and the retained cross-field checks are both reported; all errors collected (not fail-fast), matching current behavior.
- [ ] Non-object top-level / unparseable JSON → clean error, no traceback.

### US-005: Equivalence harness (the gate)
**Description:** As a maintainer, I must prove the rewrite changes no accept/reject decision.

**Acceptance Criteria:**
- [ ] A corpus of ≥30 profiles (the 21 unit cases + real `patients/*/profile.json` fixtures if available, anonymized) is run through **old (git main) and new** validators; every accept/reject decision is identical, diff printed.
- [ ] The 21-case unit suite passes unchanged against the new script.
- [ ] CI job (`unit + integration`) green.
- [ ] Any intentional difference is explicitly listed and approved (expected: none).

### US-006: Reconcile prose doc ↔ schema as single source of truth
**Description:** As a maintainer, I want `patient-profile-schema.md` to point at the schema files as the machine-readable truth.

**Acceptance Criteria:**
- [ ] `patient-profile-schema.md` "Canonical shape" section updated: schema files are the enforced truth; prose describes them.
- [ ] `CHANGELOG.md` `[Unreleased]` entry.
- [ ] No behavior change to downstream skills (they call the same script).

## 4. Functional Requirements

- FR-1: The validator MUST validate `profile.json` against `references/schemas/profile.schema.json`.
- FR-2: It MUST also validate `readiness.json` and `role.json` against their schemas when those files exist.
- FR-3: Cross-field ordering checks for treatment lines (`line` non-decreasing, `start` chronological) belong to the `treatment_lines.json` validator (`validate_structured_outputs.py`), NOT this one — under v3, ordered treatment lines no longer live in `profile.json`. This validator covers profile shape only.
- FR-4: It MUST preserve top-level `additionalProperties: true` (unknown keys ignored) for `profile.json`.
- FR-5: It MUST treat present-but-null on a nullable field as "absent/unknown" (accept) and present-but-null on a required field as invalid (reject) — exactly today's post-#10 behavior.
- FR-6: It MUST exit 0 on valid, non-zero on invalid, and emit `ERROR:`-prefixed lines to stderr; it MUST never emit a Python traceback for any JSON input.
- FR-7: It MUST run offline with no network and (recommendation A) no third-party pip dependency.
- FR-8: The CLI signature `validate-profile-schema.sh <patient_dir>` MUST be unchanged.

## 5. Non-Goals (Out of Scope)

- **No contract/policy changes.** Not tightening empty `source_evidence[]` or null
  `review_flags[]` content-keys here (that is a separate product decision — see #10).
- **Not** touching the per-artifact schemas already WIP in the local tree
  (`comorbidities/labs/molecular/patient_summary/timeline/treatment_lines/missing_items.schema.json`)
  — those serve a different (vmtb structured-output) decomposition; this PRD only
  adds `profile/readiness/role` schemas. Convergence with them is a later question.
- No changes to how downstream skills *call* the validator.
- No migration of `patients/` data on disk.
- No new validation surface (e.g. timeline.md, INDEX.md) beyond the three JSON files validated today.

## 6. Technical Considerations

### Final form
```
scripts/
  validate-profile-schema.sh      # thin: parse args, load schemas, run engine, run cross-field checks, collect errors
  lib/jsonschema_mini.py          # (option A) vendored stdlib-only Draft-subset validator, ~80 LOC
references/schemas/
  profile.schema.json             # NEW — source of truth for profile.json
  readiness.schema.json           # NEW
  role.schema.json                # NEW
  (existing per-artifact *.schema.json — untouched)
tests/unit/
  validate-profile-schema.test.sh # unchanged 21 cases must pass
  validate-equivalence.test.sh    # NEW — old-vs-new decision diff (US-005)
```

### Asset extraction (what we reuse vs write fresh)
- **Reuse:** the 21 unit cases (become the equivalence corpus + traceability table); the prose contract in `patient-profile-schema.md` (becomes the schema's spec); the enum/range/required facts already encoded in the current script (transcribe into schema).
- **Reuse pattern, not files:** the existing local `*.schema.json` show the house style (Draft version, naming) — match it; do not import them.
- **Write fresh:** 3 schema files, the engine wiring, the equivalence harness, the retained cross-field checker.

### Dependency graph
```
validate-profile-schema.sh
 ├─ python3 (stdlib: json, sys, os, datetime)        [already required]
 ├─ references/schemas/profile|readiness|role.schema.json   [new data]
 ├─ engine:
 │   ├─ option A: scripts/lib/jsonschema_mini.py      [vendored, 0 ext deps]   ← recommended
 │   └─ option B: jsonschema (pip)                    [1 ext dep, install step]
 └─ cross-field checker (inline python)               [retained logic from current script]

Consumers (unchanged): cancer-buddy-organize, cancerdao-vmtb, and every sub-skill
that reads readiness.json at entry — all call the script, none import it.
CI: .github workflow `unit + integration (bash + python3)` — must stay green.
```

### Branch strategy
- Single feature branch `feat/declarative-profile-schema` off `main`.
- Atomic commits per US (schema files → engine → rewrite → equivalence harness → doc).
- **One PR**, not phased — per the cross-form-migration rule, a schema/engine swap ships in one move (no half-migrated state where some fields are schema-validated and others still hand-checked). The equivalence harness (US-005) is the merge gate.
- Adapter/benchmark concerns: none; this is product-internal.

### Risks & mitigations
| Risk | Mitigation |
|---|---|
| Silent behavior drift (a profile that passed now fails or vice-versa) | US-005 equivalence harness is a hard merge gate; old-vs-new decision diff must be empty. |
| Regressing `additionalProperties` → rejecting `geo`/`molecular`/etc. | FR-4 + explicit unit case asserting an unknown top-level key still passes. |
| Cross-field rules (date/line ordering) not expressible in stock JSON Schema | Keep them as a post-schema code check (FR-3); schema covers shape, code covers ordering. |
| New pip dependency breaks `npx skills add` installs / CI | Recommendation A (vendored stdlib validator, zero deps). If B chosen, guarded import + actionable error. |
| Schema and prose doc drift again later | US-006 makes schema the cited source of truth; doc references it. |
| Touching founder's uncommitted local schema WIP | Explicit Non-Goal; this PRD adds only profile/readiness/role schemas. |

## 7. Success Metrics

- **Bug-class closure:** adding a future optional nullable field requires editing
  only a `.schema.json` (and maybe a unit case) — zero new imperative guards. (Verified by a worked example in the PR description.)
- **Zero behavior drift:** equivalence harness shows identical decisions on the full corpus.
- **Line delta:** imperative validation logic in the `.sh` drops substantially (≈140 → thin loader + cross-field check), with rules moved into declarative JSON.
- **No new install friction:** (option A) `pip list` for the skill is still empty.

## 8. Open Questions

1. **Engine: vendored stdlib mini-validator (A, recommended) vs `jsonschema` pip dep (B)?**
   A keeps zero-dep distribution but we maintain ~80 LOC of validator; B is battle-tested but adds an install step to a skill shipped via `npx skills add`. **Recommendation: A**, given the skill's zero-dep posture and that we only need a Draft subset (type/enum/required/pattern/const/nullable). Need founder sign-off.
2. **Scope of schemas now:** profile + readiness + role (recommended), or profile only first? Recommendation: all three in one PR — they share the engine and the current script already validates all three.
3. **Converge with the existing local `*.schema.json` set?** They model vmtb structured outputs, not `profile.json`. Recommendation: out of scope here; revisit once these three ship and prove the pattern.
4. **Should the two #10-deferred policy tightenings (empty `source_evidence[]`, null `review_flags[]` content-keys) ride along?** Recommendation: NO — keep this a pure refactor; decide policy separately to keep the equivalence gate meaningful.
