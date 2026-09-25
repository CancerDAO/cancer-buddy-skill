# Cancer Buddy

Cancer Buddy is a non-clinical navigation skill for people affected by cancer and authorized caregivers. It organizes records, explains stable concepts, looks up and explains — with sources — what current authoritative guidelines / standard care generally say, prepares visit questions, discovers public resources, and builds source-traceable packets. It does not diagnose, restage, infer ECOG/response/progression/prognosis, or choose treatment for you personally.

## Modules

| Module | Purpose | Boundary |
|---|---|---|
| `cancer-buddy-organize` | Provenance-preserving record organization; lists source-worded acute findings first, checks missing pages and record recency, keeps every read channel's raw reading for uncertain fields; lab-column pairing and lexicon candidates are computed by scripts and re-checked by the acceptance gate (a missing core file, missing jsonschema or an unrecorded semantic PII scan means the run is not done) | No inferred stage, response, ECOG, progression, treatment line, or test indication; flag severity grades extraction/archive uncertainty, not clinical severity |
| `cancer-buddy-visit-prep` | Snapshot, bring-list, and questions | Questions only |
| `cancer-buddy-education` | Patient education | Version-sensitive claims require answer-time verification against a current primary source and fail closed |
| `cancer-buddy-nutrition` | Symptom-directed food education and interaction verification | No automatic cancer/phase-based prescription |
| `cancer-buddy-caregiver` | Visit logistics, family roles, child communication | Family relationship is not record authority |
| `cancer-buddy-disclosure` | Information-preference and communication support | No model capacity determination or maintained deception |
| `cancer-buddy-find-care` | Official institutions, clinicians, services, and trial sites | Unranked resources; no quality recommendation or eligibility decision |
| `cancer-buddy-case-precedent` | Case-report retrieval | Complete outcomes and differences; no similarity score, treatment direction, or prognosis |
| `cancer-buddy-second-opinion` | Source summary, index, questions, and send checklist | Live logistics verification; no automatic transmission |
| `cancer-buddy-vault` | Local inventory, permissions, export, and audit workflow | Host authentication required; patient code is not authorization |
| `cancer-buddy-charts` | Printable static charts of the patient's own labs, treatment, molecular and coverage data | Renders only values already in the source report; no trend interpretation, no response/prognosis verdict; no data means no chart |

The repository also includes the `cancer-buddy` router and the `web-access` retrieval layer.

## Clinical safety model

- Preserve every source clinical string. Validated normalization and patient-language translation are additive, labeled layers; they never silently replace the source.
- Keep `source_reported`, `patient_reported`, `caregiver_reported`, and `system_normalized` data separate.
- Do not derive RECIST/response/progression from imaging, markers, or symptoms; do not infer ECOG or treatment line.
- Guidelines, labels, interactions, trials, institutions, laws, and prognosis figures require current primary-source verification. If verification fails, version-sensitive detail is withheld rather than reconstructed from model memory.
- Laboratory display uses the exact result's unit, reference range, report flag, and critical flag. Code does not assign clinical severity. Lab tables are paired column by column: values matched only by position are labeled unverified candidates, and a table whose item and result counts differ is not paired at all.
- When an imaging, lab or clinical report itself states a thrombus, fracture, increasing effusion, suspected drug-induced pneumonitis or a critical value, the organized archive lists that text, its date and source first and suggests telling the treating team soon; the organizer does not grade severity or advise management. A small or unquantified effusion or a follow-up suggestion is still listed, without escalation; contact bleeding at endoscopy, pathology sign-off boilerplate and germline-testing disclaimers are not findings. A report's "new" is recorded as comparison wording and never escalates a class such as suspected pneumonitis; the list is written on every run, including a partial rerun on an older archive.
- All cycles of one regimen are one treatment episode — a cycle number is not a treatment line — and ongoing treatment is stated with its basis (administration record, the current clinician note, an imaging-request indication or a family statement); an undated family statement is labeled as such, never given a borrowed date.
- Photos and scanned pages without a text layer are transcribed page by page by the host model; that transcription is the body. A script then has a deterministic OCR engine (Apple Vision on macOS, else tesseract) read every page a second time and aligns the key fields — dates, values, stages, drug names — character by character: agreement is not marked; an engine that read nothing usable there ("no signal") leaves a single-channel read without a flag; only a clear, different engine reading marks the field for review. Engine text never enters the body, and the model looking at its own image again is never a second read. Born-digital PDFs use their text layer as is, with no OCR.
- Uncertain fields keep each read channel's raw reading; lexicon candidates are possible readings only and never replace the source. An uncertainty mark covers only its own characters — what is read clearly on the same line is recorded as usual. The diagnosis is taken verbatim from the first source on the ladder pathology > discharge/clinic diagnosis > order or imaging indication > the clinical-diagnosis box of a genomic report, and the one-line condition always states it (or says the diagnosis is missing).
- Organizing records is one long task (about one to two hours): until the closing acceptance gate passes, the run does not end the conversation with an interim summary — acute-finding notices and summaries go out together with the next step. The skill's own files are read-only during a run: a skill defect is reported, never patched in place, and the closing gate checks that the skill files match the ones the run started with. Runtime bindings cover Claude Code, headless Codex and grok. Every transcript carries a fixed provenance header (document type, read channels, independent reread, original's hash) that the acceptance gate checks against the source inventory, and only worker subagents write the archive — the orchestrator never writes it by hand.
- An archive organized before this contract is fully re-transcribed once from its stored originals the first time new records are added (`legacy_upgrade`); the previous output is kept in the originals vault under `raw/_legacy_<timestamp>/`, never deleted, and no file is upgraded piecemeal; the acceptance gate reports an archive whose outputs were rewritten but whose records were never re-transcribed under the new format. The closing gate (`--final`) also requires the review summary, index, timeline, case text and case summary, a recorded faithfulness check, and echoes the case summary's template fingerprint. When a later run registers a new tell-the-team-soon finding before the case summary is regenerated, the user is asked whether to regenerate it (the old summary records which acute-findings version it read, so it counts as stale, not as an omission). Clean-up removes only the temp directory an archive was unpacked into; the user's input folder and the `raw/` originals vault are never removed. An invitation to add an existing document is made at most twice and never again once declined.
- A prior-archive digest, used only with the user's explicit permission, is history only: its performance scores and treatments never become current status. An HLA result that states only 杂合/纯合 (heterozygous/homozygous) without an allele records that typing was done and is not used for trial matching.
- Platform-level self-harm/suicide safety remains the responsibility of the host LLM; this skill does not add a competing path.

See [`references/clinical-content-governance.md`](references/clinical-content-governance.md).

## Install

```bash
npx skills add CancerDAO/cancer-buddy-skill -g --all
# or project-local
npx skills add CancerDAO/cancer-buddy-skill --all
```

See [INSTALL.md](INSTALL.md). Cancer Buddy does not automatically install or invoke another clinical skill at runtime. Any separate trial-matching tool remains subject to current-protocol review by the research site.

## Data and authorization

The default patient-root chain is:

```text
$CANCER_BUDDY_PATIENTS_DIR
→ $VMTB_PATIENT_DATA_ROOT
→ $HOME/CancerDAO/patients
```

Patient codes are random storage locators, not credentials. Originals remain in access-controlled `raw/`; derived sidecars and delivered surfaces are text-masked and minimized but may remain re-identifiable. Patient-specific access and export require host authentication and explicit, purpose-limited, revocable authorization.

## Test

```bash
bash tests/eval/run.sh
for test in tests/unit/*.sh tests/integration/*.sh; do bash "$test"; done
```

This tool supports organization, education, and communication preparation. It is not medical advice. For acute dangerous symptoms, follow the treating team's instructions or seek local emergency care.

License: [MIT](LICENSE). Project: [CancerDAO](https://github.com/CancerDAO).
