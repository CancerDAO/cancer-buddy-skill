#!/usr/bin/env python3
"""_high_risk_spans.py — the one authority on which strings of a sidecar body are high-risk spans,
and on how two readings of one span are compared (organizer-prompt-phase1-ocr.md §5).

A span is a place in the model transcription (the sidecar body) that the deterministic second read
must look at: a date, a number with its unit, a table cell holding a number or a reference range, a
TNM / stage string, a cycle number, a drug / IHC-marker / lymph-node-station lexicon hit, and the
connector between two drug names. The worker cannot shrink this list; it may only ADD spans the
patterns cannot see (a diagnosis, an institution, a drug outside the lexicon, an `[不可读]` region, a
layout anomaly) through raw/_extract/<stem>.declared.json.

Comparison is class-specific and fails toward "no signal", never toward a false conflict:

  * normalisation: NFKC, case fold, İ/ı → i, × → x, whitespace removed; `×10⁹/L`, `x109/L`,
    `10°9/L`, `10^9/L` are one unit; dates compare as YYYY-MM-DD (2026-0707 = 2026-07-07);
    numbers keep the decimal point (11.5 ≠ 115) and drop only thousands separators;
  * no signal: nothing aligned, engine confidence under NO_SIGNAL_BELOW, similarity < 0.5,
    a reading that is not grammatical for its class (a date that is no date, a TNM string that is
    not TNM, a number span without a digit, a connector that is not + / -), an engine reading that
    only lost some non-numeric glyphs of the transcription (non-numeric classes), or a lexicon
    near-miss (the transcription is a lexicon line, the engine reading is not, distance ≤ 1);
  * conflict: a confident, grammatical engine reading that differs from the transcription.

Pure functions only (no I/O except lexicon loading); second_read_align.py and the validator import
them, so the worker, the script and the gate share one definition.
"""
from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
LEXICON_DIR_ENV = "CB_ORGANIZE_LEXICON_DIR"
LEXICON_CLASSES = {"drug_name": "oncology_drugs", "ihc_marker": "ihc_markers", "ln_station": "ln_stations"}

# engine confidence below which a reading is "no signal" (FIX_PLAN A16: tesseract word conf 0-100,
# Apple Vision observation confidence 0-1). Pinned here; tune only with a re-run on real archives.
NO_SIGNAL_BELOW = {"tesseract": 50.0, "apple_vision": 0.5}
DEFAULT_NO_SIGNAL_BELOW = 0.5
SIMILARITY_FLOOR = 0.5

# value-class conflicts grade red; a diagnosis_text conflict grades yellow (phase2 §6.1)
VALUE_CLASSES = ("date", "number", "unit", "stage", "drug_name", "ihc_marker", "ln_station", "variant",
                 "regimen_connector", "cycle_number")

# the appendix headings a sidecar body ends at (phase1 §4 G); a transcribed `## …` heading of the
# document itself is body text
APPENDIX_HEADINGS = ("高风险字段复读", "文本层字形异常", "列配对", "不确定字段", "PII")
_APPENDIX_RE = re.compile(r"^##\s+(" + "|".join(APPENDIX_HEADINGS) + r")\b")
TOKEN_RE = re.compile(r"\[OCR_UNCERTAIN:U-\d{3,}\]")
MASK = "[PII_MASKED]"
UNREADABLE = "[不可读]"

# ---------------------------------------------------------------- sidecar layout

_HEADER_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*):(?:\s|$)")


def header_length(lines: list[str]) -> int:
    """Leading `KEY: value` lines (the pinned header block)."""
    n = 0
    for line in lines:
        if not _HEADER_LINE_RE.match(line):
            break
        n += 1
    return n


def body_bounds(lines: list[str]) -> tuple[int, int]:
    """(first, end) 0-based line indexes of the body: after the header block and its blank line, up
    to the first appendix heading (or the end)."""
    n = header_length(lines)
    first = n + 1 if n < len(lines) and not lines[n].strip() else n
    end = len(lines)
    for i in range(first, len(lines)):
        if _APPENDIX_RE.match(lines[i]):
            end = i
            break
    return first, end


def strip_tokens(s: str) -> str:
    return TOKEN_RE.sub("", s)


def body_text(sidecar_text: str) -> str:
    """The body with every [OCR_UNCERTAIN:U-nnn] removed — what body_sha256 hashes."""
    lines = sidecar_text.splitlines()
    a, b = body_bounds(lines)
    return strip_tokens("\n".join(lines[a:b]))


# ---------------------------------------------------------------- lexicons

def lexicon_dir() -> Path:
    env = os.environ.get(LEXICON_DIR_ENV)
    return Path(env) if env else SKILL_ROOT / "references" / "lexicons"


def load_lexicons(directory: Path | None = None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    d = directory or lexicon_dir()
    for fc, name in LEXICON_CLASSES.items():
        try:
            out[fc] = [unicodedata.normalize("NFKC", l).strip()
                       for l in (d / f"{name}.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
        except OSError:
            out[fc] = []
    return out


def lexicon_sha256(directory: Path | None = None) -> str:
    """One hash over the three lexicons the span patterns read (a changed lexicon changes the derivation)."""
    import hashlib
    h = hashlib.sha256()
    d = directory or lexicon_dir()
    for name in sorted(LEXICON_CLASSES.values()):
        p = d / f"{name}.txt"
        h.update(name.encode() + b"\0" + (p.read_bytes() if p.is_file() else b"") + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------- span patterns

_DATE_RE = re.compile(r"(?<![\d.])(?:19|20)\d{2}\s*[-./年]\s*\d{1,2}(?:\s*[-./月]\s*\d{1,2}\s*日?|\s*月)?(?![\d])")
_TNM_RE = re.compile(r"(?<![A-Za-z])(?:[cpyra]{1,3})?T[0-4x](?:is)?[a-d]?\s*N[0-3x][a-c]?\s*M[01x][a-c]?(?![A-Za-z0-9])",
                     re.I)
_STAGE_RE = re.compile(r"(?:(?<![A-Za-z])(?:IV|I{1,3}|V)|[ⅠⅡⅢⅣⅤ]|(?<![\d.])[1-4])[ABCabc]?\s*期|(?:局限|广泛)期")
_CYCLE_RE = re.compile(r"第\s*[0-9一二三四五六七八九十]+\s*(?:个疗程|疗程|个周期|周期|程)|(?<![A-Za-z])C\d{1,2}D\d{1,2}(?!\d)")
_UNITS = (
    r"[x×]\s*10\s*[\^~°`˚]?\s*(?:9|12|⁹|¹²)\s*/\s*L", r"10\s*(?:[\^~°`˚]\s*(?:9|12)|⁹|¹²)\s*/\s*L", r"mg/m2", r"mg/m²", r"mg/kg",
    r"mg/d", r"μg/L", r"ug/L", r"ng/ml", r"ng/mL", r"pg/ml", r"pg/mL", r"IU/ml", r"IU/mL", r"IU/L", r"U/ml",
    r"U/mL", r"U/L", r"pmol/L", r"nmol/L", r"μmol/L", r"umol/L", r"mmol/L", r"g/L", r"g/dL", r"mmHg", r"mg",
    r"μg", r"ug", r"mcg", r"kg", r"ml", r"mL", r"cm", r"mm", r"Gy", r"%", r"℃", r"°C", r"次/分", r"bpm",
)
_NUM_UNIT_RE = re.compile(r"(?<![A-Za-z\d.])\d+(?:[.,]\d+)*\s*(?:" + "|".join(_UNITS) + r")(?![A-Za-z])")
_AUC_RE = re.compile(r"AUC\s*\d+(?:\.\d+)?")
_CELL_NUM_RE = re.compile(r"^[<>≤≥]?\s*\d+(?:[.,]\d+)*\s*[↑↓]?$")
_CELL_RANGE_RE = re.compile(r"^\d+(?:\.\d+)?\s*[-~～–]\s*\d+(?:\.\d+)?$")
_PROSE_RANGE_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?\s*[-~～–]\s*\d+(?:\.\d+)?(?![\d.])")
_RANGE_LINE_RE = re.compile(r"(?i)normal\s*range|reference\s*range|参考范围|参考值|参考区间")
_CONNECTORS = "+＋/／-－"
_ASCII_ALNUM = re.compile(r"[A-Za-z0-9]")


def _free(taken: list[tuple[int, int]], s: int, e: int) -> bool:
    return all(e <= a or s >= b for a, b in taken)


def _masked_ranges(line: str) -> list[tuple[int, int]]:
    out, i = [], line.find(MASK)
    while i != -1:
        out.append((i, i + len(MASK)))
        i = line.find(MASK, i + 1)
    return out


def _lexicon_hits(line: str, lex: dict[str, list[str]]) -> list[tuple[int, int, str]]:
    """Greedy longest lexicon matches (case-insensitive); ASCII-edged entries need non-alnum edges;
    a bare-digit lymph-node station counts only before 组 / 站 / 区."""
    low = line.casefold()
    by_first: dict[str, list[tuple[str, str]]] = {}
    for fc, entries in lex.items():
        for ent in entries:
            if ent:
                by_first.setdefault(ent[0].casefold(), []).append((ent, fc))
    for k in by_first:
        by_first[k].sort(key=lambda x: -len(x[0]))
    hits: list[tuple[int, int, str]] = []
    i = 0
    while i < len(line):
        found = None
        for ent, fc in by_first.get(low[i], []):
            j = i + len(ent)
            if low[i:j] != ent.casefold():
                continue
            if _ASCII_ALNUM.match(ent[0]) and i > 0 and _ASCII_ALNUM.match(line[i - 1]):
                continue
            if _ASCII_ALNUM.match(ent[-1]) and j < len(line) and _ASCII_ALNUM.match(line[j]):
                continue
            if fc == "ln_station" and ent.isdigit() and not (j < len(line) and line[j] in "组站区"):
                continue
            found = (i, j, fc)
            break
        if found:
            hits.append(found)
            i = found[1]
        else:
            i += 1
    return hits


def derive_spans(lines: list[str], first_line_no: int, lex: dict[str, list[str]]) -> list[dict]:
    """High-risk spans of body `lines` (token-free), numbered from sidecar line `first_line_no`.
    Returns [{id, field_class, line, start, end, text, origin: "derived"}] in reading order."""
    spans: list[dict] = []
    for k, line in enumerate(lines):
        ln = first_line_no + k
        taken = list(_masked_ranges(line))

        def add(s: int, e: int, fc: str) -> None:
            text = line[s:e]
            # trim whitespace the patterns may include at the edges
            while text and text[0].isspace():
                s, text = s + 1, text[1:]
            while text and text[-1].isspace():
                e, text = e - 1, text[:-1]
            if text and _free(taken, s, e):
                taken.append((s, e))
                spans.append({"field_class": fc, "line": ln, "start": s, "end": e, "text": text})

        for m in _DATE_RE.finditer(line):
            add(m.start(), m.end(), "date")
        for m in _TNM_RE.finditer(line):
            add(m.start(), m.end(), "stage")
        for m in _STAGE_RE.finditer(line):
            add(m.start(), m.end(), "stage")
        for m in _CYCLE_RE.finditer(line):
            add(m.start(), m.end(), "cycle_number")
        hits = _lexicon_hits(line, lex)
        for s, e, fc in hits:
            add(s, e, fc)
        for m in _AUC_RE.finditer(line):
            add(m.start(), m.end(), "number")
        for m in _NUM_UNIT_RE.finditer(line):
            add(m.start(), m.end(), "number")
        if line.lstrip().startswith("|"):
            pos = line.find("|")
            for cell in line[pos + 1:].split("|"):
                c0 = pos + 1
                pos = c0 + len(cell)
                raw = cell.strip()
                if raw and (_CELL_NUM_RE.match(raw) or _CELL_RANGE_RE.match(raw)):
                    s = c0 + cell.index(raw)
                    e = s + len(raw.rstrip("↑↓").rstrip())
                    add(s, e, "number")
                elif raw and _unit_norm(raw) in KNOWN_UNITS:
                    s = c0 + cell.index(raw)
                    add(s, s + len(raw), "unit")
        else:
            # a line holding only a number (a result printed on its own line), and the range of a
            # labelled range line (Normal range: 0 - 35)
            raw = line.strip()
            if raw and _CELL_NUM_RE.match(raw):
                s = line.index(raw)
                add(s, s + len(raw.rstrip("↑↓").rstrip()), "number")
            if _RANGE_LINE_RE.search(line):
                for m in _PROSE_RANGE_RE.finditer(line):
                    add(m.start(), m.end(), "number")
        # connector between two drug names on the line (方案里药名之间的 + / -)
        drugs = sorted((s, e) for s, e, fc in hits if fc == "drug_name")
        for (s1, e1), (s2, e2) in zip(drugs, drugs[1:]):
            gap = line[e1:s2]
            if gap.strip() and len(gap.strip()) == 1 and gap.strip() in _CONNECTORS:
                c = e1 + gap.index(gap.strip())
                add(c, c + 1, "regimen_connector")
    # chart ticks: a line that is only a number, equal to a number on a nearby range line, is a scale
    # label of a range bar, not a result (FIX_PLAN ORG-P0-02 step 1)
    kept = []
    for sp in spans:
        k = sp["line"] - first_line_no
        if sp["field_class"] == "number" and lines[k].strip().strip("|").strip() == sp["text"]:
            window = lines[max(0, k - 6):k] + lines[k + 1:k + 7]
            num = re.sub(r"[^\d.]", "", sp["text"])
            if any(_RANGE_LINE_RE.search(w) and num in re.findall(r"\d+(?:\.\d+)?", w) for w in window):
                continue
        kept.append(sp)
    kept.sort(key=lambda s: (s["line"], s["start"]))
    for i, sp in enumerate(kept, start=1):
        sp["id"] = f"S-{i:03d}"
        sp["origin"] = "derived"
    return kept


# ---------------------------------------------------------------- normalisation + comparison

def norm_char_stream(s: str) -> tuple[str, list[int]]:
    """Alignment normalisation of `s` → (normalised string, index of each normalised char in `s`).
    NFKC per character, case fold, İ/ı → i, × → x; whitespace dropped."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(s):
        if ch.isspace():
            continue
        t = unicodedata.normalize("NFKC", ch).casefold()
        t = t.replace("i̇", "i").replace("ı", "i").replace("×", "x")
        for c in t:
            if c.isspace():
                continue
            out.append(c)
            idx.append(i)
    return "".join(out), idx


def _base(s: str) -> str:
    return norm_char_stream(s or "")[0]


def _unit_norm(s: str) -> str:
    t = _base(s)
    t = re.sub(r"x?10[\^~°`˚]?(9|12)/l", r"10^\1/l", t) if re.search(r"(x10|10[\^~°`˚])", t) else t
    return t.replace("²", "2").replace("μ", "u").replace("mcg", "ug")


def canonical_date(s: str) -> str | None:
    t = _base(s)
    m = re.fullmatch(r"((?:19|20)\d{2})\D*?(\d{1,2})(?:\D*?(\d{1,2})\D*)?", t.rstrip("日月"))
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), m.group(3)
    if not 1 <= mo <= 12:
        return None
    if d is None:
        return f"{y:04d}-{mo:02d}"
    if not 1 <= int(d) <= 31:
        return None
    return f"{y:04d}-{mo:02d}-{int(d):02d}"


def _number_parts(s: str) -> tuple[str | None, str]:
    t = _unit_norm(s)
    m = re.match(r"[<>≤≥]?(\d+(?:[.,]\d+)*)", t)
    if not m:
        return None, t
    num = m.group(1)
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num):
        num = num.replace(",", "")
    return num, t[m.end():].lstrip("↑↓")


def _range_parts(s: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)[-~～–](\d+(?:\.\d+)?)", _base(s))
    return (m.group(1), m.group(2)) if m else None


_TNM_FULL = re.compile(r"[cpyra]{0,3}t[0-4x](?:is)?[a-d]?n[0-3x][a-c]?m[01x][a-c]?")
_STAGE_FULL = re.compile(r"(?:iv|i{1,3}|v|[1-4])[abc]?期|(?:局限|广泛)期")
_CYCLE_FULL = re.compile(r"第?[0-9一二三四五六七八九十]+(?:个疗程|疗程|个周期|周期|程)|c\d{1,2}d\d{1,2}")


# the units a number span may carry, normalised (_unit_norm): a different one of these is a conflict,
# anything else in the unit position is a garbled read (no signal)
KNOWN_UNITS = frozenset({
    "10^9/l", "10^12/l", "mg/m2", "mg/kg", "mg/d", "ug/l", "ng/ml", "pg/ml", "iu/ml", "iu/l", "u/ml", "u/l",
    "pmol/l", "nmol/l", "umol/l", "mmol/l", "g/l", "g/dl", "mmhg", "mg", "ug", "kg", "g", "ml", "l", "cm", "mm",
    "gy", "%", "°c", "次/分", "bpm",
})


def grammatical(field_class: str, reading: str) -> bool:
    t = _base(reading)
    if not t:
        return False
    if field_class == "date":
        return canonical_date(reading) is not None
    if field_class == "stage":
        return bool(_TNM_FULL.fullmatch(t) or _STAGE_FULL.fullmatch(t))
    if field_class == "cycle_number":
        return bool(_CYCLE_FULL.fullmatch(t))
    if field_class in ("number", "unit"):
        return bool(re.search(r"\d", t))
    if field_class == "regimen_connector":
        return t in {"+", "/", "-"}
    return True


def equal(field_class: str, a: str, b: str) -> bool:
    """Do the transcription `a` and the engine reading `b` say the same thing (class-specific)?"""
    if field_class == "date":
        ca, cb = canonical_date(a), canonical_date(b)
        return ca is not None and ca == cb
    if field_class in ("number", "unit"):
        if _unit_norm(a) == _unit_norm(b):
            return True
        ra, rb = _range_parts(a), _range_parts(b)
        if ra or rb:
            return ra == rb
        na, ua = _number_parts(a)
        nb, ub = _number_parts(b)
        return na is not None and na == nb and ua == ub
    if field_class == "regimen_connector":
        m = {"＋": "+", "／": "/", "－": "-"}
        return m.get(a.strip(), a.strip()) == m.get(b.strip(), b.strip())
    if field_class in ("date", "stage", "cycle_number"):
        return _base(a) == _base(b)
    # text classes: punctuation and bracket shapes are not the reading (（ vs 〈, ， vs ,)
    return _letters(a) == _letters(b)


def _letters(s: str) -> str:
    return "".join(c for c in _base(s) if unicodedata.category(c)[0] in "LN")


def _edit(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(c in it for c in short)


def classify(field_class: str, model_text: str, engine_text: str | None, engine_conf,
             engine: str | None, lex: dict[str, list[str]] | None = None,
             anchored: bool = True) -> tuple[str, str]:
    """(state, reason) for one span: state ∈ agree | no_signal | conflict."""
    if engine is None:
        return "no_signal", "no engine"
    if engine_text is None or not _base(engine_text):
        return "no_signal", "nothing aligned"
    if equal(field_class, model_text, engine_text):
        return "agree", "same reading"
    floor = NO_SIGNAL_BELOW.get(engine, DEFAULT_NO_SIGNAL_BELOW)
    if engine_conf is None or float(engine_conf) < floor:
        return "no_signal", f"engine confidence under {floor:g}"
    if not anchored:
        return "no_signal", "not anchored by aligned context"
    a, b = _base(model_text), _base(engine_text)
    if SequenceMatcher(None, a, b, autojunk=False).ratio() < SIMILARITY_FLOOR:
        return "no_signal", "similarity under 0.5"
    if not grammatical(field_class, engine_text):
        return "no_signal", f"not a grammatical {field_class}"
    if field_class in ("number", "unit") and not (_range_parts(model_text) or _range_parts(engine_text)):
        na, ua = _number_parts(model_text)
        nb, ub = _number_parts(engine_text)
        if na is not None and na == nb and ua != ub:
            # same number, the unit read differently: a unit the engine lost or garbled is no signal;
            # another real unit (mg vs g) is a conflict
            if not ub or _is_subsequence(ub, ua) or ub not in KNOWN_UNITS:
                return "no_signal", "engine lost or garbled the unit glyphs"
            return "conflict", "same number, another unit"
    numeric = field_class in ("date", "number", "unit", "stage", "cycle_number")
    if not numeric and len(b) < len(a) and _is_subsequence(b, a) and \
            all(not c.isdigit() for c in _drop(a, b)):
        return "no_signal", "engine only lost non-numeric glyphs"
    if field_class in LEXICON_CLASSES and lex is not None:
        entries = {_base(x) for x in lex.get(field_class, [])}
        if a in entries and b not in entries and _edit(a, b) <= 1:
            return "no_signal", "lexicon near-miss"
    return "conflict", "confident grammatical reading differs"


def _drop(a: str, b: str) -> str:
    """Characters of `a` left over after matching subsequence `b`."""
    out, it = [], iter(b)
    nxt = next(it, None)
    for c in a:
        if nxt is not None and c == nxt:
            nxt = next(it, None)
        else:
            out.append(c)
    return "".join(out)
