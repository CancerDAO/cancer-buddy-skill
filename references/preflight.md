# Patient-directory preflight

Apply before any sub-skill reads or writes a patient directory. This is an authorization and source-fidelity
gate, not a clinical-readiness score.

## 1. Viewer and authority

- Resolve the authenticated viewer through the host. `role.json` describes interaction role but does not
  grant access.
- Patient: access to their own information after host authentication.
- Caregiver/family: require explicit, purpose-limited, time-bounded authorization for the requested records
  and action. Relationship alone is insufficient.
- Writes, exports and external sharing require a fresh scope/recipient confirmation and optimistic concurrency
  check. Preserve both versions on conflict.

Without authorization, continue only with general information that does not expose patient-specific data.

## 2. Disclosure preference

Read `profile.disclosure_state` as a communication preference, not an ACL or capacity decision. Avoid
unexpected disclosure in an unrelated request. A capable patient's explicit request for their own information
is not overridden by a family-set flag. An unauthorized viewer still receives no patient-specific information.
For capacity, proxy or legal disputes, pause the disputed disclosure and route to the treating institution.
See `disclosure-behavior.md`.

## 3. Documentation coverage

- Missing `readiness.json`: offer record organization, but continue stable general education or question
  preparation.
- `documentation_coverage` describes whether an existing document is present, absent from the archive or
  unknown. It is not a probability, grade, diagnostic confidence, quality score or permission to act.
- `missing_items.json` is an existing-document inventory. Never turn an inventory gap into a recommendation
  to order a test.

## 4. Source/faithfulness flags

For every field the task would use, check unresolved `readiness.json.review_flags[]` and the field's provenance.

- An unresolved flag prevents only that affected field from being shown as settled fact.
- Show all conflicting source values and their anchors; do not select a winner by recency, source type, model
  judgment or patient override.
- A patient/caregiver may add a separate reported statement, but this does not resolve a clinician-source
  conflict.
- Resolution requires a corrected source, authorized clinician attestation or documented administrative
  provenance repair. The original value and anchor remain in history.
- Unaffected organization, education and question preparation may proceed with the limitation stated.

## 5. Schema and urgency

Run the applicable schema/anchor validators before relying on structured fields. Corrupt JSON or dangling
sources block the affected artifact, not all support.

If the current user message contains an acute dangerous symptom or a source carries an explicit critical-value
instruction, apply `safety-guardrails.md` first. Preflight and record completion must not delay urgent care.
