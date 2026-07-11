---
name: cancer-buddy-vault
description: >-
  Manage a patient-controlled local cancer-record vault: inventory files, define intended sharing scopes, preview de-identified exports, create safe local export copies that exclude raw originals, and record user-approved export events. Use when the user asks 数据保险箱、N=1 健康档案、数据分享、脱敏导出、撤销分享、data vault, or wants to understand how to keep and selectively share cancer records. This is not cloud storage, identity verification, remote access control, or proof that a recipient opened a file.
---

# cancer-buddy-vault

Before archive or sharing operations, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md). Urgent help never waits for vault access.

Build truthful local controls around an archive; do not simulate cloud security features that are not implemented.

## Modes and authorization

Read [`authorization-and-consent.md`](../cancer-buddy/references/authorization-and-consent.md) and [`preflight.md`](../cancer-buddy/references/preflight.md).

- Without verified archive authorization, provide stateless privacy/sharing guidance only.
- A self-declared caregiver/family role or `role.json` history is not authorization.
- Every export/share requires a preview manifest and explicit confirmation of recipient, purpose, exact scope, destination, expiry expectations, and limitations.
- Cross-border, research/AI, mental-health, genomic, and minor data each require a separate applicable consent/legal basis. Do not bundle consent.

## Locale

Per [`i18n.md`](../cancer-buddy/references/i18n.md): use host locale, an existing authorized profile locale, or the conversation language in that order. Do not create/modify a clinical profile merely to save language. Only the scaffold (labels, prose, notices) is localized — **clinical entities stay verbatim, never translated** (drug names, genes/variants, TNM/stage, numbers + units, biomarker labels); a verified normalized term may appear beside the source with provenance.

## Inputs

- An authorized `patients/{patient_code}/` archive produced by `cancer-buddy-organize`; or
- No archive, for a general privacy/export plan.

## Truthful outputs

When authorized and explicitly requested, create only:

- `vault-manifest.md` — local table of contents and sensitivity labels.
- `sharing-plan.json` — intended recipient/scope/expiry plan; it does not itself enforce access.
- `export-ledger.jsonl` — append-only record of exports this tool actually created or revoked locally. It cannot prove recipient views.
- A fresh safe-share export produced by the organizer's `export_share.py`, after its validation gate, excluding `raw/`, historical snapshots, identity maps, and other non-shareable artifacts.

Do not claim to create signed URLs, authenticate clinicians, send email, log remote access, revoke a file already copied elsewhere, or provide cloud storage unless a separately installed and user-authorized system actually implements and verifies those capabilities.

## Trust by inspection

A skeptical user should be able to verify the privacy claims themselves, not take them on faith. When they doubt "文件真的在我这里 / 你们没偷偷上传"，surface these three concrete, available-now checks (offer them plainly, in the user's language):

- **Look at the raw files yourself, right now.** Give the exact local path (e.g. `patients/<你的编号>/`) and tell them to open it in their own 文件管理器 / Finder / `ls` — every record is a plain file on their own disk, readable without this skill. Nothing is hidden inside a proprietary blob.
- **Export a copy to your own folder — available now.** Alongside the manifest and delete actions, offer "把一份副本导出到你自己的文件夹" as a present, do-it-now owner operation, not a future consent-gated promise. This is the owner keeping their own backup (no external recipient, so no recipient/cross-border consent gate); still show the file list before writing, and let them pick the destination folder. Personal backups to a folder the owner controls may include originals — only third-party shares strip `raw/`.
- **Confirm it makes no outbound call.** Tell a technical user how to check the "本地、不在我们云上" claim rather than just asserting it: this skill reads and writes only local files under the archive path and calls no network API; they can watch for themselves with a network monitor (e.g. Little Snitch / `lsof -i` / a firewall log) while it runs and see zero outbound connection. If any component ever needs the network, it must say so first.

Never overstate: verification shows what this skill does locally; it is not a security audit of the wider device or OS.

## Workflow

1. Verify authorization and the requested operation scope.
2. Read only the minimum required archive inventory; never read `raw/` to build a share export.
3. Produce a preview manifest showing every included/excluded file and residual re-identification risks.
4. Run the organizer validation and safe-export script via absolute paths resolved from the installed `cancer-buddy-organize` skill.
5. Ask for explicit confirmation immediately before writing the export. For public/research/cross-border use, ask a separate consent question and recommend appropriate privacy/legal review.
6. Write the local export ledger entry. Explain that deletion/revocation can remove local copies/permissions only; it cannot recall copies already received.

## De-identification limits

- De-identified is not anonymous. Rare cancer, genomic features, dates, hospitals, geography, or an unusual treatment sequence may re-identify someone.
- Default to removing direct identifiers, exact dates when unnecessary, free-text notes, institution/location details, small-cell combinations, and raw images. Preserve clinical utility only to the minimum needed for the stated purpose.
- Never say “no re-identification possible.”
- Never use patient data for model training, federated learning, research, or public release without separate, explicit consent and an actual governed recipient/process.

## Role behavior

- **Role = patient**: owner operations only after verified authorization and action-specific consent.
- **Role = caregiver**: only the exact read/export/share scope granted by the patient or verified legal authority.
- **Role = family**: stateless privacy guidance by default; no automatic “anonymized view.”

## Disclosure

Per [`disclosure-behavior.md`](../cancer-buddy/references/disclosure-behavior.md): `disclosure_state` is a communication-planning hint, not access control — it never hides an authorized, decision-capable adult patient's own archive. Every export/share requires explicit **scope-specific consent** (recipient, purpose, exact scope, destination) confirmed at export time; **never infer** consent from `disclosure_state`, and never reveal to an unauthorized person whether an archive exists.

## Safety

- Silence is not consent. Permanent deletion requires explicit itemized confirmation and should use recoverable trash/quarantine when possible.
- Never put passwords in chat, filenames, command history, or the same channel as an encrypted archive. Encryption is optional and may be claimed only after a supported tool actually creates and verifies it.
- This skill helps implement local privacy hygiene; it does not certify PIPL, HIPAA, GDPR, HGR, or other legal compliance.

## References

- [data-vault.md](references/data-vault.md) — local manifest/export schemas and legal cautions
- [authorization-and-consent.md](../cancer-buddy/references/authorization-and-consent.md)
- [patient-profile-schema.md](../cancer-buddy/references/patient-profile-schema.md)
- [safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md)
