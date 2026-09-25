# Installation

## Install all Cancer Buddy skills

```bash
npx skills add CancerDAO/cancer-buddy-skill -g --all
```

Project-local installation:

```bash
npx skills add CancerDAO/cancer-buddy-skill --all
```

The package contains the router, ten patient-support companions, and the bundled `web-access` retrieval layer. Restart the host after installation if it caches available skills.

## Selective installation

If you install only `cancer-buddy-find-care`, include `web-access` or provide another supported live-web tool. Without live access, find-care must report that it cannot verify current resources; it must not return a list from model memory.

```bash
npx skills add CancerDAO/cancer-buddy-skill
```

Use the installer's selection UI to choose skills. No Cancer Buddy workflow automatically installs another repository or executes `npx` on the user's behalf.

## Optional external tools

Clinical-trial matching is not part of this repository. A separately installed tool may help structure protocol criteria, but its output is not proof of eligibility. The research site must review the current protocol, amendments, disease status, labs, medications, timing and source records.

Likewise, virtual MTB or other clinical-decision tools are outside the public Cancer Buddy scope. Cancer Buddy may organize records and questions for a qualified treating team; it does not generate a substitute decision report.

## Record organization: the OCR second-read engine

`cancer-buddy-organize` transcribes photos and scanned pages with the host model and has a deterministic OCR engine read
every page a second time. Check which engine this host offers:

```bash
python3 skills/cancer-buddy-organize/scripts/run_ocr_engine.py which
```

- `apple_vision` — macOS with the Xcode command-line tools (`swiftc`): the bundled `scripts/vision_ocr.swift` is compiled
  on first use and cached in `~/.cache/cancer-buddy-organize/` (override with `CB_ORGANIZE_CACHE_DIR`). Preferred.
- `tesseract` — **WARN**: works (`chi_sim` + `eng` language data), but reads fewer printed Chinese characters correctly, so
  more high-risk fields end up as single-channel reads. Install the command-line tools on macOS to get `apple_vision`.
- no engine (exit 3) — organize still runs, but every high-risk field is a single-channel read (no independent second
  read); install one of the two before organizing real records.

PDF page typing uses PyMuPDF when importable, else poppler (`pdfinfo`, `pdffonts`, `pdfimages`, `pdftotext`).

## Verify

```bash
bash tests/eval/run.sh
for test in tests/unit/*.sh tests/integration/*.sh; do bash "$test"; done
```

For help, open an issue at the [CancerDAO repository](https://github.com/CancerDAO/cancer-buddy-skill).
