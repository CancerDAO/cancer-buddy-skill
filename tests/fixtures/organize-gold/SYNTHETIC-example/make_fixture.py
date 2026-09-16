#!/usr/bin/env python3
"""Generate the one synthetic gold page. No real data, no binary committed to git.

Writes `page-001.pdf` beside this file: a born-digital single page carrying exactly the
values annotated in `page-001.expected.frontmatter.yaml`. Born-digital on purpose — it is
the only kind of page whose ground truth can be asserted independently of any model, by
reading the embedded text layer back out.

    python3 make_fixture.py [--out DIR]

Exit codes: 0 written · 1 PyMuPDF unavailable · 2 bad invocation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LINES = [
    (72, 90, "SYNTHETIC CLINIC — BLOOD COUNT REPORT", 14),
    (72, 120, "Report date 2026-03-15", 11),
    (72, 145, "Accession SYN-0000001", 11),
    (72, 180, "WBC        3.21   10^9/L    ref 3.50-9.50", 11),
    (72, 205, "HGB         128   g/L       ref 130-175", 11),
    (72, 230, "PLT         185   10^9/L    ref 125-350", 11),
    (72, 275, "CEA        25.3   ng/mL     ref 0.00-5.00", 11),
    (72, 320, "Reviewed by: (synthetic — no signatory)", 10),
]


def build(out_dir: Path) -> Path:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF is required to generate the synthetic page", file=sys.stderr)
        raise SystemExit(1)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text, size in LINES:
        page.insert_text((x, y), text, fontsize=size)
    out = out_dir / "page-001.pdf"
    doc.save(str(out))
    doc.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="make_fixture.py", description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args(argv)
    out_dir = Path(args.out).resolve()
    if not out_dir.is_dir():
        print(f"ERROR: {out_dir} is not a directory", file=sys.stderr)
        return 2
    print(f"wrote {build(out_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
