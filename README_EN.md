# cancer-buddy

[中文](README.md) · [Install](INSTALL.md) · [Changelog](CHANGELOG.md)

A set of agent skills (for Claude Code and similar hosts) that helps people with cancer and their authorised family members:

- turn a pile of medical records (photos, PDFs, archives) into a traceable local archive;
- understand reports, prepare questions for appointments, chart lab trends;
- find hospitals and trial sites, check diet and supplement interactions, talk with family, prepare a second-opinion package, and share records with a stated purpose and expiry.

It explains the general picture — what a term means, what guidelines generally recommend — with live, cited sources. Decisions about the individual patient (response, next treatment, dose, prognosis) go back to the treating team, together with a clear list of questions.

## Modules

`cancer-buddy` (router + shared rules and scripts, required) · `organize` · `visit-prep` · `charts` · `education` · `nutrition` · `caregiver` · `disclosure` · `find-care` · `case-precedent` · `second-opinion` · `vault` · `web-access` (vendored third-party).

## Install

```bash
npx skills add CancerDAO/cancer-buddy-skill -g --all
```

Python ≥ 3.9. See [INSTALL.md](INSTALL.md).

## Example prompts

- "Organize the records in ~/Downloads/dad-scans."
- "Prepare questions for my follow-up next Wednesday."
- "How has my CEA changed?"
- "Can my mother take reishi spore powder with her targeted therapy?"

## Data and privacy

Archives live on your own machine (default `~/CancerDAO/patients/PT-XXXXXXXXXX/`, override with `CANCER_BUDDY_PATIENTS_DIR`). Originals are kept unmodified in `raw/`; transcripts mask names, ID numbers, phone numbers, addresses and record numbers. Record content is read by the AI service you use. Exports never include `raw/`, record recipient/purpose/expiry, and cannot be recalled once shared; anonymity is not promised.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Disclaimer

Information and navigation only. Not a medical device; no diagnosis or treatment advice. For emergencies (severe breathlessness, chest pain, confusion, heavy bleeding) go to the nearest emergency department.

MIT · CancerDAO
