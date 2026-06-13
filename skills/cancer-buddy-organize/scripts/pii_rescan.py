#!/usr/bin/env python3
"""pii_rescan.py — deterministic PII residue gate on Phase-1 LLM sidecars.

The Phase-1 LLM Markdown ingestion worker masks PII into the literal token `[PII_MASKED]` as a
per-line *semantic* judgement (organizer-prompt-phase1-ocr.md §2.4). That LLM
pass is the primary redactor — but a single LLM pass can miss a phone number on
a busy lab footer or a 身份证号 buried in a discharge header. The sidecar MD is
the **single downstream plaintext boundary** (timeline / case_text / profile /
段D HTML all read the MD and NEVER re-read the original source file), so any
plaintext PII that survives in an MD leaks all the way through.

This script is the **门** that runs AFTER the worker writes sidecars and BEFORE
Phase 2 consumes them. It does NOT rely on the LLM's self-report (`## PII`
trailer) — it independently rescans the *body text* of every sidecar with a
small deterministic PII-pattern family and flags any line that still looks like
it carries plaintext PII. It never performs OCR.

Scope (matches phase1-ocr.md §2.4 — "touches PII tokens ONLY"):
  - Only the OCR body is scanned. The `SOURCE:`/`ORIGINAL:` header and the
    `## PII` trailer are metadata, not clinical content — skipped.
  - A line is skipped once its PII value has already been replaced by
    `[PII_MASKED]` (i.e. label present but value is the mask → clean).
  - Clinical fidelity wins: this gate flags label+value PII shapes and
    standalone identifiers. It does NOT flag clinical dates, lab
    values, drug names, TNM, or molecular markers — those carry no PII regex
    signature and are left untouched (anti-anchoring §2.2a unaffected).
  - Multi-locale: the detector runs an UNCONDITIONAL union of zh + en field
    labels (姓名/患者姓名/patient name, 身份证/MRN/SSN, 电话/phone/mobile, …) plus
    locale-agnostic standalone shapes (中国身份证/手机/座机 + email + US-SSN +
    international/E.164 phone). A residue gate must over-detect, so patterns fire
    regardless of the run's locale rather than being gated to one language. Latin
    single-word labels (phone/cell/born/bed/address) require a real colon so they
    do not false-fire on ordinary English prose ("cell count", "bed rest").

This is a *detector*, not an auto-rewriter: medical-record redaction is a
judgement task (phase1-ocr.md §2.4 — "not a fixed regex list"), so the fix is
made by the agent re-reading the flagged line in context and re-masking, then
re-running this gate until it passes. A regex auto-replace here would risk
eating a clinical character adjacent to the matched span.

Usage:
    python3 scripts/pii_rescan.py <patient_dir_or_sidecar_dir_or_file> [...]

If given a directory, every `*.md` under `<dir>/ocr/` is scanned (the Phase-1
central staging dir); if `<dir>/ocr/` does not exist, every `*.md` under the
buckets `01_…14_` is scanned (post-Phase-2 co-located sidecars). A direct path
to a single `.md` file scans just that file.

OCR frequently splits a PII label and its value across two adjacent lines (the
label at the tail of one line, the bare number at the head of the next). Each
file is therefore scanned line-by-line AND with a sliding 2-line join, so a
`住院号：` / `0001234567` straddle is still caught. A value already masked to
`[PII_MASKED]` is never flagged.

Output: human-readable findings to stderr; a one-line machine summary to stdout:
    PII_RESCAN: files=<N> clean=<N> with_residue=<N> findings=<N>

Exit codes:
    0  — no residue found (gate PASSES — safe to proceed to Phase 2)
    1  — at least one plaintext-PII residue found (gate FAILS — re-mask + re-run)
    2  — bad invocation / nothing to scan
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MASK_TOKEN = "[PII_MASKED]"

# --- separators -------------------------------------------------------------
_SEP = r"\s*[:：\s]\s*"

# Colon-MANDATORY separator for single-word Latin labels (phone/cell/born/bed/
# address/name). These Latin labels are short, common words that also appear in
# ordinary clinical prose ("cell count", "born in 1950", "bed rest"); requiring a
# real colon prevents the space-tolerant _SEP from false-firing on English text.
_SEP_COLON = r"\s*[:：]\s*"

# A "value" that still looks like plaintext PII (NOT already the mask token and
# not empty). We deliberately keep this loose — any non-trivial run of chars
# after a PII label that is not the mask token is suspicious.
#   - rejects: "" (empty), lines where the very next thing is the mask token
#   - the per-line skip for `[PII_MASKED]` is handled separately below
_PII_LABEL_PATTERNS = [
    # patient_name: only the unambiguous FIELD labels (患者姓名 / 姓名). Bare 患者 / 病人
    # are excluded — they are ordinary clinical-prose words ("患者神志清", "病人诉…"),
    # not name-field labels, and including them false-fires on normal records.
    (re.compile(r"(患者姓名|姓\s*名)" + _SEP + r"(\S)"), "patient_name"),
    (re.compile(r"(身份证号?码?|证件号码?|护照号?码?)" + _SEP + r"(\S)"), "id_number"),
    (re.compile(r"(电\s*话|联系电话|手\s*机|联系方式|Tel|TEL)" + _SEP + r"(\S)"), "phone"),
    (re.compile(r"(地\s*址|住\s*址|家庭地址|通讯地址|联系地址)" + _SEP + r"(\S)"), "address"),
    (re.compile(r"(住院号|住院病历号|病历号|门诊号|就诊号|就诊卡号|病案号|报告单号|卡号|ID号)" + _SEP + r"(\S)"), "admission_id"),
    (re.compile(r"(床\s*号|病\s*床|床\s*位)" + _SEP + r"(\S)"), "bed_number"),
    (re.compile(r"(出生日期|出生年月)" + _SEP + r"(\S)"), "birth_date"),
    # --- English / Latin field labels (multi-locale safety net; colon-mandatory
    #     via _SEP_COLON to avoid false-firing on ordinary English prose) --------
    (re.compile(r"(?i)(patient\s*name|pt\.?\s*name|full\s*name|given\s*name|family\s*name|surname)" + _SEP_COLON + r"(\S)"), "patient_name"),
    (re.compile(r"(?i)(mrn|medical\s*record\s*(?:no\.?|number|#)|patient\s*id|account\s*(?:no\.?|number|#)|ssn|social\s*security(?:\s*(?:no\.?|number))?|passport(?:\s*(?:no\.?|number|#))?)" + _SEP_COLON + r"(\S)"), "id_number"),
    (re.compile(r"(?i)(phone|mobile|cell(?:\s*phone)?|telephone|fax|contact\s*(?:no\.?|number)?)" + _SEP_COLON + r"(\S)"), "phone"),
    (re.compile(r"(?i)(address|addr|residence|home\s*address)" + _SEP_COLON + r"(\S)"), "address"),
    (re.compile(r"(?i)(admission\s*(?:no\.?|number|id)|encounter\s*(?:no\.?|id)|visit\s*(?:no\.?|id)|chart\s*(?:no\.?|number))" + _SEP_COLON + r"(\S)"), "admission_id"),
    (re.compile(r"(?i)(bed(?:\s*(?:no\.?|number|#))?|ward(?:\s*(?:no\.?|number))?)" + _SEP_COLON + r"(\S)"), "bed_number"),
    (re.compile(r"(?i)(date\s*of\s*birth|d\.?o\.?b\.?|birth\s*date|born)" + _SEP_COLON + r"(\S)"), "birth_date"),
]

# Label-only patterns (label, then a REQUIRED trailing colon, then END of line) —
# used for cross-line detection where the value spills onto the next line. The
# colon is MANDATORY: a cross-line straddle only counts when the previous line ends
# with a real field label like `住院号：` / `姓名：`. Without this, an ordinary
# clinical line ending in a noun (e.g. "…既往体健患者") followed by a line starting
# with 2–4 汉字 ("双肺纹理清晰") was being mis-flagged as a name straddle and the gate
# failed on clean records. Keyed to the same category set as _PII_LABEL_PATTERNS.
_TAIL_SEP = r"\s*[:：]\s*$"
_PII_LABEL_TAIL = [
    (re.compile(r"(患者姓名|姓\s*名)" + _TAIL_SEP), "patient_name"),
    (re.compile(r"(身份证号?码?|证件号码?|护照号?码?)" + _TAIL_SEP), "id_number"),
    (re.compile(r"(电\s*话|联系电话|手\s*机|联系方式|Tel|TEL)" + _TAIL_SEP), "phone"),
    (re.compile(r"(地\s*址|住\s*址|家庭地址|通讯地址|联系地址)" + _TAIL_SEP), "address"),
    (re.compile(r"(住院号|住院病历号|病历号|门诊号|就诊号|就诊卡号|病案号|报告单号|卡号|ID号)" + _TAIL_SEP), "admission_id"),
    (re.compile(r"(床\s*号|病\s*床|床\s*位)" + _TAIL_SEP), "bed_number"),
    (re.compile(r"(出生日期|出生年月)" + _TAIL_SEP), "birth_date"),
    # English / Latin labels (colon already mandatory via _TAIL_SEP)
    (re.compile(r"(?i)(patient\s*name|pt\.?\s*name|full\s*name|given\s*name|family\s*name|surname)" + _TAIL_SEP), "patient_name"),
    (re.compile(r"(?i)(mrn|medical\s*record\s*(?:no\.?|number|#)|patient\s*id|account\s*(?:no\.?|number|#)|ssn|social\s*security(?:\s*(?:no\.?|number))?|passport(?:\s*(?:no\.?|number|#))?)" + _TAIL_SEP), "id_number"),
    (re.compile(r"(?i)(phone|mobile|cell(?:\s*phone)?|telephone|fax|contact\s*(?:no\.?|number)?)" + _TAIL_SEP), "phone"),
    (re.compile(r"(?i)(address|addr|residence|home\s*address)" + _TAIL_SEP), "address"),
    (re.compile(r"(?i)(admission\s*(?:no\.?|number|id)|encounter\s*(?:no\.?|id)|visit\s*(?:no\.?|id)|chart\s*(?:no\.?|number))" + _TAIL_SEP), "admission_id"),
    (re.compile(r"(?i)(bed(?:\s*(?:no\.?|number|#))?|ward(?:\s*(?:no\.?|number))?)" + _TAIL_SEP), "bed_number"),
    (re.compile(r"(?i)(date\s*of\s*birth|d\.?o\.?b\.?|birth\s*date|born)" + _TAIL_SEP), "birth_date"),
]

# Standalone high-precision identifiers (no label needed). Locale-agnostic by
# shape — these fire on any record regardless of language.
_STANDALONE = [
    (re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"), "id_number"),  # 中国身份证 18-digit
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "phone"),                # 中国手机
    (re.compile(r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)"), "phone"),      # 中国座机
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "email"),                # email (any locale)
    (re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"), "id_number"),      # US SSN shape
    (re.compile(r"(?<![\w+])\+\d[\d\s().-]{6,}\d"), "phone"),          # E.164 / international (must start with +)
    (re.compile(r"(?<!\d)\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"), "phone"),  # US 10-digit w/ separators
]


def _value_after_label_is_masked(line: str, m: re.Match) -> bool:
    """True if the value region after the label is already the mask token (label
    present but value masked → *clean* line, not residue).

    Handles Markdown table cells where the label and value are separated by `|`:
    `| 患者姓名 | [PII_MASKED] |` — the captured `\\S` after the label sep is the
    `|` pipe, so we strip leading separators/pipes before checking the mask."""
    # group(2) is the first non-space char of the value region.
    val_start = m.start(2)
    tail = line[val_start:].lstrip()
    # strip a Markdown table-cell delimiter run (`|`) + surrounding space
    tail = re.sub(r"^\|\s*", "", tail)
    return tail.startswith(MASK_TOKEN)


def scan_line(line: str) -> list[tuple[str, str]]:
    """Return list of (pii_type, matched_snippet) for residue on this line."""
    findings: list[tuple[str, str]] = []
    stripped = line.strip()
    if not stripped:
        return findings

    # Label + plaintext value
    for pattern, pii_type in _PII_LABEL_PATTERNS:
        for m in pattern.finditer(line):
            if _value_after_label_is_masked(line, m):
                continue
            snippet = line[m.start(): min(len(line), m.start() + 24)].strip()
            findings.append((pii_type, snippet))

    # Standalone identifiers (skip if the match sits inside a mask token region —
    # it never will, the mask token has no digits, but guard anyway)
    for pattern, pii_type in _STANDALONE:
        for m in pattern.finditer(line):
            findings.append((pii_type, m.group(0)))

    return findings


# A value at the HEAD of the next line that looks like plaintext PII (digit run,
# id-ish token, a CJK name, a capitalised Latin name, or an email). Not the mask
# token, not a markdown delimiter. Only consulted AFTER a PII label tail matched
# the previous line (scan_cross_line), so the broad Latin-name arm cannot
# false-fire on ordinary sentence-initial capitalisation.
_NEXTLINE_VALUE_RE = re.compile(
    r"^\s*(?!\[PII_MASKED\])(\|?\s*)"
    # digit-run / CJK name / Latin name (any case, incl. Latin-1 accents like Müller) / email
    r"([0-9][0-9A-Za-z\-]{1,}|[一-龥]{2,4}|[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.\-]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ'.\-]+)?|[\w.+-]+@[\w-]+\.[\w.-]+)"
)


def scan_cross_line(prev_line: str, next_line: str) -> list[tuple[str, str]]:
    """Detect a PII label at the tail of prev_line whose value spills onto the
    head of next_line. Returns (pii_type, snippet) findings."""
    findings: list[tuple[str, str]] = []
    # strip a trailing markdown table pipe so `| 住院号 |` still matches as a tail
    prev_for_match = re.sub(r"\|\s*$", "", prev_line.rstrip())
    vm = _NEXTLINE_VALUE_RE.match(next_line)
    if not vm:
        return findings
    for pattern, pii_type in _PII_LABEL_TAIL:
        if pattern.search(prev_for_match):
            snippet = (prev_line.strip()[-12:] + " ⏎ " + next_line.strip()[:16]).strip()
            findings.append((pii_type, snippet))
            break
    return findings


def scan_sidecar(path: Path) -> list[tuple[int, str, str]]:
    """Scan one MD sidecar's BODY (skip header + `## PII` trailer).

    Returns list of (line_no_1based, pii_type, snippet)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # unreadable sidecar is itself a finding-worthy state
        return [(0, "unreadable", str(e))]

    lines = text.splitlines()
    in_pii_trailer = False
    results: list[tuple[int, str, str]] = []
    prev_body: tuple[int, str] | None = None  # (line_no, text) of last body line
    for i, line in enumerate(lines, start=1):
        # Skip the SOURCE/ORIGINAL header lines (metadata, not OCR body)
        if line.startswith("SOURCE:") or line.startswith("ORIGINAL:"):
            continue
        # `## PII` trailer is metadata — stop scanning the body once we hit it
        if re.match(r"^##\s+PII\b", line):
            in_pii_trailer = True
            continue
        if in_pii_trailer:
            continue
        # per-line label+value and standalone identifiers
        for pii_type, snippet in scan_line(line):
            results.append((i, pii_type, snippet))
        # cross-line: PII label at tail of previous body line, value at head of
        # this line (only fires when the value is not already masked / per-line).
        if prev_body is not None:
            for pii_type, snippet in scan_cross_line(prev_body[1], line):
                results.append((i, f"{pii_type}(cross-line)", snippet))
        prev_body = (i, line)
    return results


def collect_sidecars(target: Path) -> list[Path]:
    if target.is_file() and target.suffix.lower() == ".md":
        return [target]
    if not target.is_dir():
        return []
    ocr_dir = target / "ocr"
    if ocr_dir.is_dir():
        return sorted(ocr_dir.glob("*.md"))
    # post-Phase-2: sidecars co-located in NN_ buckets
    buckets = sorted(target.glob("[0-9][0-9]_*"))
    out: list[Path] = []
    for b in buckets:
        if b.is_dir():
            out.extend(sorted(b.rglob("*.md")))
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: pii_rescan.py <patient_dir|sidecar_dir|sidecar.md> [...]", file=sys.stderr)
        return 2

    sidecars: list[Path] = []
    for arg in argv[1:]:
        sidecars.extend(collect_sidecars(Path(arg).resolve()))

    # de-dup preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for s in sidecars:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    sidecars = uniq

    if not sidecars:
        print("ERROR: no .md sidecars found to scan", file=sys.stderr)
        return 2

    total_findings = 0
    files_with_residue = 0
    for sc in sidecars:
        findings = scan_sidecar(sc)
        if findings:
            files_with_residue += 1
            total_findings += len(findings)
            print(f"\nRESIDUE: {sc}", file=sys.stderr)
            for line_no, pii_type, snippet in findings:
                loc = f"L{line_no}" if line_no else "(file)"
                print(f"  {loc}  [{pii_type}]  {snippet!r}", file=sys.stderr)

    clean = len(sidecars) - files_with_residue
    print(
        f"PII_RESCAN: files={len(sidecars)} clean={clean} "
        f"with_residue={files_with_residue} findings={total_findings}"
    )

    if total_findings:
        print(
            "\nGATE FAILED: plaintext PII residue survived Phase-1 redaction. "
            "Re-read each flagged line in context, mask the PII token(s) to "
            f"{MASK_TOKEN} (clinical chars untouched — §2.2a / §2.4), and re-run "
            "this gate until it reports findings=0 BEFORE proceeding to Phase 2.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
