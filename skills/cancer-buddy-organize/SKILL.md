---
name: cancer-buddy-organize
description: "Organize patient medical records from PDF/images/docx into a canonical patients/<patient_code>/ directory with profile.json, timeline.md, readiness.json, OCR sidecars, and 01_当前状态…11_诊断证明 buckets. Use when the user hands over a folder of medical records, or says 病历整理, 我有一堆报告, 帮我整理报告. Dispatches a fresh general-purpose subagent with the organizer prompt to do OCR, classification, and schema extraction in isolated context."
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

1. **Resolve input** — confirm the user-supplied path with them. For archives, the subagent will unpack to `/tmp/`. For single PDF/DOCX, it treats as a 1-file source.

2. **Dispatch the organizer subagent.**

   Heavy LLM work (vision-based OCR on potentially dozens of images, multi-file classification, schema extraction) runs in an isolated subagent context. Invoke via the `Agent` tool:

   - `subagent_type: general-purpose`
   - `description: "Organize patient records"`
   - `prompt`: the full content of [`references/organizer-prompt.md`](references/organizer-prompt.md), with the following substitutions appended as a `## Call parameters` section at the end:
     - `input_path: <user-supplied path, absolute>`
     - `patient_code: <optional — auto-generate `PT-<hex>` from hash(basename + mtime) if missing>`
     - `patient_data_root: <first defined among $CANCER_BUDDY_PATIENTS_DIR, $VMTB_PATIENT_DATA_ROOT, $HOME/CancerDAO/patients>`

   The subagent uses Claude's native vision for image OCR (no external OCR tools required — zero-config). It returns pure JSON: `{role, patient_dir, files_classified, ocr_sidecars_generated, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green, review_summary_path}`.

   If `review_flags_total` OR `review_summary_path` field is missing from the returned JSON, the organizer is non-compliant — re-dispatch with explicit reminder to run Step 4.6 + 4.7.

3. **Verify outputs** — parse the returned JSON; confirm `profile.json` exists and required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are populated. If any are missing or null, surface to the user as a blocker before routing to any other sub-skill.

4. **Grade readiness** — from the returned JSON take `readiness_grade` + `readiness_score`. If grade is F or D, present the information-gap checklist 🔴🟡🟢 (derived from `blocking_gaps`) to the patient.

5. **Display review_summary.md (MANDATORY, ALWAYS)** — read the file at `review_summary_path` and display its full content to the user. This is the **first** thing the user sees after organize — before profile card, before review_flags. It is a 1-page spot-check of extracted key fields with verbatim source citations.

   Why this is the first display: many real OCR errors produce **internally consistent wrong values** (e.g. all 7 documents in one hospitalization OCR'd to the same wrong drug name). The 5-check `review_flags` audit cannot detect those — but a human reading `review_summary.md` can spot a wrong character in 30 seconds.

   After displaying, prompt the user: "请核对上面 5 个检查要点。任何字段需要修正,直接告诉我哪个字段 + 正确值,我会更新 profile.json 并重新生成清单。"

6. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after `review_summary.md`. This is a hard gate, not optional polish:
   - **If any 🔴 red flag present**: tell the user "进入下游 skill 之前请先逐条确认或 override 这些 🔴 项 — 它们会直接影响 trial-match / mtb-lite / vmtb 的推荐"
   - **If only 🟡/🟢 flags**: present them as "建议核对", do not block downstream routing
   - **If `review_flags_total: 0`**: still tell the user "所有提取字段已通过 5 项可疑值检查 (格式/跨文档矛盾/临床逻辑/原始证据/数值趋势), 无待确认项 — 但仍请核对上面的 review_summary.md 速查清单"
   - The user's resolution per flag (`accept_suggestion` / `keep_original` / `custom_value` / `defer`) is logged back into `readiness.json.review_flags[i].user_confirmed = true` plus a `resolution` sub-object.

7. **Output profile card** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "🔍 待人工确认" section pulls from `readiness.json.review_flags[]`.

   **Downstream gate**: do NOT route the user to any downstream sub-skill (mtb-lite / trial-match / vmtb / nutrition / education) while any 🔴 red review_flag is unconfirmed. A wrong drug name at this stage poisons every downstream report.

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

- [organizer-prompt.md](references/organizer-prompt.md) — full subagent prompt (dispatched verbatim)
- [profile-card.md](references/profile-card.md) — Patient Profile Card display template
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md) — schema contract shared with vmtb-skill
- [../../references/terminology.md](../../references/terminology.md) — 中英 + 通俗解释 format
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
