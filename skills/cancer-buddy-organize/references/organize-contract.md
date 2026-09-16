# Cancer Buddy Organize Contract

This contract separates source preservation, extraction, organization, and patient-facing rendering. It
does not authorize clinical interpretation.

## Pipeline

The run is **四段编排 + 两道子门** — six numbered nodes: 段 0 / 段 1 / 段 1.5 / 段 2 / 段 2.5 / 段 3.
The four stages proper are 段 0、段 1、段 2、段 3; 段 1.5 (channel-independent second read) and
段 2.5 (source faithfulness) are the two sub-gates. The numbering is the contract; how a host
schedules them is a binding detail (`runtime-bindings/`). No file uses `Phase N` / `Stage N` /
`Step N` any more — those three spellings are retired.

### 段 0 — Adapt (deterministic, zero LLM)

Unpack archives, normalize containers (HEIC→raster), hash bytes, store originals verbatim under
access-controlled `raw/` with de-identified filenames, mint immutable `source_id`s.

Render each PDF page (`pdftoppm`, one fixed resolution per contract default `-r 150`), extract that
page's character layer, and classify `text_layer_kind`:

| value | meaning |
|---|---|
| `born_digital` | real electronic text on the page |
| `embedded_ocr` | a text layer exists but the page is essentially a full-page image (scanner OCR output) |
| `absent` | no text layer |
| `not_applicable` | non-visual modality decoded by a deterministic adapter (DICOM headers/SR, VCF, timeseries) |

Also detect orientation, blank/duplicate pages, and optionally run a deterministic OCR appendix.
Non-visual modalities are decoded here by validated format-specific tools and become a `text_layer`
(`domain-pack.md` §3). **An LLM never decodes binary data.**

Output: a page package per page — `{image, text_layer, text_layer_kind, ocr_appendix?}` — plus a
cache lookup keyed on the four-part key
`sha256(image_bytes) + "." + sha256(text_layer_text)[:16] + "." + prompt_version + "." + model_id`
(a changed text layer is a different page and must never hit an old entry).

### 段 1 — Transcribe (stateless, one page per call)

Each page is transcribed **independently**: no cross-page memory, no access to other pages'
output, no clinical judgment. Input is exactly
`{image, text_layer, text_layer_kind, page_index, page_total, source_id}`; output is a YAML
frontmatter plus a `# 全文` verbatim body (`organizer-prompt-phase1-transcribe.md`).

There is **no `prev_page_tail`** — carrying the previous page's tail made the call half-stateful and
made the cache either unreproducible (key ignores it) or worthless (key includes it, so editing one
page invalidates the whole chain). Cross-page continuation is expressed in the body with `[续上页]`
and resolved by 段 2, not by 段 1 remembering. The cache key is therefore fully page-local:

```
sha256(image_bytes) + "." + sha256(text_layer_text)[:16] + "." + prompt_version + "." + model_id
```

Two page-level rules:

- **Pixel pages (`absent` / `embedded_ocr`): the pixels are the character truth.** The model's
  full-text Markdown is the body. A scanner's own OCR layer is not authoritative — it is demoted to a
  comparison channel; a high-risk-field conflict with it goes into `discrepancy[]`.
- **Born-digital pages: the text layer is the body.** Vision only restores layout and adds the paper
  elements the character layer cannot hold (stamps, handwriting, checkbox state, circled marks,
  tables `pdftotext` shredded). A token-level conflict goes into `discrepancy[]` and triggers a
  second read; **the probabilistic layer never overwrites the deterministic one.**

Deterministic OCR (e.g. `tesseract`), when it runs, is a **three-state additive signal, never a veto**:
0 bytes or garbage = **no signal** (produces no flag and is not a disagreement); parseable and in
numeric conflict on a high-risk field = a real signal that triggers a second read; parseable and
agreeing = a confidence bonus. A host without the OCR tool installed must satisfy the second read
through another independent channel — it may not leave a high-risk field read only once.

Every page produces **two Markdown files**:

| file | content | who may read it |
|---|---|---|
| `raw/transcript/<source_id>/page-NNN.md` | verbatim | **deterministic scripts + authorized humans only** — see the reader rule below |
| `ocr/<source_id>/page-NNN.md` (transient staging; moved into its bucket by 段 2, after which `ocr/` is deleted) | masked | the only downstream read surface |

**Who may read `raw/transcript/` (the complete list):**

1. **Deterministic scripts** — `ingest_transcripts.py` (writes it), `verify_native_text.py`
   (byte identity), `export_share.py` (to *exclude* it). Zero model calls, no output that leaves
   `raw/`.
2. **An authorized human** doing the spot-check, reading the original page next to it.

Nobody else. In particular **段 2 投影、段 2.5 忠实度、PII 语义扫描都不读它**: 段 2.5 compares
against the **`raw/` page image / character layer** (a `bbox` or a `text_layer_offset`), not against
the verbatim Markdown — comparing a projection to a transcript made by the same model is
self-referential. The PII layer does not read it either: pulling unmasked text into a scanning
agent's context and logs is how the plaintext escapes.

**Consumers read nothing under `raw/` except what `source_inventory.json` references** — that
includes `raw/transcript/`, `raw/_cache/`, `raw/_provenance/` and `raw/adapter_views/`. A consumer
that reads any of them is violating this contract, and every export excludes all of them.

Structured data is a **projection** of the full text. Full-text completeness outranks field
completeness: a missing field can be re-derived, a missing paragraph is gone. A page is never
abbreviated because it does not look like a known document type.

### 段 1.5 — Channel-independent second read (targeted, not whole-archive)

Trigger = the fixed high-risk list (`high-risk-fields.md`) ∪ self-reported `uncertain` ∪
`discrepancy[]` ∪ deterministic-OCR numeric conflict. Self-reported uncertainty is a supplement,
never the primary trigger — the classic errors (decimal place, unit magnitude, HGVS `c.`/`p.`
transposition, VAF `%` vs decimal, zero count in a dose) are anti-correlated with it.

**A re-read by the same model on the same image is not an independent read.** The second channel is
one of: a **different model** (`alternate_vision_model`), a **different modality**
(`text_layer` / `barcode` / parseable `deterministic_ocr`), or a **human**. A same-model crop re-read
may only break a tie; it can never set `passed_independent_reread` and is not a valid
`reread_channel`. **Majority voting is prohibited.**

**The one and only way to record "this high-risk field passed its second read" is**
`high_risk_fields[].status: passed_independent_reread` **plus the `reread_channel` that produced
it.** The words `settled_fact` / `settled` / `settled_via` are **not** a status and must not be used
for it (the single exception is `extracted_fields.json`'s `open_verification_status: settled`, a
different enum on a different, non-citable surface).

Disagreement → `status: needs_human_review`, both readings preserved side by side,
`audience: internal_qc`, patient-facing value `null`. No channel available →
`reread_channel: none` + `status: needs_human_review`; never a silent pass, and never the string
`human` (writing `human` asserts a spot-check verdict that does not exist — see the spot-check rule
below).

Before delivery, a **human spot-check** of ≥3 fields or 5% of high-risk fields (whichever is larger)
is compared against `raw/`, recorded under `raw/_provenance/<run_id>/`. A missing spot-check record
means the run is not complete.

### 段 2 — Project (grouped synthesis + thin merge)

Readers at this stage see **only the masked Markdown and the transcribe manifest** — never `raw/`,
never `raw/transcript/`, never page images.

Field merging is script-led (it reads frontmatter `fields[]`); narrative projection is LLM-led and is
fanned out **by `clinical_class` group** (labs / molecular+pathology / timeline+narrative /
open-fields+filing) with a thin merge worker, preserving anti-anchoring, failure isolation, and
per-step context ceilings.

Field merging is `scripts/merge_fields.py` → `raw/_provenance/<run_id>/field_candidates.json`; each
group worker reads only its own `class_group` slice. The four groups key on **`clinical_class`**
(parameter `class_group`): `labs` ← `lab`; `molecular_pathology` ← `molecular`, `pathology`;
`timeline_narrative` ← `narrative`, `imaging`; `open_fields_filing` ← `admin`, `unknown` plus the
filing of every `kind: novel` source.

Outputs: the known-slot JSON set (best-effort fill), `extracted_fields.json` for open key-values,
masked sidecars moved into `NN_` buckets or `15_未分类资料/<slug>/`, one `source_inventory` row per
content unit, `projection_coverage` in `readiness.json`, and `review_flags[]` each carrying
`audience` and `category`.

**`ocr/` is drained and deleted here.** It is transient 段 1 staging only. After the masked sidecars
are moved into their buckets, 段 2 removes the whole directory including `ocr/_inbox/` and
`ocr/_reports/`. **A completed archive contains no `ocr/`**; a non-empty `ocr/` at the end of the run
is an **ERROR** that lists the residual paths. This is also why `ocr/` is not a valid anchor prefix —
it does not exist when anchors are written.

### 段 3 — Gate and render (script-led, one pass, no retry loop)

Schema, anchors (the validator checks that the anchor's target sidecar exists and that the bbox is
well-shaped — **it never opens a page image**, so this is legality of shape, not proof that the span
resolves on the pixels), taxonomy v4 including the `15_` slug regex,
source-inventory completeness, `clinical_class`-driven molecular/lab completeness gates, numeric
integrity, PII shape floor, and untrusted-content markers. The PII semantic scan runs **one pass →
targeted masking per finding → rescan only the affected surfaces → one confirmation**; it is
fail-closed and is not downgraded to optional. Then deterministic template rendering with
`template_sha`, `AGENTS.md`, and the dated snapshot.

### Definition of done

- every source has **`raw/` bytes + a masked MD + a `source_inventory` row** (a conversation is not
  a source and gets a `conversation:<ISO8601>` anchor instead — never an inventory row);
- `projection_coverage` is quantified, and every `kind: unreadable` source appears in
  `summary.unreadable_sources`;
- every high-risk field carries a `high_risk_fields[]` entry with a `status` and a `reread_channel`
  (or a flag); `none` means "no channel existed", never `human`;
- **both** spot-check files exist under `raw/_provenance/<run_id>/` —
  `human_sample_plan.json` (script-written) and `human_sample_result.json` (human-written) — the
  result's `verdicts[]` covers every entry of the plan, and `mismatch < 2`;
- `ocr/` no longer exists;
- validator exits 0 and the HTML carries `template_sha256`;
- the PII semantic scan is clean (or an audited `deferred` per `pii-rescan-prompt.md`, which
  `export_share.py` independently refuses to export over).

## Clinical truth invariants

- `source_reported`, `patient_reported`, `caregiver_reported`, and `system_normalized` never overwrite
  each other.
- Source strings remain available. Validated normalization and translation are additive.
- Stage, ECOG, response, treatment line, laboratory values, molecular results, and clinician plan are
  copied only from attributable sources.
- Conflicts remain `disputed`; patient confirmation cannot clear them.
- Existing-document inventories do not recommend tests.
- Longitudinal observations are not response trajectories.
- Missing/failed extraction yields null and review flags, never a plausible value.
- **A high-risk field that has not passed a channel-independent second read or human spot-check does
  not enter any patient-facing confirmed-fact surface.**
- **`15_未分类资料/` is never an anchor target.** `source_refs[]` in the structured JSON set is
  restricted to `01_…14_` clinical-domain buckets (`schemas/anchor-contract.md`). An open field
  references its source through `extracted_fields.json`'s own
  `open_ref = {source_id, page, bbox}`, and **open fields do not enter any confirmed-fact surface.**
  `15_` is an open archive, not a citable clinical domain — `novel` still means "kept and declared",
  never "quarantined" and never auto-deleted.
- **`extracted_fields.json` is not a legal source store for charts or core-completeness.** The
  chart/summary stage renders known slots only; an open field never becomes a trend line and never
  satisfies a core-completeness requirement. Its role is to keep the projection honest, not to
  back-door unvalidated values into patient-facing output.

## Irreversible actions

No file is deleted on silence or model confidence. Quarantine and preview first; delete only after explicit,
item-specific confirmation and append an irreversible audit event. Corrections and superseded clinical
records remain versioned with immutable anchors.

## Canonical meaning

“Canonical file” means the current storage/contract location, not that its clinical content is correct.
Clinical validity is represented separately by source, provenance layer, verification status, and dispute
state.

## Output set

The patient directory contains the source inventory, raw vault (including the controlled
`raw/transcript/` verbatim layer), clinical-domain sidecars, the `15_未分类资料/` open archive,
schema-v2 JSON, `extracted_fields.json`, timeline, neutral record summary, review flags, document
gaps, update log, and deterministic HTML. All artifacts share one patient directory; `patient_code`
is a locator, not authentication.

## Host responsibilities

The host authenticates actors, enforces consent/authorization and revocation, handles concurrent writes,
encrypts storage/transport, manages retention, and prevents the skill from overriding platform safety.
Runtime bindings may differ in mechanism but must satisfy these invariants.
