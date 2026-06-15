# visit-prep — HTML assembly prompt

This skill **only assembles existing data and organizes questions** — it never recommends treatment, never interprets a result, never makes a clinical judgment, never ranks treatment options. See `../../../references/safety-guardrails.md`.

## ⛔ Red lines — how the HTML gets built

1. **The LLM produces exactly one artifact: `visit_prep_data.json`** — a flat JSON data object (the field contract in §3–§6 below). **The LLM never writes, edits, or hand-assembles any HTML.**
2. **The HTML is produced only by the deterministic renderer**, never by the model:
   ```
   python3 ../cancer-buddy-organize/scripts/render_html_template.py \
       --template references/templates/visit-prep.template.html \
       --data <patient_dir>/visit_prep_data.json \
       --out  <patient_dir>/就诊准备包.html
   ```
   (`render_html_template.py` lives in the **cancer-buddy-organize** skill — `skills/cancer-buddy-organize/scripts/render_html_template.py` — and is a generic, zero-medical-logic template engine shared across cancer-buddy HTML artifacts. Stdlib only; runs in any Claude Code / codex / sandbox host.)
3. **The render is not done until `validate_visit_prep_html.py` passes** (exit 0) — see §9. A pack that has not passed the validator is **not** a finished pack.
4. **Hand-writing, hand-patching, or post-editing the rendered HTML is forbidden.** If something is wrong, fix `visit_prep_data.json` or the template and re-render — never touch the output HTML by hand.

These red lines exist so the pixel-exact patient-facing template is never deformed by free-text generation, and so over-fitting to one patient (e.g. silently dropping a section a patient happens not to have) is structurally impossible: the renderer renders 0..N of whatever the data carries; the template's `RENDER_IF_NOT` placeholders keep every block visible.

## 0. Read-only, de-identified sources

Read these from `patients/<pid>/` (all already produced by organize; read-only — visit-prep writes no formal field, touches no confirm-gate):

- `profile.json` — `locale`, `summary.primary`, `summary.histology`, `summary.stage`, `summary.current_regimen`, `source_refs` (drivers now in `molecular.json`, demographics in `patient_summary.json.demographics`).
- `readiness.json` — `review_flags[]` (each: `field_path`, `current_value`, `issue`, `suggested_value`, `severity`, `user_confirmed`), `blocking_gaps[]`.
- `molecular.json` — `variants[]`, `ihc[]`, `msi_mmr`, `tmb`.
- `treatment_lines.json` — `lines[]` (`line`, `regimen`, `intent`, `started_at`, `ended_at`, `best_response`, `reason_for_change`).
- `labs.json` — `panels[]` (`analyte`, `unit`, `reference_range`, `values[]` with `date`/`value`/`flag`).
- `timeline.json` (or `timeline.md`) — `events[]` (`date`, `category`, `title`, `detail`).
- `missing_items.json` — `missing[]` (`item`, `priority`, `reason`, `category`).

Never read `raw/` or any non-de-identified source. If a file is absent, treat its fields as missing (render the locale `val_pending` string) — do not fabricate.

## Shape of `visit_prep_data.json`

A flat JSON object. The renderer's grammar is: `{{i18n.<k>}}` → `data.i18n.<k>`; `{{scalar}}` → `data.<scalar>`; `<!-- LOOP arr -->…<!-- END LOOP -->` repeats once per element of `data.arr` (an **array of objects**, each item field resolved as `{{field}}`); `<!-- RENDER_IF k -->` / `<!-- RENDER_IF_NOT k -->` render their span when `data.k` is truthy / falsy.

```jsonc
{
  "i18n": { "html_lang": "...", "doc_title": "...", /* every key from the template's locale string table for this locale */ },
  "fallbacks": { "__default__": "<i18n.val_pending string>" },  // any null scalar → this placeholder
  "one_line_condition": "...", "visit_type_label": "...", "report_date": "YYYY-MM-DD",
  "is_followup": true,                                         // Block 4 gate (see §2)
  "snapshot_diagnosis": "...", "snapshot_molecular": "...", "snapshot_current_line": "...", "snapshot_key_labs": "...",
  "confirm_questions":   [ { "text": "..." }, … ],            // 0..N — array of {text}
  "supplement_questions":[ { "text": "..." }, … ],
  "next_questions":      [ { "text": "..." }, … ],
  "framework_questions": [ { "text": "..." }, … ],
  "bring_originals":     [ { "text": "..." }, … ],
  "bring_for_questions": [ { "text": "..." }, … ],
  "change_symptoms":     [ { "text": "..." }, … ],            // followup only; [] when none
  "change_lab_trends":   [ { "text": "..." }, … ],
  "change_new_tests":    [ { "text": "..." }, … ]
}
```

Every loop array is `0..N` — emit one `{text}` object per real item, **no padding, no trimming**. An empty array is fine: the template's `RENDER_IF_NOT` placeholder keeps the section visible with the `val_pending` (or `val_none_flagged`) line. Never invent an item to fill a section.

## 1. Locale → the `i18n` object

Read `profile.json.locale` first; if present use it, do not re-detect (visit-prep runs after organize). If absent, detect from the records' primary patient-facing language per `../../../references/i18n.md` §2 and write it back to `profile.json.locale`.

Build `data.i18n` from the template's locale string table for that `locale` — one key per `{{i18n.<key>}}` the template uses (incl. `html_lang`). For a locale not in the table, generate equivalents in the target language — same meaning, same tone. **Keep every clinical entity verbatim** regardless of locale (drug names, genes/variants, TNM/stage, RECIST codes, numbers + units, biomarker labels) — `../../../references/i18n.md` §4; mistranslating one is a P0 safety bug (`../../../references/safety-guardrails.md`).

## 2. visit_type

`visit_type` ∈ {`first` 初诊, `followup` 复诊, `switch` 换线决策}. If the caller passed it, use it. If not detectable from context, ask the user one short question and wait. Set `data.visit_type_label` to the matching locale string (`vt_first` / `vt_followup` / `vt_switch`). Set **`data.is_followup = true` only when `visit_type == followup`** (else `false`) — Block 4 (上次→这次变化) renders only when `is_followup` is truthy.

## 3. Block 1 — 医生速览 (direct field mapping, clinical entities verbatim)

Map structured fields straight into the snapshot, verbatim — no interpretation:

| placeholder | source |
|---|---|
| `{{one_line_condition}}` | one-sentence condition line from `profile.json` (`summary.primary` + `summary.histology` + `summary.stage` + headline driver), e.g. `非小细胞肺癌 腺癌 IIIA (cT3N2M0)，EGFR L858R`. |
| `{{snapshot_diagnosis}}` | `summary.primary` / `summary.histology` / `summary.stage` joined verbatim. |
| `{{snapshot_molecular}}` | from `molecular.json`: variants (`gene` + `variant`), `msi_mmr.status`, key `ihc[]`, `tmb` — verbatim, comma-joined. |
| `{{snapshot_current_line}}` | current line from `treatment_lines.json` (latest line with no `ended_at`, or `profile.summary.current_regimen`): `regimen` + line number, verbatim. |
| `{{snapshot_key_labs}}` | from `labs.json`: latest value of each panel whose newest value has `flag` ∈ {H, L, HH, LL}, as `analyte value unit (date)` verbatim. |

Any source field null/absent → set that scalar to `null` (the renderer substitutes `fallbacks.__default__` = the locale `val_pending` string). Never fabricate a value.

## 4. Block 2 — 我要问医生的 (subagent-derived; do NOT hardcode a keyword list)

This is the core block and is **LLM-derived by a subagent**, not a hardcoded keyword/phrase table. Dispatch a subagent with the four source arrays + the patient's `visit_type` and the question scaffolds in `question-frameworks.md`. The subagent returns four question groups, which become `data.confirm_questions` / `supplement_questions` / `next_questions` / `framework_questions` — each an **array of `{ "text": "<question>" }` objects** (0..N, one per real source item; empty array if none).

Subagent instructions:

> You are drafting questions a cancer patient will ask their own doctor. You produce **questions only** — never an answer, never a recommendation, never a treatment ranking, never a clinical interpretation. Output all prose in `<locale>`; keep every clinical entity verbatim (drug names / genes / variants / TNM / numbers+units). Return JSON with four arrays, each element `{ "text": "<one question>" }`.
>
> **`confirm_questions`** — one per `readiness.json.review_flags[]` entry (regardless of `severity` / `user_confirmed`). Each is phrased strictly as a **request for the doctor to confirm**, never as an assertion of fact: "请医生确认：我的档案里 `<field_path>` 记的是 `<current_value>`，这个对吗？" If `suggested_value` exists, you may add "（系统提示可能应是 `<suggested_value>`，请医生核对）" — still framed as a question, the flag is **not** resolved here. If `review_flags[]` is empty, return an empty array (the template renders the `val_none_flagged` line).
>
> **`supplement_questions`** — one per `missing_items.json.missing[]` entry: "能不能补做/补齐 `<item>`？" append "（`<reason>`）" when `reason` present. Ask whether it can be added — never assert it is required.
>
> **`next_questions`** — derive from the most recent `timeline.json` events / `treatment_lines[].best_response` / `reason_for_change`: questions about what happens next, e.g. after a progression event "下一步的检查/复查节奏是怎样的？接下来有哪些方向可以讨论？". Patient-facing, **not** clinical advice — you ask the doctor what the options are, you do not state them.
>
> **`framework_questions`** — take the `<visit_type>` scaffold from `question-frameworks.md` and lightly personalize each skeleton question by slotting in this patient's verbatim fields (cancer type, current regimen, driver). Do **not** invent new clinical content beyond the scaffold; keep them as questions to the doctor.

The renderer maps these arrays to template loops: `confirm_questions` → Group A (each wrapped with the `q-confirm-tag` 待确认 tag inside the `.q-confirm` yellow box — these are **待医生确认项, never facts**); `supplement_questions` → Group B; `next_questions` → Group C; `framework_questions` → Group D. You only emit the data arrays; the template + renderer place them.

## 5. Block 3 — 带什么

From `missing_items.json` + archive state (`profile.json.source_refs` / which buckets hold originals). Both are arrays of `{ "text": "..." }`:

- `bring_originals` — the originals worth physically bringing: pathology原件, imaging 光盘/胶片, NGS/基因报告原件, 出院/诊断证明. Infer presence from `source_refs` and bucket coverage; if none inferable, leave the array empty (the template's `RENDER_IF_NOT` shows the `val_pending` line). List **what to bring** only — never interpret the content.
- `bring_for_questions` — for each Block-2 question, the record that backs it (e.g. a `confirm` question about `stage` → bring the original pathology / diagnosis certificate; a `supplement` question about a missing scan → bring prior imaging for comparison).

## 6. Block 4 — 上次 → 这次的变化 (followup only)

Populated only when `visit_type == followup` (and `data.is_followup = true`; otherwise leave these arrays empty / `is_followup = false` and the whole block does not render). From `timeline.json` + `labs.json`, list **factual changes since the previous consult event** — no interpretation of whether a trend is good or bad. Each is an array of `{ "text": "..." }`:

- `change_symptoms` — new symptom/complaint events in `timeline` after the last `consult` event.
- `change_lab_trends` — panels with ≥2 values spanning the interval, each `text` as `analyte v1 → v2 unit (date1 → date2)`, numbers + units verbatim. State the trend, do not judge it.
- `change_new_tests` — `imaging` / `molecular_test` / `lab` events dated after the last consult.

Each empty sub-block → its array is `[]`; the template's `RENDER_IF_NOT` shows the `val_pending` line so the sub-block still renders.

## 7. Guardrails (hard lines — `../../../references/safety-guardrails.md`)

- `review_flags` are always presented as **待医生确认项 (questions to confirm)**, never adjudicated into facts. They live in the yellow `.q-confirm` box with the 待确认 tag.
- **No treatment recommendation, no result interpretation, no clinical judgment, no treatment-option ranking.** visit-prep only assembles existing data + organizes questions.
- **Never fabricate.** Any null/absent field → the locale `val_pending` string.
- **Read-only on de-identified sources.** No formal-field writes, no confirm-gate, never read `raw/`.
- **Clinical entities verbatim**, scaffold localized to `profile.json.locale` (`../../../references/i18n.md` §4).

## 8. Output — render via script, never by hand

1. Write `visit_prep_data.json` (the §-shape object above) to `patients/<pid>/visit_prep_data.json`.
2. Render with the generic engine (do **not** hand-write HTML — see the Red lines at the top):
   ```
   python3 ../cancer-buddy-organize/scripts/render_html_template.py \
       --template references/templates/visit-prep.template.html \
       --data  patients/<pid>/visit_prep_data.json \
       --out   patients/<pid>/就诊准备包.html
   ```
   The renderer exits non-zero if any `{{…}}` placeholder survives (a data-contract gap) — fix the JSON, never the HTML, and re-render.

## 9. Validator gate — the pack is not done until this passes

Run the form-invariant validator; **exit 0 is the definition of "rendered HTML done":**

```
python3 scripts/validate_visit_prep_html.py patients/<pid>/就诊准备包.html
```

It asserts only *form* invariants fixed by the template (style byte-identical to the template, every class ⊆ the template's classes, no residual `{{…}}` / `LOOP` / `RENDER_IF` markers, no PII — DOB still barred, but **precise age is allowed** (clinical-trial matching + 就诊场景 need it), skeleton present) — it makes **no content-existence assertions**, so a patient with zero labs / zero review-flags / zero changes still passes. If it fails, fix `visit_prep_data.json` or the template and re-render + re-validate. A pack that has not passed this validator is not a finished pack.
