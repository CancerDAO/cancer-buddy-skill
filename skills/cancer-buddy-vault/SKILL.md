---
name: cancer-buddy-vault
description: "Build the patient's N=1 data vault — structured directory, sharing levels (🔒 private → 🔑 authorized → 📊 anonymized-for-AI → 🌐 public), access log. Not cloud storage; it's a local file structure the patient owns, can move, and can share selectively. Triggers on 数据保险箱, N=1, 我的健康档案, 数据分享, data vault."
---

# cancer-buddy-vault

The patient's own public-style cancer data vault — every report, every visit note, every image, organized, searchable, owned by the patient.

## When to use

- Patient asks about organizing their records long-term.
- After 3+ months of treatment when records start piling up.
- Patient says: 数据保险箱 / N=1 / 我的健康档案 / 数据分享.

## Locale

Read [../../references/i18n.md](../../references/i18n.md). Before producing any patient-visible output:

1. Read `patients/<pid>/profile.json` → `locale`. If present, use it — do not re-detect.
2. If absent (no profile, or `locale` is null — vault is entered after organize, so a `locale` is almost always already persisted), detect from the **primary patient-facing language of the records**, tie-breaking to the language the user is conversing in (the `record-consuming generative sub-skills` row in `../../references/i18n.md` §2), then write it back to `profile.json.locale` (BCP-47, e.g. `en` / `zh` / `fr`).
3. Render every patient-visible scaffold string — `vault-manifest.md`, sharing-level labels, confirmation prompts, missing-data reminders, revocation confirmations, breach notices, the public / anonymized case report — in that `locale`.
4. Keep every clinical entity verbatim (drug names, genes/variants, TNM/stage, numbers + units, biomarker labels) regardless of `locale` — never translate, transliterate, or normalize them. Mistranslating a clinical entity is a P0 medical-safety bug.
5. Honor an explicit user language override ("answer me in English" / "用中文") → update `profile.json.locale` and follow it going forward.

## Inputs

- Existing `patients/<pid>/` tree produced by `cancer-buddy-organize`.
- Optional: external health app exports (Apple Health, Google Fit, CGM data, etc.).

## Outputs

Augments `patients/<pid>/`:
- `sharing-settings.json` — per-directory sharing level (JSON keys verbatim; any human-readable `description` / note values rendered in `locale`)
- `access.log` — who accessed what, when (structured fields verbatim; `purpose` free-text in `locale`)
- `vault-manifest.md` — human-readable table of contents, rendered in `locale`
- `exports/` — encrypted bundles ready to share (public / anonymized case report rendered in `locale`)

## Sharing levels

- 🔒 **Private**: patient + immediate family only
- 🔑 **Authorized**: specific clinicians by email/contact (signed URL with expiry)
- 📊 **Anonymized-for-AI**: stripped of PII, hashed patient_id, available for research use
- 🌐 **Public**: de-identified case report, patient consent required

Patient can change level per-file or per-directory anytime. Every change is logged.

## Workflow

See [references/data-vault.md](references/data-vault.md) for the schema and protocol. Resolve `locale` first (see Locale). Main steps:

1. Walk `patients/<pid>/`, classify each artifact by sensitivity.
2. Initialize `sharing-settings.json` — everything starts 🔒 Private unless patient overrides.
3. Generate `vault-manifest.md` — patient-readable TOC, scaffold (section titles, level labels, completeness copy) in `locale`; clinical entities (diagnosis names, drug names, genes, TNM, values + units) verbatim.
4. For each anonymization request, run de-identification (strip name, birthday, MRN, institution, replace dates with intervals-since-diagnosis); the public / anonymized case-report scaffold is rendered in `locale`, clinical entities stay verbatim.
5. Log all access / share / export events to `access.log` (the `purpose` free-text in `locale`).

Scaffold localization: a generative artifact (manifest narrative, missing-data reminder, case report, any confirmation / notice prose) carries the instruction "Output all scaffold/narrative prose in `<locale>`; keep clinical entities verbatim per `../../references/i18n.md` §4." Any fixed label set (sharing-level names/descriptions, manifest section titles, breach-notice headings) is rendered as a `locale → string` lookup, never hardcoded single-language. Heavy LLM judgment (case-report narrative, de-identification) runs via a sub-skill prompt with the locale instruction, not a hardcoded phrase list.

## Safety and privacy

- PII stripping is conservative — err on the side of removing.
- Every share action triggers a confirmation prompt, rendered in `locale` (e.g. `zh`: "你确认要把 [scope] 分享给 [recipient] 级别 [level]?"; `en`: "Confirm sharing [scope] with [recipient] at level [level]?"). `[scope]` / `[recipient]` / `[level]` and any clinical entity inside them stay verbatim.
- Access log is append-only; do not let any other sub-skill modify it.
- Default export format: encrypted zip (password shared out-of-band).

## Role behavior

- **Role = patient**: owner view. Can set any sharing level, export, delete.
  - *Disclosure*: disclosure_state=suppressed + patient → render redacted view (diagnosis fields masked).
- **Role = caregiver**: authorized view. Read+write OK; sharing-level changes require `patients/<patient_code>/role.json.history` confirming patient previously set role=caregiver. Export allowed.
- **Role = family**: 📊 anonymized view only. Name / birthday / MRN stripped, diagnosis-intervals relative to diagnosis date, no free-text notes. Cannot change sharing settings.

## References

- [data-vault.md](references/data-vault.md) — schema, anonymization protocol, sharing flow
- [../../references/i18n.md](../../references/i18n.md) — shared locale layer: detection, persist to `profile.json.locale`, verbatim-clinical policy, scaffold localization
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
