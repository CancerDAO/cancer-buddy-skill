# 药物-食物相互作用 — workflow

## 证据契约（EVIDENCE CONTRACT — 最高优先级）

每一条向患者展示的 🔴 红色（必须避免）或 🟡 黄色（需谨慎）药物-食物/补剂相互作用，**必须**满足以下之一,否则不得展示：

1. 通过 **web-access skill** 实时联网核实于权威源（FDA/NMPA 药品说明书、DrugBank、Lexicomp、UpToDate、PubMed 等），并随条目附上来源链接；或
2. 携带可追溯的内联引用（说明书条目、指南、文献 PMID）。

**禁止仅凭训练记忆，就把任何一条相互作用作为 🔴 红色「必须避免」直接发给患者。** 记忆可以用来*提示需要去核实哪些组合*，但不能作为最终展示给患者的证据。

若当前离线、无法联网核实，或核实后仍不确定：**不得标红**，一律降级呈现为 🟡「需药师确认（未在线核实）」，并提示患者向主诊医生/药剂师确认。

充分确立的经典相互作用（TKI ↔ 西柚 / 华法林 ↔ 维 K 食物 / 奥沙利铂 ↔ 冷食 / 5-FU + capecitabine ↔ 柚子 / methotrexate ↔ 酒精 等）依然可作为应当核查的候选清单，但向患者展示时**每条都必须带上来源引用**——「众所周知」不能替代引用。

> 本文件**不**内置硬编码相互作用表。原因仍然成立：硬编码表永远落后于 FDA/NMPA 审批、患者实际 `current_therapy` 可能不在表内、且「查表无命中→结论无相互作用」会制造虚假信心。但这绝不意味着可以用训练记忆代替核实——每条展示给患者的相互作用都受上面的证据契约约束。

What this skill DOES require, structurally:

## Workflow

1. From `profile.json.current_therapy` + `treatment_history` + any patient-volunteered supplements, **enumerate every active drug, every recent (< 1 month) drug, and every supplement**.
2. For each drug, use your training knowledge **only to assemble a candidate list** of clinically meaningful food/supplement combinations worth checking. Cover at minimum: CYP3A4 substrates (TKIs, anti-emetics, statins) + CYP-modulating foods (西柚 / 杨桃 / 圣约翰草 / 大蒜补剂 / 银杏 / 人参), warfarin + vitamin K balance, MAOI + tyramine, methotrexate + alcohol / NSAIDs / PPI, oxaliplatin + cold exposure (acute neuropathy), nadir-period food safety (raw / unpasteurized / 生腌).
3. **For each candidate, before showing it to the patient, satisfy the 证据契约 above**: load the **web-access skill** and verify against a live authoritative source, or attach a traceable inline citation. Only then classify: 🔴 must-avoid (clinically dangerous, **verified**) / 🟡 caution (timing or quantity matters) / 🟢 informational. A candidate you could not verify online (offline / unreachable / still uncertain) is **never 🔴** — present it as 🟡「需药师确认（未在线核实）」.
4. Write all findings to `patients/<patient_code>/reports/nutrition/interactions-flagged.md`, **each entry carrying its source link / citation** (or the「未在线核实」marker).
5. Any verified 🔴 interaction MUST be highlighted at the top of the patient menu in red, with its citation.

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
