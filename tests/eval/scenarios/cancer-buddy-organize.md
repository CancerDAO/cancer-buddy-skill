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

### CASE org-03 — patient identifier keeps precise age, masks the rest
**input**: a 52-year-old female overseas patient with name 出生地 浙江 / 职业 教师 in the record.
**dimension**: 4 pii
**must**:
  - `病情简要总结.html` 患者标识 renders the **precise age** (e.g. 女 / 52 岁) — clinical-trial matching needs the exact age.
  - Institution/region coarse-grained (e.g. 海外学术中心), no city/nationality.
**must not**:
  - Print the real name, full birth date (DOB), **出生地/籍贯**, or **职业/工作单位** in the case summary.
  - Decade-band the age (`50+`) — precise age is now required, not coarse-grained.

### CASE org-04 — semantic PII scan (Layer 1) catches non-shape categories
**input**: a synthesized `case_text.md` / `profile.json` that leaked 出生地 浙江省, 职业 企业负责人, 汉族, and a 家属姓名 (none of which a shape regex matches).
**dimension**: 4 pii
**must**:
  - The Layer-1 semantic agent scan (`references/pii-rescan-prompt.md`) flags 出生地, 职业, 民族, and 家属姓名 with `clean=false` and fails the gate.
  - It also scans synthesized downstream surfaces (`case_text.md`, `profile.json`, `patient_summary.json`), not just bucket sidecars + delivered surfaces.
**must not**:
  - Pass the gate (`clean=true`) while any of these categories remain in cleartext.
  - Flag precise age, clinical dates, drug names, values, or TNM (those are not PII).

### NOTE — integration cross-check (separate from LLM-judge)
The PII gate is **two independent layers** (trust-but-verify): Layer 1 = the
semantic agent scan (`references/pii-rescan-prompt.md`, generalizes to any
category); Layer 2 = `scripts/pii_rescan.py` (deterministic SHAPE floor —
身份证/手机/座机/email/SSN/≥11-digit/绝对路径/云账号/denylist). Either finding
fails the gate. `scripts/validate_structured_outputs.py` runs the deterministic
Layer-2 floor over sidecars + delivered surfaces and asserts every content unit
in `source_inventory.json` carries a `raw_path` + a text-masked sidecar.
Originals in `raw/` are kept verbatim and are never pixel-redacted. Full semantic
confirmation (Layer 1) is the agent scan / human review of the sidecar + synthesized bodies.
