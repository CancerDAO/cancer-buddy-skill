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

   The subagent uses Claude's native vision for image OCR (no external OCR tools required — zero-config). It returns pure JSON: `{role, patient_dir, files_classified, ocr_sidecars_generated, readiness_grade, readiness_score, blocking_gaps, warnings, review_flags_total, review_flags_red, review_flags_yellow, review_flags_green}`.

   If `review_flags_total` field is missing from the returned JSON, the organizer is non-compliant — re-dispatch with explicit reminder to run Step 4.6.

3. **Verify outputs** — parse the returned JSON; confirm `profile.json` exists and required fields (`patient_code`, `primary_cancer`, `histology`, `stage`) are populated. If any are missing or null, surface to the user as a blocker before routing to any other sub-skill.

4. **Grade readiness** — from the returned JSON take `readiness_grade` + `readiness_score`. If grade is F or D, present the information-gap checklist 🔴🟡🟢 (derived from `blocking_gaps`) to the patient.

5. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, read `review_flags.md` and display its content to the user immediately after the Patient Profile Card. This is a hard gate, not optional polish:
   - **If any 🔴 red flag present**: tell the user "进入下游 skill 之前请先逐条确认或 override 这些 🔴 项 — 它们会直接影响 trial-match / mtb-lite / vmtb 的推荐"
   - **If only 🟡/🟢 flags**: present them as "建议核对", do not block downstream routing
   - **If `review_flags_total: 0`**: still tell the user "所有提取字段已通过 5 项可疑值检查 (格式/跨文档矛盾/临床逻辑/原始证据/数值趋势), 无待确认项"
   - The user's resolution per flag (`accept_suggestion` / `keep_original` / `custom_value` / `defer`) is logged back into `readiness.json.review_flags[i].user_confirmed = true` plus a `resolution` sub-object.

6. **Output summary** — display the Patient Profile Card ([references/profile-card.md](references/profile-card.md)) to the patient using the `terminology.md` format rules (中英 + 通俗解释). The card's "🔍 待人工确认" section pulls from `readiness.json.review_flags[]`.

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

After successful organize, route the patient to the most relevant next sub-skill based on their initial question. For clinical-judgment skills (MTB / trial matching / pathway exploration) — which live outside the public cancer-buddy bundle — **scan the available-skills list first** and tell the user explicitly which engine the environment has, so they don't get a silent "skill not found" downstream.

- Newly diagnosed, wants to understand → `cancer-buddy-explore` (private, in cancer-buddy-pro-skill)
- Has gene report, wants treatment guidance → see "MTB hand-off" below
- Looking for trials → `cancer-buddy-trial-match` (private, in cancer-buddy-pro-skill)
- Wants to find a hospital/center that does MTB or runs trials → `cancer-buddy-find-care` (public, ships in this repo)

### MTB hand-off — environment-aware

When the user has gene/molecular reports and asks about treatment guidance, scan the current session's available-skills list and route as follows. The full vMTB project ships under either of two registered skill names — `cancerdao-vmtb` (current) or `vmtb-skill` (legacy/alias) — accept either. **Do not silently degrade — always tell the user which engine ran (or that none did) so the patient knows what they're getting.**

| Env state | Action | What to tell the user |
|---|---|---|
| `cancerdao-vmtb` **or** `vmtb-skill` present (public, full clinician-grade vMTB — multi-agent committee + verifier + auditable HTML report) | Hand off to whichever name resolved. | "环境里检测到完整版 vMTB skill (`cancerdao-vmtb` / `vmtb-skill`) — 多专家委员会 + 5 维质控 + 可审计 HTML 报告。我把整理好的 profile 接力过去。" |
| `cancer-buddy-mtb-lite` present (private, ships inside cancer-buddy-pro-skill — lighter clinical flow) | Hand off to `cancer-buddy-mtb-lite`. | "环境里有内部版 mtb-lite。这是简化的临床流程（比完整版 vmtb-skill 轻），适合快速过一遍。" |
| Both present | Default to the full vMTB (more thorough); mention `mtb-lite` as the lighter alternative and let the user choose. | "你环境里两个都装了。我默认走完整版 vMTB；如果只是想快速过一遍可以切到 `mtb-lite`。" |
| Neither present | Do **not** generate any MTB-style recommendation inside cancer-buddy itself — public cancer-buddy is companion-scope, MTB is explicitly out of scope (see `../cancer-buddy/SKILL.md`). Route the user to `cancer-buddy-find-care` so they can find a hospital MTB clinic, and tell them what they'd need to install if they want to run it locally. | "公开版抗癌搭子不做 MTB 临床判断。要在本地跑 MTB，需要安装 `cancerdao-vmtb` / `vmtb-skill`（公开）或 `cancer-buddy-pro-skill`（内部）。要找做 MTB 的医院，我可以接力到 `cancer-buddy-find-care`。" |

The disclosure is mandatory in all four branches. Never run a "best-effort" MTB recommendation from cancer-buddy itself — that's exactly the boundary the public skill is drawn around.

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
