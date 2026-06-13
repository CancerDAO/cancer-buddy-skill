# 药物-食物相互作用 — workflow

> **Trust your clinical pharmacology training data**, do NOT consult a hardcoded interaction table here.

> **Locale**: the `zh` patient-facing strings below (the 🟡 uncertainty line, the last-resort note) are the **source string table** — render the localized equivalent in `profile.json.locale` at output time per `../../../references/i18n.md` §5. Drug names, supplement names and the `[INTERACTION_UNCERTAIN: <drug>]` sidecar key stay verbatim across locales.

This file used to contain a hardcoded ~30-row drug-food interaction table. It was deleted because:

1. The model already knows the standard oncology drug-food interactions (TKI ↔ 西柚 / 华法林 ↔ 维 K 食物 / 奥沙利铂 ↔ 冷食 / 5-FU + capecitabine ↔ 柚子 / methotrexate ↔ 酒精 / etc.) from training data
2. A hardcoded table is always behind FDA/NMPA approvals — the patient's actual `summary.current_regimen` may not be in the table
3. A consistent-but-incomplete table creates false confidence: agent checks the table, finds no match, concludes "no interactions" — when in fact the table just didn't list this drug

What this skill DOES require, structurally:

## Workflow

1. From `profile.json.summary.current_regimen` + ordered lines of therapy in `treatment_lines.json` + any patient-volunteered supplements, **enumerate every active drug, every recent (< 1 month) drug, and every supplement**.
2. For each drug, use your training knowledge to identify **known clinically meaningful food/supplement interactions**. Cover at minimum: CYP3A4 substrates (TKIs, anti-emetics, statins) + CYP-modulating foods (西柚 / 杨桃 / 圣约翰草 / 大蒜补剂 / 银杏 / 人参), warfarin + vitamin K balance, MAOI + tyramine, methotrexate + alcohol / NSAIDs / PPI, oxaliplatin + cold exposure (acute neuropathy), nadir-period food safety (raw / unpasteurized / 生腌).
3. For each interaction surfaced, classify: 🔴 must-avoid (clinically dangerous) / 🟡 caution (timing or quantity matters) / 🟢 informational.
4. Write all findings to `patients/<patient_code>/reports/nutrition/interactions-flagged.md`.
5. Any 🔴 interaction MUST be highlighted at the top of the patient menu in red.

## Uncertainty escape hatch

When you encounter a drug whose interaction profile you genuinely don't know with confidence (rare drug / new approval / regional generic):
- Do NOT make up plausible-sounding interactions
- Write `[INTERACTION_UNCERTAIN: <drug>]` in the sidecar
- Add to `interactions-flagged.md` as a 🟡 yellow flag with text: "<drug> 的食物相互作用我不确定,建议向药剂师/主诊医生确认"

When you are certain there are NO meaningful interactions (e.g., supportive-care drugs like 维生素 D, 钙片, 益生菌):
- Note in sidecar: "no clinically meaningful food interactions per training data"
- Move on without forced 🟡 flag

## TCM / Chinese herbal — be more cautious

TCM herbal medications have more variable evidence than Western pharmacology, and "I don't know" is the correct answer more often. Use `[INTERACTION_UNCERTAIN]` liberally for: 圣约翰草 (this one is well-known: CYP3A4/P-gp inducer, lowers many drug levels), 大黄, 人参 (anti-platelet, BP), 灵芝, 黄芪, 冬虫夏草 / 百令胶囊, 复方草药汤药. List them all in the sidecar; flag the ones whose interaction with the patient's specific regimen you are not sure about.

## Project convention (workflow rules, not clinical facts)

- Output path: `patients/<patient_code>/reports/nutrition/interactions-flagged.md`
- Severity colors: 🔴 / 🟡 / 🟢 (override schema: see `../../../../references/preflight.md` §Step 2.5)
- Patient menu top-of-page: any 🔴 interaction must be the first thing the patient sees

## Last resort

When uncertain, tell the patient to ask their oncologist or pharmacist. Do NOT recommend Google.
