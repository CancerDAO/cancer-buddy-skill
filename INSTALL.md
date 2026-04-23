# Installation

## Requirements

- Claude Code (latest). Get it from https://claude.ai/code.
- Python 3.9+ (for OCR tools used by the `cb-organizer` subagent).
- `pdftotext` (part of poppler-utils) for PDF extraction:
  - macOS: `brew install poppler`
  - Debian/Ubuntu: `sudo apt install poppler-utils`
- `pytesseract` for image OCR: `pip install pytesseract`
- Tesseract OCR engine:
  - macOS: `brew install tesseract tesseract-lang`
  - Debian/Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim`

## Install the plugin

### Global (recommended)

```
cd ~/.claude/plugins
git clone https://github.com/CancerDAO/cancer-buddy-skill
```

### Project-scoped

```
cd <your-project>/.claude/plugins
git clone https://github.com/CancerDAO/cancer-buddy-skill
```

Restart Claude Code after install.

## Optional: install vmtb-skill for full MTB

```
cd ~/.claude/plugins
git clone https://github.com/zwbao/vmtb-skill
```

After install, when you run MTB through cancer-buddy, you'll be asked whether to use the lite (2-5 min, built into cancer-buddy) or full (15-20 min, via vmtb-skill) version.

## Verify

In Claude Code, type:
```
抗癌搭子
```

The meta-skill should respond. If nothing happens, check:
1. `ls ~/.claude/plugins/cancer-buddy-skill/skills/cancer-buddy/SKILL.md` — does the file exist?
2. Claude Code version — older versions may not pick up plugins automatically.
3. Run `bash ~/.claude/plugins/cancer-buddy-skill/scripts/validate-plugin.sh` — any errors?

## Update

```
cd ~/.claude/plugins/cancer-buddy-skill && git pull
```

## Uninstall

```
rm -rf ~/.claude/plugins/cancer-buddy-skill
```

Your `patients/` directory is not touched — back it up or move it first if you want to preserve it.
