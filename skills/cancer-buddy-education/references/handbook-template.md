# Patient Education Handbook Template

## Phase 8: Patient Education

Generate patient-friendly educational materials from clinical data.

> **Locale**: read `profile.json.locale` (detect + persist per `../../../references/i18n.md` if absent). Render every section title, label, and narrative below in that locale; keep clinical entities (drug names, genes/variants, TNM/stage, numbers + units, biomarker labels) verbatim. The section names listed here are the `zh` rendering — output the same meaning in the patient's locale.

1. Take vMTB report or Patient Profile as input
2. Select relevant chapters based on patient's condition and comorbidities
3. Generate Markdown handbook (all scaffold/narrative prose in `locale`, clinical entities verbatim) with:
   - Quick reference card (emergency info, key contacts)
   - My Health Summary (plain language)
   - Drug details with side effect management
   - Daily living guide
   - Follow-up schedule
   - Cost/insurance navigation
   - FAQ
4. Include Mermaid diagrams for disease mechanisms and treatment decision trees — node labels and explanations in `locale`, clinical entities verbatim
5. Output filename: localize the `患者教育手册` descriptor per `locale`, keep `{patient_code}` and `{date}` (ISO `YYYY-MM-DD`) verbatim. zh → `{patient_code}_{date}_患者教育手册.md`; en → `{patient_code}_{date}_patient_education_handbook.md`; other locales → the locale's rendering of "patient education handbook" as a lowercase ASCII-safe slug.
