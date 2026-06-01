---
name: cancer-buddy-second-opinion
description: "为跨境或国内第二意见生成审阅者可直接使用的英文病例资料包。产出简洁英文病例摘要（1-2 页可转 PDF 的 markdown）、病历索引、医生对医生的转诊信、DHL/FedEx 病历寄送指南，以及「如何把第二意见带回主治医生处沟通」的脚本。覆盖国内三甲与国际中心（如 MSK、MD Anderson 等，更多见正文 top-centers）。按角色处理：仅限患者或照护者，其他家属路由会被拒绝。Use when 患者或照护者想去国内别家医院或跨境寻求第二意见、需要把病例打包成审阅者可用的英文资料包时。Triggers on: 第二意见, 去别的医院看看, 跨境会诊, MSK, MD Anderson, 日本癌研, 梅奥, 香港养和。"
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: oncology second-opinion cross-border referral patient-navigation
---

# cancer-buddy-second-opinion

Second opinions change treatment plans in ~20-30% of oncology cases — but only if the reviewer has a clean, consumable packet. This skill generates that packet.

## When to use

- User says: 第二意见 / 去其他医院看看 / 跨境会诊 / MSK / MD Anderson / 日本癌研 / 香港养和.
- Complex case where the primary oncologist has suggested second-opinion.
- Before expanded-access or cross-border treatment decisions.

## Preflight

Run [../../references/preflight.md](../../references/preflight.md) — role + disclosure + readiness grade + **review_flags red gate (Step 2.5)** + schema validity. Second-opinion packets are sent to international reviewers (MSK / MD Anderson / 癌研有明 / 养和); packaging an unconfirmed 🔴 RED review_flag on diagnosis / stage / treatment_history / molecular_drivers will mislead the reviewer and waste a one-shot consultation slot. Block until every relevant RED flag is human-resolved.

In addition:
- Role: patient or caregiver only. Family → refuse + redirect.
- `profile.json` must be populated with at least diagnosis, stage, treatment history, latest imaging.

## Workflow

### 1. Determine target

- **Domestic second opinion** (去另一家三甲): reviewer usually reads Chinese. Packet can be in Chinese + English summary.
- **Cross-border** (MSK / MDA / 日本癌研 / 新加坡国立 / 梅奥): English packet required.

### 2. Generate case summary

Per [references/case-summary-template.md](references/case-summary-template.md). 1-2 pages. Structure:
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

Produce a single index.md listing each file with: date, hospital, type, confidence tag, filename.

### 4. Generate cover letter

Per [references/cover-letter-template.md](references/cover-letter-template.md). Doctor-to-doctor tone, 250-400 words English, specific question stated at top.

### 5. Cross-border shipping guide

If target is overseas, per [references/cross-border-shipping.md](references/cross-border-shipping.md): DHL/FedEx medical-records shipping process, customs declarations, expected transit time, how to request digital alternative if the reviewer accepts.

### 6. How to present opinion back to primary oncologist

After receiving the second opinion, patient/caregiver needs to discuss with primary oncologist. Generate a 1-page discussion script:
- Summary of what the second opinion said
- Points of agreement with primary oncologist
- Points of divergence + specific questions
- Decision framework

## Role behavior

- **Role = patient**: 1st-person packet. Case summary uses "I", cover letter implies patient or caregiver authorship.
  - *Disclosure*: disclosure_state=suppressed + patient → refuse (operator-only task).
- **Role = caregiver**: 2nd-person packet helpers. Cover letter can be signed as caregiver on behalf. Include "你帮 X 做翻译电话时的 checklist" for if a phone consultation follows.
- **Role = family**: refuse. Emit: `第二意见的操作需要主照护者或患者本人来推进（需要签字、身份证明、支付）。`

## Output

Written under `patients/<patient_code>/reports/second-opinion/<target-center>/`:
- `case-summary.md` — 1-2 page English case summary
- `records-index.md` — list of medical records in the packet
- `cover-letter.md` — doctor-to-doctor letter
- `shipping-instructions.md` — if cross-border
- `presentation-script.md` — post-opinion discussion guide

## Safety

- Never promise a specific outcome from a second opinion ("MSK 会给你新方案").
- Never encourage sending records to paid internet services that are not established medical institutions.
- Respect patient privacy — the packet should include only what's relevant to the clinical question.
- Cross-border shipping involves real customs/medical-privacy considerations. Do not handwave.
- **Never fabricate center intake details.** International second-opinion programs, intake emails, portals, eligibility rules, fees and turnaround change frequently and are sometimes discontinued. Do NOT assert that a given center "has an online second-opinion program" / "accepts X" / "intake email is Y" from memory or from the seed data in [references/top-centers.md](references/top-centers.md) / [references/cross-border-shipping.md](references/cross-border-shipping.md). Confirm the intake program on the center's **official international-patient page** before stating it to the user. The center seed data in those references is `last_verified`-dated and **non-authoritative** — treat it as a starting point for lookup, never as the source of truth. When you cannot verify live, say so and point the user to the official international-patient office rather than inventing a contact.

## References

- [case-summary-template.md](references/case-summary-template.md)
- [cover-letter-template.md](references/cover-letter-template.md)
- [cross-border-shipping.md](references/cross-border-shipping.md)
- [top-centers.md](references/top-centers.md) — key Chinese + international centers + their second-opinion intake processes
