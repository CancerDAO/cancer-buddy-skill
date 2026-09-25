# organize-regress fixtures (synthetic only)

This repository is public: everything under this directory is invented. Patient code,
dates (2029-2030), the institution name, regimen and drug names, lab values and every
sentence were made up for the tests. No real record, name, hospital, phone number or
record number may be added here — real archives are replayed only through the
`CB_REGRESS_CASES` environment variable of `tests/integration/organize-regress.sh`,
which copies them to a temporary directory and prints counts only. Do not copy or lightly
reword a real sentence, table layout or number sequence either: invent new wording, values,
dates and institutions. `tests/eval/lint/14-real-phrase-denylist.sh` checks this against a
private phrase list kept outside the repository (`CB_REAL_PHRASES_FILE`).

| Path | What it is |
|---|---|
| `make_syn_current.py` | Generator of the clean current-contract archive (readiness / timeline / labs … 2.1, patient_summary 2.2, source_inventory_v2.1, acute_findings / update_log v1) |
| `syn-current/src/` | Its committed output (the integration harness fails on drift). `AGENTS.md` is generated at test time by `fill_agents_md.py` |
| `syn-lab-columns/src/linear.txt` | Linear OCR text of an invented tumour-marker table with the column-interleaving failure shape (8 items / 8 results / 7 units / 7 ranges, arrow glyphs read as 小/个); the panel, order, ranges, values and layout were made up for this file |
| `synlib.py` | Test helpers: copy + mutate one thing, run the validator or one gate, derive the pre-v2.1 (legacy) variant. `make()` also writes `make_syn_current.EXTRACT_FILES` (the `raw/_extract` input the lab sidecar's `## 列配对` record names) into the copy, because the repository ignores every `raw/`; `make(..., with_raw=False)` leaves it out |
| `agents-md.template.d84b7eb.md` | The AGENTS.md template as shipped on `main` before this iteration (sha256 `8069660844a5…`), for the test that an AGENTS.md filled from an earlier shipped template is a WARN, not an ERROR |

Directory names avoid `raw/` and `patients/` (the root `.gitignore` would swallow them).
