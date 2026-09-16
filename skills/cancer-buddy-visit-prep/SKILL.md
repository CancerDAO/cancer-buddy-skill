---
name: cancer-buddy-visit-prep
description: "Assemble a one-page 就诊准备包 (visit prep pack) from an organized patient_dir — doctor's 30-second snapshot, the questions to ask the doctor, what to bring, and (follow-up only) what changed since last visit. Only assembles existing data + organizes questions; no treatment advice, no result interpretation, no clinical judgment. Triggers on 就诊准备, 明天看医生, 复诊准备, 该问医生什么, visit prep."
---

# cancer-buddy-visit-prep

Turn an already-organized patient archive into a one-page pack the patient brings to a consult: a snapshot a doctor reads in 30 seconds + a worked list of questions to ask. **Assemble + organize only — no treatment advice, no interpretation, no clinical judgment.**

## When to use

- Patient/caregiver says: 就诊准备 / 明天要看医生 / 复诊准备 / 不知道该问医生什么 / 该问医生什么 / visit prep.
- A `patient_dir` from organize already exists (patient_summary/timeline/labs/molecular/treatment episodes/document inventory/source-review flags).

## Inputs

- `patient_dir` = `patients/<pid>/` — requires organize to have run. If `profile.json` is absent, **route to `cancer-buddy-organize` first** ("先把病历整理成档案，再回来出就诊准备包"), then return here.
- Optional `visit_type` ∈ {`first` 初诊, `followup` 复诊, `decision_discussion` 决策讨论}. If the caller passed it, use it; if it cannot be detected from context, ask one short question before assembling.

## Locale

Read [../../references/i18n.md](../../references/i18n.md). The pack is a patient-visible template artifact:

1. If the caller / host supplies `locale` (the user's explicit product UI language), use it first and write/update `profile.json.locale` when profile state is available.
2. Otherwise read `patients/<pid>/profile.json` → `locale`. If present, use it — do not re-detect (visit-prep runs after organize, so a `locale` is almost always already persisted).
3. If absent, detect from the records' **primary patient-facing language**, tie-breaking to the language the user is conversing in (the `record-consuming generative sub-skills` row in `../../references/i18n.md` §2), then write it back to `profile.json.locale` (BCP-47).
4. Render every patient-visible scaffold string in that `locale` from the template's locale string table — section titles, question-group titles, "待确认" tag, disclaimer, `val_pending` placeholder, footer.
5. Preserve the source string for drugs, genes/variants, TNM/stage, response labels, numbers, units and biomarkers. A patient-facing translation may be added beside the original and must be marked as a translation.
6. Honor an explicit user language override → update `profile.json.locale` and follow it.

## Workflow

1. **Resolve locale** from caller-supplied `locale`, else `profile.json.locale`, else detection fallback + persist.
2. **Resolve `visit_type`** (caller arg → else ask one question).
3. **Read de-identified sources** (read-only): `patient_summary.json`, `readiness.json` (`review_flags[]` + `projection_coverage`), `molecular.json`, `treatment_lines.json`, `labs.json`, `timeline.json`, `missing_items.json`, and `source_inventory.json` — from the inventory read **`high_risk_fields[]` only** (the per-field array; the row-level `high_risk_review_status` is a derived summary and must not decide a single snapshot cell). Never read `raw/` (including `raw/transcript/`, `raw/_cache/`, `raw/adapter_views/`), and **never read `extracted_fields.json`** — nor its `open_verification_status`.
4. **Map Block 1 医生速览** — direct source mapping; null → `val_pending`. Do not calculate stage, ECOG, response, progression or treatment line. **Only verified values are admissible** — see [`review_flags` 分流与医生速览准入](#review_flags-分流与医生速览准入consumer-side-organize-v3).
5. **Derive Block 2 我要问医生的** per [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md): **route `review_flags[]` by `audience` first** (§ below) — only `audience == clinician` flags become confirmation questions, `internal_qc` ones collapse to a single line; document-inventory gaps remain questions about adding existing records, never recommendations to order tests; timeline content remains source-attributed. A host may use one bounded worker or do this directly; the output contract is identical.
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

## `review_flags` 分流与医生速览准入（consumer side, organize v3）

`readiness.json.review_flags[]` **不再无差别渲染成「请医生确认」**。逐条按 `audience` 分流：

| `audience` | 去处 | 患者向 HTML |
|---|---|---|
| `clinician` | Block 2 Group A「请医生确认」黄框 = `confirm_questions[]` | 逐条显示（跨源临床矛盾、分期版次缺失…） |
| `internal_qc` | 内部质检面 `review_flags.md` | **一条也不进医生面**；整组只折叠一行「档案有 N 处读数待家属对原件核对，见 review_flags.md」 |

`audience == internal_qc` 至少覆盖这四类 `category`：`transcription_disagreement`、`ocr_artifact`、`untrusted_content_marker`、`pii_semantic_deferred`。它们是感知层质检噪音，不是临床问题；把它们塞进医生面会稀释真正需要医生裁决的那几条。

**旧档案兜底（v3 之前归档、`review_flags[]` 没有 `audience` 字段）**：按 `category` 判 —— 上述四类视为 `internal_qc`，其余（`source_conflict` / `source_faithfulness` / `coverage_gap` / `other` / 空 `category`）视为 `clinician`。一旦走兜底，**必须在输出里标「旧档案兜底」**：`.visit_prep_data.json` 置 `legacy_flag_fallback: true`，模板把它渲染成 Group A 标题旁的灰色标签 + 折叠行里一句「本档案没有 audience 字段，分流按 category 兜底判定」。不要静默兜底。

`.visit_prep_data.json` 对应字段（详见 [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md) §3）：

- `confirm_questions[]` — 只来自 `audience == clinician`，一条 flag 一个问题。
- `internal_qc_count` — `audience == internal_qc` 的条数（含兜底判定）。`0` / 缺省 → 折叠行整块不渲染（内部质检项没有患者面「暂无」占位）。
- `internal_qc_flags[]`（可选，审计用）— `[{"id": …, "category": …}]`；给出时条数必须等于 `internal_qc_count`。
- `legacy_flag_fallback` — 本次是否用了兜底（`review_flags[]` 缺 `audience` / inventory 行缺 `high_risk_fields[]` / 某准入值 `verification_status == unverified`，任一命中即 `true`）。
- `snapshot_admission[]`（可选，审计用）— 一格一 label 一条，记录四个速览格各自凭什么准入 / 为什么没准入：`{cell, admitted, basis, label?, source_id?, high_risk_fields_present?}`。`basis` 取值表见 [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md) §3；给出时 `validate_visit_prep_html.py` 硬校验（含「有数组就必须按数组判」）。

### 医生速览（Block 1）准入

一个速览格只放**已核实**的值。准入判据二选一，满足其一即准入：

1. 该值的 `verification_status == clinician_verified`（结构化 JSON 的四值枚举 `unverified | clinician_verified | disputed | withdrawn`）；**或**
2. 该值所属源在 `source_inventory.json` 的 inventory 行 `high_risk_fields[]` 里、**该 `label` 对应的那一项** `status == passed_independent_reread`。

**按字段数组判，不按行级 `high_risk_review_status` 判。** 行级值是派生摘要（同行任一字段 `needs_human_review` → 整行 `needs_human_review`），拿它判单个格子会把同一行里已过通道独立第二读的字段一并误杀。只有当 inventory 行**根本没有** `high_risk_fields[]` 数组时（A13 legacy 档案），才退回行级 `high_risk_review_status == passed_independent_reread` 判，并置 `legacy_flag_fallback: true`。

不满足 → 该格渲染 `val_pending`；如果这个缺口本身有一条 `audience == clinician` 的 flag，它照常进 Group A，否则只计入折叠行。

**`verification_status` 是四值枚举**：`unverified | clinician_verified | disputed | withdrawn`。**`withdrawn` 只存在于 `timeline.json` 的事件行**（`timeline.schema.json`），语义是「来源自己撤回了这条事件」，其余结构化 JSON 只有前三值。`withdrawn` **永不准入**：被撤回的事件不是证据，靠它的速览格与 `disputed` 一样渲染 `val_pending`。不要按枚举之外的取值判准入。organize 内部 `extracted_fields.json` 另有一个同义容易混淆的状态字段 `open_verification_status`，它是 open-fields 归档面的字段，取值域与这里不同，**visit-prep 绝不读 `extracted_fields.json`，也绝不读它的 `open_verification_status`**——因此它的任何取值都不该在消费侧出现（`validate_visit_prep_html.py` 硬校验：`.visit_prep_data.json` 里出现这两个字样即 ERROR）。

**速览格内禁止出现 `读数1` / `读数2` 这类并列两读，禁止出现 `needs_human_review` 字样，禁止出现任何 internal_qc 标记。** 未过通道独立第二读的高风险字段不进任何患者向「已核实事实」面。`validate_visit_prep_html.py` 对速览区和「请医生确认」区做硬校验。

**四值口径（写死）**：`clinician_verified` → 准入；`disputed` → 不准入（改走 Group A 待确认）；`withdrawn`（仅 timeline）→ 不准入，且该事件不进任何速览格；`unverified` → **按 v2 行为呈现（准入并保留来源标注），并置 `legacy_flag_fallback: true`**。`unverified` 走的是兜底通道，必须在输出里标「旧档案兜底」，不要静默准入。

## Guardrails

Apply [../../references/safety-guardrails.md](../../references/safety-guardrails.md):

- **`review_flags` are routed by `audience`, never rendered wholesale as 「请医生确认」** — only `audience == clinician` reaches the yellow 待确认 box, and even there it stays a question to confirm, never adjudicated into fact. `audience == internal_qc` (转写分歧 / OCR 伪影 / 不可信内容标记 / PII 复扫延后) never reaches the doctor-facing surface; it collapses to one line pointing at `review_flags.md`. Archives with no `audience` field fall back by `category` **and say so** (「旧档案兜底」). See [`review_flags` 分流与医生速览准入](#review_flags-分流与医生速览准入consumer-side-organize-v3).
- **医生速览 only carries verified values** — admission is decided **per field**, from the inventory row's `high_risk_fields[]` entry for that `label` (`status == passed_independent_reread`) or from `verification_status == clinician_verified`; the row-level `high_risk_review_status` is only a legacy fallback when the array is absent. A high-risk field that has not passed an independent second read (`needs_human_review`, two parallel readings) renders `val_pending` instead; `读数1` / `读数2` / `needs_human_review` must never appear in a snapshot cell or in the 请医生确认 box. `extracted_fields.json` and its `open_verification_status` are never read here.
- **No treatment recommendation. No result interpretation. No clinical judgment. No ranking of treatment options.** visit-prep only assembles existing data + organizes questions.
- **Never fabricate** — any null/absent field renders the locale `val_pending` string ("资料缺失 / 待补充"), not an invented value.
- **Read-only on de-identified sources** — no formal-field writes, no confirm-gate involvement, never read `raw/`.
- **Source strings preserved**, with any patient-facing translation placed beside the original and labeled ([../../references/i18n.md](../../references/i18n.md)).
- **HTML is rendered by the template engine + must pass the validator — never hand-written.** The LLM produces `.visit_prep_data.json` only; `render_html_template.py` fills the template; the pack is "done" only after `validate_visit_prep_html.py` exits 0. Hand-writing or post-editing the rendered HTML is forbidden.

## Role behavior

Authoritative matrix in [`../../references/roles.md`](../../references/roles.md). For this skill:

- **Role = patient**: 患者本人备问题 — first-person question list for the patient's own consult.
- **Role = caregiver**: 帮家人备问题 — same pack reframed as the caregiver preparing questions for the patient's visit.
- **Role = family**: if authorized for this task, operate only within the documented scope; otherwise
  provide a blank visit-question template without reading patient records. Relationship alone is neither
  permission nor a reason to disclose.

**Disclosure** ([`../../references/disclosure-behavior.md`](../../references/disclosure-behavior.md)): family preferences do not override a capable patient's explicit request for their own information. For any legally valid restriction or uncertain capacity, show only content authorized for that viewer and route disclosure decisions to the treating team.


## Charting an indicator the user asked about

When the user asks about a **specific named lab value or observation** (CEA, 白蛋白, 体重…),
check `longitudinal_observations.json` / `labs.json` for that analyte BEFORE answering in prose:

- **≥2 comparable points** → answer in text **and attach a chart**:
  `python3 ../cancer-buddy-charts/scripts/render_chart.py --chart trend --from-longitudinal <patient_dir>/longitudinal_observations.json --metric <analyte> --out-html <patient_dir>/charts/<analyte>_趋势.html`
- **fewer than 2, or not comparable** → answer in text and say in one line why there is no chart

Volunteering a chart covers only the analyte the user named. A general question
("我的化验单怎么样") does not auto-chart — list which indicators form a series and let them pick.
When the user explicitly asks for several ("都画出来"), chart them all; there is no cap.

**Answer the question, do not wall it off.** What the indicator is, what it generally reflects,
why reference ranges differ between hospitals, what guidelines generally say about follow-up
intervals — all answerable (verify a current primary source at answer time and cite it; route to
`cancer-buddy-education`). Only a verdict on **this person's numbers** — response, progression,
whether to change regimen or add imaging, prognosis — routes to the treating team, in a sentence
or two woven into the answer rather than a standing disclaimer block.

Keep implementation detail out of the reply: no script names, exit codes, rule numbers, or your
own verification steps.

## References

- [references/visit-prep-html-prompt.md](references/visit-prep-html-prompt.md) — assembly prompt (emit `.visit_prep_data.json`; question list via subagent; render + validate gate)
- [references/question-frameworks.md](references/question-frameworks.md) — 初诊 / 复诊 / 换线决策 question scaffolds
- [references/templates/visit-prep.template.html](references/templates/visit-prep.template.html) — one-page 4-block template + locale string table
- [scripts/validate_visit_prep_html.py](scripts/validate_visit_prep_html.py) — deterministic form/shape PII validator **+ internal_qc leakage gate** (no `读数1` / `读数2` / `needs_human_review` / other internal_qc markers in the snapshot or 请医生确认 box; an `internal_qc_count > 0` in `.visit_prep_data.json` with no collapsed line in the HTML fails) **+ forbidden-read gate** (`extracted_fields` / `open_verification_status` anywhere in the data JSON fails) **+ admission-basis gate** (a declared `snapshot_admission[]` must decide each cell per field from `high_risk_fields[]`; the row-level `high_risk_review_status` basis is refused unless the row genuinely has no array, and both legacy bases require `legacy_flag_fallback: true`). `--help` for options. Contextual minimization of age and other quasi-identifiers remains a producer/authorization review.
- [../cancer-buddy-organize/scripts/render_html_template.py](../cancer-buddy-organize/scripts/render_html_template.py) — generic zero-medical-logic template engine (shared, stdlib only)
- [../../references/i18n.md](../../references/i18n.md) — shared locale layer (host `locale` first, otherwise profile locale / detection fallback / persist / verbatim-clinical)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md) — safety red lines
- [../../references/citation-format.md](../../references/citation-format.md)
- [../../references/evidence-trust-tiers.md](../../references/evidence-trust-tiers.md)
- [../../references/reference-library.md](../../references/reference-library.md)
