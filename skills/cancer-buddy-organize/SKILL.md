---
name: cancer-buddy-organize
description: "Organize patient medical records (PDF/images/docx/spreadsheets/archives) into a canonical patients/<patient_code>/ directory via LLM-first Markdown ingestion — the text-masked MD sidecar is written by the LLM, never by dumb OCR/parsers. Produces profile.json, timeline, readiness.json, bucket-co-located text-masked sidecars, 6 schema-validated structured JSONs, missing_items.json, update_log.json, and a 1:1 病情简要总结.html generated from text-masked JSON/MD (the full artifact set is enumerated in ## Outputs). Uploaded originals are kept verbatim in a raw/ vault (never pixel-redacted, never deleted); the only content-level desensitization is the sidecar text masking, and the raw/ on-disk filename is de-identified by Phase 1. The patient-facing 段D HTML keeps precise age for clinical-trial matching while masking name/DOB/birthplace/occupation. Use when the user hands over a folder of medical records, or says 病历整理, 我有一堆报告, 帮我整理报告."
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
- Any other sub-skill detects missing `profile.json` / `readiness.json` and prompts the user to run organize first.

## Inputs

- Path to a folder OR a single PDF/DOCX OR a zip/rar/7z/tar.gz archive.

## Outputs

Written under `patients/<patient_code>/`:

- `INDEX.md` (first line: `# patient_code: <code>`)
- `AGENTS.md` — **agent-facing cross-session recall pointer** (filled from `references/templates/agents-md.template.md`). A harness that auto-loads `AGENTS.md` from the cwd (pi, Claude Code, …) gets the patient identity + a routing table (which structured file answers which question) + the two-layer drill-down rule (top-level JSON → `source_refs`/`source_inventory.json` sidecars) + the verbatim-citation / no-fabrication floor — so any session whose cwd is in this patient dir can answer from the archive **without first invoking the cancer-buddy skill**. Two fields injected verbatim from `profile.json` (`patient_code`, `summary.one_line_condition`); the static body is patient-independent.
- `profile.json` (conforms to `../../references/patient-profile-schema.md`; now also carries `alias` field)
- `timeline.md` (human-readable treatment timeline; every line ends with at least one `[[src:...]]` anchor)
- `readiness.json` — coverage grade + `review_flags[]` (MTB readiness + 9-check suspicious-value audit, including cross-patient name collision + anchor-coverage gap + filename↔content mismatch)
- `review_flags.md` — auto-generated human-readable rendering of `readiness.json.review_flags[]` (only written when array non-empty)
- `review_summary.md` — **always written**: 1-page checklist of extracted key fields with verbatim source citations, for user spot-check (catches internally consistent but wrong ingestion that review_flags can't)
- `case_text.md` (consolidated narrative; every factual sentence anchored via `[[src:<bucket>/<canonical>.md#L<a>-L<b>]]` — bucket-relative, the text-masked MD that now lives next to its image)
- `update_log.json` — append-only audit trail of every full / incremental run (timestamps, added/removed files, affected summaries, readiness deltas)
- **6 structured JSON outputs** (schema-validated against `references/schemas/*.schema.json`):
  - `patient_summary.json` — demographics + diagnosis + current_status rollup
  - `timeline.json` — machine-readable mirror of `timeline.md`
  - `molecular.json` — NGS variants + IHC + MSI/MMR + TMB
  - `treatment_lines.json` — ordered lines of therapy
  - `labs.json` — lab panels with serial values
  - `comorbidities.json` — conditions + long-term meds + allergies
- `missing_items.json` — cancer-type checklist diff (driven by `references/checklists/<cancer_type>.yaml`)
- `gap_asks.json` — **append-only ask-once ledger** for the 补料邀请 behavior (Step 11.4 / Q&A trigger). Records each high-value (P0/P1) missing-data ask already surfaced to the patient — `{item_key, priority, category, item, asked_at, surfaced_at_trigger, status: pending|provided|declined}` — so the same gap is never re-asked (spec: [`references/gap-followup.md`](references/gap-followup.md) §7).
- `source_inventory.json` — one entry per content unit: `file_id`, `source_id`, `original_path`, `raw_path` (deep-link to the verbatim original in `raw/`), `page_range`, LLM read mode, adapter provenance, sidecar path, bucket path, modality, and `persist`. Conforms to `references/schemas/source_inventory.schema.json` (`source_inventory_v1`).
- `01_身份与基础信息/`…`14_患者自管补充/` (14 clinical-domain buckets, scheme_version 3 — see `references/bucket-taxonomy.md`). Each bucket holds **only the text-masked MD sidecars** `<bucket>/<canonical>.md` (canonical = `<YYYY-MM-DD>_<doc_type>_<hospital>`, 4-level hospital fallback; the downstream-only read source — no plaintext PII). **The uploaded original is NOT copied into the bucket** — it lives once in `raw/`, deep-linked from each sidecar via `source_inventory.json.raw_path`.
- `raw/` — hidden vault. raw/ keeps every uploaded original's BYTES verbatim (never byte-altered, never pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by Phase 1 (identity token stripped; if the whole basename is the identity, fall back to `<source_id>.<ext>`) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared surface. The verbatim original filename is preserved ONLY in raw/_FILENAME_MAPPING.md (Phase-1, schema `verbatim_upload_name | deid_raw_name | source_id`; inside raw/, excluded from export, never a delivered/scanned surface). Phase 2 additionally writes raw/_SIDECAR_MAP.md (the de-identified raw→sidecar→bucket nav table; contains NO verbatim name) — a separate file so it never clobbers the verbatim audit table. Each sidecar deep-links back to its original via `source_inventory.json.raw_path`. See `references/bucket-taxonomy.md` §4–§5.
- `longitudinal_observations.json` — parsed time series from `timeseries`/trended `structured` sources (wearable / PRO / lab trends); raw export filed in `10_随访与监测`. Conforms to `references/schemas/longitudinal_observations.schema.json` (`longitudinal_observations_v1`).
- `病情简要总结.html` — 段D one-page case summary, 1:1 against the gold-standard template, generated after the Profile Card from text-masked JSON only (never raw images). Includes a **关键趋势 hero chart** + **实验室指标 trend rows** (inline-SVG sparklines drawn from `longitudinal_observations.json`, treatment-line changes overlaid on the same axis) and a **自上次总结的变化 delta strip** diffing the previous snapshot — so a patient who keeps adding follow-up records sees their trajectory and what changed. The patient-root file is always the **latest**; immutable **dated versions** accumulate under `case_summary_versions/病情简要总结_<date>.html` (a re-render never destroys the version a patient already shared).
- `case_summary_versions/` — dated immutable snapshots of every 段D generation: both `病情简要总结_<date>.html` (patient-facing history) and `case_summary_data_<date>.json` (the render data, which is the comparison base for the next generation's 自上次总结的变化 delta).

Additionally, at the patients-root level (one level above `<patient_code>`):

- `<alias>/` symlink → `<patient_code>/` (business-readable, when `profile.json.alias` is set; format `{patient_id_short}_{cancer_code}_{year}`, e.g. `17CE02_CRC_2019`)
- `alias_map.json` (when symlinks aren't supported, e.g. Windows / restricted containers)

A **derived, on-demand export** (not part of the canonical archive) is produced by `scripts/export_share.py <patient_dir> --out <dest>`: a shareable copy of the patient dir that EXCLUDES `raw/` and strips `.DS_Store` + empty `ocr/`, gated by `validate_structured_outputs.py` passing first (see **Safe export** below). It is written to `<dest>`, never under `<patient_code>/`.

## Patient-dir file map (read/consume relationships)

A consumer answering questions on an **already-organized** `patients/<patient_code>/` reads **selectively**, in the order defined by the patient-facing read protocol (`../cancer-buddy/SKILL.md` → 档案读取协议). This is the role map:

| File | Role | Read it when |
|---|---|---|
| `profile.json` | **Slim canonical first-read snapshot** (`cancer_buddy_profile_v3`): identity + `locale` + denormalized `summary` + `latest_status` | **Always first** — who is this + current state + language |
| `readiness.json` | Coverage grade + `blocking_gaps` + 9 `review_flags` | **Second** — honesty gate; if the asked domain is a blocking gap, say what's missing |
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
- **Clinical entities are never translated** — drug names, gene/variant symbols, TNM/stage strings, numbers + units, biomarker labels, and the document's own `doc_type` stay verbatim in their source form (mistranslation is a P0 medical-safety bug, see `../../references/safety-guardrails.md`).
- An explicit user language override ("用英文" / "answer in English") updates `profile.json.locale` and wins over auto-detection.

## Workflow

1. **Resolve input** — confirm the user-supplied path with them. For archives, unpack to `/tmp/cb-unpack-$$/` first (zip / rar / 7z / tar.gz / single pdf-or-docx). After unpack, the **resolved input directory** (`$src`) is what Step 2 plans against.

2. **Plan slicing (single-pass vs fan-out)** — `glob $src` for immediate subdirectories, count files, and decide slice boundaries.

   **MAX 15 image-like inputs per Phase 1 worker on Claude Code.** Claude has a per-conversation total-image budget when many images/rendered pages are loaded into a single context. A worker that tries to ingest 25+ HEIC images or rendered PDF pages in one dispatch can hit image/context limits partway through and abort with partial output. Host-specific adapters may choose a different budget.

   Slicing rules:

   - **Single-pass mode**: ≤ 15 files total → one Phase 1 worker
   - **Sub-directory fan-out**: ≥ 2 subdirectories AND each subdir has ≤ 15 files → one worker per subdir
   - **Sub-directory fan-out with internal split**: ≥ 2 subdirectories AND any subdir has > 15 files → split each oversized subdir into halves/thirds (e.g. `h1_part1`/`h1_part2`), one worker per part. Typical case: 73 images across 3 hospitalizations of ~25 each → 6 workers (each hospitalization split into 2 halves of ~12-13 files).
   - **Flat fan-out**: no subdirectories, > 15 files → split into N-file chunks (alphabetical or arbitrary), name slices `batch_a`/`batch_b`/etc.

   Workers across slices run in parallel (single message, N concurrent Agent tool calls). Within a worker, files run sequentially.

   Decide `patient_code`: caller-supplied OR auto-generate `PT-<hex>` from `hash(basename + mtime)`. Resolve `patient_data_root` from `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Compute `patient_dir = <patient_data_root>/<patient_code>` and `mkdir -p` **only `ocr/` + `raw/`** at setup. **Do NOT pre-create the 14 clinical buckets** — an empty `09_手术与操作/` (or any other empty domain) is misleading scaffold that reads as "no such record exists" when it really means "no source for it was filed yet". Phase 2 **lazily creates a clinical bucket only when it has a sidecar to place in it** (Step 1a classification in `organizer-prompt-phase2-synthesis.md` does the `mkdir -p <bucket>` immediately before writing each sidecar). The result: a bucket appears on disk **iff** the archive actually contains a record for that domain — an absent `09_手术与操作/` then truthfully means "no surgery document was provided", and `missing_items.json` (not an empty folder) is the channel that flags an expected-but-missing domain.

3. **Dispatch Phase 1 LLM Markdown Ingestion Workers (parallel)** — for each slice, dispatch one `general-purpose` subagent in **a single message with N tool calls** (so they run concurrently, not sequentially). Each worker gets:

   - `subagent_type: general-purpose`
   - `description: "Organize LLM ingestion slice <slice_id>"`
   - `prompt`: the full content of [`references/organizer-prompt-phase1-ocr.md`](references/organizer-prompt-phase1-ocr.md), with these `## Call parameters` appended at the end:
     - `slice_input_path: <absolute path to the slice's source directory>`
     - `slice_id: <short logical label — e.g. h1, h2, batch_a>`
     - `patient_dir: <absolute patient_dir>`
     - `original_subdir: <relative path under raw/ where verbatim originals go — usually the source subdir's basename>`

   Each Phase 1 worker writes ONLY to `<patient_dir>/ocr/` (text-masked MD sidecars) and `<patient_dir>/raw/<original_subdir>/` (raw/ keeps every uploaded original's BYTES verbatim — never byte-altered, never pixel-redacted, never deleted; the on-disk FILENAME is DE-IDENTIFIED by Phase 1 (identity token stripped; if the whole basename is the identity, fall back to `<source_id>.<ext>`) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared surface; the verbatim original filename is preserved ONLY in `raw/_FILENAME_MAPPING.md` — inside raw/, excluded from export, never a delivered/scanned surface). It may create temporary adapter outputs (HEIC raster, PDF rendered pages, DOCX/table payloads) only to feed the driver LLM; those adapter outputs are not stored, not anchors, and not clinical text sources. Workers do NOT touch INDEX.md / timeline.md / profile.json / etc — those are Phase 2's job. Workers don't share context, so anti-anchoring is structurally enforced.

   Each worker returns: `{slice_id, files_processed, sidecars_written, stub_sidecars, full_ingestion_sidecars, ingestion_uncertain_files, candidates_files, ingestion_blocked_files, continuation_needed, continuation_resume_from}`.

4. **Phase 1 continuation loop** — for each worker that returned `continuation_needed: true`, dispatch a continuation worker for that slice:

   > "Resume Phase 1 LLM Markdown ingestion for slice `<slice_id>` of `<patient_code>`. The previous dispatch processed up to `<continuation_resume_from>` and stopped. Skip every file whose sidecar already exists in `<patient_dir>/ocr/` (these have lower mtime than source); ingest all remaining files in `<slice_input_path>`. Return same JSON contract; set `continuation_needed: false` if done, or `true` with next resume point if context fills again."

   Loop per-slice until all slices report `continuation_needed: false`. Slices that finished cleanly do NOT need re-dispatch; only laggards. This is more efficient than re-dispatching the whole organize.

5. **Dispatch Phase 2 Synthesis Worker** — after every Phase 1 worker reports `continuation_needed: false`, dispatch a SINGLE `general-purpose` subagent for synthesis:

   - `subagent_type: general-purpose`
   - `description: "Organize synthesis"`
   - `prompt`: the full content of [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md), with these `## Call parameters` appended:
     - `patient_dir: <absolute patient_dir>`
     - `phase1_summary: <JSON list of all Phase 1 worker results>`

   Phase 2 reads all sidecars (cross-slice), classifies into the 14 clinical buckets, builds source_inventory.json / INDEX.md / timeline.md / case_text.md / profile.json / readiness.json, runs the Step 3 review_flags audit (now WITH cross-slice visibility), and writes review_flags.md (if non-empty) + review_summary.md (always).

   Phase 2 returns: `{role, patient_dir, files_classified, md_sidecars_relocated, coverage_complete, missing_sidecars, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path, source_inventory_path}`.

6. **Coverage gap retry** — if Phase 2 returns `coverage_complete: false`, dispatch a retry-mini-Phase1 worker with just the missing files as input, then re-run Phase 2. Loop until `coverage_complete: true`. Most runs converge in 0 or 1 retries.

7. **Verify outputs** — parse Phase 2's returned JSON; confirm `profile.json` exists and the required v3 fields (`patient_code`, `summary.primary`, `summary.histology`, `summary.stage`) are populated. If any are missing or null, surface to the user as a blocker before routing to any other sub-skill.

8. **Grade readiness** — from Phase 2's returned JSON take `readiness_grade` + `readiness_score`. If grade is F or D, present the information-gap checklist 🔴🟡🟢 (derived from `blocking_gaps`) to the patient.

9. **Display review_summary.md (MANDATORY, ALWAYS)** — read the file at `review_summary_path` and display its full content to the user. This is the **first** thing the user sees after organize — before profile card, before review_flags. It is a 1-page spot-check of extracted key fields with verbatim source citations.

   Why this is the first display: many real ingestion/transcription errors produce **internally consistent wrong values** (e.g. all 7 documents in one hospitalization copied the same wrong drug name). The 9-check `review_flags` audit cannot detect those — but a human reading `review_summary.md` can spot a wrong character in 30 seconds.

   After displaying, prompt the user: "请核对上面的检查要点。任何字段需要修正,直接告诉我哪个字段 + 正确值,我会更新 profile.json 并重新生成清单。"

10. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after `review_summary.md`. This is a hard gate, not optional polish:
    - **If any 🔴 red flag present**: tell the user "进入下游 skill 之前请先逐条确认或 override 这些 🔴 项 — 它们会直接影响 find-care / vmtb / 内部版临床工具（pro-skill mtb-lite）/ 开源 clinical-trial-matching的推荐"
    - **If only 🟡/🟢 flags**: present them as "建议核对", do not block downstream routing
    - **If `review_flags_total: 0`**: still tell the user "所有提取字段已通过 9 项可疑值检查 (格式/跨文档矛盾/临床逻辑/原始证据/数值趋势), 无待确认项 — 但仍请核对上面的 review_summary.md 速查清单"
    - The user's resolution per flag (`accept_suggestion` / `keep_original` / `custom_value` / `defer`) is logged back into `readiness.json.review_flags[i].user_confirmed = true` plus a `resolution` sub-object.

11. **Output profile card** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "🔍 待人工确认" section pulls from `readiness.json.review_flags[]`.

    **Downstream gate**: do NOT route the user to any downstream sub-skill (nutrition / education / find-care / vmtb / the pro-skill clinical tools mtb-lite·trial-match) while any 🔴 red review_flag is unconfirmed. A wrong drug name at this stage poisons every downstream report.

11.4. **补料信号 — 一句极短的低压信号，不在此刻摊详细邀请** — right after the Profile Card. **重做后 post-organize 只给一句信号，不再是 top 2–3 详细邀请**——organize 刚结束是患者认知最过载的时刻，且 profile card 的信息缺口已降级为覆盖度分级（不再铺冷清单，见 `profile-card.md`）。详细邀请让给"顺手且相关"的下游时机（visit-prep / 路由 / 被问题限制的 Q&A），主力见 `gap-followup.md` §5.5。Full spec: [`references/gap-followup.md`](references/gap-followup.md)。In short:
    - Load `missing_items.json` + `readiness.json`，按 `gap-followup.md` §3 filters 判断**是否存在**任何 P0/P1 高价值缺口（**只看有没有，不在此列举、不给动作细节**）。
    - 若有 → 给**一句极短、可忽略的信号**（`profile.json.locale`）：如"档案里还差几样比较关键的（像基因检测这类）——需要的时候我随时帮你补，现在不挡着往下走。" 若无高价值缺口 → **什么都不加**。
    - **不在 post-organize 写 `gap_asks.json` 的 pending**（避免旧的"提过就永久沉默"）——只有 §5.5/§6 真正递出一条**具体**邀请时才登记 ledger（cooldown + 上限见 `gap-followup.md` §7）。永不阻塞下游路由。

11.5. **Phase 2.5 — extraction faithfulness check (MANDATORY, runs before 段D renders)** — after Phase 2 has written the structured JSONs and the user has spot-checked review_summary.md, but **before** Step 12 generates the patient HTML, dispatch a `general-purpose` subagent with the full content of [`references/organizer-prompt-phase2_5-faithfulness.md`](references/organizer-prompt-phase2_5-faithfulness.md), appending `## Call parameters`: `patient_dir: <absolute patient_dir>`. This is the independent re-read that catches the *internally-consistent-but-wrong* errors `gate_numeric_integrity` cannot (the CEA column-shift that read a tumor-marker value off the wrong table row, a renal abnormal silently dropped at the JSON stage, a surgery-date that propagated the wrong value across sidecars). The subagent re-compares each structured value against its `source_refs[]` sidecar and returns a per-value verdict.

    On a **CRITICAL "not faithful" verdict** for a specific value, the orchestrator MUST:
    - **(a)** collect every CRITICAL `not_faithful` `{file, json_path, value}` into an **`unfaithful_values` list** and pass it to the Step-12 段D producer (as a Call parameter — see Step 12). The 段D producer is the **sole writer** of `.case_summary_data.json`, so it — not a pre-render patch — must **omit those exact values** when it builds the render data (emit the field `null` → the template's `资料缺失` placeholder) **and must not restate them in the 病情概要 narrative**. Sequencing matters: `.case_summary_data.json` does **not exist** until Step 12 creates it, so the drop happens *inside* Step 12's producer, never "before render". The bad value stays in the structured JSON (flagged) for the user to correct; only the patient-facing summary drops it. **Array-element drops are element-aware**: for a `labs[]`/`molecular_rows[]`/`treatment_lines[]` element, null ONLY the value field, KEEP the element (renders a `资料缺失` row), and set every sibling `*_class` field (`lab_class` / `line_marker_class` / `line_badge_class`) to an **explicit `""`** — never omit them, or the `__default__` fallback injects `资料缺失` into a `class="…"` attribute and `validate_case_summary_html` fail-closes the whole HTML. (The renderer also defends this: `*_class` placeholders never take the fallback — belt-and-suspenders.)
        **Denormalized-string scrub (single fix point for `one_line_condition`)**: if an unfaithful value is embedded in the **pre-computed `profile.json.summary.one_line_condition`** (it concatenates stage / histology / primary driver / current-line status), the orchestrator MUST re-stitch that denormalized convenience string with the unfaithful component dropped (→ `资料缺失` / omitted) and write the scrubbed string back to `profile.json.summary.one_line_condition`. Because the 段D header subtitle, the narrative, AND `AGENTS.md` (Step 13) all copy `one_line_condition` verbatim, scrubbing it at this one source propagates the drop to every consumer. The granular `summary.stage` / `patient_summary.diagnosis.stage` etc. stay flagged for the user to correct — only the denormalized convenience copy is scrubbed.
    - **(b)** add a review_flag to `readiness.json.review_flags[]` (and re-render `review_flags.md`) with the **closed-enum shape** so it actually gates: `severity: "red"`, `category: "unverified_critical_field"` (the registered roster category covering a downstream-critical field whose value is untrustworthy — the Phase-2.5 faithfulness mismatch is a sub-case; do **not** write `severity:"CRITICAL"` or `category:"extraction_faithfulness"` — those are off-enum and the 🔴 gate keys on `severity=="red"`), plus `id` (RF-NNN), `field_path`, `current_value`, `issue`, `source_evidence[]`, `suggested_action`, `user_confirmed:false`. This surfaces as 🔴 in Step 10's gate on any later session.

    A run is **not "done"** until **all three** hold: (1) `python3 scripts/validate_structured_outputs.py <patient_dir>` (which runs `gate_numeric_integrity` + `gate_pii_rescan` — the deterministic **Layer-2** shape floor) exits 0; (2) the **Layer-1 semantic PII scan** has run clean — dispatch a `general-purpose` subagent with the full content of [`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md) (`patient_dir: <absolute>`), which scans sidecar bodies + **synthesized downstream surfaces** (`case_text.md`/`profile.json`/`patient_summary.json`/…) + delivered surfaces for ANY identifying category (出生地/职业/家属姓名/民族/…) that the shape floor cannot match, and returns `clean=true`; remasking at the producer until clean; (3) this Phase 2.5 faithfulness step has run with no unresolved CRITICAL verdict (resolved = the value is dropped from the final `.case_summary_data.json` per (a) + a 🔴 red flag written per (b), or the user corrected it).

12. **Generate 病情简要总结.html (段D)** — immediately after the Profile Card and the Phase 2.5 faithfulness check, dispatch a `general-purpose` subagent with the full content of [`references/case-summary-html-prompt.md`](references/case-summary-html-prompt.md), appending `## Call parameters`: `patient_dir: <absolute patient_dir>` **and `unfaithful_values: <the Step-11.5 CRITICAL not_faithful list, or []>`** (the producer omits those exact values → `资料缺失` and never restates them in the narrative) **and `adjudications: <the Step-3c load-bearing cross_doc_contradiction adjudications, or []>`** (the producer renders each as a `(来源存在差异，已按X裁决)` caveat in `caveats[]`) **and `lab_trend_caveats: <the US-006 lab/tumor-marker trend OCR caveats, or []>`** (the producer renders each into `caveats[]` AND appends the inline OCR caveat when the 病情概要 narrative states a marker/lab trend). The worker reads only the **desensitized** structured JSONs (`profile.json` / `patient_summary.json` / `molecular.json` / `labs.json` / `treatment_lines.json` / `timeline.json` / **`longitudinal_observations.json` when present** + the imaging段 of `case_text.md`) — never raw images, never a sidecar with plaintext PII. The narrative 病情概要 段 is generated by the subagent in `profile.json.locale` (LLM, no hardcoded keyword/template-句 stitching); every other section is a direct field-map. The subagent assembles a **data JSON** (`{{i18n.*}}` string table for the locale + scalar fields + `trend_charts` (关键趋势, **0..N featured charts — the subagent decides how many are clinically salient from the treating physician's view, not a fixed count**) + the section LOOP arrays `lab_trends` / `lesions` / `molecular_rows` / `treatment_lines` / `path_items`, each 0..N — an empty array is fine, the template's `RENDER_IF_NOT` shows the `资料缺失` placeholder). The **trend `series[]` values are copied verbatim from `longitudinal_observations.json`/`labs.json`; the subagent computes no chart geometry and invents no point.** Two deterministic zero-medical scripts then enrich the data JSON — `compute_version_delta.py` (自上次总结的变化, diffing the previous snapshot) and `compute_sparklines.py` (injects the inline-SVG coordinates + runs the anti-fabrication gate) — before it **renders deterministically** through the generic engine.

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

    # (2) 富化 —— 注入内联 SVG 趋势坐标 + 反造假门(画出的每个点必须在纵向库/labs 里查得到,否则 exit 3)
    long_arg=""; [ -f "<patient_dir>/longitudinal_observations.json" ] && long_arg="--longitudinal <patient_dir>/longitudinal_observations.json"
    python3 scripts/compute_sparklines.py \
      --data "<patient_dir>/.case_summary_data.json" $long_arg --labs "<patient_dir>/labs.json"
    # ↑ exit 3 = 有 series 点在源库查无 → 修数据(改回 verbatim 原值或删点)再重跑,绝不绕过

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

    The renderer is a zero-medical-logic template engine: it only substitutes `{{key}}` and expands `<!-- LOOP -->` / `<!-- RENDER_IF -->` blocks from the data, so CSS/DOM stay 1:1 and clinical entities are passed through verbatim. It stamps a `template_sha256:` provenance comment proving the HTML came from the template. 患者标识 keeps precise age for clinical-trial matching (女 / 52 岁 / 海外 — never real name, DOB, birthplace, or occupation); any `null` field maps to the `资料缺失` placeholder, never a fabricated value. The patient-root `病情简要总结.html` is the latest pointer; `case_summary_versions/病情简要总结_<date>.html` is the immutable history.

    **🔴 TEXT/HTML GATE — 段D HTML is complete when both hold:**
    1. `病情简要总结.html` was produced by `render_html_template.py` from `references/templates/case-summary.template.html` (**rendered, not hand-written**). A subagent that pastes HTML inline fails this gate.
    2. `python3 scripts/validate_case_summary_html.py --html <patient_dir>/病情简要总结.html --template references/templates/case-summary.template.html --profile <patient_dir>/profile.json --data <patient_dir>/.case_summary_data.json` exits 0 (shape + PII + provenance invariants hold, **plus the (j) core-completeness gate** — `--profile`/`--data` hard-fail if a core singleton **分期 / 驱动基因 / 当前方案** is present in source but dropped from the summary; labs/comorbidities are NOT gated — they're curated for a one-pager).

    The structured-output acceptance门 is separate: `python3 scripts/validate_structured_outputs.py <patient_dir>` exits 0 once the structured JSONs + anchors validate, the text sidecars pass the PII residue rescan, `source_inventory.json` is complete (every content unit carries a `raw_path` + a text-masked sidecar), and the case-summary HTML shape holds. Surface in the final report to the user the **`template_sha`** echoed by `validate_case_summary_html.py` (proof the template was used). Never mark a medical source `persist:false` merely to make this gate pass; if a formal artifact cites its sidecar, keep it `persist:true`. Uploaded originals in `raw/` are kept verbatim — there is no source-file redaction step gating persistence.

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

14. **无关文件处置门 (段E, MANDATORY when the relevance gate isolated anything)** — Phase 2's Step 1·0 relevance triage (see [`references/relevance-gate.md`](references/relevance-gate.md)) diverted any non-medical file out of the 14 clinical buckets into `99_无关文件/` (`high_confidence/` vs `uncertain/`). If either sub-dir is non-empty, surface **one plain-language disposition notice** (rendered in `profile.json.locale` — see `references/relevance-gate.md` → disposition-notice §) before the user moves on. The privacy-floor sentence **"我们不保存你的原始无关文件 —— 你不确认，我也会自动删除"** (zh template; rendered semantically-identical in the user's locale, e.g. `en`: "We don't keep your raw unrelated files — if you don't confirm, I'll delete them automatically.") is mandatory and must appear in that locale with no softening — the user is entitled to know *silence ⇒ deletion* before it happens. List each `uncertain/` (borderline) file individually with a one-line reason; summarize the `high_confidence/` batch as a count.

    Then parse the user's response into exactly three resolution paths (full logic in `relevance-gate.md`):
    - **删 (high-confidence non-medical)** — user confirms unrelated **OR** does not respond / defers / 随便 / closes the chat → **delete** the file from `99_无关文件/high_confidence/`. This is irreversible and intended (privacy floor: silence ⇒ delete). The `99_无关文件/` copy is the only copy (these were never anchored or bucketed), so deleting it is the whole point.
    - **回收 (reclassify — "X 其实有用")** — user claims a specific isolated file matters → move it out of `99_无关文件/` into its correct typed bucket, run the *normal* late-arriving path (LLM ingestion → 文本脱敏 MD → canonical rename → co-locate MD → add to INDEX/timeline/case_text/structured JSONs; the verbatim original is also kept in `raw/`).
    - **Hold (borderline `relevance_uncertain`, the one exception)** — for borderline files the user has **not** explicitly resolved → **do nothing, keep in `99_无关文件/uncertain/`, never auto-delete.** Silence deletes a high-confidence non-medical file; silence does **not** delete a borderline file — deleting something that might be a real medical record is the worse error. Only an explicit "删"/"无关" deletes it; "留"/"这是病历" reclassifies it. Either way mark the `relevance_uncertain` review_flag `user_confirmed: true` with the chosen `resolution`.

    Record every isolated/deleted/reclassified/held action in `update_log.json.relevance` (the `auto_deleted` array is the irreversible-action ledger). The authoritative deletion red-line is the 段E entry in [`../../references/safety-guardrails.md`](../../references/safety-guardrails.md); this step is its operational门控.

15. **Conversation-incremental capture (段C, on demand)** — this is not part of the initial organize run; it is the entry point for later turns. When the patient/caregiver is *chatting* about their condition (not handing over files) and a `<patient_dir>` with an existing `update_log.json` exists, run `run_mode: "conversation_incremental"` (see the dedicated section below) to capture archivable facts surfaced in dialogue → diff card → user-confirmed write, with `[[src:conversation:<ISO8601>]]` provenance. Unconfirmed talk never touches formal fields.

16. **Upload reconciliation (扩段C, on re-upload)** — when the user re-uploads one or more files onto an **already-existing** `patient_dir` (has `update_log.json`), run `run_mode: "upload_reconciliation"` (see [`references/upload-reconciliation.md`](references/upload-reconciliation.md)). Each new file first passes the 段E relevance gate (high-confidence non-medical → 段E isolate/delete logic, not reconciliation); medical/borderline files then get an LLM relation判断 — **new / supersede / conflict** (semantic comparison against the existing archive, NOT a hardcoded same-name-same-date Python check) → a diff card asking **替换? 并存? 忽略?**. This **reuses段C's single "先确认" gate — it does not start a second gate**: 替换 archives the old doc to `_superseded_<ts>/` (not deleted) and remaps its anchors; 并存 keeps both and adds a second timeline row; 忽略 / 未确认 writes no formal field. conflict is never silently overwritten — both facts are shown side by side for the user to adjudicate, and 关键字段 (分期/分子/治疗线) conflicts require explicit confirmation. Provenance logs an `update_log.json` entry with `run_mode: "upload_reconciliation"`. **This flow introduces no new auto-deletion** — the only auto-delete is段E's high-confidence non-medical path; borderline medical files are never auto-deleted without explicit confirmation.

17. **Finalize — strip staging cruft (always, at end of a run)** — remove any stray `.DS_Store` files anywhere under `<patient_dir>`, and remove the `ocr/` staging dir if it is empty (after Phase 2 has relocated every sidecar into its lazily-created clinical bucket, `ocr/` should be empty; a non-empty `ocr/` means a sidecar wasn't placed — leave it and surface as a warning, don't silently delete). This keeps the archive (and any later export) free of OS cruft and an orphan empty staging dir.

    ```bash
    find "<patient_dir>" -name .DS_Store -type f -delete
    rmdir "<patient_dir>/ocr" 2>/dev/null || true   # only removes ocr/ if empty
    ```

18. **Safe export (on demand, when the user wants a shareable copy)** — see the **Safe export** section below. **First re-run the PII Layer-1 semantic agent scan** ([`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md), `patient_dir: <absolute>`) and confirm `clean=true` — this is mandatory here because `export_share.py` only runs the deterministic **Layer-2** shape floor (via `validate_structured_outputs.py`), which by design cannot catch semantic-only PII (出生地/籍贯/职业/民族/家属名) in the synthesized surfaces; and a 段C increment or a later standalone export may have rewritten `case_text.md`/`profile.json` since the Step-11.5 done-gate. Only on `clean=true` produce the share copy with `scripts/export_share.py`, which additionally refuses to run unless the acceptance gate (`validate_structured_outputs.py`: Layer-2 PII shape floor + schema + anchors + numeric integrity + source_inventory completeness + case-summary HTML shape) passes. (Extraction faithfulness is the separate Phase-2.5 step / Step-11.5 done-gate — it is NOT re-checked by `export_share.py`; the orchestrator must have resolved any CRITICAL not_faithful before export.) So a copy carrying raw originals or shape/semantic-PII never ships.

### Safe export

To hand a sanitized, shareable copy of an organized patient dir to a third party (doctor, family, another platform), use the dedicated exporter — never `cp -r` the patient dir (that would ship `raw/` originals + OS cruft):

```bash
python3 scripts/export_share.py <patient_dir> --out <dest>
```

`export_share.py` produces a shareable copy of `<patient_dir>` at `<dest>` that:

- **EXCLUDES `raw/`** entirely (the un-redacted vault of verbatim originals never leaves the local archive — only the text-masked sidecars + structured JSONs + patient-facing HTML go out).
- removes `.DS_Store` files and an empty `ocr/` staging dir (same cleanup as Step 17, applied to the exported tree), and drops the build-intermediate / provenance dotfiles `.case_summary_data.json` / `.rename_plan.json` / `.phase1_sources.json` / `.identity_denylist.json` (a safe superset — these are internal render/plan state, not part of a shared archive).
- **EXCLUDES `case_summary_versions/`** (the immutable dated 段D snapshots) — only the latest root `病情简要总结.html` ships in a share; the version history stays in the local archive (`export_share.py` `EXCLUDE_TOPLEVEL`).
- **refuses to run unless `python3 scripts/validate_structured_outputs.py <patient_dir>` passes first** — the acceptance gate (schema + anchors + `gate_pii_rescan` incl. the delivered surfaces INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html + the synthesized surfaces case_text.md / profile.json / … + `gate_numeric_integrity` + `source_inventory.json` completeness + case-summary HTML shape) must be green, so no PII / path leak ships in a shared copy. (Extraction faithfulness is enforced upstream at the Phase-2.5 / Step-11.5 done-gate, not by this export gate.) If the gate fails, the export aborts with the gate's errors and writes nothing.

## Definition of Done（终态硬门 —— 结束前必过、必贴，抗压缩的单一收口）

done 判据以前散在 Step 7 / 11.5 / 12 / 13 和好几个 validator 里；压缩后容易只记得"产出了文件"就自报完成。这里把它收成**一个终态清单**：以下**全绿之前，本次 organize 未完成**，不许对用户说"整理好了"。

1. **结构化验收门 exit 0 且已贴输出**：`python3 scripts/validate_structured_outputs.py <patient_dir>` 返回 0（它内含 schema + anchors + `gate_pii_rescan` + `gate_numeric_integrity` + `source_inventory` 完整性 + **段D HTML 形+provenance** `validate_case_summary_html`）。把它回显的 **`template_sha`** 贴给用户——这是"HTML 确实走了模板、不是手写"的证明。**没有 template_sha = 没完成。**
2. **段D HTML 带 provenance**：`病情简要总结.html` 含 `<!-- template_sha256: … -->` 注释（顶部不变量第 1 条）。手写 HTML 没有它，会在第 1 项里 fail。
3. **PII Layer-1 语义扫描 clean**：`references/pii-rescan-prompt.md` 子代理返回 `clean=true`（覆盖 sidecar + 合成下游面 + 交付面）。
4. **Phase 2.5 忠实度无未决 CRITICAL**：每个 CRITICAL `not_faithful` 要么已从 `.case_summary_data.json` 丢弃（→`资料缺失`）并写了 🔴 `unverified_critical_field` flag，要么用户已更正（Step 11.5）。
5. **AGENTS.md 已生成且非 stub**（Step 13：两个占位符已解析成真值）。

自检话术（贴给用户的收尾里体现）：`validate_structured_outputs.py exit 0 ✅ · template_sha=<…> ✅ · PII clean ✅`。任一非绿 → 回到对应 Step 修复重跑，**不要**把一份形不合规/缺 provenance/带 PII 的产物留在 `patient_dir` 或对用户报完成。

## Runtime adaptation

The Workflow above (Step 2–5: `glob`-based slicing → parallel `Agent` Phase-1 LLM Markdown ingestion fan-out → continuation loop → single `Agent` Phase-2 reduce, plus `Read`-based LLM vision/file-context ingestion and adapter commands such as `sips` HEIC decode) is the **Claude Code reference binding** — one concrete way to drive organize, not the contract. The runtime-neutral **behavior contract** (what each step produces / when it may write / which invariants hold, with zero tool names) lives in [`references/organize-contract.md`](references/organize-contract.md); the per-host fill-ins are in [`references/runtime-bindings/`](references/runtime-bindings/) (`claude-code.md` = the mechanism documented here; `headless-codex.md`; `_template.md` for OpenClaw/OpenCode/other agents).

What this means for non-CC hosts:

- A headless / single-process host (codex GPT-5.5, workbuddy, OpenClaw/OpenCode, Cursor, …) **drives its own steps** — the `Agent` fan-out + reduce, `Read` vision/file context, and `sips` decode are reference mechanisms, not requirements. It may run Phase-1 sequentially, feed LLM vision via `-i` or LLM file context, adapt formats with cross-platform commands, and persist outputs with its own storage primitives.
- Whatever the binding, it produces the **same canonical output set** the contract defines (14 clinical buckets + co-located 文本脱敏 MD, `raw/` verbatim originals, `INDEX.md`, `source_inventory.json`, `profile.json`, `AGENTS.md`, `timeline.*`, `case_text.md`, `readiness.json`, `review_summary.md`, `review_flags.md` (when non-empty), the 6 structured JSONs + conditional `longitudinal_observations.json`, `missing_items.json`, `update_log.json`, bucket-relative anchors) and honors the same invariants (sidecar text is LLM-generated; the text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) are scanned by pii_rescan.py for name / path / account leaks — de-identification therefore covers the sidecar body AND every delivered surface; uploaded original BYTES in `raw/` are kept verbatim while the on-disk filename is de-identified by Phase 1; unconfirmed → no formal write / no irreversible delete; clinical entities verbatim; logic/schema/产物结构 unchanged).
- The five seams (编排 / LLM 输入源 / 格式适配 / 确认门 / 存储) and each host's fill-in are the matrix in `organize-contract.md` §6. The `MAX 15 image files per worker` rule in Step 2 is a Claude many-image budget feature → **host-tunable** (don't slice / slice to the host's own budget); it is not a contract invariant.

Claude Code does not change: the mechanism in Step 2–5 is preserved verbatim as the reference binding, the neutral layer is added on top, and the CC path regresses identically.

## Why fan-out + reduce instead of single-pass

The original design was a single subagent processing every input file sequentially. A 73-image archive took ~33 minutes. Splitting into Phase 1 (parallel per-slice LLM Markdown ingestion) + Phase 2 (cross-slice synthesis + audit) gives three benefits:

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
- `profile.json.alias` is sticky — never overwritten by an incremental run.
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

The flow: an LLM detects candidate archivable facts (新诊断/分期 / 新检验值 / 治疗变更 / 症状 / 体能-ECOG) → maps each to a `profile.json` field or a `timeline.md` row → presents a **diff card** (before → after, with the user's own words as 依据) → the user confirms / corrects / defers → only confirmed candidates are written. Provenance uses the conversation anchor `[[src:conversation:<ISO8601>]]` (never a file anchor). Confirmed facts land in the **corresponding clinical domain's** `conversation_notes/` subdir, resolved by the domain's stable `NN_` prefix against the archive's existing (locale-localized) buckets — e.g. a lab value → the `07_` domain (`07_检验/` for zh, `07_labs/` for en/fr…), a staging change → the `04_` domain; the `14_` domain is the fallback when the fact fits no domain — with a `patient_curated` tag and update the formal field/row; `update_log.json` gets a `run_mode: "conversation_incremental"` entry. **Unconfirmed talk never touches formal fields** — this gate prevents a mis-spoken value from poisoning downstream reports. This mode does NOT re-ingest files or re-run synthesis; for new *files* use full or incremental mode. Major changes ("我整套方案都换了") route to a full re-organize, not turn-by-turn merge.

## Business-readable alias

When `profile.json.alias` is set by Phase 2 (format `{patient_id_short}_{cancer_code}_{year}`, e.g. `17CE02_CRC_2019`), the synthesis worker creates a symlink under the patients root:

```
<patients_root>/17CE02_CRC_2019 -> PT-17CE02BC33/
```

Internal storage continues to use the `PT-<hex>` directory. Downstream sub-skills accept either name; the alias is the human-friendly handle for exports and conversations ("我跟病人沟通的是 17CE02_CRC_2019,不是 PT- 那串十六进制"). If filesystem symlinks are not available, the synthesis worker writes `<patients_root>/alias_map.json` mapping aliases to `PT-<hex>` codes.

## patient_code collision

If the generated `patient_code` (e.g. `PT-17CE02BC33`) already exists under the patients root, the subagent appends `_2`, `_3`, etc., and announces the assigned code in the summary.

## Configurable root

The `patients/` root resolves in order: `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Override by exporting one of those. Shared with vmtb-skill.

## Safety

Organize does not make medical recommendations. Still:

- Never fabricate fields — when a value is truly unreadable in the source, the subagent writes `null` (JSON) or `[OCR_UNCERTAIN]` (text) and surfaces it as a gap.
- Text masking only masks PII in the sidecar body — it never alters clinical characters (anti-anchoring). The MD sidecar is the downstream-only read source and must not carry plaintext PII. The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) are scanned by pii_rescan.py for name / path / account leaks. De-identification therefore covers the sidecar body AND every delivered surface.
- Downstream sub-skills apply the full `safety-guardrails.md` rule set when they read what organize produced; wrong data here poisons every downstream report.
- raw/ keeps every uploaded original's BYTES verbatim (never byte-altered, never pixel-redacted, never deleted); the on-disk FILENAME is DE-IDENTIFIED by Phase 1 (identity token stripped; if the whole basename is the identity, fall back to `<source_id>.<ext>`) so a patient-named upload (e.g. 王国洪-报告.pdf) never leaks into a scanned/shared surface. The verbatim original filename is preserved ONLY in raw/_FILENAME_MAPPING.md (inside raw/, excluded from export, never a delivered/scanned surface). It is the vault the frontend deep-links a sidecar back to (`source_inventory.json.raw_path`). The text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) are scanned by pii_rescan.py for name / path / account leaks. De-identification therefore covers the sidecar body AND every delivered surface; downstream artifacts are built from the text sidecars, so they stay de-identified even though the original bytes are kept verbatim. (One output-side step is layered on top for the patient-facing 段D HTML only: identity is coarse-grained — **precise age is retained** (clinical-trial matching needs it) while name / DOB / birthplace / occupation are masked — see `references/case-summary-html-prompt.md`.) See `references/bucket-taxonomy.md` §5.

## Next-step guidance

After successful organize, route the patient to the most relevant **shipped companion** based on their initial question. Only route to skills that ship in this public package — the clinical skills (`explore` / `mtb-lite` / `trial-match` / `access` / `manage` / …) moved to the private `cancer-buddy-pro-skill` (see [`../../references/roles.md`](../../references/roles.md)), so routing the public patient to them dead-ends:

- Newly diagnosed, wants to understand their disease → `cancer-buddy-education` (patient self-study handbook), or hand back to the meta `cancer-buddy` router.
- Has a gene report, wants treatment guidance → this is clinical (MTB-grade) judgment: route via the meta router's **conditional vMTB detection** (`../cancer-buddy/SKILL.md` 「MTB 路由（条件性）」 — call `vmtb-skill` if installed, else the public "近期开源" fallback + `find-care` / `second-opinion`). Never route to a bare `mtb-lite` — it is not in the public set.
- Looking for trials → `cancer-buddy-find-care` (finds recruiting centers + MTB hospitals; auto-pulls the open-source `clinical-trial-matching` skill on demand for criterion-level matching).
- A clinic visit is coming up → `cancer-buddy-visit-prep`.
- **Wondering how others like them were treated / feeling out of options** → `cancer-buddy-case-precedent`. Right after organize is a natural moment to *offer* this once: the similarity-profile fields it needs (癌种 / 分子 / 治疗线) are at their most complete. **Only a soft, one-line offer, never an auto-search** — e.g. (zh) "病历整理好了。文献里有没有和你情况像的真实病人、别人当时怎么治的，也是很多人会想看的——要不要我顺手去翻一下？不急也可以先放着。" If the patient says yes → hand to `cancer-buddy-case-precedent` (which runs its own Step 0 intent check). Offer at most once; if ignored, don't re-push (same ask-once discipline as 补料).

## Role behavior

Authoritative matrix in `../../references/roles.md`. For this skill:

- **Role = patient**: First-person. "帮我整理我的病历" → produce profile.json / timeline.md / readiness.json. Profile's top-level `source_refs[]` names patient as source.
  - *Disclosure*: disclosure_state=suppressed on patient entry → warn that organize will likely break suppression; proceed only with confirmation.
- **Role = caregiver**: Second-person. "帮你家人整理报告". On first-ever organize in this patient_code, offer to populate `patient_summary.json.caregivers[]` with the caregiver's relation + name + contact preference. Tone warmer, includes "整理这些很累吧，一步一步来"-style acknowledgment.
- **Role = family**: Refuse. Emit: `病历整理要靠主照护者操作（Ta 手里有原件）。要不要我帮你生成一份 2 页要点让 Ta 参考？` Do not run organize.

## References

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) — Phase 1 worker prompt: per-slice LLM Markdown ingestion, parallel-safe, sidecars-only
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — Phase 2 worker prompt: cross-slice synthesis + 9-check review_flags audit (incl. filename_content_mismatch second-check) + review_summary + 6 structured JSONs + missing_items.json + update_log.json + alias
- [conversation-incremental-prompt.md](references/conversation-incremental-prompt.md) — 段C conversation-incremental worker prompt: detect archivable facts in chat → diff card → user-confirmed write to profile field / timeline row with `[[src:conversation:<ISO8601>]]` provenance + `patient_curated` tag; unconfirmed talk never written
- [relevance-gate.md](references/relevance-gate.md) — 段E medical-relevance triage: LLM judgment (not keyword list) → medical / non-medical-high-confidence / borderline; `99_无关文件/` quarantine semantics; disposition notice + privacy floor; 删 (high-confidence auto-delete on no-confirm) / 回收 (reclassify) / hold (borderline never auto-deleted); `relevance_uncertain` 8th review_flag + `update_log.json.relevance` ledger
- [upload-reconciliation.md](references/upload-reconciliation.md) — 扩段C re-upload reconciliation: LLM new/supersede/conflict relation判断 (not hardcoded same-name-date) → diff card 替换?/并存?/忽略? reusing段C's "先确认" gate; 替换 archives old doc to `_superseded_<ts>/` (not deleted) + anchor remap; conflict never silently overwritten; introduces no new auto-deletion; `run_mode: "upload_reconciliation"` update_log
- [organizer-prompt-phase2_5-faithfulness.md](references/organizer-prompt-phase2_5-faithfulness.md) — Step 11.5 Phase 2.5 worker prompt: independently re-read each structured value against its `source_refs[]` sidecar → per-value faithfulness verdict (catches column-shift / dropped-abnormal / propagated-wrong-date that `gate_numeric_integrity` can't); CRITICAL "not faithful" → the Step-12 段D producer omits the value when building `.case_summary_data.json` (→`资料缺失`) + a 🔴 red `unverified_critical_field` `readiness.json.review_flags[]` entry is added
- [case-summary-html-prompt.md](references/case-summary-html-prompt.md) — 段D worker prompt: read text-masked JSONs → fill the gold-standard template 1:1 → `病情简要总结.html`; subagent generates only the 病情概要 narrative, every other section is field-mapping; coarse-grained identity, `null` → 资料缺失
- [templates/case-summary.template.html](references/templates/case-summary.template.html) — 段D gold-standard HTML/CSS template (1:1 reproduction target, not "style-similar")
- [templates/agents-md.template.md](references/templates/agents-md.template.md) — Step 13 agent-facing recall pointer template (organize-owned, next to `case-summary.template.html`; the *generated* `AGENTS.md` is consumed by the whole cancer-buddy family + vmtb): patient identity + routing table + two-layer (top-level JSON → sidecar) drill-down + verbatim-citation/no-fabrication floor; only `{{patient_code}}` + `{{one_line_condition}}` injected verbatim from `profile.json`. Auto-loaded by harnesses (pi / Claude Code) from the cwd so any session can answer from the archive without first invoking cancer-buddy
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [gap-followup.md](references/gap-followup.md) — 补料邀请 behavior spec: warm, priority-ranked invitation to supplement the most valuable missing data. Consumes `missing_items.json` + `readiness.json`; surfaces only P0/P1 high-clinical-value gaps ranked by impact (**选得准，不是全都催** — never dumps the list, never nags P2); two triggers (post-organize top 2–3 warm closing + Q&A context-triggered one-liner via the question→gap map); benefit-tied + actionable phrasing (not "你缺了 X"); ask-once via the append-only `gap_asks.json` ledger; no treatment advice, patient can decline
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [references/schemas/](references/schemas/) — Draft 2020-12 JSON Schemas for the 6 structured outputs + conditional `longitudinal_observations.json` + `missing_items.json` + `source_inventory.json`
- [references/schemas/anchor-contract.md](references/schemas/anchor-contract.md) — `[[src:...]]` anchor token syntax + coverage + path validity contract (bucket-relative file anchors + `conversation:<ISO8601>` anchors; `ocr/` prefix deprecated)
- [references/checklists/](references/checklists/) — cancer-type minimum-data checklists driving `missing_items.json`
- [scripts/validate_structured_outputs.py](scripts/validate_structured_outputs.py) — **structured-output acceptance门** (one entry, aggregated exit code): structured-output schema + anchor validation **plus** PII residue rescan of the text sidecars AND the delivered surfaces (`pii_rescan` — the text-masked sidecar body is the primary downstream plaintext boundary; ADDITIONALLY the delivered surfaces INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html are scanned for name / path / account leaks, so de-identification covers the sidecar body AND every delivered surface), a no-bypass check that formal source citations cannot be marked `persist:false`, required `source_inventory.json` (every content unit carries a `raw_path` + text-masked sidecar), and case-summary HTML shape+provenance (`validate_case_summary_html`).
- [scripts/render_html_template.py](scripts/render_html_template.py) — generic, stdlib-only (no jinja2) HTML template engine with **zero medical/case logic**: substitutes `{{key}}` and expands `<!-- LOOP -->` (0..N, data-driven) / `<!-- RENDER_IF -->` / `<!-- RENDER_IF_NOT -->` (empty section → `资料缺失` placeholder, never deleted) from a data JSON; stamps a `template_sha256:` provenance comment. Used by 段D to render `病情简要总结.html` from `templates/case-summary.template.html`.
- [scripts/validate_case_summary_html.py](scripts/validate_case_summary_html.py) — case-summary HTML validator: checks **shape invariants only** (template-fixed, patient-independent) — byte-identical `<style>`, used-classes ⊆ template classes, no residual `{{…}}`, no PII (DOB/email/ID/phone — precise age is allowed for clinical-trial matching), full section skeleton, and `template_sha` provenance == the supplied template's SHA-256. **Never** asserts patient-specific content exists (would false-positive on a patient with no labs/lesions). Echoes `template_sha` on pass.
- The PII gate is **two independent layers** (trust-but-verify): **Layer 1** = the semantic agent scan [`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md) — the PRIMARY, generalizing scan that flags ANY identifying category (出生地/籍贯/职业/家属姓名/民族/签名/检验号 …) by meaning over sidecar bodies, synthesized downstream surfaces (case_text.md/profile.json/…), AND delivered surfaces; **Layer 2** = [scripts/pii_rescan.py](scripts/pii_rescan.py) — the deterministic, zero-network SHAPE floor, scoped by surface: **on sidecar bodies** it runs only the pure-shape standalone arms (身份证18位/手机/座机/email/SSN/E.164/≥11位数字ID); **on delivered + synthesized surfaces** it ALSO runs the `/Users/`绝对路径/云账号/identity-denylist-token arms (those never appear in OCR bodies). Independent second opinion. Either layer's finding fails the gate. Layer 2 skips `[PII_MASKED]` values + the `## PII` trailer; it is a detector, not an auto-rewriter (re-masking is a per-line judgement). De-identification covers the sidecar body, the synthesized downstream artifacts, AND every delivered surface.
- [scripts/export_share.py](scripts/export_share.py) — safe-export tool: `python3 scripts/export_share.py <patient_dir> --out <dest>` produces a shareable copy that **excludes `raw/`**, strips `.DS_Store` + empty `ocr/`, and **refuses to run unless `validate_structured_outputs.py` passes first** (so no un-redacted original / residual PII / path leak ships). Used by Step 18 (Safe export).
- [../../references/preflight.md](../../references/preflight.md) — shared entry-gate (role + disclosure + readiness grade + Step 2.5 review_flags red gate + schema validity)
- [../../references/i18n.md](../../references/i18n.md) — shared locale contract: host `locale` parameter first, otherwise profile locale / detection fallback → persist `profile.json.locale` → reuse; scaffold-localized / clinical-entity-verbatim policy; locale→bucket-name map (`NN_` prefix stable)
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
