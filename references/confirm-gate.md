# Confirm Gate — Shared "Nothing Formal Without Confirmation" Rule

Every companion sub-skill that proposes to change a patient's archived record — a `profile.json` field, a `timeline.md` / `timeline.json` row, a structured JSON, or the keep/delete fate of a file — passes through **one** gate before anything is written or irreversibly removed: the user sees a plain-language **diff card** and explicitly confirms. This document is the single authority for that gate. Callers cite it; they do not re-define it.

The reason the gate is shared and not re-implemented per skill: a confirmation rule that drifts is worse than no rule. A patient mis-speaking ("我好像是三期吧?"), a stray screenshot in an upload folder, a re-uploaded photo that contradicts the record — each must hit the *same* "I won't write/delete until you confirm" floor, so no sub-skill quietly poisons a downstream report or deletes a real record.

## Scope — who cites this

This gate governs any companion run that would write a *formal* artifact or *irreversibly* remove a file. Current callers and their skill-specific specialization (which stays in their own doc):

| caller | trigger source | skill-specific specialization (NOT defined here) |
|---|---|---|
| `cancer-buddy-organize` 段C — [`../skills/cancer-buddy-organize/references/conversation-incremental-prompt.md`](../skills/cancer-buddy-organize/references/conversation-incremental-prompt.md) | a fact surfaces in conversation | the 5 archivable-fact categories, the conversation anchor, `patient_curated` tagging |
| `cancer-buddy-organize` 段E — [`../skills/cancer-buddy-organize/references/relevance-gate.md`](../skills/cancer-buddy-organize/references/relevance-gate.md) | a file's medical-relevance is triaged | the 3 relevance classes (medical / high-confidence non-medical / borderline), `99_无关文件/` quarantine, the irreversible-delete sub-rule below |
| `cancer-buddy-organize` upload-reconciliation — [`../skills/cancer-buddy-organize/references/upload-reconciliation.md`](../skills/cancer-buddy-organize/references/upload-reconciliation.md) | a file is re-uploaded onto an existing archive | the 3 relations (new / supersede / conflict), `_superseded_<ts>/` archive-don't-delete |
| any companion that asks before writing a confirmed `profile.json` / timeline field | — | its own field set |

## The gate (universal)

1. **Unconfirmed input never touches a formal field.** `profile.json`, `timeline.md`, `timeline.json`, `case_text.md`, `readiness.json`, and the structured JSONs are not written from a candidate the user has not explicitly confirmed.
2. **Confirmation controls archiving, not clinical truth.** A confirmed patient or caregiver statement is stored as `patient_reported`/`caregiver_reported` with speaker, timestamp, and conversation anchor. It never overwrites or becomes equivalent to `source_reported` or `clinician_verified`.
3. **Silence / deferral / "随便" / closing the chat = no-confirm** for writes and deletions → take no irreversible action.
4. **Never fabricate a precise value the user did not give.** If a candidate is genuinely ambiguous on a critical field (stage / molecular driver / line of therapy), ask one clarifying question *in the card* rather than guessing.
5. **Critical-field changes are never a fait accompli.** Stage, ECOG, molecular results, laboratory values, treatment line, or response may enter the clinician/source layer only from a source document or authorized clinician attestation.
6. **Never resolve a clinical conflict by user choice.** Preserve both values, their provenance, and `status: disputed`. Only an amended source document or authorized clinician attestation may resolve the canonical clinical field.
7. **Candidate classification is contextual and auditable.** Deterministic filename/date/hash comparisons may supply evidence, but no keyword or same-name/same-date rule may silently adjudicate a clinical conflict or overwrite a record. Preserve the basis for the proposed relation and show it in the diff card.
8. **`profile.json.alias` is optional and user-controlled** — a clinical extraction never generates or rewrites
   it. It must remain non-clinical and non-identifying. No gated run rewrites `case_text.md` /
   `readiness.json` / the structured JSONs beyond the specific confirmed field/row.

## Irreversible-delete sub-rule

No file is deleted on model confidence or user silence. Quarantine suspected non-medical files and show an
item-specific preview. Delete only after explicit confirmation that explains irreversibility. Medical,
medication, symptom, wound, device, billing, and borderline files default to hold. Superseded clinical
records remain archived with version and provenance.

## Diff card presentation (universal)

Every gated decision is presented as one compact, plain-language diff card before anything is written or deleted. One card per run, listing all candidates:

- Show `current_value → proposed_value` for a field change; show the full new line for a timeline row; show "isolated as X — <one-line reason>" for a relevance/delete candidate.
- Quote the user's own words (conversation) or give a checkable basis (检查名 / 日期 / 机构 / 矛盾字段) as the `依据` / `evidence`.
- Mark `low`-confidence candidates plainly and offer a correction / opt-out action ("改一下" / "先不写" / "先忽略") so the user can fix a value rather than accept a guess.
- Never render a critical-field change, or a "已替换/已删除", as already done.
- Conflicts present **both** facts side by side, flagged ⚠️, with source layer and resolution status; the card cannot offer a patient action that promotes one value to clinician-verified truth.

**Rendering is runtime-neutral:** both an **inline diff card** (the Claude Code binding — user resolves it in the same turn) and **confirm-as-product** (a headless host emits the same candidate data as an artifact for its own UI to ask the user about after the fact, then re-feeds the decision) are compliant. The gate contract is unchanged either way — the items above (current→proposed, checkable basis, low-confidence opt-out, never-a-fait-accompli, conflicts side by side) and the irreversible-delete asymmetry hold identically regardless of who renders the card. See [`../skills/cancer-buddy-organize/references/organize-contract.md`](../skills/cancer-buddy-organize/references/organize-contract.md) §3 / §6「确认门」seam.

**Locale (i18n):** render the diff card in the resolved locale. Keep the source clinical string visible; any normalization or translation is additive, labeled and reviewable under [`i18n.md`](i18n.md) §4. On-disk bucket slugs follow the actual stored path. The privacy-floor sentence in the delete path is mandatory in every locale.

## Provenance — record every gated action in `update_log.json`

Every gated run appends one entry to `update_log.json` so confirmed writes and irreversible deletions are auditable. The entry carries:

- `run_mode` — the caller's mode (`conversation_incremental` | `upload_reconciliation` | `full` | …).
- `ts` — ISO-8601 of the triggering turn / upload.
- `triggered_by` — `actor_role`.
- the gated outcomes — confirmed field(s) / row(s) written with provenance layer, candidates deferred, explicitly confirmed deletions in an irreversible-action ledger, and quarantined files carried forward.

Each caller's doc specifies the exact field set for its `run_mode`; the requirement here is that **no gated write or delete happens without a matching `update_log.json` entry**. Provenance on the written field itself uses the source-appropriate anchor (conversation anchor for 段C, file anchor for a file-sourced write — see each caller's doc and [`../skills/cancer-buddy-organize/references/schemas/anchor-contract.md`](../skills/cancer-buddy-organize/references/schemas/anchor-contract.md)).

## What stays in the caller's doc

This document owns the **gate** — the confirmation floor, the diff-card contract, the delete asymmetry, the `update_log.json` requirement. Each caller keeps its own **specialization**: 段E's three relevance classes and `99_无关文件/` semantics; 段C's archivable-fact categories and conversation anchor; upload-reconciliation's new/supersede/conflict relations and `_superseded_<ts>/` mechanics. When a caller's gate behavior would differ from this doc, that is rule drift — fix it here or fix the caller, do not fork the gate.
