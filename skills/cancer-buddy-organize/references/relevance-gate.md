# Medical Relevance Gate — 段E

Before any file enters the 11-bucket clinical archive, it passes a **relevance triage**: is this file a medical record, or is it an unrelated photo / screenshot / receipt that slipped into the upload folder? This gate runs inside Phase 2 (`organizer-prompt-phase2-synthesis.md` Step 1, before classification) and decides three things: which files become formal clinical records, which are isolated as 无关, and which are too uncertain to delete without asking.

The hard rule of this gate (privacy floor): **we do not keep a patient's raw unrelated files.** A high-confidence non-medical file the patient does not claim back is deleted — silence means delete. The only file we never auto-delete is one we are *not sure* about, because deleting a real medical record is worse than keeping a stray screenshot.

This silence⇒delete (high-confidence) vs silence⇒hold (borderline) asymmetry is **not defined here in isolation** — it is the irreversible-delete sub-rule of the shared confirm-gate, [`../../../references/confirm-gate.md`](../../../references/confirm-gate.md); cite it as authoritative. This doc keeps the 段E specialization: the three relevance classes, `99_无关文件/` quarantine semantics, the `relevance_uncertain` review_flag, and the disposition notice.

## Why this is an LLM judgment, not a keyword list

Real upload folders are messy: a phone camera roll mixed in, a WeChat screenshot of a doctor's message (which *is* clinically useful), a photo of a pill bottle (useful), a selfie taken in a hospital ward (not useful), a meal photo (not useful), a receipt for a CT scan (administrative, borderline). No keyword list survives contact with this — "医院" appears in both a discharge summary and a parking receipt; a screenshot can be either a lab result or a chat about dinner.

So relevance is decided by **reading the OCR sidecar content + looking at the image**, the same way a person triaging the folder would. Do NOT pattern-match filenames or run a hardcoded keyword classifier. Judge the file.

## Three classes

For every file, after reading its sidecar (and, when ambiguous, the image itself), assign exactly one relevance class:

| class | what it looks like | landing place |
|---|---|---|
| **medical** | Any record carrying clinical content: 检查单 / 化验报告 / 病理报告 / 影像（含影像截图）/ 基因报告 / 出院小结 / 处方 / 医嘱 / 知情同意书 / 医生发来的诊疗信息截图 / 用药照片（药盒/药瓶可辨）/ 手术记录 / 会诊意见. When in real doubt but it *plausibly* carries clinical value, lean **medical**, not borderline — a record wrongly dropped is the costly error. | normal → into the 11 buckets, full OCR→脱敏 MD→classify flow |
| **non-medical, high-confidence** | Clearly unrelated to the patient's care: 风景照 / 自拍 / 宠物 / 餐食 / 旅游 / 无关聊天截图 / 广告 / 纯生活收据 / app 界面截图 / 重复的空白页 / 误拍的桌面. You would bet money it has no clinical value. | isolate → `99_无关文件/`, NOT into the 11 buckets; eligible for auto-delete on no-confirm |
| **borderline / 拿不准** | Could go either way and you genuinely cannot tell: a blurry photo that *might* be a report, a receipt that might encode which scan was done, a screenshot whose text is unreadable, a partial document. | isolate → `99_无关文件/` **but flag** `relevance_uncertain`; **never** auto-deleted — waits for the user to decide 删/留 |

Calibration: the bar for **non-medical high-confidence** is "I would bet money this has no clinical value." If you are not at that bar, it is **borderline**, not high-confidence non-medical — because the high-confidence bucket is the one that gets auto-deleted on silence, and that deletion is irreversible.

## `99_无关文件/` bucket semantics

`99_无关文件/` is a **quarantine staging area, not part of the formal archive**. Files here are:

- NOT OCR'd into a 脱敏 MD sidecar (no clinical content to extract), NOT classified into a typed bucket, NOT referenced by any anchor, timeline, profile field, or structured JSON.
- NOT mirrored as a permanent record — they are explicitly the files we intend not to keep.
- Held only long enough for the user to claim any back ("X 其实有用") before the high-confidence ones are deleted.

It is deliberately the last-numbered bucket and sits outside the `00_…11_` clinical scheme so downstream sub-skills never read it. A file in `99_无关文件/` has, by definition, not entered the patient's clinical record.

Inside `99_无关文件/`, separate the two non-medical sub-classes so the delete/keep logic is unambiguous:

```
99_无关文件/
  high_confidence/    # non-medical high-confidence → auto-delete on no-confirm
  uncertain/          # borderline → review_flag relevance_uncertain, NEVER auto-deleted
```

## review_flag: `relevance_uncertain`

Every borderline file produces one review_flag so the uncertainty is surfaced to the user (and to `readiness.json`) rather than silently resolved. The `issue` / `suggested_action` strings are patient-facing scaffold → render in `profile.json.locale` (the `zh` text below is the template); `field_path` keeps the on-disk localized bucket slug.

```json
{
  "id": "RF-0NN",
  "severity": "yellow",
  "category": "relevance_uncertain",
  "field_path": "99_无关文件/uncertain/<filename>",
  "current_value": "isolated as uncertain-relevance",
  "issue": "拿不准这张是不是病历资料 — 隔离待用户定夺，未自动删除。",
  "source_evidence": [],
  "suggested_action": "请用户确认：这张是病历资料(归档回去) / 还是无关文件(删除)。在用户显式选择前不删。",
  "user_confirmed": false
}
```

- `severity: yellow` — it should be reviewed, but it does not break any downstream record (the file is not in the archive). It is NOT `red`: it gates no eligibility/dosing decision.
- `category: relevance_uncertain` — this is the **8th** review_flag category, added to the 7-check audit set (`format_violation`, `cross_doc_contradiction`, `clinical_logic_anomaly`, `unverified_critical_field`, `value_trend_anomaly`, `cross_patient_name_collision`, `anchor_coverage_gap`, **`relevance_uncertain`**).
- High-confidence non-medical files do **not** get a review_flag — they are surfaced collectively in the disposition notice (below) and auto-delete on no-confirm. Only the borderline batch needs per-file flags, because the borderline batch is the one that waits.

### readiness.json reflection

- Each `relevance_uncertain` review_flag is appended to `readiness.json.review_flags[]` like any other flag.
- Add a one-line warning per uncertain file: `"relevance_uncertain: 99_无关文件/uncertain/<filename> — 待用户确认删/留"` into `readiness.json.warnings`.
- Relevance triage does **not** lower the 8-domain readiness score (无关文件 are not missing clinical data) — but unresolved `relevance_uncertain` flags are listed so the user sees there are pending 删/留 decisions before the archive is considered settled.

## User disposition notice (surfaced after organize)

**Locale (i18n):** this notice is patient-facing scaffold → render it in `profile.json.locale` (detect/persist per [`../../../references/i18n.md`](../../../references/i18n.md); the `zh` wording below is the template). The privacy-floor sentence is mandatory in **every** locale — it must appear with the same meaning and no softening (semantically identical, not omitted). Clinical content inside isolated-file reasons stays verbatim. Bucket-path slugs in the listing (`99_无关文件/uncertain/…` ↔ `99_unrelated/uncertain/…`) follow the localized slug actually on disk (i18n.md §6).

When the gate isolated any files, surface one plain-language notice. The privacy-floor sentence is mandatory and must be stated explicitly — the user has to know we do not retain raw unrelated files:

```
整理时我发现这些文件看起来跟病情无关，没有收进正式档案：

无关（我比较确定 — 风景照/截图/收据等）：N 张
  我们不保存你的原始无关文件 —— 你不确认，我也会自动删除。
  如果其中哪张其实有用，告诉我是哪张，我归档回去。

拿不准（M 张）：这几张我不确定是不是病历资料，先留着没删，
  请你帮我看一眼：是病历(归档回去) / 还是无关(删掉)。

  ① 99_无关文件/uncertain/<文件名>  — <一句话为什么拿不准>
  ② ...
```

Rules for the notice:
- The sentence **"我们不保存你的原始无关文件 —— 你不确认，我也会自动删除"** (in `zh`; rendered semantically-identical in the user's `locale` for any other language — e.g. `en`: "We don't keep your raw unrelated files — if you don't confirm, I'll delete them automatically.") is mandatory and must appear in that locale with no softening. The user is entitled to know silence ⇒ deletion *before* it happens.
- List the borderline (uncertain) files individually with a one-line reason each, because each needs a per-file 删/留 decision.
- High-confidence non-medical files may be summarized as a count (they don't each need a decision — silence deletes them); the user only needs to know they exist and can claim any back.

## Runtime adaptation — 确认门产物化

The disposition notice above and the 删/留 prompt are rendered, in the **Claude Code binding**, as an inline diff card the user resolves in the same turn (inline 即时往返). That inline card is a **CC reference mechanism, not the contract**. The contract ([`organize-contract.md`](organize-contract.md) §3 确认门, §6「确认门」seam) requires only that the disposition decision be **gated** — never the specific rendering.

A headless host (no inline turn) satisfies the same gate by **confirm-as-product**: it emits the待确认项 (the per-`uncertain/` file with its one-line reason, plus the high-confidence-batch count and the mandatory privacy-floor sentence) as a **data artifact** for its own UI to ask the user about after the fact, then re-feeds the user's 删/留/回收 decisions in a second round. The contract is unchanged either way: **未确认不写正式字段, and the silence⇒delete (high-confidence) vs silence⇒hold (borderline) asymmetry holds identically** — the privacy-floor sentence must still reach the user *before* any deletion regardless of rendering, and a borderline file with no explicit resolution is still never auto-deleted. Only "who renders the question" differs; the gate, the asymmetry, and the `update_log.json.relevance` ledger do not.

## Disposition parsing — three resolution paths

After the notice, parse the user's response. There are exactly three outcomes per file:

### 1. Delete (删)

Applies to **high-confidence non-medical files** in two situations:
- the user confirms they're unrelated, **OR**
- the user does not respond / does not claim any back (silence, deferral, "随便", closing the chat).

→ **Delete** the file from `99_无关文件/high_confidence/`. This is irreversible and intended (privacy floor). Record it in `update_log.json` (see below). Do NOT delete the originals from anywhere else — high-confidence non-medical files were never copied into the 11 buckets or anchored, so the `99_无关文件/` copy is the only copy and deleting it is the whole point.

### 2. Keep / reclassify (回收 — "X 其实有用")

Applies when the user says a specific isolated file actually matters.

→ **Reclassify**: move the file out of `99_无关文件/` into its correct typed bucket, then run the *normal* path it should have had — OCR → 脱敏 MD → canonical rename → co-locate MD → add to INDEX/timeline/case_text/structured JSONs as a late-arriving medical record. This is the error-correction path: a file the gate wrongly judged non-medical is recovered into the formal archive. After reclassify it is a normal clinical record with full anchors; it is no longer in `99_无关文件/`.

A reclassified file follows the same Step 1 classify+rename+MD-colocate mechanics as any medical file (it just enters late). If it's a raster image it also gets appended to `redaction_manifest.json` so 段B redacts its PII pixels.

### 3. Hold (borderline default — the one exception)

Applies to **borderline `relevance_uncertain` files** for which the user has **not** made an explicit 删/留 choice.

→ **Do nothing — keep the file in `99_无关文件/uncertain/`, do not auto-delete.** This is the explicit exception to the silence-deletes rule: a borderline file is held until the user *explicitly* says 删 or 留, because deleting something that might be a real medical record is the worse error. Silence deletes a high-confidence non-medical file; silence does **not** delete a borderline file.

When the user does explicitly resolve a borderline file:
- "删" / "无关" → delete it (now treat as path 1).
- "留" / "这是病历" → reclassify it into the archive (now treat as path 2).
- In both cases the `relevance_uncertain` review_flag is marked `user_confirmed: true` with the chosen `resolution`.

## Auto-delete is irreversible — invariants

These are the load-bearing rules; the rest of the doc explains them. They are the 段E instance of the shared confirm-gate's irreversible-delete sub-rule ([`../../../references/confirm-gate.md`](../../../references/confirm-gate.md)) — the asymmetry below must stay identical to that doc; if they ever diverge it is rule drift, fix it at the shared gate.

1. **High-confidence non-medical, no confirmation ⇒ delete.** Silence/deferral counts as no-confirm and the file is deleted. This is by design (we do not retain raw unrelated files), not a bug.
2. **Borderline (`relevance_uncertain`) ⇒ never auto-deleted.** It is held in `99_无关文件/uncertain/` until the user *explicitly* chooses 删/留. Silence does NOT delete a borderline file.
3. **medical files are never touched by this gate's deletion** — they're in the 11 buckets with the normal "redact-then-delete" carve-out (段B), not the relevance carve-out.
4. The user must be told, before any deletion, that we don't keep raw unrelated files and that silence ⇒ delete (mandatory disposition-notice sentence above).

## update_log.json — record every relevance action

Each organize run that touched the gate appends relevance actions to `update_log.json` so the irreversible deletions are auditable:

```json
{
  "run_mode": "full",
  "relevance": {
    "isolated_high_confidence": 4,
    "isolated_uncertain": 2,
    "auto_deleted": ["99_无关文件/high_confidence/IMG_0042.jpg"],
    "reclassified": [
      {"from": "99_无关文件/high_confidence/IMG_0051.jpg",
       "to": "07_治疗记录/化疗/2024-05-02_临时医嘱_中山六院.jpg"}
    ],
    "held_uncertain": ["99_无关文件/uncertain/IMG_0077.jpg"]
  }
}
```

`auto_deleted` is the irreversible-action ledger — every entry here was a file we deleted because it was high-confidence non-medical and unclaimed. `held_uncertain` files carry over to the next run still flagged `relevance_uncertain` until the user decides.

## Relationship to the rest of the pipeline

- Runs **inside Phase 2 Step 1, before** classify+rename — see `organizer-prompt-phase2-synthesis.md` Step 1 (triage step). A file judged non-medical never reaches the bucket scheme.
- The deletion carve-out it relies on is the 段E entry in `../../references/safety-guardrails.md` (high-confidence auto-delete on no-confirm; borderline never auto-deleted). That guardrail is the authoritative red-line; this doc is the operational logic.
- It does NOT touch the 段B redaction carve-out (different deletion: 段B deletes the *pre-redaction* original of a *medical* image after QA; 段E deletes an *unrelated* file we never archived).
