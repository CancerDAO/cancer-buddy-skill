# Gap follow-up — proactively invite the patient to supplement the most valuable missing data

> Behavior spec for a **first-class cancer-buddy behavior**: after organize, and again inside Q&A, warmly invite the patient to supplement the **few most clinically valuable** missing records — priority-ranked, benefit-tied, actionable, ask-once. This is a companion behavior, not a clinical judgment: it never recommends treatment, never decides staging, never interprets a result. It only says *"this one record, if you can get it, would help you the most, and here's how to get it."*

Discipline in one line: **选得准，不是全都催** — surface the 1–3 highest-impact gaps, never dump the checklist, never nag.

---

## 1. Purpose

organize already computes what's missing (`missing_items.json`, priority-ranked) and how ready the archive is (`readiness.json`, `blocking_gaps` + per-domain `gaps`). But a raw gap list is cold and long — a patient reading "你缺了 12 项" shuts down. This behavior turns that list into a **warm, human invitation**: pick the very few gaps that would most change what a doctor / MTB / the patient's own understanding can do, and ask for each in a way that ties it to a benefit the patient cares about and tells them concretely how to get it.

The patient is always free to ignore it. Supplementing records is optional; the ask is an offer, never a demand.

---

## 2. Input

- **`missing_items.json`** (patient_dir root) — the cancer-type checklist diff. Each `missing[]` item carries `priority` (`P0`/`P1`/`P2`), `category` (`pathology`/`imaging`/`lab`/`molecular`/`history`/`consent`), `item` (plain-language description), and `reason` (why it's needed). Priorities are driven by `references/checklists/<cancer_type>.yaml`.
- **`readiness.json`** — `blocking_gaps[]` (`{domain, reason}`, the honesty gate's hard gaps) and per-domain `domains.<name>.gaps[]`. A domain that is both a `blocking_gap` AND has a P0/P1 checklist item behind it is the strongest candidate to surface.
- **`gap_asks.json`** (patient_dir root, this behavior's own ledger — see §7) — what has already been surfaced, so we never re-ask.
- **`profile.json.locale`** — all patient-facing text is rendered in this locale (clinical entities stay verbatim, see §8).

---

## 3. Prioritization rule (what to surface — and what NOT to)

**Surface only P0/P1 high-clinical-value gaps. NEVER surface P2, and NEVER dump the full `missing[]` list.** A minor / incidental missing lab (routine 血常规 already partially covered, a P2 supplementary marker, a nice-to-have consent form) is **not** surfaced even if it's technically missing.

Rank the eligible gaps by **clinical impact — what would most change the analysis or the patient's care**, not by checklist order. The mental question is: *"if the patient added exactly one record, which one moves the needle most?"* In descending impact:

1. **A targetable-driver molecular test** (NGS / a key mutation panel / PD-L1 / MSI-MMR / HER2) — decides whether a whole class of targeted or immuno therapy is even on the table. Usually the single most decision-changing record.
2. **A recent imaging study for response assessment / staging** (胸腹盆 CT, 盆腔 MRI, PET-CT) — anchors 分期 and answers "is the treatment actually working".
3. **The diagnostic / post-op pathology report** — the ground floor of staging and recurrence-risk judgment.
4. A **staging-relevant** lab or tumor-marker baseline/trend that's genuinely absent (not a routine incidental lab).

Apply these filters before surfacing anything:

- **Priority filter**: item `priority ∈ {P0, P1}`. Drop all P2.
- **Impact filter**: the gap plausibly changes what a doctor / MTB / the patient can understand or do. A missing routine/incidental item that changes nothing → drop.
- **Ask-once filter**: the item is not already in `gap_asks.json` with `status` `pending` / `provided` / `declined` (see §7) → drop if already asked.
- **Count cap**: post-organize surface **at most the top 2–3**; Q&A surfaces **exactly one** (the single one most relevant to the question asked).

If nothing survives the filters (archive is already rich, or every high-value gap was already asked), **surface nothing** — silence is correct here, not a fabricated ask.

---

## 4. Phrasing template

Each ask is **one short warm sentence** built from three parts:

> **[gap, plainly] + [benefit the patient cares about] + [concretely how to get it] — 要不要补？**

Rules:

- **Warm + benefit-tied, NOT "你缺了 X"**. Lead with what it *does for them*, not with a deficiency. Never a scolding or checklist tone.
- **Actionable**: always name a concrete way to get it (影像科刻盘/导出、找主诊医生调取、病案室、问检测机构要电子报告).
- **Optional**: the ask ends open — "要不要传？" / "要不要补？" — the patient can say no or ignore it.
- **No treatment advice**: describe why the record *helps the analysis / the doctor / the patient's understanding*. NEVER imply which drug, regimen, or decision the record would lead to. ("基因检测决定有没有靶向药可用" = describing what the *test* determines, allowed; "你应该上靶向药" = treatment advice, forbidden.)
- **Clinical entities verbatim** (NGS / PD-L1 / MSI / drug & gene names, TNM) — never translated even in a non-`zh` locale (see §8).

### Worked examples (use these as the calibration standard)

- 影像 (imaging): "你还没上传影像报告——补上能让分期和'治疗到底有没有效'判断得更准。要不要传？（影像科一般能刻盘或导出报告）"
- 基因检测 (molecular / NGS): "档案里没看到基因检测(NGS)——它决定有没有靶向药可用，是最能改变方案的一份。可以找主诊医生调取或问检测机构要电子报告。"
- 病理 (pathology): "术后病理原件缺了一份——它是分期和后续判断的地基，能找主治或病案室调取。"

Each example = gap + why it helps the patient + how to get it, in one warm line. Match this register.

---

## 5. Trigger 1 — Post-organize warm closing

**Where**: `cancer-buddy-organize/SKILL.md`, immediately **after the Profile Card step (Step 11)**, as a warm closing to the organize run. Runs after the profile card so the patient has already seen their档案 overview.

**What**:

1. Load `missing_items.json` + `readiness.json`, apply §3 filters, rank by §3 impact.
2. Take the **top 2–3** surviving gaps. If none survive → surface nothing (skip this step silently).
3. Frame as a short, optional, warm closing (rendered in `profile.json.locale`) — e.g. zh:
   > "档案整理好了。还差这几样最关键的，补上能更帮到你——不急，方便的时候补就行："
   then the 2–3 asks from §4, each on its own line. Close with something like "现在这些都不影响我陪你往下走，随时补都可以。"
4. **Record each surfaced ask to `gap_asks.json`** (§7) with `status: "pending"`, `surfaced_at_trigger: "post_organize"`, `asked_at` = now (ISO-8601).

This is **optional** for the patient — it never blocks routing to a downstream sub-skill (unlike the 🔴 review_flag gate). It's an invitation, not a gate.

---

## 6. Trigger 2 — Q&A context-triggered inline ask

**Where**: `cancer-buddy/SKILL.md` 档案读取协议 (Archive Read Protocol) — when answering a patient question **whose answer is materially limited by a missing item**.

**What**: when the honest answer to the patient's question is weakened because a specific high-value record is absent, after answering as fully as the archive allows, add a **single warm one-line ask** inline (§4 phrasing). Ask-once via `gap_asks.json`.

- Surface **exactly one** ask — the one gap most relevant to *this* question. Never turn a Q&A answer into a checklist recital.
- Only fire when the gap is genuinely P0/P1 high-value AND materially limits the answer (per §3). If the archive already answers the question well, add nothing.
- Ask-once: if the mapped gap's `item_key` is already in `gap_asks.json` (any non-reset status), **do not re-ask** — answer with what's there and move on.
- Record the surfaced ask to `gap_asks.json` with `surfaced_at_trigger: "qa"`.

### Question → gap map

Use this to decide whether the asked question is one whose answer is limited by a missing item, and which gap to offer:

| 患者问的问题（意图） | 被哪个缺失项限制 → 可提的补料 |
|---|---|
| "治疗有没有效 / 换不换方案" | recent imaging (响应评估) 或 tumor-marker trend 缺失 |
| "有没有靶向 / 免疫可用" | NGS / PD-L1 / MSI (targetable-driver 检测) 缺失 |
| "我是几期 / 分期" | staging pathology 或 staging imaging 缺失 |
| "复发风险 / 会不会复发" | post-op pathology (术后病理) 缺失 |

The map is a routing aid, not an exhaustive list — the governing test is always §3 (P0/P1 + materially limits the answer). A question outside the map that is still limited by a high-value gap may surface one ask; a question inside the map whose gap is already covered (or already asked) surfaces nothing.

---

## 7. `gap_asks.json` — ask-once tracking ledger

A new patient-facing artifact at **`<patient_dir>/gap_asks.json`** (patient_dir root, next to `missing_items.json`). **Append-only**: each time a gap is surfaced (by either trigger), append one entry; never rewrite history. The behavior reads it before surfacing and **skips any item already present** unless the patient later provides it or a new run finds a genuinely new high-value gap.

```json
{
  "schema_version": "1",
  "patient_code": "PT-XXXX",
  "asks": [
    {
      "item_key": "molecular:NGS",
      "priority": "P0",
      "category": "molecular",
      "item": "基因检测(NGS)",
      "asked_at": "2026-07-09T21:00:00+08:00",
      "surfaced_at_trigger": "post_organize",
      "status": "pending"
    }
  ]
}
```

Field notes:

- **`item_key`** — a stable key for the gap so the same gap is recognized across runs regardless of prose wording. Compose it as `<category>:<short-slug>` (e.g. `molecular:NGS`, `imaging:response-CT`, `pathology:postop`). Derive the slug from the checklist `category` + the item's clinical noun, NOT from the full localized sentence (so a re-render in another locale still matches).
- **`priority`** — copied from the `missing_items.json` item (`P0`/`P1`).
- **`asked_at`** — ISO-8601 timestamp of when this ask was surfaced.
- **`surfaced_at_trigger`** — `"post_organize"` or `"qa"`.
- **`status`** — one of:
  - `"pending"` — surfaced, no patient action yet. **Do not re-ask.**
  - `"provided"` — the patient later supplied the record (a subsequent organize/incremental run finds the item now covered → flip to `provided`). A `provided` item is no longer a gap; if a NEW high-value gap appears it can be asked fresh.
  - `"declined"` — the patient explicitly said they don't want to / can't get it. **Do not re-ask.**

**Ask-once rule**: before surfacing any gap, load `gap_asks.json`; if the gap's `item_key` already has an entry with `status ∈ {pending, provided, declined}`, skip it. The only paths back to asking are (a) the patient provides it (status → `provided`, and it's no longer surfaced because it's covered) or (b) a **new** high-value gap (a different `item_key`) shows up in a later run.

If `gap_asks.json` does not exist yet (first organize), create it with an empty `asks[]` and append as you surface.

---

## 8. Tone rules (hard)

- **Warm** — an invitation from someone on the patient's side, never a clinical audit. Lead with the benefit, not the deficiency.
- **Benefit-tied** — every ask says what the record *does for the patient* (更准的分期 / 判断治疗有没有效 / 看有没有靶向药可用 / 分期与复发风险的地基).
- **Actionable** — every ask names a concrete way to obtain it (影像科刻盘或导出、找主诊医生调取、病案室、问检测机构要电子报告).
- **Ask-once, no nagging** — one pass, tracked in `gap_asks.json`; never re-surface an item already asked; never repeat within a session.
- **选得准，不是全都催** — top 2–3 post-organize, exactly one in Q&A; NEVER the full list, NEVER P2/low-value items.
- **Patient can decline** — the ask is always optional and open-ended; ignoring it is fine and never blocks anything.
- **No treatment advice** — cancer-buddy stays out of clinical decisions. Describe why a *record* helps the analysis/doctor/understanding; never imply which drug/regimen/decision it points to. (This mirrors the meta router's "我不做的事" boundary.)
- **Locale + verbatim clinical entities** — render the scaffold/prose in `profile.json.locale`; keep drug/gene/variant/TNM/biomarker names and numbers verbatim regardless of locale (mistranslation is a P0 safety bug — see `../../references/safety-guardrails.md`).
