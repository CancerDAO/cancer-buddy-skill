---
name: cancer-buddy-organize
description: "Organize patient medical records from PDF/images/docx/spreadsheets/archives into a canonical patients/<patient_code>/ directory. Every input format first goes through LLM-first Markdown ingestion: host adapters may render/decode/unpack files so the driver LLM can read them, but the redacted MD sidecar is written by the LLM, never by dumb OCR/parsers. Produces profile.json, timeline.md, readiness.json, bucket-co-located redacted MD sidecars, source_inventory.json, 6 schema-validated structured JSONs, missing_items.json, update_log.json, a 1:1 病情简要总结.html generated from redacted JSON/MD, redaction_manifest.json for full-format source redaction, and source_redaction_status.json as the final archive/persist hard gate. Final persistence is allowed only after source files are redacted, QA-passed, and plaintext originals deleted. Use when the user hands over a folder of medical records, or says 病历整理, 我有一堆报告, 帮我整理报告. Supports multi-slice Phase-1 LLM Markdown Ingestion Workers, Phase-2 synthesis, incremental updates, and conversation_incremental capture."
---

# cancer-buddy-organize

Turn raw medical records into structured data every other sub-skill can use.

## When to use

- User provides a folder path or set of files (PDF, JPG, PNG, DOCX, ZIP).
- User asks: 病历整理 / 帮我整理这些报告 / 我有一堆检查单.
- Any other sub-skill detects missing `profile.json` / `readiness.json` and prompts the user to run organize first.

## Inputs

- Path to a folder OR a single PDF/DOCX OR a zip/rar/7z/tar.gz archive.

## Outputs

Written under `patients/<patient_code>/`:

- `INDEX.md` (first line: `# patient_code: <code>`)
- `profile.json` (conforms to `../../references/patient-profile-schema.md`; now also carries `alias` field)
- `timeline.md` (human-readable treatment timeline; every line ends with at least one `[[src:...]]` anchor)
- `readiness.json` — coverage grade + `review_flags[]` (MTB readiness + 7-check suspicious-value audit, including cross-patient name collision + anchor-coverage gap)
- `review_flags.md` — auto-generated human-readable rendering of `readiness.json.review_flags[]` (only written when array non-empty)
- `review_summary.md` — **always written**: 1-page checklist of extracted key fields with verbatim source citations, for user spot-check (catches internally consistent but wrong ingestion that review_flags can't)
- `case_text.md` (consolidated narrative; every factual sentence anchored via `[[src:<bucket>/<canonical>.md#L<a>-L<b>]]` — bucket-relative, the desensitized MD that now lives next to its image)
- `update_log.json` — append-only audit trail of every full / incremental run (timestamps, added/removed files, affected summaries, readiness deltas)
- **6 structured JSON outputs** (schema-validated against `references/schemas/*.schema.json`):
  - `patient_summary.json` — demographics + diagnosis + current_status rollup
  - `timeline.json` — machine-readable mirror of `timeline.md`
  - `molecular.json` — NGS variants + IHC + MSI/MMR + TMB
  - `treatment_lines.json` — ordered lines of therapy
  - `labs.json` — lab panels with serial values
  - `comorbidities.json` — conditions + long-term meds + allergies
- `missing_items.json` — cancer-type checklist diff (driven by `references/checklists/<cancer_type>.yaml`)
- `source_inventory.json` — one entry per input source file/content unit: original/mirror path, LLM read mode, adapter provenance, sidecar path, bucket path, and persist/redaction intent. Conforms to `references/schemas/source_inventory.schema.json` (`source_inventory_v1`).
- `01_当前状态/`…`11_诊断证明/` (raw file buckets; filenames follow `<YYYY-MM-DD>_<doc_type>_<hospital>.<ext>` — 4-level hospital fallback). Each file is co-located with its **desensitized MD sidecar** at `<bucket>/<canonical>.md` (the downstream-only read source — no plaintext PII).
- `redaction_manifest.json` — 段B full-format hand-off contract (`redaction_manifest_v2`): one entry per persisted source file that needs body redaction, with `source_id/source_kind`, bucket + mirror paths, adapter frame, and PII `regions[]` carrying category + coordinates/structure locators only (never plaintext PII). Conforms to `references/schemas/redaction_manifest.schema.json`.
- `redaction_status.json` — written by 段B's `run_redaction_job.py`: per-source `pending/redacted_pending_qa/done/failed/blocked`, `coverage_passed`, `llm_qa_passed`, `qa_report_id`, `qa_passed`, `original_deleted`. Conforms to `references/schemas/redaction_status.schema.json` (`redaction_status_v2`).
- `source_redaction_status.json` — final archive/persist hard gate for all source files. Every `persist:true && redaction_required:true` source must be `done`, `coverage_passed:true`, `llm_qa_passed:true`, `qa_passed:true`, and `original_deleted:true`; unsupported binary formats are `blocked_unsupported` and cannot be persisted. Conforms to `references/schemas/source_redaction_status.schema.json` (`source_redaction_status_v1`).
- `病情简要总结.html` — 段D one-page case summary, 1:1 against the gold-standard template, generated after the Profile Card from desensitized JSON only (never raw images).

Additionally, at the patients-root level (one level above `<patient_code>`):

- `<alias>/` symlink → `<patient_code>/` (business-readable, when `profile.json.alias` is set; format `{patient_id_short}_{cancer_code}_{year}`, e.g. `17CE02_CRC_2019`)
- `alias_map.json` (when symlinks aren't supported, e.g. Windows / restricted containers)

## Locale (i18n)

This skill follows the shared locale contract in [`../../references/i18n.md`](../../references/i18n.md). organize is the **canonical writer** of `profile.json.locale`:

- On entry, if `profile.json` already exists, **read `profile.json.locale` and reuse it** (don't re-detect). Otherwise the Phase-2 Synthesis Worker **detects** the locale from the **primary patient-facing language of the records** (LLM judgment, mixed-language tie-break per i18n.md §2.1) and **persists** it to `profile.json.locale` (BCP-47, e.g. `zh` / `en` / `fr`).
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

   Decide `patient_code`: caller-supplied OR auto-generate `PT-<hex>` from `hash(basename + mtime)`. Resolve `patient_data_root` from `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Compute `patient_dir = <patient_data_root>/<patient_code>` and `mkdir -p` its 11 buckets + `ocr/` + `10_原始文件/`.

3. **Dispatch Phase 1 LLM Markdown Ingestion Workers (parallel)** — for each slice, dispatch one `general-purpose` subagent in **a single message with N tool calls** (so they run concurrently, not sequentially). Each worker gets:

   - `subagent_type: general-purpose`
   - `description: "Organize LLM ingestion slice <slice_id>"`
   - `prompt`: the full content of [`references/organizer-prompt-phase1-ocr.md`](references/organizer-prompt-phase1-ocr.md), with these `## Call parameters` appended at the end:
     - `slice_input_path: <absolute path to the slice's source directory>`
     - `slice_id: <short logical label — e.g. h1, h2, batch_a>`
     - `patient_dir: <absolute patient_dir>`
     - `original_subdir: <relative path under 10_原始文件/ where audit copies go — usually the source subdir's basename>`

   Each Phase 1 worker writes ONLY to `<patient_dir>/ocr/` (redacted MD sidecars) and `<patient_dir>/10_原始文件/<original_subdir>/` (audit mirror). It may create temporary adapter outputs (HEIC raster, PDF rendered pages, DOCX/table payloads) only to feed the driver LLM; those adapter outputs are not stored, not anchors, and not clinical text sources. Workers do NOT touch INDEX.md / timeline.md / profile.json / etc — those are Phase 2's job. Workers don't share context, so anti-anchoring is structurally enforced.

   Each worker returns: `{slice_id, files_processed, sidecars_written, pii_region_files_written, stub_sidecars, full_ingestion_sidecars, ingestion_uncertain_files, candidates_files, ingestion_blocked_files, continuation_needed, continuation_resume_from}`.

4. **Phase 1 continuation loop** — for each worker that returned `continuation_needed: true`, dispatch a continuation worker for that slice:

   > "Resume Phase 1 LLM Markdown ingestion for slice `<slice_id>` of `<patient_code>`. The previous dispatch processed up to `<continuation_resume_from>` and stopped. Skip every file whose sidecar already exists in `<patient_dir>/ocr/` (these have lower mtime than source); ingest all remaining files in `<slice_input_path>`. Return same JSON contract; set `continuation_needed: false` if done, or `true` with next resume point if context fills again."

   Loop per-slice until all slices report `continuation_needed: false`. Slices that finished cleanly do NOT need re-dispatch; only laggards. This is more efficient than re-dispatching the whole organize.

5. **Dispatch Phase 2 Synthesis Worker** — after every Phase 1 worker reports `continuation_needed: false`, dispatch a SINGLE `general-purpose` subagent for synthesis:

   - `subagent_type: general-purpose`
   - `description: "Organize synthesis"`
   - `prompt`: the full content of [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md), with these `## Call parameters` appended:
     - `patient_dir: <absolute patient_dir>`
     - `phase1_summary: <JSON list of all Phase 1 worker results>`

   Phase 2 reads all sidecars (cross-slice), classifies into the 11 buckets, builds source_inventory.json / INDEX.md / timeline.md / case_text.md / profile.json / readiness.json, runs the §4.6 review_flags audit (now WITH cross-slice visibility), and writes review_flags.md (if non-empty) + review_summary.md (always) + redaction_manifest.json + source_redaction_status.json skeleton.

   Phase 2 returns: `{role, patient_dir, files_classified, md_sidecars_relocated, coverage_complete, missing_sidecars, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path, source_inventory_path, source_redaction_status_path, redaction_manifest_path, archive_persist_ready}`.

6. **Coverage gap retry** — if Phase 2 returns `coverage_complete: false`, dispatch a retry-mini-Phase1 worker with just the missing files as input, then re-run Phase 2. Loop until `coverage_complete: true`. Most runs converge in 0 or 1 retries.

7. **Verify outputs** — parse Phase 2's returned JSON; confirm `profile.json` exists and required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are populated. If any are missing or null, surface to the user as a blocker before routing to any other sub-skill.

8. **Grade readiness** — from Phase 2's returned JSON take `readiness_grade` + `readiness_score`. If grade is F or D, present the information-gap checklist 🔴🟡🟢 (derived from `blocking_gaps`) to the patient.

9. **Display review_summary.md (MANDATORY, ALWAYS)** — read the file at `review_summary_path` and display its full content to the user. This is the **first** thing the user sees after organize — before profile card, before review_flags. It is a 1-page spot-check of extracted key fields with verbatim source citations.

   Why this is the first display: many real ingestion/transcription errors produce **internally consistent wrong values** (e.g. all 7 documents in one hospitalization copied the same wrong drug name). The 5-check `review_flags` audit cannot detect those — but a human reading `review_summary.md` can spot a wrong character in 30 seconds.

   After displaying, prompt the user: "请核对上面 5 个检查要点。任何字段需要修正,直接告诉我哪个字段 + 正确值,我会更新 profile.json 并重新生成清单。"

10. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after `review_summary.md`. This is a hard gate, not optional polish:
    - **If any 🔴 red flag present**: tell the user "进入下游 skill 之前请先逐条确认或 override 这些 🔴 项 — 它们会直接影响 trial-match / mtb-lite / vmtb 的推荐"
    - **If only 🟡/🟢 flags**: present them as "建议核对", do not block downstream routing
    - **If `review_flags_total: 0`**: still tell the user "所有提取字段已通过 5 项可疑值检查 (格式/跨文档矛盾/临床逻辑/原始证据/数值趋势), 无待确认项 — 但仍请核对上面的 review_summary.md 速查清单"
    - The user's resolution per flag (`accept_suggestion` / `keep_original` / `custom_value` / `defer`) is logged back into `readiness.json.review_flags[i].user_confirmed = true` plus a `resolution` sub-object.

11. **Output profile card** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "🔍 待人工确认" section pulls from `readiness.json.review_flags[]`.

    **Downstream gate**: do NOT route the user to any downstream sub-skill (mtb-lite / trial-match / vmtb / nutrition / education) while any 🔴 red review_flag is unconfirmed. A wrong drug name at this stage poisons every downstream report.

12. **Generate 病情简要总结.html (段D)** — immediately after the Profile Card, dispatch a `general-purpose` subagent with the full content of [`references/case-summary-html-prompt.md`](references/case-summary-html-prompt.md), appending `## Call parameters`: `patient_dir: <absolute patient_dir>`. The worker reads only the **desensitized** structured JSONs (`profile.json` / `patient_summary.json` / `molecular.json` / `labs.json` / `treatment_lines.json` / `timeline.json` + the imaging段 of `case_text.md`) — never raw images, never a sidecar with plaintext PII. The narrative 病情概要 段 is generated by the subagent in `profile.json.locale` (LLM, no hardcoded keyword/template-句 stitching); every other section is a direct field-map. The subagent assembles a **data JSON** (`{{i18n.*}}` string table for the locale + scalar fields + the section LOOP arrays `lesions` / `molecular_rows` / `labs` / `treatment_lines` / `path_items`, each 0..N — an empty array is fine, the template's `RENDER_IF_NOT` shows the `资料缺失` placeholder), then **renders deterministically** through the generic engine:

    ```bash
    python3 scripts/render_html_template.py \
      --template references/templates/case-summary.template.html \
      --data <patient_dir>/.case_summary_data.json \
      --out  <patient_dir>/病情简要总结.html
    ```

    The renderer is a zero-medical-logic template engine: it only substitutes `{{key}}` and expands `<!-- LOOP -->` / `<!-- RENDER_IF -->` blocks from the data, so CSS/DOM stay 1:1 and clinical entities are passed through verbatim. It stamps a `template_sha256:` provenance comment proving the HTML came from the template. 患者标识 stays coarse-grained (女 / 50+ / 海外 — never real name or birth date); any `null` field maps to the `资料缺失` placeholder, never a fabricated value.

    **🔴 TEXT/HTML GATE — 段D HTML is complete when both hold:**
    1. `病情简要总结.html` was produced by `render_html_template.py` from `references/templates/case-summary.template.html` (**rendered, not hand-written**). A subagent that pastes HTML inline fails this gate.
    2. `python3 scripts/validate_case_summary_html.py --html <patient_dir>/病情简要总结.html --template references/templates/case-summary.template.html` exits 0 (shape + PII + provenance invariants hold).

    The full archive/persist acceptance门 is separate: `python3 scripts/validate_structured_outputs.py <patient_dir>` exits 0 only after `source_inventory.json` is complete and every persisted source has `source_redaction_status.done && qa_passed && original_deleted`. Before Step 13, this gate may fail because source-file redaction is still pending/blocked; that does **not** invalidate the desensitized MD/JSON/HTML artifacts, but it means `archive_persist_ready:false`. Surface in the final report to the user: the **`template_sha`** echoed by `validate_case_summary_html.py` (proof the template was used) plus the archive/persist readiness state. Do not declare final archive/persist complete until Step 13 passes and the full acceptance gate exits 0.

13. **Run or schedule source-file redaction before archive/persist (段B)** — Phase 2 has already written `redaction_manifest.json` and `source_redaction_status.json` for every persisted source that needs body redaction. A backend worker may run this after 段A/D text/HTML generation, but **final archive/persist MUST block until every persisted source is redacted, LLM-QA-passed, and its plaintext original deleted**. 段B does not do OCR or PII judgment. It only applies the LLM-provided coordinates/locators from `redaction_manifest_v2`.

    ```bash
    python3 skills/cancer-buddy-organize/scripts/run_redaction_job.py prepare <patient_dir>
    # Then an LLM QA worker reviews redacted previews/payloads and writes:
    # <patient_dir>/llm_redaction_qa.json  (pass/fail + category + file id only; no PII)
    python3 skills/cancer-buddy-organize/scripts/run_redaction_job.py commit \
      <patient_dir> \
      --qa-report <patient_dir>/llm_redaction_qa.json
    ```

    `prepare` reads the v2 manifest, generates redacted candidates for images/HEIC, rasterized PDFs, DOCX, XLSX/CSV/TXT/HTML/MD, or redacted archive payloads, then writes `redacted_pending_qa` status. It does **not** replace bucket files and does **not** delete originals. The LLM QA gate reviews only redacted previews/payloads and writes pass/fail by file id with no PII. `commit` runs the deterministic coverage gate and only when `coverage_passed:true && llm_qa_passed:true` atomically replaces the bucket copy and the `10_原始文件/` mirror with the redacted candidate, deletes the pre-redaction original by replacement, and writes `done + qa_passed:true + original_deleted:true`. Failed/blocked sources remain local-only and cannot enter the final package. Full manifest/status contract, exit codes, and platform trigger convention: [`references/redaction-job.md`](references/redaction-job.md).

14. **无关文件处置门 (段E, MANDATORY when the relevance gate isolated anything)** — Phase 2's Step 1·0 relevance triage (see [`references/relevance-gate.md`](references/relevance-gate.md)) diverted any non-medical file out of the 11 buckets into `99_无关文件/` (`high_confidence/` vs `uncertain/`). If either sub-dir is non-empty, surface **one plain-language disposition notice** (rendered in `profile.json.locale` — see `references/relevance-gate.md` → disposition-notice §) before the user moves on. The privacy-floor sentence **"我们不保存你的原始无关文件 —— 你不确认，我也会自动删除"** (zh template; rendered semantically-identical in the user's locale, e.g. `en`: "We don't keep your raw unrelated files — if you don't confirm, I'll delete them automatically.") is mandatory and must appear in that locale with no softening — the user is entitled to know *silence ⇒ deletion* before it happens. List each `uncertain/` (borderline) file individually with a one-line reason; summarize the `high_confidence/` batch as a count.

    Then parse the user's response into exactly three resolution paths (full logic in `relevance-gate.md`):
    - **删 (high-confidence non-medical)** — user confirms unrelated **OR** does not respond / defers / 随便 / closes the chat → **delete** the file from `99_无关文件/high_confidence/`. This is irreversible and intended (privacy floor: silence ⇒ delete). The `99_无关文件/` copy is the only copy (these were never anchored or bucketed), so deleting it is the whole point.
    - **回收 (reclassify — "X 其实有用")** — user claims a specific isolated file matters → move it out of `99_无关文件/` into its correct typed bucket, run the *normal* late-arriving path (LLM ingestion → 脱敏 MD → canonical rename → co-locate MD → add to INDEX/timeline/case_text/structured JSONs; raster image also appended to `redaction_manifest.json` for 段B).
    - **Hold (borderline `relevance_uncertain`, the one exception)** — for borderline files the user has **not** explicitly resolved → **do nothing, keep in `99_无关文件/uncertain/`, never auto-delete.** Silence deletes a high-confidence non-medical file; silence does **not** delete a borderline file — deleting something that might be a real medical record is the worse error. Only an explicit "删"/"无关" deletes it; "留"/"这是病历" reclassifies it. Either way mark the `relevance_uncertain` review_flag `user_confirmed: true` with the chosen `resolution`.

    Record every isolated/deleted/reclassified/held action in `update_log.json.relevance` (the `auto_deleted` array is the irreversible-action ledger). The authoritative deletion red-line is the 段E entry in [`../../references/safety-guardrails.md`](../../references/safety-guardrails.md); this step is its operational门控.

15. **Conversation-incremental capture (段C, on demand)** — this is not part of the initial organize run; it is the entry point for later turns. When the patient/caregiver is *chatting* about their condition (not handing over files) and a `<patient_dir>` with an existing `update_log.json` exists, run `run_mode: "conversation_incremental"` (see the dedicated section below) to capture archivable facts surfaced in dialogue → diff card → user-confirmed write, with `[[src:conversation:<ISO8601>]]` provenance. Unconfirmed talk never touches formal fields.

16. **Upload reconciliation (扩段C, on re-upload)** — when the user re-uploads one or more files onto an **already-existing** `patient_dir` (has `update_log.json`), run `run_mode: "upload_reconciliation"` (see [`references/upload-reconciliation.md`](references/upload-reconciliation.md)). Each new file first passes the 段E relevance gate (high-confidence non-medical → 段E isolate/delete logic, not reconciliation); medical/borderline files then get an LLM relation判断 — **new / supersede / conflict** (semantic comparison against the existing archive, NOT a hardcoded same-name-same-date Python check) → a diff card asking **替换? 并存? 忽略?**. This **reuses段C's single "先确认" gate — it does not start a second gate**: 替换 archives the old doc to `_superseded_<ts>/` (not deleted) and remaps its anchors; 并存 keeps both and adds a second timeline row; 忽略 / 未确认 writes no formal field. conflict is never silently overwritten — both facts are shown side by side for the user to adjudicate, and 关键字段 (分期/分子/治疗线) conflicts require explicit confirmation. Provenance logs an `update_log.json` entry with `run_mode: "upload_reconciliation"`. **This flow introduces no new auto-deletion** — the only auto-delete is段E's high-confidence non-medical path; borderline medical files are never auto-deleted without explicit confirmation.

## Runtime adaptation

The Workflow above (Step 2–5: `glob`-based slicing → parallel `Agent` Phase-1 LLM Markdown ingestion fan-out → continuation loop → single `Agent` Phase-2 reduce, plus `Read`-based LLM vision/file-context ingestion and adapter commands such as `sips` HEIC decode) is the **Claude Code reference binding** — one concrete way to drive organize, not the contract. The runtime-neutral **behavior contract** (what each step produces / when it may write / which invariants hold, with zero tool names) lives in [`references/organize-contract.md`](references/organize-contract.md); the per-host fill-ins are in [`references/runtime-bindings/`](references/runtime-bindings/) (`claude-code.md` = the mechanism documented here; `headless-codex.md`; `_template.md` for OpenClaw/OpenCode/other agents).

What this means for non-CC hosts:

- A headless / single-process host (codex GPT-5.5, workbuddy, OpenClaw/OpenCode, Cursor, …) **drives its own steps** — the `Agent` fan-out + reduce, `Read` vision/file context, and `sips` decode are reference mechanisms, not requirements. It may run Phase-1 sequentially, feed LLM vision via `-i` or LLM file context, adapt formats with cross-platform commands, and persist only redacted outputs with its own storage primitives.
- Whatever the binding, it produces the **same canonical output set** the contract defines (11 buckets + co-located 脱敏 MD, `source_inventory.json`, `profile.json`, `timeline.*`, `case_text.md`, `readiness.json`, `review_flags.md`, the 6 structured JSONs, `missing_items.json`, `update_log.json`, `redaction_manifest.json`, `source_redaction_status.json`, bucket-relative anchors) and honors the same invariants (sidecar text is LLM-generated; sidecar is the only downstream plaintext boundary; unconfirmed → no formal write / no irreversible delete; clinical entities verbatim; final persist waits for source-file redaction; logic/schema/产物结构 unchanged).
- The five seams (编排 / LLM 输入源 / 格式适配 / 确认门 / 存储+持久化前本体脱敏) and each host's fill-in are the matrix in `organize-contract.md` §6. The `MAX 15 image files per worker` rule in Step 2 is a Claude many-image budget feature → **host-tunable** (don't slice / slice to the host's own budget); it is not a contract invariant.

Claude Code does not change: the mechanism in Step 2–5 is preserved verbatim as the reference binding, the neutral layer is added on top, and the CC path regresses identically.

## Why fan-out + reduce instead of single-pass

The original design was a single subagent processing every input file sequentially. A 73-image archive took ~33 minutes. Splitting into Phase 1 (parallel per-slice LLM Markdown ingestion) + Phase 2 (cross-slice synthesis + audit) gives three benefits:

1. **Speed**: 3 parallel Phase-1 LLM ingestion workers + 1 Phase-2 finishes in roughly the time of the SLOWEST slice + the synthesis pass — ~3× faster on multi-hospitalization archives in practice.
2. **Anti-anchoring is stronger**: each Phase 1 worker only sees its slice (one hospitalization), so the narrative window the model could anchor on is shorter. Cross-slice contradictions are caught explicitly in Phase 2's §4.6 audit (which has the deterministic cross-doc check) rather than being smoothed over by a single agent's running narrative.
3. **Better failure isolation**: if one slice's worker hits context exhaustion, only that slice retries (continuation loop). Slices that finished cleanly are not re-dispatched.

Single-pass is preserved for small inputs (< 30 files OR no subdirs) — the parallelism overhead isn't worth it.

## Incremental mode

When `<patient_dir>` already has `update_log.json`, the caller may pass `run_mode: "incremental"` to Phase 2. In that mode:

- Phase 1 only re-ingests files that are new under `10_原始文件/` or whose source mtime is newer than their sidecar. Other slices are skipped.
- Phase 2 reclassifies only the new sidecars; existing bucket assignments are preserved.
- Top-level artifacts (`case_text.md`, `timeline.md`, `patient_summary.json`, `timeline.json`, `molecular.json`, `treatment_lines.json`, `labs.json`, `comorbidities.json`, `missing_items.json`) are rewritten only when their content would actually change.
- `update_log.json` gets a new entry with `run_mode: "incremental"`, `added_files`, `removed_files`, `affected_summaries`, `triggered_by`, `reason`.
- `profile.json.alias` is sticky — never overwritten by an incremental run.

Use full mode (`run_mode: "full"`, default) for the very first organize, or whenever the patient indicates major changes ("我换了治疗方案", "重新做了一次基因检测") where rewriting the whole narrative is cleaner than merging.

**Re-uploading files onto an existing archive** is a distinct entry: pass `run_mode: "upload_reconciliation"` instead of plain `incremental`. That mode runs the 段E relevance gate on each new file, then an LLM new/supersede/conflict relation判断 → a diff card (替换? 并存? 忽略?) gated by the **same "先确认" door段C uses** — unconfirmed re-uploads never write formal fields, and 替换 archives the superseded doc to `_superseded_<ts>/` rather than deleting it. Full logic: [`references/upload-reconciliation.md`](references/upload-reconciliation.md). Plain `incremental` (above) is for newly-added files that don't supersede or conflict with an existing doc.

## Conversation-incremental mode (段C)

When the patient or caregiver is *chatting* about their condition (not handing over files) and a `<patient_dir>` with an existing `update_log.json` already exists, the caller may run `run_mode: "conversation_incremental"` to capture archivable facts that surface in the dialogue. Dispatch a `general-purpose` subagent with the full content of [`references/conversation-incremental-prompt.md`](references/conversation-incremental-prompt.md), appending `## Call parameters`: `patient_dir`, `conversation_turn` (verbatim user message + context), `turn_timestamp` (ISO-8601), `actor_role`.

The flow: an LLM detects candidate archivable facts (新诊断/分期 / 新检验值 / 治疗变更 / 症状 / 体能-ECOG) → maps each to a `profile.json` field or a `timeline.md` row → presents a **diff card** (before → after, with the user's own words as 依据) → the user confirms / corrects / defers → only confirmed candidates are written. Provenance uses the conversation anchor `[[src:conversation:<ISO8601>]]` (never a file anchor). Confirmed facts land in `09_患者补充/conversation_notes/` with a `patient_curated` tag and update the formal field/row; `update_log.json` gets a `run_mode: "conversation_incremental"` entry. **Unconfirmed talk never touches formal fields** — this gate prevents a mis-spoken value from poisoning downstream reports. This mode does NOT re-ingest files or re-run synthesis; for new *files* use full or incremental mode. Major changes ("我整套方案都换了") route to a full re-organize, not turn-by-turn merge.

## Business-readable alias

When `profile.json.alias` is set by Phase 2 (format `{patient_id_short}_{cancer_code}_{year}`, e.g. `17CE02_CRC_2019`), the synthesis worker creates a symlink under the patients root:

```
<patients_root>/17CE02_CRC_2019 -> PT-17CE02BC33/
```

Internal storage continues to use the `PT-<hex>` directory. Downstream sub-skills accept either name; the alias is the human-friendly handle for exports and conversations ("我跟病人沟通的是 003_CRC_2024,不是 PT- 那串十六进制"). If filesystem symlinks are not available, the synthesis worker writes `<patients_root>/alias_map.json` mapping aliases to `PT-<hex>` codes.

## patient_code collision

If the generated `patient_code` (e.g. `PT-17CE02BC33`) already exists under the patients root, the subagent appends `_2`, `_3`, etc., and announces the assigned code in the summary.

## Configurable root

The `patients/` root resolves in order: `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Override by exporting one of those. Shared with vmtb-skill.

## Safety

Organize does not make medical recommendations. Still:

- Never fabricate fields — when a value is truly unreadable in the source, the subagent writes `null` (JSON) or `[OCR_UNCERTAIN]` (text) and surfaces it as a gap.
- Desensitization only masks PII — it never alters clinical characters (anti-anchoring). The MD sidecar is the downstream-only read source and must not carry plaintext PII.
- Downstream sub-skills apply the full `safety-guardrails.md` rule set when they read what organize produced; wrong data here poisons every downstream report.
- `10_原始文件/` is local staging/audit during the run — a byte-identical mirror of every source file **until** source-file redaction commits. Per the platform "redact-then-delete" carve-out (`safety-guardrails.md`), once a file's redaction status has `coverage_passed:true`, `llm_qa_passed:true`, and `qa_passed:true`, the job replaces the mirror with the **redacted** version and deletes the pre-redaction original by replacement (bucket copy + mirror original); the audit chain is then itself desensitized. QA failure/blocked → original stays only in local workspace for manual handling, marked `failed`/`blocked`, and must not be persisted.

## Next-step guidance

After successful organize, route the patient to the most relevant next sub-skill based on their initial question:

- Newly diagnosed, wants to understand → `cancer-buddy-explore` (maximal diagnostics tier)
- Has gene report, wants treatment guidance → `cancer-buddy-mtb-lite`
- Looking for trials → `cancer-buddy-trial-match`

## Role behavior

Authoritative matrix in `../../references/roles.md`. For this skill:

- **Role = patient**: First-person. "帮我整理我的病历" → produce profile.json / timeline.md / readiness.json. Profile's `data_sources[]` names patient as source.
  - *Disclosure*: disclosure_state=suppressed on patient entry → warn that organize will likely break suppression; proceed only with confirmation.
- **Role = caregiver**: Second-person. "帮你家人整理报告". On first-ever organize in this patient_code, offer to populate `profile.json.caregivers[]` with the caregiver's relation + name + contact preference. Tone warmer, includes "整理这些很累吧，一步一步来"-style acknowledgment.
- **Role = family**: Refuse. Emit: `病历整理要靠主照护者操作（Ta 手里有原件）。要不要我帮你生成一份 2 页要点让 Ta 参考？` Do not run organize.

## References

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) — Phase 1 worker prompt: per-slice LLM Markdown ingestion, parallel-safe, sidecars-only
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — Phase 2 worker prompt: cross-slice synthesis + 7-check review_flags audit + review_summary + 6 structured JSONs + missing_items.json + update_log.json + alias
- [conversation-incremental-prompt.md](references/conversation-incremental-prompt.md) — 段C conversation-incremental worker prompt: detect archivable facts in chat → diff card → user-confirmed write to profile field / timeline row with `[[src:conversation:<ISO8601>]]` provenance + `patient_curated` tag; unconfirmed talk never written
- [relevance-gate.md](references/relevance-gate.md) — 段E medical-relevance triage: LLM judgment (not keyword list) → medical / non-medical-high-confidence / borderline; `99_无关文件/` quarantine semantics; disposition notice + privacy floor; 删 (high-confidence auto-delete on no-confirm) / 回收 (reclassify) / hold (borderline never auto-deleted); `relevance_uncertain` 8th review_flag + `update_log.json.relevance` ledger
- [upload-reconciliation.md](references/upload-reconciliation.md) — 扩段C re-upload reconciliation: LLM new/supersede/conflict relation判断 (not hardcoded same-name-date) → diff card 替换?/并存?/忽略? reusing段C's "先确认" gate; 替换 archives old doc to `_superseded_<ts>/` (not deleted) + anchor remap; conflict never silently overwritten; introduces no new auto-deletion; `run_mode: "upload_reconciliation"` update_log
- [case-summary-html-prompt.md](references/case-summary-html-prompt.md) — 段D worker prompt: read desensitized JSONs → fill the gold-standard template 1:1 → `病情简要总结.html`; subagent generates only the 病情概要 narrative, every other section is field-mapping; coarse-grained identity, `null` → 待补充
- [templates/case-summary.template.html](references/templates/case-summary.template.html) — 段D gold-standard HTML/CSS template (1:1 reproduction target, not "style-similar")
- [redaction-job.md](references/redaction-job.md) — 段B contract: `redaction_manifest_v2` → `run_redaction_job.py prepare` → LLM QA → `commit` → bucket+mirror replace → delete original (only on coverage + LLM QA pass) → `redaction_status_v2`; pre-persist worker trigger convention
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [references/schemas/](references/schemas/) — Draft 2020-12 JSON Schemas for the 6 structured outputs + `missing_items.json` + `source_inventory.json` + `source_redaction_status.json`
- [references/schemas/anchor-contract.md](references/schemas/anchor-contract.md) — `[[src:...]]` anchor token syntax + coverage + path validity contract (bucket-relative file anchors + `conversation:<ISO8601>` anchors; `ocr/` prefix deprecated)
- [references/schemas/redaction_manifest.schema.json](references/schemas/redaction_manifest.schema.json) — `redaction_manifest_v2` schema (段B full-format source-redaction work queue produced by Phase 2)
- [references/schemas/redaction_status.schema.json](references/schemas/redaction_status.schema.json) — `redaction_status_v2` schema (段B per-file progress written by the job)
- [references/checklists/](references/checklists/) — cancer-type minimum-data checklists driving `missing_items.json`
- [scripts/validate_structured_outputs.py](scripts/validate_structured_outputs.py) — **archive/persist acceptance门** (one entry, aggregated exit code): the original structured-output schema + anchor validation **plus** PII residue rescan (`pii_rescan`), full-format redaction-manifest coverage for every persisted redaction-required source, required `source_inventory.json`, required `source_redaction_status.json` hard gate for persisted sources, and case-summary HTML shape+provenance (`validate_case_summary_html`).
- [scripts/render_html_template.py](scripts/render_html_template.py) — generic, stdlib-only (no jinja2) HTML template engine with **zero medical/case logic**: substitutes `{{key}}` and expands `<!-- LOOP -->` (0..N, data-driven) / `<!-- RENDER_IF -->` / `<!-- RENDER_IF_NOT -->` (empty section → `资料缺失` placeholder, never deleted) from a data JSON; stamps a `template_sha256:` provenance comment. Used by 段D to render `病情简要总结.html` from `templates/case-summary.template.html`.
- [scripts/validate_case_summary_html.py](scripts/validate_case_summary_html.py) — case-summary HTML validator: checks **shape invariants only** (template-fixed, patient-independent) — byte-identical `<style>`, used-classes ⊆ template classes, no residual `{{…}}`, no PII / precise age, full section skeleton, and `template_sha` provenance == the supplied template's SHA-256. **Never** asserts patient-specific content exists (would false-positive on a patient with no labs/lesions). Echoes `template_sha` on pass.
- [scripts/pii_rescan.py](scripts/pii_rescan.py) — deterministic PII-residue门 on the desensitized MD sidecars (the single downstream plaintext boundary): independently re-scans sidecar bodies with a text-only PII-pattern family, skips `[PII_MASKED]` values + the `## PII` trailer, flags any surviving label+value or standalone 身份证/手机/座机. Detector, not auto-rewriter (re-masking is a judgement task).
- [scripts/run_redaction_job.py](scripts/run_redaction_job.py) — 段B batch processor: v2 manifest → deterministic redacted candidates → LLM QA gate → commit bucket+mirror replace → delete-on-pass → `redaction_status.json` (idempotent, retryable)
- [../../references/preflight.md](../../references/preflight.md) — shared entry-gate (role + disclosure + readiness grade + Step 2.5 review_flags red gate + schema validity)
- [../../references/i18n.md](../../references/i18n.md) — shared locale contract: detect → persist `profile.json.locale` → reuse; scaffold-localized / clinical-entity-verbatim policy; locale→bucket-name map (`NN_` prefix stable)
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
