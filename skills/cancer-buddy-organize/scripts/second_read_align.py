#!/usr/bin/env python3
"""second_read_align.py — the deterministic second read of one Phase 1 sidecar
(organizer-prompt-phase1-ocr.md §4 E, §5).

The model transcription in the sidecar body is the character truth of a pixel page (photo, scan,
PDF page without a text layer). AFTER the body is written and masked, this script — and only this
script — runs the deterministic OCR engine once per page image, aligns the engine text with the body
character by character, and decides every high-risk span (_high_risk_spans.derive_spans + the
worker's declared spans) as agree / no_signal / conflict. It then writes, itself:

  * `[OCR_UNCERTAIN:U-nnn]` right after the literal of every conflict span and every declared
    unreadable / layout-anomaly span (the body keeps the transcription's characters);
  * `## 高风险字段复读` (engine / body_sha256 / record lines + the 5-column table, 一致 = 是 / 否 / 无信号);
  * `## 不确定字段` entries (readings = the transcription + the engine's own string and confidence,
    masked; candidates = lexicon_candidates.compute);
  * the header's SECOND_READ_CHANNEL / INDEPENDENT_REREAD / CONFIDENCE (rule-derived);
  * raw/_extract/<stem>.second_read.json — the record the gate recomputes from.

A born-digital page (text_layer_kind.py: born_digital) is not OCR'd: `--text-layer` checks the body
line by line against the raw `pdftotext -layout` output (identity, not an independent read).

`body_sha256` hashes the body without tokens. The first body the engine was run against is kept in
the record: a later --apply on the same worker's sidecar is refused (exit 4) unless the only change
is PII masking, so a transcription cannot be edited towards the engine after seeing it.

CLI:
    second_read_align.py --apply <sidecar> --patient-dir <pd> --image <page image> [--image …]
                         [--engine auto|apple_vision|tesseract|none] [--engine-json <run_ocr_engine output>]
    second_read_align.py --apply <sidecar> --patient-dir <pd> --text-layer <pdftotext output>
    second_read_align.py --check <sidecar> --patient-dir <pd>
Exit: 0 ok; 1 --check found problems; 2 bad invocation or sidecar shape; 3 engine failed to run;
      4 the body changed after the engine read (other than PII masking).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _high_risk_spans as hrs  # noqa: E402

TOOL = "second_read_align"
VERSION = "1"
SECTION = "## 高风险字段复读"
UNCERTAIN = "## 不确定字段"
TABLE_HEAD = "| 字段 | 行 | 主通道读数 | 第二通道读数 | 一致 |"
STATE_CELL = {"agree": "是", "no_signal": "无信号", "conflict": "否", "declared": "否"}
IDENTITY_ENGINE = "text_layer_identity"
_TOKEN_ID_RE = re.compile(r"\[OCR_UNCERTAIN:(U-\d{3,})\]")


# ------------------------------------------------------------------ small helpers

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(pd: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(pd.resolve()).as_posix()
    except ValueError:
        return p.name


def deny_tokens(pd: Path) -> set[str]:
    try:
        import pii_rescan
        return {t for t in pii_rescan.load_deny_tokens(pd) if len(t) >= 2}
    except Exception:
        return set()


def mask_reading(text: str | None, tokens: set[str]) -> str | None:
    """Engine readings pass the identity word list and the PII shape floor before they are written
    anywhere a downstream reader sees (phase1 §5)."""
    if text is None:
        return None
    out = text
    for t in sorted(tokens, key=len, reverse=True):
        out = out.replace(t, hrs.MASK)
    try:
        import pii_rescan
        for _, snip in pii_rescan.scan_line(out):
            out = out.replace(snip, hrs.MASK)
    except Exception:
        pass
    return out


def mask_compatible(masked: str | None, raw: str | None) -> bool:
    """`masked` is `raw` with some substrings replaced by [PII_MASKED]."""
    if masked in (None, "—") or raw in (None, "—"):
        return (masked in (None, "—")) == (raw in (None, "—"))
    if hrs.MASK not in masked:
        return masked == raw
    pat = "(?:.+?)".join(re.escape(p) for p in masked.split(hrs.MASK))
    return re.fullmatch(pat, raw, re.S) is not None


def only_masking_changed(old: str, new: str) -> bool:
    return old == new or (hrs.MASK in new and mask_compatible(new, old))


def plain(s: str | None) -> str:
    """A table cell's text as parse_section reads it back."""
    if s is None or s == "":
        return "—"
    return s.replace("\n", " ")


def cell(s: str | None) -> str:
    if s is None or s == "":
        return "—"
    return s.replace("\n", " ").replace("|", "\\|")


def yaml_str(s: str | None) -> str:
    if s is None:
        return "null"
    return json.dumps(s, ensure_ascii=False)


# ------------------------------------------------------------------ engine text + alignment

def engine_stream(engine_doc: dict) -> tuple[str, list]:
    """Engine text (pages / lines joined by newlines, words by spaces) and a confidence per char."""
    chars: list[str] = []
    conf: list = []
    first = True
    for page in engine_doc.get("pages") or []:
        for line in page.get("lines") or []:
            if not first:
                chars.append("\n")
                conf.append(None)
            first = False
            words = line.get("words")
            if words:
                for k, w in enumerate(words):
                    if k:
                        chars.append(" ")
                        conf.append(None)
                    t = str(w.get("text") or "")
                    chars.extend(t)
                    conf.extend([w.get("confidence")] * len(t))
            else:
                t = str(line.get("text") or "")
                chars.extend(t)
                conf.extend([line.get("confidence")] * len(t))
    return "".join(chars), conf


class Aligner:
    """Whole-page character alignment of the body against the engine text (SequenceMatcher,
    autojunk off), mapped by position — never a global search for the span's string."""

    def __init__(self, body: str, engine_text: str, engine_conf: list):
        self.body = body
        self.bn, self.bi = hrs.norm_char_stream(body)
        self.en, self.ei = hrs.norm_char_stream(engine_text)
        self.engine_text = engine_text
        self.engine_conf = engine_conf
        self.ops = SequenceMatcher(None, self.bn, self.en, autojunk=False).get_opcodes()
        self.equal = [False] * len(self.bn)
        for tag, i1, i2, _, _ in self.ops:
            if tag == "equal":
                for i in range(i1, i2):
                    self.equal[i] = True

    def _map(self, pos: int, end: bool) -> int:
        for tag, i1, i2, j1, j2 in self.ops:
            if tag == "insert":
                continue
            if (i1 <= pos < i2) if not end else (i1 < pos <= i2):
                if tag == "equal":
                    return j1 + (pos - i1)
                if tag == "delete":
                    return j1
                if (pos == i1 and not end) or (pos == i2 and end):
                    return j1 if not end else j2
                return j1 + round((pos - i1) * (j2 - j1) / (i2 - i1))
        return len(self.en) if end else 0

    def norm_range(self, start: int, end: int) -> tuple[int, int]:
        """Body char range [start, end) → normalised body range."""
        from bisect import bisect_left
        return bisect_left(self.bi, start), bisect_left(self.bi, end)

    def reading(self, start: int, end: int) -> tuple[str | None, object, bool]:
        """(engine reading, min confidence, anchored) for the body char range [start, end)."""
        s, e = self.norm_range(start, end)
        if s >= e:
            return None, None, False
        js, je = self._map(s, False), self._map(e, True)
        anchored = any(self.equal[k] for k in range(s, e)) or \
            any(self.equal[k] for k in range(max(0, s - 2), s)) or \
            any(self.equal[k] for k in range(e, min(len(self.bn), e + 2)))
        if je <= js:
            return None, None, anchored
        a, b = self.ei[js], self.ei[je - 1] + 1
        text = self.engine_text[a:b].strip()
        confs = [c for c in self.engine_conf[a:b] if isinstance(c, (int, float))]
        return (text or None), (min(confs) if confs else None), anchored


# ------------------------------------------------------------------ sidecar surgery

def split_sidecar(text: str) -> dict:
    lines = text.splitlines()
    a, b = hrs.body_bounds(lines)
    n_hdr = hrs.header_length(lines)
    sections: list[tuple[str, list[str]]] = []
    cur: tuple[str, list[str]] | None = None
    for line in lines[b:]:
        m = re.match(r"^##\s+(\S+)", line)
        if m and hrs._APPENDIX_RE.match(line):
            cur = (m.group(1), [line])
            sections.append(cur)
        elif cur is not None:
            cur[1].append(line)
    return {"lines": lines, "header": lines[:n_hdr], "body_first": a, "body_end": b,
            "body": _trim(lines[a:b]), "sections": sections}


def header_dict(header: list[str]) -> dict[str, str]:
    out = {}
    for line in header:
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def set_header(header: list[str], updates: dict[str, str]) -> list[str]:
    out = []
    for line in header:
        k = line.partition(":")[0].strip()
        out.append(f"{k}: {updates[k]}" if k in updates else line)
    return out


def section_block(sections, name) -> list[str] | None:
    for n, block in sections:
        if n == name:
            return block
    return None


def parse_section(block: list[str] | None) -> dict:
    """Keys (engine / body_sha256 / record / identity) and table rows of a `## 高风险字段复读` block."""
    out: dict = {"rows": []}
    if not block:
        return out
    for line in block[1:]:
        m = re.match(r"^(engine|body_sha256|record|identity):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
            continue
        if line.startswith("|") and not line.startswith("|---") and line.strip() != TABLE_HEAD:
            cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
            if len(cells) == 5:
                out["rows"].append({"field_class": cells[0], "line": cells[1], "model": cells[2],
                                    "engine": cells[3], "state": cells[4]})
    return out


# ------------------------------------------------------------------ core computation

def load_declared(pd: Path, stem: str) -> list[dict]:
    p = pd / "raw" / "_extract" / f"{stem}.declared.json"
    if not p.is_file():
        return []
    doc = json.loads(p.read_text(encoding="utf-8"))
    spans = doc.get("spans") if isinstance(doc, dict) else doc
    return [s for s in spans or [] if isinstance(s, dict)]


def locate_declared(body_lines: list[str], first_line_no: int, declared: list[dict],
                    taken: list[dict]) -> tuple[list[dict], list[str]]:
    """Declared spans on their line (first occurrence not already a derived span)."""
    out, problems = [], []
    for d in declared:
        ln, text = d.get("line"), d.get("text")
        fc = d.get("field_class") or "other"
        kind = d.get("kind") or "value"
        if not isinstance(ln, int) or not isinstance(text, str) or not text:
            problems.append(f"declared span {d!r} needs an integer line and a text")
            continue
        k = ln - first_line_no
        if not 0 <= k < len(body_lines):
            problems.append(f"declared span line {ln} is not a body line")
            continue
        line = body_lines[k]
        pos, found = 0, None
        while True:
            i = line.find(text, pos)
            if i == -1:
                break
            clash = any(t["line"] == ln and not (i + len(text) <= t["start"] or i >= t["end"]) for t in taken + out)
            if not clash:
                found = i
                break
            pos = i + 1
        if found is None:
            if any(t["line"] == ln and t["text"] == text for t in taken):
                continue  # the patterns already cover it: a declaration may only add
            problems.append(f"declared span {text!r} "
                            + ("overlaps a span the script already derives on line %d — declare only what the patterns "
                               "miss" % ln if text in line else f"is not on body line {ln}"))
            continue
        if fc not in hrs.VALUE_CLASSES + ("diagnosis_text", "other"):
            problems.append(f"declared span {text!r} field_class {fc!r} is not a pinned field_class")
            continue
        if kind not in ("value", "unreadable", "layout"):
            problems.append(f"declared span {text!r} kind {kind!r} is not value | unreadable | layout")
            continue
        out.append({"field_class": fc, "line": ln, "start": found, "end": found + len(text), "text": text,
                    "origin": "declared", "kind": kind, "layout": d.get("layout") or "none"})
    return out, problems


_SPAN_KEYS = ("field_class", "line", "start", "end", "text", "origin", "kind", "layout")


def compute(body_lines: list[str], first_line_no: int, engine_doc: dict | None, declared: list[dict],
            lex: dict, spans_from: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """Spans with their engine reading and state — the pure recomputation --check repeats. `spans_from`
    (the record's spans) replaces the derivation when the lexicons changed after the second read."""
    if spans_from is not None:
        spans, problems = [], []
        for s in spans_from:
            k = (s.get("line") or 0) - first_line_no
            ok = isinstance(s.get("start"), int) and isinstance(s.get("end"), int) and 0 <= k < len(body_lines)
            if not ok or body_lines[k][s["start"]:s["end"]] != s.get("text"):
                problems.append(f"recorded span {s.get('text')!r} is no longer at line {s.get('line')} of the body")
                continue
            spans.append({key: s.get(key) for key in _SPAN_KEYS})
    else:
        derived = hrs.derive_spans(body_lines, first_line_no, lex)
        extra, problems = locate_declared(body_lines, first_line_no, declared, derived)
        spans = derived + extra
    spans = sorted(spans, key=lambda s: (s["line"], s["start"]))
    engine = engine_doc.get("engine") if engine_doc else None
    body = "\n".join(body_lines)
    offsets, pos = [], 0
    for line in body_lines:
        offsets.append(pos)
        pos += len(line) + 1
    aligner = None
    if engine_doc and engine:
        et, ec = engine_stream(engine_doc)
        aligner = Aligner(body, et, ec)
    for i, sp in enumerate(spans, start=1):
        sp["id"] = f"S-{i:03d}"
        k = sp["line"] - first_line_no
        if aligner:
            text, conf, anchored = aligner.reading(offsets[k] + sp["start"], offsets[k] + sp["end"])
        else:
            text, conf, anchored = None, None, False
        sp["engine_text"], sp["engine_conf"] = text, conf
        if sp.get("origin") == "declared" and sp.get("kind") in ("unreadable", "layout"):
            sp["state"], sp["reason"] = "declared", f"declared {sp['kind']}"
            floor = hrs.NO_SIGNAL_BELOW.get(engine or "", hrs.DEFAULT_NO_SIGNAL_BELOW)
            sp["signal"] = bool(text) and isinstance(conf, (int, float)) and conf >= floor
        else:
            state, reason = hrs.classify(sp["field_class"], sp["text"], text, conf, engine, lex, anchored)
            sp["state"], sp["reason"] = state, reason
            sp["signal"] = state in ("agree", "conflict")
    return spans, problems


def summary_of(spans: list[dict], engine: str | None) -> dict:
    return {"engine": engine or "none", "spans_total": len(spans),
            "agree": sum(s["state"] == "agree" for s in spans),
            "no_signal": sum(s["state"] == "no_signal" for s in spans),
            "conflict": sum(s["state"] == "conflict" for s in spans),
            "declared": sum(s["state"] == "declared" for s in spans)}


def render(split: dict, spans: list[dict], engine_doc: dict | None, record_rel: str, body_sha: str,
           deny: set[str], lex_dir: Path | None) -> tuple[list[str], list[str], list[str], dict]:
    """(new body lines with tokens, the 复读 section, the 不确定字段 section, header updates)."""
    import lexicon_candidates as lc
    first = split["body_first"] + 1
    body = [hrs.strip_tokens(l) for l in split["body"]]
    channel = engine_doc.get("channel") if engine_doc else None
    tok_spans = [s for s in spans if s["state"] in ("conflict", "declared")]
    for n, s in enumerate(tok_spans, start=1):
        s["token"] = f"U-{n:03d}"
    for s in sorted(tok_spans, key=lambda x: (x["line"], x["end"]), reverse=True):
        k = s["line"] - first
        body[k] = body[k][:s["end"]] + f"[OCR_UNCERTAIN:{s['token']}]" + body[k][s["end"]:]
    for s in spans:
        s["engine_text_masked"] = mask_reading(s["engine_text"], deny)
    sec = [SECTION, "", f"engine: {channel or 'none'}", f"body_sha256: {body_sha}", f"record: {record_rel}", "",
           TABLE_HEAD, "|---|---|---|---|---|"]
    for s in spans:
        sec.append(f"| {s['field_class']} | {s['line']} | {cell(s['text'])} | {cell(s['engine_text_masked'])} | "
                   f"{STATE_CELL[s['state']]} |")
    sec.append("")
    unc: list[str] = []
    if tok_spans:
        unc = [UNCERTAIN, ""]
        for s in tok_spans:
            model = None if s["text"] == hrs.UNREADABLE else s["text"]
            reads = [f'    - {{channel: llm_vision, text: {yaml_str(model)}, confidence: null}}']
            if channel:
                c = s["engine_conf"]
                reads.append(f'    - {{channel: "{channel}", text: {yaml_str(s["engine_text_masked"])}, '
                             f'confidence: {"null" if c is None else round(float(c), 4)}}}')
            cands = []
            if s["field_class"] in lc.FIELD_CLASS_LEXICON:
                lex_lines = lc.load_lexicon(lc.FIELD_CLASS_LEXICON[s["field_class"]], lex_dir)
                if lex_lines is not None:
                    cands = lc.compute([model, s["engine_text_masked"]], lex_lines,
                                       lc.FIELD_CLASS_LEXICON[s["field_class"]])
            unc += [f"- id: {s['token']}", f"  line: {s['line']}", f"  field_class: {s['field_class']}",
                    "  readings:"] + reads
            if cands:
                unc.append("  candidates:")
                unc += [f'    - {{text: {yaml_str(c["text"])}, lexicon: {c["lexicon"]}, confidence: {c["confidence"]}}}'
                        for c in cands]
            else:
                unc.append("  candidates: []")
            unc += ["  cross_doc_supported: {status: none, refs: []}",
                    f"  layout: {s.get('layout') or 'none'}" if s.get("kind") == "layout" else "  layout: none",
                    "  layout_intent: null", ""]
    hdr = header_dict(split["header"])
    signal = any(s.get("signal") for s in spans)
    indep = bool(channel) and channel.startswith("deterministic_ocr:") and signal
    no_signal_rows = any(s["state"] == "no_signal" for s in spans)
    if tok_spans or hdr.get("CONFIDENCE") == "low":
        conf = "low"
    elif indep and not no_signal_rows:
        conf = "high"
    else:
        conf = "medium"
    updates = {"SECOND_READ_CHANNEL": channel or "none", "INDEPENDENT_REREAD": "true" if indep else "false",
               "CONFIDENCE": conf}
    return body, sec, unc, updates


def review_status(spans: list[dict], indep: bool) -> str:
    if not spans:
        return "not_applicable"
    return "passed_independent_reread" if indep and all(s["state"] == "agree" for s in spans) else "needs_human_review"


def assemble(split: dict, header: list[str], body: list[str], sec: list[str], unc: list[str]) -> str:
    keep = [(n, b) for n, b in split["sections"] if n not in ("高风险字段复读", "不确定字段")]
    order = ["文本层字形异常", "列配对", "PII"]
    out = header + [""] + body
    while out and not out[-1].strip():
        out.pop()
    out.append("")
    out += sec
    for name in order[:-1]:
        for n, b in keep:
            if n == name:
                out += _trim(b) + [""]
    if unc:
        out += unc
    for n, b in keep:
        if n == "PII":
            out += _trim(b)
    return "\n".join(out).rstrip("\n") + "\n"


def _trim(block: list[str]) -> list[str]:
    b = list(block)
    while b and not b[-1].strip():
        b.pop()
    return b


# ------------------------------------------------------------------ --apply

def _record_path(pd: Path, stem: str) -> Path:
    return pd / "raw" / "_extract" / f"{stem}.second_read.json"


def apply(sidecar: Path, pd: Path, images: list[Path], text_layer: Path | None, engine: str,
          engine_json: Path | None, lex_dir: Path | None) -> tuple[int, dict]:
    text = sidecar.read_text(encoding="utf-8")
    split = split_sidecar(text)
    hdr = header_dict(split["header"])
    if len(split["header"]) != 12:
        return 2, {"error": "the sidecar has no pinned 12-key header (phase1 §3) — write it first"}
    if section_block(split["sections"], "PII") is None:
        return 2, {"error": "the sidecar has no `## PII` trailer — mask the body and write the trailer first (phase1 §4 F-G)"}
    primary = hrs._base(hdr.get("PRIMARY_CHANNEL", ""))
    if text_layer is not None and primary != "text_layer":
        return 2, {"error": "--text-layer is the born-digital identity check: PRIMARY_CHANNEL must be text_layer"}
    if text_layer is None and primary != "llm_vision":
        return 2, {"error": "a pixel page is transcribed by the model: PRIMARY_CHANNEL must be llm_vision (phase1 §2)"}
    stem = sidecar.stem
    ext = pd / "raw" / "_extract"
    ext.mkdir(parents=True, exist_ok=True)
    body_clean = hrs.strip_tokens("\n".join(split["body"]))
    body_sha = sha256_text(body_clean)
    rec_path = _record_path(pd, stem)
    prior = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.is_file() else None
    worker = hdr.get("EXTRACTOR", "")
    if prior and prior.get("extractor") == worker and isinstance(prior.get("first_body"), str) \
            and not only_masking_changed(prior["first_body"], body_clean):
        return 4, {"error": "the body changed after the engine read (other than PII masking) — the transcription "
                            "must stay the model's own reading; restore it (the engine output is never a source for "
                            "the body)"}
    first_body = prior["first_body"] if prior and prior.get("extractor") == worker else body_clean
    lex = hrs.load_lexicons(lex_dir)
    declared = load_declared(pd, stem)
    first_line_no = split["body_first"] + 1

    if text_layer is not None:
        raw = text_layer.read_text(encoding="utf-8", errors="replace").replace("\f", "\n")
        raw_norm = {hrs._base(l) for l in raw.splitlines() if hrs._base(l)}
        unmatched = [first_line_no + k for k, l in enumerate(split["body"])
                     if hrs._base(hrs.strip_tokens(l)) and hrs._base(hrs.strip_tokens(l)) not in raw_norm
                     and not l.startswith("#")]
        total = sum(1 for l in split["body"] if hrs._base(l) and not l.startswith("#"))
        sec = [SECTION, "", f"engine: {IDENTITY_ENGINE}", f"body_sha256: {body_sha}",
               f"record: {_rel(pd, rec_path)}",
               f"identity: {total - len(unmatched)}/{total} 行与原始文本层一致"
               + (f"；未对上：{', '.join(f'L{n}' for n in unmatched[:20])}" if unmatched else ""), ""]
        record = {"tool": TOOL, "version": VERSION, "mode": "text_layer_identity", "sidecar": _rel(pd, sidecar),
                  "extractor": worker, "body_sha256": body_sha, "first_body": first_body,
                  "text_layer": _rel(pd, text_layer), "text_layer_sha256": sha256_file(text_layer),
                  "lines_total": total, "unmatched_lines": unmatched,
                  "summary": {"engine": IDENTITY_ENGINE, "spans_total": 0, "agree": 0, "no_signal": 0, "conflict": 0,
                              "declared": 0}}
        body = [hrs.strip_tokens(l) for l in split["body"]]
        conf = "low" if hdr.get("CONFIDENCE") == "low" else "medium"
        header = set_header(split["header"], {"SECOND_READ_CHANNEL": "none", "INDEPENDENT_REREAD": "false",
                                              "CONFIDENCE": conf})
        sidecar.write_text(assemble(split, header, body, sec, []), encoding="utf-8")
        rec_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0, {"sidecar": _rel(pd, sidecar), "mode": "text_layer_identity", "lines_total": total,
                   "unmatched_lines": len(unmatched), "high_risk_review_status": "not_applicable",
                   "second_read_summary": record["summary"], "record": _rel(pd, rec_path)}

    import run_ocr_engine as roe
    engine_doc = None
    same_worker = bool(prior) and prior.get("extractor") == worker
    if same_worker and prior.get("engine_output") and (pd / prior["engine_output"]).is_file():
        # the engine read is fixed by the first --apply: a re-apply (after PII masking) replays it, whatever
        # --engine / --engine-json now say — no second engine run, no switching engines to lose a conflict
        engine_doc = json.loads((pd / prior["engine_output"]).read_text(encoding="utf-8"))
        if engine_json is not None and json.loads(engine_json.read_text(encoding="utf-8")) != engine_doc:
            return 4, {"error": "the engine read of this sidecar is fixed by its first --apply; it cannot be replaced"}
    elif engine_json is not None:
        engine_doc = json.loads(engine_json.read_text(encoding="utf-8"))
    elif engine != "none":
        shas = [sha256_file(p) for p in images]
        if prior and prior.get("engine_output") and (not images or prior.get("image_sha256s") == shas):
            cached = pd / prior["engine_output"]
            if cached.is_file():
                engine_doc = json.loads(cached.read_text(encoding="utf-8"))  # one engine run per page, ever
        if engine_doc is None and not images:
            return 2, {"error": "pass the page image(s) with --image (pixel page) or --text-layer (born-digital page)"}
        if engine_doc is None:
            chosen = roe.pick_engine(engine)
            if chosen is not None:
                try:
                    engine_doc = roe.read_images(images, chosen, pd)
                except roe.EngineError as e:
                    return 3, {"error": f"engine {chosen} failed: {e}"}
    if engine_doc is not None:
        if engine_doc.get("tool") != "run_ocr_engine" or engine_doc.get("engine") not in hrs.NO_SIGNAL_BELOW:
            return 2, {"error": "the engine output is not a run_ocr_engine.py document"}
        out_path = ext / f"{stem}.{engine_doc['engine']}.json"
        body_json = json.dumps(engine_doc, ensure_ascii=False, indent=2) + "\n"
        if not out_path.is_file() or out_path.read_text(encoding="utf-8") != body_json:
            out_path.write_text(body_json, encoding="utf-8")
    spans, problems = compute([hrs.strip_tokens(l) for l in split["body"]], first_line_no, engine_doc, declared, lex)
    if problems:
        return 2, {"error": "; ".join(problems)}
    deny = deny_tokens(pd)
    body, sec, unc, updates = render(split, spans, engine_doc, _rel(pd, rec_path), body_sha, deny, lex_dir)
    header = set_header(split["header"], updates)
    indep = updates["INDEPENDENT_REREAD"] == "true"
    record = {
        "tool": TOOL, "version": VERSION, "mode": "engine", "sidecar": _rel(pd, sidecar), "extractor": worker,
        "body_sha256": body_sha, "first_body": first_body,
        "engine": engine_doc.get("engine") if engine_doc else None,
        "channel": engine_doc.get("channel") if engine_doc else None,
        "engine_output": _rel(pd, ext / f"{stem}.{engine_doc['engine']}.json") if engine_doc else None,
        "engine_output_sha256": sha256_file(ext / f"{stem}.{engine_doc['engine']}.json") if engine_doc else None,
        "image_sha256s": [p.get("image_sha256") for p in (engine_doc or {}).get("pages") or []],
        "declared": declared,
        "lexicon_sha256": hrs.lexicon_sha256(lex_dir),
        "no_signal_below": hrs.NO_SIGNAL_BELOW,
        "spans": [{k: s.get(k) for k in ("id", "field_class", "line", "start", "end", "text", "origin", "kind",
                                         "layout", "engine_text", "engine_text_masked", "engine_conf", "state",
                                         "reason", "signal", "token")} for s in spans],
        "summary": summary_of(spans, engine_doc.get("engine") if engine_doc else None),
        "independent_reread": indep,
        "high_risk_review_status": review_status(spans, indep),
    }
    sidecar.write_text(assemble(split, header, body, sec, unc), encoding="utf-8")
    rec_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0, {"sidecar": _rel(pd, sidecar), "channel": record["channel"] or "none",
               "second_read_summary": record["summary"], "tokens": [s["token"] for s in spans if s.get("token")],
               "independent_reread": indep, "confidence": updates["CONFIDENCE"],
               "high_risk_review_status": record["high_risk_review_status"], "record": _rel(pd, rec_path)}


# ------------------------------------------------------------------ --check (also imported by the gate)

def check(sidecar: Path, pd: Path, lex_dir: Path | None = None) -> tuple[list[str], list[str]]:
    """The five gate_second_read checks for one sidecar → (errors, warnings)."""
    errs: list[str] = []
    warns: list[str] = []
    text = sidecar.read_text(encoding="utf-8", errors="replace")
    split = split_sidecar(text)
    hdr = header_dict(split["header"])
    sec = parse_section(section_block(split["sections"], "高风险字段复读"))
    rel = _rel(pd, sidecar)
    pixel = hdr.get("READ_MODE") == "model_vision_primary"
    if "engine" not in sec:
        if pixel:
            errs.append(f"{rel}: READ_MODE model_vision_primary without a `{SECTION}` block written by "
                        "second_read_align.py --apply (phase1 §4 E)")
        return errs, warns
    body_clean = hrs.strip_tokens("\n".join(split["body"]))
    body_sha = sha256_text(body_clean)
    if sec.get("body_sha256") != body_sha:
        errs.append(f"{rel}: body_sha256 {sec.get('body_sha256')!r} ≠ the body without tokens ({body_sha[:12]}…) — "
                    "the body changed after the second read, or the block was written by hand")
    rec_rel = sec.get("record")
    rec_path = pd / rec_rel if rec_rel else None
    if rec_path is None or not rec_path.is_file():
        (warns if not (pd / "raw").is_dir() else errs).append(
            f"{rel}: second-read record {rec_rel!r} not found"
            + (" (no raw/ in this copy: only body_sha256 checked)" if not (pd / "raw").is_dir() else ""))
        return errs, warns
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    if rec.get("body_sha256") != body_sha and sec.get("body_sha256") == body_sha:
        errs.append(f"{rel}: record body_sha256 ≠ the sidecar body")
    fb = rec.get("first_body")
    if isinstance(fb, str) and not only_masking_changed(fb, body_clean):
        errs.append(f"{rel}: the body differs from the one the engine was run against by more than PII masking — "
                    "the transcription was edited after the second read")
    if rec.get("mode") == IDENTITY_ENGINE or sec.get("engine") == IDENTITY_ENGINE:
        second = hdr.get("SECOND_READ_CHANNEL", "")
        if second == "none" and hdr.get("INDEPENDENT_REREAD") == "false":
            return errs, warns
        # phase1 §6: the one born-digital second read — an engine read of a layout-anomaly region, backing a
        # document intent (text layer + engine agreeing). It needs the region's engine output and such an entry.
        stem = Path(str(rec.get("sidecar") or sidecar.name)).stem  # the Phase-1 name the raw/_extract files use
        errs += region_read_problems(stem, pd, text, hdr, rel)
        return errs, warns
    engine_doc = None
    if rec.get("engine_output"):
        ep = pd / rec["engine_output"]
        if not ep.is_file():
            errs.append(f"{rel}: engine output {rec['engine_output']} missing — the second read cannot be recomputed")
            return errs, warns
        if sha256_file(ep) != rec.get("engine_output_sha256"):
            errs.append(f"{rel}: engine output {rec['engine_output']} changed after the second read")
        engine_doc = json.loads(ep.read_text(encoding="utf-8"))
    channel = engine_doc.get("channel") if engine_doc else None
    if sec.get("engine") != (channel or "none"):
        errs.append(f"{rel}: block engine {sec.get('engine')!r} ≠ the recorded engine {channel or 'none'!r}")
    if hdr.get("SECOND_READ_CHANNEL") != (channel or "none"):
        errs.append(f"{rel}: SECOND_READ_CHANNEL {hdr.get('SECOND_READ_CHANNEL')!r} ≠ the engine the script ran "
                    f"({channel or 'none'})")
    lex = hrs.load_lexicons(lex_dir)
    spans_from = None
    if rec.get("lexicon_sha256") and rec["lexicon_sha256"] != hrs.lexicon_sha256(lex_dir):
        # the lexicons changed after this second read: the span list is the record's (still recomputed
        # against the stored engine output), and the pattern-only spans must all be in it
        spans_from = rec.get("spans") or []
        warns.append(f"{rel}: the lexicons changed after the second read — spans taken from the record")
        have = {(s.get("line"), s.get("start"), s.get("end")) for s in spans_from}
        pattern_only = [s for s in hrs.derive_spans([hrs.strip_tokens(l) for l in split["body"]],
                                                    split["body_first"] + 1, {k: [] for k in lex})
                        if (s["line"], s["start"], s["end"]) not in have]
        if pattern_only:
            errs.append(f"{rel}: span {pattern_only[0]['text']!r} (line {pattern_only[0]['line']}) is missing from the "
                        "second-read record — the span list can only grow")
    spans, problems = compute([hrs.strip_tokens(l) for l in split["body"]],
                              split["body_first"] + 1, engine_doc, rec.get("declared") or [], lex, spans_from)
    errs += [f"{rel}: {p}" for p in problems]
    # (1) the table covers every span, (2) the states recompute
    rows = sec["rows"]
    want = [(s["field_class"], str(s["line"]), plain(s["text"]), STATE_CELL[s["state"]]) for s in spans]
    got = [(r["field_class"], r["line"], r["model"], r["state"]) for r in rows]
    if want != got:
        missing = [w for w in want if w not in got]
        extra = [g for g in got if g not in want]
        errs.append(f"{rel}: the {SECTION} table is not the recomputed second read ({len(want)} span(s) expected, "
                    f"{len(got)} row(s)); first difference: "
                    + (f"span {missing[0][0]} L{missing[0][1]} {missing[0][2]!r} → {missing[0][3]} not in the table"
                       if missing else f"row {extra[0]!r} is not a recomputed span" if extra else "order differs"))
    # (4) readings = the engine's own string (masked)
    for s, r in zip(spans, rows):
        if not mask_compatible(r["engine"], plain(s["engine_text"])):
            errs.append(f"{rel}: row L{r['line']} {r['model']!r}: second-channel reading {r['engine']!r} is not the "
                        "engine's own string (masking aside)")
            break
    import validate_structured_outputs as vso
    block, _ = vso._uncertain_block(text)
    tok_by_id = {f"U-{n:03d}": s for n, s in enumerate(
        [s for s in spans if s["state"] in ("conflict", "declared")], start=1)}
    for e in vso.parse_uncertain_entries(block):
        s = tok_by_id.get(str(e.get("id")))
        if s is None:
            continue
        eng = [r for r in (e.get("readings") or []) if isinstance(r, dict) and r.get("channel") == channel]
        if channel and (not eng or not mask_compatible(eng[0].get("text"), s["engine_text"])):
            errs.append(f"{rel}: `## 不确定字段` {e.get('id')} engine reading is not the engine's own string")
        if e.get("field_class") != s["field_class"] or e.get("line") != s["line"]:
            errs.append(f"{rel}: `## 不确定字段` {e.get('id')} field_class / line ≠ the recomputed span "
                        f"({s['field_class']} L{s['line']})")
    # (3) tokens only on conflict / declared spans, right after the span's literal
    body_lines = split["body"]
    first = split["body_first"] + 1
    want_tok = {(s["line"], s["end"]) for s in spans if s["state"] in ("conflict", "declared")}
    got_tok = set()
    for k, line in enumerate(body_lines):
        clean_pos = 0
        pos = 0
        for m in _TOKEN_ID_RE.finditer(line):
            clean_pos += m.start() - pos
            pos = m.end()
            got_tok.add((first + k, clean_pos))
    if got_tok != want_tok:
        bad = sorted(got_tok - want_tok)
        miss = sorted(want_tok - got_tok)
        if bad:
            errs.append(f"{rel}: [OCR_UNCERTAIN] at line {bad[0][0]} col {bad[0][1]} sits on no conflict / declared span "
                        "(agree and no-signal spans carry no token)")
        if miss:
            errs.append(f"{rel}: the conflict / declared span at line {miss[0][0]} (ends col {miss[0][1]}) has no "
                        "[OCR_UNCERTAIN] token")
    # (5) INDEPENDENT_REREAD is mechanical
    indep = bool(channel) and channel.startswith("deterministic_ocr:") and any(s.get("signal") for s in spans)
    if hdr.get("INDEPENDENT_REREAD") != ("true" if indep else "false"):
        errs.append(f"{rel}: INDEPENDENT_REREAD {hdr.get('INDEPENDENT_REREAD')} but the second read has "
                    f"{'a' if indep else 'no'} signal row — true iff a deterministic engine read ≥ 1 span")
    # the engine output belongs to an image that exists (when raw/ is here)
    for page in (engine_doc or {}).get("pages") or []:
        img = page.get("image")
        if isinstance(img, str) and (pd / img).is_file() and sha256_file(pd / img) != page.get("image_sha256"):
            errs.append(f"{rel}: engine page image {img} does not hash to the recorded image_sha256")
    return errs, warns


def region_read_problems(stem: str, pd: Path, text: str, hdr: dict, rel: str) -> list[str]:
    import validate_structured_outputs as vso
    out = []
    second = hdr.get("SECOND_READ_CHANNEL", "")
    if not second.startswith("deterministic_ocr:") or hdr.get("INDEPENDENT_REREAD") != "true":
        return [f"{rel}: a born-digital identity check is not a second read — SECOND_READ_CHANNEL none and "
                "INDEPENDENT_REREAD false, unless a layout-anomaly region was read by an engine (phase1 §6)"]
    engine = second.split(":", 1)[1]
    reg = pd / "raw" / "_extract" / f"{stem}.region.json"
    if not reg.is_file():
        return [f"{rel}: SECOND_READ_CHANNEL {second} on a born-digital page without its region engine read "
                f"raw/_extract/{stem}.region.json (run_ocr_engine.py read, phase1 §6)"]
    doc = json.loads(reg.read_text(encoding="utf-8"))
    if doc.get("tool") != "run_ocr_engine" or doc.get("engine") != engine:
        out.append(f"{rel}: {reg.name} is not a run_ocr_engine.py document of engine {engine}")
    region_text = engine_stream(doc)[0] if isinstance(doc, dict) else ""
    block, _ = vso._uncertain_block(text)
    backed = []
    for e in vso.parse_uncertain_entries(block):
        if e.get("layout_intent") in ("deleted", "amended") and vso._agreeing_independent_reads(e):
            eng = [r for r in e.get("readings") or [] if isinstance(r, dict) and r.get("channel") == second]
            if eng and isinstance(eng[0].get("text"), str) and hrs._base(eng[0]["text"]) in hrs._base(region_text):
                backed.append(e.get("id"))
    if not backed:
        out.append(f"{rel}: an engine second read on a born-digital page exists only to back a document intent — no "
                   "`## 不确定字段` entry has layout_intent deleted/amended with the text layer and the region read "
                   f"({second}, found in {reg.name}) agreeing (phase1 §6)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", metavar="SIDECAR")
    g.add_argument("--check", metavar="SIDECAR")
    ap.add_argument("--patient-dir", required=True)
    ap.add_argument("--image", action="append", default=[])
    ap.add_argument("--text-layer")
    ap.add_argument("--engine", default="auto", choices=("auto", "apple_vision", "tesseract", "none"))
    ap.add_argument("--engine-json", help="an existing run_ocr_engine.py output (replay / tests)")
    ap.add_argument("--lexicon-dir")
    a = ap.parse_args(argv)
    pd = Path(a.patient_dir)
    lex_dir = Path(a.lexicon_dir) if a.lexicon_dir else None
    if a.check:
        errs, warns = check(Path(a.check), pd, lex_dir)
        for w in warns:
            print(f"WARN: {w}", file=sys.stderr)
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        print(json.dumps({"sidecar": a.check, "ok": not errs, "errors": len(errs)}, ensure_ascii=False))
        return 1 if errs else 0
    rc, out = apply(Path(a.apply), pd, [Path(p) for p in a.image], Path(a.text_layer) if a.text_layer else None,
                    a.engine, Path(a.engine_json) if a.engine_json else None, lex_dir)
    print(json.dumps(out, ensure_ascii=False), file=sys.stdout if rc == 0 else sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
