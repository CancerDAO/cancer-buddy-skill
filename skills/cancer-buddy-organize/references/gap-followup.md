# Gap follow-up — proactively invite the patient to supplement the most valuable missing data

> Behavior spec for a **first-class cancer-buddy behavior**: after organize, and again inside Q&A, warmly invite the patient to supplement the **few most clinically valuable** missing records — priority-ranked, benefit-tied, actionable, ask-once. This is a companion behavior, not a clinical judgment: it never recommends treatment, never decides staging, never interprets a result. It only says *"this one record, if you can get it, would help you the most, and here's how to get it."*

Discipline in one line: **选得准，不是全都催；挑对时机，不是整理完就推** — surface the 1–3 highest-impact gaps, at a moment where the ask is *relevant* (a visit is coming, a question was limited by the gap, we're routing somewhere the record matters), never dump the checklist, never nag, and never let "asked once at the worst moment" silence a gap forever.

> **改版要点（为什么重做）**：旧版把补料**堆在 organize 刚结束那一刻**（患者认知最过载），且 profile card 已先铺过一遍冷缺口清单（重复），加上 ask-once 是**永久 pending**（错过那一次就再也不提）。重做后：**主力是时机触发**（§6），**post-organize 降为一句极短的信号**（§5），profile card 不再铺冷清单（只给覆盖度分级，见 `profile-card.md`），ask-once 改为**冷却期 cooldown 而非永久沉默**（§7），并加**"没做 vs 做了没上传"分叉**（§4）和**补料成功的即时正反馈闭环**（§9）。这份 spec 是"缺失/补料"的**单一真相源**：profile card / post-organize / 时机触发 / Q&A 四个入口都引用它，口径不漂移。

---

## 1. Purpose

organize already computes what's missing (`missing_items.json`, priority-ranked) and how ready the archive is (`readiness.json`, `blocking_gaps` + per-domain `gaps`). But a raw gap list is cold and long — a patient reading "你缺了 12 项" shuts down. This behavior turns that list into a **warm, human invitation**: pick the very few gaps that would most change what a doctor / MTB / the patient's own understanding can do, and ask for each in a way that ties it to a benefit the patient cares about and tells them concretely how to get it.

The patient is always free to ignore it. Supplementing records is optional; the ask is an offer, never a demand.

---

## 2. Input

- **`missing_items.json`** (patient_dir root) — the cancer-type checklist diff. Each `missing[]` item carries `priority` (`P0`/`P1`/`P2`), `category` (`pathology`/`imaging`/`lab`/`molecular`/`history`/`consent`), `item` (plain-language description), and `reason` (why it's needed). Priorities are driven by `checklists/<cancer_type>.yaml`.
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

### "没做" vs "做了没上传" —— 一个轻分叉（必加，否则答非所问）

底层 `missing_items` 只知道"缺这份**文档**"，分不清两种完全不同的现实，而它们的**下一步动作相反**：

- **做了、报告在别处**（别的医院 / 医生手里 / 自己没传）→ 动作是**调取/上传**：影像科刻盘或导出、找主诊医生调取、病案室、问检测机构要电子报告。
- **根本没做过这项检查** → 动作是**去问医生要不要做**（描述这项检查*决定什么*，绝不建议具体用药）。

所以每条邀请**默认带一个轻问句区分二者**，别默认患者一定是"做了没传"：

> "档案里没看到基因检测(NGS)——它决定有没有靶向药可用，是最能改变方案的一份。**你是已经做了、报告在医生那，还是还没做过？** 做了的话可以找主诊医生调取或问检测机构要电子版；还没做的话，下次见医生可以问问要不要做。"

患者答"做了" → 走调取/上传路径（并按 §9 收进档案后给正反馈）；答"没做" → 记录为"未做项"（`gap_asks.json` 的 `status:"declined"` 不合适，用一个新状态 `not_done`，见 §7），下次它更适合出现在 visit-prep 的"问医生"清单里，而不是反复催上传。

---

## 5. Trigger 1 — Post-organize：只留一句极短的信号，不在此刻摊 top 2–3

**Where**: `cancer-buddy-organize/SKILL.md`，Profile Card（Step 11）之后。

**为什么降级**：organize 刚结束是患者**认知最过载**的时刻（刚看完一大张卡 + 核对 + 确认 🔴 review_flags）。补料是低优先、可延后的动作，此刻塞"你还差这几样"是在最差的时机派活；而真正该补的时机是**后来**（复诊前、被缺口卡住时）。所以 post-organize **不再摊 top 2–3 详细邀请**。

**What（只做这一点）**：

1. Load `missing_items.json` + `readiness.json`，按 §3 过滤/排序，看是否**存在**任何 P0/P1 高价值缺口。
2. 若有 → 只给**一句极短、可忽略的信号**（`profile.json.locale`），**不逐条列、不给动作细节**：
   > "档案里还差几样比较关键的（像 <最高价值那一样的类别，如'基因检测'>）——需要的时候我随时帮你补，现在这些都不挡着我陪你往下走。"
3. 若无高价值缺口 → **什么都不加**（沉默正确）。
4. **不在 post-organize 写 `gap_asks.json` 的 pending**（否则会触发旧的"提过就永久沉默"）。只在真正把某条**具体邀请**递出去（§6 时机触发 / Q&A）时才登记，见 §7。

这一步**可忽略**、永不阻塞下游路由。它只是"我知道还缺、你需要时找我"的一个低压信号，把详细邀请让给更合适的时机。

## 5.5. Trigger 2（主力）— 时机触发：在补料"顺手且相关"的时刻才递详细邀请

补料的**主要出口不是 organize 完成时，而是这些下游时刻**——此时提某条缺口，患者会觉得相关、不突兀：

| 时机 | 递哪条缺口 |
|---|---|
| **visit-prep 就诊准备**（快见医生了） | 把"没做过"的高价值检查（NGS / 分期影像）整理进"下次可以问医生"的清单；把"做了没传"的整理进"记得带上/调取"清单。这是"没做 vs 没传"分叉最自然的落点。 |
| **要路由到 find-care / second-opinion / vmtb**（缺口会削弱那份产物） | 提一句"补上 <缺口> 能让 <那份产物> 更准，要不要先补？"，患者可跳过。 |
| **Q&A 被缺口限制**（§6） | 回答完再补一句最相关的那一条。 |

规则：每个时机**最多一条**、按 §3 选最相关的那条、按 §4 措辞（含"没做 vs 没传"分叉）、按 §7 冷却期去重。**这是 top 1–3 详细邀请真正该出现的地方**，不是 organize 刚结束那一刻。

---

## 6. Trigger 3 — Q&A context-triggered inline ask (§5.5 时机触发的一个具体子例)

**Where**: `cancer-buddy/SKILL.md` 档案读取协议 (Archive Read Protocol) — when answering a patient question **whose answer is materially limited by a missing item**. 这是 §5.5 时机触发里"被问题限制"那一行的展开。

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
  - `"pending"` — surfaced, no patient action yet. **Cooldown applies (not permanent silence)** — see the cooldown rule below.
  - `"provided"` — the patient later supplied the record (a subsequent organize/incremental run finds the item now covered → flip to `provided`). A `provided` item is no longer a gap.
  - `"declined"` — the patient explicitly said they don't want to / can't get it. **Do not re-ask.**
  - `"not_done"` — the patient said the investigation **was never performed** (the §4 fork). Not a "won't upload" case — it's "hasn't happened yet". **Don't keep asking to upload it**; instead it becomes a candidate for the visit-prep "问医生要不要做" list. Re-surfacing allowed only in that visit-prep context, not as an upload nag.
- **`last_surfaced_at`** — ISO-8601 of the most recent time this `item_key` was surfaced (drives cooldown).
- **`surface_count`** — integer, how many times surfaced (hard cap, see below).

**Cooldown rule (replaces the old permanent-`pending` silence)**：旧版"提过一次 → 永久不再提"太狠，把最该补的后续时机也堵死了。改为**冷却期 + 硬上限**：

- 一个 `item_key` 为 `pending` 时，**同一会话内不再提**；跨会话则需距 `last_surfaced_at` **≥ 14 天**才可再提一次，且**只在 §5.5 的时机触发（visit-prep / 路由 / 被问题限制）**下、当它确实是此刻最相关的那条时才提——**不是**每 14 天主动 nag。
- **硬上限 `surface_count ≤ 3`**：提满 3 次仍无行动 → 视作患者无意补，转 `declined`，不再提。
- `provided` / `declined` / `not_done` 一律不再作为"上传催办"重提（`not_done` 仅在 visit-prep 语境作"问医生"候选）。
- post-organize 的那句极短信号（§5）**不写 ledger、不占 cooldown 名额**——它不是一条具体邀请，只是个信号。真正登记的是 §5.5/§6 递出的**具体**邀请。

**Surface 前的检查**：load `gap_asks.json`；若 `item_key` 已 `provided`/`declined`，skip；若 `pending`/`not_done`，按上面的 cooldown + 上限判定能否再提；否则可提，提后 append/更新 `last_surfaced_at` + `surface_count`。

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
- **Locale + verbatim clinical entities** — render the scaffold/prose in `profile.json.locale`; keep drug/gene/variant/TNM/biomarker names and numbers verbatim regardless of locale (mistranslation is a P0 safety bug — see `../../cancer-buddy/references/safety-guardrails.md`).

---

## 9. 补料成功的即时正反馈闭环（补完要有回声，别让它沉进静默账本）

旧版补料是**单向静默**：患者补了一份报告，`provided` 靠"下一次 organize 被动发现已覆盖"才翻转，当下**没有任何回声**。补料对患者是有情绪价值的动作（我在为自己的病做事）——不给回声，体验就冷。补完必须立刻闭环：

1. **即时确认收到**（`profile.json.locale`，warm）："收到了，这份 <缺口，如 NGS 报告> 我加进你的档案了。"
2. **说明它解锁了什么**（把补料和"更帮到你"挂钩，仍**不给治疗建议**——只说这份*记录*让**分析/医生/你自己的理解**多了什么）："这下分期和有没有靶向药可用这两块能判得更准了。"
3. **顺势给一个可选的下一步**（把补料接回价值，不强推）："要不要我现在把相关的部分重新过一遍？" → 触发对应的 `incremental` / `upload_reconciliation`（走各自的确认门）。
4. **翻状态**：把该 `item_key` 在 `gap_asks.json` 置 `provided`（若这次是通过对话上传/调取补入的，不必等下一轮 organize 被动发现）。

若患者答的是"没做过"（§4 分叉）→ 不进本闭环，按 §7 记 `not_done`，并轻轻说一句"那这个先记着，下次见医生可以问问要不要做"，把它交给 visit-prep，而不是继续催上传。
