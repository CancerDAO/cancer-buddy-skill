---
name: cancer-buddy-organize
description: "Turn a patient's raw medical records (PDF/images/docx) into a canonical, structured patients/<patient_code>/ directory every other sub-skill can consume. Use when the user hands over a folder of medical records, or says 病历整理 / 我有一堆报告 / 帮我整理报告."
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: medical-records ocr structuring oncology patient-data readiness
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
- `readiness.json` — `use_case_gates`（用途门控）+ `tier1/tier2_gaps`（含 action_category）+ `review_flags[]`（可疑值审计）+ `synthesis_quality`（合成质量自报）
- `review_flags.md` — auto-generated human-readable rendering of `readiness.json.review_flags[]` (only written when array non-empty)
- `review_summary.md` — **always written**: 1-page checklist of extracted key fields with verbatim source citations, for user spot-check (catches consistent-but-wrong OCR that review_flags can't)
- `case_text.md` (consolidated narrative — raw OCR text organized by section)
- `case_summary_brief.md` — **always written**: standardized 1-2 page clinical summary (Modules 1-2-6-7 from `../../references/case-summary-template.md`)
- `case_summary_detailed.md` — **always written**: standardized 8-10 page full clinical summary (all 7 modules)
- `01_当前状态/`…`11_诊断证明/` (raw file buckets)
- `ocr/` (OCR sidecars with SOURCE/CONFIDENCE headers)

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

5. **询问输出格式（Phase 2 dispatch 前）** — 在所有 Phase 1 worker 完成后、派遣 Phase 2 之前，向用户发送一条消息：

   > "病历整理完成，即将生成报告。请问您希望以哪种格式输出报告？"
   > 1. **Markdown**（.md，可直接阅读）
   > 2. **Word 文档**（.docx，可进一步编辑）
   > 3. **PDF**（.pdf，适合打印或发送）

   等待用户回复，将选择（`"markdown"` / `"docx"` / `"pdf"`）作为 `output_format` 参数传入 Phase 2 的 call parameters。若用户未回复超时，默认使用 `"markdown"`。

5b. **Dispatch Phase 2 Synthesis Worker** — after every Phase 1 worker reports `continuation_needed: false`, dispatch a SINGLE `general-purpose` subagent for synthesis:

   - `subagent_type: general-purpose`
   - `description: "Organize synthesis"`
   - `prompt`: the full content of [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md), with these `## Call parameters` appended:
     - `patient_dir: <absolute patient_dir>` (current bootstrap path; Phase 2 may rename it in Step 1.7)
     - `phase1_summary: <JSON list of all Phase 1 worker results>`

   Phase 2 reads all sidecars (cross-slice), classifies into the 11 buckets **using original basenames** (Step 1), then judges per-file `{date, doc_type, 机构, page}` plus patient-level `{cancer_label, first_dx_date}` from the OCR text itself and writes `.rename_plan.json` (Step 1.5 — semantic judgment, no hardcoded vocab), atomically renames physical files + sidecars + back-fills `source_manifest.tsv` (Step 1.6 — mechanical bash, atomic with collision suffix), and renames the patient_dir itself to `<cancer>_<YYYY-MM>_<hash4>` when OCR yields a recognizable cancer type (Step 1.7). Only after canonical naming does Phase 2 build INDEX.md / timeline.md / case_text.md / profile.json / readiness.json, run the §4.6 review_flags audit, and write review_flags.md (if non-empty) + review_summary.md (always).

   Phase 2 returns: `{role, patient_dir, patient_dir_original, patient_dir_renamed, files_classified, files_renamed_canonical, files_renamed_skipped, rename_plan_path, ocr_sidecars_read, coverage_complete, missing_sidecars, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path}`. The `patient_dir` field is the post-rename path; if the caller still holds the bootstrap `PT-<hex>` path, use `patient_dir` (not the original) for any downstream operations.

6. **Coverage gap retry** — if Phase 2 returns `coverage_complete: false`, dispatch a retry-mini-Phase1 worker with just the missing files as input, then re-run Phase 2. Loop until `coverage_complete: true`. Most runs converge in 0 or 1 retries.

7. **Verify outputs** — parse Phase 2's returned JSON; confirm `profile.json` exists and required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are populated. If any are missing or null, surface to the user as a blocker before routing to any other sub-skill.

8. **呈现用途门控 + 行动指引** — 从 readiness.json 读取 `use_case_gates` 和 `tier1_gaps[]` / `tier2_gaps[]`。

   **原则：无论覆盖度高低，都生成并交付报告。缺失字段转化为行动指引，不降级，不拒绝。绝不向用户展示任何数字分数或字母等级。**

   向用户展示用途门控状态（白话，不展示字段名）：

   | use_case_gates 值 | 向用户展示 |
   |---|---|
   | basic_summary: not_ready | "当前资料过少，暂时无法生成有意义的总结，建议先补充以下文件：[tier1_gaps]" |
   | clinic_visit: not_ready | "当前资料尚不足以支持门诊就医参考，核心缺口：[gate_blocking_reasons.clinic_visit]" |
   | clinic_visit: ready_with_gaps | "可用于门诊就医参考，以下补充项有助于提升精准度：[tier2_gaps priority:high]" |
   | clinic_visit: ready | "当前资料已满足门诊就医参考要求。" |
   | second_opinion: not_ready | "如需外院第二意见，还需补充：[gate_blocking_reasons.second_opinion]" |
   | second_opinion: ready_with_gaps | "基本满足外院第二意见要求，以下项目补充后更完整：[tier2_gaps]" |
   | second_opinion: ready | "资料已满足外院第二意见要求。" |
   | trial_match: not_ready | "如需临床试验匹配，还需：[gate_blocking_reasons.trial_match]" |
   | trial_match: ready | "资料满足临床试验匹配要求。" |

   展示 tier1_gaps 时，附上每条的 `action_detail`（具体操作建议）；展示 tier2_gaps priority:high 时同理。`action_category` 不需要逐字展示，已内嵌在 action_detail 里。

9. **Phase 3 报告质量评审（必经步骤）** — Phase 2 完成报告生成后必然触发，不再是条件性的。

   **触发时机**：Phase 2 返回后，报告已写入磁盘（report_data.json + case_summary_brief.md + case_summary_detailed.md）。

   **例外，跳过 Phase 3**：
   - `use_case_gates.basic_summary == "not_ready"`（资料过少，评审无意义）
   - 本次运行已经是定向重合成后的 retry（不再二次评审，避免无限循环）

   **执行步骤**：
   1. 读取 `patient_dir/report_data.json` 和 `patient_dir/readiness.json`
   2. 执行 `ls patient_dir/ocr/` 构建 sidecar_index（文件名 + 首行 SOURCE/CONFIDENCE 摘要）
   3. 以 [references/organizer-prompt-phase3-evaluation.md](references/organizer-prompt-phase3-evaluation.md) 为 prompt，dispatch Phase 3 Worker（`general-purpose` subagent），传入：
      - `patient_dir`
      - `report_data_json`（文件全文）
      - `readiness_json`（文件全文）
      - `case_summary_brief_path`（绝对路径）
      - `sidecar_index`（JSON 列表）
   4. Phase 3 Worker 完成后，读取 `patient_dir/qa_evaluation.json`
   5. 根据 `delivery_decision` 执行（**deliver_report 永远为 true，始终交付已生成报告**）：

   | delivery_decision 字段 | 为 true 时的操作 |
   |---|---|
   | `generate_patient_checklist` | 展示 `patient_dir/待补充材料清单.md` 给用户，告知哪些文件需要补充 |
   | `trigger_re_ocr` | 告知用户 `re_ocr_targets` 中列出的文件需要重新识别，提示手动重跑 Phase 1 → Phase 2 |
   | `trigger_re_synthesis` | Dispatch 定向重合成 Worker（`general-purpose`），prompt 为 Phase 2 的 prompt 末尾追加 `re_synthesis_instructions`；重合成后直接更新 report_data.json，重新生成 case_summary 文件，**不再触发第二次 Phase 3** |

   **max retry = 1**：定向重合成最多执行一次。若重合成后仍有问题，将 qa_evaluation.json 中的 issues 转化为 review_flags 追加到 readiness.json，随报告一并交付，由用户决定是否进一步补充材料。

10. **Display review_summary.md (MANDATORY, ALWAYS)** — read the file at `review_summary_path` and display its full content to the user. This is the **first** thing the user sees after organize — before profile card, before review_flags. It is a 1-page spot-check of extracted key fields with verbatim source citations.

    Why this is the first display: many real OCR errors produce **internally consistent wrong values** (e.g. all 7 documents in one hospitalization OCR'd to the same wrong drug name). The 5-check `review_flags` audit cannot detect those — but a human reading `review_summary.md` can spot a wrong character in 30 seconds.

    After displaying, prompt the user: "请核对上面 5 个检查要点。任何字段需要修正,直接告诉我哪个字段 + 正确值,我会更新 profile.json 并重新生成清单。"

11. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after `review_summary.md`. This is a hard gate, not optional polish:
    - **待确认项（severity=red）存在时**：告知用户 "进入下游 skill 之前请先逐条确认或 override 这些待确认项 — 它们会直接影响后续分析与推荐（若装有 pro-skill: trial-match / mtb-lite / vmtb）"。若 flag 由 Phase 3 产生，附注 "（已经过独立核查）"。
    - **仅有建议/提示项**：作为 "建议核对" 展示，不阻断下游路由
    - **review_flags_total = 0**：仍告知用户 "所有提取字段已通过 5 项可疑值检查（格式/跨文档矛盾/临床逻辑/原始证据/数值趋势），无待确认项 — 但仍请核对上面的 review_summary.md 速查清单"
    - 用户对每个 flag 的处置（`accept_suggestion` / `keep_original` / `custom_value` / `defer`）记录回 `readiness.json.review_flags[i].user_confirmed = true` 及 `resolution` 子对象

12. **Output profile card** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "待人工确认" section pulls from `readiness.json.review_flags[]`.

    **Downstream gate**: do NOT route the user to any downstream sub-skill (education / find-care / vault, or any 若装有 pro-skill analysis route) while any critical review_flag is unconfirmed. A wrong drug name at this stage poisons every downstream report.

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

After successful organize, route the patient to the most relevant next companion sub-skill based on their initial question:

- Newly diagnosed, wants to understand their condition → `cancer-buddy-education`
- Wants help finding the right hospital / specialist → `cancer-buddy-find-care`
- Wants to keep their organized records as a personal data vault → `cancer-buddy-vault`

If the user has the private **pro-skill** bundle installed, deeper analysis routes become available — gate any mention of them behind "若装有 pro-skill":

- 若装有 pro-skill, newly diagnosed wanting maximal diagnostics → `cancer-buddy-explore`
- 若装有 pro-skill, has a gene report and wants treatment guidance → `cancer-buddy-mtb-lite`
- 若装有 pro-skill, looking for clinical trials → `cancer-buddy-trial-match`

## Role behavior

Authoritative matrix in `../../references/roles.md`. For this skill:

- **Role = patient**: First-person. "帮我整理我的病历" → produce profile.json / timeline.md / readiness.json. Profile's `data_sources[]` names patient as source.
  - *Disclosure*: disclosure_state=suppressed on patient entry → warn that organize will likely break suppression; proceed only with confirmation.
- **Role = caregiver**: Second-person. "帮你家人整理报告". Tone warmer, includes "整理这些很累吧，一步一步来"-style acknowledgment. On first-ever organize in this patient_code, organize creates the profile but does NOT write `profile.json.caregivers[]` itself — that array is owned by `cancer-buddy-caregiver` (a documented exception in `../../references/patient-profile-schema.md`, which writes the caregiver's relation + name + contact preference). Offer to hand the user off to `cancer-buddy-caregiver` to record who they are.
- **Role = family**: Refuse. Emit: `病历整理要靠主照护者操作（Ta 手里有原件）。要不要我帮你生成一份 2 页要点让 Ta 参考？` Do not run organize.

## References

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) — Phase 1 worker prompt: per-slice OCR, parallel-safe, sidecars-only
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — Phase 2 worker prompt: cross-slice synthesis + Step 1.5–1.7 canonical naming (semantic judgment + atomic bash mv) + review_flags audit + review_summary
- [organizer-prompt-phase3-evaluation.md](references/organizer-prompt-phase3-evaluation.md) — Phase 3 worker prompt: 报告质量评审（Track A 完整度 + Track B 可用度），必经步骤，生成 qa_evaluation.json + 患者行动清单
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [../../references/preflight.md](../../references/preflight.md) — shared entry-gate (role + disclosure + readiness grade + Step 2.5 review_flags red gate + schema validity)
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
