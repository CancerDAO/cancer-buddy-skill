#!/usr/bin/env python3
"""Adversarial validator for cancer-buddy chart output (stdlib only, fail-closed).

Run on EVERY chart before it reaches a patient — channel B files directly, and
the chart fragments of the 段D summary via --html. It assumes the generator is
wrong and tries to prove it, rather than confirming the happy path.

Checks
  (a) print-safe        — no <script>/<canvas>/<embed>/<object>/<iframe>/
                          <foreignObject>, no on*= handlers, no javascript: URI.
                          A patient prints these, screenshots them into a family
                          chat, and forwards them to a second-opinion clinician;
                          anything that renders differently in those three places
                          is a defect, and anything executable in a medical-record
                          file is a trust problem the patient should not have to
                          reason about.
  (b) zero external     — no http(s) reference except the SVG XML namespace
                          (a namespace declaration is not a network fetch).
                          A file that needs the network shows a broken chart to
                          exactly the patients least able to debug it.
  (c) type floor        — every font-size >= 8pt. Patients with cancer skew
                          older than 60 and print these charts.
  (d) palette lock      — every colour must come from the CancerDAO token table.
                          One stray hex is how a design system dies.
  (e) red restraint     — the critical red may not appear more often than the
                          number of source-flagged critical values declared via
                          --critical-count (default 0). Out-of-range gets amber
                          outline, never red fill.
  (f) no green          — green reads as "good", which is a verdict.
  (g) card anatomy      — title / reading note / figure / source line all present
                          (channel B only).
  (h) verdict floor     — the title and reading note carry no verdict phrase.
  (i) well-formed       — every <svg> parses as XML.

Exit codes: 0 ok · 2 bad invocation · 1 one or more checks failed.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chart_core import (  # noqa: E402
    AMBER, AMBER_BG, BAND, CARD, CARD_ALT, CRIT, CRIT_BG, INK, LADDER, MUTED,
    MUTED_DEEP, PRIMARY, PRIMARY_HI, RULE, FS_MIN,
)
from render_chart import verdict_violations  # noqa: E402

ALLOWED_COLOURS = {c.lower() for c in (
    [INK, MUTED, MUTED_DEEP, PRIMARY, PRIMARY_HI, AMBER, AMBER_BG, CRIT,
     CRIT_BG, CARD, CARD_ALT, RULE, BAND] + LADDER
)} | {"none", "#fff", "#ffffff", "currentcolor", "transparent"}

FORBIDDEN_TAGS = ("script", "canvas", "embed", "object", "iframe", "foreignObject")
NAMESPACE_OK = "http://www.w3.org/2000/svg"
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}")
FONTSIZE_ATTR_RE = re.compile(r'font-size="([\d.]+)"')
FONTSIZE_CSS_RE = re.compile(r"font-size:\s*([\d.]+)pt")
SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S)
GREENISH = re.compile(r"#(?:[0-9a-f]{0,2})(?:[89a-f][0-9a-f])(?:[0-9a-f]{0,2})", re.I)


def check(path: Path, critical_count: int, channel_b: bool):
    errs, warns = [], []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"cannot read {path}: {e}"], []

    # (a) print-safe
    for tag in FORBIDDEN_TAGS:
        if re.search(rf"<\s*{tag}\b", text, re.I):
            errs.append(f"(a) forbidden tag <{tag}> — charts must be static inline SVG")
    # Not `\son[a-z]+=`: an injected handler can land right after a '>' rather
    # than after whitespace. Anchor on "not preceded by a letter/hyphen" so
    # `>onclick=` is caught while `comparison=` and `data-on=` are not.
    if re.search(r"(?<![a-zA-Z\-])on[a-z]{2,}\s*=", text, re.I):
        errs.append("(a) inline event handler (on*=) present")
    if re.search(r"javascript:", text, re.I):
        errs.append("(a) javascript: URI present")

    # (b) zero external
    for url in set(re.findall(r"https?://[^\"'\s>]+", text)):
        if url.rstrip("/") != NAMESPACE_OK:
            errs.append(f"(b) external reference {url!r} — output must be self-contained")

    # (c) type floor
    sizes = [float(s) for s in FONTSIZE_ATTR_RE.findall(text)]
    sizes += [float(s) for s in FONTSIZE_CSS_RE.findall(text)]
    for s in sizes:
        if s < FS_MIN - 1e-9:
            errs.append(f"(c) font-size {s}pt below the {FS_MIN}pt floor")
    if not sizes:
        warns.append("(c) no font-size found — chart has no labels at all?")

    # (d) palette lock
    for hexv in set(h.lower() for h in HEX_RE.findall(text)):
        if hexv not in ALLOWED_COLOURS:
            errs.append(f"(d) colour {hexv} is outside the CancerDAO token table")

    # (e) red restraint
    n_red = len(re.findall(re.escape(CRIT), text, re.I))
    if n_red > critical_count:
        errs.append(
            f"(e) critical red {CRIT} used {n_red}x but only {critical_count} "
            f"source-flagged critical value(s) declared — out-of-range must use "
            f"the amber outline, not red")

    # (f) no green
    for hexv in set(h.lower() for h in HEX_RE.findall(text)):
        if hexv in ALLOWED_COLOURS:
            continue
        if GREENISH.fullmatch(hexv):
            errs.append(f"(f) green-ish colour {hexv} — green reads as a verdict")

    # (g) card anatomy + (h) verdict floor  [channel B only]
    if channel_b:
        title = re.search(r"<h1>(.*?)</h1>", text, re.S)
        sub = re.search(r'class="sub">(.*?)</div>', text, re.S)
        for name, m in (("title <h1>", title), ("reading note .sub", sub),
                        ("figure .fig", re.search(r'class="fig"', text)),
                        ("source line .src", re.search(r'class="src"', text))):
            if not m:
                errs.append(f"(g) card anatomy incomplete — missing {name}")
        authored = [m.group(1) for m in (title, sub) if m]
        for t, phrase in verdict_violations(*authored):
            errs.append(f"(h) verdict phrase {phrase!r} in {t.strip()[:60]!r}")

    # (i) well-formed SVG
    for i, frag in enumerate(SVG_RE.findall(text)):
        try:
            ET.fromstring(frag)
        except ET.ParseError as e:
            errs.append(f"(i) svg #{i} is not well-formed XML: {e}")

    return errs, warns


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed validator for clinical charts.")
    ap.add_argument("paths", nargs="+", help="chart HTML/SVG files to validate")
    ap.add_argument("--critical-count", type=int, default=0,
                    help="number of values the SOURCE REPORT flagged critical (default 0)")
    ap.add_argument("--fragment", action="store_true",
                    help="validate an SVG fragment (skips the card-anatomy checks)")
    args = ap.parse_args()

    total = 0
    for p in args.paths:
        errs, warns = check(Path(p), args.critical_count, channel_b=not args.fragment)
        for w in warns:
            print(f"WARN  {p}: {w}")
        for e in errs:
            print(f"FAIL  {p}: {e}", file=sys.stderr)
        total += len(errs)
        if not errs:
            print(f"ok    {p}")
    if total:
        print(f"\n{total} check(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
