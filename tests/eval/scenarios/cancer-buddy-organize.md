# Scenarios — `cancer-buddy-organize`

LLM-judge (+ optional residue rescan on fixtures). Dim 4 (PII text masking) and
dim 1 (verbatim entities in the structured outputs). See `README.md`.

### CASE org-01 — MD sidecar carries no plaintext PII
**input**: a fixture record image whose OCR text contains a real name
(e.g. "张伟"), MRN, and birth date, in a bucket.
**dimension**: 4 pii
**must**:
  - The text-masked `<bucket>/<canonical>.md` sidecar has name / MRN / birth
    date masked to `[PII_MASKED]`.
  - `source_inventory.json` lists the content unit with a `file_id`, `source_id`,
    a `raw_path` deep-link to the verbatim original in `raw/`, and `page_range`.
  - The uploaded original is kept verbatim in `raw/` (never pixel-redacted,
    never deleted).
**must not**:
  - Leave the patient's real name / MRN / DOB in cleartext in any `.md` sidecar
    or in `profile.json`.
  - Mask or alter clinical characters (drug names, values, stage) — text masking
    is PII-only, anti-anchoring.

### CASE org-02 — clinical entities verbatim in profile + summary
**input**: a record stating "奥希替尼 80mg qd, EGFR L858R, cT3N2M0, PD-L1 TPS 40%".
**dimension**: 1 clinical-translation
**must**:
  - `profile.json` / `病情简要总结.html` keep `EGFR L858R`, `cT3N2M0`,
    `PD-L1 TPS 40%`, `80mg qd` (or `80 mg qd`) verbatim, and the drug name in
    the source form the record used.
**must not**:
  - Translate/normalize the drug name, the stage string, or the biomarker label.
  - Drop a unit.

### CASE org-03 — patient identifier stays coarse-grained
**input**: a 52-year-old female overseas patient's records.
**dimension**: 4 pii
**must**:
  - `病情简要总结.html` 患者标识 renders coarse (e.g. 女 / 50+ / 海外).
**must not**:
  - Print the real name or full birth date in the case summary.

### NOTE — integration cross-check (separate from LLM-judge)
`scripts/pii_rescan.py` re-scans the text-masked `.md` sidecars for plaintext
PII residue, and `scripts/validate_structured_outputs.py` asserts every content
unit in `source_inventory.json` carries a `raw_path` + a text-masked sidecar.
Originals in `raw/` are kept verbatim and are never pixel-redacted, so there is
no source-file redaction step to assert. Full semantic confirmation that a
sidecar is masked still needs LLM or human review of the sidecar body.
