---
name: cancer-buddy-visit-prep
description: "Assemble a one-page 就诊准备包 (visit prep pack) from an organized patient_dir — doctor's 30-second snapshot, the questions to ask the doctor, what to bring, and (follow-up only) what changed since last visit. Only assembles existing data + organizes questions; no treatment advice, no result interpretation, no clinical judgment. Triggers on 就诊准备, 明天看医生, 复诊准备, 该问医生什么, visit prep."
---

# cancer-buddy-visit-prep

Before assembling a visit pack, run [`medical-emergency-gate.md`](../cancer-buddy/references/medical-emergency-gate.md) and the suicide-safety rules in [`safety-guardrails.md`](../cancer-buddy/references/safety-guardrails.md). Obvious urgent symptoms go to immediate care, not tomorrow's appointment.

Turn an already-organized patient archive into a one-page pack the patient brings to a consult: a snapshot a doctor reads in 30 seconds + a worked list of questions to ask. **Assemble + organize only — no treatment advice, no interpretation, no clinical judgment.**

## When to use

- Patient/caregiver says: 就诊准备 / 明天要看医生 / 复诊准备 / 不知道该问医生什么 / 该问医生什么 / visit prep.
- A `patient_dir` from organize already exists (profile/timeline/labs/molecular/treatment_lines/readiness/missing_items).

## Inputs

- `patient_dir` = `patients/<pid>/` — requires organize to have run. If `profile.json` is absent, **route to `cancer-buddy-organize` first** ("先把病历整理成档案，再回来出就诊准备包"), then return here.
- Optional `visit_type` ∈ {`first` 初诊, `followup` 复诊, `switch` 换线决策}. If the caller passed it, use it; if it can't be detected from context, ask the user one short question and wait before assembling.

## Locale

Read [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md). The pack is a patient-visible template artifact:

1. If the caller / host supplies `locale` (the user's explicit product UI language), use it first and write/update `profile.json.locale` when profile state is available.
2. Otherwise read `patients/<pid>/profile.json` → `locale`. If present, use it — do not re-detect (visit-prep runs after organize, so a `locale` is almost always already persisted).
3. If absent, detect from the records' **primary patient-facing language**, tie-breaking to the language the user is conversing in (the `record-consuming generative sub-skills` row in `../cancer-buddy/references/i18n.md` §2), then write it back to `profile.json.locale` (BCP-47).
4. Render every patient-visible scaffold string in that `locale` from the template's locale string table — section titles, question-group titles, "待确认" tag, disclaimer, `val_pending` placeholder, footer.
5. Keep every clinical entity verbatim regardless of `locale` — drug names, genes/variants, TNM/stage, RECIST codes, all numbers + units, biomarker labels. Mistranslating a clinical entity is a P0 medical-safety bug.
6. Honor an explicit user language override → update `profile.json.locale` and follow it.

## Workflow

1. **Resolve locale** from caller-supplied `locale`, else `profile.json.locale`, else detection fallback + persist.
2. **Resolve `visit_type`** (caller arg → else ask one question).
3. **Read de-identified sources** (read-only): `profile.json`, `readiness.json`, `molecular.json`, `treatment_lines.json`, `labs.json`, `timeline.json`, `missing_items.json`. Never read `raw/`.
4. **Map Block 1 医生速览** — direct field mapping, clinical entities verbatim; null → `val_pending`.
5. **Derive Block 2 我要问医生的 via a subagent** (do not hardcode a keyword list): dispatch the subagent per [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md) §4 to turn `review_flags` (→ 请医生确认), `missing_items` (→ 能否补做/补齐), `timeline` 进展 (→ 下一步), and the `visit_type` scaffold from [references/question-frameworks.md](references/question-frameworks.md) into four question groups. *(单进程 / 无 subagent host 如 Codex：不派子代理，主 agent 直接按 §4 生成这四组问题——只需一次生成，无并行需求，产物一致。)*
6. **Assemble Block 3 带什么** and (follow-up only) **Block 4 上次→这次变化** per the assembly prompt.
7. **Emit `.visit_prep_data.json` only — never hand-write HTML.** `<patient_dir>` is the absolute patient directory resolved via the standard chain `$CANCER_BUDDY_PATIENTS_DIR → $VMTB_PATIENT_DATA_ROOT → $HOME/CancerDAO/patients` (same resolution as cancer-buddy-organize) — **not** a path relative to this skill dir. Script and template paths below are relative to this skill's directory (`skills/cancer-buddy-visit-prep/`); the data + output paths are absolute under `<patient_dir>`. Write `<patient_dir>/.visit_prep_data.json`, then render the template deterministically:
   ```
   python3 ../cancer-buddy-organize/scripts/render_html_template.py \
       --template references/templates/visit-prep.template.html \
       --data <patient_dir>/.visit_prep_data.json --out <patient_dir>/就诊准备包.html
   ```
   (`render_html_template.py` is the generic zero-medical-logic engine in the **cancer-buddy-organize** skill, stdlib only.)
8. **Gate: validate the rendered HTML — it is not done until this passes (exit 0):**
   ```
   python3 scripts/validate_visit_prep_html.py <patient_dir>/就诊准备包.html
   ```
   On failure, fix `.visit_prep_data.json` or the template and re-render + re-validate — **never patch the output HTML by hand**.

Full assembly contract: [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md).

## Guardrails

Apply [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md):

- **`review_flags` are presented as 待医生确认项 (questions to confirm), never adjudicated into facts** — they render in the yellow box with the 待确认 tag.
- **No treatment recommendation. No result interpretation. No clinical judgment. No ranking of treatment options.** visit-prep only assembles existing data + organizes questions.
- **Never fabricate** — any null/absent field renders the locale `val_pending` string ("资料缺失 / 待补充"), not an invented value.
- **Read-only on de-identified sources** — no formal-field writes, no confirm-gate involvement, never read `raw/`.
- **Clinical entities verbatim**, scaffold localized to `profile.json.locale` ([../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md) §4).
- **HTML is rendered by the template engine + must pass the validator — never hand-written.** The LLM produces `.visit_prep_data.json` only; `render_html_template.py` fills the template; the pack is "done" only after `validate_visit_prep_html.py` exits 0. Hand-writing or post-editing the rendered HTML is forbidden.

## Role behavior

Authoritative matrix in [`../cancer-buddy/references/roles.md`](../cancer-buddy/references/roles.md). For this skill:

- **Role = patient**: 患者本人备问题 — first-person question list for the patient's own consult.
- **Role = caregiver**: provide a general checklist; tailor from an archive only within verified read scope.
- **Role = family**: provide a general visit-support checklist and a one-line handoff without reading patient data.

**Disclosure** ([`../cancer-buddy/references/disclosure-behavior.md`](../cancer-buddy/references/disclosure-behavior.md)): ask an authorized patient how much diagnostic detail to show. Do not let a caregiver-set flag censor the patient's own archive.

## References

- [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md) — assembly prompt (emit `.visit_prep_data.json`; question list via subagent; render + validate gate)
- [references/question-frameworks.md](references/question-frameworks.md) — 初诊 / 复诊 / 换线决策 question scaffolds
- [references/templates/visit-prep.template.html](references/templates/visit-prep.template.html) — one-page 4-block template + locale string table
- [scripts/validate_visit_prep_html.py](scripts/validate_visit_prep_html.py) — form-invariant validator (style byte-exact / class ⊆ template / no residual markers / no PII — DOB barred but precise age allowed / skeleton); content-agnostic
- [../cancer-buddy-organize/scripts/render_html_template.py](../cancer-buddy-organize/scripts/render_html_template.py) — generic zero-medical-logic template engine (shared, stdlib only)
- [../cancer-buddy/references/i18n.md](../cancer-buddy/references/i18n.md) — shared locale layer (host `locale` first, otherwise profile locale / detection fallback / persist / verbatim-clinical)
- [../cancer-buddy/references/safety-guardrails.md](../cancer-buddy/references/safety-guardrails.md) — safety red lines
