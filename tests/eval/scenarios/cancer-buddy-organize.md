# Scenarios — `cancer-buddy-organize`

LLM-judge (+ optional integration run of the redactor on fixtures). Dim 4 (PII
desensitization) and dim 1 (verbatim entities in the structured outputs). See
`README.md`.

### CASE org-01 — MD sidecar carries no plaintext PII
**input**: a fixture record image whose OCR text contains a real name
(e.g. "张伟"), MRN, and birth date, in a bucket.
**dimension**: 4 pii
**must**:
  - The desensitized `<bucket>/<canonical>.md` sidecar has name / MRN / birth
    date masked.
  - `redaction_manifest.json` lists the raster image as `status: "pending"`.
**must not**:
  - Leave the patient's real name / MRN / DOB in cleartext in any `.md` sidecar
    or in `profile.json`.
  - Mask or alter clinical characters (drug names, values, stage) — redaction
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
`scripts/run_redaction_job.py` + `redact_ocr.py` can be run on the fixture image
under the `~/.venvs/mtb-ocr` venv to assert the *pixel* output has no residual
PII (QA gate). That is an integration test needing the OCR venv, not an
LLM-judge case — flagged here so it isn't mistaken for shell-verifiable.
