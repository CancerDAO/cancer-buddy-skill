# Local Vault and Export Contract

## Archive boundary

The canonical archive is produced by `cancer-buddy-organize`. Vault is a consumer; it must not define competing profile/timeline schemas or copy `raw/` into a share surface. Use [`PATIENT_DIR_CONTRACT.md`](../../cancer-buddy-organize/references/PATIENT_DIR_CONTRACT.md) and [`patient-profile-schema.md`](../../cancer-buddy/references/patient-profile-schema.md).

## sharing-plan.json

This file records an intended share and user choices. It does not enforce remote access.

```json
{
  "schema_version": "1",
  "plan_id": "share-opaque-id",
  "recipient_label": "user-provided label",
  "purpose": "second_opinion",
  "scope": ["profile", "timeline", "selected_reports"],
  "cross_border": false,
  "expires_at": null,
  "consent_recorded_at": "ISO-8601",
  "status": "draft"
}
```

Do not store recipient credentials, passwords, legal identity numbers, access tokens, or email-session data here.

## export-ledger.jsonl

One JSON object per export this tool actually created:

```json
{"event_id":"opaque","ts":"ISO-8601","plan_id":"share-opaque-id","action":"export_created","destination":"user-visible local path","manifest_sha256":"hex","notes":null}
```

Allowed actions are `export_created`, `local_copy_deleted`, and `plan_revoked`. `plan_revoked` means “do not create future exports under this plan”; it does not recall copies already sent. Never record a fabricated `recipient_viewed` event.

## Export preview

Before writing an export, show:

- recipient and purpose;
- included files/fields;
- excluded files (`raw/`, identity maps, historical snapshots, temporary/intermediate files);
- remaining re-identification risks;
- destination and whether it is cross-border;
- what revocation can and cannot do.

Require explicit confirmation after the preview. Use the organizer safe-export validator and script; do not hand-copy files.

## De-identification

Remove direct identifiers and unnecessary quasi-identifiers. Treat rare disease + variant + dates + institution/location as potentially identifying. Preserve source clinical terms needed for the stated purpose, but coarsen dates/locations and omit free text where it does not materially help the recipient. A preview should call out every retained high-risk element.

## Legal cautions (not legal advice)

Health, genomic, mental-health, and information about children under 14 are sensitive personal information under China's PIPL. Depending on actor, purpose, scale, recipient, and jurisdiction, processing can require necessity, strict safeguards, separate consent, impact assessment, guardian consent, data-export mechanisms, or other duties. Human genetic resources rules may separately apply to research/cooperation and provision to foreign organizations.

Do not reduce this to “genomic data must stay in China,” a universal three-year log rule, or a universal 72-hour breach notice. Current rules and thresholds change. For an actual organizational, research, or cross-border workflow, verify the current official rules and obtain qualified privacy/legal review.

Primary official starting points (reviewed 2026-07-11):

- PIPL: <https://www.gov.cn/xinwen/2021-08/20/content_5632486.htm>
- CAC cross-border data policy hub: <https://www.cac.gov.cn/wxzw/sjzl/sjcjaqpg/A09370801index_1.htm>
- 2026 CAC cross-border Q&A: <https://www.cac.gov.cn/2026-01/30/c_1771505108953002.htm>
- Human Genetic Resources Regulation: <https://www.nhc.gov.cn/bgt/gwywj2/201906/7f057bf005b44d87894e6764e73d557a.shtml>
