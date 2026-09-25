#!/usr/bin/env python3
"""text_layer_kind.py — which pages of a PDF have a real text layer (organizer-prompt-phase1-ocr.md §2).

Per page:
  born_digital — a native text layer (Word / report-system export): the text layer IS the body; no
                 OCR, no model transcription; second_read_align.py --text-layer checks identity only.
  embedded_ocr — the text sits on a full-page image (image cover ≥ 0.85), is invisible (render mode
                 3), or uses a glyphless / OCR font: somebody's OCR, not the document's characters →
                 a pixel page (the model transcribes the rendered page; an engine second read).
  absent       — no text at all → a pixel page.

`pdffonts … uni:no` is NOT a criterion (most exports carry such a font and read fine). Damaged glyph
runs in a born-digital layer (a letter, then ! " # $ % & * + < = > @ \\ ^ _ ` | ~, then a letter — `le!t` —
or a stray İ / ı inside Latin text) are listed per page as glyph_anomaly_lines: the body keeps the layer's
characters and the worker reads only those lines once more by eye (`## 文本层字形异常`).

PyMuPDF when importable; otherwise poppler (pdffonts / pdfimages / pdftotext / pdfinfo).

CLI:
    text_layer_kind.py <pdf> [--out <json>]
Output JSON: {tool, version, file, sha256, method, pages: [{page, kind, chars, image_cover, invisible_text,
              ocr_font, fonts[], glyph_anomaly_lines: [{line, text}]}], summary: {born_digital[], embedded_ocr[],
              absent[]}}
Exit: 0; 2 bad invocation / unreadable PDF; 3 neither PyMuPDF nor poppler is available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE_COVER_MIN = 0.85
OCR_FONT_RE = re.compile(r"glyphless|tesseract|ocr", re.I)
GLYPH_ANOMALY_RE = re.compile(r"[A-Za-z][!\"#$%&*+<=>@\\^_`|~]+[A-Za-z]|[A-Za-z]*[İı][A-Za-z]*")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def glyph_anomalies(text: str) -> list[dict]:
    out = []
    for i, line in enumerate(text.replace("\f", "\n").splitlines(), start=1):
        if GLYPH_ANOMALY_RE.search(line) and re.search(r"[A-Za-z]", line):
            m = GLYPH_ANOMALY_RE.search(line)
            if m.group(0) in ("İ", "ı") and not re.search(r"[A-Za-z]", line.replace(m.group(0), "")):
                continue
            out.append({"line": i, "text": line.strip()})
    return out


def classify(chars: int, cover: float, invisible: bool, ocr_font: bool) -> str:
    if chars == 0:
        return "absent"
    if cover >= IMAGE_COVER_MIN or invisible or ocr_font:
        return "embedded_ocr"
    return "born_digital"


def _pymupdf(pdf: Path) -> list[dict]:
    import fitz  # PyMuPDF
    pages = []
    with fitz.open(pdf) as doc:
        for n, page in enumerate(doc, start=1):
            text = page.get_text("text")
            chars = len(re.sub(r"\s", "", text))
            area = abs(page.rect) or 1.0
            cover = 0.0
            for info in page.get_image_info():
                r = fitz.Rect(info.get("bbox")) & page.rect
                cover = max(cover, abs(r) / area)
            fonts = sorted({f[3] for f in page.get_fonts()})
            invisible = False
            try:
                spans = page.get_texttrace()
                visible = [s for s in spans if s.get("type") != 3 and s.get("opacity", 1) > 0]
                invisible = bool(spans) and not visible
            except Exception:
                pass
            pages.append({"page": n, "chars": chars, "image_cover": round(cover, 3), "invisible_text": invisible,
                          "fonts": fonts, "text": text})
    return pages


def _poppler(pdf: Path) -> list[dict]:
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    if not m:
        raise ValueError("pdfinfo cannot read the file")
    n_pages = int(m.group(1))
    size = re.search(r"^Page size:\s+([\d.]+) x ([\d.]+)", info, re.M)
    pw, ph = (float(size.group(1)), float(size.group(2))) if size else (612.0, 792.0)
    imgs = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True, text=True, timeout=120).stdout
    cover: dict[int, float] = {}
    for line in imgs.splitlines()[2:]:
        c = line.split()
        if len(c) >= 14 and c[0].isdigit():
            try:
                # width/height in pixels at x-ppi / y-ppi → points
                w_pt = int(c[3]) / float(c[12]) * 72
                h_pt = int(c[4]) / float(c[13]) * 72
            except (ValueError, ZeroDivisionError):
                continue
            cover[int(c[0])] = max(cover.get(int(c[0]), 0.0), min(1.0, (w_pt * h_pt) / (pw * ph)))
    pages = []
    for n in range(1, n_pages + 1):
        text = subprocess.run(["pdftotext", "-layout", "-f", str(n), "-l", str(n), str(pdf), "-"],
                              capture_output=True, text=True, timeout=120).stdout
        fonts_out = subprocess.run(["pdffonts", "-f", str(n), "-l", str(n), str(pdf)], capture_output=True,
                                   text=True, timeout=120).stdout
        fonts = sorted({l.split()[0] for l in fonts_out.splitlines()[2:] if l.split()})
        pages.append({"page": n, "chars": len(re.sub(r"\s", "", text)), "image_cover": round(cover.get(n, 0.0), 3),
                      "invisible_text": False, "fonts": fonts, "text": text})
    return pages


class NoBackend(Exception):
    pass


METHOD_ENV = "CB_TEXT_LAYER_METHOD"  # tests force the poppler fallback on a host that has PyMuPDF


def analyse(pdf: Path) -> dict:
    try:
        if os.environ.get(METHOD_ENV) == "poppler":
            raise ImportError("poppler forced")
        import fitz  # noqa: F401
        method, raw = "pymupdf", _pymupdf(pdf)
    except ImportError:
        if not all(shutil.which(t) for t in ("pdfinfo", "pdfimages", "pdftotext", "pdffonts")):
            raise NoBackend("neither PyMuPDF nor poppler (pdfinfo/pdfimages/pdftotext/pdffonts) is available")
        method, raw = "poppler", _poppler(pdf)
    pages = []
    for p in raw:
        ocr_font = any(OCR_FONT_RE.search(f) for f in p["fonts"])
        kind = classify(p["chars"], p["image_cover"], p["invisible_text"], ocr_font)
        pages.append({"page": p["page"], "kind": kind, "chars": p["chars"], "image_cover": p["image_cover"],
                      "invisible_text": p["invisible_text"], "ocr_font": ocr_font, "fonts": p["fonts"],
                      "glyph_anomaly_lines": glyph_anomalies(p["text"]) if kind == "born_digital" else []})
    summary = {k: [p["page"] for p in pages if p["kind"] == k] for k in ("born_digital", "embedded_ocr", "absent")}
    return {"tool": "text_layer_kind", "version": "1", "file": pdf.name, "sha256": _sha256(pdf), "method": method,
            "pages": pages, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    pdf = Path(a.pdf)
    if not pdf.is_file():
        print(json.dumps({"error": f"{pdf} not found"}), file=sys.stderr)
        return 2
    try:
        doc = analyse(pdf)
    except NoBackend as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 3
    except Exception as e:  # unreadable / encrypted PDF → the worker writes a stub (phase1 §4.2)
        print(json.dumps({"error": f"cannot read the PDF: {type(e).__name__}: {e}"}), file=sys.stderr)
        return 2
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
