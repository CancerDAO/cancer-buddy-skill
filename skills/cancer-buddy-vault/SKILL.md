---
name: cancer-buddy-vault
description: "为患者建立 N=1 数据保险箱——结构化目录、分级分享（🔒 私密 → 🔑 授权 → 📊 匿名供 AI → 🌐 公开）、访问日志。不是云存储，而是患者自己拥有、可迁移、可选择性分享的本地文件结构。Use when 患者想长期整理病历、把数据分级分享给医生/研究者、或控制谁能看自己的健康档案。Triggers on: 数据保险箱, N=1, 我的健康档案, 数据分享, 隐私, 谁能看, 匿名, data vault."
license: MIT
metadata:
  author: CancerDAO
  version: "0.2.0"
  tags: 数据保险箱 隐私 数据分享 匿名化 访问日志 N=1
---

# cancer-buddy-vault

The patient's own public-style cancer data vault — every report, every visit note, every image, organized, searchable, owned by the patient.

## When to use

- Patient asks about organizing their records long-term.
- After 3+ months of treatment when records start piling up.
- Patient says: 数据保险箱 / N=1 / 我的健康档案 / 数据分享.

## Inputs

- Existing `patients/<pid>/` tree produced by `cancer-buddy-organize`.
- Optional: external health app exports (Apple Health, Google Fit, CGM data, etc.).

## Outputs

Augments `patients/<pid>/`:
- `sharing-settings.json` — per-directory sharing level
- `access.log` — who accessed what, when
- `vault-manifest.md` — human-readable table of contents
- `exports/` — encrypted bundles ready to share

## Sharing levels

- 🔒 **Private**: patient + immediate family only
- 🔑 **Authorized**: specific clinicians by email/contact (signed URL with expiry)
- 📊 **Anonymized-for-AI**: stripped of PII, hashed patient_id, available for research use
- 🌐 **Public**: de-identified case report, patient consent required

Patient can change level per-file or per-directory anytime. Every change is logged.

## Workflow

See [references/data-vault.md](references/data-vault.md) for the schema and protocol. Main steps:

1. Walk `patients/<pid>/`, classify each artifact by sensitivity.
2. Initialize `sharing-settings.json` — everything starts 🔒 Private unless patient overrides.
3. Generate `vault-manifest.md` — patient-readable TOC.
4. For each anonymization request, run de-identification (strip name, birthday, MRN, institution, replace dates with intervals-since-diagnosis).
5. Log all access / share / export events to `access.log`.

## Safety and privacy

- PII stripping is conservative — err on the side of removing.
- Every share action triggers a confirmation prompt: "你确认要把 [scope] 分享给 [recipient] 级别 [level]?"
- Access log is append-only; do not let any other sub-skill modify it.
- Default export format: encrypted zip (password shared out-of-band).

## Role behavior

- **Role = patient**: owner view. Can set any sharing level, export, delete.
  - *Disclosure*: disclosure_state=suppressed + patient → render redacted view (diagnosis fields masked).
- **Role = caregiver**: authorized view. Read+write OK; sharing-level changes require `patients/<patient_code>/role.json.history` confirming patient previously set role=caregiver. Export allowed.
- **Role = family**: 📊 anonymized view only. Name / birthday / MRN stripped, diagnosis-intervals relative to diagnosis date, no free-text notes. Cannot change sharing settings.

## References

- [data-vault.md](references/data-vault.md) — schema, anonymization protocol, sharing flow
- [../../references/patient-profile-schema.md](../../references/patient-profile-schema.md)
- [../../references/safety-guardrails.md](../../references/safety-guardrails.md)
