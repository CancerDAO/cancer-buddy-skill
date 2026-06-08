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

1. **Unconfirmed input never touches a formal field.** `profile.json`, `timeline.md`, `timeline.json`, `case_text.md`, `readiness.json`, and the structured JSONs are not written from a candidate the user has not explicitly confirmed. The diff card + explicit confirmation is the only thing that opens the write.
2. **Silence / deferral / "随便" / closing the chat = no-confirm** for *write* candidates → write nothing for that candidate. (The one exception where silence triggers an *action* is the irreversible-delete sub-rule below, and only on its high-confidence branch.)
3. **Never fabricate a precise value the user did not give.** If a candidate is genuinely ambiguous on a critical field (stage / molecular driver / line of therapy), ask one clarifying question *in the card* rather than guessing.
4. **Critical-field changes are never a fait accompli.** A change to stage / molecular driver / line of therapy must be explicitly confirmed — never presented as already done.
5. **Never silently overwrite a contradicting value.** When a candidate conflicts with an existing record-sourced value, surface *both* in the card and let the user decide; do not overwrite the record value without explicit confirmation.
6. **Detecting / classifying candidates is an LLM judgment task** — read each input in context (against the existing `profile.json` / `timeline.md` / bucket sidecars); do **not** run a hardcoded keyword list or a Python same-name/same-date comparator. Hand the judgment to a subagent / the LLM.
7. **`profile.json.alias` is sticky** — no gated run rewrites it. No gated run rewrites `case_text.md` / `readiness.json` / the structured JSONs beyond the specific confirmed field/row.

## Irreversible-delete sub-rule (load-bearing asymmetry)

When the gated decision is not "write a field" but "delete a file we don't archive," confirmation is asymmetric by confidence. This asymmetry is load-bearing — flattening it either keeps junk forever or deletes real records:

- **High-confidence non-medical, no-confirm ⇒ delete.** A file confidently judged non-medical (风景照 / 自拍 / 餐食 / 无关聊天截图 / 广告 / 纯生活收据 / 误拍…) is isolated, never archived, and **deleted on silence/deferral/no-claim**. Silence ⇒ delete is *by design* (privacy floor: we do not retain a patient's raw unrelated files), not a bug.
- **Borderline (`relevance_uncertain`), no-confirm ⇒ hold, never auto-delete.** A file that *might* be a real medical record is **held** until the user *explicitly* says 删/留. Silence does **NOT** delete it. Deleting something that might be a real medical record is the worse error, so the borderline batch is the explicit exception to "silence resolves."

The calibration bar between the two: the high-confidence (auto-deletable) class is "I would bet money this has no clinical value." Anything short of that bar is borderline, because the high-confidence bucket is the one silence deletes and that deletion is irreversible.

The user MUST be told *before* any deletion that we do not keep raw unrelated files and that silence ⇒ delete (the mandatory disposition-notice sentence, defined verbatim per-locale in 段E). The full red-line lives in [`safety-guardrails.md`](safety-guardrails.md) (段E carve-out); 段E's `relevance-gate.md` is the operational logic. This sub-rule is the shared statement of the asymmetry both cite.

> Note: archive-don't-delete actions (段C/upload-reconciliation supersede → `_superseded_<ts>/`, conflict → coexist) are **not** deletions and introduce no auto-delete. The only auto-delete in the whole gate is the high-confidence non-medical branch above.

## Diff card presentation (universal)

Every gated decision is presented as one compact, plain-language diff card before anything is written or deleted. One card per run, listing all candidates:

- Show `current_value → proposed_value` for a field change; show the full new line for a timeline row; show "isolated as X — <one-line reason>" for a relevance/delete candidate.
- Quote the user's own words (conversation) or give a checkable basis (检查名 / 日期 / 机构 / 矛盾字段) as the `依据` / `evidence`.
- Mark `low`-confidence candidates plainly and offer a correction / opt-out action ("改一下" / "先不写" / "先忽略") so the user can fix a value rather than accept a guess.
- Never render a critical-field change, or a "已替换/已删除", as already done.
- Conflicts present **both** facts side by side, flagged ⚠️, and never as a settled overwrite.

**Rendering is runtime-neutral:** both an **inline diff card** (the Claude Code binding — user resolves it in the same turn) and **confirm-as-product** (a headless host emits the same candidate data as an artifact for its own UI to ask the user about after the fact, then re-feeds the decision) are compliant. The gate contract is unchanged either way — the items above (current→proposed, checkable basis, low-confidence opt-out, never-a-fait-accompli, conflicts side by side) and the irreversible-delete asymmetry hold identically regardless of who renders the card. See [`../skills/cancer-buddy-organize/references/organize-contract.md`](../skills/cancer-buddy-organize/references/organize-contract.md) §3 / §6「确认门」seam.

**Locale (i18n):** the diff card is patient-facing scaffold → render the whole card in `profile.json.locale` (detect / persist per [`i18n.md`](i18n.md)). The `zh` wording in each caller's doc is the source string table; render the localized equivalent at output time (`i18n.md` §5). **Clinical entities inside the card stay verbatim** — drug names, gene symbols, variants, TNM/stage strings, numbers + units — per [`safety-guardrails.md`](safety-guardrails.md) "Clinical entities are never translated (P0)" and `i18n.md` §4. On-disk bucket slugs in the card follow the localized slug actually on disk (`i18n.md` §6). The privacy-floor sentence in the delete path is mandatory in **every** locale with no softening.

## Provenance — record every gated action in `update_log.json`

Every gated run appends one entry to `update_log.json` so confirmed writes and irreversible deletions are auditable. The entry carries:

- `run_mode` — the caller's mode (`conversation_incremental` | `upload_reconciliation` | `full` | …).
- `ts` — ISO-8601 of the triggering turn / upload.
- `triggered_by` — `actor_role`.
- the gated outcomes — confirmed field(s) / row(s) written, candidates deferred, and (for the delete sub-rule) the `relevance` block whose `auto_deleted[]` array is the **irreversible-action ledger** (every entry was a high-confidence non-medical file deleted on no-claim), plus `held_uncertain[]` carrying borderline files forward still flagged.

Each caller's doc specifies the exact field set for its `run_mode`; the requirement here is that **no gated write or delete happens without a matching `update_log.json` entry**. Provenance on the written field itself uses the source-appropriate anchor (conversation anchor for 段C, file anchor for a file-sourced write — see each caller's doc and [`../skills/cancer-buddy-organize/references/schemas/anchor-contract.md`](../skills/cancer-buddy-organize/references/schemas/anchor-contract.md)).

## What stays in the caller's doc

This document owns the **gate** — the confirmation floor, the diff-card contract, the delete asymmetry, the `update_log.json` requirement. Each caller keeps its own **specialization**: 段E's three relevance classes and `99_无关文件/` semantics; 段C's archivable-fact categories and conversation anchor; upload-reconciliation's new/supersede/conflict relations and `_superseded_<ts>/` mechanics. When a caller's gate behavior would differ from this doc, that is rule drift — fix it here or fix the caller, do not fork the gate.
