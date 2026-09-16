# organize-gold — the transcription accuracy fixture

**This directory contains no real patient data, and never will.** It holds this README
and one fully synthetic worked example (`SYNTHETIC-example/`). The real gold standard is
assembled locally, from a de-identified copy, and is never committed.

## 1. Why this fixture exists

Every other test in `tests/` proves that organize v3 produces *well-formed* artifacts:
schemas validate, anchors resolve, the open domain cannot impersonate a pinned one, a
`passed_independent_reread` claim carries a channel. None of them proves the numbers are
**right**. A dropped decimal point, a swapped digit, a misread date and a page of phantom
glyphs all survive every structural gate, because the JSON stays perfectly well-formed.

The single recorded accuracy data point the v3 design rests on is anecdotal: one run, one
page of phantom characters, one misread date. That is not a measurement — it is a story.
This fixture turns it into a number, so a change to the transcription prompt, the page
DPI, the escalation thresholds or the host model can be judged as better or worse instead
of argued about.

## 2. Composition of the gold set

| part | size | why it is in the set |
|---|---|---|
| PT-84 s2–s4 | 39 pages | A real, ordinary multi-source archive: born-digital PDFs, scanner-OCR pages, and phone photos in one patient. It is the distribution the pipeline actually meets, not a curated easy case. |
| two known-misread pages | 2 pages | The pages that produced the phantom-glyph run and the misread date. A regression set whose only job is to stay fixed once fixed. |
| one out-of-scheme document | 1 document | Material no pinned 01_–14_ domain fits, so the set exercises the open domain: `kind: novel`, a model-written `15_` slug, `clinical_class` routing, and `extracted_fields.json` with its own `open_ref`. Without it the fixture would only ever measure closed-world performance. |

All of it is **de-identified before it is copied here**: no names, no 身份证, no 住院号,
no phone/email, no host-absolute paths, no upload filenames. De-identification is not the
same as anonymity, and this set is for local accuracy measurement only — it is not a
shareable corpus and must not be committed, exported, or attached to an issue.

## 3. Layout

```text
tests/fixtures/organize-gold/
├── README.md                    <- committed
├── eval_transcription.py        <- committed: the scorer (§5)
├── SYNTHETIC-example/           <- committed: one synthetic page, end to end
│   ├── make_fixture.py               generates the PDF (no binary in git)
│   ├── page-001.expected.frontmatter.yaml
│   └── notes.md
└── PT-84/                       <- LOCAL ONLY, gitignored, never committed
    ├── raw/incoming/<source>.pdf
    └── expected/
        └── <source_id>/
            └── page-NNN.expected.frontmatter.yaml
```

One annotation file per page, named after the page it annotates. The annotation lives
beside the page rather than in one big manifest so a single page can be re-annotated,
reviewed and diffed on its own.

## 4. Annotation format

`page-NNN.expected.frontmatter.yaml` is the **ground truth for that page's high-risk
fields**, in the same shape `ingest_transcripts.py` already validates, so the evaluator
compares like with like:

```yaml
source_id: s002
page: 1
text_layer_kind: absent          # what prepare_pages.py must decide, also scored
doc_kind: 检验报告
clinical_class: lab
fields:                          # ONLY the high-risk fields are ground-truthed
  - label: 白细胞计数
    value: "3.21"                # verbatim, as the page prints it
    unit: "10^9/L"
    high_risk_class: lab_value   # one of the 12 classes in high-risk-fields.md
  - label: 报告日期
    value: "2026-03-15"
    high_risk_class: date
full_text_tokens:                # for the recall metric (§5), not字段-level scoring
  - "白细胞计数"
  - "3.21"
  - "参考 3.50-9.50"
  - "[手写: 复查]"
known_defect: null               # or a short note for the two regression pages
```

Rules that keep the annotation honest:

- **Verbatim, not normalized.** `value` is the string the page prints. `12.4` and `12.40`
  are different answers; deciding they are the same is a scoring policy, declared in the
  evaluator, never smuggled into the truth file.
- **Only the 12 high-risk classes are ground-truthed** (9 universal + 3 oncology pack,
  `references/high-risk-fields.md`). Annotating every field on 39 pages costs days and
  measures the wrong thing: those are the fields where a slip is dangerous.
- **`full_text_tokens` is a spot-check list, not a transcript.** Tokens a complete
  transcription must contain — including paper elements an electronic text layer has no
  way to carry (`[手写: …]`, `[☑]`, `[圈: …]`, 章). It measures whether the full-text
  pass dropped content; it deliberately does not attempt a full-text diff.
- **A disputed page has no truth value.** If two human annotators disagree on what the
  page says, the field is recorded as `null` with a note, and the evaluator excludes it
  from the denominator. Guessing a truth value to keep the denominator round is how an
  accuracy number stops meaning anything.

## 5. Scoring a run against the gold set

The evaluator lives here: `eval_transcription.py`. It is deterministic, stdlib-only
(PyYAML is used when importable and a built-in subset parser otherwise), makes no network
call and runs no model — every comparison is a documented string operation.

```bash
python3 tests/fixtures/organize-gold/eval_transcription.py \
    tests/fixtures/organize-gold/PT-84/expected \
    <patient_dir> --json <out.json>
# the README convention `--gold … --run … --run-id … --report …` is accepted as an alias
```

It walks every `<gold_dir>/<source_id>/page-NNN.expected.frontmatter.yaml`, opens the
run's verbatim transcript for that same page at
`<patient_dir>/raw/transcript/<source_id>/page-NNN.md`, and compares them. The patient
directory may live anywhere on disk; nothing requires it to be inside `tests/`.

Three numbers, and they are reported separately on purpose — one blended score would let a
gain in the cheap one hide a loss in the dangerous one:

| metric | definition | why |
|---|---|---|
| **字段级准确率** field accuracy | exact-match high-risk field values ÷ ground-truthed high-risk fields, reported **per `high_risk_class`** | The headline number. Per-class because a 2% aggregate error is a different problem when it is all in `dose` than when it is all in `identifier`. |
| **漏报率** miss rate | ground-truthed high-risk fields absent from `fields[]` ÷ ground-truthed high-risk fields | A field the model never claimed is invisible to an accuracy score: it is not wrong, it is missing, and nothing downstream will ever ask for it. This is the number that made the metric split necessary. |
| **全文召回率** full-text recall | `full_text_tokens` found in the verbatim transcript ÷ total tokens | 段 1's own rule is 「MD 完整优先于字段完整」 — a field can be recovered later, a paragraph that was never transcribed is gone. Paper elements are counted here because they are exactly what a text-layer-only path silently loses. |

Reported alongside, never folded in: `text_layer_kind` classification accuracy (a
born-digital page misread as `absent` costs a free second read; an `embedded_ocr` page
misread as `born_digital` promotes a scanner's error to truth), the escalation rate, and
the cache hit rate.

**Interpretation floor.** These numbers describe transcription, not clinical correctness.
A 100% field accuracy says the characters were copied faithfully; it says nothing about
whether the report was right, and it never licenses dropping the channel-independent
second read for high-risk fields.

### 5.1 A worked run

Against `SYNTHETIC-example/` with a deliberately imperfect candidate transcription — the
`CEA` value misread `25.3` as `253` (the decimal point, the classic slip), and `PLT`
never emitted at all — so that every number below is non-trivial and hand-checkable:

```bash
python3 tests/fixtures/organize-gold/eval_transcription.py \
        tests/fixtures/organize-gold/SYNTHETIC-example \
        tests/fixtures/organize-gold/_candidate-run \
        --json tests/fixtures/organize-gold/_candidate-run/eval-report.json
```

`_candidate-run/` is gitignored like everything else here; it holds one candidate page so
this command reproduces, and a real invocation points the second argument at an actual
patient directory anywhere on disk. Verbatim output (0.06 s wall):

```text
==============================================================================
TRANSCRIPTION ACCURACY vs GOLD SET
==============================================================================
gold        : tests/fixtures/organize-gold/SYNTHETIC-example
candidate   : tests/fixtures/organize-gold/_candidate-run
pages       : 1 scored / 1 ground-truthed
class source: gold   taxonomy: imported from skills/cancer-buddy-organize/scripts/plan_second_read.py
value policy: verbatim after documented normalization (12.4 != 12.40)

(a) FIELD-LEVEL ACCURACY and (b) MISS RATE, by high-risk class (12 + `other`)
class               n_exp  match  wrong   miss  accuracy  miss rate
-------------------------------------------------------------------
date                    1      1      0      0   100.00%      0.00%
lab_value               4      2      1      1    50.00%     25.00%
reference_range         2      2      0      0   100.00%      0.00%
accession               1      1      0      0   100.00%      0.00%
-------------------------------------------------------------------
OVERALL                 8      6      1      1    75.00%     12.50%

(c) FULL-TEXT TOKEN RECALL (全文 spot-check tokens found in the candidate body)
tokens                  8 / 10                           80.00%

SIDE SIGNALS (reported alongside, never folded into the three numbers)
text_layer_kind         1 / 1                           100.00%
doc_kind                1 / 1                           100.00%
clinical_class          1 / 1                           100.00%

TAXONOMY DIAGNOSTIC (gold-declared class vs plan_second_read.py's keyword table)
  ground-truthed fields          : 8
  the keyword table classifies   : 2
  the keyword table MISSES       : 6  <- these would not enter the A11 deterministic denominator
      SYNTHETIC-example p001 'WBC' declared=lab_value
      SYNTHETIC-example p001 'WBC ref' declared=reference_range
      SYNTHETIC-example p001 'HGB' declared=lab_value
      SYNTHETIC-example p001 'PLT' declared=lab_value
      SYNTHETIC-example p001 'CEA' declared=lab_value
      SYNTHETIC-example p001 'CEA ref' declared=reference_range

DEFECTS (4)
  [missing] SYNTHETIC-example p001: [lab_value] 'PLT': expected '185', got None
  [wrong_value] SYNTHETIC-example p001: [lab_value] 'CEA': expected '25.3', got '253'
  [token_missing] SYNTHETIC-example p001: 全文 token '25.3' not found in the candidate body
  [token_missing] SYNTHETIC-example p001: 全文 token 'Reviewed by' not found in the candidate body

WHAT THESE NUMBERS CANNOT PROVE: they describe character-level transcription only.
They do not show the page was clinically correct, that a matched field means what its
label says, or that a field absent from the gold annotation was read right — only the
high-risk classes are ground-truthed. A 100% row never licenses skipping the
channel-independent second read.

JSON report written to tests/fixtures/organize-gold/_candidate-run/eval-report.json
```

Hand-check: 8 ground-truthed fields, 6 exact matches, 1 wrong value (`CEA`), 1 never
emitted (`PLT`) → 75.00% accuracy, 12.50% miss rate, both concentrated in `lab_value`
(2/4 = 50.00%, miss 1/4 = 25.00%). 10 spot-check tokens, of which `25.3` and
`Reviewed by` are absent from the body → 80.00% recall. `--strict` on the same run exits
3 and names all three breached thresholds.

**What the three numbers do and do not prove.** They prove the pipeline copied characters
off the page: a value that changed between the paper and `fields[].value` is now a number
rather than an anecdote, per class, so a prompt edit, a DPI change or a host-model swap
can be judged instead of argued about. They prove nothing clinical — a page transcribed at
100% can still be a wrong report, and the metric has no opinion about that. They say
nothing about any field outside the annotation, since only the 12 high-risk classes are
ground-truthed and the `other` tier only ever collects ground-truthed fields no class
claimed. They say nothing about a field the gold set records as disputed (`value: null`),
which leaves the denominator rather than getting a guessed truth value. And a perfect row
never licenses dropping the channel-independent second read: the evaluator only sees what
the pipeline wrote down, so it can confirm a transcription is faithful but never that one
reading was enough.


## 6. `SYNTHETIC-example/`

One page, fully synthetic, generated by `make_fixture.py` (the PDF is generated, not
committed, so no binary enters git). It exists so the annotation format and the evaluator
contract can be exercised — and reviewed — without any real archive present. It is a
worked example of the format, not a benchmark: one synthetic page measures nothing.
