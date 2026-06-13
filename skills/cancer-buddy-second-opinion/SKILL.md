---
name: cancer-buddy-second-opinion
description: "Generate a reviewer-consumable English case packet for cross-border or domestic second opinions. Produces concise English case summary (1-2 page PDF-ready markdown), medical records index, doctor-to-doctor cover letter, DHL/FedEx medical-record shipping guide, and 'how to present the second opinion back to your primary oncologist' script. Covers major Chinese tertiary + international centers (MSK, MD Anderson, 日本癌研, 新加坡国立). Role-aware: patient or caregiver only; other-family routing refused. Triggers on: 第二意见, 去别的医院看看, 跨境会诊, MSK, MD Anderson, 日本癌研, 梅奥, 香港养和."
---

# cancer-buddy-second-opinion

Second opinions change treatment plans in ~20-30% of oncology cases — but only if the reviewer has a clean, consumable packet. This skill generates that packet.

## When to use

- User says: 第二意见 / 去其他医院看看 / 跨境会诊 / MSK / MD Anderson / 日本癌研 / 香港养和.
- Complex case where the primary oncologist has suggested second-opinion.
- Before expanded-access or cross-border treatment decisions.

## Locale

Read [../../references/i18n.md](../../references/i18n.md). This sub-skill has **two locale axes** — keep them distinct:

- **`profile.json.locale`** (the patient's scaffold language) governs every output the **patient/caregiver** reads: the `presentation-script.md`, the packaging explanation, role-refusal copy, and the caregiver phone-consult checklist.
  1. Read `patients/<patient_code>/profile.json` → `locale`. If present, use it — do not re-detect (second-opinion runs after organize, so a `locale` is almost always already persisted).
  2. If absent (no profile, or `locale` is null), detect from the language the user is conversing in, then write it back to `profile.json.locale` (BCP-47, e.g. `en` / `zh` / `fr`).
  3. Honor an explicit user language override ("用中文" / "answer me in English") → update `profile.json.locale` and follow it going forward.
- **`reviewer_locale`** (the **target center's** language) governs the **reviewer-facing** artifacts (`case-summary.md`, `cover-letter.md`, `records-index.md`). This is NOT `profile.json.locale` — the packet must be in the language the reviewing oncologist reads, regardless of the patient's scaffold language. Derive it from the target chosen in Workflow §1 / `top-centers.md`:
  - MSK / MD Anderson / Mayo / Dana-Farber / Johns Hopkins / NCIS (新加坡) / 养和 (English intake) → `en`.
  - 日本国立癌研究中心 / 癌研有明 → `ja` (route through the Japanese concierge for translation per `cross-border-shipping.md`; generate the `en` packet first as the source-of-truth, flag `ja` translation as a downstream concierge step).
  - Domestic 三甲 (去另一家三甲) → the reviewer's language (typically `zh`); a short `en` summary may still ride along.
  - Any other center → the center's intake language.

In all artifacts, on both axes: **keep every clinical entity verbatim** (drug names, genes/variants, TNM/stage, numbers + units, biomarker labels) regardless of locale — never translate, transliterate, or normalize them. Mistranslating a clinical entity is a P0 medical-safety bug. Only the scaffold (section headers, field labels, narrative connectives, disclaimers, date formats) is localized; for the reviewer artifacts the scaffold follows `reviewer_locale`, for the patient artifacts it follows `profile.json.locale`.

## Preflight

Run [../../references/preflight.md](../../references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. Second-opinion packets are sent to international reviewers (MSK / MD Anderson / 癌研有明 / 养和); packaging an unconfirmed 🔴 RED review_flag on diagnosis / summary.stage / treatment lines (`treatment_lines.json`) / molecular drivers (`molecular.json`) will mislead the reviewer and waste a one-shot consultation slot. Block until every relevant RED flag is human-resolved.

In addition:
- Role: patient or caregiver only. Family → refuse + redirect.
- `profile.json` must be populated with at least diagnosis, stage, treatment history, latest imaging.

## Workflow

### 1. Determine target

- **Domestic second opinion** (去另一家三甲): reviewer usually reads Chinese → `reviewer_locale = zh`. Packet in the reviewer's language + optional English summary.
- **Cross-border** (MSK / MDA / 日本癌研 / 新加坡国立 / 梅奥): per the Locale block, derive `reviewer_locale` (`en` for US/UK/SG/HK English intake; `ja` for the Japanese centers). The reviewer-facing packet is rendered in `reviewer_locale`.

### 1.5 Verify-before-send (live center check — medical-agent red line)

`top-centers.md` and `cross-border-shipping.md` are **routing hints, not a current source of intake/contact truth**. International-patient offices rename, relocate, change emails/portals, and pause or close their second-opinion programs with no notice. A stale contact / intake / program-status line packaged as if current sends a patient's irreplaceable pathology blocks to a dead address and burns a scarce one-shot cross-border consultation slot.

So before the target center's contact, intake process, shipping address, or program status is quoted into **any** artifact (the cover letter, the shipping instructions, the records-index destination, or anything the patient acts on):

- For each center to be used, do a **live web check via the `web-access` skill** against that center's `source_url` (from its `top-centers.md` `freshness` line). Confirm, against the center's own official international-patient page, the current: international-office contact (email/phone/portal), second-opinion intake process + required materials, eligibility, and **whether the second-opinion / online-consultation program is still open**. Do **not** silently fall back to the static values in `top-centers.md` / `cross-border-shipping.md` — that is the medical-agent no-silent-snapshot red line (`references/safety-guardrails.md`).
- **Live result wins** over the catalogue. If the live check disagrees, use the live values and note the catalogue was stale.
- If the live source is unreachable or the detail cannot be confirmed, **do not invent or reuse a stale line** — mark that item in the packet as `需用户自行向中心确认 / to be confirmed by the patient directly with the center` (rendered per the artifact's locale), and point the patient at the center's official `source_url` to confirm.
- This is **routing / logistics fidelity, not evidence synthesis.** The check only refreshes where-to-send and how-to-send facts (addresses, intake, program status); it never generates, edits, or second-guesses the patient's clinical content — clinical entities stay verbatim from the records exactly as everywhere else.
- The verify step is LLM-driven over the live page (read the center's page and decide what the current intake/contact is) — do not hardcode a keyword/string list of "what changed"; hand the page to the subagent/LLM and let it reconcile against the catalogue.

### 2. Generate case summary

Per [references/case-summary-template.md](references/case-summary-template.md). Render the scaffold (section headers, field labels, formatting-rule prose) in `reviewer_locale`; the template carries a `reviewer_locale → string table` — never hardcode a single language. Clinical entities stay verbatim. 1-2 pages. Structure:
- Demographics + ECOG
- Diagnosis + stage + date
- Histology + molecular (MUST include)
- Treatment history (regimen / start / end / best response)
- Latest imaging (date + finding)
- Latest labs (date + values)
- Current status + specific question for reviewer

### 3. Build medical records index

Scan `patients/<patient_code>/` for key files:
- Pathology report(s)
- NGS / molecular report(s)
- Imaging CDs/PDFs
- Treatment summaries
- Recent labs

Produce a single index.md listing each file with: date, hospital, type, confidence tag, filename. Column headers / labels in `reviewer_locale`; filenames, dates, hospital names and clinical entities verbatim.

### 4. Generate cover letter

Per [references/cover-letter-template.md](references/cover-letter-template.md). Doctor-to-doctor tone, 250-400 words, written in `reviewer_locale` (the template carries a `reviewer_locale → string table` for the fixed scaffold lines), specific question stated at top. Clinical entities verbatim. Any center contact / addressee / intake reference must come from the §1.5 live check — not the static catalogue; unconfirmed items go in as `需用户自行向中心确认 / to be confirmed with the center`.

### 5. Cross-border shipping guide

If target is overseas, per [references/cross-border-shipping.md](references/cross-border-shipping.md): DHL/FedEx medical-records shipping process, customs declarations, expected transit time, how to request digital alternative if the reviewer accepts. The **specific shipping address / intake email / portal** for the target center must be the §1.5 live-verified value, not the static one in `cross-border-shipping.md`; if unconfirmed, instruct the patient to confirm the current address directly with the center rather than printing a possibly-dead one. This is a **patient-facing operational guide** → render it in `profile.json.locale` (the customs-declaration strings the courier needs stay in the destination's required language — usually English — verbatim).

### 6. How to present opinion back to primary oncologist

After receiving the second opinion, patient/caregiver needs to discuss with primary oncologist. This is **patient-facing** → render in `profile.json.locale`; clinical entities verbatim. Generate a 1-page discussion script:
- Summary of what the second opinion said
- Points of agreement with primary oncologist
- Points of divergence + specific questions
- Decision framework

## Role behavior

- **Role = patient**: 1st-person packet. Case summary uses "I", cover letter implies patient or caregiver authorship.
  - *Disclosure*: disclosure_state=suppressed + patient → refuse (operator-only task).
- **Role = caregiver**: 2nd-person packet helpers. Cover letter can be signed as caregiver on behalf. Include "你帮 X 做翻译电话时的 checklist" for if a phone consultation follows.
- **Role = family**: refuse. Emit the refusal in `profile.json.locale` (zh reference wording): `第二意见的操作需要主照护者或患者本人来推进（需要签字、身份证明、支付）。`

## Output

Written under `patients/<patient_code>/reports/second-opinion/<target-center>/`. Reviewer-facing files follow `reviewer_locale`; patient-facing files follow `profile.json.locale`; clinical entities verbatim in all:
- `case-summary.md` — 1-2 page case summary *(reviewer_locale)*
- `records-index.md` — list of medical records in the packet *(reviewer_locale)*
- `cover-letter.md` — doctor-to-doctor letter *(reviewer_locale)*
- `shipping-instructions.md` — if cross-border *(profile.json.locale)*
- `presentation-script.md` — post-opinion discussion guide *(profile.json.locale)*

## Safety

- Never promise a specific outcome from a second opinion ("MSK 会给你新方案").
- Never encourage sending records to paid internet services that are not established medical institutions.
- Respect patient privacy — the packet should include only what's relevant to the clinical question.
- Cross-border shipping involves real customs/medical-privacy considerations. Do not handwave.
- **Never translate a clinical entity** (drug name, gene, variant, TNM/stage, number, unit, biomarker label) when localizing the packet — keep the source form verbatim. A reviewer acting on a mistranslated drug/dose/stage is a P0 medical-safety failure. Localize only the scaffold.
- **Never package a static center contact / intake / shipping address / program-status line as if current.** `top-centers.md` and `cross-border-shipping.md` are routing hints; run the §1.5 live check (`web-access`) before quoting any of it. No silent snapshot fallback — unconfirmed items are marked `需用户自行向中心确认`. This is routing/logistics fidelity (where + how to send), never evidence synthesis.

## References

- [case-summary-template.md](references/case-summary-template.md)
- [cover-letter-template.md](references/cover-letter-template.md)
- [cross-border-shipping.md](references/cross-border-shipping.md)
- [top-centers.md](references/top-centers.md) — key Chinese + international centers + their second-opinion intake processes
