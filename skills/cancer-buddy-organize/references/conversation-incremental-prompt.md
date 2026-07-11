# Organizer Prompt — Conversation-Incremental Worker (段C)

This is the `conversation-incremental` run mode of `cancer-buddy-organize`. It runs while the patient (or caregiver) is *chatting* about their condition — not when they hand over a folder of files. Its job is to catch archivable facts that surface in conversation, propose them as a reviewable diff, and write them only after the user confirms.

The hard rule of this mode: **unconfirmed talk never touches formal fields.** A patient mis-speaking ("我好像是三期吧?") must not silently rewrite `profile.json.summary.stage` and poison every downstream report. The diff card + explicit confirmation is the gate.

That gate is **not redefined here** — it is the shared confirm-gate. The "unconfirmed → no formal write" floor, the diff-card presentation contract, and the `update_log.json` provenance requirement all live in [`../../cancer-buddy/references/confirm-gate.md`](../../cancer-buddy/references/confirm-gate.md); cite it as authoritative. This doc keeps only what is **specific to conversation mode**: the 5 archivable-fact categories, the conversation anchor, and `patient_curated` tagging.

## When this mode runs

- The caller (meta-skill or a companion sub-skill) is in an ongoing chat with the user about their illness, and a `<patient_dir>` with an existing `update_log.json` already exists (organize has run at least once).
- A turn in that chat contains a candidate archivable fact (see below).
- Caller passes `run_mode: "conversation_incremental"` plus `patient_dir`.

This mode does NOT re-OCR files and does NOT re-run Phase-1/Phase-2 synthesis. It writes only the archived conversation note (into the fact's corresponding clinical domain's `conversation_notes/` subdir, or `14_患者自管补充/conversation_notes/` as fallback — see Step 4a) plus the confirmed `profile.json` field / `timeline` row. For new *files*, use full or incremental mode instead.

## Inputs (caller supplies these)

- `patient_dir` (required): absolute path of the existing patient directory.
- `conversation_turn` (required): the user's message(s) this run is examining, plus enough surrounding context to disambiguate. Verbatim — do not pre-summarize.
- `turn_timestamp` (required): ISO-8601 timestamp of the user turn, used to build the conversation anchor. e.g. `2026-06-07T14:32:05Z`.
- `actor_role` (required): `patient` | `caregiver` (family role does not write — see SKILL.md Role behavior).

## What counts as an archivable fact

Detecting these is an **LLM judgment task — do not pattern-match a keyword list.** Read the turn in the context of the existing `profile.json` / `timeline.md` and decide whether the user just stated something clinically archivable. Five categories to look for:

| category | examples of what the user might say |
|---|---|
| 新诊断 / 分期变更 | "上周复查说转移到肝了", "医生改判成 IV 期了" |
| 新检验值 | "昨天 CEA 查出来 48", "白细胞掉到 2.1 了" |
| 治疗变更 | "这周开始换成奥希替尼了", "化疗停了，改靶向" |
| 症状 | "最近一周咳血", "脚肿得厉害" |
| 体能 / ECOG | "现在基本卧床了", "能自己走但走不远" |

Ignore turns that are purely emotional, logistical, or questions ("我会不会死", "下次几号复查"). Those are not archivable clinical facts — route them to the appropriate companion sub-skill instead, write nothing.

If a turn is genuinely ambiguous about a critical field (stage / molecular driver / line of therapy), prefer to **ask one clarifying question in the diff card** over guessing. Never fabricate a precise value the user did not give.

## Process

### Step 1 — Read existing state

```bash
cat "$patient_dir/profile.json"
sed -n '1,80p' "$patient_dir/timeline.md"   # for context only
```

You need the current value of any field a candidate fact would change, so the diff card can show before → after.

### Step 2 — Extract candidate facts (LLM judgment)

From `conversation_turn`, extract zero or more candidate facts. For each, decide its **target**:

- **profile.json field** — when the fact updates a structured field. Use the dot path from [`../../cancer-buddy/references/patient-profile-schema.md`](../../cancer-buddy/references/patient-profile-schema.md), e.g. `summary.stage`, `summary.current_regimen`, `latest_status.ecog`. (Drivers now live in `molecular.json`, demographics in `patient_summary.json`, and ordered lines of therapy in `treatment_lines.json` — those are no longer profile.json fields.) Only write fields that exist in the schema.
- **timeline row** — when the fact is a dated clinical event (a new line of therapy starting, a symptom onset, a new lab draw). One new line appended to `timeline.md`, mirrored as one entry in `timeline.json`.

A single turn may yield both (e.g. "这周换奥希替尼了" → `summary.current_regimen` field change **and** a new timeline row for the switch).

Each candidate carries:
- `target`: `profile_field` | `timeline_row`
- `field_path` (for `profile_field`) or `event_date` + `event_text` (for `timeline_row`)
- `current_value` (what's there now, or `null`)
- `proposed_value`
- `category` (from the table above)
- `confidence`: `high` only if the user stated it plainly and unambiguously; `low` if you had to infer or the user hedged ("好像", "大概")

### Step 3 — Emit a diff card (do NOT write yet)

Present every candidate to the user as a compact, plain-language diff card, per the diff-card contract in [`../../cancer-buddy/references/confirm-gate.md`](../../cancer-buddy/references/confirm-gate.md) (current→proposed, quote the 依据, mark `low` confidence, critical-field never a fait accompli, locale + verbatim-clinical). One card per turn, listing all candidates. Conversation-specific format:

```
我从刚才的对话里听到这些可以归档的信息，确认后我才会写进档案：

① 分期  III 期  →  IV 期（肝转移）
   依据: 你说"上周复查说转移到肝了"
   [确认]  [改一下]  [先不写]

② 时间线  + 2026-06-05  CEA 48 ng/mL（你口述，待化验单佐证）
   [确认]  [改一下]  [先不写]

口述信息我会标成"患者自述"，等正式化验单/报告到了再升级。
```

Rules for the card:
- Show `current_value → proposed_value` for field changes; show the full new line for timeline rows.
- Quote the user's own words as the 依据.
- For `low`-confidence candidates, say so plainly and offer "改一下" so the user can correct the value rather than accept a guess.
- Never present a critical-field change (stage / molecular driver / line of therapy) as a fait accompli — it must be explicitly confirmed.

### Step 4 — On user confirmation, write

Only write the candidates the user confirms (`确认`). For `改一下` use the user's corrected value, then write. For `先不写` / silence / deferral, write nothing for that candidate.

**4a. Archive the note (always, for every confirmed candidate) — routed to its clinical domain:**

First, decide **which clinical domain** the confirmed fact belongs to, then file the note into THAT domain's `conversation_notes/` subdir — not unconditionally into `14_`. Use the **same Step-1a-style LLM domain judgment the synthesis worker uses**: read the confirmed fact in the context of the existing `profile.json` and pick the matching domain from the 14 clinical domains in [`bucket-taxonomy.md`](bucket-taxonomy.md) §1.1. This is **LLM judgment — do NOT use a hardcoded keyword→domain map** (per the skill's no-hardcode rule). What's load-bearing is the **two-digit `NN_` prefix** of the chosen domain; the slug after it is **localized to `profile.json.locale`** (zh slug like `07_检验` when locale=zh, the `en` slug like `07_labs` for every other locale — see `bucket-taxonomy.md` §1.1a / [`../../cancer-buddy/references/i18n.md`](../../cancer-buddy/references/i18n.md) §6). Typical mappings (shown with zh slugs for illustration; resolve to the actual localized dir at write time):

- a new lab value → `07_` (检验 / labs)
- a newly stated pathology / diagnosis / staging → `04_` (诊断与分期 / diagnosis_staging)
- a treatment change → `08_` (治疗 / treatment)
- an imaging finding → `05_` (影像 / imaging)
- a molecular / NGS result → `06_` (分子与组学 / molecular_omics)
- a symptom / PRO / ECOG / follow-up observation → `10_` (随访与监测 / followup_monitoring)

Only when the fact fits **no clinical domain** (a general life note, an undirected remark) does it fall back to the `14_` domain (患者自管补充 / patient_supplement) `conversation_notes/`.

Append to a dated note under the chosen domain's `conversation_notes/` subdir. **Resolve `$domain_dir` by globbing the bucket by its `NN_` prefix; if it does NOT exist yet, create it under the locale-correct pinned slug** — organize now uses **lazy bucket creation** (setup makes only `ocr/`+`raw/`; a clinical bucket exists only if a prior run filed a sidecar there), so on a typical 段C archive the target bucket is usually ABSENT and MUST be created, never silently misfiled to the patient-dir root:

```bash
nn=07   # the two-digit prefix from the LLM domain judgment above (14 = no-domain fallback)
domain_dir=$(basename "$(ls -d "$patient_dir/${nn}_"*/ 2>/dev/null | head -1)")
# Lazy-archive guard: bucket not materialized yet → use the pinned slug for this
# locale (zh slug e.g. 07_检验 when profile.json.locale=zh; en slug e.g. 07_labs for
# every other locale) per i18n.md §6 / bucket-taxonomy.md §1.1a. NEVER leave it empty
# (empty → mkdir -p "$patient_dir//conversation_notes" collapses to the ROOT and the
# note escapes the NN_-keyed PII gate + every NN_-prefix consumer).
[ -z "$domain_dir" ] && domain_dir="<localized NN_ slug for nn from profile.json.locale>"
mkdir -p "$patient_dir/$domain_dir/conversation_notes"
# write to <domain_dir>/conversation_notes/<turn_timestamp-date>.md
```

**PII (MANDATORY — 段C has no Phase-1 masker, so do it here):** before writing the verbatim user quote into the note, mask PII in the quote to `[PII_MASKED]` per the **same open-ended category judgment as `organizer-prompt-phase1-ocr.md` §2.4** (patient/family name, MRN/住院号/门诊号, phone, address, bed, signatory names, ID, DOB, specimen_id 检验号/标本编号, postal code, 出生地/籍贯, 职业/工作单位, 民族 …) — clinical entities stay verbatim (§2.2a). Then run **both §2.5 layers** on the note: the Layer-1 semantic agent scan (`pii-rescan-prompt.md`) AND `python3 "$ORGANIZE_SKILL_DIR/scripts/pii_rescan.py" "$patient_dir/$domain_dir/conversation_notes/<file>.md"`, re-masking until **both** are clean. Filing under an `NN_` bucket (above) ALSO ensures a later full/incremental acceptance-gate rescan covers it; the gate additionally scans `conversation_notes/*.md` wherever it lands as defense-in-depth.

The note file carries a `tags: [patient_curated]` front-matter marker and the **PII-masked** user quote + the confirmed structured value. This file is the **archive**, not the citation target — facts cite the conversation anchor, not this file (see anchor-contract §1b). The note still carries the **conversation** anchor, never a file anchor, because the source is the dialogue turn — domain routing only chooses where the archive lands, it does not change the provenance class.

**4b. Update the formal field / timeline (only after confirm):**

- `profile_field` → update that field in `profile.json` to the confirmed value. Append a `source_refs` entry `"conversation:<turn_timestamp>"` wherever the schema carries provenance for that field. Leave every other field untouched.
- `timeline_row` → append one line to `timeline.md` ending with the conversation anchor, and one mirrored entry to `timeline.json` with `source_refs: ["conversation:<turn_timestamp>"]`. Keep timeline date-sorted.

**Provenance — use the conversation anchor, never a file anchor:**

```
- 2026-06-05 患者自述 CEA 48 ng/mL（待化验单佐证） [[src:conversation:2026-06-07T14:32:05Z]]
```

The anchor's timestamp is `turn_timestamp` (the chat turn), per [`schemas/anchor-contract.md`](schemas/anchor-contract.md) §1b. Conversation anchors have no path and no `#fragment` — the dialogue turn is the source.

**4c. Mark provenance class.** Any field or timeline row written from conversation is tagged `patient_curated` (口述), distinct from `record_sourced` (OCR'd from a file). Downstream readers and the 段D HTML can render "（患者自述，待报告佐证）" so a spoken value is never mistaken for a confirmed lab/report value. When a real report later arrives and is OCR'd, full/incremental organize upgrades the field to a file anchor; the conversation note stays as the original capture.

### Step 5 — Log the run

Append one entry to `update_log.json`:

```json
{
  "run_mode": "conversation_incremental",
  "ts": "<turn_timestamp>",
  "triggered_by": "<actor_role>",
  "confirmed_fields": ["summary.stage"],
  "confirmed_timeline_rows": 1,
  "rejected_or_deferred": 1,
  "conversation_anchor": "conversation:<turn_timestamp>",
  "reason": "patient reported liver metastasis in conversation"
}
```

`profile.json.alias` is sticky — never touched by a conversation-incremental run. Do not rewrite `case_text.md`, `readiness.json`, or the 6 structured JSONs beyond the specific field/row confirmed; a major change ("我整套方案都换了") should be routed to a full re-organize, not merged turn-by-turn.

## Step 6 — Return JSON

Final message MUST be pure JSON, no prose:

```json
{
  "role": "conversation_incremental_worker",
  "patient_dir": "<abs patient_dir>",
  "candidates_detected": 2,
  "candidates_confirmed": 1,
  "candidates_corrected": 1,
  "candidates_deferred": 0,
  "profile_fields_written": ["summary.stage"],
  "timeline_rows_added": 1,
  "conversation_note_path": "07_检验/conversation_notes/2026-06-07.md",
  "conversation_anchor": "conversation:2026-06-07T14:32:05Z",
  "run_logged": true
}
```

## Rules

The gate rules (unconfirmed → no formal write; silence = no-confirm; never fabricate; critical-field never a fait accompli; never silently overwrite a contradicting value; LLM judgment not a keyword list; `alias` sticky / no broad rewrite) are the shared floor in [`../../cancer-buddy/references/confirm-gate.md`](../../cancer-buddy/references/confirm-gate.md) — that doc is authoritative; do not fork them here. Conversation-mode specializations on top of that floor:

- **Never use a file anchor for a conversation fact.** Conversation provenance is `[[src:conversation:<ISO8601>]]` only — domain routing of the archive note (Step 4a) does not change this; the source is still the dialogue turn.
- **Route the archived conversation note to its corresponding clinical domain's `conversation_notes/` subdir**, not unconditionally into the `14_` domain. Pick the domain with the same Step-1a-style LLM domain judgment the synthesis worker uses (read the confirmed fact + existing profile context against the 14 domains in `bucket-taxonomy.md` §1.1) — e.g. a lab value → `07_` domain, a staging change → `04_` domain, a treatment change → `08_` domain. The `14_` domain is the **fallback only**, used when the fact fits no clinical domain. **Resolve the actual directory by its stable `NN_` prefix against the existing buckets (Step 4a), so the note lands in the archive's locale-correct slug (`07_检验` for zh, `07_labs` for en/fr…) — never hardcode the zh slug and never mkdir a phantom second bucket.** This is LLM judgment, **not a hardcoded keyword→domain map**.
- Detecting and classifying the 5 archivable-fact categories is an LLM judgment task — read each turn in context, do not run a hardcoded keyword list.
- Tag every conversation-sourced field/row `patient_curated`; never let a spoken value masquerade as a confirmed report value.
