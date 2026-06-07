# visit-prep — HTML assembly prompt

Fill `templates/visit-prep.template.html` from the patient's structured JSON. This skill **only assembles existing data and organizes questions** — it never recommends treatment, never interprets a result, never makes a clinical judgment, never ranks treatment options. See `../../../references/safety-guardrails.md`.

## 0. Read-only, de-identified sources

Read these from `patients/<pid>/` (all already produced by organize; read-only — visit-prep writes no formal field, touches no confirm-gate):

- `profile.json` — `locale`, `primary_cancer`, `histology`, `stage`, `molecular_drivers_known`, `current_therapy`, `demographics`, `data_sources`.
- `readiness.json` — `review_flags[]` (each: `field_path`, `current_value`, `issue`, `suggested_value`, `severity`, `user_confirmed`), `blocking_gaps[]`.
- `molecular.json` — `variants[]`, `ihc[]`, `msi_mmr`, `tmb`.
- `treatment_lines.json` — `lines[]` (`line`, `regimen`, `intent`, `started_at`, `ended_at`, `best_response`, `reason_for_change`).
- `labs.json` — `panels[]` (`analyte`, `unit`, `reference_range`, `values[]` with `date`/`value`/`flag`).
- `timeline.json` (or `timeline.md`) — `events[]` (`date`, `category`, `title`, `detail`).
- `missing_items.json` — `missing[]` (`item`, `priority`, `reason`, `category`).

Never read `10_原始文件/` or any non-de-identified source. If a file is absent, treat its fields as missing (render the locale `val_pending` string) — do not fabricate.

## 1. Locale

Read `profile.json.locale` first; if present use it, do not re-detect (visit-prep runs after organize). If absent, detect from the records' primary patient-facing language per `../../../references/i18n.md` §2 and write it back to `profile.json.locale`.

Fill every `{{i18n.<key>}}` placeholder from the template's locale string table for that `locale` (the `<html lang>` and `{{i18n.html_lang}}` follow it too). For a locale not in the table, generate equivalents in the target language — same meaning, same tone. **Keep every clinical entity verbatim** regardless of locale (drug names, genes/variants, TNM/stage, RECIST codes, numbers + units, biomarker labels) — `../../../references/i18n.md` §4; mistranslating one is a P0 safety bug (`../../../references/safety-guardrails.md`).

## 2. visit_type

`visit_type` ∈ {`first` 初诊, `followup` 复诊, `switch` 换线决策}. If the caller passed it, use it. If not detectable from context, ask the user one short question and wait. Fill `{{visit_type_label}}` from the matching locale string (`vt_first` / `vt_followup` / `vt_switch`). Block 4 (上次→这次变化) renders **only when `visit_type == followup`** — otherwise drop the whole `RENDER_IF visit_type == followup … END RENDER_IF` span.

## 3. Block 1 — 医生速览 (direct field mapping, clinical entities verbatim)

Map structured fields straight into the snapshot, verbatim — no interpretation:

| placeholder | source |
|---|---|
| `{{one_line_condition}}` | one-sentence condition line from `profile.json` (`primary_cancer` + `histology` + `stage` + headline driver), e.g. `非小细胞肺癌 腺癌 IIIA (cT3N2M0)，EGFR L858R`. |
| `{{snapshot_diagnosis}}` | `primary_cancer` / `histology` / `stage` joined verbatim. |
| `{{snapshot_molecular}}` | from `molecular.json`: variants (`gene` + `variant`), `msi_mmr.status`, key `ihc[]`, `tmb` — verbatim, comma-joined. |
| `{{snapshot_current_line}}` | current line from `treatment_lines.json` (latest line with no `ended_at`, or `profile.current_therapy`): `regimen` + line number, verbatim. |
| `{{snapshot_key_labs}}` | from `labs.json`: latest value of each panel whose newest value has `flag` ∈ {H, L, HH, LL}, as `analyte value unit (date)` verbatim. |

Any source field null/absent → render the locale `val_pending` string for that cell. Never fabricate a value.

## 4. Block 2 — 我要问医生的 (subagent-derived; do NOT hardcode a keyword list)

This is the core block and is **LLM-derived by a subagent**, not a hardcoded keyword/phrase table. Dispatch a subagent with the four source arrays + the patient's `visit_type` and the question scaffolds in `question-frameworks.md`. The subagent returns four question groups; you only fill the template loops.

Subagent instructions:

> You are drafting questions a cancer patient will ask their own doctor. You produce **questions only** — never an answer, never a recommendation, never a treatment ranking, never a clinical interpretation. Output all prose in `<locale>`; keep every clinical entity verbatim (drug names / genes / variants / TNM / numbers+units). Return JSON with four arrays.
>
> **`confirm_questions`** — one per `readiness.json.review_flags[]` entry (regardless of `severity` / `user_confirmed`). Each is phrased strictly as a **request for the doctor to confirm**, never as an assertion of fact: "请医生确认：我的档案里 `<field_path>` 记的是 `<current_value>`，这个对吗？" If `suggested_value` exists, you may add "（系统提示可能应是 `<suggested_value>`，请医生核对）" — still framed as a question, the flag is **not** resolved here. If `review_flags[]` is empty, return an empty array (the template renders the `val_none_flagged` line).
>
> **`supplement_questions`** — one per `missing_items.json.missing[]` entry: "能不能补做/补齐 `<item>`？" append "（`<reason>`）" when `reason` present. Ask whether it can be added — never assert it is required.
>
> **`next_questions`** — derive from the most recent `timeline.json` events / `treatment_lines[].best_response` / `reason_for_change`: questions about what happens next, e.g. after a progression event "下一步的检查/复查节奏是怎样的？接下来有哪些方向可以讨论？". Patient-facing, **not** clinical advice — you ask the doctor what the options are, you do not state them.
>
> **`framework_questions`** — take the `<visit_type>` scaffold from `question-frameworks.md` and lightly personalize each skeleton question by slotting in this patient's verbatim fields (cancer type, current regimen, driver). Do **not** invent new clinical content beyond the scaffold; keep them as questions to the doctor.

Render: `confirm_questions` → Group A loop (each wrapped with the `q-confirm-tag` 待确认 tag inside the `.q-confirm` yellow box — these are **待医生确认项, never facts**); `supplement_questions` → Group B; `next_questions` → Group C; `framework_questions` → Group D.

## 5. Block 3 — 带什么

From `missing_items.json` + archive state (`profile.json.data_sources` / which buckets hold originals):

- `bring_originals` — the originals worth physically bringing: pathology原件, imaging 光盘/胶片, NGS/基因报告原件, 出院/诊断证明. Infer presence from `data_sources` and bucket coverage; if none inferable, render the `val_pending` line. List **what to bring** only — never interpret the content.
- `bring_for_questions` — for each Block-2 question, the record that backs it (e.g. a `confirm_question` about `stage` → bring the original pathology / diagnosis certificate; a `supplement_question` about a missing scan → bring prior imaging for comparison).

## 6. Block 4 — 上次 → 这次的变化 (followup only)

Render only when `visit_type == followup`. From `timeline.json` + `labs.json`, list **factual changes since the previous consult event** — no interpretation of whether a trend is good or bad:

- `change_symptoms` — new symptom/complaint events in `timeline` after the last `consult` event.
- `change_lab_trends` — panels with ≥2 values spanning the interval, rendered as `analyte v1 → v2 unit (date1 → date2)`, numbers + units verbatim. State the trend, do not judge it.
- `change_new_tests` — `imaging` / `molecular_test` / `lab` events dated after the last consult.

Each empty sub-block → render its `val_pending` line.

## 7. Guardrails (hard lines — `../../../references/safety-guardrails.md`)

- `review_flags` are always presented as **待医生确认项 (questions to confirm)**, never adjudicated into facts. They live in the yellow `.q-confirm` box with the 待确认 tag.
- **No treatment recommendation, no result interpretation, no clinical judgment, no treatment-option ranking.** visit-prep only assembles existing data + organizes questions.
- **Never fabricate.** Any null/absent field → the locale `val_pending` string.
- **Read-only on de-identified sources.** No formal-field writes, no confirm-gate, never read `10_原始文件/`.
- **Clinical entities verbatim**, scaffold localized to `profile.json.locale` (`../../../references/i18n.md` §4).

## 8. Output

Write the filled HTML to `patients/<pid>/就诊准备包.html`. Verify no `{{…}}` placeholder, `LOOP`, `RENDER_IF`, or locale-table comment survives in the output.
