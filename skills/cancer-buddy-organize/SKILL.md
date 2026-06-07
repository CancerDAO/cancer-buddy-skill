---
name: cancer-buddy-organize
description: "Organize patient medical records from PDF/images/docx into a canonical patients/<patient_code>/ directory with profile.json, timeline.md, readiness.json, desensitized MD sidecars co-located in 01_当前状态…11_诊断证明 buckets, 6 schema-validated structured JSONs (patient_summary / timeline / molecular / treatment_lines / labs / comorbidities), a cancer-checklist-driven missing_items.json, a business-readable alias ({patient_id}_{cancer_type}_{year}), an update_log.json audit trail, a 1:1 gold-standard 病情简要总结.html case summary, and a redaction_manifest.json hand-off for the async PaddleOCR pixel-redaction job. Every factual statement carries a [[src:...]] anchor (bucket-relative MD, or conversation:<ISO8601> for chat-captured facts). Use when the user hands over a folder of medical records, or says 病历整理, 我有一堆报告, 帮我整理报告. For multi-hospitalization archives ≥ 30 files: fans out parallel Phase-1 OCR Workers (one per source subdirectory) and reduces with a Phase-2 Synthesis Worker that does cross-slice + cross-patient review_flags audit. For small/flat inputs: single-pass. Supports run_mode=incremental for delta updates and run_mode=conversation_incremental to capture archivable facts from chat (diff-card confirmed)."
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
- `review_summary.md` — **always written**: 1-page checklist of extracted key fields with verbatim source citations, for user spot-check (catches consistent-but-wrong OCR that review_flags can't)
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
- `01_当前状态/`…`11_诊断证明/` (raw file buckets; filenames follow `<YYYY-MM-DD>_<doc_type>_<hospital>.<ext>` — 4-level hospital fallback). Each file is co-located with its **desensitized MD sidecar** at `<bucket>/<canonical>.md` (the downstream-only read source — no plaintext PII).
- `redaction_manifest.json` — hand-off contract to 段B (the async PaddleOCR pixel-redaction job): one entry per raster image still carrying plaintext PII pixels, listing its bucket copy + `10_原始文件/` mirror + `pii_hint[]` + `status: "pending"`. Conforms to `references/schemas/redaction_manifest.schema.json` (`redaction_manifest_v1`).
- `redaction_status.json` — written by 段B's `run_redaction_job.py` (not by organize): per-file `pending/done/failed/blocked`, `qa_passed`, `original_deleted`. Conforms to `references/schemas/redaction_status.schema.json` (`redaction_status_v1`).
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

   **MAX 15 image files per Phase 1 worker.** Claude has a per-conversation total-image budget when many images are loaded into a single context. A worker that tries to OCR 25+ HEIC images in one dispatch will hit "An image in the conversation exceeds the dimension limit for many-image requests" partway through and abort with partial output. (Empirically observed: 24-image slice failed at sidecar 5 of 24.)

   Slicing rules:

   - **Single-pass mode**: ≤ 15 files total → one Phase 1 worker
   - **Sub-directory fan-out**: ≥ 2 subdirectories AND each subdir has ≤ 15 files → one worker per subdir
   - **Sub-directory fan-out with internal split**: ≥ 2 subdirectories AND any subdir has > 15 files → split each oversized subdir into halves/thirds (e.g. `h1_part1`/`h1_part2`), one worker per part. Typical case: 73 images across 3 hospitalizations of ~25 each → 6 workers (each hospitalization split into 2 halves of ~12-13 files).
   - **Flat fan-out**: no subdirectories, > 15 files → split into N-file chunks (alphabetical or arbitrary), name slices `batch_a`/`batch_b`/etc.

   Workers across slices run in parallel (single message, N concurrent Agent tool calls). Within a worker, files run sequentially.

   Decide `patient_code`: caller-supplied OR auto-generate `PT-<hex>` from `hash(basename + mtime)`. Resolve `patient_data_root` from `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Compute `patient_dir = <patient_data_root>/<patient_code>` and `mkdir -p` its 11 buckets + `ocr/` + `10_原始文件/`.

3. **Dispatch Phase 1 OCR Workers (parallel)** — for each slice, dispatch one `general-purpose` subagent in **a single message with N tool calls** (so they run concurrently, not sequentially). Each worker gets:

   - `subagent_type: general-purpose`
   - `description: "Organize OCR slice <slice_id>"`
   - `prompt`: the full content of [`references/organizer-prompt-phase1-ocr.md`](references/organizer-prompt-phase1-ocr.md), with these `## Call parameters` appended at the end:
     - `slice_input_path: <absolute path to the slice's source directory>`
     - `slice_id: <short logical label — e.g. h1, h2, batch_a>`
     - `patient_dir: <absolute patient_dir>`
     - `original_subdir: <relative path under 10_原始文件/ where audit copies go — usually the source subdir's basename>`

   Each Phase 1 worker writes ONLY to `<patient_dir>/ocr/` (sidecars) and `<patient_dir>/10_原始文件/<original_subdir>/` (audit mirror). They do NOT touch INDEX.md / timeline.md / profile.json / etc — those are Phase 2's job. Workers don't share context, so anti-anchoring is structurally enforced (each worker only sees its slice, no narrative buildup across hospitalizations).

   Each worker returns: `{slice_id, files_processed, sidecars_written, stub_sidecars, full_ocr_sidecars, ocr_uncertain_files, candidates_files, continuation_needed, continuation_resume_from}`.

4. **Phase 1 continuation loop** — for each worker that returned `continuation_needed: true`, dispatch a continuation worker for that slice:

   > "Resume Phase 1 OCR for slice `<slice_id>` of `<patient_code>`. The previous dispatch processed up to `<continuation_resume_from>` and stopped. Skip every file whose sidecar already exists in `<patient_dir>/ocr/` (these have lower mtime than source); OCR all remaining files in `<slice_input_path>`. Return same JSON contract; set `continuation_needed: false` if done, or `true` with next resume point if context fills again."

   Loop per-slice until all slices report `continuation_needed: false`. Slices that finished cleanly do NOT need re-dispatch; only laggards. This is more efficient than re-dispatching the whole organize.

5. **Dispatch Phase 2 Synthesis Worker** — after every Phase 1 worker reports `continuation_needed: false`, dispatch a SINGLE `general-purpose` subagent for synthesis:

   - `subagent_type: general-purpose`
   - `description: "Organize synthesis"`
   - `prompt`: the full content of [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md), with these `## Call parameters` appended:
     - `patient_dir: <absolute patient_dir>`
     - `phase1_summary: <JSON list of all Phase 1 worker results>`

   Phase 2 reads all sidecars (cross-slice), classifies into the 11 buckets, builds INDEX.md / timeline.md / case_text.md / profile.json / readiness.json, runs the §4.6 review_flags audit (now WITH cross-slice visibility), and writes review_flags.md (if non-empty) + review_summary.md (always).

   Phase 2 returns: `{role, patient_dir, files_classified, ocr_sidecars_read, coverage_complete, missing_sidecars, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path}`.

6. **Coverage gap retry** — if Phase 2 returns `coverage_complete: false`, dispatch a retry-mini-Phase1 worker with just the missing files as input, then re-run Phase 2. Loop until `coverage_complete: true`. Most runs converge in 0 or 1 retries.

7. **Verify outputs** — parse Phase 2's returned JSON; confirm `profile.json` exists and required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are populated. If any are missing or null, surface to the user as a blocker before routing to any other sub-skill.

8. **Grade readiness** — from Phase 2's returned JSON take `readiness_grade` + `readiness_score`. If grade is F or D, present the information-gap checklist 🔴🟡🟢 (derived from `blocking_gaps`) to the patient.

9. **Display review_summary.md (MANDATORY, ALWAYS)** — read the file at `review_summary_path` and display its full content to the user. This is the **first** thing the user sees after organize — before profile card, before review_flags. It is a 1-page spot-check of extracted key fields with verbatim source citations.

   Why this is the first display: many real OCR errors produce **internally consistent wrong values** (e.g. all 7 documents in one hospitalization OCR'd to the same wrong drug name). The 5-check `review_flags` audit cannot detect those — but a human reading `review_summary.md` can spot a wrong character in 30 seconds.

   After displaying, prompt the user: "请核对上面 5 个检查要点。任何字段需要修正,直接告诉我哪个字段 + 正确值,我会更新 profile.json 并重新生成清单。"

10. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after `review_summary.md`. This is a hard gate, not optional polish:
    - **If any 🔴 red flag present**: tell the user "进入下游 skill 之前请先逐条确认或 override 这些 🔴 项 — 它们会直接影响 trial-match / mtb-lite / vmtb 的推荐"
    - **If only 🟡/🟢 flags**: present them as "建议核对", do not block downstream routing
    - **If `review_flags_total: 0`**: still tell the user "所有提取字段已通过 5 项可疑值检查 (格式/跨文档矛盾/临床逻辑/原始证据/数值趋势), 无待确认项 — 但仍请核对上面的 review_summary.md 速查清单"
    - The user's resolution per flag (`accept_suggestion` / `keep_original` / `custom_value` / `defer`) is logged back into `readiness.json.review_flags[i].user_confirmed = true` plus a `resolution` sub-object.

11. **Output profile card** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "🔍 待人工确认" section pulls from `readiness.json.review_flags[]`.

    **Downstream gate**: do NOT route the user to any downstream sub-skill (mtb-lite / trial-match / vmtb / nutrition / education) while any 🔴 red review_flag is unconfirmed. A wrong drug name at this stage poisons every downstream report.

12. **Generate 病情简要总结.html (段D)** — immediately after the Profile Card, dispatch a `general-purpose` subagent with the full content of [`references/case-summary-html-prompt.md`](references/case-summary-html-prompt.md), appending `## Call parameters`: `patient_dir: <absolute patient_dir>`. The worker reads only the **desensitized** structured JSONs (`profile.json` / `patient_summary.json` / `molecular.json` / `labs.json` / `treatment_lines.json` / `timeline.json` + the imaging段 of `case_text.md`) — never raw images, never a sidecar with plaintext PII — fills the gold-standard template [`references/templates/case-summary.template.html`](references/templates/case-summary.template.html) 1:1, and writes `<patient_dir>/病情简要总结.html`. The scaffold (section titles, disclaimer, labels, "待补充" placeholders) is rendered in `profile.json.locale` via the template's i18n string-table block; CSS/DOM stay 1:1; clinical entities verbatim. The narrative 病情概要 段 is generated by the subagent in that locale (LLM, no hardcoded keyword/template-句 stitching); all other sections are direct field-mapping from the JSONs. 患者标识 stays coarse-grained (女 / 50+ / 海外 — never real name or birth date); any `null` field renders `待主治医师补充 / 资料缺失` rather than a fabricated value.

13. **Hand off the redaction job (段B)** — organize does NOT run the pixel-redaction itself and does NOT block on it. By this point Phase 2 has already written `redaction_manifest.json` (the work queue). The platform's async backend worker picks it up and runs the vendored PaddleOCR redactor with the OCR venv interpreter:

    ```bash
    ~/.venvs/mtb-ocr/bin/python \
      skills/cancer-buddy-organize/scripts/run_redaction_job.py <patient_dir>
    ```

    `run_redaction_job.py` reads the manifest, redacts each image via `redact_ocr.py`'s `redact_image_ocr()`, runs a **QA gate** (re-scan confirms no residual PII before the irreversible delete), then replaces both the bucket copy and the `10_原始文件/` mirror with the redacted version, deletes the pre-redaction original **only when `qa_passed: true`**, and writes per-file progress to `redaction_status.json` (idempotent — re-runs skip `done` files; missing venv → all `blocked`). Full manifest/status contract, exit codes, and platform trigger convention: [`references/redaction-job.md`](references/redaction-job.md). The skill surfaces to the user that pixel redaction runs asynchronously and the bucket images may still carry plaintext PII pixels until the job reports `done` — the desensitized `.md` sidecars are already clean and are the only downstream read source.

14. **无关文件处置门 (段E, MANDATORY when the relevance gate isolated anything)** — Phase 2's Step 1·0 relevance triage (see [`references/relevance-gate.md`](references/relevance-gate.md)) diverted any non-medical file out of the 11 buckets into `99_无关文件/` (`high_confidence/` vs `uncertain/`). If either sub-dir is non-empty, surface **one plain-language disposition notice** (rendered in `profile.json.locale` — see `references/relevance-gate.md` → disposition-notice §) before the user moves on. The privacy-floor sentence **"我们不保存你的原始无关文件 —— 你不确认，我也会自动删除"** (zh template; rendered semantically-identical in the user's locale, e.g. `en`: "We don't keep your raw unrelated files — if you don't confirm, I'll delete them automatically.") is mandatory and must appear in that locale with no softening — the user is entitled to know *silence ⇒ deletion* before it happens. List each `uncertain/` (borderline) file individually with a one-line reason; summarize the `high_confidence/` batch as a count.

    Then parse the user's response into exactly three resolution paths (full logic in `relevance-gate.md`):
    - **删 (high-confidence non-medical)** — user confirms unrelated **OR** does not respond / defers / 随便 / closes the chat → **delete** the file from `99_无关文件/high_confidence/`. This is irreversible and intended (privacy floor: silence ⇒ delete). The `99_无关文件/` copy is the only copy (these were never anchored or bucketed), so deleting it is the whole point.
    - **回收 (reclassify — "X 其实有用")** — user claims a specific isolated file matters → move it out of `99_无关文件/` into its correct typed bucket, run the *normal* late-arriving path (OCR → 脱敏 MD → canonical rename → co-locate MD → add to INDEX/timeline/case_text/structured JSONs; raster image also appended to `redaction_manifest.json` for 段B).
    - **Hold (borderline `relevance_uncertain`, the one exception)** — for borderline files the user has **not** explicitly resolved → **do nothing, keep in `99_无关文件/uncertain/`, never auto-delete.** Silence deletes a high-confidence non-medical file; silence does **not** delete a borderline file — deleting something that might be a real medical record is the worse error. Only an explicit "删"/"无关" deletes it; "留"/"这是病历" reclassifies it. Either way mark the `relevance_uncertain` review_flag `user_confirmed: true` with the chosen `resolution`.

    Record every isolated/deleted/reclassified/held action in `update_log.json.relevance` (the `auto_deleted` array is the irreversible-action ledger). The authoritative deletion red-line is the 段E entry in [`../../references/safety-guardrails.md`](../../references/safety-guardrails.md); this step is its operational门控.

15. **Conversation-incremental capture (段C, on demand)** — this is not part of the initial organize run; it is the entry point for later turns. When the patient/caregiver is *chatting* about their condition (not handing over files) and a `<patient_dir>` with an existing `update_log.json` exists, run `run_mode: "conversation_incremental"` (see the dedicated section below) to capture archivable facts surfaced in dialogue → diff card → user-confirmed write, with `[[src:conversation:<ISO8601>]]` provenance. Unconfirmed talk never touches formal fields.

16. **Upload reconciliation (扩段C, on re-upload)** — when the user re-uploads one or more files onto an **already-existing** `patient_dir` (has `update_log.json`), run `run_mode: "upload_reconciliation"` (see [`references/upload-reconciliation.md`](references/upload-reconciliation.md)). Each new file first passes the 段E relevance gate (high-confidence non-medical → 段E isolate/delete logic, not reconciliation); medical/borderline files then get an LLM relation判断 — **new / supersede / conflict** (semantic comparison against the existing archive, NOT a hardcoded same-name-same-date Python check) → a diff card asking **替换? 并存? 忽略?**. This **reuses段C's single "先确认" gate — it does not start a second gate**: 替换 archives the old doc to `_superseded_<ts>/` (not deleted) and remaps its anchors; 并存 keeps both and adds a second timeline row; 忽略 / 未确认 writes no formal field. conflict is never silently overwritten — both facts are shown side by side for the user to adjudicate, and 关键字段 (分期/分子/治疗线) conflicts require explicit confirmation. Provenance logs an `update_log.json` entry with `run_mode: "upload_reconciliation"`. **This flow introduces no new auto-deletion** — the only auto-delete is段E's high-confidence non-medical path; borderline medical files are never auto-deleted without explicit confirmation.

## Why fan-out + reduce instead of single-pass

The original design was a single subagent processing every input file sequentially. A 73-image archive took ~33 minutes. Splitting into Phase 1 (parallel per-slice OCR) + Phase 2 (cross-slice synthesis + audit) gives three benefits:

1. **Speed**: 3 parallel Phase-1 workers + 1 Phase-2 finishes in roughly the time of the SLOWEST slice + the synthesis pass — ~3× faster on multi-hospitalization archives in practice.
2. **Anti-anchoring is stronger**: each Phase 1 worker only sees its slice (one hospitalization), so the narrative window the model could anchor on is shorter. Cross-slice contradictions are caught explicitly in Phase 2's §4.6 audit (which has the deterministic cross-doc check) rather than being smoothed over by a single agent's running narrative.
3. **Better failure isolation**: if one slice's worker hits context exhaustion, only that slice retries (continuation loop). Slices that finished cleanly are not re-dispatched.

Single-pass is preserved for small inputs (< 30 files OR no subdirs) — the parallelism overhead isn't worth it.

## Incremental mode

When `<patient_dir>` already has `update_log.json`, the caller may pass `run_mode: "incremental"` to Phase 2. In that mode:

- Phase 1 only re-OCRs files that are new under `10_原始文件/` or whose source mtime is newer than their sidecar. Other slices are skipped.
- Phase 2 reclassifies only the new sidecars; existing bucket assignments are preserved.
- Top-level artifacts (`case_text.md`, `timeline.md`, `patient_summary.json`, `timeline.json`, `molecular.json`, `treatment_lines.json`, `labs.json`, `comorbidities.json`, `missing_items.json`) are rewritten only when their content would actually change.
- `update_log.json` gets a new entry with `run_mode: "incremental"`, `added_files`, `removed_files`, `affected_summaries`, `triggered_by`, `reason`.
- `profile.json.alias` is sticky — never overwritten by an incremental run.

Use full mode (`run_mode: "full"`, default) for the very first organize, or whenever the patient indicates major changes ("我换了治疗方案", "重新做了一次基因检测") where rewriting the whole narrative is cleaner than merging.

**Re-uploading files onto an existing archive** is a distinct entry: pass `run_mode: "upload_reconciliation"` instead of plain `incremental`. That mode runs the 段E relevance gate on each new file, then an LLM new/supersede/conflict relation判断 → a diff card (替换? 并存? 忽略?) gated by the **same "先确认" door段C uses** — unconfirmed re-uploads never write formal fields, and 替换 archives the superseded doc to `_superseded_<ts>/` rather than deleting it. Full logic: [`references/upload-reconciliation.md`](references/upload-reconciliation.md). Plain `incremental` (above) is for newly-added files that don't supersede or conflict with an existing doc.

## Conversation-incremental mode (段C)

When the patient or caregiver is *chatting* about their condition (not handing over files) and a `<patient_dir>` with an existing `update_log.json` already exists, the caller may run `run_mode: "conversation_incremental"` to capture archivable facts that surface in the dialogue. Dispatch a `general-purpose` subagent with the full content of [`references/conversation-incremental-prompt.md`](references/conversation-incremental-prompt.md), appending `## Call parameters`: `patient_dir`, `conversation_turn` (verbatim user message + context), `turn_timestamp` (ISO-8601), `actor_role`.

The flow: an LLM detects candidate archivable facts (新诊断/分期 / 新检验值 / 治疗变更 / 症状 / 体能-ECOG) → maps each to a `profile.json` field or a `timeline.md` row → presents a **diff card** (before → after, with the user's own words as 依据) → the user confirms / corrects / defers → only confirmed candidates are written. Provenance uses the conversation anchor `[[src:conversation:<ISO8601>]]` (never a file anchor). Confirmed facts land in `09_患者补充/conversation_notes/` with a `patient_curated` tag and update the formal field/row; `update_log.json` gets a `run_mode: "conversation_incremental"` entry. **Unconfirmed talk never touches formal fields** — this gate prevents a mis-spoken value from poisoning downstream reports. This mode does NOT re-OCR or re-run synthesis; for new *files* use full or incremental mode. Major changes ("我整套方案都换了") route to a full re-organize, not turn-by-turn merge.

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
- `10_原始文件/` is the audit trail — a byte-identical mirror of every source file **until** 段B's redaction job runs. Per the platform "redact-then-delete" carve-out (`safety-guardrails.md`), once a file's `redaction_status.json` entry is `qa_passed: true` the job replaces the mirror with the **redacted** version and deletes the pre-redaction original (bucket copy + mirror original); the audit chain is then itself desensitized. QA failure → original kept, marked `failed`, nothing deleted.

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

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) — Phase 1 worker prompt: per-slice OCR, parallel-safe, sidecars-only
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — Phase 2 worker prompt: cross-slice synthesis + 7-check review_flags audit + review_summary + 6 structured JSONs + missing_items.json + update_log.json + alias
- [conversation-incremental-prompt.md](references/conversation-incremental-prompt.md) — 段C conversation-incremental worker prompt: detect archivable facts in chat → diff card → user-confirmed write to profile field / timeline row with `[[src:conversation:<ISO8601>]]` provenance + `patient_curated` tag; unconfirmed talk never written
- [relevance-gate.md](references/relevance-gate.md) — 段E medical-relevance triage: LLM judgment (not keyword list) → medical / non-medical-high-confidence / borderline; `99_无关文件/` quarantine semantics; disposition notice + privacy floor; 删 (high-confidence auto-delete on no-confirm) / 回收 (reclassify) / hold (borderline never auto-deleted); `relevance_uncertain` 8th review_flag + `update_log.json.relevance` ledger
- [upload-reconciliation.md](references/upload-reconciliation.md) — 扩段C re-upload reconciliation: LLM new/supersede/conflict relation判断 (not hardcoded same-name-date) → diff card 替换?/并存?/忽略? reusing段C's "先确认" gate; 替换 archives old doc to `_superseded_<ts>/` (not deleted) + anchor remap; conflict never silently overwritten; introduces no new auto-deletion; `run_mode: "upload_reconciliation"` update_log
- [case-summary-html-prompt.md](references/case-summary-html-prompt.md) — 段D worker prompt: read desensitized JSONs → fill the gold-standard template 1:1 → `病情简要总结.html`; subagent generates only the 病情概要 narrative, every other section is field-mapping; coarse-grained identity, `null` → 待补充
- [templates/case-summary.template.html](references/templates/case-summary.template.html) — 段D gold-standard HTML/CSS template (1:1 reproduction target, not "style-similar")
- [redaction-job.md](references/redaction-job.md) — 段B contract: `redaction_manifest.json` → `run_redaction_job.py` → QA gate → bucket+mirror replace → delete original (only on `qa_passed`) → `redaction_status.json`; platform async trigger convention + `~/.venvs/mtb-ocr` venv requirement
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [references/schemas/](references/schemas/) — Draft 2020-12 JSON Schemas for the 6 structured outputs + `missing_items.json`
- [references/schemas/anchor-contract.md](references/schemas/anchor-contract.md) — `[[src:...]]` anchor token syntax + coverage + path validity contract (bucket-relative file anchors + `conversation:<ISO8601>` anchors; `ocr/` prefix deprecated)
- [references/schemas/redaction_manifest.schema.json](references/schemas/redaction_manifest.schema.json) — `redaction_manifest_v1` schema (段B work queue produced by Phase 2)
- [references/schemas/redaction_status.schema.json](references/schemas/redaction_status.schema.json) — `redaction_status_v1` schema (段B per-file progress written by the job)
- [references/checklists/](references/checklists/) — cancer-type minimum-data checklists driving `missing_items.json`
- [scripts/validate_structured_outputs.py](scripts/validate_structured_outputs.py) — schema + anchor validator for the 6 structured outputs
- [scripts/redact_ocr.py](scripts/redact_ocr.py) — 段B PaddleOCR pixel-redaction engine (vendored from `cancer-buddy-organize-local-skill`): `redact_image_ocr()` boxes only PII regions
- [scripts/run_redaction_job.py](scripts/run_redaction_job.py) — 段B batch processor: manifest → redact → QA gate → bucket+mirror replace → delete-on-pass → `redaction_status.json` (idempotent, retryable)
- [../../references/preflight.md](../../references/preflight.md) — shared entry-gate (role + disclosure + readiness grade + Step 2.5 review_flags red gate + schema validity)
- [../../references/i18n.md](../../references/i18n.md) — shared locale contract: detect → persist `profile.json.locale` → reuse; scaffold-localized / clinical-entity-verbatim policy; locale→bucket-name map (`NN_` prefix stable)
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
