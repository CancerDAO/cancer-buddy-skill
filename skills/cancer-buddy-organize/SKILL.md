---
name: cancer-buddy-organize
description: "Organize patient medical records into a provenance-preserving patient directory. Produces source-attributed summaries and schema-validated JSON while keeping source-reported, patient-reported and normalized layers separate. It does not infer diagnosis, stage, ECOG, response, progression, treatment line, prognosis or testing indications. Triggers on 病历整理, 整理报告, organize medical records."
---

# cancer-buddy-organize

Turn raw medical records into structured data every other sub-skill can use.

## 🔴 抗压缩不变量（读到这份 skill 就先记住这几条 —— 上下文被压缩后它们必须存活）

这条流程很长（18 步），`病情简要总结.html` 的生成在很靠后（Step 12）。**当 host 压缩上下文时，"产出 HTML" 这个目标会存活，而"怎么产"的机制会被摘掉** —— 于是模型容易走捷径**手写一份 HTML**，这是**非法交付**。下面三条是即使正文被摘要也不能丢的硬约束：

1. **provenance-first：任何 `病情简要总结.html` 若不含 `<!-- template_sha256: … -->` provenance 注释 = 非法交付，必须经模板管线重生成。** HTML 的唯一合法产生路径是 `render_html_template.py` 从 `references/templates/case-summary.template.html` 渲染，**永不手写 / 拼接 / 内联 HTML**。手写的 HTML 没有 provenance 注释，会被 `validate_case_summary_html.py` 当场判非法。
2. **段D 全管线在一个自包含 subagent 内完成并返回 `template_sha`**（Step 12）：编排器**不自己拼 HTML、也不自己散跑那串 bash**，只负责"派 subagent → 收它返回的 `template_sha`（校验已通过的证明）→ 做 dated 快照"。派活的机制被隔离在子代理的干净上下文里，不受编排器压缩影响。
3. **Definition of Done（终态硬门）：本次 organize 未完成，直到 `python3 scripts/validate_structured_outputs.py <patient_dir>` exit 0 且你已把它的输出（含 `template_sha`）贴给用户。** 见文末「Definition of Done」。不许在没跑这道门、没贴 template_sha 的情况下自报"整理完成"。

## When to use

- User provides a folder path or set of files (PDF, JPG, PNG, DOCX, ZIP).
- User asks: 病历整理 / 帮我整理这些报告 / 我有一堆检查单.
- Any other sub-skill needs a source-attributed patient archive. Missing fields limit only the affected output; they do not block general education.

## Inputs

- Path to a folder OR a single PDF/DOCX OR a zip/rar/7z/tar.gz archive.

## Outputs

Written under `patients/<patient_code>/`:

- `INDEX.md` (first line: `# patient_code: <code>`)
- `AGENTS.md` — **agent-facing cross-session recall pointer** (filled from `references/templates/agents-md.template.md`). A harness that auto-loads `AGENTS.md` from the cwd (pi, Claude Code, …) gets the patient identity + a routing table (which structured file answers which question) + the two-layer drill-down rule (top-level JSON → `source_refs`/`source_inventory.json` sidecars) + the verbatim-citation / no-fabrication floor — so any session whose cwd is in this patient dir can answer from the archive **without first invoking the cancer-buddy skill**. Two fields injected verbatim from `profile.json` (`patient_code`, `summary.one_line_condition`); the static body is patient-independent.
- `profile.json` (conforms to `../../references/patient-profile-schema.md`; optional alias is user-chosen, non-clinical, and non-identifying)
- `timeline.md` (human-readable treatment timeline; every line ends with at least one `[[src:...]]` anchor)
- `readiness.json` — compatibility filename containing documentation coverage plus unresolved extraction/source-faithfulness flags; no clinical readiness grade
- `review_flags.md` — auto-generated human-readable rendering of `readiness.json.review_flags[]` (only written when array non-empty)
- `review_summary.md` — **always written**: 1-page checklist of extracted key fields with verbatim source citations, for user spot-check (catches internally consistent but wrong ingestion that review_flags can't)
- `case_text.md` (consolidated narrative; every factual sentence anchored via `[[src:<bucket>/<canonical>.md#L<a>-L<b>]]` — bucket-relative, the text-masked MD that now lives next to its image)
- `update_log.json` — append-only audit trail of every full / incremental run (timestamps, added/archived files, affected summaries, documentation-coverage deltas)
- **6 structured JSON outputs** (schema-validated against `references/schemas/*.schema.json`):
  - `patient_summary.json` — demographics + diagnosis + current_status rollup
  - `timeline.json` — machine-readable mirror of `timeline.md`
  - `molecular.json` — report-linked NGS variants + IHC + separate MSI/MMR + TMB results
  - `treatment_lines.json` — chronological treatment episodes; a clinical line label is copied only when documented
  - `labs.json` — lab panels with per-result unit, reference range and report flag
  - `comorbidities.json` — conditions + long-term meds + allergies
- `missing_items.json` — existing-document inventory gaps only; never a recommendation to order a test
- `gap_asks.json` — **append-only ask-once ledger** for invitations to add an existing document. Records
  `{item_key, document_category, asked_at, surfaced_at_trigger, status: pending|provided|declined}`;
  it never assigns clinical priority or recommends a test.
- `source_inventory.json` — one entry per content unit: stable IDs, protected original path, source span,
  native/deterministic extractor provenance, independent high-risk-field reread status, sidecar path,
  modality, and persistence state. Conforms to `source_inventory_v2`.
- `01_身份与基础信息/`…`14_患者自管补充/` (14 clinical-domain buckets, scheme_version 3 — see `references/bucket-taxonomy.md`). Each bucket holds **only the text-masked MD sidecars** `<bucket>/<canonical>.md` (canonical = `<YYYY-MM-DD>_<doc_type>_<hospital>`, 4-level hospital fallback; the downstream-only read source — no plaintext PII). **The uploaded original is NOT copied into the bucket** — it lives once in `raw/`, deep-linked from each sidecar via `source_inventory.json.raw_path`.
- `raw/` — access-controlled originals. Organization preserves uploaded bytes under a de-identified filename
  and never silently overwrites, transforms, or deletes them. Retention/deletion is a host-governed,
  authenticated lifecycle action. Original filenames remain protected provenance and are excluded from
  derived exports. Each sidecar links to the authorized original through `source_inventory.json.raw_path`.
- `longitudinal_observations.json` — parsed time series from `timeseries`/trended `structured` sources (wearable / PRO / lab trends); raw export filed in `10_随访与监测`. Conforms to `references/schemas/longitudinal_observations.schema.json` (`longitudinal_observations_v1`).
- `病情简要总结.html` — 段D one-page case summary, 1:1 against the gold-standard template, generated after the Profile Card from text-masked JSON only (never raw images). Includes a **关键趋势 hero chart** + **实验室指标 trend rows** (inline-SVG sparklines drawn from `longitudinal_observations.json`, treatment-line changes overlaid on the same axis) and a **自上次总结的变化 delta strip** diffing the previous snapshot — so a patient who keeps adding follow-up records sees their trajectory and what changed. The patient-root file is always the **latest**; immutable **dated versions** accumulate under `case_summary_versions/病情简要总结_<date>.html` (a re-render never destroys the version a patient already shared).
- `case_summary_versions/` — dated immutable snapshots of every 段D generation: both `病情简要总结_<date>.html` (patient-facing history) and `case_summary_data_<date>.json` (the render data, which is the comparison base for the next generation's 自上次总结的变化 delta).

An optional alias remains a protected profile field only. Do not create diagnosis-bearing symlinks or a
root-level alias map; filesystem locators use the random `patient_code`.

A **derived, on-demand export** is created only after host authentication and explicit confirmation of
recipient, scope, purpose, and expiry. `scripts/export_share.py` requires an allowlist of included paths,
excludes `raw/` and protected build/provenance files, and runs structural gates. It does not itself grant
authorization or prove anonymity.

## Patient-dir file map (read/consume relationships)

A consumer answering questions on an **already-organized** `patients/<patient_code>/` reads **selectively**, in the order defined by the patient-facing read protocol (`../cancer-buddy/SKILL.md` → 档案读取协议). This is the role map:

| File | Role | Read it when |
|---|---|---|
| `profile.json` | **Slim canonical first-read snapshot** (`cancer_buddy_profile_v3`): identity + `locale` + denormalized `summary` + `latest_status` | **Always first** — who is this + current state + language |
| `readiness.json` | Documentation coverage + unresolved source/faithfulness flags | **Second** — disclose uncertainty for the affected field; never convert coverage into a clinical readiness score |
| `INDEX.md` | File manifest (file_id / 桶 / 类型 / 日期 / 机构 / 置信 / MD / Raw原件 / 页码) | **Third** — to know which sources exist + map fact→filename for citation |
| `patient_summary.json` | **Full structured** demographics / diagnosis / current_status rollup (authoritative for structured diagnosis) | Diagnosis / staging / demographics questions |
| `molecular.json` / `labs.json` / `treatment_lines.json` / `timeline.json` / `comorbidities.json` | 5 of the 6 structured JSONs (patient_summary.json is the row above; schema-validated, each row carries `source_refs[]`) | The matching question domain — read **one**, not all |
| `longitudinal_observations.json` | Time series (wearable / PRO / lab trends) | Trend / trajectory questions |
| `case_text.md` / `timeline.md` | Human-readable narrative (anchored) | Only when quoting / a verbatim citation is needed |
| `source_inventory.json` | `file_id ↔ sidecar ↔ raw_path` map | Frontend deep-link to a `raw/` original |
| `missing_items.json` / `review_summary.md` / `review_flags.md` / `update_log.json` | Coverage gaps / spot-check / audit | Completeness / audit questions |
| `病情简要总结.html` | Patient-facing one-page summary | Hand to the patient as-is |
| `.case_summary_data.json` | **Hidden** render intermediate for the HTML | Never read for Q&A (build artifact) |

**Producer**: Phase 2 writes everything except the 段D HTML (a 段D subagent + `render_html_template.py`) and `AGENTS.md` (orchestrator Step 13, filled from the post-correction `profile.json` — it depends on the user-corrected profile, so it runs after Phase 2 + the confirm gate, not inside the synthesis worker). **`timeline.md` vs `timeline.json`** = human surface vs machine mirror (same content); **`profile.json` vs `patient_summary.json`** = slim denormalized snapshot vs full normalized rollup (`profile.summary` is an intentional convenience copy — see `../../references/patient-profile-schema.md`).

## Locale (i18n)

This skill follows the shared locale contract in [`../../references/i18n.md`](../../references/i18n.md). organize is the **canonical writer** of `profile.json.locale`:

- On entry, if the caller / host supplies `locale` (the user's explicit product UI language), pass it into Phase 2 and let Phase 2 write / overwrite `profile.json.locale` with that value. This wins over any existing profile locale and over record-language detection.
- If no host `locale` is supplied and `profile.json` already exists, **read `profile.json.locale` and reuse it** (don't re-detect). Otherwise the Phase-2 Synthesis Worker **detects** the locale from the **primary patient-facing language of the records** (LLM judgment, mixed-language tie-break per i18n.md §2.1) and **persists** it to `profile.json.locale` (BCP-47, e.g. `zh` / `en` / `fr`).
- Every patient-visible output renders its **scaffold** in that locale — bucket folder slugs (the `NN_` prefix stays a stable, language-independent key — downstream anchors match on `NN_`, never on the localized slug), `timeline.md` / `case_text.md` / `review_summary.md` prose, the 段D 病情简要总结 HTML (string table in the template), the 段E disposition notice, and 段C / 扩段C diff cards.
- **Source strings are always preserved.** Patient-facing translations may be added beside the original and must be labeled and reviewable; a translation never silently replaces a drug, gene/variant, TNM/stage string, value, unit or biomarker label.
- An explicit user language override ("用英文" / "answer in English") updates `profile.json.locale` and wins over auto-detection.

## Workflow

> **跨 host 提示（Codex / 单进程先读这句）**：下面 Step 2–5 的 `Agent` 并行 fan-out + reduce 是 **Claude Code 参考绑定，不是契约**。无 subagent 的单进程 host（Codex 等）请以 [`references/organize-contract.md`](references/organize-contract.md)（零工具名的行为契约）+ [`references/runtime-bindings/headless-codex.md`](references/runtime-bindings/headless-codex.md) 为准：把 Phase 1 fan-out 改为**顺序遍历 source inventory 逐源调用**（`codex exec -i` 提供视觉 + 干净上下文），Phase 2 单次综合。**并行只关乎速度，产物集与不变量完全一致**。详见文末「Runtime adaptation」。

1. **Resolve input** — confirm the user-supplied path with them. For archives, unpack to `/tmp/cb-unpack-$$/` first (zip / rar / 7z / tar.gz / single pdf-or-docx). After unpack, the **resolved input directory** (`$src`) is what Step 2 plans against.

2. **Plan slicing (single-pass vs fan-out)** — `glob $src` for immediate subdirectories, count files, and decide slice boundaries.

   **MAX 15 image-like inputs per Phase 1 worker on Claude Code.** Claude has a per-conversation total-image budget when many images/rendered pages are loaded into a single context. A worker that tries to ingest 25+ HEIC images or rendered PDF pages in one dispatch can hit image/context limits partway through and abort with partial output. Host-specific adapters may choose a different budget.

   Slicing rules:

   - **Single-pass mode**: ≤ 15 files total → one Phase 1 worker
   - **Sub-directory fan-out**: ≥ 2 subdirectories AND each subdir has ≤ 15 files → one worker per subdir
   - **Sub-directory fan-out with internal split**: ≥ 2 subdirectories AND any subdir has > 15 files → split each oversized subdir into halves/thirds (e.g. `h1_part1`/`h1_part2`), one worker per part. Typical case: 73 images across 3 hospitalizations of ~25 each → 6 workers (each hospitalization split into 2 halves of ~12-13 files).
   - **Flat fan-out**: no subdirectories, > 15 files → split into N-file chunks (alphabetical or arbitrary), name slices `batch_a`/`batch_b`/etc.

   Workers across slices run in parallel (single message, N concurrent Agent tool calls). Within a worker, files run sequentially.

   Decide `patient_code`: generate a cryptographically random `PT-<hex>` locator. Reject a supplied
   real-world identifier rather than preserving it. The code is not authentication and must not be derived
   from a name, path, diagnosis or timestamp. Resolve `patient_data_root` from
   `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Compute
   `patient_dir = <patient_data_root>/<patient_code>` and `mkdir -p` **only `ocr/` + `raw/`** at setup.
   **Do NOT pre-create the 14 clinical buckets.**

3. **Dispatch Phase 1 source-fidelity ingestion workers (parallel)** — each worker follows
   `organizer-prompt-phase1-ocr.md`: deterministic/native character extraction first, preservation of raw
   text and provenance, LLM layout/semantic assistance second, and independent rereading of high-risk fields.
   For each slice, dispatch one `general-purpose` subagent in a single message with N tool calls.

   - `subagent_type: general-purpose`
   - `description: "Organize source-fidelity ingestion slice <slice_id>"`
   - `prompt`: the full content of [`references/organizer-prompt-phase1-ocr.md`](references/organizer-prompt-phase1-ocr.md), with these `## Call parameters` appended at the end:
     - `slice_input_path: <absolute path to the slice's source directory>`
     - `slice_id: <short logical label — e.g. h1, h2, batch_a>`
     - `patient_dir: <absolute patient_dir>`
     - `original_subdir: <relative path under raw/ where verbatim originals go — usually the source subdir's basename>`

   Each Phase 1 worker writes only source-fidelity sidecars/provenance under `<patient_dir>/ocr/` and
   access-controlled originals under `<patient_dir>/raw/<original_subdir>/`. Native text/OCR output is a
   preserved character source; LLM proposals are separate and cannot overwrite it. Temporary renderings are
   adapter views, not independent evidence. Workers do not touch INDEX.md/timeline.md/profile.json.

   Each worker returns: `{slice_id, files_processed, sidecars_written, stub_sidecars, full_ingestion_sidecars, ingestion_uncertain_files, candidates_files, ingestion_blocked_files, continuation_needed, continuation_resume_from}`.

4. **Phase 1 continuation loop** — for each worker that returned `continuation_needed: true`, dispatch a continuation worker for that slice:

   > "Resume Phase 1 source-fidelity ingestion for slice `<slice_id>` of `<patient_code>`. The previous dispatch processed up to `<continuation_resume_from>` and stopped. Skip every file whose sidecar already exists in `<patient_dir>/ocr/` (these have lower mtime than source); ingest all remaining files in `<slice_input_path>`. Return same JSON contract; set `continuation_needed: false` if done, or `true` with next resume point if context fills again."

   Loop per-slice until all slices report `continuation_needed: false`. Slices that finished cleanly do NOT need re-dispatch; only laggards. This is more efficient than re-dispatching the whole organize.

5. **Dispatch Phase 2 Synthesis Worker** — after every Phase 1 worker reports `continuation_needed: false`, dispatch a SINGLE `general-purpose` subagent for synthesis:

   - `subagent_type: general-purpose`
   - `description: "Organize synthesis"`
   - `prompt`: the full content of [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md), with these `## Call parameters` appended:
     - `patient_dir: <absolute patient_dir>`
     - `phase1_summary: <JSON list of all Phase 1 worker results>`

   Phase 2 reads all sidecars (cross-slice), classifies into the 14 clinical buckets, builds source_inventory.json / INDEX.md / timeline.md / case_text.md / profile.json / readiness.json, runs the Step 3 review_flags audit (now WITH cross-slice visibility), and writes review_flags.md (if non-empty) + review_summary.md (always).

   Phase 2 returns: `{role, patient_dir, files_classified, md_sidecars_relocated, coverage_complete, missing_sidecars, documentation_coverage, document_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path, source_inventory_path}`.

6. **Coverage gap retry** — if Phase 2 returns `coverage_complete: false`, dispatch a retry-mini-Phase1 worker with just the missing files as input, then re-run Phase 2. Loop until `coverage_complete: true`. Most runs converge in 0 or 1 retries.

7. **Verify outputs** — parse Phase 2's returned JSON and confirm `profile.json` plus source/provenance fields validate. Missing diagnosis fields remain unknown; they limit affected patient-specific output but do not block stable general help.

8. **Describe documentation coverage** — report archive coverage without an A–F grade. `document_gaps` means existing records not found/unknown, never a recommendation to obtain a test.

9. **Display review_summary.md (MANDATORY, ALWAYS)** — read the file at `review_summary_path` and display its full content to the user. This is the **first** thing the user sees after organize — before profile card, before review_flags. It is a 1-page spot-check of extracted key fields with verbatim source citations.

   Why this is the first display: many real ingestion/transcription errors produce **internally consistent wrong values** (e.g. all 7 documents in one hospitalization copied the same wrong drug name). The 9-check `review_flags` audit cannot detect those — but a human reading `review_summary.md` can spot a wrong character in 30 seconds.

   After displaying, invite corrections as a separate patient-reported layer: "如果这里和你的理解不一致，我可以记录你的说法；正式临床字段仍需原报告更正或主诊医生核对。"

10. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after `review_summary.md`. This is a hard gate, not optional polish:
    - **If any 🔴 red flag present**: explain that the affected field cannot be used for patient-specific reasoning until an amended source or authorized clinician attestation resolves it.
    - **If only 🟡/🟢 flags**: present them as "建议核对", do not block downstream routing
    - **If `review_flags_total: 0`**: still tell the user "所有提取字段已通过 9 项可疑值检查 (格式/跨文档矛盾/临床逻辑/原始证据/数值趋势), 无待确认项 — 但仍请核对上面的 review_summary.md 速查清单"
    - A user acknowledgment may be logged, but it cannot clear a source-level clinical conflict or promote a model suggestion. Resolution requires an amended source or authorized clinician attestation.

11. **Output profile card** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "🔍 待人工确认" section pulls from `readiness.json.review_flags[]`.

    **Downstream gate**: do not pass an unresolved red-flag field into patient-specific reasoning. Unrelated safe functions and stable general education may continue with the limitation stated.

11.4. **补料信号 — 一句极短的低压信号** — right after the Profile Card. Only offer to add one existing record that is directly relevant to the user's requested artifact; do not rank clinical importance or recommend a new test. Full spec: [`references/gap-followup.md`](references/gap-followup.md).
    - Load `missing_items.json` and check whether existing documents are absent from the archive; do not use P0/P1 clinical priority.
    - 若有 → 只问患者是否已经有相关报告愿意归档，并明确“没有不代表需要补做检查”。
    - **不在 post-organize 写 `gap_asks.json` 的 pending**（避免旧的"提过就永久沉默"）——只有 §5.5/§6 真正递出一条**具体**邀请时才登记 ledger（cooldown + 上限见 `gap-followup.md` §7）。永不阻塞下游路由。

11.5. **Phase 2.5 — extraction faithfulness check (MANDATORY, runs before 段D renders)** — after Phase 2 writes structured JSON and before Step 12, perform the independent reread in [`references/organizer-prompt-phase2_5-faithfulness.md`](references/organizer-prompt-phase2_5-faithfulness.md). Compare structured values with the protected original/native text and exact source span, not merely another LLM-derived sidecar. Prefer a different extraction method or human review; a similar LLM pass is not independent evidence. This catches errors a deterministic source-shape gate cannot detect.

    On a **CRITICAL "not faithful" verdict** for a specific value, the orchestrator MUST:
    - **(a)** collect every CRITICAL `not_faithful` `{file, json_path, value}` into an **`unfaithful_values` list** and pass it to the Step-12 段D producer (as a Call parameter — see Step 12). The 段D producer is the **sole writer** of `.case_summary_data.json`, so it — not a pre-render patch — must **omit those exact values** when it builds the render data (emit the field `null` → the template's `资料缺失` placeholder) **and must not restate them in the 病情概要 narrative**. Sequencing matters: `.case_summary_data.json` does **not exist** until Step 12 creates it, so the drop happens *inside* Step 12's producer, never "before render". The bad value stays in the structured JSON (flagged) for the user to correct; only the patient-facing summary drops it. **Array-element drops are element-aware**: for a `labs[]`/`molecular_rows[]`/`treatment_lines[]` element, null ONLY the value field, KEEP the element (renders a `资料缺失` row), and set every sibling `*_class` field (`lab_class` / `line_marker_class` / `line_badge_class`) to an **explicit `""`** — never omit them, or the `__default__` fallback injects `资料缺失` into a `class="…"` attribute and `validate_case_summary_html` fail-closes the whole HTML. (The renderer also defends this: `*_class` placeholders never take the fallback — belt-and-suspenders.)
        **Denormalized-string scrub (single fix point for `one_line_condition`)**: if an unfaithful value is embedded in the **pre-computed `profile.json.summary.one_line_condition`** (it concatenates stage / histology / primary driver / current-line status), the orchestrator MUST re-stitch that denormalized convenience string with the unfaithful component dropped (→ `资料缺失` / omitted) and write the scrubbed string back to `profile.json.summary.one_line_condition`. Because the 段D header subtitle, the narrative, AND `AGENTS.md` (Step 13) all copy `one_line_condition` verbatim, scrubbing it at this one source propagates the drop to every consumer. The granular `summary.stage` / `patient_summary.diagnosis.stage` etc. stay flagged for the user to correct — only the denormalized convenience copy is scrubbed.
    - **(b)** add a source-faithfulness flag to `readiness.json.review_flags[]` with `id`, `category`, `affected_field`, `current_source_values[]`, `issue`, and `resolution_status:"unresolved"`. Do not add a model replacement value. The affected field is omitted from settled-fact surfaces until a corrected source or authorized clinician attestation resolves it; the rest of the archive continues.

    A run is **not "done"** until **all three** hold: (1) `validate_structured_outputs.py` source-shape, schema, anchor, inventory, and deterministic PII gates exit 0; (2) the semantic PII scan is clean; (3) Phase 2.5 has no unresolved critical source-faithfulness issue. A user correction is stored only as `patient_reported`; only a corrected source or authorized clinician attestation can resolve a clinician/source field.

12. **Generate 病情简要总结.html (段D)** — dispatch the renderer workflow defined in [`references/case-summary-html-prompt.md`](references/case-summary-html-prompt.md). Pass `unfaithful_values` and unresolved disputes; never pass an adjudicated clinical winner. The summary is a neutral source index: trends are descriptive only, ECOG/response are clinician-reported only, and no treatment-path field or section exists. Deterministic scripts may compute geometry and version diffs but contain no medical interpretation.

    **🔴 Ownership (compression-robust): the 段D subagent owns the WHOLE pipeline and RETURNS a passing `template_sha`.** Inside its own clean context (immune to the orchestrator's compression), the subagent runs, per [`case-summary-html-prompt.md`](references/case-summary-html-prompt.md): assemble `.case_summary_data.json` → `backfill_lab_trends.py` → `compute_version_delta.py` → `compute_sparklines.py` → `render_html_template.py` → `validate_case_summary_html.py`, fail-closed, and its return value MUST be **either** `{status:"ok", template_sha:"<64-hex>"}` (validator passed) **or** `{status:"failed", reason, exit_code}` — never inline HTML. **The orchestrator does NOT hand-write HTML and does NOT itself run the enrich/render/validate scripts** — it only (i) dispatches the subagent, (ii) checks a passing `template_sha` came back (redispatch if `status:"failed"`; **never** accept a hand-written HTML or a "done" claim without a `template_sha`), and (iii) does the **dated-snapshot `cp`** below (the one file-level step the data-only subagent is not responsible for). This is the single thing the orchestrator must remember across compression: *"did the段D subagent return a passing `template_sha`?"* — everything else lives in the subagent's fresh context. The bash below is shown as one pipeline for reference; steps (1)–(3)+validate execute **inside the subagent**, step (4) executes **in the orchestrator after** a passing `template_sha` returns:

    ```bash
    # (1) 富化 —— 自上次总结的变化：对比上一版数据快照(首版无快照 → version_delta:null)
    mkdir -p "<patient_dir>/case_summary_versions"
    prev=$(ls -1 "<patient_dir>/case_summary_versions/case_summary_data_"*.json 2>/dev/null | sort | tail -1)
    if [ -n "$prev" ]; then
      python3 scripts/compute_version_delta.py --data "<patient_dir>/.case_summary_data.json" --prev "$prev"
    else
      python3 scripts/compute_version_delta.py --data "<patient_dir>/.case_summary_data.json"
    fi

    # (1b) 保底 —— 若 producer 把 lab_trends 落成空(即便有化验),从 labs.json 的 panels 自动补齐
    #       (已有内容则 no-op,不覆盖 LLM 的病情相关选择)。放在画 sparkline 之前。
    python3 scripts/backfill_lab_trends.py \
      --data "<patient_dir>/.case_summary_data.json" --labs "<patient_dir>/labs.json" --profile "<patient_dir>/profile.json"

    # (2) 富化 —— 注入内联 SVG 趋势坐标 + 参考区间带 + 反造假门
    #     (画出的每个点必须在纵向库/labs 里查得到,否则 exit 3)
    long_arg=""; [ -f "<patient_dir>/longitudinal_observations.json" ] && long_arg="--longitudinal <patient_dir>/longitudinal_observations.json"
    python3 ../cancer-buddy-charts/scripts/render_chart.py \
      --data "<patient_dir>/.case_summary_data.json" $long_arg --labs "<patient_dir>/labs.json"
    # ↑ exit 3 = 有 series 点在源库查无 → 修数据(改回 verbatim 原值或删点)再重跑,绝不绕过
    # ↑ exit 4 = reading_note/title 里出现疗效或病情判决词 → 改写成读图指引(说明这张图怎么看、
    #            数据能不能比),不是删掉图。规则见 cancer-buddy-charts/SKILL.md §标题怎么写
    #
    # render_chart.py 是 compute_sparklines.py 的向后兼容替代:既有字段逐字节相同,
    # 新增 has_band/band_y/band_h/reference_range_text(参考区间带)与 dots[].stroke/fill(语义色)。
    # trend_charts[].reference_range 只填该次报告自带的区间,禁止套用通用参考值;填不出就留空,
    # 模板会明说"未提供可解析的参考区间"。
    # 若 cancer-buddy-charts 未随本 skill 一同安装,退回 scripts/compute_sparklines.py
    # (功能等价,但没有参考区间带与语义色)。

    # (3) 渲染
    python3 scripts/render_html_template.py \
      --template references/templates/case-summary.template.html \
      --data <patient_dir>/.case_summary_data.json \
      --out  <patient_dir>/病情简要总结.html

    # (4) ORCHESTRATOR-ONLY, runs AFTER the subagent returned a passing template_sha.
    # Dated version control — snapshot every generation. 病情简要总结.html at the patient
    # root is ALWAYS the latest (canonical; what downstream/patient links point to). Immutable
    # dated copies accumulate under case_summary_versions/, so a patient who shared an older
    # summary can still retrieve exactly what they shared, and a re-render never destroys the
    # prior version. (date = generation date; same-day re-render suffixes _2, _3, …)
    # BOTH the HTML and the enriched data JSON are snapshotted — the data snapshot is the
    # comparison base for the NEXT generation's compute_version_delta.
    ver_date=$(date +%F)
    snap="<patient_dir>/case_summary_versions/病情简要总结_${ver_date}.html"
    dsnap="<patient_dir>/case_summary_versions/case_summary_data_${ver_date}.json"
    n=2; while [ -e "$snap" ]; do snap="<patient_dir>/case_summary_versions/病情简要总结_${ver_date}_${n}.html"; dsnap="<patient_dir>/case_summary_versions/case_summary_data_${ver_date}_${n}.json"; n=$((n+1)); done
    cp "<patient_dir>/病情简要总结.html" "$snap"
    cp "<patient_dir>/.case_summary_data.json" "$dsnap"
    ```

    The renderer is a zero-medical-logic template engine: it only substitutes `{{key}}` and expands `<!-- LOOP -->` / `<!-- RENDER_IF -->` blocks from the data, so CSS/DOM stay 1:1 and source clinical strings remain traceable. It stamps a `template_sha256:` provenance comment proving the HTML came from the template. Patient identity is minimized; any `null` field maps to the `资料缺失` placeholder. The patient-root `病情简要总结.html` is the latest pointer; dated snapshots remain immutable.

    **🔴 TEXT/HTML GATE — 段D HTML is complete when both hold:**
    1. `病情简要总结.html` was produced by `render_html_template.py` from `references/templates/case-summary.template.html` (**rendered, not hand-written**). A subagent that pastes HTML inline fails this gate.
    2. `python3 scripts/validate_case_summary_html.py --html <patient_dir>/病情简要总结.html --template references/templates/case-summary.template.html --profile <patient_dir>/profile.json --data <patient_dir>/.case_summary_data.json` exits 0 (shape + PII + provenance invariants hold, **plus the (j) core-completeness gate** — `--profile`/`--data` hard-fail if a core singleton **分期 / 驱动基因 / 当前方案** is present in source but dropped from the summary; labs/comorbidities are NOT gated — they're curated for a one-pager).

    The structured-output acceptance门 is separate: `python3 scripts/validate_structured_outputs.py <patient_dir>` exits 0 once the structured JSONs + anchors validate, the text sidecars pass the PII residue rescan, `source_inventory.json` is complete (every content unit carries a `raw_path` + a text-masked sidecar), and the case-summary HTML shape holds. Surface in the final report to the user the **`template_sha`** echoed by `validate_case_summary_html.py` (proof the template was used). Never mark a medical source `persist:false` merely to make this gate pass; if a formal artifact cites its sidecar, keep it `persist:true`. Uploaded originals in `raw/` remain access-controlled source records under the host's retention/deletion policy; derived-sidecar masking is not a claim that the original is anonymous.

13. **Generate AGENTS.md (agent-facing recall pointer)** — deterministically fill [`references/templates/agents-md.template.md`](references/templates/agents-md.template.md) (organize-owned template, next to `case-summary.template.html`; organize is the sole filler — the *generated* `AGENTS.md` is what the cancer-buddy family + vmtb consume) and write it to `<patient_dir>/AGENTS.md`. This is the **cross-session discovery + recall** pointer: harnesses that auto-load `AGENTS.md` from the cwd (pi, Claude Code) then have, in *every* session whose cwd is inside the patient dir, the patient identity + the routing table + the two-layer drill-down rule + the verbatim-citation/no-fabrication floor — solving "patient organized records but a later session can't find/read them" without the cancer-buddy skill having to be invoked first.

    **Always runs on the first build** (a `full` organize run reaches this step unconditionally). It depends only on `profile.json` — **not gated by the 段D HTML outcome** above; generate it even if 段D was deferred or failed its gate. Placed after the profile card + review/correction steps so it reflects any field the user just corrected.

    Only **two placeholders** are injected, **copied verbatim from `profile.json` (no LLM synthesis)**: `{{patient_code}}` ← `profile.json.patient_code`; `{{one_line_condition}}` ← `profile.json.summary.one_line_condition` (`资料缺失` when null). Claude Code reference binding:

    ```bash
    python3 - "<patient_dir>" references/templates/agents-md.template.md <<'PY'
    import json, pathlib, sys
    pdir, tpl = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    d = json.loads((pdir / "profile.json").read_text())
    olc = (d.get("summary") or {}).get("one_line_condition") or "资料缺失"
    out = tpl.read_text().replace("{{patient_code}}", d["patient_code"]).replace("{{one_line_condition}}", olc)
    (pdir / "AGENTS.md").write_text(out)
    PY
    ```

    **VERIFY, don't re-author**: after writing, the run must confirm the written `AGENTS.md` is the **fully-filled template** (the rich routing table + drill-down rule + citation floor are present and the two placeholders resolved to real values, not left as `{{patient_code}}`/`{{one_line_condition}}` or a bare stub) — if a stub was produced, re-fill from `references/templates/agents-md.template.md`. Never author a new template; the template is already rich and is the only source.

    The full citation **rendering** spec (角标 + 末尾脚注 format) stays in [`../cancer-buddy/SKILL.md`](../cancer-buddy/SKILL.md)「来源引用」节 — single, patient-agnostic source of truth. AGENTS.md carries only the **self-contained floor** (cite via the fact's own `source_refs[]`, never fabricate a hospital name), so the floor holds even in a bare session where no skill is loaded; the skill, when invoked, adds the richer rendering on top (defense-in-depth, floor vs ceiling). Idempotent — a later `incremental` / `upload_reconciliation` run re-fills it from the current `profile.json` (it holds no user-curated content, so overwrite is safe). A pre-existing archive that lacks `AGENTS.md` (built before this feature) is backfilled the same way — see `../cancer-buddy/SKILL.md` 档案读取协议. Runtime-neutral: any host writes the same `AGENTS.md` from the same two `profile.json` fields; non-CC hosts may use their own templating.

14. **无关文件处置门 (段E)** — quarantine `likely_unrelated` and `possibly_relevant` files under `99_无关文件/`, show an item-specific preview/reason, and explain that silence means hold. No model-confidence branch may delete automatically.

    Resolution paths: explicit delete confirmation; reclassify into the proper archive; or hold. Silence, deferral, “随便”, and closing the chat all hold. Medical, medication, symptom, wound, device, billing and borderline material defaults to hold.

    Record every isolated/deleted/reclassified/held action in `update_log.json.relevance`; every deletion entry must include the user's explicit item-specific confirmation.

15. **Conversation-incremental capture (段C, on demand)** — archive confirmed statements only as `patient_reported`/`caregiver_reported` with a conversation anchor. They never overwrite source/clinician fields or become clinical truth through confirmation.

16. **Upload reconciliation (扩段C, on re-upload)** — classify duplicate/later version/formal amendment/conflict under `upload-reconciliation.md`. Preserve immutable originals and anchors. Conflicting clinical values remain `disputed`; a patient cannot select a canonical winner. Only a formal amended source or authorized clinician attestation resolves the field.

17. **Finalize — strip staging cruft (always, at end of a run)** — remove any stray `.DS_Store` files anywhere under `<patient_dir>`, and remove the `ocr/` staging dir if it is empty (after Phase 2 has relocated every sidecar into its lazily-created clinical bucket, `ocr/` should be empty; a non-empty `ocr/` means a sidecar wasn't placed — leave it and surface as a warning, don't silently delete). This keeps the archive (and any later export) free of OS cruft and an orphan empty staging dir.

    ```bash
    find "<patient_dir>" -name .DS_Store -type f -delete
    rmdir "<patient_dir>/ocr" 2>/dev/null || true   # only removes ocr/ if empty
    ```

18. **Purpose-limited export (on demand)** — authenticate the actor; verify authority; confirm recipient,
scope, purpose, de-identification choice, and expiry; select only the necessary relative paths; then rerun
source-faithfulness and both PII layers. If any gate is unavailable or has findings, do not export.
`export_share.py` then runs the structural gate and excludes `raw/` plus protected provenance/build files.
The host records the authorization and enforces revocation/expiry. A clean scan reduces risk but does not
guarantee anonymity.

### Purpose-limited export

Never copy the whole patient directory. After the authorization flow above, call the exporter with an
explicit allowlist and a host audit reference:

```bash
python3 scripts/export_share.py <patient_dir> --out <dest> \
  --include profile.json \
  --include 04_诊断与分期/病理报告/<selected-sidecar>.md \
  --recipient <recipient> \
  --purpose <purpose> \
  --expires-at <ISO-8601> \
  --authorization-ref <host-audit-id>
```

The script rejects broad/protected paths, validates each selection stays inside the patient directory,
requires future expiry metadata, and writes `_SHARE_MANIFEST.json`. It refuses to run when the structural
gate fails. The host remains responsible for legal basis, minimum-necessary selection, secure transfer,
recipient verification, expiry/revocation, and the audit trail.

## Definition of Done（终态硬门 —— 结束前必过、必贴，抗压缩的单一收口）

done 判据以前散在 Step 7 / 11.5 / 12 / 13 和好几个 validator 里；压缩后容易只记得"产出了文件"就自报完成。这里把它收成**一个终态清单**：以下**全绿之前，本次 organize 未完成**，不许对用户说"整理好了"。

1. **结构化验收门 exit 0 且已贴输出**：`python3 scripts/validate_structured_outputs.py <patient_dir>` 返回 0（schema + anchors + PII shape + source-shape fidelity + source inventory + HTML form/provenance）。它不判断临床值是否正常或重要。把回显的 **`template_sha`** 贴给用户。
2. **段D HTML 带 provenance**：`病情简要总结.html` 含 `<!-- template_sha256: … -->` 注释（顶部不变量第 1 条）。手写 HTML 没有它，会在第 1 项里 fail。
3. **PII Layer-1 语义扫描 clean**：`references/pii-rescan-prompt.md` 子代理返回 `clean=true`（覆盖 sidecar + 合成下游面 + 交付面）。
4. **Phase 2.5 忠实度问题已按受影响字段处理**：每个 `not_faithful` 值从患者摘要中置 `null`，并写 source-faithfulness flag；只有更正来源或授权临床签认可恢复为 settled fact。其余字段不被全局阻断。
5. **AGENTS.md 已生成且非 stub**（Step 13：两个占位符已解析成真值）。

自检话术（贴给用户的收尾里体现）：`validate_structured_outputs.py exit 0 ✅ · template_sha=<…> ✅ · PII clean ✅`。任一非绿 → 回到对应 Step 修复重跑，**不要**把一份形不合规/缺 provenance/带 PII 的产物留在 `patient_dir` 或对用户报完成。

## Runtime adaptation

The Workflow above (Step 2–5: `glob`-based slicing → parallel `Agent` Phase-1 source-fidelity ingestion fan-out → continuation loop → single `Agent` Phase-2 reduce, plus native/deterministic extraction, reviewable LLM assistance, and adapter commands such as `sips` HEIC decode) is the **Claude Code reference binding** — one concrete way to drive organize, not the contract. The runtime-neutral **behavior contract** (what each step produces / when it may write / which invariants hold, with zero tool names) lives in [`references/organize-contract.md`](references/organize-contract.md); the per-host fill-ins are in [`references/runtime-bindings/`](references/runtime-bindings/) (`claude-code.md` = the mechanism documented here; `headless-codex.md`; `_template.md` for OpenClaw/OpenCode/other agents).

What this means for non-CC hosts:

- A headless / single-process host (codex GPT-5.5, workbuddy, OpenClaw/OpenCode, Cursor, …) **drives its own steps** — the `Agent` fan-out + reduce, bounded vision/file-context assistance, and `sips` decode are reference mechanisms, not requirements. It may run Phase 1 sequentially and adapt formats with cross-platform commands, but it still preserves native/deterministic character output and may use model vision only as a separately recorded assist/review layer.
- Whatever the binding, it produces the same canonical output set and honors the same invariants: source strings plus provenance are retained; reported and normalized layers stay separate; uploaded originals remain in `raw/`; derived and delivered surfaces are scanned for PII; unconfirmed user talk does not become clinician fact; no irreversible deletion occurs without explicit item-specific confirmation.
- The five seams (编排 / LLM 输入源 / 格式适配 / 确认门 / 存储) and each host's fill-in are the matrix in `organize-contract.md` §6. The `MAX 15 image files per worker` rule in Step 2 is a Claude many-image budget feature → **host-tunable** (don't slice / slice to the host's own budget); it is not a contract invariant.

Claude Code does not change: the mechanism in Step 2–5 is preserved verbatim as the reference binding, the neutral layer is added on top, and the CC path regresses identically.

## Why fan-out + reduce instead of single-pass

The original design was a single subagent processing every input file sequentially. A 73-image archive took ~33 minutes. Splitting into Phase 1 (parallel per-slice source-fidelity ingestion) + Phase 2 (cross-slice synthesis + audit) gives three benefits:

1. **Speed**: 3 parallel Phase-1 LLM ingestion workers + 1 Phase-2 finishes in roughly the time of the SLOWEST slice + the synthesis pass — ~3× faster on multi-hospitalization archives in practice.
2. **Anti-anchoring is stronger**: each Phase 1 worker only sees its slice (one hospitalization), so the narrative window the model could anchor on is shorter. Cross-slice contradictions are caught explicitly in Phase 2's Step 3 review_flags audit (which has the deterministic cross-doc check) rather than being smoothed over by a single agent's running narrative.
3. **Better failure isolation**: if one slice's worker hits context exhaustion, only that slice retries (continuation loop). Slices that finished cleanly are not re-dispatched.

Single-pass is preserved for small inputs (≤ 15 files and no actionable sub-directory split — the governing rule is the Step-2 slicing table above) — the parallelism overhead isn't worth it.

## Incremental mode

When `<patient_dir>` already has `update_log.json`, the caller may pass `run_mode: "incremental"` to Phase 2. In that mode:

- Phase 1 only re-ingests files that are new under `raw/` or whose source mtime is newer than their sidecar. Other slices are skipped.
- Phase 2 reclassifies only the new sidecars; existing bucket assignments are preserved.
- Top-level artifacts (`case_text.md`, `timeline.md`, `patient_summary.json`, `timeline.json`, `molecular.json`, `treatment_lines.json`, `labs.json`, `comorbidities.json`, `longitudinal_observations.json` (when timeseries data is present), `source_inventory.json`, `review_summary.md`, `missing_items.json`) are rewritten only when their content would actually change. (`AGENTS.md` is re-filled from `profile.json` per Step 13.)
- `update_log.json` gets a new entry with `run_mode: "incremental"`, `added_files`, `removed_files`, `affected_summaries`, `triggered_by`, `reason`.
- `profile.json.alias` is user-controlled and never generated or overwritten by clinical ingestion.
- **段D summary freshness** — see "Case-summary freshness gate" below; an incremental run that touches summary-source fields does NOT silently re-render the HTML, it asks first.

Use full mode (`run_mode: "full"`, default) for the very first organize, or whenever the patient indicates major changes ("我换了治疗方案", "重新做了一次基因检测") where rewriting the whole narrative is cleaner than merging.

### Case-summary freshness gate (段D re-render prompt)

`病情简要总结.html` is generated once (Step 12) and is NOT auto-regenerated, because re-rendering is a user-visible artifact the patient may have shared. Any later run that **changes a field the summary draws on** — incremental, `upload_reconciliation`, conversation-incremental (段C), **or a full-run 段E `回收` reclassify (Step 14) that moves a real medical file back into the clinical buckets** — must, after writing, **detect staleness and prompt the user** rather than regenerate silently:

- **Detect**: the summary is stale if any of `profile.json` / `patient_summary.json` / `molecular.json` / `labs.json` / `treatment_lines.json` / `timeline.json` / **`longitudinal_observations.json`** was modified after `病情简要总结.html`'s mtime (or `update_log.json.affected_summaries` includes one of them, or a 段E `回收` in this run re-added a summary-source fact). `longitudinal_observations.json` matters specifically because a **new follow-up lab / new timepoint** changes the trend curves and the 自上次总结的变化 delta even when no scalar field moved — the single most common "patient supplemented material" case. If the HTML doesn't exist yet, there is nothing to refresh — skip.
- **Prompt (rendered in `profile.json.locale`)**: e.g. zh — "你的病情记录有更新（<改了什么>）。要我重新生成一份病情简要总结吗？" / en — "Your record changed (<what changed>). Want me to regenerate the case summary?" Offer 重新生成 / 暂不.
- **Act**: only on explicit yes, re-dispatch the Step 12 段D worker (same `case-summary-html-prompt.md` → `render_html_template.py` → validate). On no/defer, leave the existing HTML and record `case_summary_stale: true` in `update_log.json` so the next session can re-offer. The regenerated HTML follows `profile.json.locale` (the summary template is fully localized — `references/templates/case-summary.template.html` string table).
- **Versioned, never destructive**: every (re)generation writes a new dated snapshot to `case_summary_versions/病情简要总结_<date>.html` and updates the root `病情简要总结.html` to the latest (Step 12). So even if the patient defers a refresh, the version they already shared is preserved on disk, and accepting a refresh never erases the prior copy. Note: because the original Step-12 generation in a full run happens at Step 12 — *before* the Step 14 段E `回收` — a same-run reclaim that the user accepts re-renders a fresh dated version rather than leaving the shared one silently stale.
- This is the confirm-gate floor applied to the summary: no silent rewrite of a patient-facing artifact, and no silent loss of a prior one.

**Re-uploading files onto an existing archive** is a distinct entry: pass `run_mode: "upload_reconciliation"` instead of plain `incremental`. That mode runs the 段E relevance gate on each new file, then an LLM new/supersede/conflict relation判断 → a diff card (替换? 并存? 忽略?) gated by the **same "先确认" door段C uses** — unconfirmed re-uploads never write formal fields, and 替换 archives the superseded doc to `_superseded_<ts>/` rather than deleting it. Full logic: [`references/upload-reconciliation.md`](references/upload-reconciliation.md). Plain `incremental` (above) is for newly-added files that don't supersede or conflict with an existing doc.

## Conversation-incremental mode (段C)

When the patient or caregiver is *chatting* about their condition (not handing over files) and a `<patient_dir>` with an existing `update_log.json` already exists, the caller may run `run_mode: "conversation_incremental"` to capture archivable facts that surface in the dialogue. Dispatch a `general-purpose` subagent with the full content of [`references/conversation-incremental-prompt.md`](references/conversation-incremental-prompt.md), appending `## Call parameters`: `patient_dir`, `conversation_turn` (verbatim user message + context), `turn_timestamp` (ISO-8601), `actor_role`.

The flow: an LLM detects candidate patient/caregiver-reported information (possible new diagnosis wording, a reported lab value, treatment change, symptom or function description) → presents a **diff card** with the speaker's words → the user confirms that the note faithfully captures what they said. Confirmation archives only the `patient_reported` or `caregiver_reported` layer; it never turns stage, ECOG, response or progression into clinician-verified fact. Provenance uses `[[src:conversation:<ISO8601>]]`. Conflicts remain side by side with `disputed` status and originals are preserved. This mode does not re-ingest files or rerun synthesis; major record changes route to a full re-organize.

## Optional alias

The host may store a user-chosen non-clinical, non-identifying alias in a protected profile field. Phase 2
does not generate one from diagnosis, year, institution, name, or record identifiers, and does not expose it
as a filesystem symlink. The random `patient_code` remains the storage locator and is not authentication.

## patient_code collision

If the generated `patient_code` (e.g. synthetic `PT-A1B2C3D4E5`) already exists under the patients root, the subagent appends `_2`, `_3`, etc., and announces the assigned code in the summary.

## Configurable root

The `patients/` root resolves in order: `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Override by exporting one of those. Shared with vmtb-skill.

## Safety

Organize does not make medical recommendations. Still:

- Never fabricate fields — when a value is truly unreadable in the source, the subagent writes `null` (JSON) or `[OCR_UNCERTAIN]` (text) and surfaces it as a gap.
- Text masking only masks PII in the sidecar body — it never alters clinical characters (anti-anchoring). The MD sidecar is the downstream-only read source and must not carry plaintext PII. The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) are scanned by pii_rescan.py for name / path / account leaks. De-identification therefore covers the sidecar body AND every delivered surface.
- Downstream sub-skills apply the full `safety-guardrails.md` rule set when they read what organize produced; wrong data here poisons every downstream report.
- Organization preserves original bytes under host access control and uses source-fidelity sidecars for derived
  outputs. It does not promise anonymity or indefinite retention. Patient-facing summaries and exports apply
  task-specific authorization, purpose limitation, and data minimization; age, dates, institution, and other
  quasi-identifiers are included only when necessary. PII semantic and deterministic scans cover derived
  sidecars, synthesized artifacts, and delivered surfaces.

## Next-step guidance

After successful organize, route the patient to the most relevant shipped companion based on their initial
question. A clinical-decision request goes to the treating team; never auto-install or imply that another
tool supplied a clinical conclusion:

- Newly diagnosed, wants to understand their disease → `cancer-buddy-education` (patient self-study handbook), or hand back to the meta `cancer-buddy` router.
- Has a gene report and wants treatment guidance → organize the report and questions, then route the decision
  to the treating team or a formal second opinion. Do not interpret actionability or choose treatment.
- Looking for trials → `cancer-buddy-find-care` (finds currently listed sites and official contacts; no eligibility judgment and no automatic installation of another skill).
- A clinic visit is coming up → `cancer-buddy-visit-prep`.
- Asking whether comparable cases have been published → `cancer-buddy-case-precedent`, described explicitly as a biased case-report search that cannot generate treatment direction or prognosis. Never auto-search.

## Role behavior

Authoritative matrix in `../../references/roles.md`. For this skill:

- **Role = patient**: First-person. "帮我整理我的病历" → produce source-attributed archive files. Patient statements remain `patient_reported` and do not overwrite clinician-source facts.
  - *Disclosure*: explain that organizing records may surface diagnosis details. A capable patient's explicit request for their own information is not overridden by family suppression; for another viewer, show only authorized content and route capacity/代理争议 to the treating institution.
- **Role = caregiver**: Second-person. "帮你家人整理报告". Require host authorization for the task
  and keep authorization/contact data outside the clinical summary in the host's access-control system.
  Tone may acknowledge caregiver workload without implying decision authority.
- **Role = family**: if the viewer is authorized for this task, operate only within that documented scope;
  otherwise provide a blank organization checklist without reading/writing patient records. Relationship
  labels alone neither grant nor deny authorization.


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

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) — native/deterministic extraction, LLM-assisted review, independent high-risk-field reread
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — source-preserving synthesis, review flags, structured JSON, document gaps, and audit log
- [conversation-incremental-prompt.md](references/conversation-incremental-prompt.md) — 段C conversation-incremental worker prompt: detect archivable facts in chat → diff card → user-confirmed write to profile field / timeline row with `[[src:conversation:<ISO8601>]]` provenance + `patient_curated` tag; unconfirmed talk never written
- [relevance-gate.md](references/relevance-gate.md) — 段E relevance triage and quarantine; silence always holds, explicit item-specific confirmation is required for deletion
- [upload-reconciliation.md](references/upload-reconciliation.md) — 扩段C re-upload reconciliation: LLM new/supersede/conflict relation判断 (not hardcoded same-name-date) → diff card 替换?/并存?/忽略? reusing段C's "先确认" gate; 替换 archives old doc to `_superseded_<ts>/` (not deleted) + anchor remap; conflict never silently overwritten; introduces no new auto-deletion; `run_mode: "upload_reconciliation"` update_log
- [organizer-prompt-phase2_5-faithfulness.md](references/organizer-prompt-phase2_5-faithfulness.md) — independent source-faithfulness verification; `not_faithful` values are omitted from settled-fact surfaces and flagged without proposing a replacement
- [case-summary-html-prompt.md](references/case-summary-html-prompt.md) — 段D worker prompt: read text-masked JSONs → fill the gold-standard template 1:1 → `病情简要总结.html`; subagent generates only the 病情概要 narrative, every other section is field-mapping; coarse-grained identity, `null` → 资料缺失
- [templates/case-summary.template.html](references/templates/case-summary.template.html) — 段D gold-standard HTML/CSS template (1:1 reproduction target, not "style-similar")
- [templates/agents-md.template.md](references/templates/agents-md.template.md) — Step 13 agent-facing recall pointer template (organize-owned, next to `case-summary.template.html`; the *generated* `AGENTS.md` is consumed by the whole cancer-buddy family + vmtb): patient identity + routing table + two-layer (top-level JSON → sidecar) drill-down + verbatim-citation/no-fabrication floor; only `{{patient_code}}` + `{{one_line_condition}}` injected verbatim from `profile.json`. Auto-loaded by harnesses (pi / Claude Code) from the cwd so any session can answer from the archive without first invoking cancer-buddy
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [gap-followup.md](references/gap-followup.md) — ask-once invitation to add an existing record needed for the requested artifact; never recommends a new test or ranks clinical importance
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [references/schemas/](references/schemas/) — Draft 2020-12 JSON Schemas for the 6 structured outputs + conditional `longitudinal_observations.json` + `missing_items.json` + `source_inventory.json`
- [references/schemas/anchor-contract.md](references/schemas/anchor-contract.md) — `[[src:...]]` anchor token syntax + coverage + path validity contract (bucket-relative file anchors + `conversation:<ISO8601>` anchors; `ocr/` prefix deprecated)
- [references/checklists/](references/checklists/) — cancer-type minimum-data checklists driving `missing_items.json`
- [scripts/validate_structured_outputs.py](scripts/validate_structured_outputs.py) — **structured-output acceptance门** (one entry, aggregated exit code): structured-output schema + anchor validation **plus** PII residue rescan of the text sidecars AND the delivered surfaces (`pii_rescan` — the text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html are scanned for name / path / account leaks, so de-identification covers the sidecar body AND every delivered surface), a no-bypass check that formal source citations cannot be marked `persist:false`, required `source_inventory.json` (every content unit carries a `raw_path` + text-masked sidecar), and case-summary HTML shape+provenance (`validate_case_summary_html`).
- [scripts/render_html_template.py](scripts/render_html_template.py) — generic, stdlib-only (no jinja2) HTML template engine with **zero medical/case logic**: substitutes `{{key}}` and expands `<!-- LOOP -->` (0..N, data-driven) / `<!-- RENDER_IF -->` / `<!-- RENDER_IF_NOT -->` (empty section → `资料缺失` placeholder, never deleted) from a data JSON; stamps a `template_sha256:` provenance comment. Used by 段D to render `病情简要总结.html` from `templates/case-summary.template.html`.
- [scripts/validate_case_summary_html.py](scripts/validate_case_summary_html.py) — case-summary HTML form validator. Context-dependent minimization of age and other quasi-identifiers remains a producer/authorization review, not a regex claim that they are always safe.
- The PII gate is **two independent layers** (trust-but-verify): **Layer 1** = the semantic agent scan [`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md) — the PRIMARY, generalizing scan that flags ANY identifying category (出生地/籍贯/职业/家属姓名/民族/签名/检验号 …) by meaning over sidecar bodies, synthesized downstream surfaces (case_text.md/profile.json/…), AND delivered surfaces; **Layer 2** = [scripts/pii_rescan.py](scripts/pii_rescan.py) — the deterministic, zero-network SHAPE floor, scoped by surface: **on sidecar bodies** it runs only the pure-shape standalone arms (身份证18位/手机/座机/email/SSN/E.164/≥11位数字ID); **on delivered + synthesized surfaces** it ALSO runs the `/Users/`绝对路径/云账号/identity-denylist-token arms (those never appear in OCR bodies). Independent second opinion. Either layer's finding fails the gate. Layer 2 skips `[PII_MASKED]` values + the `## PII` trailer; it is a detector, not an auto-rewriter (re-masking is a per-line judgement). De-identification covers the sidecar body, the synthesized downstream artifacts, AND every delivered surface.
- [scripts/export_share.py](scripts/export_share.py) — technical export helper that excludes `raw/` and runs
  structural gates. It does not grant sharing authority or prove anonymity; the caller must first authenticate,
  confirm recipient/scope/purpose/expiry, and select only the minimum necessary files.
- [../../references/preflight.md](../../references/preflight.md) — shared permission, disclosure, source-fidelity and affected-field gate
- [../../references/i18n.md](../../references/i18n.md) — shared locale contract: preserve the source string and add a labeled translation when helpful
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
- [../../references/disclosure-behavior.md](../../references/disclosure-behavior.md)
