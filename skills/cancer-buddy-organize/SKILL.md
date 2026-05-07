---
name: cancer-buddy-organize
description: "Organize patient medical records from PDF/images/docx into a canonical patients/<patient_code>/ directory with profile.json, timeline.md, readiness.json, OCR sidecars, and 01_当前状态…11_诊断证明 buckets. Use when the user hands over a folder of medical records, or says 病历整理, 我有一堆报告, 帮我整理报告. For multi-hospitalization archives ≥ 30 files: fans out parallel Phase-1 OCR Workers (one per source subdirectory) and reduces with a Phase-2 Synthesis Worker that does cross-slice review_flags audit. For small/flat inputs: single-pass."
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
- `profile.json` (conforms to `../../references/patient-profile-schema.md`)
- `timeline.md` (human-readable treatment timeline)
- `readiness.json` — coverage grade + `review_flags[]` (MTB readiness + suspicious-value audit)
- `review_flags.md` — auto-generated human-readable rendering of `readiness.json.review_flags[]` (only written when array non-empty)
- `review_summary.md` — **always written**: 1-page checklist of extracted key fields with verbatim source citations, for user spot-check (catches consistent-but-wrong OCR that review_flags can't)
- `case_text.md` (consolidated narrative)
- `01_当前状态/`…`11_诊断证明/` (raw file buckets)
- `ocr/` (OCR sidecars with SOURCE/CONFIDENCE headers)

## Workflow

1. **Resolve input** — confirm the user-supplied path with them. For archives, unpack to `/tmp/cb-unpack-$$/` first (zip / rar / 7z / tar.gz / single pdf-or-docx). After unpack, the **resolved input directory** (`$src`) is what Step 2 plans against.

2. **Plan slicing (single-pass vs fan-out)** — `glob $src` for immediate subdirectories.

   - **Fan-out mode (parallel Phase 1)**: if `$src` contains ≥ 2 subdirectories AND total file count ≥ 30, treat each subdirectory as a slice. Each slice = one Phase 1 OCR Worker. Typical case: a patient archive with one folder per hospitalization (e.g. `20240702_第一次住院/`, `20240808_第二次住院/`, `20240905_第三次住院/`). 73 images across 3 subfolders → 3 parallel workers.
   - **Single-pass mode**: if `$src` is flat OR has < 30 files, treat the whole thing as a single slice. One Phase 1 worker. Avoids parallelism overhead for small inputs.

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

## Why fan-out + reduce instead of single-pass

The original design was a single subagent processing every input file sequentially. A 73-image archive took ~33 minutes. Splitting into Phase 1 (parallel per-slice OCR) + Phase 2 (cross-slice synthesis + audit) gives three benefits:

1. **Speed**: 3 parallel Phase-1 workers + 1 Phase-2 finishes in roughly the time of the SLOWEST slice + the synthesis pass — ~3× faster on multi-hospitalization archives in practice.
2. **Anti-anchoring is stronger**: each Phase 1 worker only sees its slice (one hospitalization), so the narrative window the model could anchor on is shorter. Cross-slice contradictions are caught explicitly in Phase 2's §4.6 audit (which has the deterministic cross-doc check) rather than being smoothed over by a single agent's running narrative.
3. **Better failure isolation**: if one slice's worker hits context exhaustion, only that slice retries (continuation loop). Slices that finished cleanly are not re-dispatched.

Single-pass is preserved for small inputs (< 30 files OR no subdirs) — the parallelism overhead isn't worth it.

## patient_code collision

If the generated `patient_code` (e.g. `PT-17CE02BC33`) already exists under the patients root, the subagent appends `_2`, `_3`, etc., and announces the assigned code in the summary.

## Configurable root

The `patients/` root resolves in order: `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`. Override by exporting one of those. Shared with vmtb-skill.

## Safety

Organize does not make medical recommendations. Still:

- Never fabricate fields — when a value is truly unreadable in the source, the subagent writes `null` (JSON) or `[OCR_UNCERTAIN]` (text) and surfaces it as a gap.
- Downstream sub-skills apply the full `safety-guardrails.md` rule set when they read what organize produced; wrong data here poisons every downstream report.
- `10_原始文件/` is the audit trail — always a byte-identical mirror of every source file.

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
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — Phase 2 worker prompt: cross-slice synthesis + review_flags audit + review_summary
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [../../references/preflight.md](../../references/preflight.md) — shared entry-gate (role + disclosure + readiness grade + Step 2.5 review_flags red gate + schema validity)
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
