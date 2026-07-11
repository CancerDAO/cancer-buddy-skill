# Confirm Gate — Shared "Nothing Formal Without Confirmation" Rule

Every companion sub-skill that proposes to change a patient's archived record — a `profile.json` field, a `timeline.md` / `timeline.json` row, a structured JSON, or the keep/delete fate of a file — passes through **one** gate before anything is written or irreversibly removed: the user sees a plain-language **diff card** and explicitly confirms. This document is the single authority for that gate. Callers cite it; they do not re-define it.

The reason the gate is shared and not re-implemented per skill: a confirmation rule that drifts is worse than no rule. A patient mis-speaking ("我好像是三期吧?"), a stray screenshot in an upload folder, a re-uploaded photo that contradicts the record — each must hit the *same* "I won't write/delete until you confirm" floor, so no sub-skill quietly poisons a downstream report or deletes a real record.

## Scope — who cites this

This gate governs any companion run that would write a *formal* artifact or *irreversibly* remove a file. Current callers and their skill-specific specialization (which stays in their own doc):

| caller | trigger source | skill-specific specialization (NOT defined here) |
|---|---|---|
| `cancer-buddy-organize` 段C — [`conversation-incremental-prompt.md`](../../cancer-buddy-organize/references/conversation-incremental-prompt.md) | a fact surfaces in conversation | the 5 archivable-fact categories, the conversation anchor, `patient_curated` tagging |
| `cancer-buddy-organize` 段E — [`relevance-gate.md`](../../cancer-buddy-organize/references/relevance-gate.md) | a file's medical-relevance is triaged | the 3 relevance classes (medical / high-confidence non-medical / borderline), quarantine, and explicit disposition choices |
| `cancer-buddy-organize` upload-reconciliation — [`upload-reconciliation.md`](../../cancer-buddy-organize/references/upload-reconciliation.md) | a file is re-uploaded onto an existing archive | the 3 relations (new / supersede / conflict), `_superseded_<ts>/` archive-don't-delete |
| any companion that asks before writing a confirmed `profile.json` / timeline field | — | its own field set |

## The gate (universal)

1. **Unconfirmed input never touches a formal field.** `profile.json`, `timeline.md`, `timeline.json`, `case_text.md`, `readiness.json`, and the structured JSONs are not written from a candidate the user has not explicitly confirmed. The diff card + explicit confirmation is the only thing that opens the write.
2. **Silence / deferral / "随便" / closing the chat = no-confirm** for writes and destructive actions. Write nothing and permanently delete nothing for that candidate.
3. **Never fabricate a precise value the user did not give.** If a candidate is genuinely ambiguous on a critical field (stage / molecular driver / line of therapy), ask one clarifying question *in the card* rather than guessing.
4. **Critical-field changes are never a fait accompli.** A change to stage / molecular driver / line of therapy must be explicitly confirmed — never presented as already done.
5. **Never silently overwrite a contradicting value.** When a candidate conflicts with an existing record-sourced value, surface *both* in the card and let the user decide; do not overwrite the record value without explicit confirmation.
6. **Detecting / classifying candidates is an LLM judgment task** — read each input in context (against the existing `profile.json` / `timeline.md` / bucket sidecars); do **not** run a hardcoded keyword list or a Python same-name/same-date comparator. Hand the judgment to a subagent / the LLM.
7. **`profile.json.alias` is sticky** — no gated run rewrites it. No gated run rewrites `case_text.md` / `readiness.json` / the structured JSONs beyond the specific confirmed field/row.

## Destructive-action rule

Never treat confidence, silence, a closed chat, or "随便" as permission to permanently delete a user file.

- Classify candidate non-medical files in an agent-created staging area **before** copying them into the canonical archive. Do not place them in `raw/` first.
- For a high-confidence non-medical candidate, offer `删除临时副本` / `保留在原位置但不归档` / `这是病历，重新分类`. No reply means: do not archive it, preserve the user-supplied source, and clean up only agent-created temporary copies after verifying the source still exists.
- For a borderline candidate, hold it in a recoverable quarantine and ask the user to keep or exclude it. No reply means hold; never delete.
- Permanently deleting a user-supplied source or the only remaining copy always requires an explicit, itemized confirmation immediately before deletion. Prefer recoverable trash/quarantine when the host supports it.

Archive-don't-delete actions (supersede → `_superseded_<ts>/`, conflict → coexist) are not destructive and remain allowed after the normal diff-card confirmation.

## Diff card presentation (universal)

Every gated decision is presented as one compact, plain-language diff card before anything is written or deleted. One card per run, listing all candidates:

- Show `current_value → proposed_value` for a field change; show the full new line for a timeline row; show "isolated as X — <one-line reason>" for a relevance/delete candidate.
- Quote the user's own words (conversation) or give a checkable basis (检查名 / 日期 / 机构 / 矛盾字段) as the `依据` / `evidence`.
- Mark `low`-confidence candidates plainly and offer a correction / opt-out action ("改一下" / "先不写" / "先忽略") so the user can fix a value rather than accept a guess.
- Never render a critical-field change, or a "已替换/已删除", as already done.
- Conflicts present **both** facts side by side, flagged ⚠️, and never as a settled overwrite.

**Rendering is runtime-neutral:** both an inline diff card and a host UI confirmation are compliant. The gate contract is unchanged either way. See [`organize-contract.md`](../../cancer-buddy-organize/references/organize-contract.md) §3 / §6「确认门」seam.

**Locale (i18n):** render the diff card in the active locale per [`i18n.md`](i18n.md). Keep clinical entities verbatim and show any verified normalized term beside—not instead of—the source term. The destructive-action warning must clearly say that no permanent deletion occurs without explicit confirmation.

## Provenance — record every gated action in `update_log.json`

Every gated run appends one entry to `update_log.json` so confirmed writes and irreversible deletions are auditable. The entry carries:

- `run_mode` — the caller's mode (`conversation_incremental` | `upload_reconciliation` | `full` | …).
- `ts` — ISO-8601 of the triggering turn / upload.
- `triggered_by` — `actor_role`.
- the gated outcomes — confirmed field(s) / row(s) written, candidates deferred, excluded-but-source-preserved files, explicitly confirmed deletions, and held uncertain files.

Each caller's doc specifies the exact field set for its `run_mode`; the requirement here is that **no gated write or confirmed deletion happens without a matching `update_log.json` entry**. See [`anchor-contract.md`](../../cancer-buddy-organize/references/schemas/anchor-contract.md).

## What stays in the caller's doc

This document owns the **gate** — the confirmation floor, diff-card contract, destructive-action rule, and `update_log.json` requirement. Each caller keeps its own specialization. When a caller differs, fix the drift; do not fork the gate.
