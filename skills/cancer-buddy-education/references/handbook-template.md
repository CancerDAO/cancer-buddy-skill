# Patient Education Handbook Template

## Phase 8: Patient Education

Generate patient-friendly educational materials from clinical data.

> **Locale**: resolve locale per `../../cancer-buddy/references/i18n.md` (host `locale` first, otherwise `profile.json.locale`, otherwise detection fallback + persist). Render every section title, label, and narrative below in that locale; keep clinical entities (drug names, genes/variants, TNM/stage, numbers + units, biomarker labels) verbatim. The section names listed here are the `zh` rendering — output the same meaning in the patient's locale.

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

> **疗效红线（P0，见 `../../cancer-buddy/references/safety-guardrails.md` → Efficacy/response is a clinician's judgment）**：手册**绝不自行判疗效**。"效果怎么样 / 治疗反应"这类行**只能**复述来源/医生逐字写出的响应类别（CR/PR/SD/PD，带引用），来源没写就写"档案里没有医生的疗效评价"。**禁止**把影像描述("病灶缩小")转成"部分缓解/PR"，**禁止**加 RECIST 定义式注解（"病灶缩小超过 30%"是定义,不是这个患者的实测数据）。肿瘤标志物可如实呈现升降趋势,但不得据此说"治疗有效/好转"。
5. Output filename: localize the `患者教育手册` descriptor per `locale`, keep `{patient_code}` and `{date}` (ISO `YYYY-MM-DD`) verbatim. zh → `{patient_code}_{date}_患者教育手册.md`; en → `{patient_code}_{date}_patient_education_handbook.md`; other locales → the locale's rendering of "patient education handbook" as a lowercase ASCII-safe slug.
