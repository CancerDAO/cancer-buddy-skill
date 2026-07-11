# Archive Preflight

Use this only when a workflow intends to read or modify an existing patient directory. General support never requires an archive.

## 0. Safety first

Run [`medical-emergency-gate.md`](medical-emergency-gate.md) and the suicide-safety rule before role, authorization, or readiness checks.

## 1. Choose operating mode

- If the request can be answered generally, start in **stateless/general mode** and offer archive personalization as an optional enhancement.
- If the user explicitly asks to use an archive, apply [`authorization-and-consent.md`](authorization-and-consent.md). Conversation role is tone only. Without a verified, in-scope grant, do not reveal whether an archive exists; stay in stateless mode.
- An export, share, cross-border transfer, research/AI use, raw-record collection, or destructive action requires separate explicit consent immediately before the action.

## 2. Disclosure

Treat a missing disclosure field as `unknown`, not `full`. `disclosure_state` helps plan a family conversation; it is not access control and cannot hide an authorized competent adult's own archive. Do not let an unverified caregiver set or use it to censor the patient. Capacity or representative authority must be established by the relevant clinical/legal process, not by this skill.

## 3. Readiness for archive-dependent claims

- Missing `readiness.json` or grade D/F does **not** block general help. Explain that personalization is limited and offer a general checklist or answer.
- For an artifact that materially depends on archive facts, read only the relevant domain. If a required field is missing, state exactly what is unknown, avoid guessing, and offer `cancer-buddy-organize` as an optional next step.
- Grades A/B/C permit use of available fields but never override field-level uncertainty or source conflicts.

## 4. Review flags

Before using a field, inspect relevant red `review_flags`. An unresolved red flag on a field needed for this task blocks **that field-dependent portion**, not unrelated general help.

Show a compact diff card with the current value, concern, evidence, and choices. Do not update the profile from the consuming skill. Send an explicitly confirmed correction back through the canonical organizer/writer and log it. If the user chooses to proceed with the current value, label the artifact as based on an unresolved/overridden value; never describe it as verified.

Yellow/green flags do not block but should be surfaced when relevant.

## 5. Schema and source validity

Use the organizer's validators via absolute paths resolved from the installed skill directory. Corrupt JSON, missing source anchors, or a required schema failure blocks only the personalized artifact that depends on it. Continue to offer safe stateless help.
