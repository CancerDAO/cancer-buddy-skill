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

- Missing `readiness.json`: offer record organization, but continue general / conditional education
  (answer-time sourced) or question preparation. Missing case data limits only individual-case
  conclusions, not general education. (Source-lookup *failure* is the separate case that falls back to
  concept-only with no regimen/line names — see `safety-guardrails.md` §Live external lookup.)
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
- A field with an unconfirmed `document_intent` flag (`resolution_status: unresolved`) or containing an
  `[OCR_UNCERTAIN:U-nnn]` token is never a premise for staging, pathology or treatment reasoning, and never
  spawns an alternative-stage or alternative-diagnosis scenario. Lexicon candidates are possible readings,
  not values; a `labs.json` `candidate_value` (with `value: null`) is an unverified position-paired reading,
  not a measured result.
- `provenance_layer: prior_archive` facts (a user-authorized digest of an earlier archive, original not in
  this archive) are history only — never current status, the current regimen or the basis of a
  recommendation — and are labeled as such when cited.
- Current treatment is stated with its recorded basis (`profile.json.latest_status.status_basis`, copied from
  the ongoing episode): an imaging-request indication (`order_or_indication_only`) or a family statement
  (`patient_reported`; undated when `status_as_of_precision` is `undated_self_report`) is neither upgraded to an
  administration record nor denied — say what the source says and that the treating team confirms it.
- A review flag's `severity` (`red|yellow|info`) grades extraction / archive-completeness uncertainty, not
  clinical severity. `red` means only that the affected field may not be presented as settled fact; it says
  nothing about how ill the patient is.
- Unaffected organization, education and question preparation may proceed with the limitation stated.

## 5. Schema and urgency

Run the applicable schema/anchor validators before relying on structured fields — a reader that is not the
organize run itself calls `validate_structured_outputs.py <patient_dir> --readonly`, which never writes into the
archive. Corrupt JSON or dangling sources block the affected artifact, not all support.

If the current user message contains an acute dangerous symptom, a source carries an explicit critical-value
instruction, or `acute_findings.json` holds `emergent`/`urgent` rows, apply `safety-guardrails.md` first (Urgent
physical symptoms): quote the source-worded finding with its date and suggest telling the treating team soon,
without explaining cause or grading severity. A missing `acute_findings.json` means "not checked", never
"none found". Preflight and record completion must not delay urgent care.
